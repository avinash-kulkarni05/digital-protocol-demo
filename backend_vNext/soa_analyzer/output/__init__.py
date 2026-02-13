"""
SOA Output Module

Generates user-friendly review JSONs for Phase 1 (Extraction Validation)
and Phase 2 (Interpretation Wizard) workflows.

Usage:
    from soa_analyzer.output import (
        generate_extraction_review,
        generate_interpretation_review,
        ExtractionReviewGenerator,
        InterpretationReviewGenerator,
    )

    # Phase 1: Extraction Validation
    extraction_review = generate_extraction_review(
        soa_output, protocol_id, protocol_title
    )

    # Phase 2: Interpretation Wizard
    interpretation_review = generate_interpretation_review(
        pipeline_result, protocol_id, protocol_title
    )
"""

from .extraction_review_generator import (
    ExtractionReviewGenerator,
    generate_extraction_review,
)

from .interpretation_review_generator import (
    InterpretationReviewGenerator,
    generate_interpretation_review,
)

__all__ = [
    "ExtractionReviewGenerator",
    "generate_extraction_review",
    "InterpretationReviewGenerator",
    "generate_interpretation_review",
]
