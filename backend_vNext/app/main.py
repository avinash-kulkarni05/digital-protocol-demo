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


def _seed_if_empty():
    """Seed production database with dev data if tables are empty."""
    import psycopg2
    db_url = settings.effective_database_url
    if not db_url:
        logger.warning("_seed_if_empty: No database URL available - cannot seed")
        return

    db_host = db_url.split("@")[1].split("/")[0] if "@" in db_url else "unknown"
    logger.info(f"_seed_if_empty: Connecting to database host={db_host}")

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()

        try:
            cur.execute("SELECT count(*) FROM backend_vnext.protocols")
            count = cur.fetchone()[0]
            if count > 0:
                logger.info(f"Database already has {count} protocols - skipping seed")
                return
        except Exception as e:
            logger.info(f"Protocols table not ready yet - skipping seed: {str(e)[:100]}")
            return

        seed_candidates = [
            Path(__file__).parent.parent / "seed_data.sql",
            Path("/home/runner/workspace/backend_vNext/seed_data.sql"),
            Path(__file__).parent.parent.parent / "scripts" / "seed_data_lean.sql",
            Path("/home/runner/workspace/scripts/seed_data_lean.sql"),
        ]
        seed_file = None
        for candidate in seed_candidates:
            logger.info(f"Checking seed path: {candidate} exists={candidate.exists()}")
            if candidate.exists():
                seed_file = candidate
                break

        if not seed_file:
            logger.error(f"SEED FILE NOT FOUND. Tried: {[str(c) for c in seed_candidates]}")
            return

        logger.info(f"Database is empty - seeding from {seed_file} ({seed_file.stat().st_size / 1024:.0f} KB)...")

        success = 0
        errors = 0

        with open(seed_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("--"):
                    continue
                try:
                    cur.execute(line)
                    success += 1
                except Exception as e:
                    errors += 1
                    if errors <= 5:
                        logger.warning(f"Seed error: {str(e)[:200]}")
                    try:
                        cur.close()
                        conn.close()
                    except Exception:
                        pass
                    conn = psycopg2.connect(db_url)
                    conn.autocommit = True
                    cur = conn.cursor()

        logger.info(f"Seeding complete: {success} succeeded, {errors} errors")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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

    # Seed production data if tables are empty
    try:
        _seed_if_empty()
    except Exception as e:
        logger.warning(f"Data seeding skipped due to error: {e}")

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
