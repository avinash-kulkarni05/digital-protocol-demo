-- Migration 005: Add quality_scores and from_cache to module_results
--
-- This migration adds columns to store full 5D quality scores (accuracy, completeness,
-- usdm_adherence, provenance, terminology) to ensure API extraction produces the same
-- output as CLI extraction (main.py).
--
-- Run with: psql -f migrations/005_add_quality_scores_to_module_results.sql

-- Add quality_scores JSONB column for full 5D quality scores
ALTER TABLE backend_vnext.module_results
ADD COLUMN IF NOT EXISTS quality_scores JSONB;

-- Add from_cache boolean column to track cache hits
ALTER TABLE backend_vnext.module_results
ADD COLUMN IF NOT EXISTS from_cache BOOLEAN DEFAULT FALSE;

-- Add comment explaining the quality_scores structure
COMMENT ON COLUMN backend_vnext.module_results.quality_scores IS
'Full 5D quality scores: {accuracy, completeness, usdm_adherence, provenance, terminology, overall, from_cache, duration_seconds}';

COMMENT ON COLUMN backend_vnext.module_results.from_cache IS
'Whether the extraction result was retrieved from cache';

-- Verify the changes
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_schema = 'backend_vnext'
AND table_name = 'module_results'
ORDER BY ordinal_position;
