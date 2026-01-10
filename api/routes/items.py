"""
Items API Routes
Endpoints for querying item information and properties
"""

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from sqlalchemy import create_engine
import pandas as pd
from config.settings import config

router = APIRouter()


def _engine():
    return create_engine(config.get_db_connection_string_sqlalchemy())


# Pydantic models for request/response
class ItemBasicInfo(BaseModel):
    item_vnum: int
    item_name: str
    item_type: str
    item_subtype: Optional[str] = None
    icon_filename: str
    is_tradeable: bool
    is_stackable: bool


class ItemPriceInfo(BaseModel):
    item_vnum: int
    item_name: str
    current_price_yang: int
    current_price_won: int
    average_price_yang: int
    min_price_yang: int
    max_price_yang: int
    price_volatility: float
    trend: str


class ItemAttributeInfo(BaseModel):
    stat_id: int
    value: int
    is_random: bool
    description: str


class ItemDetailResponse(BaseModel):
    basic_info: ItemBasicInfo
    price_info: Optional[ItemPriceInfo] = None
    attributes: List[ItemAttributeInfo] = []
    quality_score: float
    estimated_value: int


# Routes

@router.get("/search", response_model=List[ItemBasicInfo])
async def search_items(
    query: str = Query(..., min_length=1, description="Item name or vnum to search"),
    item_type: Optional[str] = Query(None, description="Filter by item type"),
    limit: int = Query(10, ge=1, le=100, description="Max results to return")
):
    """
    Search for items by name or vnum
    
    Query parameters:
    - query: Search term (name or vnum)
    - item_type: Optional item type filter
    - limit: Number of results (1-100)
    """
    engine = _engine()
    
    try:
        # Check if query is a number (vnum search)
        try:
            vnum = int(query)
            sql = """
                SELECT DISTINCT 
                    item_vnum, 
                    item_name, 
                    item_type, 
                    item_subtype,
                    '' as icon_filename,
                    true as is_tradeable,
                    false as is_stackable
                FROM dim_item
                WHERE item_vnum = %(vnum)s
                LIMIT %(limit)s;
            """
            params = {"vnum": vnum, "limit": limit}
        except ValueError:
            # Text search
            sql = """
                SELECT DISTINCT 
                    item_vnum, 
                    item_name, 
                    item_type, 
                    item_subtype,
                    '' as icon_filename,
                    true as is_tradeable,
                    false as is_stackable
                FROM dim_item
                WHERE item_name ILIKE %(search)s
            """
            params = {"search": f"%{query}%", "limit": limit}
            
            if item_type:
                sql += " AND item_type = %(item_type)s"
                params["item_type"] = item_type
            
            sql += " ORDER BY item_name LIMIT %(limit)s;"
        
        df = pd.read_sql_query(sql, engine, params=params)
        
        results = []
        for _, row in df.iterrows():
            results.append({
                "item_vnum": int(row["item_vnum"]),
                "item_name": row["item_name"],
                "item_type": row["item_type"],
                "item_subtype": row["item_subtype"] if pd.notna(row["item_subtype"]) else None,
                "icon_filename": row["icon_filename"],
                "is_tradeable": bool(row["is_tradeable"]),
                "is_stackable": bool(row["is_stackable"])
            })
        
        return results
    finally:
        engine.dispose()


@router.get("/", response_model=dict)
async def get_items(
    search: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(30, ge=1, le=100)
):
    """
    Get items with optional search
    """
    if search:
        items = await search_items(query=search, limit=limit)
        return {"items": items}
    
    # Return empty if no search
    return {"items": []}


@router.get("/{item_vnum}", response_model=ItemDetailResponse)
async def get_item_details(
    item_vnum: int = Path(..., description="Item vnum")
):
    """
    Get detailed information about a specific item
    
    Path parameters:
    - item_vnum: The item's unique vnum identifier
    """
    # This would fetch from database
    raise HTTPException(status_code=404, detail="Item not found")


@router.get("/type/{item_type}", response_model=List[ItemBasicInfo])
async def get_items_by_type(
    item_type: str = Path(..., description="Item type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get all items of a specific type
    
    Path parameters:
    - item_type: The type of items (WEAPON, ARMOR, etc.)
    
    Query parameters:
    - skip: Number of results to skip (pagination)
    - limit: Number of results to return
    """
    return []


@router.get("/trending/expensive", response_model=List[ItemPriceInfo])
async def get_most_expensive_items(
    limit: int = Query(20, ge=1, le=100, description="Number of items to return")
):
    """
    Get the most expensive items by current market price
    
    Query parameters:
    - limit: Number of top items to return
    """
    return []


@router.get("/trending/valuable", response_model=List[ItemDetailResponse])
async def get_most_valuable_items(
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    min_quality: float = Query(0, ge=0, le=100, description="Minimum quality score")
):
    """
    Get the most valuable items based on quality score and attributes
    
    Query parameters:
    - limit: Number of top items to return
    - min_quality: Minimum quality score (0-100)
    """
    return []


@router.get("/weapons", response_model=List[ItemBasicInfo])
async def get_weapons(
    min_damage: Optional[int] = Query(None, description="Minimum average damage"),
    max_price: Optional[int] = Query(None, description="Maximum price in Yang"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get weapons with optional filtering
    
    Query parameters:
    - min_damage: Filter by minimum average damage
    - max_price: Filter by maximum price
    - skip: Pagination offset
    - limit: Number of results
    """
    return []


@router.get("/armor", response_model=List[ItemBasicInfo])
async def get_armor(
    min_defense: Optional[int] = Query(None, description="Minimum defense value"),
    max_price: Optional[int] = Query(None, description="Maximum price in Yang"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get armor items with optional filtering
    
    Query parameters:
    - min_defense: Filter by minimum defense value
    - max_price: Filter by maximum price
    - skip: Pagination offset
    - limit: Number of results
    """
    return []


@router.get("/high-attributes", response_model=List[ItemDetailResponse])
async def get_high_attribute_items(
    min_attributes: int = Query(4, ge=1, le=7, description="Minimum number of attributes"),
    min_rarity: float = Query(50, ge=0, le=100, description="Minimum rarity score"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get items with high attribute counts and rarity
    
    Query parameters:
    - min_attributes: Minimum number of attributes (1-7)
    - min_rarity: Minimum rarity score (0-100)
    - limit: Number of results
    """
    return []


class ItemComparisonRequest(BaseModel):
    item_vnums: List[int]


@router.post("/compare", response_model=List[ItemDetailResponse])
async def compare_items(request: ItemComparisonRequest):
    """
    Compare multiple items side by side
    
    Request body:
    - item_vnums: List of item vnums to compare (max 5)
    """
    if len(request.item_vnums) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 items to compare")
    
    return []
