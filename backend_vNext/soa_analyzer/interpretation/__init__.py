"""
SOA Interpretation Pipeline

12-stage pipeline for comprehensive SOA interpretation using LLM-first architecture.
Converts extracted SOA tables into complete visit schedules with USDM 4.0 compliance.

Design Principles:
1. LLM-First - Use LLM reasoning over brittle regex/hardcoded rules
2. Confidence-Based - Auto-apply high-confidence, escalate low-confidence to human review
3. Audit Trail - Full provenance for every generated entity
4. USDM Compliant - 6-field Code objects, referential integrity, Condition linkage

Stages:
    Stage 1: Domain Categorization (CRITICAL) - Map activities to CDISC domains
    Stage 2: Activity Expansion - Decompose parent activities to components
    Stage 3: Hierarchy Building - Build parent-child activity trees
    Stage 4: Alternative Resolution - Handle X or Y choice points
    Stage 5: Specimen Enrichment - Extract tube/volume details
    Stage 6: Conditional Expansion - Apply population/clinical conditions
    Stage 7: Timing Distribution - Expand BI/EOI, pre/post-dose
    Stage 8: Cycle Expansion - Generate visits for repeating patterns
    Stage 9: Protocol Mining - Cross-reference non-SOA sections
    Stage 10: Human Review Assembly - Package for review
    Stage 11: Schedule Generation - Apply decisions, generate final
    Stage 12: USDM Compliance (CRITICAL) - Code object expansion + validation

Usage:
    from soa_analyzer.interpretation import InterpretationPipeline

    pipeline = InterpretationPipeline()
    result = await pipeline.run(soa_extraction_output)
"""

__version__ = "1.0.0"

# Stage 1: Domain Categorization (CRITICAL)
from .stage1_domain_categorization import (
    DomainCategorizer,
    DomainMapping,
    CategorizationResult,
    categorize_soa_activities,
    VALID_DOMAINS,
)

# Stage 2: Activity Component Expansion
from .stage2_activity_expansion import (
    ActivityExpander,
    ExpansionConfig,
    Stage2Result,
    expand_activities,
)

# Stage 3: Hierarchy Building
from .stage3_hierarchy_builder import (
    HierarchyBuilder,
    HierarchyConfig,
    Stage3Result,
    build_hierarchy,
    DOMAIN_INFO,
)

# Stage 4: Alternative Resolution
from .stage4_alternative_resolution import (
    AlternativeResolver,
    AlternativePatternRegistry,
    Stage4Result,
    resolve_alternatives,
)

# Stage 5: Specimen Enrichment
from .stage5_specimen_enrichment import (
    SpecimenEnricher,
    SpecimenPatternRegistry,
    Stage5Result,
    enrich_specimens,
)

# Stage 6: Conditional Expansion
from .stage6_conditional_expansion import (
    ConditionalExpander,
    ConditionalExpansionConfig,
    ConditionExtraction,
    ConditionPatternRegistry,
    Stage6Result,
    expand_conditions,
)

# Stage 7: Timing Distribution
from .stage7_timing_distribution import (
    TimingDistributor,
    TimingDistributionConfig,
    TimingPatternRegistry,
    Stage7Result,
    distribute_timing,
)

# Stage 8: Cycle Expansion
from .stage8_cycle_expansion import (
    CycleExpander,
    CycleExpansionConfig,
    CyclePatternRegistry,
    Stage8Result,
    expand_cycles,
)

# Stage 9: Protocol Mining
from .stage9_protocol_mining import (
    ProtocolMiner,
    ModuleMappingRegistry,
    Stage9Result,
    mine_protocol,
)

# Stage 10: Human Review Assembly
from .stage10_human_review import (
    HumanReviewAssembler,
    Stage10Result,
    assemble_review_package,
)

# Stage 11: Schedule Generation
from .stage11_schedule_generation import (
    ScheduleGenerator,
    Stage11Config,
    Stage11Result,
    generate_schedule,
)

# Stage 12: USDM Compliance (CRITICAL)
from .stage12_usdm_compliance import (
    USDMComplianceChecker,
    ComplianceIssue,
    ComplianceResult,
    ensure_usdm_compliance,
)

# Pipeline Orchestrator
from .interpretation_pipeline import (
    InterpretationPipeline,
    PipelineConfig,
    PipelineResult,
    run_interpretation_pipeline,
)

__all__ = [
    # Stage 1
    "DomainCategorizer",
    "DomainMapping",
    "CategorizationResult",
    "categorize_soa_activities",
    "VALID_DOMAINS",
    # Stage 2
    "ActivityExpander",
    "ExpansionConfig",
    "Stage2Result",
    "expand_activities",
    # Stage 3
    "HierarchyBuilder",
    "HierarchyConfig",
    "Stage3Result",
    "build_hierarchy",
    "DOMAIN_INFO",
    # Stage 4
    "AlternativeResolver",
    "AlternativePatternRegistry",
    "Stage4Result",
    "resolve_alternatives",
    # Stage 5
    "SpecimenEnricher",
    "SpecimenPatternRegistry",
    "Stage5Result",
    "enrich_specimens",
    # Stage 6
    "ConditionalExpander",
    "ConditionalExpansionConfig",
    "ConditionExtraction",
    "ConditionPatternRegistry",
    "Stage6Result",
    "expand_conditions",
    # Stage 7
    "TimingDistributor",
    "TimingDistributionConfig",
    "TimingPatternRegistry",
    "Stage7Result",
    "distribute_timing",
    # Stage 8
    "CycleExpander",
    "CycleExpansionConfig",
    "CyclePatternRegistry",
    "Stage8Result",
    "expand_cycles",
    # Stage 9
    "ProtocolMiner",
    "ModuleMappingRegistry",
    "Stage9Result",
    "mine_protocol",
    # Stage 10
    "HumanReviewAssembler",
    "Stage10Result",
    "assemble_review_package",
    # Stage 11
    "ScheduleGenerator",
    "Stage11Config",
    "Stage11Result",
    "generate_schedule",
    # Stage 12
    "USDMComplianceChecker",
    "ComplianceIssue",
    "ComplianceResult",
    "ensure_usdm_compliance",
    # Pipeline Orchestrator
    "InterpretationPipeline",
    "PipelineConfig",
    "PipelineResult",
    "run_interpretation_pipeline",
]
