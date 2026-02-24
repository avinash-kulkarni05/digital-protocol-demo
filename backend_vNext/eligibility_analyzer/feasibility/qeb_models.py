"""
Queryable Eligibility Block (QEB) Data Models.

These models represent the output of Stage 12 QEB Builder, which transforms
atomic criteria into queryable blocks for the feasibility application.

Each QEB maps 1:1 to an original protocol criterion with combined SQL,
LLM-generated clinical names, and proper deduplication.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


class QueryableStatus(str, Enum):
    """
    Classification of how a criterion can be queried for feasibility.

    Data source-aware taxonomy that distinguishes between:
    - Structured data (SQL/FHIR queryable)
    - Unstructured data (LLM extractable from clinical notes)
    - Hybrid (both structured and unstructured)
    - True screening requirements (real-time assessment needed)
    - Administrative/consent requirements (not patient filters)
    """
    # Structured data sources - SQL/FHIR queryable
    FULLY_QUERYABLE = "fully_queryable"           # SQL against OMOP CDM / FHIR REST

    # Unstructured data sources - LLM extraction
    LLM_EXTRACTABLE = "llm_extractable"           # LLM can extract from clinical notes

    # Hybrid sources - both structured and unstructured
    HYBRID_QUERYABLE = "hybrid_queryable"         # SQL + LLM (partial structured + notes)

    # True enrollment-time requirements
    SCREENING_ONLY = "screening_only"             # Requires real-time clinical assessment

    # Administrative/procedural
    NOT_APPLICABLE = "not_applicable"             # Consent, compliance (not patient filters)

    # Legacy (for backward compatibility)
    PARTIALLY_QUERYABLE = "partially_queryable"   # Some aspects queryable
    REQUIRES_MANUAL = "requires_manual"           # Manual chart review


class DataSourceType(str, Enum):
    """
    Classification of where clinical data is typically found.

    Used to determine the appropriate query method for each atomic criterion.
    """
    # Structured EHR data with standard codes
    EHR_STRUCTURED = "ehr_structured"

    # Pathology and molecular diagnostics reports
    PATHOLOGY_REPORT = "pathology_report"

    # Imaging and radiology reports
    RADIOLOGY_REPORT = "radiology_report"

    # Clinical notes and progress documentation
    CLINICAL_NOTES = "clinical_notes"

    # Requires NEW assessment at enrollment
    REAL_TIME_ASSESSMENT = "real_time_assessment"

    # Requires subjective investigator evaluation
    CLINICAL_JUDGMENT = "clinical_judgment"

    # Requires formula calculation at enrollment
    CALCULATED_VALUE = "calculated_value"

    # Requires patient agreement or consent
    PATIENT_DECISION = "patient_decision"


@dataclass
class DataSourceClassification:
    """
    Classification of where clinical data for an atomic criterion is found.

    Determines whether data can be queried from structured sources,
    extracted from unstructured notes via LLM, or requires real-time assessment.
    """
    atomic_id: str
    primary_data_source: str                      # DataSourceType value
    secondary_data_source: Optional[str] = None   # Optional secondary source
    note_types: List[str] = field(default_factory=list)  # e.g., ["Pathology", "Radiology"]
    confidence: float = 0.9
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "atomicId": self.atomic_id,
            "primaryDataSource": self.primary_data_source,
            "secondaryDataSource": self.secondary_data_source,
            "noteTypes": self.note_types,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


@dataclass
class NlpQuerySpec:
    """
    Specification for LLM-based extraction from clinical notes.

    Used when queryableStatus is LLM_EXTRACTABLE or HYBRID_QUERYABLE.
    Provides the information needed for downstream NLP extraction.
    """
    note_types: List[str]                         # ["Pathology", "Radiology", "Progress Note"]
    extraction_prompt: Optional[str] = None       # LLM prompt for extraction
    expected_values: List[str] = field(default_factory=list)  # Valid extracted values
    value_type: str = "categorical"               # "categorical", "numeric", "boolean", "date"
    temporal_constraint: Optional[str] = None     # "most_recent", "within_6_months", "any"
    confidence_threshold: float = 0.70            # Below this triggers human review

    def to_dict(self) -> Dict[str, Any]:
        return {
            "noteTypes": self.note_types,
            "extractionPrompt": self.extraction_prompt,
            "expectedValues": self.expected_values,
            "valueType": self.value_type,
            "temporalConstraint": self.temporal_constraint,
            "confidenceThreshold": self.confidence_threshold,
        }


@dataclass
class OMOPConceptRef:
    """Reference to an OMOP concept used in a QEB."""

    concept_id: int
    concept_name: str
    domain_id: str
    vocabulary_id: Optional[str] = None
    concept_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conceptId": self.concept_id,
            "conceptName": self.concept_name,
            "domain": self.domain_id,
            "vocabularyId": self.vocabulary_id,
            "conceptCode": self.concept_code,
        }


@dataclass
class FHIRResourceRef:
    """Reference to a FHIR resource specification for a QEB."""

    resource_type: str
    search_params: Dict[str, Any]
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resourceType": self.resource_type,
            "searchParams": self.search_params,
            "description": self.description,
        }


@dataclass
class CDISCBiomedicalConcept:
    """
    CDISC Biomedical Concept for eligibility criteria.

    Provides standardized CDISC terminology alongside OMOP/FHIR mappings.
    Enables cross-pipeline consistency with Main Pipeline and SOA Pipeline BC objects.

    Fields:
    - concept_name (required): Standardized clinical concept name (max 150 chars)
    - cdisc_code (required): NCI EVS code or "CUSTOM" if no standard code exists (max 20 chars)
    - domain (required): CDISC domain (CM, LB, VS, MH, DS, etc.)
    - specimen (optional): Specimen type if applicable
    - method (optional): Method/route if applicable
    - confidence (optional): 0.0-1.0, defaults to 0.5 for CUSTOM codes
    - rationale (optional): Brief explanation for code assignment (max 200 chars)
    - source_omop_concept_id (optional): Link back to OMOP concept this was mapped from
    """

    concept_name: str
    cdisc_code: str  # NCI EVS code or "CUSTOM"
    domain: str  # CDISC domain: CM, LB, VS, MH, DS, AE, etc.
    specimen: Optional[str] = None
    method: Optional[str] = None
    confidence: float = 0.5
    rationale: Optional[str] = None
    source_omop_concept_id: Optional[int] = None  # Link to source OMOP concept

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "conceptName": self.concept_name,
            "cdiscCode": self.cdisc_code,
            "domain": self.domain,
            "confidence": self.confidence,
        }
        if self.specimen:
            result["specimen"] = self.specimen
        if self.method:
            result["method"] = self.method
        if self.rationale:
            result["rationale"] = self.rationale
        if self.source_omop_concept_id:
            result["sourceOmopConceptId"] = self.source_omop_concept_id
        return result


@dataclass
class QEBProvenance:
    """Provenance information for a QEB."""

    page_number: Optional[int] = None
    section_id: Optional[str] = None
    text_snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pageNumber": self.page_number,
            "sectionId": self.section_id,
            "textSnippet": self.text_snippet,
        }


@dataclass
class ClinicalConceptGroup:
    """
    A clinical concept grouping of related atomics.

    Groups atomics that represent variants of the same clinical question
    (e.g., EGFR ex19 + EGFR L858R → "EGFR Activating Mutation").
    """

    group_name: str                          # "EGFR Activating Mutation", "Non-squamous NSCLC"
    clinical_category: str                   # disease_indication, biomarker, prior_therapy, etc.
    atomic_ids: List[str] = field(default_factory=list)  # ["A0009", "A0010"]
    queryable_status: str = "fully_queryable"  # Aggregate status of atomics in group
    treatment_implication: Optional[str] = None  # "EGFR TKI eligible"
    plain_english: Optional[str] = None        # Human-readable description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "groupName": self.group_name,
            "clinicalCategory": self.clinical_category,
            "atomicIds": self.atomic_ids,
            "queryableStatus": self.queryable_status,
            "treatmentImplication": self.treatment_implication,
            "plainEnglish": self.plain_english,
        }


@dataclass
class ScreeningOnlyRequirement:
    """
    An atomic marked as screening_only (documentation/site requirement, not patient filter).
    """

    atomic_id: str
    description: str
    note: Optional[str] = None  # "Site documentation requirement, not patient filter"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "atomicId": self.atomic_id,
            "description": self.description,
            "note": self.note,
        }


@dataclass
class ClinicalSummary:
    """
    Clinical abstraction layer for a QEB.

    Provides a higher-level clinical view alongside the detailed atomics,
    enabling both precise technical queries and clinical readability.
    """

    # Groups of related atomics with clinical names
    concept_groups: List[ClinicalConceptGroup] = field(default_factory=list)

    # Atomics marked as screening-only (documentation/site requirements)
    screening_only_requirements: List[ScreeningOnlyRequirement] = field(default_factory=list)

    # Plain English summary of the criterion's clinical logic
    clinical_logic_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conceptGroups": [g.to_dict() for g in self.concept_groups],
            "screeningOnlyRequirements": [s.to_dict() for s in self.screening_only_requirements],
            "clinicalLogicSummary": self.clinical_logic_summary,
        }


@dataclass
class QueryableEligibilityBlock:
    """
    A single queryable unit for the feasibility application.

    Maps 1:1 to an original protocol criterion (INC_1, EXC_5, etc.)
    with combined SQL implementing the full logical structure.
    """

    # Identification
    qeb_id: str                          # "QEB_INC_3", "QEB_EXC_5"
    original_criterion_id: str           # "INC_3", "EXC_5"
    criterion_type: str                  # "inclusion" or "exclusion"

    # Clinical Context (LLM-generated)
    clinical_name: str                   # "Non-small Cell Lung Cancer Diagnosis"
    clinical_description: str            # "Patient must have cytologically confirmed..."
    clinical_category: str               # LLM-determined, free-form

    # Funnel Placement (LLM-determined)
    funnel_stage: str                    # "Disease Indication", etc.
    funnel_stage_order: int              # 1, 2, 3, ...

    # Query Execution
    combined_sql: str                    # Single SQL implementing full logic
    sql_logic_explanation: str           # "A0003 OR A0004 AND A0005"
    queryable_status: str                # "fully_queryable", "partially_queryable", "requires_manual"
    non_queryable_reason: Optional[str] = None  # Why manual review needed

    # Impact Metrics (LLM-determined, evidence-backed)
    estimated_elimination_rate: Optional[float] = None  # Only set if epidemiological evidence exists
    is_killer_criterion: bool = False                   # High-impact flag (requires evidence)
    epidemiological_evidence: Optional[str] = None      # Citation/source for elimination rate

    # Component Atomics (for transparency)
    atomic_ids: List[str] = field(default_factory=list)  # ["A0003", "A0004", ...]
    atomic_count: int = 0
    internal_logic: str = "SIMPLE"       # "AND", "OR", "COMPLEX", "SIMPLE"

    # OMOP/FHIR Resources (deduplicated)
    omop_concepts: List[OMOPConceptRef] = field(default_factory=list)
    fhir_resources: List[FHIRResourceRef] = field(default_factory=list)

    # CDISC Biomedical Concepts (cross-pipeline consistency)
    biomedical_concepts: List[CDISCBiomedicalConcept] = field(default_factory=list)

    # Provenance
    protocol_text: str = ""              # Original criterion text from protocol
    provenance: Optional[QEBProvenance] = None

    # Clinical Summary (additive abstraction layer for UI/feasibility)
    # Groups related atomics, identifies screening-only requirements,
    # and provides plain English clinical logic summary
    clinical_summary: Optional[ClinicalSummary] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "qebId": self.qeb_id,
            "originalCriterionId": self.original_criterion_id,
            "criterionType": self.criterion_type,
            "clinicalName": self.clinical_name,
            "clinicalDescription": self.clinical_description,
            "clinicalCategory": self.clinical_category,
            "funnelStage": self.funnel_stage,
            "funnelStageOrder": self.funnel_stage_order,
            "combinedSql": self.combined_sql,
            "sqlLogicExplanation": self.sql_logic_explanation,
            "queryableStatus": self.queryable_status,
            "nonQueryableReason": self.non_queryable_reason,
            "estimatedEliminationRate": self.estimated_elimination_rate,
            "isKillerCriterion": self.is_killer_criterion,
            "epidemiologicalEvidence": self.epidemiological_evidence,
            "atomicIds": self.atomic_ids,
            "atomicCount": self.atomic_count,
            "internalLogic": self.internal_logic,
            "omopConcepts": [c.to_dict() for c in self.omop_concepts],
            "fhirResources": [r.to_dict() for r in self.fhir_resources],
            "biomedicalConcepts": [bc.to_dict() for bc in self.biomedical_concepts],
            "protocolText": self.protocol_text,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            # Clinical abstraction layer (atomics + clinical groupings shown side by side)
            "clinicalSummary": self.clinical_summary.to_dict() if self.clinical_summary else None,
        }


@dataclass
class QEBFunnelStage:
    """
    A funnel stage containing grouped QEBs.

    Stage names and groupings are LLM-determined based on therapeutic area.
    """

    stage_id: str                        # "FS_1", "FS_2", etc.
    stage_name: str                      # LLM-generated name
    stage_order: int                     # 1, 2, 3, ...
    qeb_ids: List[str] = field(default_factory=list)
    combined_elimination_rate: float = 0.0
    stage_description: Optional[str] = None  # LLM-generated description

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "stageId": self.stage_id,
            "stageName": self.stage_name,
            "stageOrder": self.stage_order,
            "qebIds": self.qeb_ids,
            "combinedEliminationRate": self.combined_elimination_rate,
            "stageDescription": self.stage_description,
        }


@dataclass
class QEBSummary:
    """Summary statistics for QEB output."""

    total_qebs: int = 0
    inclusion_qebs: int = 0
    exclusion_qebs: int = 0

    # Data source-aware queryability breakdown
    fully_queryable: int = 0             # SQL/FHIR queryable (structured data)
    llm_extractable: int = 0             # LLM can extract from clinical notes
    hybrid_queryable: int = 0            # Both SQL and LLM extraction
    screening_only: int = 0              # Requires real-time assessment
    not_applicable: int = 0              # Consent/compliance, not patient filters

    # Legacy (backward compatibility)
    partially_queryable: int = 0
    requires_manual_review: int = 0

    total_atomics_consolidated: int = 0
    unique_omop_concepts: int = 0
    deduplication_rate: float = 0.0      # % reduction from atomics to QEBs
    killer_criteria_count: int = 0
    funnel_stages_count: int = 0
    # Eligibility section page range from PDF
    eligibility_page_start: Optional[int] = None
    eligibility_page_end: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "totalQEBs": self.total_qebs,
            "inclusionQEBs": self.inclusion_qebs,
            "exclusionQEBs": self.exclusion_qebs,
            # Data source-aware queryability
            "fullyQueryable": self.fully_queryable,
            "llmExtractable": self.llm_extractable,
            "hybridQueryable": self.hybrid_queryable,
            "screeningOnly": self.screening_only,
            "notApplicable": self.not_applicable,
            # Legacy (backward compatibility)
            "partiallyQueryable": self.partially_queryable,
            "requiresManualReview": self.requires_manual_review,
            "totalAtomicsConsolidated": self.total_atomics_consolidated,
            "uniqueOmopConcepts": self.unique_omop_concepts,
            "deduplicationRate": self.deduplication_rate,
            "killerCriteriaCount": self.killer_criteria_count,
            "funnelStagesCount": self.funnel_stages_count,
        }
        # Add page range if available
        if self.eligibility_page_start is not None and self.eligibility_page_end is not None:
            result["eligibilitySectionPages"] = {
                "start": self.eligibility_page_start,
                "end": self.eligibility_page_end
            }
        return result


@dataclass
class QEBExecutionGuide:
    """
    Guide for executing QEBs in the feasibility application.

    Contains recommended execution order and special handling flags.
    """

    recommended_order: List[str] = field(default_factory=list)  # QEB IDs in order
    killer_criteria: List[str] = field(default_factory=list)    # High-impact QEBs
    manual_review_required: List[str] = field(default_factory=list)
    execution_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "recommendedOrder": self.recommended_order,
            "killerCriteria": self.killer_criteria,
            "manualReviewRequired": self.manual_review_required,
            "executionNotes": self.execution_notes,
        }


@dataclass
class QEBOutput:
    """
    Complete QEB output for a protocol.

    This is the main output of Stage 12 QEB Builder, containing:
    - Summary statistics
    - Funnel stages with grouped QEBs
    - Individual QEB details
    - Execution guide for the feasibility application
    - Atomic criteria with queryability classifications (for validation UI)
    - Logical groups mapping QEBs to their constituent atomics
    """

    protocol_id: str
    version: str = "1.0"
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    therapeutic_area: Optional[str] = None

    summary: QEBSummary = field(default_factory=QEBSummary)
    funnel_stages: List[QEBFunnelStage] = field(default_factory=list)
    queryable_blocks: List[QueryableEligibilityBlock] = field(default_factory=list)
    execution_guide: QEBExecutionGuide = field(default_factory=QEBExecutionGuide)

    # Atomic-level data (for validation UI)
    # Each atomic includes queryabilityClassification from LLM
    atomic_criteria: List[Dict[str, Any]] = field(default_factory=list)

    # Logical groups mapping QEBs to atomics (for validation UI)
    # Each group has: qebId, criterionType, criterionText, atomicIds, funnelStage, isKiller
    logical_groups: List[Dict[str, Any]] = field(default_factory=list)

    # Processing metadata
    processing_time_seconds: float = 0.0
    llm_model_used: Optional[str] = None
    stage_inputs_used: List[str] = field(default_factory=list)  # ["stage2", "stage5", "stage6"]
    llm_warnings: List[str] = field(default_factory=list)  # LLM failures/warnings tracked

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "protocolId": self.protocol_id,
            "version": self.version,
            "generatedAt": self.generated_at,
            "therapeuticArea": self.therapeutic_area,
            "summary": self.summary.to_dict(),
            "funnelStages": [s.to_dict() for s in self.funnel_stages],
            "queryableBlocks": [q.to_dict() for q in self.queryable_blocks],
            "executionGuide": self.execution_guide.to_dict(),
            # Atomic-level data for validation UI (includes queryabilityClassification)
            "atomicCriteria": self.atomic_criteria,
            # Logical groups for validation UI (QEB -> atomic mapping)
            "logicalGroups": self.logical_groups,
            "processingMetadata": {
                "processingTimeSeconds": self.processing_time_seconds,
                "llmModelUsed": self.llm_model_used,
                "stageInputsUsed": self.stage_inputs_used,
                "llmWarnings": self.llm_warnings,
            },
        }

    def get_qeb_by_id(self, qeb_id: str) -> Optional[QueryableEligibilityBlock]:
        """Look up a QEB by its ID."""
        for qeb in self.queryable_blocks:
            if qeb.qeb_id == qeb_id:
                return qeb
        return None

    def get_qebs_by_stage(self, stage_name: str) -> List[QueryableEligibilityBlock]:
        """Get all QEBs in a given funnel stage."""
        result = []
        for qeb in self.queryable_blocks:
            if qeb.funnel_stage == stage_name:
                result.append(qeb)
        return result

    def get_inclusion_qebs(self) -> List[QueryableEligibilityBlock]:
        """Get all inclusion QEBs."""
        return [q for q in self.queryable_blocks if q.criterion_type == "inclusion"]

    def get_exclusion_qebs(self) -> List[QueryableEligibilityBlock]:
        """Get all exclusion QEBs."""
        return [q for q in self.queryable_blocks if q.criterion_type == "exclusion"]

    def get_killer_qebs(self) -> List[QueryableEligibilityBlock]:
        """Get all killer criteria QEBs."""
        return [q for q in self.queryable_blocks if q.is_killer_criterion]


def save_qeb_output(output: QEBOutput, output_dir, protocol_id: str) -> str:
    """
    Save QEB output to a JSON file.

    Args:
        output: QEBOutput instance
        output_dir: Directory to save to
        protocol_id: Protocol identifier

    Returns:
        Path to the saved file
    """
    import json
    from pathlib import Path

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{protocol_id}_qeb_output.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output.to_dict(), f, indent=2, ensure_ascii=False)

    return str(output_path)


def load_qeb_output(file_path) -> QEBOutput:
    """
    Load QEB output from a JSON file.

    Args:
        file_path: Path to the QEB output JSON file

    Returns:
        QEBOutput instance
    """
    import json
    from pathlib import Path

    file_path = Path(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Parse summary
    summary_data = data.get("summary", {})
    summary = QEBSummary(
        total_qebs=summary_data.get("totalQEBs", 0),
        inclusion_qebs=summary_data.get("inclusionQEBs", 0),
        exclusion_qebs=summary_data.get("exclusionQEBs", 0),
        fully_queryable=summary_data.get("fullyQueryable", 0),
        partially_queryable=summary_data.get("partiallyQueryable", 0),
        requires_manual_review=summary_data.get("requiresManualReview", 0),
        total_atomics_consolidated=summary_data.get("totalAtomicsConsolidated", 0),
        unique_omop_concepts=summary_data.get("uniqueOmopConcepts", 0),
        deduplication_rate=summary_data.get("deduplicationRate", 0.0),
        killer_criteria_count=summary_data.get("killerCriteriaCount", 0),
        funnel_stages_count=summary_data.get("funnelStagesCount", 0),
    )

    # Parse funnel stages
    funnel_stages = []
    for stage_data in data.get("funnelStages", []):
        funnel_stages.append(QEBFunnelStage(
            stage_id=stage_data.get("stageId", ""),
            stage_name=stage_data.get("stageName", ""),
            stage_order=stage_data.get("stageOrder", 0),
            qeb_ids=stage_data.get("qebIds", []),
            combined_elimination_rate=stage_data.get("combinedEliminationRate", 0.0),
            stage_description=stage_data.get("stageDescription"),
        ))

    # Parse QEBs
    queryable_blocks = []
    for qeb_data in data.get("queryableBlocks", []):
        # Parse OMOP concepts
        omop_concepts = []
        for c in qeb_data.get("omopConcepts", []):
            omop_concepts.append(OMOPConceptRef(
                concept_id=c.get("conceptId", 0),
                concept_name=c.get("conceptName", ""),
                domain_id=c.get("domain", ""),
                vocabulary_id=c.get("vocabularyId"),
                concept_code=c.get("conceptCode"),
            ))

        # Parse FHIR resources
        fhir_resources = []
        for r in qeb_data.get("fhirResources", []):
            fhir_resources.append(FHIRResourceRef(
                resource_type=r.get("resourceType", ""),
                search_params=r.get("searchParams", {}),
                description=r.get("description"),
            ))

        # Parse CDISC biomedical concepts
        biomedical_concepts = []
        for bc in qeb_data.get("biomedicalConcepts", []):
            biomedical_concepts.append(CDISCBiomedicalConcept(
                concept_name=bc.get("conceptName", ""),
                cdisc_code=bc.get("cdiscCode", "CUSTOM"),
                domain=bc.get("domain", "OTHER"),
                specimen=bc.get("specimen"),
                method=bc.get("method"),
                confidence=bc.get("confidence", 0.5),
                rationale=bc.get("rationale"),
                source_omop_concept_id=bc.get("sourceOmopConceptId"),
            ))

        # Parse provenance
        prov_data = qeb_data.get("provenance")
        provenance = None
        if prov_data:
            provenance = QEBProvenance(
                page_number=prov_data.get("pageNumber"),
                section_id=prov_data.get("sectionId"),
                text_snippet=prov_data.get("textSnippet"),
            )

        queryable_blocks.append(QueryableEligibilityBlock(
            qeb_id=qeb_data.get("qebId", ""),
            original_criterion_id=qeb_data.get("originalCriterionId", ""),
            criterion_type=qeb_data.get("criterionType", ""),
            clinical_name=qeb_data.get("clinicalName", ""),
            clinical_description=qeb_data.get("clinicalDescription", ""),
            clinical_category=qeb_data.get("clinicalCategory", ""),
            funnel_stage=qeb_data.get("funnelStage", ""),
            funnel_stage_order=qeb_data.get("funnelStageOrder", 0),
            combined_sql=qeb_data.get("combinedSql", ""),
            sql_logic_explanation=qeb_data.get("sqlLogicExplanation", ""),
            queryable_status=qeb_data.get("queryableStatus", ""),
            non_queryable_reason=qeb_data.get("nonQueryableReason"),
            estimated_elimination_rate=qeb_data.get("estimatedEliminationRate"),
            is_killer_criterion=qeb_data.get("isKillerCriterion", False),
            epidemiological_evidence=qeb_data.get("epidemiologicalEvidence"),
            atomic_ids=qeb_data.get("atomicIds", []),
            atomic_count=qeb_data.get("atomicCount", 0),
            internal_logic=qeb_data.get("internalLogic", "SIMPLE"),
            omop_concepts=omop_concepts,
            fhir_resources=fhir_resources,
            biomedical_concepts=biomedical_concepts,
            protocol_text=qeb_data.get("protocolText", ""),
            provenance=provenance,
        ))

    # Parse execution guide
    guide_data = data.get("executionGuide", {})
    execution_guide = QEBExecutionGuide(
        recommended_order=guide_data.get("recommendedOrder", []),
        killer_criteria=guide_data.get("killerCriteria", []),
        manual_review_required=guide_data.get("manualReviewRequired", []),
        execution_notes=guide_data.get("executionNotes"),
    )

    # Parse metadata
    metadata = data.get("processingMetadata", {})

    return QEBOutput(
        protocol_id=data.get("protocolId", ""),
        version=data.get("version", "1.0"),
        generated_at=data.get("generatedAt", ""),
        therapeutic_area=data.get("therapeuticArea"),
        summary=summary,
        funnel_stages=funnel_stages,
        queryable_blocks=queryable_blocks,
        execution_guide=execution_guide,
        atomic_criteria=data.get("atomicCriteria", []),
        logical_groups=data.get("logicalGroups", []),
        processing_time_seconds=metadata.get("processingTimeSeconds", 0.0),
        llm_model_used=metadata.get("llmModelUsed"),
        stage_inputs_used=metadata.get("stageInputsUsed", []),
        llm_warnings=metadata.get("llmWarnings", []),
    )
