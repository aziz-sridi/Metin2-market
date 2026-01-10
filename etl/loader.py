"""
ETL Loading Module
Loads transformed data into PostgreSQL data warehouse
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

import os

import psycopg2

from pygrametl import ConnectionWrapper
from pygrametl.tables import CachedDimension, FactTable


class WarehouseLoader:
    """Handles loading data into PostgreSQL data warehouse"""
    
    def __init__(self, connection_string: str):
        """Initialize loader with PostgreSQL connection string"""
        self.connection_string = connection_string
        self.conn: Optional[Any] = None
        self.dwconn: Optional[ConnectionWrapper] = None

        # pygramETL table abstractions (initialized after connect)
        self.dim_item: Optional[CachedDimension] = None
        self.dim_time: Optional[CachedDimension] = None
        self.dim_transaction_type: Optional[CachedDimension] = None

        self.fact_market_transaction: Optional[FactTable] = None
        self.fact_item_attributes: Optional[FactTable] = None
        self.fact_undervalued_items: Optional[FactTable] = None
    
    def connect(self) -> bool:
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(self.connection_string)
            self._ensure_schema_extensions()
            self.dwconn = ConnectionWrapper(self.conn)
            self.dwconn.setasdefault()
            self._setup_pygrametl_tables()
            return True
        except Exception as e:
            print(f"Failed to connect to database: {e}")
            return False

    def _ensure_schema_extensions(self) -> None:
        """Idempotently add newer columns needed for filtering parity.

        This avoids requiring explicit migrations when the warehouse already exists.
        """
        if not self.conn:
            raise RuntimeError("Database connection is not initialized")

        cur = self.conn.cursor()
        try:
            # fact_market_transaction
            cur.execute("ALTER TABLE fact_market_transaction ADD COLUMN IF NOT EXISTS server_id INTEGER")
            cur.execute("ALTER TABLE fact_market_transaction ADD COLUMN IF NOT EXISTS seller_name VARCHAR(255)")
            cur.execute("ALTER TABLE fact_market_transaction ADD COLUMN IF NOT EXISTS job_id INTEGER")
            cur.execute("ALTER TABLE fact_market_transaction ADD COLUMN IF NOT EXISTS category_code VARCHAR(50)")
            cur.execute("ALTER TABLE fact_market_transaction ADD COLUMN IF NOT EXISTS category_id VARCHAR(50)")

            # fact_item_attributes
            cur.execute("ALTER TABLE fact_item_attributes ADD COLUMN IF NOT EXISTS server_id INTEGER")
            cur.execute("ALTER TABLE fact_item_attributes ADD COLUMN IF NOT EXISTS seller_name VARCHAR(255)")
            cur.execute("ALTER TABLE fact_item_attributes ADD COLUMN IF NOT EXISTS job_id INTEGER")
            cur.execute("ALTER TABLE fact_item_attributes ADD COLUMN IF NOT EXISTS category_code VARCHAR(50)")
            cur.execute("ALTER TABLE fact_item_attributes ADD COLUMN IF NOT EXISTS category_id VARCHAR(50)")

            # Price normalization:
            # - Source payload provides (wonPrice, yangPrice) where yangPrice is the remainder.
            # - We store transaction_price_yang as TOTAL yang for comparisons/analytics.
            # - Conversion rule is configurable via env var; default: 1 won = 100,000,000 yang.
            #
            # This also migrates older rows that were loaded when the system used
            # 100,000,000 yang per won (or when transaction_price_yang held only the remainder).
            won_to_yang_new = int(os.getenv("WON_TO_YANG", "100000000"))
            won_to_yang_old = int(os.getenv("WON_TO_YANG_OLD", "1000000000"))

            if won_to_yang_new != won_to_yang_old:
                cur.execute(
                    """
                    UPDATE fact_market_transaction
                    SET transaction_price_yang = (transaction_price_won * %s) + (
                        CASE
                            WHEN transaction_price_yang IS NULL THEN 0
                            WHEN transaction_price_yang BETWEEN 0 AND (%s - 1) THEN transaction_price_yang
                            ELSE (transaction_price_yang - (transaction_price_won * %s))
                        END
                    )
                    WHERE transaction_price_won IS NOT NULL
                      AND transaction_price_won > 0
                      AND (
                           transaction_price_yang IS NULL
                           OR transaction_price_yang BETWEEN 0 AND (%s - 1)
                           OR (transaction_price_yang - (transaction_price_won * %s)) BETWEEN 0 AND (%s - 1)
                      )
                    """,
                    (
                        won_to_yang_new,
                        won_to_yang_old,
                        won_to_yang_old,
                        won_to_yang_old,
                        won_to_yang_old,
                        won_to_yang_old,
                    ),
                )

            self.conn.commit()
        finally:
            cur.close()
    
    def disconnect(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

        self.conn = None
        self.dwconn = None

        self.dim_item = None
        self.dim_time = None
        self.dim_transaction_type = None

        self.fact_market_transaction = None
        self.fact_item_attributes = None
        self.fact_undervalued_items = None

    def _setup_pygrametl_tables(self) -> None:
        if not self.dwconn:
            raise RuntimeError("Database connection is not initialized")

        # Dimensions
        self.dim_item = CachedDimension(
            name="dim_item",
            key="item_key",
            attributes=[
                "item_vnum",
                "item_name",
                "item_type",
                "item_subtype",
                "icon_filename",
                "is_tradeable",
                "is_stackable",
            ],
            lookupatts=["item_vnum"],
        )

        self.dim_time = CachedDimension(
            name="dim_time",
            key="time_key",
            attributes=[
                "full_date",
                "year",
                "quarter",
                "month",
                "week",
                "day_of_month",
                "day_of_week",
                "day_name",
                "is_weekend",
            ],
            lookupatts=["full_date"],
        )

        self.dim_transaction_type = CachedDimension(
            name="dim_transaction_type",
            key="transaction_type_key",
            attributes=["transaction_type", "description"],
            lookupatts=["transaction_type"],
        )

        # Facts
        self.fact_market_transaction = FactTable(
            name="fact_market_transaction",
            keyrefs=["item_key", "time_key", "transaction_type_key"],
            measures=[
                "price_category_key",
                "server_id",
                "seller_name",
                "job_id",
                "category_code",
                "category_id",
                "transaction_price_yang",
                "transaction_price_won",
                "quantity_traded",
                "enhancement_level",
                "durability_percentage",
                "socket_count",
                "attribute_count",
                "transaction_timestamp",
            ],
        )

        self.fact_item_attributes = FactTable(
            name="fact_item_attributes",
            keyrefs=["item_key", "time_key"],
            measures=[
                "server_id",
                "seller_name",
                "job_id",
                "category_code",
                "category_id",
                "attribute_1_stat_id",
                "attribute_1_value",
                "attribute_2_stat_id",
                "attribute_2_value",
                "attribute_3_stat_id",
                "attribute_3_value",
                "attribute_4_stat_id",
                "attribute_4_value",
                "attribute_5_stat_id",
                "attribute_5_value",
                "attribute_6_stat_id",
                "attribute_6_value",
                "attribute_7_stat_id",
                "attribute_7_value",
                "total_attribute_value",
                "attribute_rarity_score",
                "estimated_value_multiplier",
                "recorded_timestamp",
            ],
        )

        self.fact_undervalued_items = FactTable(
            name="fact_undervalued_items",
            keyrefs=["item_key", "time_key"],
            measures=[
                "current_price_yang",
                "estimated_fair_value_yang",
                "undervaluation_percentage",
                "confidence_score",
                "potential_profit_yang",
                "deal_rating",
                "detected_timestamp",
                "is_still_available",
            ],
        )

    def _ensure_transaction_type(self, transaction_type: str) -> int:
        if not self.dim_transaction_type:
            raise RuntimeError("pygramETL tables not initialized")

        return int(
            self.dim_transaction_type.ensure(
                {
                    "transaction_type": transaction_type,
                    "description": f"{transaction_type} transaction",
                }
            )
        )
    
    def load_dimension_items(self, items: List[Dict[str, Any]]) -> bool:
        """Load items into dim_item dimension table"""
        try:
            if not self.dim_item or not self.dwconn:
                raise RuntimeError("Database is not connected")

            for item in items:
                # ensure inserts if missing, otherwise returns existing surrogate key
                self.dim_item.ensure(
                    {
                        "item_vnum": int(item["item_vnum"]),
                        "item_name": item["item_name"],
                        "item_type": item.get("item_type"),
                        "item_subtype": item.get("item_subtype"),
                        "icon_filename": item.get("icon_filename"),
                        "is_tradeable": bool(item.get("is_tradeable", True)),
                        "is_stackable": bool(item.get("is_stackable", False)),
                    }
                )

            self.dwconn.commit()
            return True
        except Exception as e:
            if self.dwconn:
                self.dwconn.rollback()
            print(f"Error loading items: {e}")
            return False
    
    def load_item_properties(self, properties: List[Dict[str, Any]]) -> bool:
        """Load properties into dim_item_properties"""
        try:
            if not self.dim_item or not self.dwconn:
                raise RuntimeError("Database is not connected")

            insert_query = """
                INSERT INTO dim_item_properties
                (item_key, property_type, stat_id, base_value, max_value, min_value, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (item_key, property_type, stat_id) DO UPDATE SET
                    base_value = EXCLUDED.base_value,
                    max_value = EXCLUDED.max_value,
                    min_value = EXCLUDED.min_value,
                    description = EXCLUDED.description
            """

            for prop in properties:
                item_key = int(self.dim_item.lookup({"item_vnum": int(prop["item_vnum"])}) or 0)
                if not item_key:
                    # If the item wasn't loaded yet, insert it minimally.
                    item_key = int(
                        self.dim_item.ensure(
                            {
                                "item_vnum": int(prop["item_vnum"]),
                                "item_name": "Unknown Item",
                                "item_type": None,
                                "item_subtype": None,
                                "icon_filename": None,
                                "is_tradeable": True,
                                "is_stackable": False,
                            }
                        )
                    )

                self.dwconn.execute(
                    insert_query,
                    (
                        item_key,
                        prop.get("property_type"),
                        prop.get("stat_id"),
                        prop.get("base_value"),
                        prop.get("max_value"),
                        prop.get("min_value"),
                        prop.get("description"),
                    ),
                )

            self.dwconn.commit()
            return True
        except Exception as e:
            if self.dwconn:
                self.dwconn.rollback()
            print(f"Error loading properties: {e}")
            return False
    
    def load_time_dimension(self, time_records: List[Dict[str, Any]]) -> bool:
        """Load time dimension records"""
        try:
            if not self.dim_time or not self.dwconn:
                raise RuntimeError("Database is not connected")

            for rec in time_records:
                self.dim_time.ensure(
                    {
                        "full_date": rec["full_date"],
                        "year": rec.get("year"),
                        "quarter": rec.get("quarter"),
                        "month": rec.get("month"),
                        "week": rec.get("week"),
                        "day_of_month": rec.get("day_of_month"),
                        "day_of_week": rec.get("day_of_week"),
                        "day_name": rec.get("day_name"),
                        "is_weekend": rec.get("is_weekend"),
                    }
                )

            self.dwconn.commit()
            return True
        except Exception as e:
            if self.dwconn:
                self.dwconn.rollback()
            print(f"Error loading time dimension: {e}")
            return False
    
    def load_fact_market_transactions(self, transactions: List[Dict[str, Any]]) -> bool:
        """Load market transactions into fact table"""
        try:
            if not self.dim_item or not self.dim_time or not self.fact_market_transaction or not self.dwconn:
                raise RuntimeError("Database is not connected")

            for trans in transactions:
                ts = trans.get("timestamp")
                if not isinstance(ts, datetime):
                    raise ValueError("transaction timestamp must be a datetime")

                item_key = int(self.dim_item.ensure({"item_vnum": int(trans["item_vnum"]), "item_name": "Unknown Item"}))
                time_key = int(self.dim_time.ensure({"full_date": ts.date()}))
                ttype_key = self._ensure_transaction_type(trans.get("transaction_type", "BUY"))

                self.fact_market_transaction.insert(
                    {
                        "item_key": item_key,
                        "time_key": time_key,
                        "transaction_type_key": ttype_key,
                        "price_category_key": None,
                        "server_id": trans.get("server_id"),
                        "seller_name": trans.get("seller_name"),
                        "job_id": trans.get("job_id"),
                        "category_code": trans.get("category_code"),
                        "category_id": trans.get("category_id"),
                        "transaction_price_yang": trans.get("price_yang"),
                        "transaction_price_won": trans.get("price_won"),
                        "quantity_traded": trans.get("quantity", 1),
                        "enhancement_level": trans.get("enhancement_level", 0),
                        "durability_percentage": trans.get("durability_percentage", 100),
                        "socket_count": trans.get("socket_count", 0),
                        "attribute_count": trans.get("attribute_count", 0),
                        "transaction_timestamp": ts,
                    }
                )

            self.dwconn.commit()
            return True
        except Exception as e:
            if self.dwconn:
                self.dwconn.rollback()
            print(f"Error loading market transactions: {e}")
            return False
    
    def load_fact_price_history(self, price_history: List[Dict[str, Any]]) -> bool:
        """Load price history into fact table"""
        try:
            insert_query = """
                INSERT INTO fact_price_history
                (item_key, time_key, average_price_yang, average_price_won,
                 min_price_yang, max_price_yang, min_price_won, max_price_won,
                 transaction_count, total_quantity_traded, price_volatility,
                 price_trend, recorded_timestamp)
                SELECT 
                    di.item_key,
                    dt.time_key,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                FROM dim_item di
                CROSS JOIN dim_time dt
                WHERE di.item_vnum = %s
                    AND dt.full_date = %s::date
                ON CONFLICT (item_key, time_key) DO UPDATE SET
                    average_price_yang = EXCLUDED.average_price_yang,
                    average_price_won = EXCLUDED.average_price_won,
                    min_price_yang = EXCLUDED.min_price_yang,
                    max_price_yang = EXCLUDED.max_price_yang,
                    recorded_timestamp = EXCLUDED.recorded_timestamp
            """
            
            batch_data = [
                (hist.get('average_price_yang', 0), hist.get('average_price_won', 0),
                 hist.get('min_price_yang', 0), hist.get('max_price_yang', 0),
                 hist.get('min_price_won', 0), hist.get('max_price_won', 0),
                 hist.get('transaction_count', 0), hist.get('total_quantity_traded', 0),
                 hist.get('price_volatility', 0), hist.get('price_trend', 'STABLE'),
                 hist.get('recorded_timestamp'),
                 hist.get('item_vnum'),
                 hist.get('recorded_timestamp').date() if isinstance(hist.get('recorded_timestamp'), datetime) else hist.get('recorded_timestamp'))
                for hist in price_history
            ]
            
            execute_batch(self.cursor, insert_query, batch_data, page_size=100)
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            print(f"Error loading price history: {e}")
            return False
    
    def load_fact_item_attributes(self, attributes: List[Dict[str, Any]]) -> bool:
        """Load item attributes into fact table"""
        try:
            if not self.dim_item or not self.dim_time or not self.fact_item_attributes or not self.dwconn:
                raise RuntimeError("Database is not connected")

            for attr in attributes:
                ts = attr.get("timestamp")
                if not isinstance(ts, datetime):
                    raise ValueError("attribute timestamp must be a datetime")

                item_key = int(self.dim_item.ensure({"item_vnum": int(attr["item_vnum"]), "item_name": "Unknown Item"}))
                time_key = int(self.dim_time.ensure({"full_date": ts.date()}))

                self.fact_item_attributes.insert(
                    {
                        "item_key": item_key,
                        "time_key": time_key,
                        "server_id": attr.get("server_id"),
                        "seller_name": attr.get("seller_name"),
                        "job_id": attr.get("job_id"),
                        "category_code": attr.get("category_code"),
                        "category_id": attr.get("category_id"),
                        "attribute_1_stat_id": attr.get("attribute_1_stat_id"),
                        "attribute_1_value": attr.get("attribute_1_value"),
                        "attribute_2_stat_id": attr.get("attribute_2_stat_id"),
                        "attribute_2_value": attr.get("attribute_2_value"),
                        "attribute_3_stat_id": attr.get("attribute_3_stat_id"),
                        "attribute_3_value": attr.get("attribute_3_value"),
                        "attribute_4_stat_id": attr.get("attribute_4_stat_id"),
                        "attribute_4_value": attr.get("attribute_4_value"),
                        "attribute_5_stat_id": attr.get("attribute_5_stat_id"),
                        "attribute_5_value": attr.get("attribute_5_value"),
                        "attribute_6_stat_id": attr.get("attribute_6_stat_id"),
                        "attribute_6_value": attr.get("attribute_6_value"),
                        "attribute_7_stat_id": attr.get("attribute_7_stat_id"),
                        "attribute_7_value": attr.get("attribute_7_value"),
                        "total_attribute_value": attr.get("total_attribute_value"),
                        "attribute_rarity_score": attr.get("attribute_rarity_score"),
                        "estimated_value_multiplier": attr.get("estimated_value_multiplier"),
                        "recorded_timestamp": ts,
                    }
                )

            self.dwconn.commit()
            return True
        except Exception as e:
            if self.dwconn:
                self.dwconn.rollback()
            print(f"Error loading item attributes: {e}")
            return False

    def load_fact_undervalued_items(self, items: List[Dict[str, Any]]) -> bool:
        """Load undervalued items into fact table"""
        try:
            if not self.dim_item or not self.dim_time or not self.fact_undervalued_items or not self.dwconn:
                raise RuntimeError("Database is not connected")

            for it in items:
                ts = it.get("detected_timestamp")
                if not isinstance(ts, datetime):
                    raise ValueError("detected_timestamp must be a datetime")

                item_key = int(self.dim_item.ensure({"item_vnum": int(it["item_vnum"]), "item_name": "Unknown Item"}))
                time_key = int(self.dim_time.ensure({"full_date": ts.date()}))

                self.fact_undervalued_items.insert(
                    {
                        "item_key": item_key,
                        "time_key": time_key,
                        "current_price_yang": it.get("current_price_yang"),
                        "estimated_fair_value_yang": it.get("estimated_fair_value_yang"),
                        "undervaluation_percentage": it.get("undervaluation_percentage"),
                        "confidence_score": it.get("confidence_score"),
                        "potential_profit_yang": it.get("potential_profit_yang"),
                        "deal_rating": it.get("deal_rating"),
                        "detected_timestamp": ts,
                        "is_still_available": bool(it.get("is_still_available", True)),
                    }
                )

            self.dwconn.commit()
            return True
        except Exception as e:
            if self.dwconn:
                self.dwconn.rollback()
            print(f"Error loading undervalued items: {e}")
            return False
    
    def load_fact_undervalued_items(self, undervalued: List[Dict[str, Any]]) -> bool:
        """Load undervalued items detection results"""
        try:
            insert_query = """
                INSERT INTO fact_undervalued_items
                (item_key, time_key, current_price_yang, estimated_fair_value_yang,
                 undervaluation_percentage, confidence_score, potential_profit_yang,
                 deal_rating, detected_timestamp, is_still_available)
                SELECT 
                    di.item_key,
                    dt.time_key,
                    %s, %s, %s, %s, %s, %s, %s, %s
                FROM dim_item di
                CROSS JOIN dim_time dt
                WHERE di.item_vnum = %s
                    AND dt.full_date = %s::date
            """
            
            batch_data = [
                (item.get('current_price_yang'), item.get('estimated_fair_value_yang'),
                 item.get('undervaluation_percentage'), item.get('confidence_score'),
                 item.get('potential_profit_yang'), item.get('deal_rating'),
                 item.get('detected_timestamp'), item.get('is_still_available', True),
                 item.get('item_vnum'),
                 item.get('detected_timestamp').date() if isinstance(item.get('detected_timestamp'), datetime) else item.get('detected_timestamp'))
                for item in undervalued
            ]
            
            execute_batch(self.cursor, insert_query, batch_data, page_size=100)
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            print(f"Error loading undervalued items: {e}")
            return False
    
    def get_item_key(self, item_vnum: int) -> Optional[int]:
        """Get item_key from dim_item by vnum"""
        try:
            self.cursor.execute("SELECT item_key FROM dim_item WHERE item_vnum = %s", (item_vnum,))
            result = self.cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"Error fetching item_key: {e}")
            return None
    
    def get_time_key(self, date_obj: date) -> Optional[int]:
        """Get time_key from dim_time by date"""
        try:
            self.cursor.execute("SELECT time_key FROM dim_time WHERE full_date = %s", (date_obj,))
            result = self.cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"Error fetching time_key: {e}")
            return None
    
    def execute_query(self, query: str, params: tuple = None) -> Any:
        """Execute custom query"""
        try:
            self.cursor.execute(query, params or ())
            self.conn.commit()
            return self.cursor.fetchall()
        except Exception as e:
            self.conn.rollback()
            print(f"Error executing query: {e}")
            return None
