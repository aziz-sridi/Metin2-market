"""Server configuration.

We intentionally limit this project to a small set of Metin2 servers.
Default: Europe (502) and Teutonia (71).

You can override via env var:
- EXTERNAL_SERVER_IDS="502,71"

Note: We keep legacy EXTERNAL_SERVER_ID support as a fallback.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_SERVER_IDS: List[int] = [502, 71]

# Optional labels used by UI or logs.
SERVER_LABELS: Dict[int, str] = {
    502: "Europe",
    71: "Teutonia",
}


def parse_server_ids(value: Optional[str]) -> List[int]:
    if value is None:
        return []

    parts = [p.strip() for p in str(value).split(",")]
    out: List[int] = []
    for p in parts:
        if not p:
            continue
        try:
            out.append(int(p))
        except Exception as e:
            raise ValueError(f"Invalid server id in EXTERNAL_SERVER_IDS: {p!r}") from e
    # de-dupe preserving order
    seen = set()
    uniq: List[int] = []
    for sid in out:
        if sid in seen:
            continue
        seen.add(sid)
        uniq.append(sid)
    return uniq


def allowed_server_ids() -> List[int]:
    # Preferred: EXTERNAL_SERVER_IDS="502,71"
    env_list = parse_server_ids(os.getenv("EXTERNAL_SERVER_IDS"))
    if env_list:
        return env_list

    # Back-compat: EXTERNAL_SERVER_ID=502
    one = os.getenv("EXTERNAL_SERVER_ID")
    if one:
        try:
            return [int(one)]
        except Exception:
            pass

    return list(DEFAULT_SERVER_IDS)


def validate_allowed_server_id(server_id: int) -> int:
    allowed = set(allowed_server_ids())
    if server_id not in allowed:
        raise ValueError(f"server_id {server_id} is not allowed (allowed: {sorted(allowed)})")
    return server_id


def market_state_file_for_server(base_state_file: Path, server_id: int) -> Path:
    """Derive a per-server state file path.

    If base_state_file contains "{server_id}", it is formatted.
    Otherwise we suffix the filename: sync_state.json -> sync_state_502.json
    """

    s = str(base_state_file)
    if "{server_id}" in s:
        return Path(s.format(server_id=server_id))

    # Keep extension; put suffix before extension.
    if base_state_file.suffix:
        return base_state_file.with_name(base_state_file.stem + f"_{server_id}" + base_state_file.suffix)

    return Path(s + f"_{server_id}")
