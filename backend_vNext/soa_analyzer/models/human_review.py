"""
Human Review Models for Stage 10: Human Review Assembly

API-ready data models for aggregating review items from all pipeline stages
into a unified structure for React/Vue UI consumption.

Usage:
    from soa_analyzer.models.human_review import (
        ReviewItemType,
        ReviewPriority,
        ReviewAction,
        UnifiedReviewItem,
        StageReviewSection,
        HumanReviewPackage,
        Stage10Result,
    )
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid


# =============================================================================
# ENUMS
# =============================================================================


class ReviewItemType(str, Enum):
    """Types of review items from each pipeline stage."""
    # Stage 1 - Domain Categorization
    DOMAIN_MAPPING = "domain_mapping"

    # Stage 2 - Activity Expansion
    ACTIVITY_EXPANSION = "activity_expansion"
    COMPONENT_ADDITION = "component_addition"

    # Stage 3 - Hierarchy Building
    HIERARCHY_GROUPING = "hierarchy_grouping"
    PARENT_ASSIGNMENT = "parent_assignment"

    # Stage 4 - Alternative Resolution
    ALTERNATIVE_CHOICE = "alternative_choice"
    MUTUALLY_EXCLUSIVE = "mutually_exclusive"

    # Stage 5 - Specimen Enrichment
    SPECIMEN_TYPE = "specimen_type"
    TUBE_TYPE = "tube_type"
    COLLECTION_DETAIL = "collection_detail"

    # Stage 6 - Conditional Expansion
    CONDITION_APPLICATION = "condition_application"
    POPULATION_FILTER = "population_filter"

    # Stage 7 - Timing Distribution
    TIMING_EXPANSION = "timing_expansion"
    BI_EOI_SPLIT = "bi_eoi_split"

    # Stage 8 - Cycle Expansion
    CYCLE_COUNT = "cycle_count"
    CYCLE_PATTERN = "cycle_pattern"

    # Stage 9 - Protocol Mining
    PROTOCOL_ENRICHMENT = "protocol_enrichment"
    ENDPOINT_LINK = "endpoint_link"

    # Stage 12 - USDM Compliance
    CODE_VALIDATION = "code_validation"


class ReviewPriority(str, Enum):
    """Priority levels for review items."""
    CRITICAL = "critical"  # Blocks schedule generation
    HIGH = "high"          # Affects data quality
    MEDIUM = "medium"      # Recommended review
    LOW = "low"            # Informational


class ReviewAction(str, Enum):
    """Actions a reviewer can take on an item."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    DEFERRED = "deferred"


# =============================================================================
# SUPPORTING DATACLASSES
# =============================================================================


@dataclass
class ReviewOption:
    """
    Single option for a review item.

    Used when the reviewer must choose between predefined alternatives.
    """
    id: str
    label: str
    description: str
    is_default: bool = False
    is_recommended: bool = False
    confidence: float = 0.0
    provenance: Optional[Dict[str, Any]] = None

    def to_api(self) -> Dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "isDefault": self.is_default,
            "isRecommended": self.is_recommended,
            "confidence": self.confidence,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewOption":
        """Create from dictionary."""
        return cls(
            id=data.get("id", f"OPT-{uuid.uuid4().hex[:8].upper()}"),
            label=data.get("label", ""),
            description=data.get("description", ""),
            is_default=data.get("isDefault", data.get("is_default", False)),
            is_recommended=data.get("isRecommended", data.get("is_recommended", False)),
            confidence=data.get("confidence", 0.0),
            provenance=data.get("provenance"),
        )


@dataclass
class ProvenanceDisplay:
    """
    Rich provenance information for UI display.

    Contains all information needed to show where data came from.
    """
    page_numbers: List[int] = field(default_factory=list)
    text_snippets: List[str] = field(default_factory=list)
    source_table: Optional[str] = None
    cell_coordinates: Optional[Dict[str, int]] = None  # {"row": 5, "col": 3}
    extraction_model: Optional[str] = None
    extraction_timestamp: Optional[str] = None
    transformation_steps: List[Dict[str, Any]] = field(default_factory=list)

    def to_api(self) -> Dict[str, Any]:
        """Convert to API response format."""
        return {
            "pageNumbers": self.page_numbers,
            "textSnippets": self.text_snippets,
            "sourceTable": self.source_table,
            "cellCoordinates": self.cell_coordinates,
            "extractionModel": self.extraction_model,
            "extractionTimestamp": self.extraction_timestamp,
            "transformationSteps": self.transformation_steps,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProvenanceDisplay":
        """Create from dictionary."""
        if not data:
            return cls()
        return cls(
            page_numbers=data.get("pageNumbers", data.get("page_numbers", [])),
            text_snippets=data.get("textSnippets", data.get("text_snippets", [])),
            source_table=data.get("sourceTable", data.get("source_table")),
            cell_coordinates=data.get("cellCoordinates", data.get("cell_coordinates")),
            extraction_model=data.get("extractionModel", data.get("extraction_model")),
            extraction_timestamp=data.get("extractionTimestamp", data.get("extraction_timestamp")),
            transformation_steps=data.get("transformationSteps", data.get("transformation_steps", [])),
        )


@dataclass
class ReasoningDisplay:
    """
    LLM reasoning and decision factors for UI display.

    Shows why a particular recommendation was made.
    """
    rationale: str = ""
    decision_factors: List[str] = field(default_factory=list)
    confidence_breakdown: Dict[str, float] = field(default_factory=dict)
    alternatives_considered: List[str] = field(default_factory=list)
    model_used: Optional[str] = None

    def to_api(self) -> Dict[str, Any]:
        """Convert to API response format."""
        return {
            "rationale": self.rationale,
            "decisionFactors": self.decision_factors,
            "confidenceBreakdown": self.confidence_breakdown,
            "alternativesConsidered": self.alternatives_considered,
            "modelUsed": self.model_used,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningDisplay":
        """Create from dictionary."""
        if not data:
            return cls()
        return cls(
            rationale=data.get("rationale", ""),
            decision_factors=data.get("decisionFactors", data.get("decision_factors", [])),
            confidence_breakdown=data.get("confidenceBreakdown", data.get("confidence_breakdown", {})),
            alternatives_considered=data.get("alternativesConsidered", data.get("alternatives_considered", [])),
            model_used=data.get("modelUsed", data.get("model_used")),
        )


# =============================================================================
# CORE REVIEW ITEM
# =============================================================================


@dataclass
class UnifiedReviewItem:
    """
    Single review item in API-ready format.

    This is the core structure sent to the UI for each item requiring review.
    All review items from different stages are normalized to this format.
    """
    # Identity
    id: str = field(default_factory=lambda: f"REV-{uuid.uuid4().hex[:8].upper()}")
    stage: int = 0
    stage_name: str = ""
    item_type: ReviewItemType = ReviewItemType.DOMAIN_MAPPING

    # Display
    title: str = ""
    description: str = ""
    priority: ReviewPriority = ReviewPriority.MEDIUM

    # Source entity
    source_entity_id: str = ""
    source_entity_type: str = ""  # "activity", "visit", "specimen", etc.
    source_entity_name: str = ""

    # Options for selection
    options: List[ReviewOption] = field(default_factory=list)
    allows_custom_value: bool = True
    custom_value_label: str = "Custom value"

    # Current state
    action: ReviewAction = ReviewAction.PENDING
    selected_option_id: Optional[str] = None
    custom_value: Optional[Any] = None
    reviewer_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None

    # Confidence
    confidence: float = 0.0
    auto_apply_threshold: float = 0.90

    # Rich context
    provenance: Optional[ProvenanceDisplay] = None
    reasoning: Optional[ReasoningDisplay] = None

    # Related items
    related_item_ids: List[str] = field(default_factory=list)
    blocks_item_ids: List[str] = field(default_factory=list)  # Items that depend on this

    # Original data reference
    _original_item: Optional[Any] = field(default=None, repr=False)

    @property
    def can_auto_apply(self) -> bool:
        """Check if this item can be auto-applied based on confidence."""
        return self.confidence >= self.auto_apply_threshold

    @property
    def is_resolved(self) -> bool:
        """Check if this item has been resolved."""
        return self.action != ReviewAction.PENDING

    def to_api(self) -> Dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "stage": self.stage,
            "stageName": self.stage_name,
            "itemType": self.item_type.value,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "sourceEntity": {
                "id": self.source_entity_id,
                "type": self.source_entity_type,
                "name": self.source_entity_name,
            },
            "options": [o.to_api() for o in self.options],
            "allowsCustomValue": self.allows_custom_value,
            "customValueLabel": self.custom_value_label,
            "action": self.action.value,
            "selectedOptionId": self.selected_option_id,
            "customValue": self.custom_value,
            "reviewerNotes": self.reviewer_notes,
            "reviewedBy": self.reviewed_by,
            "reviewedAt": self.reviewed_at,
            "confidence": self.confidence,
            "canAutoApply": self.can_auto_apply,
            "provenance": self.provenance.to_api() if self.provenance else None,
            "reasoning": self.reasoning.to_api() if self.reasoning else None,
            "relatedItemIds": self.related_item_ids,
            "blocksItemIds": self.blocks_item_ids,
        }

    def apply_decision(
        self,
        action: ReviewAction,
        selected_option_id: Optional[str] = None,
        custom_value: Optional[Any] = None,
        reviewer_notes: Optional[str] = None,
        reviewed_by: Optional[str] = None,
    ) -> None:
        """Apply a review decision to this item."""
        self.action = action
        self.selected_option_id = selected_option_id
        self.custom_value = custom_value
        self.reviewer_notes = reviewer_notes
        self.reviewed_by = reviewed_by
        self.reviewed_at = datetime.now().isoformat()


# =============================================================================
# SECTION AND PACKAGE
# =============================================================================


@dataclass
class StageReviewSection:
    """
    Review items grouped by stage (UI section).

    Each pipeline stage that generates review items gets its own section.
    """
    stage: int
    stage_name: str
    description: str
    items: List[UnifiedReviewItem] = field(default_factory=list)

    # Aggregates (calculated)
    total_items: int = 0
    pending_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    modified_count: int = 0
    deferred_count: int = 0

    # Confidence distribution
    high_confidence_count: int = 0   # >= 0.90
    medium_confidence_count: int = 0  # 0.70-0.89
    low_confidence_count: int = 0    # < 0.70

    # Priority distribution
    critical_count: int = 0
    high_priority_count: int = 0

    def calculate_stats(self) -> None:
        """Calculate statistics from items."""
        self.total_items = len(self.items)
        self.pending_count = sum(1 for i in self.items if i.action == ReviewAction.PENDING)
        self.approved_count = sum(1 for i in self.items if i.action == ReviewAction.APPROVED)
        self.rejected_count = sum(1 for i in self.items if i.action == ReviewAction.REJECTED)
        self.modified_count = sum(1 for i in self.items if i.action == ReviewAction.MODIFIED)
        self.deferred_count = sum(1 for i in self.items if i.action == ReviewAction.DEFERRED)

        self.high_confidence_count = sum(1 for i in self.items if i.confidence >= 0.90)
        self.medium_confidence_count = sum(1 for i in self.items if 0.70 <= i.confidence < 0.90)
        self.low_confidence_count = sum(1 for i in self.items if i.confidence < 0.70)

        self.critical_count = sum(1 for i in self.items if i.priority == ReviewPriority.CRITICAL)
        self.high_priority_count = sum(1 for i in self.items if i.priority == ReviewPriority.HIGH)

    def to_api(self) -> Dict[str, Any]:
        """Convert to API response format."""
        self.calculate_stats()
        return {
            "stage": self.stage,
            "stageName": self.stage_name,
            "description": self.description,
            "items": [i.to_api() for i in self.items],
            "summary": {
                "totalItems": self.total_items,
                "pendingCount": self.pending_count,
                "approvedCount": self.approved_count,
                "rejectedCount": self.rejected_count,
                "modifiedCount": self.modified_count,
                "deferredCount": self.deferred_count,
                "highConfidenceCount": self.high_confidence_count,
                "mediumConfidenceCount": self.medium_confidence_count,
                "lowConfidenceCount": self.low_confidence_count,
                "criticalCount": self.critical_count,
                "highPriorityCount": self.high_priority_count,
            },
        }


@dataclass
class HumanReviewPackage:
    """
    Complete review package sent to UI (API response).

    This is the top-level structure containing all review items
    organized by stage, with summary statistics.
    """
    # Identity
    id: str = field(default_factory=lambda: f"REV-PKG-{uuid.uuid4().hex[:8].upper()}")
    protocol_id: str = ""
    protocol_name: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Sections by stage
    sections: List[StageReviewSection] = field(default_factory=list)

    # Draft schedule from Stage 11 (NEW)
    draft_schedule: Optional[Dict[str, Any]] = None  # Draft USDM with review markers
    draft_generation_summary: Optional[Dict[str, Any]] = None  # Auto-approved/pending counts

    # Global summary (calculated)
    total_items: int = 0
    total_pending: int = 0
    total_approved: int = 0
    total_rejected: int = 0
    stages_with_items: int = 0

    # Actions
    can_generate_schedule: bool = False  # True when all critical items resolved

    # Metadata
    pipeline_version: str = "1.0.0"
    usdm_version: str = "4.0.0"

    def calculate_stats(self) -> None:
        """Calculate global statistics from sections."""
        self.total_items = sum(len(s.items) for s in self.sections)
        self.total_pending = sum(s.pending_count for s in self.sections)
        self.total_approved = sum(s.approved_count for s in self.sections)
        self.total_rejected = sum(s.rejected_count for s in self.sections)
        self.stages_with_items = sum(1 for s in self.sections if s.items)

        # Check if schedule can be generated (all critical items resolved)
        all_critical_resolved = True
        for section in self.sections:
            for item in section.items:
                if item.priority == ReviewPriority.CRITICAL and item.action == ReviewAction.PENDING:
                    all_critical_resolved = False
                    break
            if not all_critical_resolved:
                break
        self.can_generate_schedule = all_critical_resolved

    def to_api(self) -> Dict[str, Any]:
        """Convert to full API response."""
        # Ensure stats are calculated
        for section in self.sections:
            section.calculate_stats()
        self.calculate_stats()

        result = {
            "id": self.id,
            "protocolId": self.protocol_id,
            "protocolName": self.protocol_name,
            "createdAt": self.created_at,
            "sections": [s.to_api() for s in self.sections],
            "summary": {
                "totalItems": self.total_items,
                "totalPending": self.total_pending,
                "totalApproved": self.total_approved,
                "totalRejected": self.total_rejected,
                "stagesWithItems": self.stages_with_items,
            },
            "canGenerateSchedule": self.can_generate_schedule,
            "pipelineVersion": self.pipeline_version,
            "usdmVersion": self.usdm_version,
        }

        # Include draft schedule if available
        if self.draft_schedule:
            result["draftSchedule"] = self.draft_schedule
        if self.draft_generation_summary:
            result["draftGenerationSummary"] = self.draft_generation_summary

        return result

    def get_item_by_id(self, item_id: str) -> Optional[UnifiedReviewItem]:
        """Find a review item by its ID."""
        for section in self.sections:
            for item in section.items:
                if item.id == item_id:
                    return item
        return None

    def get_pending_items(self) -> List[UnifiedReviewItem]:
        """Get all pending items across all sections."""
        items = []
        for section in self.sections:
            items.extend([i for i in section.items if i.action == ReviewAction.PENDING])
        return items

    def get_critical_pending_items(self) -> List[UnifiedReviewItem]:
        """Get all critical pending items."""
        items = []
        for section in self.sections:
            items.extend([
                i for i in section.items
                if i.action == ReviewAction.PENDING and i.priority == ReviewPriority.CRITICAL
            ])
        return items


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


@dataclass
class ReviewDecisionRequest:
    """Request to update a review item (API input)."""
    item_id: str
    action: ReviewAction
    selected_option_id: Optional[str] = None
    custom_value: Optional[Any] = None
    reviewer_notes: Optional[str] = None
    reviewed_by: Optional[str] = None

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "ReviewDecisionRequest":
        """Create from API request data."""
        return cls(
            item_id=data["itemId"],
            action=ReviewAction(data["action"]),
            selected_option_id=data.get("selectedOptionId"),
            custom_value=data.get("customValue"),
            reviewer_notes=data.get("reviewerNotes"),
            reviewed_by=data.get("reviewedBy"),
        )


@dataclass
class BatchReviewRequest:
    """Request to update multiple review items."""
    decisions: List[ReviewDecisionRequest]
    apply_to_similar: bool = False  # Apply same decision to similar items

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "BatchReviewRequest":
        """Create from API request data."""
        return cls(
            decisions=[ReviewDecisionRequest.from_api(d) for d in data.get("decisions", [])],
            apply_to_similar=data.get("applyToSimilar", False),
        )


# =============================================================================
# STAGE 10 RESULT
# =============================================================================


@dataclass
class Stage10Config:
    """Configuration for Stage 10 Human Review Assembly."""
    auto_approve_threshold: float = 0.95
    confidence_threshold_high: float = 0.90
    confidence_threshold_medium: float = 0.70
    include_empty_sections: bool = False
    sort_items_by_priority: bool = True
    sort_items_by_confidence: bool = False


@dataclass
class Stage10Result:
    """Result of human review assembly."""
    package: HumanReviewPackage = field(default_factory=HumanReviewPackage)

    # Metrics
    items_collected: int = 0
    items_by_stage: Dict[int, int] = field(default_factory=dict)
    items_by_priority: Dict[str, int] = field(default_factory=dict)
    items_by_type: Dict[str, int] = field(default_factory=dict)
    auto_approved_count: int = 0
    processing_time_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "package": self.package.to_api(),
            "metrics": {
                "itemsCollected": self.items_collected,
                "itemsByStage": self.items_by_stage,
                "itemsByPriority": self.items_by_priority,
                "itemsByType": self.items_by_type,
                "autoApprovedCount": self.auto_approved_count,
                "processingTimeSeconds": self.processing_time_seconds,
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }
