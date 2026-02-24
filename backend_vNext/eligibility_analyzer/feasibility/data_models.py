"""
Data models for the Patient Funnel & Key Criteria Normalization System.

This module defines all dataclasses used for:
- Criterion categorization and queryability assessment
- Key criteria normalization
- Funnel stage tracking
- Population estimation and site ranking
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime


class CriterionCategory(Enum):
    """
    Classification of eligibility criteria by clinical impact.

    Categories are ordered by typical application sequence in the patient funnel,
    with high-elimination categories applied first.
    """
    PRIMARY_ANCHOR = "primary_anchor"        # Disease + demographics (applied FIRST, ~95% elimination)
    BIOMARKER = "biomarker"                  # Genetic markers, receptor status (5-30% of remaining)
    TREATMENT_HISTORY = "treatment_history"  # Prior lines, washout periods
    FUNCTIONAL = "functional"                # ECOG, organ function labs (~20-30%)
    SAFETY_EXCLUSION = "safety_exclusion"    # Contraindications, comorbidities (~10-20%)
    ADMINISTRATIVE = "administrative"        # Consent, compliance (NON-QUERYABLE)


class QueryableStatus(Enum):
    """
    Assessment of whether a criterion can be queried against EHR/claims data.

    This drives the estimation strategy:
    - FULLY_QUERYABLE: Execute SQL, get exact counts
    - PARTIALLY_QUERYABLE: Some aspects queryable, others need prevalence
    - NON_QUERYABLE: Requires manual chart review (flagged for human assessment)
    - REFERENCE_BASED: Use published prevalence data only
    """
    FULLY_QUERYABLE = "fully_queryable"           # Direct SQL against EHR
    PARTIALLY_QUERYABLE = "partially_queryable"   # Some aspects queryable
    NON_QUERYABLE = "non_queryable"               # Manual chart review required
    REFERENCE_BASED = "reference_based"           # Use prevalence data only


class FunnelStageType(Enum):
    """
    Standard funnel stage types matching clinical feasibility methodology.

    Stages are executed in this order for optimal elimination efficiency:
    1. Disease Indication - Maximum population reduction first
    2. Demographics - Age, gender filters
    3. Biomarker Requirements - Known population frequencies
    4. Treatment History - Line of therapy, washout
    5. Performance Status - ECOG/Karnofsky
    6. Lab Criteria - ANC, platelets, creatinine clearance
    7. Safety Exclusions - CNS, cardiac, infections
    """
    DISEASE_INDICATION = "disease_indication"
    DEMOGRAPHICS = "demographics"
    BIOMARKER_REQUIREMENTS = "biomarker_requirements"
    TREATMENT_HISTORY = "treatment_history"
    PERFORMANCE_STATUS = "performance_status"
    LAB_CRITERIA = "lab_criteria"
    SAFETY_EXCLUSIONS = "safety_exclusions"


@dataclass
class PrevalenceEstimate:
    """
    Published prevalence data for a condition or biomarker.

    Used when direct querying is not possible or to validate query results.
    """
    frequency: float                    # 0.0 to 1.0 (proportion)
    source: str                         # Citation (e.g., "AACR 2023", "NCCN 2024")
    year: Optional[int] = None          # Publication year
    population: Optional[str] = None    # Target population (e.g., "NSCLC patients")
    confidence_low: Optional[float] = None   # Lower bound of CI
    confidence_high: Optional[float] = None  # Upper bound of CI
    notes: Optional[str] = None         # Additional context


@dataclass
class OmopMapping:
    """
    OMOP CDM concept mapping for a criterion.

    Links criterion to standard vocabulary concepts for querying.
    """
    concept_id: int                     # OMOP concept_id
    concept_name: str                   # Human-readable name
    vocabulary_id: str                  # e.g., "SNOMED", "LOINC", "RxNorm"
    domain_id: str                      # e.g., "Condition", "Measurement", "Drug"
    table_name: str                     # Target OMOP table
    is_standard: bool = True            # Standard vs source concept


@dataclass
class FhirMapping:
    """
    FHIR R4 resource mapping for a criterion.

    Links criterion to FHIR resources and search parameters.
    """
    resource_type: str                  # e.g., "Condition", "Observation"
    code_system: str                    # e.g., "http://snomed.info/sct"
    code: str                           # The actual code value
    display: Optional[str] = None       # Human-readable display
    search_parameter: Optional[str] = None  # FHIR search param (e.g., "code")


@dataclass
class KeyCriterion:
    """
    A normalized, prioritized criterion for the patient funnel.

    Key criteria represent the ~10-15 criteria that drive 80% of patient
    elimination. Each criterion includes:
    - Normalized text and categorization
    - SQL/FHIR query templates
    - Queryability assessment
    - Elimination rate estimates
    """
    key_id: str                                     # Unique identifier (e.g., "KC001")
    original_criterion_ids: List[str]               # Source criterion IDs from extraction
    category: CriterionCategory                     # Classification category
    normalized_text: str                            # Standardized criterion description
    criterion_type: str                             # e.g., "inclusion" or "exclusion"

    # Query information
    queryable_status: QueryableStatus               # How queryable is this criterion
    normalized_query_omop: Optional[str] = None     # OMOP SQL template
    normalized_query_fhir: Optional[str] = None     # FHIR search query
    omop_mappings: List[OmopMapping] = field(default_factory=list)
    fhir_mappings: List[FhirMapping] = field(default_factory=list)

    # Estimation
    estimated_elimination_rate: float = 0.0         # 0-100%, expected patient drop-off
    prevalence_estimate: Optional[PrevalenceEstimate] = None
    data_availability_score: float = 0.0            # 0-1, how complete is EHR data

    # Flags
    requires_manual_assessment: bool = False        # Needs human chart review
    is_killer_criterion: bool = False               # Top 5-8 eliminators
    funnel_priority: int = 0                        # Order in funnel (lower = earlier)

    # Provenance
    source_text: Optional[str] = None               # Original criterion text
    atomic_ids: List[str] = field(default_factory=list)  # Related atomic criterion IDs

    def __post_init__(self):
        """Ensure lists are initialized."""
        if self.omop_mappings is None:
            self.omop_mappings = []
        if self.fhir_mappings is None:
            self.fhir_mappings = []
        if self.atomic_ids is None:
            self.atomic_ids = []


@dataclass
class CriterionMatch:
    """
    Result of matching a criterion against patient data.

    Used during funnel execution to track counts at each criterion.
    """
    criterion_id: str                   # Key criterion ID
    patients_matching: int              # Count of patients matching
    patients_not_matching: int          # Count not matching
    query_executed: bool                # Was a query run, or prevalence-based
    execution_time_ms: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class FunnelStage:
    """
    A stage in the patient funnel.

    Each stage groups related criteria and tracks patient flow through.
    Stages are executed in order, with each reducing the patient pool.
    """
    stage_name: str                     # e.g., "Disease Indication"
    stage_type: FunnelStageType         # Stage classification
    stage_order: int                    # Execution order (1-based)
    criteria: List[KeyCriterion]        # Criteria applied at this stage

    # Patient counts
    patients_entering: int = 0          # Patients at start of stage
    patients_exiting: int = 0           # Patients remaining after stage

    # Derived metrics (calculated after execution)
    elimination_rate: float = 0.0       # Percentage eliminated at this stage
    cumulative_elimination: float = 0.0 # Total eliminated from initial population

    # Execution tracking
    criterion_matches: List[CriterionMatch] = field(default_factory=list)
    execution_time_ms: Optional[float] = None

    def calculate_elimination_rate(self) -> float:
        """Calculate the elimination rate for this stage."""
        if self.patients_entering > 0:
            eliminated = self.patients_entering - self.patients_exiting
            self.elimination_rate = (eliminated / self.patients_entering) * 100
        else:
            self.elimination_rate = 0.0
        return self.elimination_rate


@dataclass
class PopulationEstimate:
    """
    Population estimate with confidence intervals.

    Represents the estimated patient pool at various funnel points.
    """
    count: int                          # Point estimate
    confidence_low: int                 # Lower bound (e.g., 5th percentile)
    confidence_high: int                # Upper bound (e.g., 95th percentile)
    estimation_method: str              # "query", "prevalence", or "hybrid"
    data_sources: List[str] = field(default_factory=list)  # Sources used
    notes: Optional[str] = None


@dataclass
class OptimizationOpportunity:
    """
    A protocol optimization suggestion based on funnel analysis.

    Identifies criteria modifications that could improve enrollment.
    """
    criterion_id: str                   # Key criterion to modify
    criterion_text: str                 # Current criterion text
    suggestion: str                     # Recommended change
    rationale: str                      # Clinical rationale
    potential_impact_percent: float     # Estimated pool increase (0-100)
    risk_assessment: str                # Safety/efficacy risk of change
    supporting_evidence: Optional[str] = None  # Literature or data support


@dataclass
class SiteRanking:
    """
    Feasibility ranking for a clinical trial site.

    Aggregates patient funnel results for site comparison.
    """
    site_id: str                        # Site identifier
    site_name: str                      # Human-readable name

    # Population metrics
    initial_population: int             # Total patients at site
    final_eligible_estimate: PopulationEstimate

    # Ranking
    rank: int                           # Overall rank (1 = best)
    score: float                        # Composite score (0-100)

    # Breakdown by stage
    stage_counts: Dict[str, int] = field(default_factory=dict)

    # Data quality
    data_completeness_score: float = 0.0  # 0-1, how complete is site data
    queryable_criteria_percent: float = 0.0  # % of criteria directly queryable

    # Notes
    strengths: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)


@dataclass
class FunnelResult:
    """
    Complete patient funnel analysis result.

    This is the primary output of the feasibility analysis, containing:
    - Selected key criteria (~10-15)
    - Ordered funnel stages with patient counts
    - Population estimates
    - Protocol optimization opportunities
    - Site rankings (if multi-site data provided)
    """
    # Metadata
    protocol_id: str
    analysis_timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    is_draft: bool = True

    # Key criteria
    key_criteria: List[KeyCriterion] = field(default_factory=list)
    total_criteria_analyzed: int = 0

    # Funnel stages
    stages: List[FunnelStage] = field(default_factory=list)

    # Population estimates
    initial_population: int = 0
    final_eligible_estimate: Optional[PopulationEstimate] = None

    # Insights
    killer_criteria: List[str] = field(default_factory=list)  # Top 5-8 eliminators by ID
    optimization_opportunities: List[OptimizationOpportunity] = field(default_factory=list)
    manual_assessment_criteria: List[str] = field(default_factory=list)  # Non-queryable IDs

    # Site rankings (optional, if multi-site)
    site_rankings: List[SiteRanking] = field(default_factory=list)

    # Quality metrics
    data_source: str = "unknown"        # "omop", "fhir", "synthetic", "hybrid"
    data_quality_score: float = 0.0     # 0-1, overall data quality
    estimation_confidence: str = "low"  # "high", "medium", "low"

    # Execution metadata
    execution_time_seconds: float = 0.0
    stages_executed: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def get_overall_elimination_rate(self) -> float:
        """Calculate total elimination from initial to final."""
        if self.initial_population > 0 and self.final_eligible_estimate:
            eliminated = self.initial_population - self.final_eligible_estimate.count
            return (eliminated / self.initial_population) * 100
        return 0.0

    def get_funnel_efficiency_score(self) -> float:
        """
        Score how well the funnel prioritizes high-impact criteria.

        Higher score = killer criteria applied earlier in funnel.
        """
        if not self.stages or not self.killer_criteria:
            return 0.0

        # Check if killer criteria are in early stages
        killer_in_early_stages = 0
        for stage in self.stages[:3]:  # First 3 stages
            for criterion in stage.criteria:
                if criterion.key_id in self.killer_criteria:
                    killer_in_early_stages += 1

        return min(100.0, (killer_in_early_stages / len(self.killer_criteria)) * 100)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "protocolId": self.protocol_id,
            "analysisTimestamp": self.analysis_timestamp,
            "isDraft": self.is_draft,
            "keyCriteria": [
                {
                    "keyId": kc.key_id,
                    "category": kc.category.value,
                    "normalizedText": kc.normalized_text,
                    "criterionType": kc.criterion_type,
                    "queryableStatus": kc.queryable_status.value,
                    "estimatedEliminationRate": kc.estimated_elimination_rate,
                    "requiresManualAssessment": kc.requires_manual_assessment,
                    "isKillerCriterion": kc.is_killer_criterion,
                    "funnelPriority": kc.funnel_priority,
                    "omopMappings": [
                        {
                            "conceptId": m.concept_id,
                            "conceptName": m.concept_name,
                            "vocabularyId": m.vocabulary_id,
                            "domainId": m.domain_id,
                            "tableName": m.table_name
                        } for m in kc.omop_mappings
                    ] if kc.omop_mappings else []
                } for kc in self.key_criteria
            ],
            "funnelStages": [
                {
                    "stageName": stage.stage_name,
                    "stageType": stage.stage_type.value,
                    "stageOrder": stage.stage_order,
                    "patientsEntering": stage.patients_entering,
                    "patientsExiting": stage.patients_exiting,
                    "eliminationRate": stage.elimination_rate,
                    "cumulativeElimination": stage.cumulative_elimination,
                    "criteriaCount": len(stage.criteria)
                } for stage in self.stages
            ],
            "populationEstimates": {
                "initialPopulation": self.initial_population,
                "finalEligibleEstimate": self.final_eligible_estimate.count if self.final_eligible_estimate else 0,
                "confidenceInterval": {
                    "low": self.final_eligible_estimate.confidence_low if self.final_eligible_estimate else 0,
                    "high": self.final_eligible_estimate.confidence_high if self.final_eligible_estimate else 0
                },
                "estimationMethod": self.final_eligible_estimate.estimation_method if self.final_eligible_estimate else "unknown"
            },
            "killerCriteria": self.killer_criteria,
            "optimizationOpportunities": [
                {
                    "criterionId": opp.criterion_id,
                    "criterionText": opp.criterion_text,
                    "suggestion": opp.suggestion,
                    "rationale": opp.rationale,
                    "potentialImpact": opp.potential_impact_percent,
                    "riskAssessment": opp.risk_assessment
                } for opp in self.optimization_opportunities
            ],
            "manualAssessmentCriteria": self.manual_assessment_criteria,
            "siteRankings": [
                {
                    "siteId": site.site_id,
                    "siteName": site.site_name,
                    "rank": site.rank,
                    "score": site.score,
                    "eligiblePatients": site.final_eligible_estimate.count if site.final_eligible_estimate else 0,
                    "dataCompletenessScore": site.data_completeness_score
                } for site in self.site_rankings
            ],
            "metadata": {
                "dataSource": self.data_source,
                "dataQualityScore": self.data_quality_score,
                "estimationConfidence": self.estimation_confidence,
                "executionTimeSeconds": self.execution_time_seconds,
                "stagesExecuted": self.stages_executed,
                "totalCriteriaAnalyzed": self.total_criteria_analyzed,
                "overallEliminationRate": self.get_overall_elimination_rate(),
                "funnelEfficiencyScore": self.get_funnel_efficiency_score()
            },
            "errors": self.errors,
            "warnings": self.warnings
        }


# Type aliases for convenience
KeyCriteriaList = List[KeyCriterion]
FunnelStageList = List[FunnelStage]


# =============================================================================
# V2 DATA MODELS: Queryable Funnel with Atomic Criteria
# =============================================================================


@dataclass
class FhirCode:
    """Individual FHIR code within a code system."""
    system: str                     # e.g., "http://snomed.info/sct"
    code: str                       # The actual code value
    display: str                    # Human-readable display

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system": self.system,
            "code": self.code,
            "display": self.display,
        }


@dataclass
class OmopQuerySpec:
    """
    OMOP CDM SQL query specification for a criterion.

    Contains everything needed to execute against an OMOP database.
    """
    table_name: str                             # Target OMOP table
    concept_ids: List[int]                      # OMOP concept IDs
    concept_names: List[str]                    # Human-readable names
    vocabulary_ids: List[str]                   # Source vocabularies
    sql_template: str                           # Executable SQL
    sql_executable: bool = True                 # Is this fully queryable?

    # Additional query components
    value_constraint: Optional[str] = None      # e.g., "value_as_number >= 18"
    time_constraint: Optional[str] = None       # e.g., "condition_start_date >= @ref - 28 days"

    # For criteria that couldn't be fully mapped
    unmapped_reason: Optional[str] = None       # Why not fully queryable

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "tableName": self.table_name,
            "conceptIds": self.concept_ids,
            "conceptNames": self.concept_names,
            "vocabularyIds": self.vocabulary_ids,
            "sqlTemplate": self.sql_template,
            "sqlExecutable": self.sql_executable,
        }
        if self.value_constraint:
            result["valueConstraint"] = self.value_constraint
        if self.time_constraint:
            result["timeConstraint"] = self.time_constraint
        if self.unmapped_reason:
            result["unmappedReason"] = self.unmapped_reason
        return result


@dataclass
class FhirQuerySpec:
    """
    FHIR R4 query specification for a criterion.

    Contains everything needed to execute against a FHIR server.
    """
    resource_type: str                          # e.g., "Observation", "Condition"
    codes: List[FhirCode]                       # FHIR codes to search
    search_params: str                          # FHIR search parameter string
    query_executable: bool = True               # Is this fully queryable?

    # For criteria that couldn't be fully mapped
    unmapped_reason: Optional[str] = None       # Why not fully queryable

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "resourceType": self.resource_type,
            "codes": [c.to_dict() for c in self.codes],
            "searchParams": self.search_params,
            "queryExecutable": self.query_executable,
        }
        if self.unmapped_reason:
            result["unmappedReason"] = self.unmapped_reason
        return result


@dataclass
class FunnelImpact:
    """Impact assessment for a criterion in the patient funnel."""
    elimination_rate: float                     # 0-100%, expected drop-off
    impact_score: float                         # 0-1, normalized impact
    is_killer_criterion: bool                   # Top 5-8 eliminators

    # Source of estimate
    estimation_method: str = "prevalence"       # "query", "prevalence", "model"
    confidence: float = 0.8                     # 0-1, estimate confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eliminationRate": self.elimination_rate,
            "impactScore": self.impact_score,
            "isKillerCriterion": self.is_killer_criterion,
            "estimationMethod": self.estimation_method,
            "confidence": self.confidence,
        }


@dataclass
class AtomicProvenance:
    """Source document provenance for an atomic criterion."""
    page_number: int
    text_snippet: str
    confidence: float = 1.0
    original_criterion_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "pageNumber": self.page_number,
            "textSnippet": self.text_snippet,
            "confidence": self.confidence,
        }
        if self.original_criterion_id:
            result["originalCriterionId"] = self.original_criterion_id
        return result


@dataclass
class ExecutionContext:
    """
    Execution context for incremental funnel building.

    Tells the external UX how to combine this criterion with others
    when building the patient funnel incrementally.
    """
    logical_group: str                          # Group ID (e.g., "ECOG_STATUS")
    group_logic: str                            # AND/OR within group
    combine_with_previous: str                  # AND/OR/NOT with prior results
    is_exclusion: bool                          # Is this an exclusion criterion?
    sequence_hint: int                          # Suggested order in funnel

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logicalGroup": self.logical_group,
            "groupLogic": self.group_logic,
            "combineWithPrevious": self.combine_with_previous,
            "isExclusion": self.is_exclusion,
            "sequenceHint": self.sequence_hint,
        }


@dataclass
class AtomicCriterion:
    """
    A single, atomically queryable eligibility criterion.

    This is the fundamental unit for the patient funnel:
    - One testable condition
    - Tied to executable OMOP SQL
    - Tied to executable FHIR query
    - Knows how to combine with other atoms (AND/OR/NOT)
    """
    atomic_id: str                              # Unique ID (e.g., "A001")
    original_criterion_id: str                  # Source criterion ID
    criterion_type: str                         # "inclusion" or "exclusion"

    # Text representations
    atomic_text: str                            # Single condition text
    normalized_text: str                        # Standardized form

    # Clinical categorization
    category: str                               # e.g., "demographics", "disease_indication"

    # Impact assessment
    funnel_impact: FunnelImpact

    # Query specifications
    omop_query: Optional[OmopQuerySpec] = None
    fhir_query: Optional[FhirQuerySpec] = None

    # Execution context
    execution_context: Optional[ExecutionContext] = None

    # Provenance
    provenance: Optional[AtomicProvenance] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "atomicId": self.atomic_id,
            "originalCriterionId": self.original_criterion_id,
            "criterionType": self.criterion_type,
            "atomicText": self.atomic_text,
            "normalizedText": self.normalized_text,
            "category": self.category,
            "funnelImpact": self.funnel_impact.to_dict(),
        }
        if self.omop_query:
            result["omopQuery"] = self.omop_query.to_dict()
        if self.fhir_query:
            result["fhirQuery"] = self.fhir_query.to_dict()
        if self.execution_context:
            result["executionContext"] = self.execution_context.to_dict()
        if self.provenance:
            result["provenance"] = self.provenance.to_dict()
        return result


@dataclass
class LogicalGroup:
    """
    A group of atoms with defined internal and external logic.

    Enables correct combination when building funnel incrementally:
    - Atoms within group combined by internalLogic (e.g., OR for ECOG 0 OR ECOG 1)
    - Group result combined with others by combineWithOthers (e.g., AND)
    """
    group_id: str                               # Unique group ID
    group_label: str                            # Human-readable label
    internal_logic: str                         # AND/OR within group
    combine_with_others: str                    # AND/OR/NOT with other groups
    is_exclusion: bool                          # Is this an exclusion group?
    atomic_ids: List[str]                       # Atoms in this group
    sequence_order: int = 0                     # Suggested execution order

    def to_dict(self) -> Dict[str, Any]:
        return {
            "groupId": self.group_id,
            "groupLabel": self.group_label,
            "internalLogic": self.internal_logic,
            "combineWithOthers": self.combine_with_others,
            "isExclusion": self.is_exclusion,
            "atomicIds": self.atomic_ids,
            "sequenceOrder": self.sequence_order,
        }


@dataclass
class QueryableFunnelStage:
    """A stage in the queryable funnel."""
    stage_id: str
    stage_name: str
    stage_order: int
    stage_logic: str                            # AND/OR for criteria in stage
    criteria_ids: List[str]                     # Atomic IDs in this stage

    # Results (populated after execution)
    patients_entering: Optional[int] = None
    patients_exiting: Optional[int] = None
    elimination_rate: Optional[float] = None
    executed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "stageId": self.stage_id,
            "stageName": self.stage_name,
            "stageOrder": self.stage_order,
            "stageLogic": self.stage_logic,
            "criteriaIds": self.criteria_ids,
            "results": {
                "patientsEntering": self.patients_entering,
                "patientsExiting": self.patients_exiting,
                "eliminationRate": self.elimination_rate,
                "executedAt": self.executed_at,
            }
        }
        return result


@dataclass
class QueryableFunnelResult:
    """
    V2 Queryable Funnel Result with atomic criteria.

    This is the new output format that supports:
    - Atomic criteria with OMOP SQL and FHIR queries
    - Logical groups for boolean combination
    - Expression tree preservation
    - Incremental funnel building by external UX
    """
    # Metadata
    protocol_id: str
    version: str = "2.0"
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    is_draft: bool = True

    # Atomic criteria (all queryable atoms)
    atomic_criteria: List[AtomicCriterion] = field(default_factory=list)

    # Logical groups (how atoms combine)
    logical_groups: List[LogicalGroup] = field(default_factory=list)

    # Expression tree (full boolean structure, serialized)
    expression_tree: Optional[Dict[str, Any]] = None

    # Funnel stages (ordered execution)
    funnel_stages: List[QueryableFunnelStage] = field(default_factory=list)

    # Summary statistics
    total_atoms: int = 0
    queryable_atoms: int = 0
    killer_criteria: List[str] = field(default_factory=list)
    manual_assessment_criteria: List[str] = field(default_factory=list)

    # Population estimates (synthetic/prevalence-based)
    initial_population_estimate: int = 0
    final_eligible_estimate: int = 0

    # Metadata
    data_source: str = "synthetic"
    execution_time_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocolId": self.protocol_id,
            "version": self.version,
            "generatedAt": self.generated_at,
            "isDraft": self.is_draft,
            "atomicCriteria": [ac.to_dict() for ac in self.atomic_criteria],
            "logicalGroups": [lg.to_dict() for lg in self.logical_groups],
            "expressionTree": self.expression_tree,
            "funnelStages": [fs.to_dict() for fs in self.funnel_stages],
            "summary": {
                "totalAtoms": self.total_atoms,
                "queryableAtoms": self.queryable_atoms,
                "killerCriteria": self.killer_criteria,
                "manualAssessmentCriteria": self.manual_assessment_criteria,
            },
            "populationEstimates": {
                "initialPopulation": self.initial_population_estimate,
                "finalEligibleEstimate": self.final_eligible_estimate,
            },
            "metadata": {
                "dataSource": self.data_source,
                "executionTimeSeconds": self.execution_time_seconds,
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }
