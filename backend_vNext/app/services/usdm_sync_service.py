"""
Service to sync extraction results to frontend usdm_documents table.

After extraction completes, this service populates the public.usdm_documents
table so that the frontend review UI can display the extracted data.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import Protocol
from app.services.checkpoint_service import CheckpointService
from app.services.usdm_transformer import UsdmTransformer

logger = logging.getLogger(__name__)


class UsdmSyncService:
    """Service to sync extraction results to usdm_documents table."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.checkpoint_service = CheckpointService(db)

    def sync_to_usdm_documents(self, protocol_id: UUID, job_id: UUID) -> bool:
        """
        Sync completed extraction results to public.usdm_documents table.

        Args:
            protocol_id: Protocol UUID
            job_id: Job UUID

        Returns:
            True if sync successful, False otherwise
        """
        try:
            # Get protocol record
            protocol = self.db.query(Protocol).filter(Protocol.id == protocol_id).first()
            if not protocol:
                logger.error(f"Protocol {protocol_id} not found")
                return False

            # Use the already-built USDM JSON from protocol record
            # (This preserves the correct {"study": {...}} structure)
            usdm_data = protocol.usdm_json

            if not usdm_data or not isinstance(usdm_data, dict):
                logger.error(f"No valid USDM data in protocol {protocol_id}")
                return False

            # USDMCombiner already produces the correct structure with domainSections
            # No transformation needed - use usdm_data directly

            # Extract study metadata for title
            study_metadata = usdm_data.get("study", {})
            study_id = protocol.filename.replace(".pdf", "")

            # Get study title from the USDM data
            if isinstance(study_metadata, dict):
                study_name = study_metadata.get("name", {})
                if isinstance(study_name, dict):
                    study_title = study_name.get("value", study_id)
                else:
                    study_title = study_id
            else:
                study_title = study_id

            # Use simple study_id (filename without .pdf) for consistent querying
            usdm_study_id = study_id

            insert_sql = text("""
                INSERT INTO public.usdm_documents
                    (study_id, study_title, usdm_data, source_document_url, created_at, updated_at)
                VALUES
                    (:study_id, :study_title, :usdm_data, :source_url, NOW(), NOW())
                ON CONFLICT (study_id) DO UPDATE SET
                    study_title = EXCLUDED.study_title,
                    usdm_data = EXCLUDED.usdm_data,
                    updated_at = NOW()
            """)

            self.db.execute(
                insert_sql,
                {
                    "study_id": usdm_study_id,
                    "study_title": study_title,
                    "usdm_data": json.dumps(usdm_data),  # Serialize to JSON string
                    "source_url": f"http://localhost:8080/api/v1/protocols/{protocol_id}/pdf/annotated",
                }
            )
            self.db.commit()

            logger.info(
                f"Successfully synced protocol {protocol_id} to usdm_documents "
                f"(study_id: {usdm_study_id})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to sync protocol {protocol_id} to usdm_documents: {e}")
            self.db.rollback()
            return False
