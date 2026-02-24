#!/usr/bin/env python3
"""
Initialize the backend_vnext PostgreSQL schema in NeonDB.

This script creates all tables in an isolated 'backend_vnext' schema,
ensuring no interference with existing data in the 'public' schema.

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

# SQL to create the backend_vnext schema and all tables
SCHEMA_SQL = """
-- ============================================================
-- BACKEND_VNEXT SCHEMA INITIALIZATION
-- ============================================================
-- This creates an isolated schema for backend_vNext
-- All tables are prefixed with backend_vnext. to avoid conflicts
-- ============================================================

-- Create the schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS backend_vnext;

-- Set search path for this session
SET search_path TO backend_vnext;

-- ============================================================
-- TABLE: protocols
-- ============================================================
-- Stores uploaded protocol PDFs with Gemini File API cache
-- Now supports binary storage in database (file_data BYTEA column)
-- ============================================================
CREATE TABLE IF NOT EXISTS backend_vnext.protocols (
    id VARCHAR(64) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    filename VARCHAR(255) NOT NULL,
    protocol_name VARCHAR(255),
    file_hash VARCHAR(64) NOT NULL UNIQUE,
    file_data BYTEA,
    file_size BIGINT,
    content_type VARCHAR(100) DEFAULT 'application/pdf',
    gemini_file_uri VARCHAR(500),
    gemini_file_expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE backend_vnext.protocols IS 'Uploaded protocol PDFs with Gemini File API cache. PDFs stored as BYTEA in file_data.';
COMMENT ON COLUMN backend_vnext.protocols.file_data IS 'Binary PDF data stored in database (BYTEA)';
COMMENT ON COLUMN backend_vnext.protocols.file_size IS 'Size of PDF file in bytes';
COMMENT ON COLUMN backend_vnext.protocols.content_type IS 'MIME type of uploaded file';
COMMENT ON COLUMN backend_vnext.protocols.gemini_file_uri IS 'Cached Gemini File API URI (48-hour expiry)';

-- ============================================================
-- TABLE: jobs
-- ============================================================
-- Extraction jobs - one job runs all 10 modules sequentially
-- ============================================================
CREATE TABLE IF NOT EXISTS backend_vnext.jobs (
    id VARCHAR(64) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    protocol_id VARCHAR(64) NOT NULL REFERENCES backend_vnext.protocols(id),
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

COMMENT ON TABLE backend_vnext.jobs IS 'Extraction jobs - one job = all 10 modules for a protocol';
COMMENT ON COLUMN backend_vnext.jobs.status IS 'pending, running, completed, failed';
COMMENT ON COLUMN backend_vnext.jobs.completed_modules IS 'Array of completed module IDs';

-- ============================================================
-- TABLE: module_results
-- ============================================================
-- Per-module extraction results with provenance tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS backend_vnext.module_results (
    id VARCHAR(64) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    job_id VARCHAR(64) NOT NULL REFERENCES backend_vnext.jobs(id),
    protocol_name VARCHAR(255),
    module_id VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    extracted_data JSONB,
    provenance_coverage FLOAT,
    pass1_duration_seconds FLOAT,
    pass2_duration_seconds FLOAT,
    retry_count INTEGER DEFAULT 0,
    error_details JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(job_id, module_id)
);

COMMENT ON TABLE backend_vnext.module_results IS 'Per-module extraction results with provenance tracking';
COMMENT ON COLUMN backend_vnext.module_results.provenance_coverage IS '0.0 to 1.0 - target is 1.0 (100%)';
COMMENT ON COLUMN backend_vnext.module_results.extracted_data IS 'Pass 1 + Pass 2 merged result';

-- ============================================================
-- TABLE: job_events
-- ============================================================
-- Job events for SSE streaming
-- ============================================================
CREATE TABLE IF NOT EXISTS backend_vnext.job_events (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL REFERENCES backend_vnext.jobs(id),
    protocol_name VARCHAR(255),
    event_type VARCHAR(50) NOT NULL,
    module_id VARCHAR(100),
    payload JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE backend_vnext.job_events IS 'Job events for SSE streaming';
COMMENT ON COLUMN backend_vnext.job_events.event_type IS 'module_started, module_completed, job_failed, etc.';

-- ============================================================
-- EXTRACTION OUTPUTS TABLE
-- ============================================================
-- Stores all extraction output files (PDFs and JSONs) in database
CREATE TABLE IF NOT EXISTS backend_vnext.extraction_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES backend_vnext.jobs(id) ON DELETE CASCADE,
    protocol_id UUID NOT NULL REFERENCES backend_vnext.protocols(id) ON DELETE CASCADE,
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

CREATE INDEX IF NOT EXISTS idx_extraction_outputs_job_id ON backend_vnext.extraction_outputs(job_id);
CREATE INDEX IF NOT EXISTS idx_extraction_outputs_protocol_id ON backend_vnext.extraction_outputs(protocol_id);
CREATE INDEX IF NOT EXISTS idx_extraction_outputs_job_type ON backend_vnext.extraction_outputs(job_id, file_type);

COMMENT ON TABLE backend_vnext.extraction_outputs IS 'Database storage for all extraction output files (annotated PDF, quality report, etc.)';
COMMENT ON COLUMN backend_vnext.extraction_outputs.file_type IS 'Type: usdm_json, extraction_results, quality_report, annotated_pdf, annotation_report';
COMMENT ON COLUMN backend_vnext.extraction_outputs.file_data IS 'Binary data for PDF files';
COMMENT ON COLUMN backend_vnext.extraction_outputs.json_data IS 'JSONB data for JSON files (queryable)';

-- ============================================================
-- TABLE: usdm_documents (for frontend review UI)
-- ============================================================
CREATE TABLE IF NOT EXISTS backend_vnext.usdm_documents (
    id SERIAL PRIMARY KEY,
    study_id VARCHAR(255) NOT NULL UNIQUE,
    study_title TEXT NOT NULL,
    usdm_data JSONB NOT NULL,
    source_document_url TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

COMMENT ON TABLE backend_vnext.usdm_documents IS 'USDM 4.0 extracted documents for frontend review UI';

-- ============================================================
-- TABLE: usdm_edit_audit (audit trail for field edits)
-- ============================================================
CREATE TABLE IF NOT EXISTS backend_vnext.usdm_edit_audit (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES backend_vnext.usdm_documents(id),
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

COMMENT ON TABLE backend_vnext.usdm_edit_audit IS 'Audit trail for USDM field edits with full snapshots';

-- ============================================================
-- TABLE: soa_jobs (SOA extraction jobs)
-- ============================================================
-- SOA extraction job with human-in-the-loop checkpoint support
-- ============================================================
CREATE TABLE IF NOT EXISTS backend_vnext.soa_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    protocol_id UUID NOT NULL REFERENCES backend_vnext.protocols(id) ON DELETE CASCADE,
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

COMMENT ON TABLE backend_vnext.soa_jobs IS 'SOA extraction jobs with human-in-the-loop checkpoint support';
COMMENT ON COLUMN backend_vnext.soa_jobs.status IS 'detecting_pages, awaiting_page_confirmation, extracting, interpreting, validating, completed, failed';
COMMENT ON COLUMN backend_vnext.soa_jobs.detected_pages IS 'Pages detected by Phase 1 (Gemini Vision)';
COMMENT ON COLUMN backend_vnext.soa_jobs.confirmed_pages IS 'Pages confirmed/corrected by user';
COMMENT ON COLUMN backend_vnext.soa_jobs.usdm_data IS 'Final merged USDM output (all tables combined)';

CREATE INDEX IF NOT EXISTS idx_soa_jobs_protocol_id ON backend_vnext.soa_jobs(protocol_id);
CREATE INDEX IF NOT EXISTS idx_soa_jobs_status ON backend_vnext.soa_jobs(status);

-- ============================================================
-- TABLE: soa_edit_audit (audit trail for SOA edits)
-- ============================================================
CREATE TABLE IF NOT EXISTS backend_vnext.soa_edit_audit (
    id SERIAL PRIMARY KEY,
    soa_job_id UUID NOT NULL REFERENCES backend_vnext.soa_jobs(id) ON DELETE CASCADE,
    protocol_id UUID,
    protocol_name VARCHAR(255),
    field_path VARCHAR(500) NOT NULL,
    original_value JSONB,
    new_value JSONB,
    edit_type VARCHAR(50),
    updated_by VARCHAR(255),
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_soa_edit_audit_job_id ON backend_vnext.soa_edit_audit(soa_job_id);

COMMENT ON TABLE backend_vnext.soa_edit_audit IS 'Audit trail for SOA field edits';

-- ============================================================
-- TABLE: soa_table_results (per-table SOA USDM storage)
-- ============================================================
-- Stores individual USDM output for each SOA table in a protocol
-- Enables granular quality control and modular review
-- ============================================================
CREATE TABLE IF NOT EXISTS backend_vnext.soa_table_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    soa_job_id UUID NOT NULL REFERENCES backend_vnext.soa_jobs(id) ON DELETE CASCADE,
    protocol_id UUID NOT NULL REFERENCES backend_vnext.protocols(id) ON DELETE CASCADE,
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
    raw_usdm_data JSONB,

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

COMMENT ON TABLE backend_vnext.soa_table_results IS 'Per-table SOA extraction results - stores individual USDM for each SOA table';
COMMENT ON COLUMN backend_vnext.soa_table_results.table_id IS 'Table identifier: SOA-1, SOA-2, etc.';
COMMENT ON COLUMN backend_vnext.soa_table_results.table_category IS 'Table type: MAIN_SOA, PK_SOA, SAFETY_SOA, PD_SOA';
COMMENT ON COLUMN backend_vnext.soa_table_results.usdm_data IS 'Full USDM JSON for this specific table';
COMMENT ON COLUMN backend_vnext.soa_table_results.sais_count IS 'Count of scheduledActivityInstances';

-- ============================================================
-- TABLE: full_extraction_jobs (tracks all 3 pipelines as one job)
-- ============================================================
CREATE TABLE IF NOT EXISTS backend_vnext.full_extraction_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    protocol_id UUID NOT NULL REFERENCES backend_vnext.protocols(id) ON DELETE CASCADE,
    protocol_name VARCHAR(255),

    -- Overall status: pending, running, completed, completed_with_errors, failed
    status VARCHAR(50) NOT NULL DEFAULT 'pending',

    -- Sub-pipeline job IDs
    main_job_id UUID,
    soa_job_id UUID,
    eligibility_job_id UUID,

    -- Sub-pipeline statuses
    main_status VARCHAR(50) DEFAULT 'pending',
    soa_status VARCHAR(50) DEFAULT 'pending',
    eligibility_status VARCHAR(50) DEFAULT 'pending',

    -- Sub-pipeline progress (0-100)
    main_progress INTEGER DEFAULT 0,
    soa_progress INTEGER DEFAULT 0,
    eligibility_progress INTEGER DEFAULT 0,

    -- Combined progress
    overall_progress INTEGER DEFAULT 0,

    -- Error handling
    error_message TEXT,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_full_extraction_jobs_protocol_id ON backend_vnext.full_extraction_jobs(protocol_id);
CREATE INDEX IF NOT EXISTS idx_full_extraction_jobs_status ON backend_vnext.full_extraction_jobs(status);

COMMENT ON TABLE backend_vnext.full_extraction_jobs IS 'Full extraction jobs tracking all 3 pipelines (main + SOA + eligibility) as one job';

-- ============================================================
-- CLEANUP: Drop dead tables and columns
-- ============================================================
-- These tables/columns are no longer used by the application.
-- Data is stored in soa_jobs.merge_analysis JSONB instead of
-- separate merge plan tables.
-- ============================================================
DROP TABLE IF EXISTS backend_vnext.soa_merge_group_results CASCADE;
DROP TABLE IF EXISTS backend_vnext.soa_merge_plans CASCADE;
DROP TABLE IF EXISTS backend_vnext.extraction_cache CASCADE;

-- Drop dead columns from existing tables
ALTER TABLE backend_vnext.protocols DROP COLUMN IF EXISTS file_path;
ALTER TABLE backend_vnext.jobs DROP COLUMN IF EXISTS output_directory;
ALTER TABLE backend_vnext.jobs DROP COLUMN IF EXISTS output_files;
ALTER TABLE backend_vnext.module_results DROP COLUMN IF EXISTS compliance_score;
ALTER TABLE backend_vnext.module_results DROP COLUMN IF EXISTS from_cache;
ALTER TABLE backend_vnext.soa_table_results DROP COLUMN IF EXISTS quality_score;

-- ============================================================
-- MIGRATIONS: Add missing columns to existing tables
-- ============================================================
-- These ALTER statements safely add columns that may be missing
-- from tables created by earlier versions of this script.
-- Using ADD COLUMN IF NOT EXISTS (PostgreSQL 9.6+)
-- ============================================================

-- soa_jobs: Add merge_analysis column (added for merge plan storage)
ALTER TABLE backend_vnext.soa_jobs
ADD COLUMN IF NOT EXISTS merge_analysis JSONB;

-- soa_jobs: Add extraction_review column
ALTER TABLE backend_vnext.soa_jobs
ADD COLUMN IF NOT EXISTS extraction_review JSONB;

-- soa_jobs: Add interpretation_review column
ALTER TABLE backend_vnext.soa_jobs
ADD COLUMN IF NOT EXISTS interpretation_review JSONB;

-- soa_jobs: Add quality_report column
ALTER TABLE backend_vnext.soa_jobs
ADD COLUMN IF NOT EXISTS quality_report JSONB;

-- soa_jobs: Add current_phase column
ALTER TABLE backend_vnext.soa_jobs
ADD COLUMN IF NOT EXISTS current_phase VARCHAR(50);

-- soa_jobs: Add phase_progress column
ALTER TABLE backend_vnext.soa_jobs
ADD COLUMN IF NOT EXISTS phase_progress JSONB;

-- soa_jobs: Add classification_review column (Phase 3.6 - classifier results for human review)
ALTER TABLE backend_vnext.soa_jobs
ADD COLUMN IF NOT EXISTS classification_review JSONB;

-- soa_table_results: Add interpretation_stages column
ALTER TABLE backend_vnext.soa_table_results
ADD COLUMN IF NOT EXISTS interpretation_stages JSONB;

-- soa_table_results: Add raw_usdm_data column (pre-interpretation snapshot)
ALTER TABLE backend_vnext.soa_table_results
ADD COLUMN IF NOT EXISTS raw_usdm_data JSONB;

-- protocols: Add file_data column (for database storage)
ALTER TABLE backend_vnext.protocols
ADD COLUMN IF NOT EXISTS file_data BYTEA;

-- protocols: Add file_size column
ALTER TABLE backend_vnext.protocols
ADD COLUMN IF NOT EXISTS file_size BIGINT;

-- protocols: Add content_type column
ALTER TABLE backend_vnext.protocols
ADD COLUMN IF NOT EXISTS content_type VARCHAR(100) DEFAULT 'application/pdf';

-- protocols: Add extraction_status column (pending, processing, completed, failed)
ALTER TABLE backend_vnext.protocols
ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(50);

-- protocols: Add usdm_json column (extracted USDM 4.0 data for display)
ALTER TABLE backend_vnext.protocols
ADD COLUMN IF NOT EXISTS usdm_json JSONB;

-- protocols: Add sponsor column (user-entered at upload time)
ALTER TABLE backend_vnext.protocols
ADD COLUMN IF NOT EXISTS sponsor VARCHAR(500);

-- protocols: Add nct_number column (user-entered at upload time)
ALTER TABLE backend_vnext.protocols
ADD COLUMN IF NOT EXISTS nct_number VARCHAR(50);

-- protocols: Add user_email column (user-entered at upload time)
ALTER TABLE backend_vnext.protocols
ADD COLUMN IF NOT EXISTS user_email VARCHAR(255);

-- module_results: Add quality_scores JSONB column (5D quality scoring)
ALTER TABLE backend_vnext.module_results
ADD COLUMN IF NOT EXISTS quality_scores JSONB;

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_protocols_file_hash ON backend_vnext.protocols(file_hash);
CREATE INDEX IF NOT EXISTS idx_protocols_file_size ON backend_vnext.protocols(file_size);
CREATE INDEX IF NOT EXISTS idx_protocols_protocol_name ON backend_vnext.protocols(protocol_name);
CREATE INDEX IF NOT EXISTS idx_jobs_protocol_id ON backend_vnext.jobs(protocol_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON backend_vnext.jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_protocol_name ON backend_vnext.jobs(protocol_name);
CREATE INDEX IF NOT EXISTS idx_module_results_job_id ON backend_vnext.module_results(job_id);
CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON backend_vnext.job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_usdm_documents_study_id ON backend_vnext.usdm_documents(study_id);
CREATE INDEX IF NOT EXISTS idx_usdm_edit_audit_document_id ON backend_vnext.usdm_edit_audit(document_id);
CREATE INDEX IF NOT EXISTS idx_soa_table_results_job_id ON backend_vnext.soa_table_results(soa_job_id);
CREATE INDEX IF NOT EXISTS idx_soa_table_results_protocol_id ON backend_vnext.soa_table_results(protocol_id);
CREATE INDEX IF NOT EXISTS idx_soa_table_results_category ON backend_vnext.soa_table_results(table_category);

-- ============================================================
-- VERIFICATION
-- ============================================================
-- List all tables in backend_vnext schema
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'backend_vnext'
ORDER BY table_name;
"""

# SQL to verify columns exist (for reporting)
VERIFY_COLUMNS_SQL = """
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'backend_vnext'
AND table_name = 'soa_jobs'
ORDER BY ordinal_position;
"""


def init_schema():
    """Initialize the backend_vnext schema in NeonDB."""
    print(f"Connecting to database...")
    print(f"Using DATABASE_URL from: {env_path}")

    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cursor = conn.cursor()

        print("\nCreating backend_vnext schema and tables...")

        # Execute schema SQL
        cursor.execute(SCHEMA_SQL)

        # Fetch results from the verification query
        tables = cursor.fetchall()

        print("\n" + "=" * 60)
        print("SUCCESS: backend_vnext schema created!")
        print("=" * 60)
        print(f"\nTables created in backend_vnext schema:")
        for table in tables:
            print(f"  - backend_vnext.{table[0]}")

        # Verify row counts
        print("\nTable verification:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM backend_vnext.{table[0]}")
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
