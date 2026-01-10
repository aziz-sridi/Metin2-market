"""
Analytics API Routes
Endpoints for market analysis, trends, and insights
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from pathlib import Path
import json
import pandas as pd
from sqlalchemy import create_engine
from config.settings import config
import io
import base64
import matplotlib
matplotlib.use('Agg')   
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

router = APIRouter()


_ITEM_NAMES_CACHE: Optional[Dict[int, str]] = None


def _load_item_names_map() -> Dict[int, str]:
    global _ITEM_NAMES_CACHE
    if _ITEM_NAMES_CACHE is not None:
        return _ITEM_NAMES_CACHE

    # metin2_warehouse/api/routes/analytics.py -> metin2_warehouse/
    root = Path(__file__).resolve().parents[2]
    p = root / "data" / "external" / "m2_data" / "en" / "item_names.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        _ITEM_NAMES_CACHE = {int(k): str(v) for k, v in (raw or {}).items()}
    except Exception:
        _ITEM_NAMES_CACHE = {}

    return _ITEM_NAMES_CACHE


def _engine():
    return create_engine(config.get_db_connection_string_sqlalchemy())


_WON_TO_YANG = 100_000_000


def _format_yang(v: Any) -> str:
    if v is None:
        return ""
    try:
        x = float(v)
    except Exception:
        return ""

    sign = "-" if x < 0 else ""
    abs_i = int(abs(x))
    won = abs_i // _WON_TO_YANG
    yang = abs_i % _WON_TO_YANG

    if won <= 0:
        return f"{sign}{yang:,}y"
    if yang <= 0:
        return f"{sign}{won:,}w"
    return f"{sign}{won:,}w + {yang:,}y"


def _to_int_price(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        return int(round(float(v)))
    except Exception:
        return None


# Pydantic models
class PriceTrendInfo(BaseModel):
    item_vnum: int
    item_name: str
    period: str  # DAILY, WEEKLY, MONTHLY
    average_price: float
    min_price: int
    max_price: int
    price_change_percentage: float
    trend_direction: str  # UP, DOWN, STABLE
    volatility: float
    transaction_count: int


class UndervaluedItemInfo(BaseModel):
    item_vnum: int
    item_name: str
    current_price: int
    estimated_fair_value: int
    undervaluation_percentage: float
    confidence_score: float
    potential_profit: int
    deal_rating: str  # EXCELLENT, GOOD, FAIR, POOR
    roi_percentage: float


class MarketSnapshot(BaseModel):
    timestamp: datetime
    total_items_tracked: int
    total_transactions: int
    average_market_price: float
    price_volatility: float
    trending_items: List[str]


class DealOpportunity(BaseModel):
    item_vnum: int
    opportunity_type: str  # UNDERVALUED, RISING_DEMAND, STABLE_LOW_PRICE
    confidence: float
    description: str


# Routes

@router.get("/price-trends", response_model=List[PriceTrendInfo])
async def get_price_trends(
    item_type: Optional[str] = Query(None, description="Filter by item type"),
    period: str = Query("DAILY", description="DAILY, WEEKLY, or MONTHLY"),
    limit: int = Query(20, ge=1, le=100, description="Number of trends to return")
):
    """
    Get price trends for items
    
    Query parameters:
    - item_type: Optional filter by type
    - period: Analysis period (DAILY, WEEKLY, MONTHLY)
    - limit: Number of results
    """
    return []


@router.get("/undervalued-items", response_model=List[UndervaluedItemInfo])
async def get_undervalued_items(
    min_confidence: float = Query(50, ge=0, le=100, description="Minimum confidence score"),
    deal_rating: Optional[str] = Query(None, description="Filter by deal rating"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Identify undervalued items (buying opportunities)
    
    Query parameters:
    - min_confidence: Minimum confidence score (0-100)
    - deal_rating: Filter by EXCELLENT, GOOD, FAIR, or POOR
    - limit: Number of results
    """
    return []


@router.get("/item-min-price/{item_vnum}")
async def get_item_min_price(
    item_vnum: int
):
    """
    Get the minimum price for an item (works with single-day data)
    
    Path parameters:
    - item_vnum: The item's vnum (e.g., 30618 for moonstone, 80017 for voucher)
    """
    engine = _engine()
    
    # Per-sync aggregation (transaction_timestamp is set by the external sync loop).
    # We limit to recent sync groups for performance.
    query = """
        WITH s AS (
            SELECT
                di.item_vnum,
                di.item_name,
                fmt.transaction_timestamp AS sync_time,
                                MIN(CEIL((fmt.transaction_price_yang::numeric) / GREATEST(COALESCE(fmt.quantity_traded, 1), 1))) AS min_price,
                                AVG(CEIL((fmt.transaction_price_yang::numeric) / GREATEST(COALESCE(fmt.quantity_traded, 1), 1))) AS avg_price,
                                MAX(CEIL((fmt.transaction_price_yang::numeric) / GREATEST(COALESCE(fmt.quantity_traded, 1), 1))) AS max_price,
                COUNT(*) AS transaction_count
            FROM fact_market_transaction fmt
            JOIN dim_item di ON di.item_key = fmt.item_key
            WHERE di.item_vnum = %(vnum)s
              AND fmt.transaction_timestamp IS NOT NULL
                            AND fmt.transaction_price_yang IS NOT NULL
                            AND fmt.transaction_price_yang > 0
            GROUP BY di.item_vnum, di.item_name, fmt.transaction_timestamp
            ORDER BY fmt.transaction_timestamp DESC
            LIMIT 60
        )
        SELECT *
        FROM s
        ORDER BY sync_time DESC;
    """
    
    try:
        df = pd.read_sql_query(query, engine, params={"vnum": item_vnum})
        
        name_map = _load_item_names_map()

        if df.empty:
            return {
                "item_vnum": item_vnum,
                "item_name": name_map.get(item_vnum, "Unknown"),
                "latest_min_price": None,
                "avg_price": None,
                "max_price": None,
                "price_history": []
            }
        
        latest = df.iloc[0]
        
        display_name = name_map.get(item_vnum, str(latest["item_name"]))

        return {
            "item_vnum": item_vnum,
            "item_name": display_name,
            "latest_min_price": _to_int_price(latest["min_price"]),
            "avg_price": _to_int_price(latest["avg_price"]),
            "max_price": _to_int_price(latest["max_price"]),
            "transaction_count": int(latest["transaction_count"]),
            "latest_date": str(latest["sync_time"]),
            "price_history": [
                {
                    "date": str(row["sync_time"]),
                    "min_price": _to_int_price(row["min_price"]),
                    "avg_price": _to_int_price(row["avg_price"]),
                    "max_price": _to_int_price(row["max_price"]),
                    "transaction_count": int(row["transaction_count"])
                }
                for _, row in df.head(30).iterrows()
            ]
        }
    finally:
        engine.dispose()


@router.get("/dashboard-stats")
async def get_dashboard_stats():
    """
    Get key dashboard statistics for tracked items (vouchers and moonstones)
    """
    engine = _engine()
    
    # Track vouchers (80017) and moonstones (30618)
    tracked_items = [80017, 30618]
    
    stats = []
    
    name_map = _load_item_names_map()

    for vnum in tracked_items:
        query = """
            SELECT 
                di.item_vnum,
                di.item_name,
                fmt.transaction_timestamp AS sync_time,
                                MIN(CEIL((fmt.transaction_price_yang::numeric) / GREATEST(COALESCE(fmt.quantity_traded, 1), 1))) as min_price,
                                AVG(CEIL((fmt.transaction_price_yang::numeric) / GREATEST(COALESCE(fmt.quantity_traded, 1), 1))) as avg_price,
                COUNT(*) as transaction_count
            FROM fact_market_transaction fmt
            JOIN dim_item di ON di.item_key = fmt.item_key
            WHERE di.item_vnum = %(vnum)s
              AND fmt.transaction_timestamp IS NOT NULL
                            AND fmt.transaction_price_yang IS NOT NULL
                            AND fmt.transaction_price_yang > 0
            GROUP BY di.item_vnum, di.item_name, fmt.transaction_timestamp
            ORDER BY fmt.transaction_timestamp DESC
            LIMIT 25;
        """
        
        df = pd.read_sql_query(query, engine, params={"vnum": vnum})
        
        if not df.empty:
            latest = df.iloc[0]
            
            # Calculate 7-day trend if we have enough data
            trend = "stable"
            if len(df) >= 2:
                price_change = float(df.iloc[0]["min_price"]) - float(df.iloc[-1]["min_price"])
                if price_change > 0:
                    trend = "up"
                elif price_change < 0:
                    trend = "down"
            
            stats.append({
                "item_vnum": vnum,
                "item_name": name_map.get(vnum, str(latest["item_name"])),
                "current_min_price": _to_int_price(latest["min_price"]),
                "current_avg_price": _to_int_price(latest["avg_price"]),
                "transaction_count": int(latest["transaction_count"]),
                "trend": trend,
                "price_history": [
                    {
                        "date": str(row["sync_time"]),
                        "min_price": _to_int_price(row["min_price"]),
                        "avg_price": _to_int_price(row["avg_price"])
                    }
                    for _, row in df.iterrows()
                ]
            })
    
    engine.dispose()
    return {"tracked_items": stats}


@router.get("/dashboard-chart/{item_vnum}")
async def get_dashboard_chart(item_vnum: int):
    """
    Generate matplotlib chart for dashboard tracking
    Returns base64 encoded PNG image
    """
    engine = _engine()
    
    # Per-sync chart: one point per sync timestamp.
    query = """
        WITH s AS (
            SELECT
                di.item_name,
                fmt.transaction_timestamp AS sync_time,
                MIN(CEIL((fmt.transaction_price_yang::numeric) / GREATEST(COALESCE(fmt.quantity_traded, 1), 1))) AS min_price,
                AVG(CEIL((fmt.transaction_price_yang::numeric) / GREATEST(COALESCE(fmt.quantity_traded, 1), 1))) AS avg_price
            FROM fact_market_transaction fmt
            JOIN dim_item di ON di.item_key = fmt.item_key
            WHERE di.item_vnum = %(vnum)s
              AND fmt.transaction_timestamp IS NOT NULL
                            AND fmt.transaction_price_yang IS NOT NULL
                            AND fmt.transaction_price_yang > 0
            GROUP BY di.item_name, fmt.transaction_timestamp
            ORDER BY fmt.transaction_timestamp DESC
            LIMIT 160
        )
        SELECT *
        FROM s
        ORDER BY sync_time ASC;
    """
    
    try:
        df = pd.read_sql_query(query, engine, params={"vnum": item_vnum})
        
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for item {item_vnum}")
        
        # Create matplotlib figure
        plt.figure(figsize=(10, 6))
        
        name_map = _load_item_names_map()

        dates = pd.to_datetime(df["sync_time"])
        min_prices = pd.to_numeric(df["min_price"], errors="coerce").where(lambda s: s > 0)
        avg_prices = pd.to_numeric(df.get("avg_price"), errors="coerce").where(lambda s: s > 0)

        plt.plot(dates, min_prices, marker='o', label='Min Price', linewidth=2, markersize=5)
        plt.plot(dates, avg_prices, marker='s', label='Avg Price', linewidth=2, markersize=4, alpha=0.7)
        
        plt.xlabel('Sync time', fontsize=12, fontweight='bold')
        plt.ylabel('Price', fontsize=12, fontweight='bold')
        title_name = name_map.get(item_vnum, str(df["item_name"].iloc[0]))
        plt.title(f'{title_name} - Price Tracking (per sync)', fontsize=14, fontweight='bold')
        plt.legend(loc='best')
        plt.grid(True, alpha=0.3)
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: _format_yang(v)))

        # Avoid misleading 0-baseline: set y-limits around observed prices.
        vals = pd.to_numeric(pd.concat([min_prices, avg_prices]), errors='coerce').dropna().values
        vals = vals[vals > 0]
        if len(vals) > 0:
            y_max = float(vals.max())
            pad_up = max(1.0, y_max * 0.04)
            ax.set_ylim(0, y_max + pad_up)

        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Convert plot to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        plt.close()
        
        return {
            "item_vnum": item_vnum,
            "item_name": title_name,
            "chart_data": f"data:image/png;base64,{image_base64}"
        }
    finally:
        engine.dispose()


@router.get("/market-snapshot", response_model=MarketSnapshot)
async def get_market_snapshot(
    date_param: Optional[date] = Query(None, description="Specific date (default: today)")
):
    """
    Get overall market snapshot for a specific date
    
    Query parameters:
    - date_param: Date to analyze (default: today)
    """
    return MarketSnapshot(
        timestamp=datetime.now(),
        total_items_tracked=0,
        total_transactions=0,
        average_market_price=0,
        price_volatility=0,
        trending_items=[]
    )


@router.get("/deal-opportunities", response_model=List[DealOpportunity])
async def get_deal_opportunities(
    min_confidence: float = Query(60, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get current market deal opportunities
    
    Query parameters:
    - min_confidence: Minimum confidence (0-100)
    - limit: Number of opportunities
    """
    return []


@router.get("/price-history/{item_vnum}", response_model=List[PriceTrendInfo])
async def get_item_price_history(
    item_vnum: int,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    period: str = Query("DAILY", description="Aggregation period")
):
    """
    Get price history for a specific item
    
    Path parameters:
    - item_vnum: Item vnum
    
    Query parameters:
    - days: Number of days to go back
    - period: DAILY, WEEKLY, or MONTHLY aggregation
    """
    return []


@router.get("/volatility-analysis", response_model=List[dict])
async def analyze_price_volatility(
    min_volatility: float = Query(5, ge=0, description="Minimum volatility %"),
    max_volatility: Optional[float] = Query(None, description="Maximum volatility %"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Find items with specific price volatility
    
    Query parameters:
    - min_volatility: Minimum volatility percentage
    - max_volatility: Maximum volatility percentage (optional)
    - limit: Number of results
    """
    return []


@router.get("/demand-analysis", response_model=List[dict])
async def analyze_market_demand(
    period: str = Query("WEEKLY", description="WEEKLY or MONTHLY"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Analyze market demand patterns
    
    Query parameters:
    - period: WEEKLY or MONTHLY analysis
    - limit: Number of items to return
    """
    return []


@router.get("/price-prediction/{item_vnum}", response_model=dict)
async def predict_future_price(
    item_vnum: int,
    days_ahead: int = Query(7, ge=1, le=90, description="Days ahead to predict")
):
    """
    Predict future price for an item based on historical trends
    
    Path parameters:
    - item_vnum: Item vnum
    
    Query parameters:
    - days_ahead: Number of days to predict ahead (1-90)
    """
    return {
        "item_vnum": item_vnum,
        "predicted_price": 0,
        "confidence": 0,
        "trend": "UNKNOWN"
    }


@router.get("/item-correlation/{item_vnum}", response_model=List[dict])
async def find_correlated_items(
    item_vnum: int,
    correlation_threshold: float = Query(0.7, ge=0, le=1),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Find items with correlated price movements
    
    Path parameters:
    - item_vnum: Reference item vnum
    
    Query parameters:
    - correlation_threshold: Minimum correlation (0-1)
    - limit: Number of related items
    """
    return []


@router.get("/market-efficiency", response_model=dict)
async def analyze_market_efficiency(
    item_type: Optional[str] = Query(None, description="Optional type filter")
):
    """
    Analyze market efficiency (pricing consistency)
    
    Query parameters:
    - item_type: Optional type to analyze
    """
    return {
        "market_efficiency_score": 0,
        "pricing_consistency": 0,
        "arbitrage_opportunities": 0,
        "analysis_timestamp": datetime.now()
    }


@router.post("/roi-simulation", response_model=dict)
async def simulate_roi(
    item_vnum: int = Query(..., description="Item to analyze"),
    buy_price: int = Query(..., description="Buying price in Yang"),
    holding_days: int = Query(7, ge=1, le=90, description="Days to hold")
):
    """
    Simulate return on investment for buying an item
    
    Query parameters:
    - item_vnum: Item to analyze
    - buy_price: Your buying price
    - holding_days: How many days you'll hold it
    """
    return {
        "item_vnum": item_vnum,
        "buy_price": buy_price,
        "predicted_sell_price": 0,
        "expected_roi": 0,
        "confidence": 0
    }
