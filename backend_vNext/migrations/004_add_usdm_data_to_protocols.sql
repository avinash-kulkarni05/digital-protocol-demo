-- Migration: Add USDM data and extraction status to protocols table
-- Date: 2025-12-19
-- Purpose: Store extracted USDM JSON in protocol record for rich frontend display

-- Add USDM JSON column to protocols table
ALTER TABLE backend_vnext.protocols
ADD COLUMN IF NOT EXISTS usdm_json JSONB,
ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(50);

-- Create index on extraction_status for filtering
CREATE INDEX IF NOT EXISTS idx_protocols_extraction_status
ON backend_vnext.protocols(extraction_status);

COMMENT ON COLUMN backend_vnext.protocols.usdm_json IS 'Extracted USDM 4.0 JSON data for frontend display (study metadata, phase, sponsor, etc.)';
COMMENT ON COLUMN backend_vnext.protocols.extraction_status IS 'Extraction status: pending, processing, completed, failed';
