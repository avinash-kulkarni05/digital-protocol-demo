"""
Migration script to add missing columns to eligibility_jobs table.

This script adds the following columns that exist in the SQLAlchemy model
but are missing from the database table:
- interpretation_result (JSONB)
- raw_criteria (JSONB)
- feasibility_result (JSONB)
- qeb_result (JSONB) - Stage 12 QEB builder output
- quality_report (JSONB)
- inclusion_count (INTEGER)
- exclusion_count (INTEGER)
- atomic_count (INTEGER)
- started_at (TIMESTAMP)
- completed_at (TIMESTAMP)
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db import get_engine, SCHEMA_NAME


def run_migration():
    """Add missing columns to eligibility_jobs table."""
    engine = get_engine()

    # SQL to add missing columns (IF NOT EXISTS prevents errors if column already exists)
    migration_sql = f"""
    -- Add missing columns to eligibility_jobs table
    ALTER TABLE {SCHEMA_NAME}.eligibility_jobs
        ADD COLUMN IF NOT EXISTS interpretation_result JSONB,
        ADD COLUMN IF NOT EXISTS raw_criteria JSONB,
        ADD COLUMN IF NOT EXISTS feasibility_result JSONB,
        ADD COLUMN IF NOT EXISTS qeb_result JSONB,
        ADD COLUMN IF NOT EXISTS quality_report JSONB,
        ADD COLUMN IF NOT EXISTS inclusion_count INTEGER,
        ADD COLUMN IF NOT EXISTS exclusion_count INTEGER,
        ADD COLUMN IF NOT EXISTS atomic_count INTEGER,
        ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
        ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;
    """

    print(f"Running migration on schema: {SCHEMA_NAME}")
    print("Adding columns to eligibility_jobs table...")

    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()

    print("Migration completed successfully!")
    print("\nColumns added:")
    print("  - interpretation_result (JSONB)")
    print("  - raw_criteria (JSONB)")
    print("  - feasibility_result (JSONB)")
    print("  - qeb_result (JSONB)")
    print("  - quality_report (JSONB)")
    print("  - inclusion_count (INTEGER)")
    print("  - exclusion_count (INTEGER)")
    print("  - atomic_count (INTEGER)")
    print("  - started_at (TIMESTAMP)")
    print("  - completed_at (TIMESTAMP)")


if __name__ == "__main__":
    run_migration()
