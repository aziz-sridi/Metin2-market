"""Static external data sync (Metin2Alerts m2_data).

This module downloads the static JSON reference files used for decoding / labeling
market data (e.g. stat maps, item names, descriptions).

Design decision (per project requirement): language is always English.

Remote source:
- https://metin2alerts.com/m2_data/en/*.json
- https://metin2alerts.com/m2_data/*.json (non-language files)

Local storage (default): ./data/external/m2_data/...
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests


DEFAULT_BASE_URL = "https://metin2alerts.com"
DEFAULT_LANGUAGE = "en"
DEFAULT_OUTPUT_DIR = Path("./data/external")
DEFAULT_STATE_FILE = Path("./sync_static_state.json")


STATIC_DATA_FILES: Dict[str, str] = {
    # Language-scoped files (forced to English)
    "stat_map": "/m2_data/en/stat_map.json",
    "item_names": "/m2_data/en/item_names.json",
    "itemdesc": "/m2_data/en/itemdesc.json",
    "site_lang": "/m2_data/en/site_lang.json",
    "mob_names": "/m2_data/en/mob_names.json",
    "pet_skills": "/m2_data/en/pet_skills.json",
    # Non-language files
    "proto_stat_map": "/m2_data/proto_stat_map.json",
    "item_proto": "/m2_data/item_proto.json",
    "item_icon": "/m2_data/item_icon.json",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


@dataclass(frozen=True)
class StaticSyncConfig:
    base_url: str = DEFAULT_BASE_URL
    output_dir: Path = DEFAULT_OUTPUT_DIR
    state_file: Path = DEFAULT_STATE_FILE
    timeout_seconds: int = 30


def _target_path_for(remote_path: str, output_dir: Path) -> Path:
    # remote_path looks like /m2_data/en/stat_map.json
    relative = remote_path.lstrip("/")
    return output_dir / relative


def fetch_one_json(url: str, timeout_seconds: int) -> Tuple[int, bytes]:
    resp = requests.get(url, timeout=timeout_seconds)
    return resp.status_code, resp.content


def sync_static_data(cfg: StaticSyncConfig) -> Dict[str, Any]:
    """Sync static JSON files.

    Returns a dict with per-file status and overall result.
    """

    prev_state = _read_json_file(cfg.state_file) or {}
    prev_hashes: Dict[str, str] = dict(prev_state.get("hashes") or {})

    result: Dict[str, Any] = {
        "base_url": cfg.base_url,
        "language": DEFAULT_LANGUAGE,
        "output_dir": str(cfg.output_dir),
        "last_run_at": _utc_now_iso(),
        "files": {},
        "changed": False,
        "error": None,
    }

    new_hashes: Dict[str, str] = {}

    try:
        for key, remote_path in STATIC_DATA_FILES.items():
            url = f"{cfg.base_url}{remote_path}"
            target = _target_path_for(remote_path, cfg.output_dir)

            status_code, body = fetch_one_json(url, cfg.timeout_seconds)
            if status_code != 200:
                result["files"][key] = {
                    "url": url,
                    "status": "failed",
                    "http_status": status_code,
                    "target": str(target),
                }
                continue

            # Validate JSON to avoid persisting HTML/errors
            try:
                json.loads(body.decode("utf-8"))
            except Exception:
                result["files"][key] = {
                    "url": url,
                    "status": "failed",
                    "http_status": status_code,
                    "target": str(target),
                    "error": "Invalid JSON payload",
                }
                continue

            digest = _sha256_bytes(body)
            new_hashes[key] = digest

            if prev_hashes.get(key) == digest and target.exists():
                result["files"][key] = {
                    "url": url,
                    "status": "skipped_no_change",
                    "http_status": status_code,
                    "target": str(target),
                    "sha256": digest,
                }
                continue

            _atomic_write_bytes(target, body)
            result["files"][key] = {
                "url": url,
                "status": "updated",
                "http_status": status_code,
                "target": str(target),
                "sha256": digest,
            }
            result["changed"] = True

        state = {
            "last_run_at": result["last_run_at"],
            "base_url": cfg.base_url,
            "language": DEFAULT_LANGUAGE,
            "output_dir": str(cfg.output_dir),
            "hashes": new_hashes,
        }
        _atomic_write_json(cfg.state_file, state)

        return result

    except Exception as e:
        result["error"] = str(e)
        return result
