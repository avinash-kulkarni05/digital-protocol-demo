#!/usr/bin/env python3
"""
Initialize the PostgreSQL schema in NeonDB.

This script creates all tables in the 'public' schema.

Usage:
    source venv/bin/activate
    python init_schema.py
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load .env from parent directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in .env file")
    sys.exit(1)

# SQL to create tables in public schema
SCHEMA_SQL = """
-- ============================================================
-- PUBLIC SCHEMA INITIALIZATION
-- ============================================================
-- Creates all tables in the public schema
-- ============================================================

-- ============================================================
-- TABLE: protocols
-- ============================================================
-- Stores uploaded protocol PDFs with Gemini File API cache
-- Now supports binary storage in database (file_data BYTEA column)
-- ============================================================
CREATE TABLE IF NOT EXISTS protocols (
    id VARCHAR(64) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    filename VARCHAR(255) NOT NULL,
    protocol_name VARCHAR(255),
    file_hash VARCHAR(64) NOT NULL UNIQUE,
    file_path VARCHAR(500),
    file_data BYTEA,
    file_size BIGINT,
    content_type VARCHAR(100) DEFAULT 'application/pdf',
    gemini_file_uri VARCHAR(500),
    gemini_file_expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE protocols IS 'Uploaded protocol PDFs with Gemini File API cache. Supports both filesystem (file_path) and database storage (file_data).';
COMMENT ON COLUMN protocols.file_data IS 'Binary PDF data stored in database (BYTEA)';
COMMENT ON COLUMN protocols.file_size IS 'Size of PDF file in bytes';
COMMENT ON COLUMN protocols.content_type IS 'MIME type of uploaded file';
COMMENT ON COLUMN protocols.gemini_file_uri IS 'Cached Gemini File API URI (48-hour expiry)';

-- ============================================================
-- TABLE: jobs
-- ============================================================
-- Extraction jobs - one job runs all 10 modules sequentially
-- ============================================================
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(64) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    protocol_id VARCHAR(64) NOT NULL REFERENCES protocols(id),
    protocol_name VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    current_module VARCHAR(100),
    completed_modules JSONB DEFAULT '[]'::jsonb,
    failed_modules JSONB DEFAULT '[]'::jsonb,
    total_modules INTEGER DEFAULT 10,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE jobs IS 'Extraction jobs - one job = all 10 modules for a protocol';
COMMENT ON COLUMN jobs.status IS 'pending, running, completed, failed';
COMMENT ON COLUMN jobs.completed_modules IS 'Array of completed module IDs';

-- ============================================================
-- TABLE: module_results
-- ============================================================
-- Per-module extraction results with provenance tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS module_results (
    id VARCHAR(64) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    job_id VARCHAR(64) NOT NULL REFERENCES jobs(id),
    protocol_name VARCHAR(255),
    module_id VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    extracted_data JSONB,
    provenance_coverage FLOAT,
    compliance_score FLOAT,
    pass1_duration_seconds FLOAT,
    pass2_duration_seconds FLOAT,
    retry_count INTEGER DEFAULT 0,
    error_details JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(job_id, module_id)
);

COMMENT ON TABLE module_results IS 'Per-module extraction results with provenance tracking';
COMMENT ON COLUMN module_results.provenance_coverage IS '0.0 to 1.0 - target is 1.0 (100%)';
COMMENT ON COLUMN module_results.extracted_data IS 'Pass 1 + Pass 2 merged result';

-- ============================================================
-- TABLE: job_events
-- ============================================================
-- Job events for SSE streaming
-- ============================================================
CREATE TABLE IF NOT EXISTS job_events (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL REFERENCES jobs(id),
    protocol_name VARCHAR(255),
    event_type VARCHAR(50) NOT NULL,
    module_id VARCHAR(100),
    payload JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE job_events IS 'Job events for SSE streaming';
COMMENT ON COLUMN job_events.event_type IS 'module_started, module_completed, job_failed, etc.';

-- ============================================================
-- TABLE: extraction_cache
-- ============================================================
-- Database-backed cache for 16-agent extraction pipeline
-- Replaces file-based cache with database persistence
-- ============================================================
CREATE TABLE IF NOT EXISTS extraction_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    protocol_name VARCHAR(255),
    module_id VARCHAR(100) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    pdf_hash VARCHAR(64) NOT NULL,
    prompt_hash VARCHAR(64) NOT NULL,
    extracted_data JSONB NOT NULL,
    quality_score JSONB,
    pdf_path VARCHAR(500),
    cache_hits INTEGER DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    accessed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (pdf_hash, module_id, model_name, prompt_hash)
);

COMMENT ON TABLE extraction_cache IS 'Database-backed cache for extraction pipeline results';
COMMENT ON COLUMN extraction_cache.pdf_hash IS 'SHA256 hash of PDF file (first 1MB + file size)';
COMMENT ON COLUMN extraction_cache.prompt_hash IS 'SHA256 hash of combined pass1+pass2+schema';
COMMENT ON COLUMN extraction_cache.cache_hits IS 'Number of times this cache entry was retrieved';

-- ============================================================
-- EXTRACTION OUTPUTS TABLE
-- ============================================================
-- Stores all extraction output files (PDFs and JSONs) in database
CREATE TABLE IF NOT EXISTS extraction_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    protocol_id UUID NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
    protocol_name VARCHAR(255),
    file_type VARCHAR(50) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_data BYTEA,
    json_data JSONB,
    file_size BIGINT,
    content_type VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(job_id, file_type)
);

CREATE INDEX IF NOT EXISTS idx_extraction_outputs_job_id ON extraction_outputs(job_id);
CREATE INDEX IF NOT EXISTS idx_extraction_outputs_protocol_id ON extraction_outputs(protocol_id);
CREATE INDEX IF NOT EXISTS idx_extraction_outputs_job_type ON extraction_outputs(job_id, file_type);

COMMENT ON TABLE extraction_outputs IS 'Database storage for all extraction output files (annotated PDF, quality report, etc.)';
COMMENT ON COLUMN extraction_outputs.file_type IS 'Type: usdm_json, extraction_results, quality_report, annotated_pdf, annotation_report';
COMMENT ON COLUMN extraction_outputs.file_data IS 'Binary data for PDF files';
COMMENT ON COLUMN extraction_outputs.json_data IS 'JSONB data for JSON files (queryable)';

-- ============================================================
-- TABLE: usdm_documents (for frontend review UI)
-- ============================================================
CREATE TABLE IF NOT EXISTS usdm_documents (
    id SERIAL PRIMARY KEY,
    study_id VARCHAR(255) NOT NULL UNIQUE,
    study_title TEXT NOT NULL,
    usdm_data JSONB NOT NULL,
    source_document_url TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

COMMENT ON TABLE usdm_documents IS 'USDM 4.0 extracted documents for frontend review UI';

-- ============================================================
-- TABLE: usdm_edit_audit (audit trail for field edits)
-- ============================================================
CREATE TABLE IF NOT EXISTS usdm_edit_audit (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES usdm_documents(id),
    study_id VARCHAR(255) NOT NULL,
    study_title TEXT,
    field_path VARCHAR(500) NOT NULL,
    original_value JSONB,
    new_value JSONB,
    original_usdm JSONB,
    updated_usdm JSONB,
    updated_by VARCHAR(255) NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

COMMENT ON TABLE usdm_edit_audit IS 'Audit trail for USDM field edits with full snapshots';

-- ============================================================
-- TABLE: soa_jobs (SOA extraction jobs)
-- ============================================================
-- SOA extraction job with human-in-the-loop checkpoint support
-- ============================================================
CREATE TABLE IF NOT EXISTS soa_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    protocol_id UUID NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
    protocol_name VARCHAR(255),

    -- Status: detecting_pages, awaiting_page_confirmation, extracting, interpreting, validating, completed, failed
    status VARCHAR(50) NOT NULL DEFAULT 'detecting_pages',

    -- Page detection results (checkpoint data)
    detected_pages JSONB,
    confirmed_pages JSONB,

    -- Progress tracking
    phase_progress JSONB,
    current_phase VARCHAR(50),

    -- Results
    usdm_data JSONB,
    quality_report JSONB,
    extraction_review JSONB,
    interpretation_review JSONB,

    -- Merge Analysis (Phase 3.5) - stores merge plan and group results
    merge_analysis JSONB,

    -- Error handling
    error_message TEXT,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

COMMENT ON TABLE soa_jobs IS 'SOA extraction jobs with human-in-the-loop checkpoint support';
COMMENT ON COLUMN soa_jobs.status IS 'detecting_pages, awaiting_page_confirmation, extracting, interpreting, validating, completed, failed';
COMMENT ON COLUMN soa_jobs.detected_pages IS 'Pages detected by Phase 1 (Gemini Vision)';
COMMENT ON COLUMN soa_jobs.confirmed_pages IS 'Pages confirmed/corrected by user';
COMMENT ON COLUMN soa_jobs.usdm_data IS 'Final merged USDM output (all tables combined)';

CREATE INDEX IF NOT EXISTS idx_soa_jobs_protocol_id ON soa_jobs(protocol_id);
CREATE INDEX IF NOT EXISTS idx_soa_jobs_status ON soa_jobs(status);

-- ============================================================
-- TABLE: soa_edit_audit (audit trail for SOA edits)
-- ============================================================
CREATE TABLE IF NOT EXISTS soa_edit_audit (
    id SERIAL PRIMARY KEY,
    soa_job_id UUID NOT NULL REFERENCES soa_jobs(id) ON DELETE CASCADE,
    protocol_id UUID,
    protocol_name VARCHAR(255),
    field_path VARCHAR(500) NOT NULL,
    original_value JSONB,
    new_value JSONB,
    edit_type VARCHAR(50),
    updated_by VARCHAR(255),
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_soa_edit_audit_job_id ON soa_edit_audit(soa_job_id);

COMMENT ON TABLE soa_edit_audit IS 'Audit trail for SOA field edits';

-- ============================================================
-- TABLE: soa_table_results (per-table SOA USDM storage)
-- ============================================================
-- Stores individual USDM output for each SOA table in a protocol
-- Enables granular quality control and modular review
-- ============================================================
CREATE TABLE IF NOT EXISTS soa_table_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    soa_job_id UUID NOT NULL REFERENCES soa_jobs(id) ON DELETE CASCADE,
    protocol_id UUID NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
    protocol_name VARCHAR(255),

    -- Table identification
    table_id VARCHAR(50) NOT NULL,
    table_category VARCHAR(50) NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,

    -- Extraction status
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    error_message TEXT,

    -- Core USDM data for this table
    usdm_data JSONB,

    -- Quality metrics
    quality_score JSONB,

    -- Counts for quick access
    visits_count INTEGER DEFAULT 0,
    activities_count INTEGER DEFAULT 0,
    sais_count INTEGER DEFAULT 0,
    footnotes_count INTEGER DEFAULT 0,

    -- Interpretation pipeline stages (for debugging)
    interpretation_stages JSONB,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(soa_job_id, table_id)
);

COMMENT ON TABLE soa_table_results IS 'Per-table SOA extraction results - stores individual USDM for each SOA table';
COMMENT ON COLUMN soa_table_results.table_id IS 'Table identifier: SOA-1, SOA-2, etc.';
COMMENT ON COLUMN soa_table_results.table_category IS 'Table type: MAIN_SOA, PK_SOA, SAFETY_SOA, PD_SOA';
COMMENT ON COLUMN soa_table_results.usdm_data IS 'Full USDM JSON for this specific table';
COMMENT ON COLUMN soa_table_results.sais_count IS 'Count of scheduledActivityInstances';

-- ============================================================
-- TABLE: soa_merge_plans (merge plan for human review)
-- ============================================================
-- Stores suggested merge groups from 8-level merge analysis
-- Human reviews and confirms before 12-stage interpretation runs
-- ============================================================
CREATE TABLE IF NOT EXISTS soa_merge_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    soa_job_id UUID NOT NULL REFERENCES soa_jobs(id) ON DELETE CASCADE,
    protocol_id UUID NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
    protocol_name VARCHAR(255),

    -- Status: pending_confirmation, confirmed, modified
    status VARCHAR(50) NOT NULL DEFAULT 'pending_confirmation',

    -- Merge plan JSON
    merge_plan JSONB NOT NULL,

    -- Summary counts
    total_tables_input INTEGER,
    merge_groups_output INTEGER,

    -- Confirmation tracking
    confirmed_at TIMESTAMP,
    confirmed_by VARCHAR(255),
    confirmed_plan JSONB,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE soa_merge_plans IS 'SOA table merge plans for human-in-the-loop confirmation';
COMMENT ON COLUMN soa_merge_plans.merge_plan IS 'Suggested merge groups from 8-level analysis';
COMMENT ON COLUMN soa_merge_plans.confirmed_plan IS 'Final confirmed plan after user review/edits';

CREATE INDEX IF NOT EXISTS idx_soa_merge_plans_job_id ON soa_merge_plans(soa_job_id);
CREATE INDEX IF NOT EXISTS idx_soa_merge_plans_protocol_id ON soa_merge_plans(protocol_id);
CREATE INDEX IF NOT EXISTS idx_soa_merge_plans_status ON soa_merge_plans(status);

-- ============================================================
-- TABLE: soa_merge_group_results (per-group interpretation results)
-- ============================================================
-- Stores interpretation results for each confirmed merge group
-- Each group may contain 1+ tables that were merged together
-- ============================================================
CREATE TABLE IF NOT EXISTS soa_merge_group_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    soa_job_id UUID NOT NULL REFERENCES soa_jobs(id) ON DELETE CASCADE,
    merge_plan_id UUID NOT NULL REFERENCES soa_merge_plans(id) ON DELETE CASCADE,
    protocol_id UUID NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
    protocol_name VARCHAR(255),

    -- Merge group identification
    merge_group_id VARCHAR(50) NOT NULL,
    source_table_ids JSONB NOT NULL,
    merge_type VARCHAR(50),

    -- Status: pending, interpreting, completed, failed
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    error_message TEXT,

    -- Combined USDM before interpretation
    merged_usdm JSONB,

    -- Interpretation result
    interpretation_result JSONB,
    final_usdm JSONB,

    -- Quality metrics
    quality_score JSONB,

    -- Counts for quick access
    visits_count INTEGER DEFAULT 0,
    activities_count INTEGER DEFAULT 0,
    sais_count INTEGER DEFAULT 0,
    footnotes_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

COMMENT ON TABLE soa_merge_group_results IS 'Per-group interpretation results after merge confirmation';
COMMENT ON COLUMN soa_merge_group_results.source_table_ids IS 'Source table IDs: ["SOA-1", "SOA-2"]';
COMMENT ON COLUMN soa_merge_group_results.merged_usdm IS 'Combined USDM from source tables before interpretation';
COMMENT ON COLUMN soa_merge_group_results.final_usdm IS 'Final USDM after 12-stage interpretation';

CREATE INDEX IF NOT EXISTS idx_soa_merge_group_results_job_id ON soa_merge_group_results(soa_job_id);
CREATE INDEX IF NOT EXISTS idx_soa_merge_group_results_plan_id ON soa_merge_group_results(merge_plan_id);
CREATE INDEX IF NOT EXISTS idx_soa_merge_group_results_status ON soa_merge_group_results(status);

-- ============================================================
-- MIGRATIONS: Add missing columns to existing tables
-- ============================================================
-- These ALTER statements safely add columns that may be missing
-- from tables created by earlier versions of this script.
-- Using ADD COLUMN IF NOT EXISTS (PostgreSQL 9.6+)
-- ============================================================

-- soa_jobs: Add merge_analysis column (added for merge plan storage)
ALTER TABLE soa_jobs
ADD COLUMN IF NOT EXISTS merge_analysis JSONB;

-- soa_jobs: Add extraction_review column
ALTER TABLE soa_jobs
ADD COLUMN IF NOT EXISTS extraction_review JSONB;

-- soa_jobs: Add interpretation_review column
ALTER TABLE soa_jobs
ADD COLUMN IF NOT EXISTS interpretation_review JSONB;

-- soa_jobs: Add quality_report column
ALTER TABLE soa_jobs
ADD COLUMN IF NOT EXISTS quality_report JSONB;

-- soa_jobs: Add current_phase column
ALTER TABLE soa_jobs
ADD COLUMN IF NOT EXISTS current_phase VARCHAR(50);

-- soa_jobs: Add phase_progress column
ALTER TABLE soa_jobs
ADD COLUMN IF NOT EXISTS phase_progress JSONB;

-- soa_table_results: Add interpretation_stages column
ALTER TABLE soa_table_results
ADD COLUMN IF NOT EXISTS interpretation_stages JSONB;

-- protocols: Add file_data column (for database storage)
ALTER TABLE protocols
ADD COLUMN IF NOT EXISTS file_data BYTEA;

-- protocols: Add file_size column
ALTER TABLE protocols
ADD COLUMN IF NOT EXISTS file_size BIGINT;

-- protocols: Add content_type column
ALTER TABLE protocols
ADD COLUMN IF NOT EXISTS content_type VARCHAR(100) DEFAULT 'application/pdf';

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_protocols_file_hash ON protocols(file_hash);
CREATE INDEX IF NOT EXISTS idx_protocols_file_size ON protocols(file_size);
CREATE INDEX IF NOT EXISTS idx_protocols_protocol_name ON protocols(protocol_name);
CREATE INDEX IF NOT EXISTS idx_jobs_protocol_id ON jobs(protocol_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_protocol_name ON jobs(protocol_name);
CREATE INDEX IF NOT EXISTS idx_module_results_job_id ON module_results(job_id);
CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_cache_lookup ON extraction_cache(pdf_hash, module_id, model_name);
CREATE INDEX IF NOT EXISTS idx_cache_accessed ON extraction_cache(accessed_at);
CREATE INDEX IF NOT EXISTS idx_usdm_documents_study_id ON usdm_documents(study_id);
CREATE INDEX IF NOT EXISTS idx_usdm_edit_audit_document_id ON usdm_edit_audit(document_id);
CREATE INDEX IF NOT EXISTS idx_soa_table_results_job_id ON soa_table_results(soa_job_id);
CREATE INDEX IF NOT EXISTS idx_soa_table_results_protocol_id ON soa_table_results(protocol_id);
CREATE INDEX IF NOT EXISTS idx_soa_table_results_category ON soa_table_results(table_category);

-- ============================================================
-- VERIFICATION
-- ============================================================
-- List all tables in public schema
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
"""

# SQL to verify columns exist (for reporting)
VERIFY_COLUMNS_SQL = """
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
AND table_name = 'soa_jobs'
ORDER BY ordinal_position;
"""


def init_schema():
    """Initialize the public schema in NeonDB."""
    print(f"Connecting to database...")
    print(f"Using DATABASE_URL from: {env_path}")

    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cursor = conn.cursor()

        print("\nCreating tables in public schema...")

        # Execute schema SQL
        cursor.execute(SCHEMA_SQL)

        # Fetch results from the verification query
        tables = cursor.fetchall()

        print("\n" + "=" * 60)
        print("SUCCESS: public schema tables created!")
        print("=" * 60)
        print(f"\nTables created in public schema:")
        for table in tables:
            print(f"  - {table[0]}")

        # Verify row counts
        print("\nTable verification:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"  - {table[0]}: {count} rows")

        # Show soa_jobs columns (to verify migrations ran)
        print("\nsoa_jobs columns (after migrations):")
        cursor.execute(VERIFY_COLUMNS_SQL)
        columns = cursor.fetchall()
        for col_name, col_type in columns:
            print(f"  - {col_name}: {col_type}")

        cursor.close()
        conn.close()

        print("\n" + "=" * 60)
        print("Database schema initialization complete!")
        print("=" * 60)
        print("\nNote: Existing tables were preserved.")
        print("Missing columns were added via ALTER TABLE IF NOT EXISTS.")

    except Exception as e:
        print(f"\nERROR: Failed to initialize schema: {e}")
        sys.exit(1)


if __name__ == "__main__":
    init_schema()
