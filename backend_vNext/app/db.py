"""
SQLAlchemy models for backend_vnext schema.

All tables are created in the 'backend_vnext' schema to isolate from existing data.
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, Index, UniqueConstraint, create_engine, text, LargeBinary, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from sqlalchemy.pool import QueuePool

from app.config import settings


# Schema name for all tables
SCHEMA_NAME = "backend_vnext"

# Create base with schema
Base = declarative_base()


class Protocol(Base):
    """Uploaded protocol PDFs with Gemini File API cache."""

    __tablename__ = "protocols"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    protocol_name = Column(String(255), nullable=True)  # Human-readable protocol name
    file_hash = Column(String(64), nullable=False, unique=True)
    file_path = Column(String(500), nullable=True)  # Kept for backward compatibility
    file_data = Column(LargeBinary, nullable=True)  # PDF binary data (BYTEA)
    file_size = Column(BigInteger, nullable=True)  # File size in bytes
    content_type = Column(String(100), nullable=True, default="application/pdf")
    usdm_json = Column(JSONB, nullable=True)  # Extracted USDM 4.0 data for display
    extraction_status = Column(String(50), nullable=True)  # pending, processing, completed, failed
    gemini_file_uri = Column(String(500), nullable=True)
    gemini_file_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    jobs = relationship("Job", back_populates="protocol", cascade="all, delete-orphan")
    extraction_outputs = relationship("ExtractionOutput", back_populates="protocol", cascade="all, delete-orphan")


class Job(Base):
    """Extraction job tracking."""

    __tablename__ = "jobs"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    protocol_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.protocols.id"), nullable=False)
    protocol_name = Column(String(255), nullable=True)  # Human-readable protocol name
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    current_module = Column(String(100), nullable=True)
    completed_modules = Column(JSONB, default=list)
    failed_modules = Column(JSONB, default=list)
    total_modules = Column(Integer, default=10)
    output_directory = Column(String(1000), nullable=True)  # Path to extraction output directory
    output_files = Column(JSONB, nullable=True)  # List of output files with metadata
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    protocol = relationship("Protocol", back_populates="jobs")
    module_results = relationship("ModuleResult", back_populates="job", cascade="all, delete-orphan")
    events = relationship("JobEvent", back_populates="job", cascade="all, delete-orphan")
    extraction_outputs = relationship("ExtractionOutput", back_populates="job", cascade="all, delete-orphan")


class ModuleResult(Base):
    """Per-module extraction results."""

    __tablename__ = "module_results"
    __table_args__ = (
        UniqueConstraint("job_id", "module_id", name="uq_module_results_job_module"),
        {"schema": SCHEMA_NAME}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.jobs.id"), nullable=False)
    protocol_name = Column(String(255), nullable=True)  # Human-readable protocol name
    module_id = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False)  # completed, failed
    extracted_data = Column(JSONB, nullable=True)
    provenance_coverage = Column(Float, nullable=True)  # 0.0 to 1.0
    compliance_score = Column(Float, nullable=True)
    # Full 5D quality scores (accuracy, completeness, usdm_adherence, provenance, terminology, overall)
    quality_scores = Column(JSONB, nullable=True)
    pass1_duration_seconds = Column(Float, nullable=True)
    pass2_duration_seconds = Column(Float, nullable=True)
    retry_count = Column(Integer, default=0)
    from_cache = Column(Boolean, default=False)
    error_details = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    job = relationship("Job", back_populates="module_results")


class JobEvent(Base):
    """Job events for SSE streaming."""

    __tablename__ = "job_events"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.jobs.id"), nullable=False)
    protocol_name = Column(String(255), nullable=True)  # Human-readable protocol name
    event_type = Column(String(50), nullable=False)  # module_started, module_completed, etc.
    module_id = Column(String(100), nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    job = relationship("Job", back_populates="events")


class ExtractionOutput(Base):
    """Extraction output files stored in database."""
    __tablename__ = "extraction_outputs"
    __table_args__ = (
        UniqueConstraint("job_id", "file_type", name="uq_extraction_outputs_job_type"),
        {"schema": SCHEMA_NAME}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.jobs.id"), nullable=False)
    protocol_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.protocols.id"), nullable=False)
    protocol_name = Column(String(255), nullable=True)  # Human-readable protocol name
    file_type = Column(String(50), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_data = Column(LargeBinary, nullable=True)
    json_data = Column(JSONB, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    content_type = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    job = relationship("Job", back_populates="extraction_outputs")
    protocol = relationship("Protocol", back_populates="extraction_outputs")


class ExtractionCache(Base):
    """Database-backed cache for 16-agent extraction pipeline."""

    __tablename__ = "extraction_cache"
    __table_args__ = (
        UniqueConstraint("pdf_hash", "module_id", "model_name", "prompt_hash", name="uq_cache_key"),
        {"schema": SCHEMA_NAME}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    protocol_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.protocols.id"), nullable=True)  # Link to protocol
    protocol_name = Column(String(255), nullable=True)  # Human-readable protocol name
    module_id = Column(String(100), nullable=False)
    model_name = Column(String(100), nullable=False)
    pdf_hash = Column(String(64), nullable=False)  # SHA256 hash of PDF
    prompt_hash = Column(String(64), nullable=False)  # SHA256 hash of prompts+schema
    extracted_data = Column(JSONB, nullable=False)
    quality_score = Column(JSONB, nullable=True)
    pdf_path = Column(String(500), nullable=True)
    cache_hits = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    accessed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    protocol = relationship("Protocol")


class SOAJob(Base):
    """SOA extraction job with human-in-the-loop checkpoint support."""

    __tablename__ = "soa_jobs"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    protocol_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.protocols.id"), nullable=False)
    protocol_name = Column(String(255), nullable=True)  # Human-readable protocol name

    # Status: detecting_pages, awaiting_page_confirmation, extracting, interpreting, validating, completed, failed
    status = Column(String(50), default="detecting_pages")

    # Page detection results (checkpoint data)
    detected_pages = Column(JSONB, nullable=True)  # Pages detected by Phase 1
    confirmed_pages = Column(JSONB, nullable=True)  # Pages confirmed/corrected by user

    # Progress tracking
    phase_progress = Column(JSONB, nullable=True)  # { "phase": "extraction", "progress": 50 }
    current_phase = Column(String(50), nullable=True)  # Current phase name

    # Results
    usdm_data = Column(JSONB, nullable=True)  # Final USDM output
    quality_report = Column(JSONB, nullable=True)  # Quality validation results
    extraction_review = Column(JSONB, nullable=True)  # Raw extraction for review
    interpretation_review = Column(JSONB, nullable=True)  # Interpretation stages output

    # Merge Analysis (Phase 3.5) - stores merge plan and confirmation
    merge_analysis = Column(JSONB, nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    protocol = relationship("Protocol")
    table_results = relationship("SOATableResult", back_populates="soa_job", cascade="all, delete-orphan")
    edit_audits = relationship("SOAEditAudit", back_populates="soa_job", cascade="all, delete-orphan")


class SOATableResult(Base):
    """Per-table SOA extraction results.

    Stores individual USDM output for each SOA table found in a protocol.
    This enables:
    - Granular quality control (identify which table has issues)
    - Modular review (approve tables individually)
    - Independent re-processing (fix one table without re-running all)
    - Better traceability (each table linked to source pages)
    """

    __tablename__ = "soa_table_results"
    __table_args__ = (
        UniqueConstraint("soa_job_id", "table_id", name="uq_soa_table_results_job_table"),
        {"schema": SCHEMA_NAME}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    soa_job_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.soa_jobs.id"), nullable=False)
    protocol_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.protocols.id"), nullable=False)
    protocol_name = Column(String(255), nullable=True)

    # Table identification
    table_id = Column(String(50), nullable=False)  # SOA-1, SOA-2, etc.
    table_category = Column(String(50), nullable=False)  # MAIN_SOA, PK_SOA, SAFETY_SOA, PD_SOA
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)

    # Extraction status
    status = Column(String(50), nullable=False)  # success, failed, pending
    error_message = Column(Text, nullable=True)

    # Core USDM data for this table
    usdm_data = Column(JSONB, nullable=True)  # Full USDM for this specific table

    # Quality metrics
    quality_score = Column(JSONB, nullable=True)  # 5D quality scores

    # Counts for quick access without parsing JSONB
    visits_count = Column(Integer, default=0)
    activities_count = Column(Integer, default=0)
    sais_count = Column(Integer, default=0)  # scheduledActivityInstances
    footnotes_count = Column(Integer, default=0)

    # Interpretation pipeline stages (optional - for debugging)
    interpretation_stages = Column(JSONB, nullable=True)  # Stage-by-stage results

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    soa_job = relationship("SOAJob", back_populates="table_results")
    protocol = relationship("Protocol")


class SOAEditAudit(Base):
    """Audit trail for SOA field edits."""

    __tablename__ = "soa_edit_audit"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(Integer, primary_key=True, autoincrement=True)
    soa_job_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.soa_jobs.id"), nullable=False)
    protocol_id = Column(UUID(as_uuid=True), nullable=True)
    protocol_name = Column(String(255), nullable=True)
    field_path = Column(String(500), nullable=False)
    original_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    edit_type = Column(String(50), nullable=True)  # 'update', 'add', 'delete'
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    soa_job = relationship("SOAJob", back_populates="edit_audits")


class SOAMergePlan(Base):
    """SOA table merge plan for human-in-the-loop confirmation.

    Stores the suggested merge groups from the 8-level merge analysis,
    allowing human review and confirmation before running interpretation.
    """

    __tablename__ = "soa_merge_plans"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    soa_job_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.soa_jobs.id"), nullable=False)
    protocol_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.protocols.id"), nullable=False)
    protocol_name = Column(String(255), nullable=True)

    # Status: pending_confirmation, confirmed, modified
    status = Column(String(50), default="pending_confirmation")

    # Merge plan JSON (MergePlan.to_dict())
    merge_plan = Column(JSONB, nullable=False)

    # Summary counts
    total_tables_input = Column(Integer, nullable=True)
    merge_groups_output = Column(Integer, nullable=True)

    # Confirmation tracking
    confirmed_at = Column(DateTime, nullable=True)
    confirmed_by = Column(String(255), nullable=True)
    confirmed_plan = Column(JSONB, nullable=True)  # Final confirmed plan after user edits

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    soa_job = relationship("SOAJob")
    protocol = relationship("Protocol")
    group_results = relationship("SOAMergeGroupResult", back_populates="merge_plan", cascade="all, delete-orphan")


class SOAMergeGroupResult(Base):
    """Result of 12-stage interpretation for a single merge group.

    Stores the USDM output after running the interpretation pipeline
    on a confirmed merge group (which may contain 1 or more tables).
    """

    __tablename__ = "soa_merge_group_results"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    soa_job_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.soa_jobs.id"), nullable=False)
    merge_plan_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.soa_merge_plans.id"), nullable=False)
    protocol_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.protocols.id"), nullable=False)
    protocol_name = Column(String(255), nullable=True)

    # Merge group identification
    merge_group_id = Column(String(50), nullable=False)  # MG-001, MG-002, etc.
    source_table_ids = Column(JSONB, nullable=False)  # ["SOA-1", "SOA-2"]
    merge_type = Column(String(50), nullable=True)  # physical_continuation, same_schedule, etc.

    # Status: pending, interpreting, completed, failed
    status = Column(String(50), default="pending")
    error_message = Column(Text, nullable=True)

    # Combined USDM before interpretation
    merged_usdm = Column(JSONB, nullable=True)

    # Interpretation result
    interpretation_result = Column(JSONB, nullable=True)
    final_usdm = Column(JSONB, nullable=True)

    # Quality metrics
    quality_score = Column(JSONB, nullable=True)

    # Counts for quick access
    visits_count = Column(Integer, default=0)
    activities_count = Column(Integer, default=0)
    sais_count = Column(Integer, default=0)
    footnotes_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    soa_job = relationship("SOAJob")
    merge_plan = relationship("SOAMergePlan", back_populates="group_results")
    protocol = relationship("Protocol")


class EligibilityJob(Base):
    """Eligibility extraction job with human-in-the-loop checkpoint support."""

    __tablename__ = "eligibility_jobs"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    protocol_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.protocols.id"), nullable=False)
    protocol_name = Column(String(255), nullable=True)  # Human-readable protocol name

    # Status: detecting_sections, awaiting_section_confirmation, extracting, interpreting, validating, completed, failed
    status = Column(String(50), default="detecting_sections")

    # Section detection results (checkpoint data)
    detected_sections = Column(JSONB, nullable=True)  # Sections detected by Phase 1
    confirmed_sections = Column(JSONB, nullable=True)  # Sections confirmed/corrected by user

    # Progress tracking
    current_phase = Column(String(50), nullable=True)  # detection, extraction, interpretation, validation, output
    phase_progress = Column(JSONB, nullable=True)  # { "phase": "interpretation", "progress": 50, "stage": 5 }
    # Note: stage info is stored in phase_progress["stage"], no separate column needed

    # Results
    usdm_data = Column(JSONB, nullable=True)  # Final USDM eligibility output
    quality_report = Column(JSONB, nullable=True)  # 5D quality validation results
    interpretation_result = Column(JSONB, nullable=True)  # Full interpretation pipeline audit trail
    raw_criteria = Column(JSONB, nullable=True)  # Raw extracted criteria (Phase 2 output)
    feasibility_result = Column(JSONB, nullable=True)  # Stage 11 feasibility analysis
    qeb_result = Column(JSONB, nullable=True)  # Stage 12 QEB builder output

    # Counts
    inclusion_count = Column(Integer, nullable=True)
    exclusion_count = Column(Integer, nullable=True)
    atomic_count = Column(Integer, nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    protocol = relationship("Protocol")


class USDMDocument(Base):
    """USDM 4.0 extracted documents for frontend review UI."""

    __tablename__ = "usdm_documents"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(Integer, primary_key=True, autoincrement=True)
    study_id = Column(String(255), nullable=False, unique=True)
    study_title = Column(Text, nullable=False)
    usdm_data = Column(JSONB, nullable=False)
    source_document_url = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    edit_audits = relationship("USDMEditAudit", back_populates="document", cascade="all, delete-orphan")


class USDMEditAudit(Base):
    """Audit trail for USDM field edits with full snapshots."""

    __tablename__ = "usdm_edit_audit"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey(f"{SCHEMA_NAME}.usdm_documents.id"), nullable=False)
    study_id = Column(String(255), nullable=False)
    study_title = Column(Text, nullable=True)
    field_path = Column(String(500), nullable=False)
    original_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    original_usdm = Column(JSONB, nullable=True)
    updated_usdm = Column(JSONB, nullable=True)
    updated_by = Column(String(255), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    document = relationship("USDMDocument", back_populates="edit_audits")


# Indexes
Index("idx_jobs_protocol_id", Job.protocol_id)
Index("idx_jobs_status", Job.status)
Index("idx_module_results_job_id", ModuleResult.job_id)
Index("idx_job_events_job_id", JobEvent.job_id)
Index("idx_cache_lookup", ExtractionCache.pdf_hash, ExtractionCache.module_id, ExtractionCache.model_name)
Index("idx_cache_accessed", ExtractionCache.accessed_at)
Index("idx_cache_protocol_id", ExtractionCache.protocol_id)
Index("idx_soa_jobs_protocol_id", SOAJob.protocol_id)
Index("idx_soa_jobs_status", SOAJob.status)
Index("idx_eligibility_jobs_protocol_id", EligibilityJob.protocol_id)
Index("idx_eligibility_jobs_status", EligibilityJob.status)
Index("idx_usdm_documents_study_id", USDMDocument.study_id)
Index("idx_usdm_edit_audit_document_id", USDMEditAudit.document_id)
Index("idx_soa_edit_audit_job_id", SOAEditAudit.soa_job_id)
Index("idx_soa_table_results_job_id", SOATableResult.soa_job_id)
Index("idx_soa_table_results_protocol_id", SOATableResult.protocol_id)
Index("idx_soa_table_results_category", SOATableResult.table_category)
Index("idx_soa_merge_plans_job_id", SOAMergePlan.soa_job_id)
Index("idx_soa_merge_plans_protocol_id", SOAMergePlan.protocol_id)
Index("idx_soa_merge_plans_status", SOAMergePlan.status)
Index("idx_soa_merge_group_results_job_id", SOAMergeGroupResult.soa_job_id)
Index("idx_soa_merge_group_results_plan_id", SOAMergeGroupResult.merge_plan_id)
Index("idx_soa_merge_group_results_status", SOAMergeGroupResult.status)


# Database engine and session factory
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create database engine with auto-reconnect for NeonDB."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=300,  # Recycle connections every 5 minutes (NeonDB timeout)
            pool_pre_ping=True,  # Test connection before using (auto-reconnect)
            echo=settings.debug,
            connect_args={
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            }
        )
    return _engine


def get_session_factory():
    """Get or create session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine()
        )
    return _SessionLocal


def get_db() -> Session:
    """Get database session (dependency injection)."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        # Set search path to backend_vnext schema
        db.execute(text(f"SET search_path TO {SCHEMA_NAME}"))
        yield db
    finally:
        try:
            db.close()
        except Exception:
            # Connection may be stale due to NeonDB SSL timeout - ignore close errors
            pass


def init_schema():
    """Initialize database schema (create tables if not exist)."""
    engine = get_engine()

    # Create schema if not exists
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"))
        conn.commit()

    # Create all tables in the schema
    Base.metadata.create_all(bind=engine)


def drop_schema():
    """Drop entire schema (use with caution)."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE"))
        conn.commit()
