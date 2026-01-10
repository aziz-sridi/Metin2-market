"""
ETL Pipeline Orchestrator
Coordinates extraction, transformation, and loading of market data
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from etl.extractor import MarketDataExtractor, BatchDataExtractor
from etl.cleaning import clean_market_json_array
from etl.transformer import (
    DataTransformer, TimeSeriesTransformer, 
    DimensionalTransformer, AggregationTransformer
)
from etl.loader import WarehouseLoader
from models.market_models import MarketItem
from config.settings import config

# Configure logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ETLPipeline:
    """Main ETL pipeline orchestrator"""
    
    def __init__(self, connection_string: Optional[str] = None, server_id: Optional[int] = None):
        """Initialize pipeline with database connection"""
        self.extractor = MarketDataExtractor()
        self.batch_extractor = BatchDataExtractor()
        self.db_connection = connection_string or config.get_db_connection_string()
        self.loader = WarehouseLoader(self.db_connection)
        self.extracted_items: List[MarketItem] = []
        self.transformation_results: Dict[str, Any] = {}
        self.server_id: Optional[int] = server_id
    
    def extract(self, json_array: List[Dict[str, Any]]) -> bool:
        """Extract phase: Convert raw data to MarketItem objects"""
        logger.info(f"Starting extraction of {len(json_array)} items...")
        
        try:
            cleaned = clean_market_json_array(json_array)
            self.extracted_items = self.extractor.extract_from_json_array(cleaned)

            # Apply server context to all extracted listings (not always present in payload)
            if self.server_id is not None:
                for it in self.extracted_items:
                    it.server_id = self.server_id

            logger.info(f"Successfully extracted {len(self.extracted_items)} items")
            return True
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return False
    
    def extract_from_file(self, file_path: str) -> bool:
        """Extract from JSON file"""
        logger.info(f"Extracting data from file: {file_path}")
        
        try:
            self.extracted_items = self.extractor.extract_from_file(file_path)
            logger.info(f"Successfully extracted {len(self.extracted_items)} items from file")
            return True
        except Exception as e:
            logger.error(f"File extraction failed: {e}")
            return False
    
    def transform(self) -> bool:
        """Transform phase: Apply business logic and calculations"""
        logger.info(f"Starting transformation of {len(self.extracted_items)} items...")
        
        try:
            # Use a single timestamp for the whole batch so fact rows can be joined per listing.
            batch_timestamp = datetime.now()

            # Transform to dimension records
            item_dimensions = [
                DimensionalTransformer.transform_to_item_dimension(item)
                for item in self.extracted_items
            ]
            
            # Collect all properties
            all_properties = []
            for item in self.extracted_items:
                props = DimensionalTransformer.transform_to_properties_dimensions(item)
                all_properties.extend(props)
            
            # Generate time dimension for current date
            from datetime import date
            today = date.today()
            time_records = [TimeSeriesTransformer.generate_time_key(today)]
            
            # Transform to fact records
            transaction_facts = [
                DimensionalTransformer.transform_to_fact_transaction(item, batch_timestamp)
                for item in self.extracted_items
            ]
            
            attribute_facts = [
                DimensionalTransformer.transform_to_fact_attributes(item, batch_timestamp)
                for item in self.extracted_items
            ]
            
            # Detect undervalued items
            undervalued_items = []
            for item in self.extracted_items:
                fair_value = DataTransformer.estimate_item_fair_value(item)
                if item.price.yang_price > 0:
                    undervalued = DataTransformer.detect_undervalued_item(
                        item,
                        item.price.yang_price,
                        fair_value
                    )
                    if undervalued:
                        undervalued_items.append(undervalued)
            
            # Store results
            self.transformation_results = {
                'item_dimensions': item_dimensions,
                'properties': all_properties,
                'time_records': time_records,
                'transaction_facts': transaction_facts,
                'attribute_facts': attribute_facts,
                'undervalued_items': undervalued_items,
                'transformation_timestamp': batch_timestamp
            }
            
            logger.info(f"Transformation complete. Found {len(undervalued_items)} undervalued items")
            return True
        except Exception as e:
            logger.error(f"Transformation failed: {e}")
            return False
    
    def load(self) -> bool:
        """Load phase: Insert transformed data into warehouse"""
        logger.info("Starting load phase...")
        
        try:
            if not self.loader.connect():
                logger.error("Failed to connect to database")
                return False
            
            # Load dimensions
            logger.info(f"Loading {len(self.transformation_results['item_dimensions'])} items...")
            if not self.loader.load_dimension_items(self.transformation_results['item_dimensions']):
                return False
            
            logger.info(f"Loading {len(self.transformation_results['properties'])} properties...")
            if not self.loader.load_item_properties(self.transformation_results['properties']):
                return False
            
            logger.info(f"Loading {len(self.transformation_results['time_records'])} time records...")
            if not self.loader.load_time_dimension(self.transformation_results['time_records']):
                return False
            
            logger.info(f"Loading {len(self.transformation_results['transaction_facts'])} transactions...")
            if not self.loader.load_fact_market_transactions(self.transformation_results['transaction_facts']):
                return False
            
            logger.info(f"Loading {len(self.transformation_results['attribute_facts'])} attribute facts...")
            if not self.loader.load_fact_item_attributes(self.transformation_results['attribute_facts']):
                return False
            
            undervalued_list = [
                {
                    'item_vnum': item.item.vnum,
                    'current_price_yang': item.current_price,
                    'estimated_fair_value_yang': item.estimated_fair_value,
                    'undervaluation_percentage': item.undervaluation_percentage,
                    'confidence_score': item.confidence_score,
                    'potential_profit_yang': item.potential_profit,
                    'deal_rating': item.deal_rating,
                    'detected_timestamp': datetime.now(),
                    'is_still_available': True
                }
                for item in self.transformation_results['undervalued_items']
            ]
            
            if undervalued_list:
                logger.info(f"Loading {len(undervalued_list)} undervalued items...")
                if not self.loader.load_fact_undervalued_items(undervalued_list):
                    return False
            
            self.loader.disconnect()
            logger.info("Load phase complete")
            return True
        except Exception as e:
            logger.error(f"Load phase failed: {e}")
            self.loader.disconnect()
            return False
    
    def run_full_pipeline(self, json_array: List[Dict[str, Any]]) -> bool:
        """Execute complete ETL pipeline"""
        logger.info("=" * 80)
        logger.info("Starting complete ETL Pipeline")
        logger.info("=" * 80)
        
        start_time = datetime.now()
        
        # Extract
        if not self.extract(json_array):
            logger.error("Pipeline failed at extraction phase")
            return False
        
        # Transform
        if not self.transform():
            logger.error("Pipeline failed at transformation phase")
            return False
        
        # Load
        if not self.load():
            logger.error("Pipeline failed at load phase")
            return False
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("=" * 80)
        logger.info(f"ETL Pipeline completed successfully in {duration:.2f} seconds")
        logger.info(f"Items processed: {len(self.extracted_items)}")
        logger.info(f"Undervalued items found: {len(self.transformation_results.get('undervalued_items', []))}")
        logger.info("=" * 80)
        
        return True
    
    def run_pipeline_from_file(self, file_path: str) -> bool:
        """Execute ETL pipeline from file"""
        logger.info(f"Running pipeline from file: {file_path}")
        
        if not self.extract_from_file(file_path):
            return False
        
        if not self.transform():
            return False
        
        return self.load()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get pipeline execution statistics"""
        return {
            'extracted_items': len(self.extracted_items),
            'undervalued_items': len(self.transformation_results.get('undervalued_items', [])),
            'total_properties': len(self.transformation_results.get('properties', [])),
            'transformation_timestamp': self.transformation_results.get('transformation_timestamp')
        }


# Example usage
if __name__ == "__main__":
    # Sample data for testing
    sample_data = [
        {
            'vnum': 10001,
            'name': 'Sample Sword',
            'type': 'ITEM_WEAPON',
            'icon_filename': 'sword.png',
            'proto': {'Value0': 0, 'Value1': 0, 'Value2': 0, 'Value3': 10, 'Value4': 20, 'Value5': 0},
            'yang_price': 50000,
            'won_price': 0,
            'attrs': [[71, 10], [72, 5]],
            'is_tradeable': True
        }
    ]
    
    # Create and run pipeline
    pipeline = ETLPipeline()
    success = pipeline.run_full_pipeline(sample_data)
    
    if success:
        stats = pipeline.get_statistics()
        print(f"Pipeline completed: {stats}")
    else:
        print("Pipeline failed")
