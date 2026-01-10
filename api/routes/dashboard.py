"""Backend endpoints used by the React web application.

This module exposes JSON APIs under `/api/dashboard/*` consumed by the Vite + React
frontend (search, history, equipment analysis, deals, KPI data, etc.).

Note: The legacy server-rendered HTML dashboard at `/dashboard` has been removed.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import APIRouter, Body, Query
from pydantic import BaseModel
from sqlalchemy import create_engine

from config.settings import config


router = APIRouter()


EQUIPMENT_TYPES = {"ITEM_WEAPON", "ITEM_ARMOR"}

_ITEM_NAMES_CACHE: Optional[Dict[int, str]] = None
_STAT_LABELS_CACHE: Optional[Dict[int, str]] = None


def _load_item_names_map() -> Dict[int, str]:
    global _ITEM_NAMES_CACHE
    if _ITEM_NAMES_CACHE is not None:
        return _ITEM_NAMES_CACHE

    # Static reference data synced at startup.
    # metin2_warehouse/api/routes/dashboard.py -> metin2_warehouse/
    root = Path(__file__).resolve().parents[2]
    p = root / "data" / "external" / "m2_data" / "en" / "item_names.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        # file is like {"180": "Poison Sword+0", ...}
        _ITEM_NAMES_CACHE = {int(k): str(v) for k, v in (raw or {}).items()}
    except Exception:
        _ITEM_NAMES_CACHE = {}

    return _ITEM_NAMES_CACHE


def _load_stat_labels_map() -> Dict[int, str]:
    """Load stat_id -> human label mapping (English) from static reference files."""
    global _STAT_LABELS_CACHE
    if _STAT_LABELS_CACHE is not None:
        return _STAT_LABELS_CACHE

    # Static reference data synced at startup.
    # metin2_warehouse/api/routes/dashboard.py -> metin2_warehouse/
    root = Path(__file__).resolve().parents[2]
    p = root / "data" / "external" / "m2_data" / "en" / "stat_map.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            _STAT_LABELS_CACHE = {int(k): str(v) for k, v in raw.items() if v is not None}
        else:
            _STAT_LABELS_CACHE = {}
    except Exception:
        _STAT_LABELS_CACHE = {}

    return _STAT_LABELS_CACHE


def _engine():
    return create_engine(config.get_db_connection_string_sqlalchemy())


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def _parse_vnum_list(raw: str) -> List[int]:
    if not raw:
        return []
    out: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    # de-dup preserving order
    seen = set()
    deduped = []
    for v in out:
        if v in seen:
            continue
        seen.add(v)
        deduped.append(v)
    return deduped


def _parse_bonus_pairs(raw: str) -> List[Tuple[int, int]]:
    """Parse bonuses from text like: `71:10,72:5`"""
    pairs: List[Tuple[int, int]] = []
    if not raw:
        return pairs
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            continue
        a, b = part.split(":", 1)
        try:
            stat_id = int(a.strip())
            value = int(b.strip())
        except ValueError:
            continue
        pairs.append((stat_id, value))
    return pairs


def _bonus_where_clause(prefix: str, *, stat_id_param: str, min_value_param: str) -> str:
    # Checks any of the 7 attribute slots.
    # Example: (fia.attribute_1_stat_id = %(sid0)s AND fia.attribute_1_value >= %(min0)s) OR ...
    return "(" + " OR ".join(
        [
            f"({prefix}.attribute_{k}_stat_id = %({stat_id_param})s AND {prefix}.attribute_{k}_value >= %({min_value_param})s)"
            for k in range(1, 8)
        ]
    ) + ")"


def _query_item_search(engine, q: str, limit: int = 30) -> pd.DataFrame:
    if not q:
        return pd.DataFrame(columns=["item_vnum", "item_name", "item_type"])

    query = """
        SELECT item_vnum, item_name, item_type
        FROM dim_item
        WHERE item_name ILIKE %(like)s
        ORDER BY item_name ASC
        LIMIT %(limit)s;
    """
    df = pd.read_sql_query(query, engine, params={"like": f"%{q}%", "limit": limit})

    # Also search the static name map so users can select items that haven't shown
    # up in market listings yet (e.g. enhancement levels +0..+9).
    name_map = _load_item_names_map()
    ql = q.strip().lower()
    if ql and name_map:
        seen = set()
        if not df.empty:
            try:
                seen = set(int(v) for v in df["item_vnum"].tolist())
            except Exception:
                seen = set()

        extras: List[Dict[str, Any]] = []
        for vnum, name in name_map.items():
            if vnum in seen:
                continue
            if ql in str(name).lower():
                extras.append({"item_vnum": int(vnum), "item_name": str(name), "item_type": "ITEM_UNKNOWN"})
                if len(extras) >= max(0, limit - (0 if df.empty else len(df))):
                    # early stop; we'll still sort after concat
                    pass

        if extras:
            df2 = pd.DataFrame(extras)
            df = pd.concat([df, df2], ignore_index=True)

    if df.empty:
        return df

    df = df.sort_values(["item_name", "item_vnum"], ascending=[True, True]).head(limit)
    return df


def _query_deals(engine, limit: int = 30) -> pd.DataFrame:
    query = """
        SELECT
            di.item_vnum,
            di.item_name,
            dt.full_date,
            fui.current_price_yang,
            fui.estimated_fair_value_yang,
            fui.undervaluation_percentage,
            fui.potential_profit_yang,
            fui.deal_rating
        FROM fact_undervalued_items fui
        JOIN dim_item di ON di.item_key = fui.item_key
        JOIN dim_time dt ON dt.time_key = fui.time_key
        WHERE fui.current_price_yang IS NOT NULL
        ORDER BY dt.full_date DESC, fui.potential_profit_yang DESC
        LIMIT %(limit)s;
    """
    return pd.read_sql_query(query, engine, params={"limit": limit})


def _query_non_equipment_price_history(
    engine,
    item_vnums: List[int],
    *,
    days: int = 60,
    server_id: Optional[int] = None,
    category_id: Optional[str] = None,
    enchantments: Optional[List[Tuple[int, int]]] = None,
    enchant_mode: str = "AND",
) -> pd.DataFrame:
    if not item_vnums:
        return pd.DataFrame(columns=[
            "item_vnum",
            "item_name",
            "full_date",
            "min_price_yang",
            "avg_price_yang",
            "min_price_count",
            "median_lowest5_yang",
        ])

    where = [
        "di.item_vnum = ANY(%(item_vnums)s)",
        "di.item_type <> ALL(%(equipment_types)s)",
        "fmt.transaction_price_yang IS NOT NULL",
        "fmt.transaction_price_yang > 0",
        "dt.full_date >= (CURRENT_DATE - (%(days)s::int * INTERVAL '1 day'))",
        "(%(server_id)s IS NULL OR fmt.server_id = %(server_id)s)",
        "(%(category_id)s IS NULL OR fmt.category_id = %(category_id)s)",
    ]

    params: Dict[str, Any] = {
        "item_vnums": item_vnums,
        "equipment_types": list(EQUIPMENT_TYPES),
        "days": days,
        "server_id": server_id,
        "category_id": category_id,
    }

    ench = enchantments or []
    mode = (enchant_mode or "AND").upper()
    per_ench_clauses: List[str] = []
    for i, (stat_id, min_value) in enumerate(ench):
        sid_key = f"sid{i}"
        min_key = f"min{i}"
        params[sid_key] = int(stat_id)
        params[min_key] = int(min_value)
        per_ench_clauses.append(
            "(" +
            " OR ".join(
                [
                    f"(fia.attribute_{k}_stat_id = %({sid_key})s AND fia.attribute_{k}_value >= %({min_key})s)"
                    for k in range(1, 8)
                ]
            ) +
            ")"
        )

    if per_ench_clauses:
        if mode == "OR":
            where.append("(" + " OR ".join(per_ench_clauses) + ")")
        else:
            # Default AND
            where.extend(per_ench_clauses)

    # Use per-listing prices from fact_market_transaction. We avoid fact_price_history because
    # it isn't guaranteed populated.
    #
    # Required metric:
    # - lowest price
    # - how many listings at that lowest price
    # - if that count < 5, also compute median(lowest 5 prices)
    query = f"""
        WITH tx AS (
            SELECT
                di.item_vnum,
                di.item_name,
                di.item_type,
                dt.full_date,
                CEIL((fmt.transaction_price_yang::numeric) / GREATEST(COALESCE(fmt.quantity_traded, 1), 1))::bigint AS price_yang
            FROM fact_market_transaction fmt
            JOIN dim_item di ON di.item_key = fmt.item_key
            JOIN dim_time dt ON dt.time_key = fmt.time_key
            LEFT JOIN fact_item_attributes fia
              ON fia.item_key = fmt.item_key
             AND fia.time_key = fmt.time_key
             AND fia.recorded_timestamp = fmt.transaction_timestamp
            WHERE {' AND '.join(where)}
        ),
        day_min AS (
            SELECT item_vnum, full_date, MIN(price_yang) AS min_price_yang
            FROM tx
            GROUP BY item_vnum, full_date
        ),
        day_avg AS (
            SELECT item_vnum, full_date, AVG(price_yang) AS avg_price_yang
            FROM tx
            GROUP BY item_vnum, full_date
        ),
        min_counts AS (
            SELECT tx.item_vnum, tx.full_date, COUNT(*)::int AS min_price_count
            FROM tx
            JOIN day_min dm
              ON dm.item_vnum = tx.item_vnum
             AND dm.full_date = tx.full_date
             AND dm.min_price_yang = tx.price_yang
            GROUP BY tx.item_vnum, tx.full_date
        ),
        ranked AS (
            SELECT
                tx.item_vnum,
                tx.full_date,
                tx.price_yang,
                ROW_NUMBER() OVER (PARTITION BY tx.item_vnum, tx.full_date ORDER BY tx.price_yang ASC) AS rn
            FROM tx
        ),
        low5 AS (
            SELECT item_vnum, full_date, price_yang
            FROM ranked
            WHERE rn <= 5
        ),
        low5_median AS (
            SELECT
                item_vnum,
                full_date,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_yang) AS median_lowest5_yang
            FROM low5
            GROUP BY item_vnum, full_date
        )
        SELECT
            dm.item_vnum,
            (SELECT item_name FROM tx t2 WHERE t2.item_vnum = dm.item_vnum LIMIT 1) AS item_name,
            dm.full_date,
            dm.min_price_yang,
                        da.avg_price_yang,
            COALESCE(mc.min_price_count, 0) AS min_price_count,
            l5.median_lowest5_yang
        FROM day_min dm
                JOIN day_avg da
                    ON da.item_vnum = dm.item_vnum
                 AND da.full_date = dm.full_date
        LEFT JOIN min_counts mc
          ON mc.item_vnum = dm.item_vnum
         AND mc.full_date = dm.full_date
        LEFT JOIN low5_median l5
          ON l5.item_vnum = dm.item_vnum
         AND l5.full_date = dm.full_date
        ORDER BY dm.full_date ASC, dm.item_vnum ASC;
    """

    return pd.read_sql_query(
        query,
        engine,
        params=params,
    )


def _query_equipment_joined(engine, item_vnum: int, days: int = 30) -> pd.DataFrame:
    # Join transactions to attributes "per listing".
    #
    # Important: the ETL may assign a single batch timestamp to many rows (per sync),
    # which makes a raw timestamp-equality join produce a large Cartesian product.
    # To keep the API responsive and stable, we pair rows 1:1 using a row_number()
    # over a reasonable "listing identity" partition.
    query = """
        WITH tx AS (
            SELECT
                fmt.transaction_key,
                fmt.item_key,
                fmt.time_key,
                fmt.transaction_timestamp,
                CEIL((fmt.transaction_price_yang::numeric) / GREATEST(COALESCE(fmt.quantity_traded, 1), 1))::bigint AS transaction_price_yang,
                fmt.enhancement_level,
                fmt.server_id,
                fmt.seller_name,
                fmt.job_id,
                fmt.category_code,
                fmt.category_id,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        fmt.item_key,
                        fmt.time_key,
                        fmt.transaction_timestamp,
                        COALESCE(fmt.server_id, -1),
                        COALESCE(fmt.seller_name, ''),
                        COALESCE(fmt.job_id, -1),
                        COALESCE(fmt.category_code, ''),
                        COALESCE(fmt.category_id, '')
                    ORDER BY fmt.transaction_key
                ) AS rn
            FROM fact_market_transaction fmt
            JOIN dim_item di ON di.item_key = fmt.item_key
            JOIN dim_time dt ON dt.time_key = fmt.time_key
            WHERE di.item_vnum = %(item_vnum)s
              AND fmt.transaction_price_yang IS NOT NULL
              AND fmt.transaction_price_yang > 0
              AND dt.full_date >= (CURRENT_DATE - (%(days)s::int * INTERVAL '1 day'))
        ),
        attrs AS (
            SELECT
                fia.attribute_key,
                fia.item_key,
                fia.time_key,
                fia.recorded_timestamp,
                fia.server_id,
                fia.seller_name,
                fia.job_id,
                fia.category_code,
                fia.category_id,
                fia.attribute_1_stat_id, fia.attribute_1_value,
                fia.attribute_2_stat_id, fia.attribute_2_value,
                fia.attribute_3_stat_id, fia.attribute_3_value,
                fia.attribute_4_stat_id, fia.attribute_4_value,
                fia.attribute_5_stat_id, fia.attribute_5_value,
                fia.attribute_6_stat_id, fia.attribute_6_value,
                fia.attribute_7_stat_id, fia.attribute_7_value,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        fia.item_key,
                        fia.time_key,
                        fia.recorded_timestamp,
                        COALESCE(fia.server_id, -1),
                        COALESCE(fia.seller_name, ''),
                        COALESCE(fia.job_id, -1),
                        COALESCE(fia.category_code, ''),
                        COALESCE(fia.category_id, '')
                    ORDER BY fia.attribute_key
                ) AS rn
            FROM fact_item_attributes fia
        )
        SELECT
            dt.full_date,
            tx.transaction_timestamp,
            tx.transaction_price_yang AS price_yang,
            tx.enhancement_level,
            a.attribute_1_stat_id, a.attribute_1_value,
            a.attribute_2_stat_id, a.attribute_2_value,
            a.attribute_3_stat_id, a.attribute_3_value,
            a.attribute_4_stat_id, a.attribute_4_value,
            a.attribute_5_stat_id, a.attribute_5_value,
            a.attribute_6_stat_id, a.attribute_6_value,
            a.attribute_7_stat_id, a.attribute_7_value
        FROM tx
        JOIN dim_time dt ON dt.time_key = tx.time_key
        JOIN attrs a
          ON a.item_key = tx.item_key
         AND a.time_key = tx.time_key
         AND a.recorded_timestamp = tx.transaction_timestamp
         AND COALESCE(a.server_id, -1) = COALESCE(tx.server_id, -1)
         AND COALESCE(a.seller_name, '') = COALESCE(tx.seller_name, '')
         AND COALESCE(a.job_id, -1) = COALESCE(tx.job_id, -1)
         AND COALESCE(a.category_code, '') = COALESCE(tx.category_code, '')
         AND COALESCE(a.category_id, '') = COALESCE(tx.category_id, '')
         AND a.rn = tx.rn
        ORDER BY tx.transaction_timestamp ASC, tx.transaction_key ASC;
    """
    return pd.read_sql_query(query, engine, params={"item_vnum": item_vnum, "days": days})


def _unpivot_attrs(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["transaction_timestamp", "price_yang", "stat_id", "value"])  # type: ignore

    rows = []
    for _, r in df.iterrows():
        for i in range(1, 8):
            sid = r.get(f"attribute_{i}_stat_id")
            val = r.get(f"attribute_{i}_value")
            if pd.isna(sid) or pd.isna(val):
                continue
            rows.append(
                {
                    "transaction_timestamp": r["transaction_timestamp"],
                    "price_yang": r["price_yang"],
                    "enhancement_level": r.get("enhancement_level", 0),
                    "stat_id": int(sid),
                    "value": int(val),
                }
            )
    return pd.DataFrame(rows)


def _bonus_impact_table(df_attrs: pd.DataFrame, top_n: int = 12) -> pd.DataFrame:
    if df_attrs.empty:
        return pd.DataFrame(
            columns=[
                "stat_id",
                "count",
                "median_price_with",
                "median_price_without",
                "premium",
                "avg_value",
                "median_value",
            ]
        )  # type: ignore

    # Compute premiums by presence of stat_id, using MEDIAN prices (more robust than averages).
    all_prices = df_attrs[["transaction_timestamp", "price_yang"]].drop_duplicates()
    tx_price = all_prices.set_index("transaction_timestamp")["price_yang"]

    present = df_attrs.groupby("stat_id")["transaction_timestamp"].nunique().rename("count")

    med_with = df_attrs.groupby("stat_id")["price_yang"].median().rename("median_price_with")

    value_stats = (
        df_attrs.groupby("stat_id")["value"]
        .agg(["mean", "median"])
        .rename(columns={"mean": "avg_value", "median": "median_value"})
    )

    # For avg_without: transactions that do NOT have that stat.
    tx_stats = df_attrs.groupby("transaction_timestamp")["stat_id"].apply(set)

    med_without_map: Dict[int, float] = {}
    for stat_id in present.index.tolist():
        mask = ~tx_stats.apply(lambda s: stat_id in s)
        ts_without = tx_stats[mask].index
        if len(ts_without) == 0:
            med_without_map[int(stat_id)] = float("nan")
            continue
        try:
            med_without_map[int(stat_id)] = float(tx_price.loc[ts_without].median())
        except Exception:
            med_without_map[int(stat_id)] = float("nan")

    out = pd.concat([present, med_with, value_stats], axis=1).reset_index()
    out["median_price_without"] = out["stat_id"].map(med_without_map)
    out["premium"] = out["median_price_with"] - out["median_price_without"]

    out = out.sort_values(["premium", "count"], ascending=[False, False]).head(top_n)
    return out


def _examples_for_stat(df_attrs: pd.DataFrame, stat_id: int, top_k: int = 3) -> List[Dict[str, Any]]:
    if df_attrs.empty:
        return []
    # Filter to transactions that have the stat_id, then show a few examples
    tx_with = df_attrs[df_attrs["stat_id"] == stat_id][["transaction_timestamp", "price_yang", "value"]]
    if tx_with.empty:
        return []
    # Prefer highest priced examples
    tx_with = tx_with.sort_values(["price_yang"], ascending=False).head(top_k)
    return [
        {
            "transaction_timestamp": str(r["transaction_timestamp"]),
            "price_yang": int(r["price_yang"]),
            "value": int(r["value"]),
        }
        for _, r in tx_with.iterrows()
    ]


@router.get("/api/dashboard/search")
def api_search(q: str = Query(default="", min_length=0), limit: int = Query(default=30, ge=1, le=200)):
    engine = _engine()
    df = _query_item_search(engine, q, limit=limit)
    return {"results": [] if df.empty else df.to_dict(orient="records")}


@router.get("/api/dashboard/non-equipment/history")
def api_non_equipment_history(
    item_vnums: str = Query(default="", description="Comma-separated vnums"),
    days: int = Query(default=60, ge=1, le=365),
    server_id: Optional[int] = Query(default=None),
    category_id: Optional[str] = Query(default=None),
    enchantments: str = Query(default="", description="min thresholds as stat:min,stat:min"),
    enchant_mode: str = Query(default="AND", description="AND|OR"),
):
    engine = _engine()
    vnums = _parse_vnum_list(item_vnums)
    ench = _parse_bonus_pairs(enchantments)
    df = _query_non_equipment_price_history(
        engine,
        vnums,
        days=days,
        server_id=server_id,
        category_id=category_id,
        enchantments=ench,
        enchant_mode=enchant_mode,
    )
    series = []
    for item_vnum, g in df.groupby("item_vnum"):
        g = g.sort_values("full_date")
        series.append(
            {
                "item_vnum": int(item_vnum),
                "item_name": str(g["item_name"].iloc[0]),
                "dates": [str(d) for d in g["full_date"].tolist()],
                "min_price_yang": [int(round(float(x))) if not pd.isna(x) else None for x in g["min_price_yang"].tolist()],
                "avg_price_yang": [int(round(float(x))) if not pd.isna(x) else None for x in g["avg_price_yang"].tolist()],
                "min_price_count": [int(x) if not pd.isna(x) else None for x in g["min_price_count"].tolist()],
                "median_lowest5_yang": [
                    float(x) if not pd.isna(x) else None for x in g["median_lowest5_yang"].tolist()
                ],
            }
        )
    return {"days": days, "series": series}


@router.get("/api/dashboard/equipment/bonus-impact")
def api_equipment_bonus_impact(
    item_vnum: int = Query(..., ge=1),
    days: int = Query(default=30, ge=1, le=365),
    top_n: int = Query(default=12, ge=1, le=50),
    examples_per_bonus: int = Query(default=3, ge=0, le=10),
):
    engine = _engine()
    stat_labels = _load_stat_labels_map()
    eq_df = _query_equipment_joined(engine, item_vnum, days=days)
    attrs_df = _unpivot_attrs(eq_df)
    impact = _bonus_impact_table(attrs_df, top_n=top_n)
    rows: List[Dict[str, Any]] = []
    for _, r in impact.iterrows():
        sid = int(r["stat_id"])
        stat_name = stat_labels.get(sid) or f"Stat {sid}"
        typical_value = None
        if "median_value" in r and not pd.isna(r["median_value"]):
            try:
                typical_value = int(round(float(r["median_value"])))
            except Exception:
                typical_value = None
        row = {
            "stat_id": sid,
            "stat_name": stat_name,
            "typical_value": typical_value,
            "count": int(r["count"]),
            "median_price_with": float(r["median_price_with"]) if not pd.isna(r["median_price_with"]) else None,
            "median_price_without": float(r["median_price_without"]) if not pd.isna(r["median_price_without"]) else None,
            "premium": float(r["premium"]) if not pd.isna(r["premium"]) else None,
        }
        if examples_per_bonus > 0:
            row["examples"] = _examples_for_stat(attrs_df, sid, top_k=examples_per_bonus)
        rows.append(row)

    return {
        "item_vnum": item_vnum,
        "days": days,
        "top_n": top_n,
        "rows": rows,
    }


@router.get("/api/dashboard/equipment/estimate")
def api_equipment_estimate(
    item_vnum: int = Query(..., ge=1),
    bonuses: str = Query(default="", description="stat:value,stat:value"),
    days: int = Query(default=30, ge=1, le=365),
):
    pairs = _parse_bonus_pairs(bonuses)
    if not pairs:
        return {"item_vnum": item_vnum, "bonuses": [], "estimated_price_yang": None, "model": None}

    engine = _engine()
    eq_df = _query_equipment_joined(engine, item_vnum, days=days)
    attrs_df = _unpivot_attrs(eq_df)
    intercept, coefs = _fit_price_model(attrs_df)

    pred_log = intercept
    used = []
    for sid, val in pairs:
        coef = coefs.get(sid, 0.0)
        used.append({"stat_id": sid, "value": val, "coef": coef})
        pred_log += coef * float(val)

    est = int(max(0.0, float(np.expm1(pred_log))))
    return {
        "item_vnum": item_vnum,
        "days": days,
        "bonuses": used,
        "estimated_price_yang": est,
        "model": {
            "intercept": intercept,
            "coefficients": coefs,
        },
    }


# ============================================================================
# New: KPI + Alert Query + Bonus Distribution APIs (JSON)
# ============================================================================


class AlertBonusFilter(BaseModel):
    stat_id: int
    min_value: int = 0


class AlertQueryRequest(BaseModel):
    # Server scope
    server_ids: Optional[List[int]] = None

    # Item scope
    item_vnums: Optional[List[int]] = None
    # Optional substring filter on dim_item.item_name (case-insensitive)
    item_name_query: Optional[str] = None
    # any | non_equipment | equipment
    item_scope: str = "any"

    # Price / listing constraints
    max_price_yang: Optional[int] = None
    min_enhancement_level: Optional[int] = None
    max_enhancement_level: Optional[int] = None
    min_quantity: Optional[int] = None

    # Bonus constraints (equipment only, but we allow it generally; it will just match none for non-equipment)
    bonuses: Optional[List[AlertBonusFilter]] = None
    bonus_mode: str = "AND"  # AND | OR

    # Time window (ISO8601 string). If omitted, defaults to last 24h.
    since_iso: Optional[str] = None
    limit: int = 200


@router.get("/api/dashboard/kpis")
def api_kpis(
    days: int = Query(default=1, ge=1, le=30),
    server_id: Optional[int] = Query(default=None),
):
    """Basic KPI numbers for a player-facing dashboard.

    Uses the already-ingested transaction facts. Avoids relying on fact_price_history.
    """

    engine = _engine()
    try:
        query = """
            WITH tx AS (
              SELECT
                fmt.transaction_timestamp,
                fmt.server_id,
                di.item_vnum,
                di.item_type,
                fmt.transaction_price_yang AS price_yang
              FROM fact_market_transaction fmt
              JOIN dim_item di ON di.item_key = fmt.item_key
              JOIN dim_time dt ON dt.time_key = fmt.time_key
              WHERE dt.full_date >= (CURRENT_DATE - (%(days)s::int * INTERVAL '1 day'))
                AND fmt.transaction_price_yang IS NOT NULL
                AND fmt.transaction_price_yang > 0
                AND (%(server_id)s IS NULL OR fmt.server_id = %(server_id)s)
            )
            SELECT
              COUNT(*)::int AS listings,
              COUNT(DISTINCT item_vnum)::int AS unique_items,
              COUNT(*) FILTER (WHERE item_type = ANY(%(equipment_types)s))::int AS equipment_listings,
              COUNT(*) FILTER (WHERE item_type <> ALL(%(equipment_types)s))::int AS non_equipment_listings,
              PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_yang) AS median_price_yang
            FROM tx;
        """

        df = pd.read_sql_query(
            query,
            engine,
            params={
                "days": days,
                "server_id": server_id,
                "equipment_types": list(EQUIPMENT_TYPES),
            },
        )

        if df.empty:
            return {
                "days": days,
                "server_id": server_id,
                "listings": 0,
                "unique_items": 0,
                "equipment_listings": 0,
                "non_equipment_listings": 0,
                "median_price_yang": None,
            }

        row = df.iloc[0]
        return {
            "days": days,
            "server_id": server_id,
            "listings": int(row["listings"] or 0),
            "unique_items": int(row["unique_items"] or 0),
            "equipment_listings": int(row["equipment_listings"] or 0),
            "non_equipment_listings": int(row["non_equipment_listings"] or 0),
            "median_price_yang": int(row["median_price_yang"]) if not pd.isna(row["median_price_yang"]) else None,
        }
    finally:
        engine.dispose()


@router.post("/api/dashboard/query/listings")
def api_query_listings(payload: AlertQueryRequest = Body(...)):
    """Run a player-defined query (block builder) against recent listings.

    This is intentionally NOT SQL. The frontend sends structured filters.
    """

    item_scope = (payload.item_scope or "any").strip().lower()
    bonus_mode = (payload.bonus_mode or "AND").strip().upper()

    since_iso = _as_str(payload.since_iso, "")
    # Default: last 24 hours
    if not since_iso:
        since_iso = ""  # handled in SQL below

    limit = int(payload.limit or 200)
    limit = max(1, min(limit, 1000))

    where = [
        "fmt.transaction_price_yang IS NOT NULL",
        "fmt.transaction_price_yang > 0",
    ]

    params: Dict[str, Any] = {
        "equipment_types": list(EQUIPMENT_TYPES),
        "limit": limit,
    }

    # Time filter
    if since_iso:
        where.append("fmt.transaction_timestamp >= %(since_ts)s")
        params["since_ts"] = since_iso
    else:
        where.append("fmt.transaction_timestamp >= (NOW() - INTERVAL '24 hours')")

    # Server filter
    if payload.server_ids:
        server_ids = [int(x) for x in payload.server_ids if _as_int(x) is not None]
        if server_ids:
            where.append("fmt.server_id = ANY(%(server_ids)s)")
            params["server_ids"] = server_ids

    # Item vnums
    if payload.item_vnums:
        vnums = [int(x) for x in payload.item_vnums if _as_int(x) is not None]
        if vnums:
            where.append("di.item_vnum = ANY(%(item_vnums)s)")
            params["item_vnums"] = vnums

    # Item name filter (used by Alerts UI when user types a name but does not select vnums)
    if payload.item_name_query:
        q = str(payload.item_name_query).strip()
        if q:
            where.append("di.item_name ILIKE %(item_name_like)s")
            params["item_name_like"] = f"%{q}%"

    # Item scope
    if item_scope == "equipment":
        where.append("di.item_type = ANY(%(equipment_types)s)")
    elif item_scope == "non_equipment":
        where.append("di.item_type <> ALL(%(equipment_types)s)")

    # Price constraints
    if payload.max_price_yang is not None:
        where.append("fmt.transaction_price_yang <= %(max_price)s")
        params["max_price"] = int(payload.max_price_yang)

    # Enhancement constraints
    if payload.min_enhancement_level is not None:
        where.append("COALESCE(fmt.enhancement_level, 0) >= %(min_plus)s")
        params["min_plus"] = int(payload.min_enhancement_level)
    if payload.max_enhancement_level is not None:
        where.append("COALESCE(fmt.enhancement_level, 0) <= %(max_plus)s")
        params["max_plus"] = int(payload.max_enhancement_level)

    # Quantity constraints
    if payload.min_quantity is not None:
        where.append("COALESCE(fmt.quantity_traded, 1) >= %(min_qty)s")
        params["min_qty"] = int(payload.min_quantity)

    # Bonus constraints (joined per listing using timestamp equality)
    bonus_filters = payload.bonuses or []
    bonus_clauses: List[str] = []
    for idx, bf in enumerate(bonus_filters):
        sid_key = f"sid{idx}"
        min_key = f"min{idx}"
        params[sid_key] = int(bf.stat_id)
        params[min_key] = int(bf.min_value or 0)
        bonus_clauses.append(_bonus_where_clause("fia", stat_id_param=sid_key, min_value_param=min_key))

    if bonus_clauses:
        if bonus_mode == "OR":
            where.append("(" + " OR ".join(bonus_clauses) + ")")
        else:
            where.extend(bonus_clauses)

    query = f"""
        SELECT
          fmt.transaction_timestamp,
          fmt.server_id,
          di.item_vnum,
          di.item_name,
          di.item_type,
          fmt.transaction_price_yang AS price_yang,
          fmt.enhancement_level,
          fmt.seller_name,
          fmt.category_id,
          fmt.quantity_traded,
          fia.attribute_1_stat_id, fia.attribute_1_value,
          fia.attribute_2_stat_id, fia.attribute_2_value,
          fia.attribute_3_stat_id, fia.attribute_3_value,
          fia.attribute_4_stat_id, fia.attribute_4_value,
          fia.attribute_5_stat_id, fia.attribute_5_value,
          fia.attribute_6_stat_id, fia.attribute_6_value,
          fia.attribute_7_stat_id, fia.attribute_7_value
        FROM fact_market_transaction fmt
        JOIN dim_item di ON di.item_key = fmt.item_key
        JOIN dim_time dt ON dt.time_key = fmt.time_key
        LEFT JOIN fact_item_attributes fia
          ON fia.item_key = fmt.item_key
         AND fia.time_key = fmt.time_key
         AND fia.recorded_timestamp = fmt.transaction_timestamp
        WHERE {' AND '.join(where)}
        ORDER BY fmt.transaction_timestamp DESC
        LIMIT %(limit)s;
    """

    engine = _engine()
    try:
        df = pd.read_sql_query(query, engine, params=params)
        if df.empty:
            return {"results": [], "count": 0}

        results: List[Dict[str, Any]] = []
        for _, r in df.iterrows():
            bonuses: List[Dict[str, Any]] = []
            for i in range(1, 8):
                sid = r.get(f"attribute_{i}_stat_id")
                val = r.get(f"attribute_{i}_value")
                if pd.isna(sid) or pd.isna(val):
                    continue
                bonuses.append({"stat_id": int(sid), "value": int(val)})

            results.append(
                {
                    "transaction_timestamp": str(r["transaction_timestamp"]),
                    "server_id": _as_int(r.get("server_id"), None),
                    "item_vnum": int(r["item_vnum"]),
                    "item_name": str(r["item_name"]),
                    "item_type": str(r["item_type"]),
                    "price_yang": int(r["price_yang"]) if not pd.isna(r["price_yang"]) else None,
                    "enhancement_level": _as_int(r.get("enhancement_level"), 0) or 0,
                    "seller_name": _as_str(r.get("seller_name"), ""),
                    "category_id": _as_str(r.get("category_id"), ""),
                    "quantity": _as_int(r.get("quantity_traded"), 1) or 1,
                    "bonuses": bonuses,
                }
            )

        return {"results": results, "count": len(results)}
    finally:
        engine.dispose()


@router.get("/api/dashboard/analytics/bonus-price-distribution")
def api_bonus_price_distribution(
    stat_id: int = Query(..., ge=1),
    min_value: int = Query(default=0, ge=0),
    days: int = Query(default=30, ge=1, le=365),
    server_id: Optional[int] = Query(default=None),
    equipment_only: bool = Query(default=True),
    bins: int = Query(default=20, ge=5, le=80),
):
    """Histogram of prices for listings that have a given bonus.

    Intended for player analytics like “price distribution of bonus X across items”.
    """

    where = [
        "fmt.transaction_price_yang IS NOT NULL",
        "fmt.transaction_price_yang > 0",
        "dt.full_date >= (CURRENT_DATE - (%(days)s::int * INTERVAL '1 day'))",
        "(%(server_id)s IS NULL OR fmt.server_id = %(server_id)s)",
    ]
    params: Dict[str, Any] = {
        "days": days,
        "server_id": server_id,
        "equipment_types": list(EQUIPMENT_TYPES),
        "sid": int(stat_id),
        "minv": int(min_value),
    }

    if equipment_only:
        where.append("di.item_type = ANY(%(equipment_types)s)")

    # Must have stat in any slot
    where.append(_bonus_where_clause("fia", stat_id_param="sid", min_value_param="minv"))

    query = f"""
        SELECT fmt.transaction_price_yang AS price_yang
        FROM fact_market_transaction fmt
        JOIN dim_item di ON di.item_key = fmt.item_key
        JOIN dim_time dt ON dt.time_key = fmt.time_key
        JOIN fact_item_attributes fia
          ON fia.item_key = fmt.item_key
         AND fia.time_key = fmt.time_key
         AND fia.recorded_timestamp = fmt.transaction_timestamp
        WHERE {' AND '.join(where)};
    """

    engine = _engine()
    try:
        df = pd.read_sql_query(query, engine, params=params)
        if df.empty:
            return {
                "stat_id": stat_id,
                "min_value": min_value,
                "days": days,
                "server_id": server_id,
                "equipment_only": equipment_only,
                "count": 0,
                "bins": [],
                "counts": [],
                "summary": None,
            }

        prices = df["price_yang"].astype(float).to_numpy()
        prices = prices[np.isfinite(prices)]
        if prices.size == 0:
            return {
                "stat_id": stat_id,
                "min_value": min_value,
                "days": days,
                "server_id": server_id,
                "equipment_only": equipment_only,
                "count": 0,
                "bins": [],
                "counts": [],
                "summary": None,
            }

        # Histogram with linear bins.
        hist_counts, bin_edges = np.histogram(prices, bins=int(bins))
        summary = {
            "min": int(np.min(prices)),
            "p25": int(np.percentile(prices, 25)),
            "median": int(np.percentile(prices, 50)),
            "p75": int(np.percentile(prices, 75)),
            "max": int(np.max(prices)),
            "avg": float(np.mean(prices)),
        }

        return {
            "stat_id": stat_id,
            "min_value": min_value,
            "days": days,
            "server_id": server_id,
            "equipment_only": equipment_only,
            "count": int(prices.size),
            "bins": [float(x) for x in bin_edges.tolist()],
            "counts": [int(x) for x in hist_counts.tolist()],
            "summary": summary,
        }
    finally:
        engine.dispose()


@router.get("/api/dashboard/deals")
def api_deals(limit: int = Query(default=30, ge=1, le=200)):
    engine = _engine()
    df = _query_deals(engine, limit=limit)
    return {"results": [] if df.empty else df.to_dict(orient="records")}


def _fit_price_model(df_attrs: pd.DataFrame, max_features: int = 15) -> Tuple[float, Dict[int, float]]:
    """Fit a simple linear model on log1p(price):

    log1p(price) = intercept + sum_j coef[stat_id_j] * value

    Returns (intercept, coef_by_stat_id)
    """

    if df_attrs.empty:
        return 0.0, {}

    # Build per-transaction feature vectors
    tx_price = df_attrs.groupby("transaction_timestamp")["price_yang"].first()
    tx_features: Dict[Any, Dict[int, float]] = {}
    for ts, group in df_attrs.groupby("transaction_timestamp"):
        feats: Dict[int, float] = {}
        for sid, val in zip(group["stat_id"].astype(int), group["value"].astype(float)):
            feats[int(sid)] = feats.get(int(sid), 0.0) + float(val)
        tx_features[ts] = feats

    # Choose top stat_ids by frequency
    freq = df_attrs.groupby("stat_id")["transaction_timestamp"].nunique().sort_values(ascending=False)
    selected = [int(s) for s in freq.head(max_features).index.tolist()]
    if not selected:
        return float(np.log1p(float(tx_price.median()))), {}

    # Assemble X, y
    ts_list = list(tx_price.index)
    X = np.zeros((len(ts_list), 1 + len(selected)), dtype=float)
    X[:, 0] = 1.0
    y = np.log1p(tx_price.values.astype(float))

    for i, ts in enumerate(ts_list):
        feats = tx_features.get(ts, {})
        for j, sid in enumerate(selected):
            X[i, 1 + j] = feats.get(sid, 0.0)

    # Ridge-stabilized least squares
    lam = 1e-3
    XtX = X.T @ X + lam * np.eye(X.shape[1])
    Xty = X.T @ y
    beta = np.linalg.solve(XtX, Xty)

    intercept = float(beta[0])
    coefs = {sid: float(beta[1 + j]) for j, sid in enumerate(selected)}
    return intercept, coefs


class EnchantmentFilter(BaseModel):
    stat_id: int
    min_value: int = 0


class PriceEstimateRequest(BaseModel):
    item_vnum: int
    server_id: Optional[int] = None
    category_id: Optional[str] = None
    days: int = 30
    enchant_mode: str = "AND"
    enchantments: List[EnchantmentFilter] = []


def _query_item_prices(
    engine,
    *,
    item_vnum: int,
    days: int,
    server_id: Optional[int],
    category_id: Optional[str],
    enchantments: List[EnchantmentFilter],
    enchant_mode: str = "AND",
) -> pd.DataFrame:
    """Return listing prices for one item, optionally filtered by enchantments.

    Enchantment matching is AND across requested enchantments; each enchantment matches if it
    appears in any attribute slot with value >= min_value.
    """

    where = [
        "di.item_vnum = %(item_vnum)s",
        "fmt.transaction_price_yang IS NOT NULL",
        "fmt.transaction_price_yang > 0",
        "dt.full_date >= (CURRENT_DATE - (%(days)s::int * INTERVAL '1 day'))",
        "(%(server_id)s IS NULL OR fmt.server_id = %(server_id)s)",
        "(%(category_id)s IS NULL OR fmt.category_id = %(category_id)s)",
    ]
    params: Dict[str, Any] = {
        "item_vnum": int(item_vnum),
        "days": int(days),
        "server_id": server_id,
        "category_id": category_id,
    }

    per_ench_clauses: List[str] = []
    for i, ench in enumerate(enchantments or []):
        sid_key = f"sid{i}"
        min_key = f"min{i}"
        params[sid_key] = int(ench.stat_id)
        params[min_key] = max(0, int(ench.min_value or 0))

        per_ench_clauses.append(
            "(" +
            " OR ".join(
                [
                    f"(fia.attribute_{k}_stat_id = %({sid_key})s AND fia.attribute_{k}_value >= %({min_key})s)"
                    for k in range(1, 8)
                ]
            ) +
            ")"
        )

    mode = (enchant_mode or "AND").upper()
    if per_ench_clauses:
        if mode == "OR":
            where.append("(" + " OR ".join(per_ench_clauses) + ")")
        else:
            where.extend(per_ench_clauses)

    query = f"""
        SELECT
            dt.full_date,
            fmt.transaction_timestamp,
            fmt.transaction_price_yang AS price_yang
        FROM fact_market_transaction fmt
        JOIN dim_item di ON di.item_key = fmt.item_key
        JOIN dim_time dt ON dt.time_key = fmt.time_key
        LEFT JOIN fact_item_attributes fia
          ON fia.item_key = fmt.item_key
         AND fia.time_key = fmt.time_key
         AND fia.recorded_timestamp = fmt.transaction_timestamp
        WHERE {' AND '.join(where)}
        ORDER BY fmt.transaction_timestamp DESC;
    """

    return pd.read_sql_query(query, engine, params=params)


def _median_price_for_type(engine, *, item_type: str, days: int, server_id: Optional[int], category_id: Optional[str]) -> Optional[int]:
    query = """
        SELECT
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fmt.transaction_price_yang) AS median_price_yang
        FROM fact_market_transaction fmt
        JOIN dim_item di ON di.item_key = fmt.item_key
        JOIN dim_time dt ON dt.time_key = fmt.time_key
        WHERE di.item_type = %(item_type)s
          AND fmt.transaction_price_yang IS NOT NULL
          AND fmt.transaction_price_yang > 0
          AND dt.full_date >= (CURRENT_DATE - (%(days)s::int * INTERVAL '1 day'))
          AND (%(server_id)s IS NULL OR fmt.server_id = %(server_id)s)
          AND (%(category_id)s IS NULL OR fmt.category_id = %(category_id)s);
    """
    df = pd.read_sql_query(
        query,
        engine,
        params={
            "item_type": item_type,
            "days": int(days),
            "server_id": server_id,
            "category_id": category_id,
        },
    )
    if df.empty:
        return None
    val = df["median_price_yang"].iloc[0]
    if pd.isna(val):
        return None
    return int(val)


def _median_price_global(engine, *, days: int, server_id: Optional[int], category_id: Optional[str]) -> Optional[int]:
    query = """
        SELECT
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fmt.transaction_price_yang) AS median_price_yang
        FROM fact_market_transaction fmt
        JOIN dim_time dt ON dt.time_key = fmt.time_key
        WHERE fmt.transaction_price_yang IS NOT NULL
          AND fmt.transaction_price_yang > 0
          AND dt.full_date >= (CURRENT_DATE - (%(days)s::int * INTERVAL '1 day'))
          AND (%(server_id)s IS NULL OR fmt.server_id = %(server_id)s)
          AND (%(category_id)s IS NULL OR fmt.category_id = %(category_id)s);
    """
    df = pd.read_sql_query(
        query,
        engine,
        params={
            "days": int(days),
            "server_id": server_id,
            "category_id": category_id,
        },
    )
    if df.empty:
        return None
    val = df["median_price_yang"].iloc[0]
    if pd.isna(val):
        return None
    return int(val)


@router.post("/api/dashboard/item/estimate")
def api_item_estimate(payload: PriceEstimateRequest = Body(...)):
    """Estimate an item's price from observed listings.

    Behavior:
    - If listings exist that match ALL requested enchantments (with min values), return the median of those.
    - If no matching listings exist but the item has listings, fall back to the item's overall median.
    - If the item has no listings at all, fall back to the median of its item_type; then to global median.

    Also returns the latest-day observed minimum price (matching filters) when available.
    """

    days = int(max(1, min(365, payload.days)))
    enchantments = payload.enchantments or []

    engine = _engine()

    df_all = _query_item_prices(
        engine,
        item_vnum=payload.item_vnum,
        days=days,
        server_id=payload.server_id,
        category_id=payload.category_id,
        enchantments=[],
        enchant_mode=payload.enchant_mode,
    )
    df_match = _query_item_prices(
        engine,
        item_vnum=payload.item_vnum,
        days=days,
        server_id=payload.server_id,
        category_id=payload.category_id,
        enchantments=enchantments,
        enchant_mode=payload.enchant_mode,
    )

    def _latest_day_min(df: pd.DataFrame) -> Optional[int]:
        if df.empty:
            return None
        latest = df["full_date"].max()
        day_df = df[df["full_date"] == latest]
        if day_df.empty:
            return None
        return int(day_df["price_yang"].min())

    observed_min_match = _latest_day_min(df_match)
    observed_min_any = _latest_day_min(df_all)

    exists_any = not df_all.empty
    match_count = int(len(df_match))

    estimated_price: Optional[int] = None
    basis = None

    if not df_match.empty:
        estimated_price = int(df_match["price_yang"].median())
        basis = "matched_median"
    elif not df_all.empty:
        estimated_price = int(df_all["price_yang"].median())
        basis = "item_median_fallback"
    else:
        # No listings for this item: fall back to item_type median if we know the item
        item_type_df = pd.read_sql_query(
            "SELECT item_type FROM dim_item WHERE item_vnum = %(item_vnum)s LIMIT 1;",
            engine,
            params={"item_vnum": int(payload.item_vnum)},
        )
        item_type = None
        if not item_type_df.empty and not pd.isna(item_type_df["item_type"].iloc[0]):
            item_type = str(item_type_df["item_type"].iloc[0])

        if item_type:
            type_median = _median_price_for_type(
                engine,
                item_type=item_type,
                days=days,
                server_id=payload.server_id,
                category_id=payload.category_id,
            )
            if type_median is not None:
                estimated_price = int(type_median)
                basis = "type_median_fallback"
            else:
                global_median = _median_price_global(
                    engine,
                    days=days,
                    server_id=payload.server_id,
                    category_id=payload.category_id,
                )
                estimated_price = int(global_median) if global_median is not None else None
                basis = "global_median_fallback"
        else:
            global_median = _median_price_global(
                engine,
                days=days,
                server_id=payload.server_id,
                category_id=payload.category_id,
            )
            estimated_price = int(global_median) if global_median is not None else None
            basis = "global_median_fallback"

    return {
        "item_vnum": int(payload.item_vnum),
        "server_id": payload.server_id,
        "category_id": payload.category_id,
        "days": days,
        "enchant_mode": (payload.enchant_mode or "AND").upper(),
        "enchantments": [
            {"stat_id": int(e.stat_id), "min_value": int(max(0, e.min_value or 0))} for e in enchantments
        ],
        "exists_in_window": bool(exists_any),
        "match_count": match_count,
        "observed_min_price_yang": observed_min_match,
        "observed_min_price_any_yang": observed_min_any,
        "estimated_price_yang": estimated_price,
        "estimate_basis": basis,
    }


