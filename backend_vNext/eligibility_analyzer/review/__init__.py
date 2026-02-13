"""
QEB Validation - Human-in-the-Loop Review System

Provides models and services for validating LLM-generated eligibility QEBs
through human review, enabling accurate patient feasibility analysis.

Key Components:
- qeb_validation_models: Data structures for validation state
- qeb_validation_service: Business logic for session management and overrides
"""

from .qeb_validation_models import (
    AtomicWithClassification,
    ClassificationOverride,
    OMOPCorrection,
    QEBClassificationSummary,
    ClassificationSummary,
    ValidationSession,
    FunnelStageConfig,
    FunnelStageResult,
    QEBExecutionResult,
    FunnelExecutionResult,
)

from .qeb_validation_service import (
    QEBValidationService,
)

__all__ = [
    # Models
    "AtomicWithClassification",
    "ClassificationOverride",
    "OMOPCorrection",
    "QEBClassificationSummary",
    "ClassificationSummary",
    "ValidationSession",
    "FunnelStageConfig",
    "FunnelStageResult",
    "QEBExecutionResult",
    "FunnelExecutionResult",
    # Services
    "QEBValidationService",
]
