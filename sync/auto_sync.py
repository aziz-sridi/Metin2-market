"""Automatic external market fetch + warehouse load.

This script:
- Fetches external market JSON via Python requests
- Confirms new fetches by comparing a local sync state file (hash)
- Runs ETL only when the fetched data changed

Run (Windows):
  python -m sync.auto_sync --server-id 502

The sync state file (default: sync_state.json) is updated every cycle so you can
confirm the last fetch time, hash, counts, and last ETL status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from etl.pipeline import ETLPipeline


DEFAULT_BASE_URL = "https://metin2alerts.com"
DEFAULT_URL_TEMPLATE = DEFAULT_BASE_URL + "/store/public/data/{server_id}.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_of_json(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _sorted_pairs(value: Any) -> Tuple[Tuple[int, int], ...]:
    """Normalize attrs-like arrays to a sorted tuple of (stat_id, value)."""
    if not isinstance(value, list):
        return tuple()
    out: List[Tuple[int, int]] = []
    for x in value:
        if isinstance(x, (list, tuple)) and len(x) >= 2:
            out.append((_as_int(x[0]), _as_int(x[1])))
    out.sort()
    return tuple(out)


def _elem_key(value: Any) -> Tuple[int, Tuple[int, ...]]:
    # elem is typically [stat_id, [values...]]
    if not isinstance(value, list) or len(value) < 2:
        return (0, tuple())
    stat_id = _as_int(value[0])
    vals = value[1] if isinstance(value[1], list) else []
    return (stat_id, tuple(_as_int(v) for v in vals))


def _listing_fingerprint(obj: Any) -> Tuple[Any, ...]:
    """Fingerprint a listing so exact duplicates can be removed.

    Designed to handle metin2alerts payload variations.
    """
    if not isinstance(obj, dict):
        return ("__invalid__",)

    vnum = _as_int(obj.get("vnum", obj.get("Vnum", 0)))

    # Listing context
    seller = _as_str(obj.get("seller") or obj.get("seller_name") or obj.get("sellerName")).strip().lower()
    job_id = _as_int(obj.get("job", obj.get("job_id", obj.get("jobId", 0))))
    category = _as_str(obj.get("category") or obj.get("category_code") or obj.get("categoryCode")).strip()
    quantity = _as_int(obj.get("quantity", obj.get("count", obj.get("amount", 1))), 1)

    # Enhancement/sockets
    enhancement = _as_int(obj.get("enhancement_level", obj.get("enhancementLevel", obj.get("plus", obj.get("enhancement", 0)))))
    sockets = obj.get("sockets", obj.get("Sockets", []))
    if not isinstance(sockets, list):
        sockets = []
    sockets_key = tuple(_as_int(x) for x in sockets)

    # Price
    yang = _as_int(obj.get("yang_price", obj.get("yangPrice", obj.get("yang", 0))))
    won = _as_int(obj.get("won_price", obj.get("wonPrice", obj.get("won", 0))))

    # Bonuses
    attrs_key = _sorted_pairs(obj.get("attrs", []))
    rand_key = _sorted_pairs(obj.get("rand", []))
    elem_key = _elem_key(obj.get("elem", []))

    # Special
    changelook = _as_int(obj.get("changelookvnum", 0))
    absorbed = _as_int(obj.get("absorbed_vnum", 0))

    return (
        vnum,
        seller,
        job_id,
        category,
        quantity,
        enhancement,
        sockets_key,
        yang,
        won,
        attrs_key,
        rand_key,
        elem_key,
        changelook,
        absorbed,
    )


def dedupe_market_payload(items: List[Any]) -> List[Any]:
    """Remove exact duplicates while preserving order."""
    seen = set()
    out: List[Any] = []
    for obj in items:
        key = _listing_fingerprint(obj)
        if key in seen:
            continue
        seen.add(key)
        out.append(obj)
    return out


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@dataclass
class SyncConfig:
    server_id: int
    url_template: str
    state_file: Path
    interval_min_minutes: int
    interval_max_minutes: int
    timeout_seconds: int


def fetch_market_data(url: str, timeout_seconds: int) -> Tuple[int, Any]:
    resp = requests.get(url, timeout=timeout_seconds)
    return resp.status_code, resp.json()


def run_once(cfg: SyncConfig) -> int:
    url = cfg.url_template.format(server_id=cfg.server_id)

    prev_state = _read_json(cfg.state_file) or {}
    prev_hash = prev_state.get("last_hash")

    state: Dict[str, Any] = {
        "server_id": cfg.server_id,
        "source_url": url,
        "interval_minutes_range": [cfg.interval_min_minutes, cfg.interval_max_minutes],
        "last_fetch_at": _utc_now_iso(),
        "last_http_status": None,
        "last_item_count": None,
        "last_hash": prev_hash,
        "last_change_detected_at": prev_state.get("last_change_detected_at"),
        "last_load_at": prev_state.get("last_load_at"),
        "last_load_status": prev_state.get("last_load_status", "never"),
        "last_error": None,
        "run_count": int(prev_state.get("run_count", 0)) + 1,
        "change_count": int(prev_state.get("change_count", 0)),
    }

    try:
        status, data = fetch_market_data(url, cfg.timeout_seconds)
        state["last_http_status"] = status

        if status != 200:
            state["last_error"] = f"HTTP {status}"
            state["last_load_status"] = "skipped"
            _atomic_write_json(cfg.state_file, state)
            return 2

        if not isinstance(data, list):
            state["last_error"] = "Unexpected payload: expected JSON array"
            state["last_load_status"] = "skipped"
            _atomic_write_json(cfg.state_file, state)
            return 2

        # Deduplicate exact replicas within a single fetch.
        # This prevents inflating counts when identical listings are present multiple times.
        raw_count = len(data)
        data = dedupe_market_payload(data)
        state["last_item_count_raw"] = raw_count
        state["last_item_count"] = len(data)

        new_hash = _sha256_of_json(data)
        changed = (prev_hash != new_hash)

        state["last_hash"] = new_hash
        state["changed"] = bool(changed)

        if not changed:
            state["last_load_status"] = "skipped_no_change"
            _atomic_write_json(cfg.state_file, state)
            return 0

        state["last_change_detected_at"] = _utc_now_iso()
        state["change_count"] = int(state["change_count"]) + 1

        pipeline = ETLPipeline(server_id=cfg.server_id)
        ok = pipeline.run_full_pipeline(data)
        state["last_load_at"] = _utc_now_iso()
        state["last_load_status"] = "success" if ok else "failed"
        if not ok:
            state["last_error"] = "ETL pipeline failed"
            _atomic_write_json(cfg.state_file, state)
            return 1

        stats = pipeline.get_statistics()
        state["last_etl_stats"] = {
            "extracted_items": stats.get("extracted_items"),
            "undervalued_items": stats.get("undervalued_items"),
            "total_properties": stats.get("total_properties"),
            "transformation_timestamp": str(stats.get("transformation_timestamp")),
        }

        _atomic_write_json(cfg.state_file, state)
        return 0

    except Exception as e:
        state["last_error"] = str(e)
        state["last_load_status"] = "failed"
        _atomic_write_json(cfg.state_file, state)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-fetch external market data and load into PostgreSQL")
    parser.add_argument("--server-id", type=int, default=502, help="Metin2Alerts server id (default: 502)")
    parser.add_argument(
        "--url-template",
        type=str,
        default=DEFAULT_URL_TEMPLATE,
        help="Fetch URL template (must include {server_id})",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default="sync_state.json",
        help="Path to sync state file to confirm new fetches",
    )
    parser.add_argument("--min-minutes", type=int, default=10, help="Minimum minutes between fetches")
    parser.add_argument("--max-minutes", type=int, default=15, help="Maximum minutes between fetches")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--once", action="store_true", help="Fetch once and exit")

    args = parser.parse_args()

    if args.min_minutes <= 0 or args.max_minutes <= 0 or args.max_minutes < args.min_minutes:
        raise SystemExit("Invalid interval range: ensure 0 < min-minutes <= max-minutes")

    cfg = SyncConfig(
        server_id=args.server_id,
        url_template=args.url_template,
        state_file=Path(args.state_file),
        interval_min_minutes=args.min_minutes,
        interval_max_minutes=args.max_minutes,
        timeout_seconds=args.timeout,
    )

    if args.once:
        return run_once(cfg)

    # Continuous mode: sleep 10-15 minutes (random jitter) between cycles
    while True:
        rc = run_once(cfg)
        sleep_minutes = random.randint(cfg.interval_min_minutes, cfg.interval_max_minutes)
        sleep_seconds = sleep_minutes * 60
        print(f"[{_utc_now_iso()}] cycle_rc={rc} next_fetch_in={sleep_minutes}m state_file={cfg.state_file}")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
