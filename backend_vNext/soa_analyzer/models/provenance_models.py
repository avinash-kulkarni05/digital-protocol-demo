"""
Provenance Models for SOA Visit Schedule Extraction

This module defines data structures for tracking the complete audit trail
of extracted values, including:
- Cell-level coordinates
- Transformation history through pipeline stages
- Confidence score propagation
- Quality metrics and flags
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import hashlib
import uuid

from .timing_models import CellPosition, ProtocolType


# =============================================================================
# TRANSFORMATION TRACKING
# =============================================================================


@dataclass
class TransformationStep:
    """Single transformation in the pipeline.

    Records one step in the transformation chain, capturing what operation
    was performed, by which stage, and the confidence before/after.
    """
    step_id: str
    stage_name: str
    operation: str
    timestamp: datetime = field(default_factory=datetime.now)
    confidence_in: float = 1.0
    confidence_out: float = 1.0
    model_name: Optional[str] = None
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stepId": self.step_id,
            "stageName": self.stage_name,
            "operation": self.operation,
            "timestamp": self.timestamp.isoformat(),
            "confidenceIn": self.confidence_in,
            "confidenceOut": self.confidence_out,
            "modelName": self.model_name,
            "durationMs": self.duration_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def create(
        cls,
        stage: str,
        operation: str,
        confidence: float = 1.0,
        model_name: Optional[str] = None,
        **metadata,
    ) -> "TransformationStep":
        """Factory method to create a transformation step."""
        return cls(
            step_id=str(uuid.uuid4())[:8],
            stage_name=stage,
            operation=operation,
            confidence_in=confidence,
            confidence_out=confidence,
            model_name=model_name,
            metadata=metadata,
        )


@dataclass
class ProvenanceRecord:
    """Complete provenance for an extracted value.

    Tracks the full history of a value from extraction through transformation,
    including cell coordinates and confidence propagation.
    """
    record_id: str
    entity_type: str  # visit, activity, footnote, etc.
    entity_id: str
    field_name: str
    extracted_value: Any
    raw_value: str = ""
    cell_coordinate: Optional[CellPosition] = None
    transformation_chain: List[TransformationStep] = field(default_factory=list)
    final_confidence: float = 1.0
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recordId": self.record_id,
            "entityType": self.entity_type,
            "entityId": self.entity_id,
            "fieldName": self.field_name,
            "extractedValue": self.extracted_value,
            "rawValue": self.raw_value,
            "cellCoordinate": self.cell_coordinate.to_dict() if self.cell_coordinate else None,
            "transformationChain": [s.to_dict() for s in self.transformation_chain],
            "finalConfidence": self.final_confidence,
            "flags": self.flags,
        }

    def add_transformation(self, step: TransformationStep) -> None:
        """Add a transformation step and update confidence."""
        self.transformation_chain.append(step)
        self.final_confidence = self._calculate_confidence()

    def _calculate_confidence(self) -> float:
        """Calculate final confidence from transformation chain."""
        if not self.transformation_chain:
            return 1.0

        # Multiplicative confidence propagation
        confidence = 1.0
        for step in self.transformation_chain:
            confidence *= step.confidence_out

        return max(0.01, min(1.0, confidence))


# =============================================================================
# STAGE SUMMARY
# =============================================================================


@dataclass
class StageSummary:
    """Summary of a pipeline stage execution.

    Captures timing, counts, and quality metrics for a single stage.
    """
    stage_name: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: int = 0
    input_count: int = 0
    output_count: int = 0
    success_count: int = 0
    error_count: int = 0
    avg_confidence: float = 0.0
    model_name: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stageName": self.stage_name,
            "startTime": self.start_time.isoformat() if self.start_time else None,
            "endTime": self.end_time.isoformat() if self.end_time else None,
            "durationMs": self.duration_ms,
            "inputCount": self.input_count,
            "outputCount": self.output_count,
            "successCount": self.success_count,
            "errorCount": self.error_count,
            "avgConfidence": self.avg_confidence,
            "modelName": self.model_name,
            "notes": self.notes,
        }


# =============================================================================
# AUDIT TRAIL
# =============================================================================


@dataclass
class AuditTrail:
    """Complete audit trail for protocol extraction.

    The top-level container for all provenance information from a
    single extraction run.
    """
    protocol_id: str
    pdf_hash: str = ""
    extraction_start: datetime = field(default_factory=datetime.now)
    extraction_end: Optional[datetime] = None
    protocol_type: ProtocolType = ProtocolType.HYBRID
    provenance_records: List[ProvenanceRecord] = field(default_factory=list)
    stage_summaries: Dict[str, StageSummary] = field(default_factory=dict)
    quality_scores: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "auditTrail": {
                "protocolId": self.protocol_id,
                "pdfHash": self.pdf_hash,
                "extractionStart": self.extraction_start.isoformat(),
                "extractionEnd": self.extraction_end.isoformat() if self.extraction_end else None,
                "protocolType": self.protocol_type.value,
            },
            "provenanceRecords": [r.to_dict() for r in self.provenance_records],
            "stageSummaries": {k: v.to_dict() for k, v in self.stage_summaries.items()},
            "qualityScores": self.quality_scores,
            "warnings": self.warnings,
            "errors": self.errors,
        }

    def add_record(self, record: ProvenanceRecord) -> None:
        """Add a provenance record to the audit trail."""
        self.provenance_records.append(record)

    def add_stage_summary(self, summary: StageSummary) -> None:
        """Add or update a stage summary."""
        self.stage_summaries[summary.stage_name] = summary

    def get_records_for_entity(self, entity_id: str) -> List[ProvenanceRecord]:
        """Get all provenance records for a specific entity."""
        return [r for r in self.provenance_records if r.entity_id == entity_id]

    def finalize(self) -> None:
        """Mark extraction as complete and calculate final metrics."""
        self.extraction_end = datetime.now()

        # Calculate average confidence across all records
        if self.provenance_records:
            avg_conf = sum(r.final_confidence for r in self.provenance_records) / len(self.provenance_records)
            self.quality_scores["avgConfidence"] = round(avg_conf, 4)

        # Count flagged records
        flagged = sum(1 for r in self.provenance_records if r.flags)
        self.quality_scores["flaggedRecords"] = flagged
        self.quality_scores["totalRecords"] = len(self.provenance_records)

    @staticmethod
    def compute_pdf_hash(pdf_path: str) -> str:
        """Compute SHA256 hash of a PDF file."""
        try:
            with open(pdf_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except Exception:
            return "unknown"


# =============================================================================
# LINKING QUALITY METRICS
# =============================================================================


@dataclass
class LinkingQualityMetrics:
    """Quality metrics specific to cell linking.

    Detailed metrics for evaluating the success of footnote-to-cell linking.
    """
    # Coverage metrics
    total_markers: int = 0
    markers_linked: int = 0

    # Precision metrics
    column_wide_count: int = 0
    row_wide_count: int = 0
    cell_specific_count: int = 0
    ambiguous_count: int = 0  # Markers in >3 cells

    # Confidence distribution
    high_confidence_links: int = 0   # confidence >= 0.8
    medium_confidence_links: int = 0  # 0.5 <= confidence < 0.8
    low_confidence_links: int = 0    # confidence < 0.5

    # Strategy tracking
    strategy: str = "none"
    fallback_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "totalMarkers": self.total_markers,
            "markersLinked": self.markers_linked,
            "linkingCoverage": self.linking_coverage,
            "columnWideCount": self.column_wide_count,
            "rowWideCount": self.row_wide_count,
            "cellSpecificCount": self.cell_specific_count,
            "ambiguousCount": self.ambiguous_count,
            "highConfidenceLinks": self.high_confidence_links,
            "mediumConfidenceLinks": self.medium_confidence_links,
            "lowConfidenceLinks": self.low_confidence_links,
            "strategy": self.strategy,
            "fallbackUsed": self.fallback_used,
            "overallQuality": self.overall_quality,
        }

    @property
    def linking_coverage(self) -> float:
        """Ratio of markers successfully linked."""
        if self.total_markers == 0:
            return 1.0
        return self.markers_linked / self.total_markers

    @property
    def overall_quality(self) -> float:
        """Calculate overall linking quality score (0-1)."""
        if self.total_markers == 0:
            return 1.0

        coverage_score = self.linking_coverage * 0.4
        precision_score = (1 - self.ambiguous_count / max(self.markers_linked, 1)) * 0.3
        confidence_score = self.high_confidence_links / max(self.markers_linked, 1) * 0.3

        return coverage_score + precision_score + confidence_score


# Quality thresholds for linking
LINKING_QUALITY_THRESHOLDS = {
    "min_coverage": 0.50,            # At least 50% markers linked
    "max_ambiguity_rate": 0.20,      # At most 20% ambiguous
    "min_confidence_mean": 0.60,     # Mean confidence >= 60%
    "require_review_if_below": 0.70  # Flag for review if quality < 70%
}
