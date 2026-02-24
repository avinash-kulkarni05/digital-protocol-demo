"""
Shared helpers for protocol PDF access and lookup.

Used by SOA and Eligibility routers to avoid code duplication.
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.db import Protocol

logger = logging.getLogger(__name__)


def get_pdf_path_for_protocol(
    protocol: Protocol,
    db: Session,
    subdirectory: str = "protocol_pdfs",
) -> str:
    """
    Get or create a temporary file path for the protocol PDF.

    Writes the protocol's file_data (stored in DB) to a temp file
    and returns the path. Reuses existing temp files if present.

    Args:
        protocol: Protocol ORM object with file_data
        db: Database session (unused, kept for API compatibility)
        subdirectory: Temp directory name under system tmp
    """
    if not protocol.file_data:
        raise ValueError(f"Protocol {protocol.id} has no PDF data")

    temp_dir = Path(tempfile.gettempdir()) / subdirectory
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{protocol.id}_{protocol.filename}"

    if not temp_path.exists():
        with open(temp_path, 'wb') as f:
            f.write(protocol.file_data)
        logger.info(f"Created temp PDF file: {temp_path}")

    return str(temp_path)


def get_protocol_by_study_id(study_id: str, db: Session) -> Optional[Protocol]:
    """
    Find a protocol by study_id (filename without .pdf extension).
    """
    # First try exact match on filename
    protocol = db.query(Protocol).filter(
        Protocol.filename == f"{study_id}.pdf"
    ).first()

    if protocol:
        return protocol

    # Try to find by partial match
    protocol = db.query(Protocol).filter(
        Protocol.filename.ilike(f"%{study_id}%")
    ).first()

    return protocol
