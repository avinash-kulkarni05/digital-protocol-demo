"""
QEB Validation Data Models

Data structures for the Human-in-the-Loop QEB Validation System.
Supports validation sessions, classification overrides, OMOP corrections,
and funnel execution results.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Literal, Optional, Set, Any
from datetime import datetime
import json


# =============================================================================
# ATOMIC-LEVEL MODELS (Smallest unit of validation)
# =============================================================================

@dataclass
class AtomicWithClassification:
    """Single atomic criterion with queryability classification."""
    atomic_id: str
    text: str
    omop_concept_id: Optional[int]  # None if UNMAPPED
    omop_concept_name: Optional[str]
    classification: Literal["QUERYABLE", "SCREENING_ONLY", "NOT_APPLICABLE"]
    classification_confidence: float
    classification_reasoning: str
    is_unmapped: bool  # True if no OMOP concept found
    qeb_id: Optional[str] = None  # Parent QEB reference

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "atomicId": self.atomic_id,
            "text": self.text,
            "omopConceptId": self.omop_concept_id,
            "omopConceptName": self.omop_concept_name,
            "classification": self.classification,
            "classificationConfidence": self.classification_confidence,
            "classificationReasoning": self.classification_reasoning,
            "isUnmapped": self.is_unmapped,
            "qebId": self.qeb_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AtomicWithClassification":
        """Create from dictionary."""
        return cls(
            atomic_id=data.get("atomicId", ""),
            text=data.get("text", ""),
            omop_concept_id=data.get("omopConceptId"),
            omop_concept_name=data.get("omopConceptName"),
            classification=data.get("classification", "SCREENING_ONLY"),
            classification_confidence=data.get("classificationConfidence", 0.0),
            classification_reasoning=data.get("classificationReasoning", ""),
            is_unmapped=data.get("isUnmapped", True),
            qeb_id=data.get("qebId"),
        )


@dataclass
class ClassificationOverride:
    """User override to LLM's classification."""
    atomic_id: str
    original_category: Literal["QUERYABLE", "SCREENING_ONLY", "NOT_APPLICABLE"]
    new_category: Literal["QUERYABLE", "SCREENING_ONLY", "NOT_APPLICABLE"]
    justification: str
    overridden_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "atomicId": self.atomic_id,
            "originalCategory": self.original_category,
            "newCategory": self.new_category,
            "justification": self.justification,
            "overriddenAt": self.overridden_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassificationOverride":
        """Create from dictionary."""
        return cls(
            atomic_id=data.get("atomicId", ""),
            original_category=data.get("originalCategory", "SCREENING_ONLY"),
            new_category=data.get("newCategory", "SCREENING_ONLY"),
            justification=data.get("justification", ""),
            overridden_at=datetime.fromisoformat(data["overriddenAt"]) if data.get("overriddenAt") else datetime.utcnow(),
        )


@dataclass
class OMOPCorrection:
    """User-provided OMOP mapping for unmapped term."""
    atomic_id: str
    original_term: str
    selected_concept_id: int
    selected_concept_name: str
    domain: str  # Condition, Drug, Measurement, Procedure
    corrected_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "atomicId": self.atomic_id,
            "originalTerm": self.original_term,
            "selectedConceptId": self.selected_concept_id,
            "selectedConceptName": self.selected_concept_name,
            "domain": self.domain,
            "correctedAt": self.corrected_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OMOPCorrection":
        """Create from dictionary."""
        return cls(
            atomic_id=data.get("atomicId", ""),
            original_term=data.get("originalTerm", ""),
            selected_concept_id=data.get("selectedConceptId", 0),
            selected_concept_name=data.get("selectedConceptName", ""),
            domain=data.get("domain", ""),
            corrected_at=datetime.fromisoformat(data["correctedAt"]) if data.get("correctedAt") else datetime.utcnow(),
        )


# =============================================================================
# QEB-LEVEL MODELS
# =============================================================================

@dataclass
class QEBClassificationSummary:
    """Aggregated classification for a single QEB."""
    qeb_id: str
    criterion_type: Literal["inclusion", "exclusion"]
    criterion_text: str
    total_atomics: int
    queryable_count: int
    screening_only_count: int
    not_applicable_count: int
    unmapped_count: int
    is_queryable: bool  # True if any atomic is QUERYABLE
    is_killer: bool  # High elimination rate
    funnel_stage: int  # 1-8
    elimination_estimate: Optional[float] = None  # LLM-estimated elimination rate

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "qebId": self.qeb_id,
            "criterionType": self.criterion_type,
            "criterionText": self.criterion_text,
            "totalAtomics": self.total_atomics,
            "queryableCount": self.queryable_count,
            "screeningOnlyCount": self.screening_only_count,
            "notApplicableCount": self.not_applicable_count,
            "unmappedCount": self.unmapped_count,
            "isQueryable": self.is_queryable,
            "isKiller": self.is_killer,
            "funnelStage": self.funnel_stage,
            "eliminationEstimate": self.elimination_estimate,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QEBClassificationSummary":
        """Create from dictionary."""
        return cls(
            qeb_id=data.get("qebId", ""),
            criterion_type=data.get("criterionType", "inclusion"),
            criterion_text=data.get("criterionText", ""),
            total_atomics=data.get("totalAtomics", 0),
            queryable_count=data.get("queryableCount", 0),
            screening_only_count=data.get("screeningOnlyCount", 0),
            not_applicable_count=data.get("notApplicableCount", 0),
            unmapped_count=data.get("unmappedCount", 0),
            is_queryable=data.get("isQueryable", False),
            is_killer=data.get("isKiller", False),
            funnel_stage=data.get("funnelStage", 1),
            elimination_estimate=data.get("eliminationEstimate"),
        )


# =============================================================================
# SESSION-LEVEL MODELS
# =============================================================================

@dataclass
class ClassificationSummary:
    """Protocol-wide classification summary (what user sees first)."""
    total_atomics: int
    queryable_atomics: int
    screening_only_atomics: int
    not_applicable_atomics: int
    unmapped_atomics: int
    killer_criteria_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "totalAtomics": self.total_atomics,
            "queryableAtomics": self.queryable_atomics,
            "screeningOnlyAtomics": self.screening_only_atomics,
            "notApplicableAtomics": self.not_applicable_atomics,
            "unmappedAtomics": self.unmapped_atomics,
            "killerCriteriaCount": self.killer_criteria_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassificationSummary":
        """Create from dictionary."""
        return cls(
            total_atomics=data.get("totalAtomics", 0),
            queryable_atomics=data.get("queryableAtomics", 0),
            screening_only_atomics=data.get("screeningOnlyAtomics", 0),
            not_applicable_atomics=data.get("notApplicableAtomics", 0),
            unmapped_atomics=data.get("unmappedAtomics", 0),
            killer_criteria_count=data.get("killerCriteriaCount", 0),
        )


@dataclass
class FunnelStageConfig:
    """Configuration for a single funnel stage."""
    stage_number: int  # 1-8
    stage_name: str  # e.g., "Disease Indication", "Demographics"
    inclusion_qeb_ids: List[str] = field(default_factory=list)
    exclusion_qeb_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "stageNumber": self.stage_number,
            "stageName": self.stage_name,
            "inclusionQebIds": self.inclusion_qeb_ids,
            "exclusionQebIds": self.exclusion_qeb_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FunnelStageConfig":
        """Create from dictionary."""
        return cls(
            stage_number=data.get("stageNumber", 1),
            stage_name=data.get("stageName", ""),
            inclusion_qeb_ids=data.get("inclusionQebIds", []),
            exclusion_qeb_ids=data.get("exclusionQebIds", []),
        )


@dataclass
class ValidationSession:
    """Entire validation session state."""
    session_id: str
    protocol_id: str
    protocol_name: str
    qeb_output_path: str

    # Classification state
    llm_recommendation_accepted: bool = False
    classification_overrides: List[ClassificationOverride] = field(default_factory=list)
    omop_corrections: List[OMOPCorrection] = field(default_factory=list)

    # Funnel configuration (8 stages)
    funnel_stages: List[FunnelStageConfig] = field(default_factory=list)

    # Execution results (filled after execution)
    execution_result: Optional["FunnelExecutionResult"] = None

    # Audit
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sessionId": self.session_id,
            "protocolId": self.protocol_id,
            "protocolName": self.protocol_name,
            "qebOutputPath": self.qeb_output_path,
            "llmRecommendationAccepted": self.llm_recommendation_accepted,
            "classificationOverrides": [o.to_dict() for o in self.classification_overrides],
            "omopCorrections": [c.to_dict() for c in self.omop_corrections],
            "funnelStages": [s.to_dict() for s in self.funnel_stages],
            "executionResult": self.execution_result.to_dict() if self.execution_result else None,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationSession":
        """Create from dictionary."""
        return cls(
            session_id=data.get("sessionId", ""),
            protocol_id=data.get("protocolId", ""),
            protocol_name=data.get("protocolName", ""),
            qeb_output_path=data.get("qebOutputPath", ""),
            llm_recommendation_accepted=data.get("llmRecommendationAccepted", False),
            classification_overrides=[
                ClassificationOverride.from_dict(o) for o in data.get("classificationOverrides", [])
            ],
            omop_corrections=[
                OMOPCorrection.from_dict(c) for c in data.get("omopCorrections", [])
            ],
            funnel_stages=[
                FunnelStageConfig.from_dict(s) for s in data.get("funnelStages", [])
            ],
            execution_result=FunnelExecutionResult.from_dict(data["executionResult"]) if data.get("executionResult") else None,
            created_at=datetime.fromisoformat(data["createdAt"]) if data.get("createdAt") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updatedAt"]) if data.get("updatedAt") else datetime.utcnow(),
            completed_at=datetime.fromisoformat(data["completedAt"]) if data.get("completedAt") else None,
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "ValidationSession":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


# =============================================================================
# EXECUTION MODELS
# =============================================================================

@dataclass
class QEBExecutionResult:
    """Result from executing a single QEB."""
    qeb_id: str
    criterion_text: str
    patients_before: int
    patients_after: int
    sql_executed: str
    was_skipped: bool  # True if all atomics are SCREENING_ONLY
    matching_patient_ids: Set[int] = field(default_factory=set)  # Patients matching this QEB

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "qebId": self.qeb_id,
            "criterionText": self.criterion_text,
            "patientsBefore": self.patients_before,
            "patientsAfter": self.patients_after,
            "sqlExecuted": self.sql_executed,
            "wasSkipped": self.was_skipped,
            # Note: matching_patient_ids not serialized to avoid huge JSON files
            "matchingPatientCount": len(self.matching_patient_ids),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QEBExecutionResult":
        """Create from dictionary."""
        return cls(
            qeb_id=data.get("qebId", ""),
            criterion_text=data.get("criterionText", ""),
            patients_before=data.get("patientsBefore", 0),
            patients_after=data.get("patientsAfter", 0),
            sql_executed=data.get("sqlExecuted", ""),
            was_skipped=data.get("wasSkipped", False),
            matching_patient_ids=set(),  # Not deserialized from JSON
        )


@dataclass
class FunnelStageResult:
    """Result from executing a single funnel stage."""
    stage_number: int
    stage_name: str
    patients_entering: int
    patients_exiting: int
    elimination_rate: float
    qeb_results: List[QEBExecutionResult] = field(default_factory=list)
    remaining_patient_ids: Set[int] = field(default_factory=set)  # For chaining stages

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "stageNumber": self.stage_number,
            "stageName": self.stage_name,
            "patientsEntering": self.patients_entering,
            "patientsExiting": self.patients_exiting,
            "eliminationRate": self.elimination_rate,
            "qebResults": [r.to_dict() for r in self.qeb_results],
            # Note: remaining_patient_ids not serialized
            "remainingPatientCount": len(self.remaining_patient_ids),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FunnelStageResult":
        """Create from dictionary."""
        return cls(
            stage_number=data.get("stageNumber", 0),
            stage_name=data.get("stageName", ""),
            patients_entering=data.get("patientsEntering", 0),
            patients_exiting=data.get("patientsExiting", 0),
            elimination_rate=data.get("eliminationRate", 0.0),
            qeb_results=[QEBExecutionResult.from_dict(r) for r in data.get("qebResults", [])],
            remaining_patient_ids=set(),  # Not deserialized from JSON
        )


@dataclass
class FunnelExecutionResult:
    """Complete funnel execution results."""
    session_id: str
    executed_at: datetime
    database_name: str
    base_population: int
    final_population: int
    overall_elimination_rate: float
    stage_results: List[FunnelStageResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sessionId": self.session_id,
            "executedAt": self.executed_at.isoformat(),
            "databaseName": self.database_name,
            "basePopulation": self.base_population,
            "finalPopulation": self.final_population,
            "overallEliminationRate": self.overall_elimination_rate,
            "stageResults": [s.to_dict() for s in self.stage_results],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FunnelExecutionResult":
        """Create from dictionary."""
        return cls(
            session_id=data.get("sessionId", ""),
            executed_at=datetime.fromisoformat(data["executedAt"]) if data.get("executedAt") else datetime.utcnow(),
            database_name=data.get("databaseName", ""),
            base_population=data.get("basePopulation", 0),
            final_population=data.get("finalPopulation", 0),
            overall_elimination_rate=data.get("overallEliminationRate", 0.0),
            stage_results=[FunnelStageResult.from_dict(s) for s in data.get("stageResults", [])],
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "FunnelExecutionResult":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))
