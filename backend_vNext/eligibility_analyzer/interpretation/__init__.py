"""
Eligibility Criteria Interpretation Pipeline

11-stage pipeline for comprehensive eligibility criteria interpretation.
Converts raw extracted criteria into USDM 4.0 compliant JSON with OMOP concept mapping.

Design Principles:
1. LLM-First - Use Claude for complex reasoning over brittle regex
2. Confidence-Based - Auto-apply high-confidence, escalate low-confidence to human review
3. Audit Trail - Full provenance for every generated entity
4. USDM Compliant - 6-field Code objects, instanceType fields
5. OMOP Mapped - Standard concepts for EHR querying

Stages:
    Stage 1: Cohort Detection - Identify multi-arm trial cohorts
    Stage 2: Atomic Decomposition (CRITICAL) - Break into SQL-queryable pieces
    Stage 3: Clinical Categorization - Assign clinical domains
    Stage 4: Term Extraction - Extract searchable terms for OMOP
    Stage 5: OMOP Concept Mapping (CRITICAL) - Map to standard concepts
    Stage 6: SQL Template Generation - Generate OMOP CDM queries
    Stage 7: USDM Compliance (CRITICAL) - Code object expansion
    Stage 8: Tier Assignment - Criticality prioritization
    Stage 9: Human Review Assembly - Package for review
    Stage 10: Final Output Generation - Produce output files
    Stage 11: Feasibility Analysis - Patient funnel generation

Usage:
    from eligibility_analyzer.interpretation import InterpretationPipeline

    pipeline = InterpretationPipeline()
    result = await pipeline.run(raw_criteria)
"""

__version__ = "1.0.0"

# Pipeline Orchestrator
from .interpretation_pipeline import (
    InterpretationPipeline,
    PipelineConfig,
    PipelineResult,
    run_interpretation_pipeline,
)

# Stage 2: Atomic Decomposition (CRITICAL)
from .stage2_atomic_decomposition import (
    AtomicDecomposer,
    AtomicDecompositionResult,
    decompose_criteria,
)

# Stage 4: LLM Concept Expansion
from .llm_concept_expander import (
    LLMConceptExpander,
    ConceptExpansion,
    BatchExpansionResult,
    get_concept_expander,
)

from .concept_expansion_cache import (
    ConceptExpansionCache,
    get_concept_expansion_cache,
)

from .term_normalizer import (
    TermNormalizer,
    normalize_term,
    normalize_terms_async,
)

# Stage 5.5: LLM Clinical Reasoning for unmapped terms
from .llm_clinical_reasoner import (
    LLMClinicalReasoner,
    ClinicalReasoning,
    ClinicalReasoningResult,
    MappableConcept,
    get_clinical_reasoner,
    reset_clinical_reasoner,
)

# Stage 11: Feasibility Analysis
from .stage11_feasibility import (
    Stage11Feasibility,
    run_stage11,
)

__all__ = [
    # Pipeline Orchestrator
    "InterpretationPipeline",
    "PipelineConfig",
    "PipelineResult",
    "run_interpretation_pipeline",
    # Stage 2
    "AtomicDecomposer",
    "AtomicDecompositionResult",
    "decompose_criteria",
    # Stage 4: LLM Concept Expansion
    "LLMConceptExpander",
    "ConceptExpansion",
    "BatchExpansionResult",
    "get_concept_expander",
    "ConceptExpansionCache",
    "get_concept_expansion_cache",
    "TermNormalizer",
    "normalize_term",
    "normalize_terms_async",
    # Stage 5.5: LLM Clinical Reasoning
    "LLMClinicalReasoner",
    "ClinicalReasoning",
    "ClinicalReasoningResult",
    "MappableConcept",
    "get_clinical_reasoner",
    "reset_clinical_reasoner",
    # Stage 11: Feasibility Analysis
    "Stage11Feasibility",
    "run_stage11",
]
