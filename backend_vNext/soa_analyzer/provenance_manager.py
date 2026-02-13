"""
Provenance Manager - Audit Trail Collection Throughout Pipeline

This module manages the collection and aggregation of provenance information
as values flow through the SOA extraction pipeline stages. It provides:
- Recording of transformation steps with timestamps and confidence
- Cell coordinate tracking for all extracted values
- Stage summary aggregation
- Final audit trail generation

Usage:
    provenance = ProvenanceManager(protocol_id, pdf_path)
    provenance.record_transformation(...)
    provenance.start_stage("extraction")
    provenance.end_stage("extraction", success_count=10)
    audit_trail = provenance.finalize()
"""

import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    AuditTrail,
    CellPosition,
    ProvenanceRecord,
    StageSummary,
    TransformationStep,
    ProtocolType,
)

logger = logging.getLogger(__name__)


class ProvenanceManager:
    """Manage provenance collection through pipeline.

    Collects transformation history, cell coordinates, and confidence scores
    as data flows through pipeline stages. Produces a complete audit trail
    at the end of extraction.
    """

    def __init__(self, protocol_id: str, pdf_path: str):
        """Initialize provenance manager.

        Args:
            protocol_id: Unique identifier for the protocol
            pdf_path: Path to the source PDF file
        """
        self.protocol_id = protocol_id
        self.pdf_path = pdf_path

        # Initialize audit trail
        self.audit_trail = AuditTrail(
            protocol_id=protocol_id,
            pdf_hash=AuditTrail.compute_pdf_hash(pdf_path),
            extraction_start=datetime.now(),
        )

        # Track current stage for timing
        self._current_stage: Optional[str] = None
        self._stage_start_time: Optional[float] = None

        # Record lookup for updates
        self._records_by_entity: Dict[str, Dict[str, ProvenanceRecord]] = {}

        logger.debug(f"ProvenanceManager initialized for {protocol_id}")

    def set_protocol_type(self, protocol_type: ProtocolType) -> None:
        """Set the detected protocol type."""
        self.audit_trail.protocol_type = protocol_type

    # =========================================================================
    # STAGE TRACKING
    # =========================================================================

    def start_stage(
        self,
        stage_name: str,
        model_name: Optional[str] = None,
        input_count: int = 0,
    ) -> None:
        """Mark the start of a pipeline stage.

        Args:
            stage_name: Name of the stage (e.g., "detection", "extraction")
            model_name: Name of the LLM model used (if applicable)
            input_count: Number of input items to this stage
        """
        self._current_stage = stage_name
        self._stage_start_time = time.time()

        # Create stage summary
        summary = StageSummary(
            stage_name=stage_name,
            start_time=datetime.now(),
            input_count=input_count,
            model_name=model_name,
        )
        self.audit_trail.add_stage_summary(summary)

        logger.debug(f"Stage started: {stage_name}")

    def end_stage(
        self,
        stage_name: str,
        output_count: int = 0,
        success_count: int = 0,
        error_count: int = 0,
        avg_confidence: float = 1.0,
        notes: Optional[List[str]] = None,
    ) -> None:
        """Mark the end of a pipeline stage.

        Args:
            stage_name: Name of the stage
            output_count: Number of output items from this stage
            success_count: Number of successfully processed items
            error_count: Number of items that failed
            avg_confidence: Average confidence of outputs
            notes: Optional notes about the stage execution
        """
        summary = self.audit_trail.stage_summaries.get(stage_name)
        if not summary:
            logger.warning(f"End called for unknown stage: {stage_name}")
            return

        summary.end_time = datetime.now()
        summary.output_count = output_count
        summary.success_count = success_count
        summary.error_count = error_count
        summary.avg_confidence = avg_confidence

        if notes:
            summary.notes.extend(notes)

        # Calculate duration
        if self._stage_start_time and self._current_stage == stage_name:
            summary.duration_ms = int((time.time() - self._stage_start_time) * 1000)

        self._current_stage = None
        self._stage_start_time = None

        logger.debug(
            f"Stage ended: {stage_name} "
            f"(outputs={output_count}, success={success_count}, errors={error_count})"
        )

    # =========================================================================
    # TRANSFORMATION RECORDING
    # =========================================================================

    def record_transformation(
        self,
        entity_id: str,
        entity_type: str,
        field_name: str,
        stage: str,
        operation: str,
        value: Any,
        raw_value: str = "",
        cell: Optional[CellPosition] = None,
        confidence: float = 1.0,
        model_name: Optional[str] = None,
        **metadata,
    ) -> str:
        """Record a transformation step, return provenance record ID.

        Creates or updates a provenance record for the given entity/field,
        adding a new transformation step.

        Args:
            entity_id: ID of the entity (e.g., visit ID, footnote ID)
            entity_type: Type of entity (visit, activity, footnote, etc.)
            field_name: Name of the field being transformed
            stage: Pipeline stage name
            operation: Description of the operation
            value: The transformed value
            raw_value: Original raw text value
            cell: Cell position if value came from table cell
            confidence: Confidence score for this transformation
            model_name: Name of LLM model used (if applicable)
            **metadata: Additional metadata to record

        Returns:
            The provenance record ID
        """
        # Get or create record
        record = self._get_or_create_record(entity_id, entity_type, field_name)

        # Update record values
        record.extracted_value = value
        if raw_value:
            record.raw_value = raw_value
        if cell:
            record.cell_coordinate = cell

        # Create and add transformation step
        step = TransformationStep.create(
            stage=stage,
            operation=operation,
            confidence=confidence,
            model_name=model_name,
            **metadata,
        )
        record.add_transformation(step)

        logger.debug(
            f"Recorded transformation: {entity_type}/{entity_id}.{field_name} "
            f"@ {stage}/{operation} (conf={confidence:.2f})"
        )

        return record.record_id

    def record_cell_extraction(
        self,
        entity_id: str,
        entity_type: str,
        field_name: str,
        value: Any,
        cell: CellPosition,
        confidence: float = 1.0,
    ) -> str:
        """Convenience method for recording cell extraction.

        Args:
            entity_id: ID of the entity
            entity_type: Type of entity
            field_name: Field name
            value: Extracted value
            cell: Cell position
            confidence: OCR/extraction confidence

        Returns:
            Provenance record ID
        """
        return self.record_transformation(
            entity_id=entity_id,
            entity_type=entity_type,
            field_name=field_name,
            stage="extraction",
            operation="ocr_cell",
            value=value,
            raw_value=str(value),
            cell=cell,
            confidence=confidence,
        )

    def record_visit_parsing(
        self,
        visit_id: str,
        field_name: str,
        value: Any,
        confidence: float = 0.95,
        cell: Optional[CellPosition] = None,
    ) -> str:
        """Convenience method for recording visit parsing.

        Args:
            visit_id: Visit identifier
            field_name: Field being parsed (name, timing, window, etc.)
            value: Parsed value
            confidence: Parsing confidence
            cell: Optional source cell

        Returns:
            Provenance record ID
        """
        return self.record_transformation(
            entity_id=visit_id,
            entity_type="visit",
            field_name=field_name,
            stage="parsing",
            operation=f"parse_{field_name}",
            value=value,
            cell=cell,
            confidence=confidence,
        )

    def record_footnote_linking(
        self,
        footnote_id: str,
        field_name: str,
        value: Any,
        confidence: float = 0.8,
        strategy: str = "llm_cell_level",
    ) -> str:
        """Convenience method for recording footnote linking.

        Args:
            footnote_id: Footnote identifier
            field_name: Field being linked
            value: Link result (cells, visits, activities)
            confidence: Linking confidence
            strategy: Linking strategy used

        Returns:
            Provenance record ID
        """
        return self.record_transformation(
            entity_id=footnote_id,
            entity_type="footnote",
            field_name=field_name,
            stage="cell_linking",
            operation="link_footnote",
            value=value,
            confidence=confidence,
            strategy=strategy,
        )

    def _get_or_create_record(
        self,
        entity_id: str,
        entity_type: str,
        field_name: str,
    ) -> ProvenanceRecord:
        """Get existing or create new provenance record."""
        # Lookup by entity and field
        entity_records = self._records_by_entity.setdefault(entity_id, {})

        if field_name in entity_records:
            return entity_records[field_name]

        # Create new record
        record = ProvenanceRecord(
            record_id=f"prov-{str(uuid.uuid4())[:8]}",
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            extracted_value=None,
        )

        # Store and track
        entity_records[field_name] = record
        self.audit_trail.add_record(record)

        return record

    # =========================================================================
    # FLAGGING AND WARNINGS
    # =========================================================================

    def flag_record(
        self,
        entity_id: str,
        field_name: str,
        flag: str,
    ) -> None:
        """Add a flag to a provenance record.

        Args:
            entity_id: Entity ID
            field_name: Field name
            flag: Flag to add (e.g., "low_confidence", "needs_review")
        """
        entity_records = self._records_by_entity.get(entity_id, {})
        record = entity_records.get(field_name)

        if record and flag not in record.flags:
            record.flags.append(flag)

    def add_warning(self, message: str) -> None:
        """Add a warning to the audit trail."""
        self.audit_trail.warnings.append(message)
        logger.warning(f"Provenance warning: {message}")

    def add_error(self, message: str) -> None:
        """Add an error to the audit trail."""
        self.audit_trail.errors.append(message)
        logger.error(f"Provenance error: {message}")

    # =========================================================================
    # FINALIZATION AND OUTPUT
    # =========================================================================

    def finalize(self) -> AuditTrail:
        """Finalize the audit trail and return it.

        Calculates final metrics and marks extraction as complete.

        Returns:
            Complete AuditTrail object
        """
        self.audit_trail.finalize()
        logger.info(
            f"Audit trail finalized: {len(self.audit_trail.provenance_records)} records, "
            f"avg confidence: {self.audit_trail.quality_scores.get('avgConfidence', 0):.2%}"
        )
        return self.audit_trail

    def save(self, output_path: Path) -> Path:
        """Save audit trail to JSON file.

        Args:
            output_path: Directory to save the audit trail

        Returns:
            Path to the saved file
        """
        # Ensure finalized
        if self.audit_trail.extraction_end is None:
            self.finalize()

        # Save
        file_path = output_path / f"{self.protocol_id}_audit_trail.json"
        with open(file_path, "w") as f:
            json.dump(self.audit_trail.to_dict(), f, indent=2, default=str)

        logger.info(f"Audit trail saved: {file_path}")
        return file_path

    # =========================================================================
    # METRICS AGGREGATION
    # =========================================================================

    def get_confidence_summary(self) -> Dict[str, Any]:
        """Get summary of confidence scores across all records."""
        records = self.audit_trail.provenance_records
        if not records:
            return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0}

        confidences = [r.final_confidence for r in records]
        return {
            "count": len(confidences),
            "avg": sum(confidences) / len(confidences),
            "min": min(confidences),
            "max": max(confidences),
            "below_threshold": sum(1 for c in confidences if c < 0.7),
        }

    def get_stage_timing(self) -> Dict[str, int]:
        """Get timing breakdown by stage (in ms)."""
        return {
            name: summary.duration_ms
            for name, summary in self.audit_trail.stage_summaries.items()
        }

    def get_entity_counts(self) -> Dict[str, int]:
        """Get counts of entities by type."""
        counts: Dict[str, int] = {}
        for record in self.audit_trail.provenance_records:
            counts[record.entity_type] = counts.get(record.entity_type, 0) + 1
        return counts

    def get_records_needing_review(self) -> List[ProvenanceRecord]:
        """Get all records flagged for review."""
        return [
            r for r in self.audit_trail.provenance_records
            if "needs_review" in r.flags or r.final_confidence < 0.7
        ]
