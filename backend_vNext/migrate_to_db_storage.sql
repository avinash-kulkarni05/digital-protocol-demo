-- Migration script: Add binary storage columns to protocols table
-- This migration adds support for storing PDF files directly in the database
-- while maintaining backward compatibility with filesystem storage

-- Add new columns for binary storage
ALTER TABLE backend_vnext.protocols
  ADD COLUMN IF NOT EXISTS file_data BYTEA,
  ADD COLUMN IF NOT EXISTS file_size BIGINT,
  ADD COLUMN IF NOT EXISTS content_type VARCHAR(100) DEFAULT 'application/pdf',
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- Create index for efficient queries on file size
CREATE INDEX IF NOT EXISTS idx_protocols_file_size ON backend_vnext.protocols(file_size);

-- Create index for file hash (should already exist, but ensure it)
CREATE INDEX IF NOT EXISTS idx_protocols_file_hash ON backend_vnext.protocols(file_hash);

-- Add a comment to the table explaining the migration strategy
COMMENT ON TABLE backend_vnext.protocols IS 'Protocol PDFs. Both file_path (legacy) and file_data (new) are nullable during migration. After migration complete, file_path can be dropped.';

-- Add comments to new columns
COMMENT ON COLUMN backend_vnext.protocols.file_data IS 'Binary PDF data stored in database (BYTEA). NULL for legacy records until migration.';
COMMENT ON COLUMN backend_vnext.protocols.file_size IS 'Size of PDF file in bytes';
COMMENT ON COLUMN backend_vnext.protocols.content_type IS 'MIME type of uploaded file';
COMMENT ON COLUMN backend_vnext.protocols.updated_at IS 'Last modification timestamp';

-- Verify the changes
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'backend_vnext'
  AND table_name = 'protocols'
ORDER BY ordinal_position;
