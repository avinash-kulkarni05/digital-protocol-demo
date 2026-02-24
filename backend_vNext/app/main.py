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


@app.post("/api/v1/admin/setup-pgvector")
async def setup_pgvector(admin_key: str = ""):
    """Setup pgvector extension and omop_concepts table. Requires APP_PASSWORD."""
    import psycopg2
    import os

    app_password = os.environ.get("APP_PASSWORD", "")
    if not admin_key or admin_key != app_password:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Invalid admin key")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"status": "error", "message": "DATABASE_URL not set"}

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS omop_concepts (
                id SERIAL PRIMARY KEY,
                concept_id INTEGER NOT NULL,
                concept_name TEXT NOT NULL,
                domain_id VARCHAR(50),
                vocabulary_id VARCHAR(50),
                concept_class_id VARCHAR(50),
                standard_concept VARCHAR(1),
                concept_code VARCHAR(100),
                valid_start_date DATE,
                valid_end_date DATE,
                invalid_reason VARCHAR(1),
                synonyms TEXT[],
                metadata JSONB,
                embedding vector(1536),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        indexes = [
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_omop_concepts_concept_id ON omop_concepts(concept_id)",
            "CREATE INDEX IF NOT EXISTS idx_omop_concepts_domain ON omop_concepts(domain_id)",
            "CREATE INDEX IF NOT EXISTS idx_omop_concepts_vocabulary ON omop_concepts(vocabulary_id)",
            "CREATE INDEX IF NOT EXISTS idx_omop_concepts_standard ON omop_concepts(standard_concept)",
            "CREATE INDEX IF NOT EXISTS idx_omop_concepts_name_lower ON omop_concepts(lower(concept_name))",
            "CREATE INDEX IF NOT EXISTS idx_omop_concepts_embedding_hnsw ON omop_concepts USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)",
        ]
        for sql in indexes:
            cur.execute(sql)

        cur.execute("SELECT count(*) FROM omop_concepts;")
        count = cur.fetchone()[0]

        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'omop_concepts';")
        idx_names = [r[0] for r in cur.fetchall()]

        cur.close()
        conn.close()

        return {
            "status": "success",
            "message": "pgvector setup complete",
            "row_count": count,
            "indexes": idx_names,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/v1/admin/drop-tables")
async def drop_tables(admin_key: str = ""):
    """Drop all tables except omop_concepts. Requires APP_PASSWORD."""
    import psycopg2
    import os

    app_password = os.environ.get("APP_PASSWORD", "")
    if not admin_key or admin_key != app_password:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Invalid admin key")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"status": "error", "message": "DATABASE_URL not set"}

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cur = conn.cursor()

        tables_to_drop = [
            "eligibility_jobs", "extraction_cache", "extraction_outputs",
            "job_events", "jobs", "module_results", "protocols", "session",
            "soa_edit_audit", "soa_jobs", "soa_merge_group_results",
            "soa_merge_plans", "soa_table_results", "usdm_documents", "usdm_edit_audit"
        ]

        cur.execute(f"DROP TABLE IF EXISTS {', '.join(tables_to_drop)} CASCADE;")

        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;")
        remaining = [r[0] for r in cur.fetchall()]

        cur.close()
        conn.close()

        return {"status": "success", "remaining_tables": remaining}
    except Exception as e:
        return {"status": "error", "message": str(e)}



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
