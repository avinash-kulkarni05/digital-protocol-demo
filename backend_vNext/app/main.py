"""
FastAPI application entry point for backend_vNext.

Provides REST API for:
- Protocol PDF upload
- Extraction job management
- Real-time progress via SSE
- Module result retrieval
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_schema


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting backend_vNext application...")

    # Ensure directories exist
    for dir_path in [settings.uploads_dir, settings.outputs_dir, settings.tmp_dir]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    # Initialize database schema
    try:
        init_schema()
        logger.info("Database schema initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise

    logger.info("backend_vNext application started")
    yield

    # Shutdown
    logger.info("Shutting down backend_vNext application...")


# Create FastAPI application
app = FastAPI(
    title="Backend vNext",
    description="Next-generation protocol extraction pipeline with 100% provenance coverage",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "schema": settings.db_schema,
    }


# Import and include routers
from app.routers import protocol, jobs, auth, soa, eligibility
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(protocol.router, prefix="/api/v1/protocols", tags=["protocols"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(soa.router, prefix="/api/v1", tags=["soa"])
app.include_router(eligibility.router, prefix="/api/v1", tags=["eligibility"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=settings.debug,
    )
