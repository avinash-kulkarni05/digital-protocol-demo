"""
SOA Analyzer - Schedule of Activities Extraction Pipeline

Full end-to-end pipeline for extracting Schedule of Activities (SOA) tables from
clinical trial protocols and transforming them into USDM 4.0 compliant JSON.

Pipeline Phases:
    Phase 1: Detection - Find SOA pages in PDF (Gemini Vision)
    Phase 2: Extraction - PDF → HTML tables (LandingAI, 7x zoom)
    Phase 3: Interpretation - HTML → USDM structure (12-stage pipeline)
    Phase 4: Validation - 5-dimensional quality framework
    Phase 5: Output - Save results (USDM JSON, quality report)

Components:
    - soa_extraction_pipeline: Main orchestrator (full end-to-end)
    - interpretation/: 12-stage interpretation pipeline
    - soa_page_detector: SOA page detection
    - soa_html_interpreter: Claude-based HTML interpretation
    - soa_quality_checker: 5-dimensional quality framework
    - soa_cache: Version-aware caching layer

Usage:
    from soa_analyzer import SOAExtractionPipeline, run_soa_extraction

    # Option 1: Class-based
    pipeline = SOAExtractionPipeline()
    result = await pipeline.run("/path/to/protocol.pdf")

    # Option 2: Convenience function
    result = await run_soa_extraction("/path/to/protocol.pdf")

    # Access results
    if result.success:
        print(f"Quality: {result.quality_score.overall_score:.1%}")
        print(f"Output: {result.output_files}")
"""

__version__ = "3.0.0"
__author__ = "Protocol Digitalization Team"

# Main Pipeline (Full End-to-End)
from soa_analyzer.soa_extraction_pipeline import (
    SOAExtractionPipeline,
    ExtractionResult,
    PhaseResult,
    run_soa_extraction,
)

# 12-Stage Interpretation Pipeline
from soa_analyzer.interpretation import (
    InterpretationPipeline,
    PipelineConfig,
    PipelineResult,
    run_interpretation_pipeline,
)

# Detection
from soa_analyzer.soa_page_detector import detect_soa_pages_v2, get_merged_table_pages

# HTML Interpretation
from soa_analyzer.soa_html_interpreter import SOAHTMLInterpreter

# Quality
from soa_analyzer.soa_quality_checker import SOAQualityChecker, QualityScore, get_quality_checker

# Cache
from soa_analyzer.soa_cache import SOACache, get_soa_cache

# Terminology
from soa_analyzer.soa_terminology_mapper import TerminologyMapper, get_mapper

# Transformation
from soa_analyzer.soa_usdm_transformer import USDMTransformer, SOATable, get_transformer

# Enrichment
from soa_analyzer.soa_enrichment import SOAEnrichment, get_enrichment

# Backwards compatibility aliases
SOAPipeline = SOAExtractionPipeline
PipelineResultV2 = ExtractionResult
StageResult = PhaseResult

__all__ = [
    # Main Pipeline (primary)
    "SOAExtractionPipeline",
    "ExtractionResult",
    "PhaseResult",
    "run_soa_extraction",
    # 12-Stage Interpretation Pipeline
    "InterpretationPipeline",
    "PipelineConfig",
    "PipelineResult",
    "run_interpretation_pipeline",
    # Detection
    "detect_soa_pages_v2",
    "get_merged_table_pages",
    # HTML Interpretation
    "SOAHTMLInterpreter",
    # Quality
    "SOAQualityChecker",
    "QualityScore",
    "get_quality_checker",
    # Cache
    "SOACache",
    "get_soa_cache",
    # Terminology
    "TerminologyMapper",
    "get_mapper",
    # Transformation
    "USDMTransformer",
    "SOATable",
    "get_transformer",
    # Enrichment
    "SOAEnrichment",
    "get_enrichment",
    # Backwards compatibility
    "SOAPipeline",
    "PipelineResultV2",
    "StageResult",
]
