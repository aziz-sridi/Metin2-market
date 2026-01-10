"""Reference data API routes.

Serves English-only static reference data synced under `data/external/m2_data/en`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter()


class CategoryOption(BaseModel):
    id: str
    label: str


class EnchantmentOption(BaseModel):
    id: str
    label: str


def _static_en_dir() -> Path:
    base = Path(os.getenv("EXTERNAL_STATIC_OUTPUT_DIR", "./data/external"))
    return base / "m2_data" / "en"


def _load_json(path: Path) -> Dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Static reference file not found: {path.as_posix()}",
        ) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Static reference file is not valid JSON: {path.as_posix()}",
        ) from exc


@router.get("/categories", response_model=List[CategoryOption])
async def list_categories() -> List[CategoryOption]:
    """Return the category list used by the legacy UI (English-only)."""

    site_lang_path = _static_en_dir() / "site_lang.json"
    data = _load_json(site_lang_path)

    categories = data.get("categories")
    if not isinstance(categories, dict):
        raise HTTPException(status_code=503, detail="site_lang.json is missing 'categories'")

    # Preserve the original JSON order (Python 3.7+ dicts keep insertion order)
    return [CategoryOption(id=str(k), label=str(v)) for k, v in categories.items()]


@router.get("/enchantments", response_model=List[EnchantmentOption])
async def list_enchantments() -> List[EnchantmentOption]:
    """Return known stat/enchantment labels (English-only)."""

    stat_map_path = _static_en_dir() / "stat_map.json"
    data = _load_json(stat_map_path)

    if not isinstance(data, dict):
        raise HTTPException(status_code=503, detail="stat_map.json has unexpected format")

    def _sort_key(kv: Tuple[str, object]) -> int:
        key = kv[0]
        try:
            return int(str(key))
        except ValueError:
            return 10**9

    items = sorted(data.items(), key=_sort_key)
    return [EnchantmentOption(id=str(k), label=str(v)) for k, v in items]
