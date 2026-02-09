#!/usr/bin/env python3
"""
Migrate existing PDF files from filesystem to database storage.

This script migrates protocols that have file_path but no file_data,
reading the PDF from disk and storing it in the database file_data column.

Usage:
    cd backend_vNext
    source venv/bin/activate
    python scripts/migrate_files_to_db.py

    # Dry run (don't modify database)
    python scripts/migrate_files_to_db.py --dry-run

    # Migrate specific protocol by ID
    python scripts/migrate_files_to_db.py --protocol-id <uuid>
"""

import argparse
import hashlib
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.db import get_session_factory, Protocol
from app.config import settings

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def migrate_protocol(protocol: Protocol, db: Session, dry_run: bool = False) -> bool:
    """
    Migrate a single protocol from filesystem to database.

    Args:
        protocol: Protocol record to migrate
        db: Database session
        dry_run: If True, don't modify database

    Returns:
        True if migration successful, False otherwise
    """
    try:
        # Check if protocol already has file_data
        if protocol.file_data is not None:
            logger.info(f"✓ Protocol {protocol.id} already has file_data (skipping)")
            return True

        # Check if file_path exists
        if not protocol.file_path:
            logger.warning(f"✗ Protocol {protocol.id} has no file_path (skipping)")
            return False

        file_path = Path(protocol.file_path)
        if not file_path.exists():
            logger.warning(f"✗ File not found: {file_path} (skipping)")
            return False

        # Read PDF data
        logger.info(f"→ Reading file: {file_path}")
        with open(file_path, 'rb') as f:
            file_data = f.read()

        file_size = len(file_data)
        file_hash = compute_file_hash(file_path)

        # Verify hash matches
        if protocol.file_hash != file_hash:
            logger.warning(
                f"⚠ Hash mismatch for protocol {protocol.id}:\n"
                f"  Database: {protocol.file_hash}\n"
                f"  File:     {file_hash}\n"
                f"  This might indicate file corruption. Proceeding anyway..."
            )

        if dry_run:
            logger.info(
                f"[DRY RUN] Would migrate protocol {protocol.id}:\n"
                f"  Filename: {protocol.filename}\n"
                f"  Size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)\n"
                f"  Hash: {file_hash}"
            )
            return True

        # Update protocol with binary data
        protocol.file_data = file_data
        protocol.file_size = file_size
        protocol.content_type = "application/pdf"
        protocol.updated_at = datetime.utcnow()

        db.commit()

        logger.info(
            f"✓ Migrated protocol {protocol.id}:\n"
            f"  Filename: {protocol.filename}\n"
            f"  Size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)"
        )

        return True

    except Exception as e:
        logger.error(f"✗ Error migrating protocol {protocol.id}: {e}")
        db.rollback()
        return False


def migrate_all_protocols(db: Session, dry_run: bool = False) -> dict:
    """
    Migrate all protocols from filesystem to database.

    Args:
        db: Database session
        dry_run: If True, don't modify database

    Returns:
        Dict with migration statistics
    """
    # Find protocols that need migration
    protocols_to_migrate = (
        db.query(Protocol)
        .filter(Protocol.file_data.is_(None))
        .filter(Protocol.file_path.isnot(None))
        .all()
    )

    if not protocols_to_migrate:
        logger.info("No protocols need migration")
        return {
            "total": 0,
            "migrated": 0,
            "skipped": 0,
            "errors": 0
        }

    logger.info(f"\nFound {len(protocols_to_migrate)} protocols to migrate")
    logger.info("=" * 60)

    stats = {
        "total": len(protocols_to_migrate),
        "migrated": 0,
        "skipped": 0,
        "errors": 0
    }

    total_size = 0

    for i, protocol in enumerate(protocols_to_migrate, 1):
        logger.info(f"\n[{i}/{stats['total']}] Processing protocol {protocol.id}")

        success = migrate_protocol(protocol, db, dry_run)

        if success:
            if protocol.file_data or dry_run:
                stats["migrated"] += 1
                if protocol.file_size:
                    total_size += protocol.file_size
            else:
                stats["skipped"] += 1
        else:
            stats["errors"] += 1

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total protocols: {stats['total']}")
    logger.info(f"Migrated: {stats['migrated']}")
    logger.info(f"Skipped: {stats['skipped']}")
    logger.info(f"Errors: {stats['errors']}")

    if total_size > 0:
        logger.info(f"Total data migrated: {total_size:,} bytes ({total_size / (1024*1024):.2f} MB)")

    if dry_run:
        logger.info("\n⚠ DRY RUN MODE - No changes were made to the database")

    return stats


def migrate_single_protocol(protocol_id: str, db: Session, dry_run: bool = False):
    """
    Migrate a single protocol by ID.

    Args:
        protocol_id: UUID of protocol to migrate
        db: Database session
        dry_run: If True, don't modify database
    """
    from uuid import UUID

    try:
        protocol_uuid = UUID(protocol_id)
    except ValueError:
        logger.error(f"Invalid protocol ID: {protocol_id}")
        return

    protocol = db.query(Protocol).filter(Protocol.id == protocol_uuid).first()

    if not protocol:
        logger.error(f"Protocol not found: {protocol_id}")
        return

    logger.info(f"Migrating protocol {protocol_id}")
    success = migrate_protocol(protocol, db, dry_run)

    if success:
        logger.info("✓ Migration successful")
    else:
        logger.error("✗ Migration failed")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate PDF files from filesystem to database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying database"
    )
    parser.add_argument(
        "--protocol-id",
        type=str,
        help="Migrate a specific protocol by UUID"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("PDF MIGRATION: Filesystem → Database")
    logger.info("=" * 60)
    logger.info(f"Database: {settings.effective_database_url.split('@')[1] if '@' in settings.effective_database_url else 'configured'}")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    logger.info("=" * 60)

    # Create database session
    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        if args.protocol_id:
            migrate_single_protocol(args.protocol_id, db, args.dry_run)
        else:
            migrate_all_protocols(db, args.dry_run)

    except KeyboardInterrupt:
        logger.info("\n\nMigration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n\nFatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()

    logger.info("\nDone!")


if __name__ == "__main__":
    main()
