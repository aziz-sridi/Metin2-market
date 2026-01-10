"""FastAPI Application for Metin2 Market Data Warehouse.

This server also runs an automatic external sync loop:
- Sync static reference files (English) from Metin2Alerts
- Periodically fetch market data and run ETL when it changes
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date, timedelta
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routers
from api.routes import items, analytics, etl, admin, reference
from api.routes import dashboard

# Initialize FastAPI app
app = FastAPI(
    title="Metin2 Market Data Warehouse API",
    description="API for querying and analyzing Metin2 in-game market data",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(items.router, prefix="/api/items", tags=["Items"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(etl.router, prefix="/api/etl", tags=["ETL"])
app.include_router(reference.router, prefix="/api/reference", tags=["Reference"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(dashboard.router, tags=["Dashboard"])


_auto_sync_task: Optional[asyncio.Task] = None


async def _run_startup_sync() -> None:
    """Run one-time static sync and start the periodic market+ETL loop."""

    from sync.static_data_sync import StaticSyncConfig, sync_static_data
    from sync.auto_sync import SyncConfig, run_once, DEFAULT_URL_TEMPLATE
    from config.servers import allowed_server_ids, market_state_file_for_server

    base_url = os.getenv("EXTERNAL_BASE_URL", "https://metin2alerts.com")
    timeout = int(os.getenv("EXTERNAL_TIMEOUT_SECONDS", "30"))

    min_minutes = int(os.getenv("EXTERNAL_SYNC_MIN_MINUTES", "10"))
    max_minutes = int(os.getenv("EXTERNAL_SYNC_MAX_MINUTES", "15"))

    # 1) Sync static reference data once at startup (English only)
    static_cfg = StaticSyncConfig(
        base_url=base_url,
        output_dir=Path(os.getenv("EXTERNAL_STATIC_OUTPUT_DIR", "./data/external")),
        state_file=Path(os.getenv("EXTERNAL_STATIC_STATE_FILE", "./sync_static_state.json")),
        timeout_seconds=timeout,
    )
    await asyncio.to_thread(sync_static_data, static_cfg)

    # 2) Start periodic market sync that runs ETL only on change (limited servers)
    server_ids = allowed_server_ids()
    url_template = os.getenv("EXTERNAL_MARKET_URL_TEMPLATE", DEFAULT_URL_TEMPLATE)
    base_state_file = Path(os.getenv("EXTERNAL_MARKET_STATE_FILE", "./sync_state.json"))

    async def _loop() -> None:
        # Basic validation
        if min_minutes <= 0 or max_minutes <= 0:
            return
        if max_minutes < min_minutes:
            return

        while True:
            for sid in server_ids:
                cfg = SyncConfig(
                    server_id=sid,
                    url_template=url_template,
                    state_file=market_state_file_for_server(base_state_file, sid),
                    interval_min_minutes=min_minutes,
                    interval_max_minutes=max_minutes,
                    timeout_seconds=timeout,
                )
                try:
                    await asyncio.to_thread(run_once, cfg)
                except Exception:
                    # Keep the server alive even if a single server cycle fails
                    pass

            sleep_minutes = min_minutes
            # Simple fixed sleep (avoid extra jitter complexity inside the API process)
            await asyncio.sleep(sleep_minutes * 60)

    global _auto_sync_task
    _auto_sync_task = asyncio.create_task(_loop())


@app.on_event("startup")
async def _on_startup() -> None:
    await _run_startup_sync()


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    global _auto_sync_task
    if _auto_sync_task:
        _auto_sync_task.cancel()
        _auto_sync_task = None


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Check API health status"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Metin2 Market Data Warehouse"
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
            "health": "/health"
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
            "timestamp": datetime.now().isoformat()
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
            "timestamp": datetime.now().isoformat()
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from environment
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )
