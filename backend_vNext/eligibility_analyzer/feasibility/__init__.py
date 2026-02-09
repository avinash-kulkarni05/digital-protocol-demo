"""
Feasibility Module - Patient Funnel & Key Criteria Normalization System.

This module provides site feasibility assessment by normalizing eligibility
criteria into ~10-15 "key criteria" that drive 80% of patient elimination.

Key components:
- data_models: Dataclasses for criteria, funnel stages, and results
- criterion_classifier: LLM-based criterion categorization
- key_criteria_normalizer: Normalize criteria to key set
- eligibility_funnel_builder: Main funnel builder with OMOP/FHIR queries
- population_estimator: Prevalence-based population estimates
- llm_atomic_matcher: LLM-based semantic matching for concept mapping

Usage:
    from eligibility_analyzer.feasibility import (
        CriterionClassifier,
        KeyCriteriaNormalizer,
        EligibilityFunnelBuilder,
        PopulationEstimator,
    )

    # Classify criteria
    classifier = CriterionClassifier()
    key_criteria, metadata = await classifier.classify_criteria(criteria)

    # Normalize to key criteria
    normalizer = KeyCriteriaNormalizer()
    key_criteria, stages, killer_ids, manual_ids = normalizer.normalize_criteria(key_criteria)

    # Build eligibility funnel from stage outputs
    builder = EligibilityFunnelBuilder(athena_db_path)
    result = await builder.build_from_stage_outputs(protocol_id, stage2, stage5, stage6)
"""

from .data_models import (
    CriterionCategory,
    QueryableStatus,
    FunnelStageType,
    PrevalenceEstimate,
    OmopMapping,
    FhirMapping,
    KeyCriterion,
    CriterionMatch,
    FunnelStage,
    PopulationEstimate,
    OptimizationOpportunity,
    SiteRanking,
    FunnelResult,
)

# QEB (Queryable Eligibility Block) models for Stage 12
from .qeb_models import (
    QueryableEligibilityBlock,
    QEBFunnelStage,
    QEBOutput,
    QEBSummary,
    QEBExecutionGuide,
    OMOPConceptRef,
    FHIRResourceRef,
    QEBProvenance,
    save_qeb_output,
    load_qeb_output,
)

from .criterion_classifier import CriterionClassifier, load_criteria_from_extraction
from .key_criteria_normalizer import KeyCriteriaNormalizer
from .population_estimator import PopulationEstimator
from .reference_data_manager import ReferenceDataManager, get_reference_data_manager
from .eligibility_funnel_builder import (
    EligibilityFunnelBuilder,
    build_eligibility_funnel_from_files,
    build_eligibility_funnel_from_files_sync,
    save_eligibility_funnel,
    # Backward compatibility aliases
    FunnelV2Builder,
    build_v2_funnel_from_files,
    build_v2_funnel_from_files_sync,
    save_v2_funnel,
)
from .llm_atomic_matcher import LLMAtomicMatcher
from .validators import (
    validate_criteria_input,
    validate_funnel_result,
    validate_key_criterion,
    validate_funnel_output_for_export,
    ValidationError,
)

__all__ = [
    # Enums
    "CriterionCategory",
    "QueryableStatus",
    "FunnelStageType",
    # Data classes
    "PrevalenceEstimate",
    "OmopMapping",
    "FhirMapping",
    "KeyCriterion",
    "CriterionMatch",
    "FunnelStage",
    "PopulationEstimate",
    "OptimizationOpportunity",
    "SiteRanking",
    "FunnelResult",
    # QEB (Queryable Eligibility Block) models
    "QueryableEligibilityBlock",
    "QEBFunnelStage",
    "QEBOutput",
    "QEBSummary",
    "QEBExecutionGuide",
    "OMOPConceptRef",
    "FHIRResourceRef",
    "QEBProvenance",
    "save_qeb_output",
    "load_qeb_output",
    # Main classes
    "CriterionClassifier",
    "KeyCriteriaNormalizer",
    "PopulationEstimator",
    "ReferenceDataManager",
    # Eligibility Funnel (LLM-first)
    "EligibilityFunnelBuilder",
    "LLMAtomicMatcher",
    # Validators
    "validate_criteria_input",
    "validate_funnel_result",
    "validate_key_criterion",
    "validate_funnel_output_for_export",
    "ValidationError",
    # Helper functions
    "load_criteria_from_extraction",
    "get_reference_data_manager",
    "build_eligibility_funnel_from_files",
    "build_eligibility_funnel_from_files_sync",
    "save_eligibility_funnel",
    # Backward compatibility aliases
    "FunnelV2Builder",
    "build_v2_funnel_from_files",
    "build_v2_funnel_from_files_sync",
    "save_v2_funnel",
]
