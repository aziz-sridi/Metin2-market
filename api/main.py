"""FastAPI application for the Metin2 market data warehouse.

The optional background worker:
- Sync static reference files (English) from Metin2Alerts
- Periodically fetch market data and run ETL when it changes
"""

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import random
from typing import AsyncIterator, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load environment variables
load_dotenv()

# Import routers
from api.routes import admin, analytics, dashboard, etl, items, reference
from config.settings import config


logger = logging.getLogger(__name__)

_auto_sync_task: Optional[asyncio.Task] = None


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _database_is_ready() -> None:
    """Raise when PostgreSQL cannot accept a simple query."""

    from sqlalchemy import create_engine, text

    engine = create_engine(
        config.get_db_connection_string_sqlalchemy(),
        connect_args={"connect_timeout": 3},
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()


async def _run_sync_worker() -> None:
    """Run reference sync, then poll market sources until cancelled."""

    from sync.static_data_sync import StaticSyncConfig, sync_static_data
    from sync.auto_sync import SyncConfig, run_once, DEFAULT_URL_TEMPLATE
    from config.servers import allowed_server_ids, market_state_file_for_server

    timeout = int(os.getenv("EXTERNAL_TIMEOUT_SECONDS", "30"))

    min_minutes = int(os.getenv("EXTERNAL_SYNC_MIN_MINUTES", "10"))
    max_minutes = int(os.getenv("EXTERNAL_SYNC_MAX_MINUTES", "15"))

    url_template = os.getenv("EXTERNAL_MARKET_URL_TEMPLATE", DEFAULT_URL_TEMPLATE).strip()
    if not url_template:
        logger.error(
            "External sync is enabled but EXTERNAL_MARKET_URL_TEMPLATE is not configured"
        )
        return

    if _env_flag("EXTERNAL_STATIC_SYNC_ENABLED", False):
        static_base_url = os.getenv("EXTERNAL_STATIC_BASE_URL", "").rstrip("/")
        if not static_base_url:
            logger.error(
                "Static sync is enabled but EXTERNAL_STATIC_BASE_URL is not configured"
            )
        else:
            static_cfg = StaticSyncConfig(
                base_url=static_base_url,
                output_dir=Path(os.getenv("EXTERNAL_STATIC_OUTPUT_DIR", "./data/external")),
                state_file=Path(os.getenv("EXTERNAL_STATIC_STATE_FILE", "./sync_static_state.json")),
                timeout_seconds=timeout,
            )
            static_result = await asyncio.to_thread(sync_static_data, static_cfg)
            if static_result.get("error"):
                logger.warning("Static reference sync failed: %s", static_result["error"])

    server_ids = allowed_server_ids()
    base_state_file = Path(os.getenv("EXTERNAL_MARKET_STATE_FILE", "./sync_state.json"))
    load_mode = os.getenv("EXTERNAL_SYNC_LOAD_MODE", "delta")

    if min_minutes <= 0 or max_minutes < min_minutes:
        logger.error(
            "External sync disabled: invalid interval range %s-%s minutes",
            min_minutes,
            max_minutes,
        )
        return

    while True:
        for server_id in server_ids:
            cfg = SyncConfig(
                server_id=server_id,
                url_template=url_template,
                state_file=market_state_file_for_server(base_state_file, server_id),
                interval_min_minutes=min_minutes,
                interval_max_minutes=max_minutes,
                timeout_seconds=timeout,
                load_mode=load_mode,
            )
            try:
                result_code = await asyncio.to_thread(run_once, cfg)
                if result_code:
                    logger.warning("Market sync for server %s returned %s", server_id, result_code)
            except Exception:
                logger.exception("Unexpected market sync failure for server %s", server_id)

        await asyncio.sleep(random.uniform(min_minutes, max_minutes) * 60)


async def _run_sync_worker_safely() -> None:
    """Prevent a bad remote response or setting from taking down the API."""

    try:
        await _run_sync_worker()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("External synchronization worker stopped unexpectedly")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start sync without delaying API readiness and stop it cleanly."""

    global _auto_sync_task
    if _env_flag("EXTERNAL_SYNC_ENABLED", False):
        _auto_sync_task = asyncio.create_task(
            _run_sync_worker_safely(),
            name="external-market-sync",
        )

    yield

    if _auto_sync_task is not None:
        _auto_sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await _auto_sync_task
        _auto_sync_task = None


app = FastAPI(
    title="Metin2 Market Data Warehouse API",
    description="API for querying and analyzing Metin2 in-game market data",
    version="1.0.0",
    lifespan=lifespan,
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

app.include_router(items.router, prefix="/api/items", tags=["Items"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(etl.router, prefix="/api/etl", tags=["ETL"])
app.include_router(reference.router, prefix="/api/reference", tags=["Reference"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(dashboard.router, tags=["Dashboard"])


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Return process liveness without depending on external services."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "Metin2 Market Data Warehouse"
    }


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Report whether the API can reach its PostgreSQL warehouse."""

    try:
        await asyncio.to_thread(_database_is_ready)
    except Exception as exc:
        logger.warning("Readiness check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "unavailable",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    return {
        "status": "ready",
        "database": "connected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Root endpoint with API information
@app.get("/", tags=["Info"])
async def root():
    """Get API information"""
    return {
        "name": "Metin2 Market Data Warehouse API",
        "version": "1.0.0",
        "description": "Advanced market analysis platform for Metin2 game",
        "endpoints": {
            "items": "/api/items",
            "analytics": "/api/analytics",
            "etl": "/api/etl",
            "admin": "/api/admin",
            "docs": "/docs",
            "health": "/health",
            "readiness": "/ready",
        }
    }


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle value errors"""
    return JSONResponse(
        status_code=400,
        content={
            "error": str(exc),
            "status_code": 400,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from environment
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )
