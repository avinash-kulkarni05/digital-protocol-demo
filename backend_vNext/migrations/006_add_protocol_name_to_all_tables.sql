-- Migration: Add protocol_name column to all tables
-- Purpose: Human-readable protocol identifier for easy identification without tracing UUIDs
-- Date: 2026-01-06

-- Add protocol_name column to all tables
ALTER TABLE backend_vnext.protocols ADD COLUMN IF NOT EXISTS protocol_name VARCHAR(255);
ALTER TABLE backend_vnext.jobs ADD COLUMN IF NOT EXISTS protocol_name VARCHAR(255);
ALTER TABLE backend_vnext.module_results ADD COLUMN IF NOT EXISTS protocol_name VARCHAR(255);
ALTER TABLE backend_vnext.job_events ADD COLUMN IF NOT EXISTS protocol_name VARCHAR(255);
ALTER TABLE backend_vnext.extraction_cache ADD COLUMN IF NOT EXISTS protocol_name VARCHAR(255);
ALTER TABLE backend_vnext.extraction_outputs ADD COLUMN IF NOT EXISTS protocol_name VARCHAR(255);
ALTER TABLE backend_vnext.soa_jobs ADD COLUMN IF NOT EXISTS protocol_name VARCHAR(255);

-- Add indexes for faster lookups by protocol_name
CREATE INDEX IF NOT EXISTS idx_protocols_protocol_name ON backend_vnext.protocols(protocol_name);
CREATE INDEX IF NOT EXISTS idx_jobs_protocol_name ON backend_vnext.jobs(protocol_name);
CREATE INDEX IF NOT EXISTS idx_soa_jobs_protocol_name ON backend_vnext.soa_jobs(protocol_name);

-- Backfill existing data: derive protocol_name from filename (remove extension)
UPDATE backend_vnext.protocols
SET protocol_name = REGEXP_REPLACE(filename, '\.[^.]+$', '')
WHERE protocol_name IS NULL;

-- Backfill jobs from protocols
UPDATE backend_vnext.jobs j
SET protocol_name = p.protocol_name
FROM backend_vnext.protocols p
WHERE j.protocol_id = p.id AND j.protocol_name IS NULL;

-- Backfill module_results from jobs
UPDATE backend_vnext.module_results mr
SET protocol_name = j.protocol_name
FROM backend_vnext.jobs j
WHERE mr.job_id = j.id AND mr.protocol_name IS NULL;

-- Backfill job_events from jobs
UPDATE backend_vnext.job_events je
SET protocol_name = j.protocol_name
FROM backend_vnext.jobs j
WHERE je.job_id = j.id AND je.protocol_name IS NULL;

-- Backfill extraction_cache from protocols
UPDATE backend_vnext.extraction_cache ec
SET protocol_name = p.protocol_name
FROM backend_vnext.protocols p
WHERE ec.protocol_id = p.id AND ec.protocol_name IS NULL;

-- Backfill extraction_outputs from protocols
UPDATE backend_vnext.extraction_outputs eo
SET protocol_name = p.protocol_name
FROM backend_vnext.protocols p
WHERE eo.protocol_id = p.id AND eo.protocol_name IS NULL;

-- Backfill soa_jobs from protocols
UPDATE backend_vnext.soa_jobs sj
SET protocol_name = p.protocol_name
FROM backend_vnext.protocols p
WHERE sj.protocol_id = p.id AND sj.protocol_name IS NULL;
