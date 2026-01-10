"""
ETL Transformation Module
Transforms extracted market data for warehouse loading
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime, date, timedelta
import math
from models.market_models import (
    MarketItem, ItemType, MarketTrend, UndervaluedItem, PriceSnapshot
)


class DataTransformer:
    """Transforms raw extracted data for data warehouse"""
    
    @staticmethod
    def calculate_price_trend(current_price: int, previous_price: int) -> str:
        """Determine trend direction based on price change"""
        if current_price > previous_price:
            return "UP"
        elif current_price < previous_price:
            return "DOWN"
        else:
            return "STABLE"
    
    @staticmethod
    def calculate_volatility(prices: List[int]) -> float:
        """
        Calculate price volatility using standard deviation
        Returns: coefficient of variation (0-100)
        """
        if not prices or len(prices) < 2:
            return 0.0
        
        avg_price = sum(prices) / len(prices)
        if avg_price == 0:
            return 0.0
        
        variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
        std_dev = math.sqrt(variance)
        
        # Coefficient of variation as percentage
        return (std_dev / avg_price) * 100
    
    @staticmethod
    def estimate_item_fair_value(item: MarketItem) -> int:
        """
        Estimate fair market value for an item based on intrinsic value
        
        Formula:
        fair_value = base_value * quality_multiplier * attribute_multiplier
        """
        return item.estimate_market_value()
    
    @staticmethod
    def detect_undervalued_item(
        item: MarketItem,
        current_price: int,
        estimated_fair_value: int,
        price_history: List[int] = None
    ) -> UndervaluedItem:
        """
        Detect if item is undervalued compared to fair value
        
        Confidence score based on:
        - Price deviation from fair value
        - Price history volatility
        - Item quality
        """
        if current_price <= 0 or estimated_fair_value <= 0:
            return None
        
        undervaluation = current_price / estimated_fair_value
        
        # Calculate confidence score
        confidence = 50.0  # Base confidence
        
        # Adjust based on undervaluation degree
        if undervaluation < 0.7:  # Significantly undervalued
            confidence += 40
        elif undervaluation < 0.85:  # Moderately undervalued
            confidence += 25
        elif undervaluation < 1.0:  # Slightly undervalued
            confidence += 10
        else:
            return None  # Not undervalued
        
        # Adjust based on price stability
        if price_history and len(price_history) >= 10:
            volatility = DataTransformer.calculate_volatility(price_history)
            if volatility < 5:  # Very stable
                confidence += 10
            elif volatility > 20:  # High volatility
                confidence -= 15
        
        # Adjust based on item quality
        quality_factor = item.quality_score / 100
        confidence += quality_factor * 10
        
        # Cap confidence at 100
        confidence = min(confidence, 100.0)
        
        # Determine deal rating
        underval_percentage = ((estimated_fair_value - current_price) / estimated_fair_value) * 100
        if underval_percentage >= 40:
            deal_rating = "EXCELLENT"
        elif underval_percentage >= 25:
            deal_rating = "GOOD"
        elif underval_percentage >= 10:
            deal_rating = "FAIR"
        else:
            deal_rating = "POOR"
        
        potential_profit = estimated_fair_value - current_price
        
        return UndervaluedItem(
            item=item,
            current_price=current_price,
            estimated_fair_value=estimated_fair_value,
            undervaluation_percentage=underval_percentage,
            confidence_score=confidence,
            potential_profit=potential_profit,
            deal_rating=deal_rating
        )
    
    @staticmethod
    def transform_price_history(
        item_vnum: int,
        prices: List[Tuple[datetime, int]],
        period: str = "DAILY"
    ) -> MarketTrend:
        """
        Transform price history into trend analysis
        
        Args:
            item_vnum: Item vnum
            prices: List of (timestamp, price) tuples
            period: DAILY, WEEKLY, or MONTHLY
        
        Returns:
            MarketTrend object with analysis
        """
        if not prices or len(prices) < 2:
            return None
        
        # Extract price values
        price_values = [p[1] for p in prices]
        
        # Calculate metrics
        avg_price = sum(price_values) / len(price_values)
        min_price = min(price_values)
        max_price = max(price_values)
        volatility = DataTransformer.calculate_volatility(price_values)
        
        # Calculate trend
        if len(price_values) >= 2:
            first_price = price_values[0]
            last_price = price_values[-1]
            change_percentage = ((last_price - first_price) / first_price * 100) if first_price > 0 else 0
            trend = DataTransformer.calculate_price_trend(last_price, first_price)
        else:
            change_percentage = 0
            trend = "STABLE"
        
        return MarketTrend(
            item_vnum=str(item_vnum),
            period=period,
            average_price=avg_price,
            min_price=min_price,
            max_price=max_price,
            price_change_percentage=change_percentage,
            trend_direction=trend,
            volatility=volatility,
            transaction_count=len(prices)
        )
    
    @staticmethod
    def normalize_item_name(name: str) -> str:
        """Remove HTML tags and clean item name"""
        import re
        # Remove HTML tags
        clean_name = re.sub(r'<[^>]*>', '', name)
        # Remove extra whitespace
        clean_name = ' '.join(clean_name.split())
        return clean_name
    
    @staticmethod
    def categorize_item_by_price(price_yang: int) -> str:
        """Categorize item into price range"""
        if price_yang <= 0:
            return "FREE"
        elif price_yang <= 10000:
            return "VERY_CHEAP"
        elif price_yang <= 100000:
            return "CHEAP"
        elif price_yang <= 1000000:
            return "MODERATE"
        elif price_yang <= 10000000:
            return "EXPENSIVE"
        elif price_yang <= 100000000:
            return "VERY_EXPENSIVE"
        else:
            return "ULTRA_EXPENSIVE"
    
    @staticmethod
    def calculate_days_since_creation(created_timestamp: int) -> int:
        """Calculate days since pet/item creation"""
        now = datetime.now()
        created_date = datetime.fromtimestamp(created_timestamp)
        diff = now - created_date
        return max(1, diff.days)


class TimeSeriesTransformer:
    """Transforms temporal data for time dimension"""
    
    @staticmethod
    def generate_time_key(date_obj: date) -> Dict[str, Any]:
        """Generate time dimension record"""
        import calendar
        
        iso_calendar = date_obj.isocalendar()
        
        return {
            'full_date': date_obj,
            'year': date_obj.year,
            'quarter': (date_obj.month - 1) // 3 + 1,
            'month': date_obj.month,
            'week': iso_calendar[1],
            'day_of_month': date_obj.day,
            'day_of_week': date_obj.weekday() + 1,  # 1-7 (Monday-Sunday)
            'day_name': calendar.day_name[date_obj.weekday()],
            'is_weekend': date_obj.weekday() >= 5
        }
    
    @staticmethod
    def generate_date_range(start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Generate time dimension records for date range"""
        time_records = []
        current = start_date
        
        while current <= end_date:
            time_records.append(TimeSeriesTransformer.generate_time_key(current))
            current += timedelta(days=1)
        
        return time_records


class DimensionalTransformer:
    """Transforms item data into dimension table records"""
    
    @staticmethod
    def transform_to_item_dimension(item: MarketItem) -> Dict[str, Any]:
        """Transform MarketItem to dimension table record"""
        return {
            'item_vnum': item.vnum,
            'item_name': DataTransformer.normalize_item_name(item.name),
            'item_type': item.item_type.value,
            'item_subtype': item.item_subtype,
            'icon_filename': item.icon_filename,
            'is_tradeable': item.is_tradeable,
            'is_stackable': item.is_stackable,
        }
    
    @staticmethod
    def transform_to_properties_dimensions(item: MarketItem) -> List[Dict[str, Any]]:
        """Transform item attributes to property dimension records"""
        properties = []
        
        # Add weapon properties
        if item.weapon_stats:
            ws = item.weapon_stats
            properties.extend([
                {
                    'item_vnum': item.vnum,
                    'property_type': 'WEAPON_PHYSICAL',
                    'stat_id': None,
                    'min_value': ws.min_physical_attack,
                    'base_value': ws.average_physical_damage,
                    'max_value': ws.max_physical_attack,
                    'description': 'Physical Attack'
                },
                {
                    'item_vnum': item.vnum,
                    'property_type': 'WEAPON_MAGICAL',
                    'stat_id': None,
                    'min_value': ws.min_magical_attack,
                    'base_value': ws.average_magical_damage,
                    'max_value': ws.max_magical_attack,
                    'description': 'Magical Attack'
                }
            ])
        
        # Add armor properties
        if item.armor_stats:
            asp = item.armor_stats
            properties.extend([
                {
                    'item_vnum': item.vnum,
                    'property_type': 'ARMOR_DEFENSE',
                    'stat_id': None,
                    'base_value': asp.defense_value,
                    'max_value': asp.defense_value,
                    'min_value': 0,
                    'description': 'Physical Defense'
                },
                {
                    'item_vnum': item.vnum,
                    'property_type': 'ARMOR_MAGICAL_DEFENSE',
                    'stat_id': None,
                    'base_value': asp.magical_defense_value,
                    'max_value': asp.magical_defense_value,
                    'min_value': 0,
                    'description': 'Magical Defense'
                }
            ])
        
        # Add attribute bonuses
        for attr in item.attributes.attributes:
            properties.append({
                'item_vnum': item.vnum,
                'property_type': 'ATTRIBUTE_BONUS',
                'stat_id': attr.stat_id,
                'base_value': attr.value,
                'max_value': attr.value,
                'min_value': 0,
                'description': f'Stat {attr.stat_id}'
            })
        
        return properties
    
    @staticmethod
    def transform_to_fact_transaction(
        item: MarketItem,
        timestamp: datetime,
        transaction_type: str = "BUY"
    ) -> Dict[str, Any]:
        """Transform to fact transaction record"""
        return {
            'item_vnum': item.vnum,
            'timestamp': timestamp,
            'transaction_type': transaction_type,
            'price_yang': item.price.yang_price,
            'price_won': item.price.won_price,
            'quantity': int(getattr(item, 'quantity', 1) or 1),
            'enhancement_level': item.enhancement_level,
            'durability_percentage': item.durability_percentage,
            'socket_count': len(item.sockets),
            'attribute_count': len(item.attributes.attributes),

            # Listing context (for app.js parity / filtering)
            'server_id': getattr(item, 'server_id', None),
            'seller_name': getattr(item, 'seller_name', None),
            'job_id': getattr(item, 'job_id', 0),
            'category_code': getattr(item, 'category_code', None),
            'category_id': getattr(item, 'category_id', None),
        }
    
    @staticmethod
    def transform_to_fact_attributes(
        item: MarketItem,
        timestamp: datetime
    ) -> Dict[str, Any]:
        """Transform to fact item attributes record"""
        attrs = item.attributes.attributes
        
        record = {
            'item_vnum': item.vnum,
            'timestamp': timestamp,
            'total_attribute_value': item.attributes.total_attribute_value,
            'attribute_rarity_score': item.attributes.rarity_score,
            'estimated_value_multiplier': 1.0 + (item.attributes.rarity_score / 100),

            # Listing context (for app.js parity / filtering)
            'server_id': getattr(item, 'server_id', None),
            'seller_name': getattr(item, 'seller_name', None),
            'job_id': getattr(item, 'job_id', 0),
            'category_code': getattr(item, 'category_code', None),
            'category_id': getattr(item, 'category_id', None),
        }
        
        # Add individual attributes (up to 7)
        for i in range(7):
            if i < len(attrs):
                record[f'attribute_{i+1}_stat_id'] = attrs[i].stat_id
                record[f'attribute_{i+1}_value'] = attrs[i].value
            else:
                record[f'attribute_{i+1}_stat_id'] = None
                record[f'attribute_{i+1}_value'] = None
        
        return record


class AggregationTransformer:
    """Transforms raw data into aggregate fact tables"""
    
    @staticmethod
    def aggregate_daily_prices(
        transactions: List[Tuple[int, int, int, datetime]]  # (price_yang, price_won, qty, timestamp)
    ) -> Dict[str, Any]:
        """Aggregate transactions into daily summary"""
        if not transactions:
            return None
        
        prices_yang = [t[0] for t in transactions if t[0] > 0]
        quantities = [t[2] for t in transactions]
        
        return {
            'avg_price_yang': sum(prices_yang) / len(prices_yang) if prices_yang else 0,
            'min_price_yang': min(prices_yang) if prices_yang else 0,
            'max_price_yang': max(prices_yang) if prices_yang else 0,
            'transaction_count': len(transactions),
            'daily_volume': sum(quantities),
        }
    
    @staticmethod
    def aggregate_weekly_trends(
        daily_aggregates: List[Tuple[date, float]]  # (date, avg_price)
    ) -> Dict[str, Any]:
        """Aggregate daily data into weekly trends"""
        if not daily_aggregates:
            return None
        
        prices = [agg[1] for agg in daily_aggregates]
        
        if len(prices) < 2:
            change_pct = 0
        else:
            first_price = prices[0]
            last_price = prices[-1]
            change_pct = ((last_price - first_price) / first_price * 100) if first_price > 0 else 0
        
        return {
            'avg_price_yang': sum(prices) / len(prices) if prices else 0,
            'price_change_percentage': change_pct,
            'transaction_count': len(daily_aggregates),
        }
