"""
Expansion Proposal Models for SOA Interpretation Pipeline

Data models for representing activity expansions, hierarchies, and human review items.

Usage:
    from soa_analyzer.models.expansion_proposal import (
        ActivityComponent,
        ActivityExpansion,
        ActivityHierarchy,
        HumanReviewItem,
    )

    expansion = ActivityExpansion(
        parent_activity_id="ACT-001",
        parent_activity_name="Hematology",
        components=[
            ActivityComponent(name="White Blood Cell Count", loinc_code="6690-2"),
            ActivityComponent(name="Red Blood Cell Count", loinc_code="789-8"),
        ],
        confidence=0.95,
    )
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class ExpansionType(Enum):
    """Types of expansions that can be proposed."""
    COMPONENT_EXPANSION = "component_expansion"  # Lab panel → individual tests
    HIERARCHY_GROUPING = "hierarchy_grouping"  # Activities grouped under category
    ALTERNATIVE_RESOLUTION = "alternative_resolution"  # X or Y choice point
    TIMING_DISTRIBUTION = "timing_distribution"  # BI/EOI split
    CYCLE_EXPANSION = "cycle_expansion"  # Cycle 4+ → explicit cycles
    CONDITION_ADDITION = "condition_addition"  # Add demographic/clinical condition


class ReviewStatus(Enum):
    """Status of a human review item."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


@dataclass
class ActivityComponent:
    """
    A single component test within a parent activity.

    Example: "White Blood Cell Count" within "Hematology"

    v2.0: Added provenance fields for protocol-driven expansion.
    Every component must be traceable to its source.
    """
    name: str
    id: str = field(default_factory=lambda: f"COMP-{uuid.uuid4().hex[:8].upper()}")
    loinc_code: Optional[str] = None
    loinc_display: Optional[str] = None
    cdisc_code: Optional[str] = None
    cdisc_decode: Optional[str] = None
    cdash_domain: Optional[str] = None
    specimen_type: Optional[str] = None
    unit: Optional[str] = None
    is_required: bool = True
    order: int = 0

    # Provenance fields (v2.0 - protocol-driven expansion)
    source: Optional[str] = None  # "extraction_json" | "pdf_text" | "both"
    source_module: Optional[str] = None  # e.g., "laboratory_specifications"
    json_path: Optional[str] = None  # e.g., "labTests[0].testName"
    page_number: Optional[int] = None  # PDF page where found
    text_snippet: Optional[str] = None  # Supporting text from protocol (max 200 chars)
    rationale: Optional[str] = None  # Why this component belongs to the activity
    confidence: float = 1.0  # Component-level confidence

    # Protocol-derived specimen details (from extraction modules)
    tube_type: Optional[str] = None  # EDTA, SST, lithium_heparin
    collection_volume: Optional[str] = None  # "3 mL"
    fasting_required: bool = False
    processing_requirements: Optional[str] = None
    storage_requirements: Optional[str] = None

    # Controlled terminology codes (from ATHENA/OMOP CDM)
    snomed_code: Optional[str] = None
    snomed_display: Optional[str] = None
    ncit_code: Optional[str] = None  # NCI Thesaurus
    ncit_display: Optional[str] = None
    omop_concept_id: Optional[int] = None  # OMOP CDM concept ID
    vocabulary_id: Optional[str] = None  # LOINC, SNOMED, NCIt, etc.
    terminology_match_score: Optional[float] = None  # 0.0-1.0
    terminology_match_type: Optional[str] = None  # exact, synonym, fuzzy, llm_selected

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "id": self.id,
            "name": self.name,
            "isRequired": self.is_required,
            "order": self.order,
            "confidence": self.confidence,
        }
        if self.loinc_code:
            result["loincCode"] = self.loinc_code
        if self.loinc_display:
            result["loincDisplay"] = self.loinc_display
        if self.cdisc_code:
            result["cdiscCode"] = self.cdisc_code
        if self.cdisc_decode:
            result["cdiscDecode"] = self.cdisc_decode
        if self.cdash_domain:
            result["cdashDomain"] = self.cdash_domain
        if self.specimen_type:
            result["specimenType"] = self.specimen_type
        if self.unit:
            result["unit"] = self.unit

        # Provenance (include if any provenance field is set)
        provenance = {}
        if self.source:
            provenance["source"] = self.source
        if self.source_module:
            provenance["sourceModule"] = self.source_module
        if self.json_path:
            provenance["jsonPath"] = self.json_path
        if self.page_number is not None:
            provenance["pageNumber"] = self.page_number
        if self.text_snippet:
            provenance["textSnippet"] = self.text_snippet
        if self.rationale:
            provenance["rationale"] = self.rationale
        if provenance:
            result["provenance"] = provenance

        # Specimen details (if available)
        if self.tube_type:
            result["tubeType"] = self.tube_type
        if self.collection_volume:
            result["collectionVolume"] = self.collection_volume
        if self.fasting_required:
            result["fastingRequired"] = self.fasting_required
        if self.processing_requirements:
            result["processingRequirements"] = self.processing_requirements
        if self.storage_requirements:
            result["storageRequirements"] = self.storage_requirements

        # Controlled terminology (ATHENA/OMOP CDM)
        terminology = {}
        if self.snomed_code:
            terminology["snomedCode"] = self.snomed_code
            terminology["snomedDisplay"] = self.snomed_display
        if self.ncit_code:
            terminology["ncitCode"] = self.ncit_code
            terminology["ncitDisplay"] = self.ncit_display
        if self.omop_concept_id:
            terminology["omopConceptId"] = self.omop_concept_id
        if self.vocabulary_id:
            terminology["vocabularyId"] = self.vocabulary_id
        if self.terminology_match_score is not None:
            terminology["matchScore"] = self.terminology_match_score
            terminology["matchType"] = self.terminology_match_type
        if terminology:
            result["terminology"] = terminology

        return result


@dataclass
class ActivityExpansion:
    """
    Represents an expansion of a parent activity into components.

    Example: Expanding "Hematology" into CBC components.
    """
    parent_activity_id: str
    parent_activity_name: str
    components: List[ActivityComponent] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"EXP-{uuid.uuid4().hex[:8].upper()}")
    expansion_type: ExpansionType = ExpansionType.COMPONENT_EXPANSION
    confidence: float = 1.0
    rationale: Optional[str] = None
    source: Optional[str] = None  # "llm", "config", "protocol"
    requires_review: bool = False
    review_reason: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "expansionType": self.expansion_type.value,
            "parentActivityId": self.parent_activity_id,
            "parentActivityName": self.parent_activity_name,
            "components": [c.to_dict() for c in self.components],
            "confidence": self.confidence,
            "rationale": self.rationale,
            "source": self.source,
            "requiresReview": self.requires_review,
            "reviewReason": self.review_reason,
            "provenance": self.provenance,
        }


@dataclass
class ActivityHierarchyNode:
    """
    A node in the activity hierarchy tree.

    Node types:
    - "category": Top-level domain grouping (e.g., "Laboratory Tests")
    - "activity": Activity from SOA table (e.g., "Hematology")
    - "component": Component test from Stage 2 expansion (e.g., "Hemoglobin")
    """
    id: str
    name: str
    node_type: str  # "category", "activity", "component"
    cdash_domain: Optional[str] = None
    children: List["ActivityHierarchyNode"] = field(default_factory=list)
    activity_ids: List[str] = field(default_factory=list)
    order: int = 0
    is_expanded: bool = True
    # Component-specific metadata (from Stage 2)
    confidence: Optional[float] = None
    unit: Optional[str] = None
    is_required: Optional[bool] = None
    provenance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "id": self.id,
            "name": self.name,
            "nodeType": self.node_type,
            "order": self.order,
            "isExpanded": self.is_expanded,
        }
        if self.cdash_domain:
            result["cdashDomain"] = self.cdash_domain
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.activity_ids:
            result["activityIds"] = self.activity_ids
        # Component-specific fields (only for node_type="component")
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.unit:
            result["unit"] = self.unit
        if self.is_required is not None:
            result["isRequired"] = self.is_required
        if self.provenance:
            result["provenance"] = self.provenance
        return result


@dataclass
class ActivityHierarchy:
    """
    Complete hierarchy of activities organized by domain/category.

    Example:
        Laboratory Tests (LB)
        ├── Hematology
        │   ├── CBC
        │   └── Differential
        └── Chemistry
            ├── Electrolytes
            └── Liver Function
    """
    id: str = field(default_factory=lambda: f"HIER-{uuid.uuid4().hex[:8].upper()}")
    root_nodes: List[ActivityHierarchyNode] = field(default_factory=list)
    total_activities: int = 0
    total_categories: int = 0
    confidence: float = 1.0
    provenance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "rootNodes": [n.to_dict() for n in self.root_nodes],
            "totalActivities": self.total_activities,
            "totalCategories": self.total_categories,
            "confidence": self.confidence,
            "provenance": self.provenance,
        }

    def add_activity_to_domain(
        self,
        activity_id: str,
        activity_name: str,
        cdash_domain: str,
        category_name: Optional[str] = None,
    ) -> None:
        """Add an activity to the appropriate domain category."""
        # Find or create domain node
        domain_node = None
        for node in self.root_nodes:
            if node.cdash_domain == cdash_domain:
                domain_node = node
                break

        if not domain_node:
            domain_node = ActivityHierarchyNode(
                id=f"DOM-{cdash_domain}",
                name=self._get_domain_display_name(cdash_domain),
                node_type="category",
                cdash_domain=cdash_domain,
                order=self._get_domain_order(cdash_domain),
            )
            self.root_nodes.append(domain_node)
            self.total_categories += 1

        # Add activity to domain
        if category_name:
            # Find or create subcategory
            subcat_node = None
            for child in domain_node.children:
                if child.name == category_name:
                    subcat_node = child
                    break

            if not subcat_node:
                subcat_node = ActivityHierarchyNode(
                    id=f"SUBCAT-{uuid.uuid4().hex[:6].upper()}",
                    name=category_name,
                    node_type="subcategory",
                    cdash_domain=cdash_domain,
                )
                domain_node.children.append(subcat_node)

            subcat_node.activity_ids.append(activity_id)
        else:
            domain_node.activity_ids.append(activity_id)

        self.total_activities += 1

    def _get_domain_display_name(self, domain: str) -> str:
        """Get display name for a CDASH domain code."""
        domain_names = {
            "LB": "Laboratory Tests",
            "VS": "Vital Signs",
            "EG": "ECG/Cardiac Assessments",
            "PE": "Physical Examination",
            "QS": "Questionnaires/PROs",
            "MI": "Medical Imaging",
            "CM": "Concomitant Medications",
            "AE": "Adverse Events",
            "EX": "Exposure/Treatment",
            "BS": "Biospecimen Collection",
            "DM": "Demographics",
            "MH": "Medical History",
            "DS": "Disposition",
            "PR": "Procedures",
            "TU": "Tumor/Oncology",
            "PC": "Pharmacokinetics",
        }
        return domain_names.get(domain, domain)

    def _get_domain_order(self, domain: str) -> int:
        """Get sort order for a CDASH domain."""
        order = {
            "DM": 1, "MH": 2, "PE": 3, "VS": 4, "EG": 5,
            "LB": 6, "MI": 7, "BS": 8, "PC": 9, "EX": 10,
            "CM": 11, "AE": 12, "QS": 13, "TU": 14, "PR": 15, "DS": 16,
        }
        return order.get(domain, 99)

    def sort_nodes(self) -> None:
        """Sort all nodes by their order."""
        self.root_nodes.sort(key=lambda n: n.order)
        for node in self.root_nodes:
            node.children.sort(key=lambda n: n.order)


@dataclass
class HumanReviewItem:
    """
    An item requiring human review/decision.
    """
    id: str = field(default_factory=lambda: f"REV-{uuid.uuid4().hex[:8].upper()}")
    item_type: str = ""  # "expansion", "alternative", "cycle_count", etc.
    title: str = ""
    description: str = ""
    source_entity_id: Optional[str] = None
    source_entity_type: Optional[str] = None
    priority: str = "medium"  # "critical", "high", "medium", "low"
    status: ReviewStatus = ReviewStatus.PENDING
    options: List[Dict[str, Any]] = field(default_factory=list)
    selected_option: Optional[str] = None
    custom_value: Optional[Any] = None
    reviewer_notes: Optional[str] = None
    confidence: float = 0.0
    auto_apply_threshold: float = 0.90
    provenance: Optional[Dict[str, Any]] = None

    @property
    def can_auto_apply(self) -> bool:
        """Check if this item can be auto-applied based on confidence."""
        return self.confidence >= self.auto_apply_threshold

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "itemType": self.item_type,
            "title": self.title,
            "description": self.description,
            "sourceEntityId": self.source_entity_id,
            "sourceEntityType": self.source_entity_type,
            "priority": self.priority,
            "status": self.status.value,
            "options": self.options,
            "selectedOption": self.selected_option,
            "customValue": self.custom_value,
            "reviewerNotes": self.reviewer_notes,
            "confidence": self.confidence,
            "canAutoApply": self.can_auto_apply,
            "provenance": self.provenance,
        }


@dataclass
class ExpansionResult:
    """
    Result of activity expansion processing.
    """
    expansions: List[ActivityExpansion] = field(default_factory=list)
    hierarchy: Optional[ActivityHierarchy] = None
    review_items: List[HumanReviewItem] = field(default_factory=list)

    # Counts
    activities_processed: int = 0
    activities_expanded: int = 0
    components_created: int = 0
    auto_applied: int = 0
    requires_review: int = 0

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of expansion results."""
        return {
            "activitiesProcessed": self.activities_processed,
            "activitiesExpanded": self.activities_expanded,
            "componentsCreated": self.components_created,
            "autoApplied": self.auto_applied,
            "requiresReview": self.requires_review,
            "hierarchyCategories": len(self.hierarchy.root_nodes) if self.hierarchy else 0,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "summary": self.get_summary(),
            "expansions": [e.to_dict() for e in self.expansions],
            "hierarchy": self.hierarchy.to_dict() if self.hierarchy else None,
            "reviewItems": [r.to_dict() for r in self.review_items],
        }
