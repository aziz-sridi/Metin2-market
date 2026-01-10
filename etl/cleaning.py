"""Pandas-based cleaning utilities for raw source data.

The course guideline requires data cleaning with Pandas.
This module cleans/normalizes raw JSON arrays before extraction.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def clean_market_json_array(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clean and normalize raw market items using Pandas.

    - Drops rows without a valid `vnum`
    - Normalizes numeric fields (prices, enhancement)
    - Ensures `name` is a string
    - Deduplicates on `vnum` (keeps the last occurrence)

    Returns a list of dicts safe to pass into the extractor.
    """
    if not raw_items:
        return []

    df = pd.DataFrame(raw_items)

    # Ensure expected columns exist (avoid KeyErrors in conversions)
    # metin2alerts payload commonly uses camelCase: yangPrice / wonPrice.
    for col in [
        "vnum",
        "name",
        "yang_price",
        "won_price",
        "yangPrice",
        "wonPrice",
        "yang",
        "won",
        "enhancement_level",
    ]:
        if col not in df.columns:
            df[col] = None

    # Normalize and coalesce prices
    df["yang_price"] = pd.to_numeric(
        df["yang_price"].fillna(df["yangPrice"]).fillna(df["yang"]),
        errors="coerce",
    ).fillna(0).astype("int64")
    df["won_price"] = pd.to_numeric(
        df["won_price"].fillna(df["wonPrice"]).fillna(df["won"]),
        errors="coerce",
    ).fillna(0).astype("int64")

    # Normalize identifiers
    df["vnum"] = pd.to_numeric(df["vnum"], errors="coerce")
    df = df[df["vnum"].notna()]
    df["vnum"] = df["vnum"].astype("int64")

    # Text cleanup
    df["name"] = df["name"].fillna("Unknown Item").astype(str)

    # Reasonable defaults
    df["enhancement_level"] = pd.to_numeric(df["enhancement_level"], errors="coerce").fillna(0).astype("int64")

    # Do NOT deduplicate by vnum: a single vnum can have many concurrent listings.
    # If a stable listing id is present, we can deduplicate on it.
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"], keep="last")

    return df.to_dict(orient="records")
