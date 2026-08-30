"""
ETL API Routes
Endpoints for triggering ETL processes and monitoring
"""

from fastapi import APIRouter, HTTPException, File, UploadFile
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from etl.pipeline import ETLPipeline
from config.servers import validate_allowed_server_id

router = APIRouter()


# Pydantic models
class ETLJobStatus(BaseModel):
    job_id: str
    status: str  # PENDING, RUNNING, COMPLETED, FAILED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    records_processed: int = 0
    records_failed: int = 0
    error_message: Optional[str] = None


class ETLJobResult(BaseModel):
    job_id: str
    status: str
    total_records: int
    successful_records: int
    failed_records: int
    execution_time_seconds: float
    timestamp: datetime


class DataIngestionRequest(BaseModel):
    source_type: str  # JSON_FILE, JSON_ARRAY, API_ENDPOINT
    source_location: str  # File path, URL, or endpoint
    force_refresh: bool = False


# Routes

@router.post("/extract/upload")
async def upload_item_data(
    file: UploadFile = File(..., description="JSON file with item data")
):
    """
    Upload and process item data from JSON file
    
    The JSON should contain an array of item objects with:
    - vnum: unique item identifier
    - name: item name
    - type: item type
    - price_yang: current price in Yang (optional)
    - attributes: array of [stat_id, value] pairs
    - And other item properties
    """
    # This would handle file upload and trigger extraction
    return {
        "message": "File received",
        "filename": file.filename,
        "size": file.size
    }


@router.post("/extract/json", response_model=ETLJobStatus)
async def extract_from_json(request: DataIngestionRequest):
    """
    Extract item data from JSON source
    
    Request body:
    - source_type: Type of source (JSON_FILE, JSON_ARRAY, API_ENDPOINT)
    - source_location: File path or URL
    - force_refresh: Whether to refresh existing items
    """
    # This would trigger ETL extraction
    return ETLJobStatus(
        job_id="JOB_001",
        status="PENDING",
        records_processed=0,
        records_failed=0
    )


@router.post("/transform", response_model=ETLJobStatus)
async def transform_extracted_data(
    job_id: str
):
    """
    Transform extracted raw data for warehouse loading
    
    This applies business logic and calculations:
    - Quality score calculation
    - Fair value estimation
    - Undervaluation detection
    - Trend analysis
    """
    # Placeholder response
    return ETLJobStatus(
        job_id=job_id,
        status="PENDING"
    )


@router.post("/load", response_model=ETLJobStatus)
async def load_to_warehouse(
    job_id: str,
    target_tables: List[str] = ["dim_item", "fact_market_transaction", "fact_price_history"]
):
    """
    Load transformed data into data warehouse
    
    Query parameters:
    - job_id: ID of transformation job
    - target_tables: Which tables to load data into
    """
    return ETLJobStatus(
        job_id=job_id,
        status="PENDING"
    )


@router.post("/run-pipeline", response_model=ETLJobStatus)
async def run_full_pipeline(request: DataIngestionRequest):
    """
    Run complete ETL pipeline (Extract -> Transform -> Load)
    
    Request body:
    - source_type: Data source type
    - source_location: Source location
    - force_refresh: Force refresh of data
    """
    return ETLJobStatus(
        job_id="PIPELINE_001",
        status="PENDING"
    )


@router.get("/job/{job_id}", response_model=ETLJobStatus)
async def get_job_status(job_id: str):
    """
    Get status of an ETL job
    
    Path parameters:
    - job_id: ID of the job to check
    """
    # This would query job status from database
    raise HTTPException(status_code=404, detail="Job not found")


@router.get("/job/{job_id}/result", response_model=ETLJobResult)
async def get_job_result(job_id: str):
    """
    Get results of a completed ETL job
    
    Path parameters:
    - job_id: ID of the job
    """
    raise HTTPException(status_code=404, detail="Job result not found")


@router.get("/jobs", response_model=List[ETLJobStatus])
async def list_etl_jobs(
    status: Optional[str] = None,
    limit: int = 20,
    skip: int = 0
):
    """
    List ETL jobs with optional status filtering
    
    Query parameters:
    - status: Filter by status (PENDING, RUNNING, COMPLETED, FAILED)
    - limit: Number of jobs to return
    - skip: Offset for pagination
    """
    return []


@router.post("/job/{job_id}/cancel")
async def cancel_etl_job(job_id: str):
    """
    Cancel a running ETL job
    
    Path parameters:
    - job_id: ID of the job to cancel
    """
    return {
        "job_id": job_id,
        "action": "cancel_requested",
        "timestamp": datetime.now()
    }


@router.post("/schedule-recurring")
async def schedule_recurring_etl(
    source_location: str,
    interval_hours: int,
    enabled: bool = True
):
    """
    Schedule recurring ETL jobs
    
    Query parameters:
    - source_location: Data source
    - interval_hours: How often to run (in hours)
    - enabled: Whether to enable the schedule
    """
    return {
        "schedule_id": "SCHED_001",
        "status": "created",
        "interval_hours": interval_hours,
        "next_run": datetime.now()
    }


@router.get("/stats", response_model=dict)
async def get_etl_statistics():
    """
    Get ETL statistics and performance metrics
    
    Returns:
    - Total jobs processed
    - Success rate
    - Average processing time
    - Recent errors
    """
    return {
        "total_jobs": 0,
        "successful_jobs": 0,
        "failed_jobs": 0,
        "success_rate": 0,
        "average_processing_time": 0,
        "total_records_loaded": 0
    }


@router.post("/validate-data")
async def validate_extracted_data(
    job_id: str
):
    """
    Validate extracted data for quality and completeness
    
    Query parameters:
    - job_id: Job ID to validate
    
    Returns:
    - Validation report with any issues found
    """
    return {
        "job_id": job_id,
        "validation_status": "valid",
        "errors": [],
        "warnings": [],
        "timestamp": datetime.now()
    }

# ============================================================================
# External Market Data Integration
# ============================================================================

class ExternalMarketDataRequest(BaseModel):
    server_id: int
    items: List[dict]
    last_sync: Optional[str] = None
    sync_timestamp: Optional[int] = None


class MarketDataDelta(BaseModel):
    server_id: int
    added_items: List[dict] = []
    updated_items: List[dict] = []
    removed_items: List[int] = []
    total_items: int = 0
    sync_timestamp: int


@router.post("/external/ingest-market-data")
async def ingest_external_market_data(data: ExternalMarketDataRequest):
    """
    Receive market data from an authorized external source.
    
    This endpoint accepts market item data from the external market tracker
    and stores it in the data warehouse with differential update tracking.
    
    Request body:
    - server_id: Server identifier (e.g., 502 for Europe)
    - items: Array of market items
    - last_sync: Timestamp of last sync
    - sync_timestamp: Unix timestamp of sync
    """
    try:
        try:
            validate_allowed_server_id(data.server_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not data.items:
            return {
                "status": "warning",
                "message": "No items in data",
                "server_id": data.server_id,
                "items_processed": 0
            }

        pipeline = ETLPipeline(server_id=data.server_id)
        ok = pipeline.run_full_pipeline(data.items)
        if not ok:
            raise HTTPException(status_code=500, detail="ETL pipeline failed")

        stats = pipeline.get_statistics()

        return {
            "status": "success",
            "message": f"Loaded {stats['extracted_items']} items into the warehouse",
            "server_id": data.server_id,
            "items_processed": stats["extracted_items"],
            "undervalued_items_found": stats["undervalued_items"],
            "timestamp": datetime.now(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data ingestion failed: {str(e)}")


@router.post("/external/market-delta")
async def get_market_delta(data: ExternalMarketDataRequest):
    """
    Calculate delta (changes) in market data
    
    Compares new market data with stored data and returns only the differences
    (added, updated, removed items). This reduces bandwidth for periodic updates.
    
    Returns delta with add/update/remove operations.
    """
    try:
        try:
            validate_allowed_server_id(data.server_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # In a real implementation, this would:
        # 1. Query existing items for the server
        # 2. Compare with new items
        # 3. Calculate differences
        # 4. Return only changes
        
        return {
            "status": "success",
            "server_id": data.server_id,
            "delta": {
                "added": len(data.items),
                "updated": 0,
                "removed": 0,
                "total": len(data.items)
            },
            "timestamp": datetime.now()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delta calculation failed: {str(e)}")


@router.get("/external/last-sync/{server_id}")
async def get_last_sync_timestamp(server_id: int):
    """
    Get last sync timestamp for a server
    
    Path parameters:
    - server_id: Server identifier
    
    try:
        validate_allowed_server_id(server_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    Returns the last sync timestamp to enable differential fetching
    """
    # In a real implementation, query the database
    return {
        "server_id": server_id,
        "last_sync_timestamp": 0,
        "last_sync_readable": "Never",
        "status": "ready_for_initial_load"
    }
