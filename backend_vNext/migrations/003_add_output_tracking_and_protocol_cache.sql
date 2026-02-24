-- Migration: Add output tracking to Job table and protocol_id to extraction_cache
-- Date: 2025-12-19
-- Purpose: Track extraction output files and make cache identifiable by protocol

-- Add output tracking columns to jobs table
ALTER TABLE backend_vnext.jobs
ADD COLUMN IF NOT EXISTS output_directory VARCHAR(1000),
ADD COLUMN IF NOT EXISTS output_files JSONB;

-- Add protocol_id to extraction_cache table
ALTER TABLE backend_vnext.extraction_cache
ADD COLUMN IF NOT EXISTS protocol_id UUID REFERENCES backend_vnext.protocols(id);

-- Create index on protocol_id for efficient lookups
CREATE INDEX IF NOT EXISTS idx_cache_protocol_id ON backend_vnext.extraction_cache(protocol_id);

-- Update existing cache entries to link to protocols based on pdf_hash
-- (This is best-effort - if multiple protocols have the same hash, will link to first one)
UPDATE backend_vnext.extraction_cache ec
SET protocol_id = p.id
FROM backend_vnext.protocols p
WHERE ec.protocol_id IS NULL
  AND ec.pdf_hash = p.file_hash
  AND p.id = (
    SELECT id FROM backend_vnext.protocols
    WHERE file_hash = ec.pdf_hash
    LIMIT 1
  );

COMMENT ON COLUMN backend_vnext.jobs.output_directory IS 'Path to extraction output directory (e.g., protocols/{protocol_name}/extraction_output/{timestamp}/)';
COMMENT ON COLUMN backend_vnext.jobs.output_files IS 'JSONB array of output files with metadata: [{file_type, file_path, file_size, created_at}]';
COMMENT ON COLUMN backend_vnext.extraction_cache.protocol_id IS 'Foreign key to protocols table for easy identification of which protocol this cache entry belongs to';
