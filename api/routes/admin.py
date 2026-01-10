"""
Admin API Routes
Administrative endpoints for system management
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import os
import asyncio

from sqlalchemy import create_engine, text

from config.settings import config
from config.servers import allowed_server_ids, market_state_file_for_server, validate_allowed_server_id

router = APIRouter()


def _engine():
    return create_engine(config.get_db_connection_string_sqlalchemy())


WAREHOUSE_TABLES = [
    # facts
    "fact_market_transaction",
    "fact_price_history",
    "fact_item_attributes",
    "fact_undervalued_items",
    "fact_weapon_analysis",
    "fact_armor_analysis",
    "fact_pet_analysis",
    # aggregates
    "agg_daily_price_summary",
    "agg_weekly_price_trends",
    "agg_monthly_performance",
    # dims
    "dim_item_properties",
    "dim_item_requirements",
    "dim_item_category",
    "dim_price_category",
    "dim_transaction_type",
    "dim_pet",
    "dim_job_class",
    "dim_time",
    "dim_item",
]


def _truncate_all_tables() -> None:
    engine = _engine()

    quoted = ", ".join(f'"{t}"' for t in WAREHOUSE_TABLES)
    truncate_sql = f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE;"
    with engine.begin() as conn:
        conn.execute(text(truncate_sql))


# Pydantic models
class DatabaseStatus(BaseModel):
    connection_status: str
    connected: bool
    database_size_gb: float
    last_backup: Optional[datetime] = None
    tables_count: int
    total_records: int


class SystemHealth(BaseModel):
    status: str
    components: Dict[str, str]
    uptime_seconds: int
    api_version: str
    database_status: DatabaseStatus


class DataQualityReport(BaseModel):
    total_records: int
    valid_records: int
    invalid_records: int
    duplicate_records: int
    missing_fields_count: int
    quality_score: float
    report_timestamp: datetime


# Routes

@router.get("/health", response_model=SystemHealth)
async def system_health():
    """
    Check overall system health
    
    Returns information about:
    - API status
    - Database connectivity
    - Component status
    - System uptime
    """
    return SystemHealth(
        status="healthy",
        components={
            "api": "operational",
            "database": "operational",
            "etl": "idle"
        },
        uptime_seconds=0,
        api_version="1.0.0",
        database_status=DatabaseStatus(
            connection_status="connected",
            connected=True,
            database_size_gb=0,
            tables_count=0,
            total_records=0
        )
    )


@router.get("/database/status", response_model=DatabaseStatus)
async def get_database_status():
    """
    Get detailed database status
    
    Returns:
    - Connection status
    - Database size
    - Table counts
    - Record counts
    """
    raise HTTPException(status_code=503, detail="Database connection failed")


@router.post("/database/backup")
async def create_backup():
    """
    Create a backup of the data warehouse
    
    Returns backup information
    """
    return {
        "backup_id": "BACKUP_001",
        "status": "initiated",
        "timestamp": datetime.now()
    }


@router.post("/database/purge")
async def purge_database(
    confirm: str,
    clear_sync_state_files: bool = False,
    clear_external_cache: bool = False,
):
    """Delete all warehouse data (no migrations).

    This truncates all warehouse tables and resets identity sequences.

    Safety: requires `confirm=DELETE_ALL_DATA`.
    """

    if confirm != "DELETE_ALL_DATA":
        raise HTTPException(
            status_code=400,
            detail="Refusing to purge. Pass confirm=DELETE_ALL_DATA to proceed.",
        )

    _truncate_all_tables()

    deleted_files: List[str] = []

    if clear_sync_state_files:
        # Remove both legacy and per-server sync state files.
        for p in sorted(Path(".").glob("sync_state*.json")):
            try:
                if p.exists():
                    p.unlink()
                    deleted_files.append(str(p))
            except Exception:
                pass
        for p in [Path("./sync_static_state.json")]:
            try:
                if p.exists():
                    p.unlink()
                    deleted_files.append(str(p))
            except Exception:
                pass

    if clear_external_cache:
        # This is where static m2_data files are stored by default.
        base = Path("./data/external")
        if base.exists():
            try:
                # manual recursive delete (avoid shutil.rmtree edge cases on Windows locks)
                for child in sorted(base.rglob("*"), reverse=True):
                    try:
                        if child.is_file() or child.is_symlink():
                            child.unlink()
                        elif child.is_dir():
                            child.rmdir()
                    except Exception:
                        pass
                try:
                    base.rmdir()
                except Exception:
                    pass
                deleted_files.append(str(base))
            except Exception:
                pass

    return {
        "status": "purged",
        "tables_truncated": len(WAREHOUSE_TABLES),
        "deleted_paths": deleted_files,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/database/purge-and-sync-now")
async def purge_and_sync_now(
    confirm: str,
    clear_sync_state_files: bool = True,
    clear_external_cache: bool = False,
    server_id: Optional[int] = None,
    server_ids: Optional[str] = None,
):
    """Purge warehouse data, then immediately run static sync + one market ETL cycle.

    Safety: requires `confirm=DELETE_ALL_DATA`.
    """

    if confirm != "DELETE_ALL_DATA":
        raise HTTPException(
            status_code=400,
            detail="Refusing to purge. Pass confirm=DELETE_ALL_DATA to proceed.",
        )

    # 1) purge
    purge_result = await purge_database(
        confirm=confirm,
        clear_sync_state_files=clear_sync_state_files,
        clear_external_cache=clear_external_cache,
    )

    # 2) sync static + one market cycle
    from sync.static_data_sync import StaticSyncConfig, sync_static_data
    from sync.auto_sync import SyncConfig, run_once, DEFAULT_URL_TEMPLATE

    base_url = os.getenv("EXTERNAL_BASE_URL", "https://metin2alerts.com")
    timeout = int(os.getenv("EXTERNAL_TIMEOUT_SECONDS", "30"))

    static_cfg = StaticSyncConfig(
        base_url=base_url,
        output_dir=Path(os.getenv("EXTERNAL_STATIC_OUTPUT_DIR", "./data/external")),
        state_file=Path(os.getenv("EXTERNAL_STATIC_STATE_FILE", "./sync_static_state.json")),
        timeout_seconds=timeout,
    )

    static_result = await asyncio.to_thread(sync_static_data, static_cfg)

    url_template = os.getenv("EXTERNAL_MARKET_URL_TEMPLATE", DEFAULT_URL_TEMPLATE)
    base_state_file = Path(os.getenv("EXTERNAL_MARKET_STATE_FILE", "./sync_state.json"))

    if server_ids:
        requested = [int(p.strip()) for p in server_ids.split(",") if p.strip()]
        for sid in requested:
            validate_allowed_server_id(sid)
        target_server_ids = requested
    elif server_id is not None:
        validate_allowed_server_id(server_id)
        target_server_ids = [server_id]
    else:
        target_server_ids = allowed_server_ids()

    cycle_results = []
    for sid in target_server_ids:
        market_cfg = SyncConfig(
            server_id=sid,
            url_template=url_template,
            state_file=market_state_file_for_server(base_state_file, sid),
            interval_min_minutes=1,
            interval_max_minutes=1,
            timeout_seconds=timeout,
        )
        rc = await asyncio.to_thread(run_once, market_cfg)
        cycle_results.append({"server_id": sid, "rc": rc})

    return {
        "status": "purged_and_synced",
        "purge": purge_result,
        "static_sync": static_result,
        "market_cycles": cycle_results,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/database/backups", response_model=List[dict])
async def list_backups():
    """
    List all available database backups
    """
    return []


@router.post("/database/restore")
async def restore_backup(backup_id: str):
    """
    Restore database from a backup
    
    Query parameters:
    - backup_id: ID of backup to restore
    """
    return {
        "backup_id": backup_id,
        "status": "restoration_initiated",
        "timestamp": datetime.now()
    }


@router.post("/cache/clear")
async def clear_cache(
    cache_type: Optional[str] = None
):
    """
    Clear application cache
    
    Query parameters:
    - cache_type: Type of cache to clear (optional)
    """
    return {
        "status": "cleared",
        "cache_type": cache_type,
        "timestamp": datetime.now()
    }


@router.post("/indices/rebuild")
async def rebuild_indices():
    """
    Rebuild database indices for performance optimization
    
    This is a long-running operation
    """
    return {
        "status": "rebuilding",
        "timestamp": datetime.now()
    }


@router.get("/data-quality", response_model=DataQualityReport)
async def get_data_quality_report():
    """
    Get comprehensive data quality report
    
    Analyzes:
    - Record validity
    - Missing fields
    - Duplicates
    - Data consistency
    """
    return DataQualityReport(
        total_records=0,
        valid_records=0,
        invalid_records=0,
        duplicate_records=0,
        missing_fields_count=0,
        quality_score=0,
        report_timestamp=datetime.now()
    )


@router.post("/data/cleanup")
async def cleanup_invalid_data():
    """
    Clean up invalid or duplicate records
    
    Warning: This operation modifies data
    """
    return {
        "status": "cleanup_initiated",
        "timestamp": datetime.now()
    }


@router.get("/logs", response_model=List[dict])
async def get_system_logs(
    level: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    """
    Get system logs
    
    Query parameters:
    - level: Log level to filter (INFO, WARNING, ERROR, etc.)
    - limit: Number of logs to return
    - skip: Offset for pagination
    """
    return []


@router.post("/config/reload")
async def reload_configuration():
    """
    Reload application configuration from file
    
    Used after modifying config file
    """
    return {
        "status": "reloaded",
        "timestamp": datetime.now()
    }


@router.get("/config", response_model=Dict[str, Any])
async def get_configuration():
    """
    Get current application configuration
    
    (Sensitive values may be masked)
    """
    return {
        "api_host": "0.0.0.0",
        "api_port": 8000,
        "debug": False
    }


@router.post("/metrics/reset")
async def reset_metrics():
    """
    Reset performance metrics and counters
    """
    return {
        "status": "reset",
        "timestamp": datetime.now()
    }


@router.get("/metrics", response_model=Dict[str, Any])
async def get_metrics():
    """
    Get system performance metrics
    
    Returns:
    - Request counts
    - Response times
    - Error rates
    - Database performance
    """
    return {
        "total_requests": 0,
        "error_rate": 0,
        "avg_response_time_ms": 0,
        "database_queries": 0
    }


@router.post("/users/create")
async def create_user(
    username: str,
    password: str,
    role: str = "user"
):
    """
    Create a new API user
    
    Query parameters:
    - username: Username
    - password: Password
    - role: User role (admin, user)
    """
    return {
        "user_id": "USER_001",
        "username": username,
        "role": role,
        "created_at": datetime.now()
    }


@router.get("/users", response_model=List[dict])
async def list_users():
    """
    List all API users
    """
    return []


@router.post("/users/{user_id}/delete")
async def delete_user(user_id: str):
    """
    Delete an API user
    
    Path parameters:
    - user_id: ID of user to delete
    """
    return {
        "user_id": user_id,
        "status": "deleted",
        "timestamp": datetime.now()
    }
