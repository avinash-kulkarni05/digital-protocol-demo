"""
Timing Expansion Models for Stage 7: Timing Distribution

Data models for representing timing patterns, expansion decisions, and results.

Usage:
    from soa_analyzer.models.timing_expansion import (
        TimingPattern,
        TimingExpansion,
        TimingDecision,
        Stage7Result,
    )

    decision = TimingDecision(
        timing_modifier="BI/EOI",
        should_expand=True,
        expanded_timings=["BI", "EOI"],
        confidence=0.98,
        rationale="Standard Before Infusion / End of Infusion split for PK sampling",
    )
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import hashlib
import re
import uuid


@dataclass
class TimingPattern:
    """
    A known timing pattern for validation purposes.

    Used to cross-check LLM decisions, NOT for primary routing (LLM-first).

    Example:
        pattern = TimingPattern(
            id="bi_eoi",
            pattern_regex=r"^(BI|EOI)[/,](EOI|BI)$",
            atomic_timings=["BI", "EOI"],
        )
    """
    id: str
    pattern_regex: str
    atomic_timings: List[str]
    description: Optional[str] = None
    cdisc_code: Optional[str] = None

    def matches(self, timing_modifier: str) -> bool:
        """Check if this pattern matches the timing modifier."""
        if not timing_modifier:
            return False
        return bool(re.match(self.pattern_regex, timing_modifier, re.IGNORECASE))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "patternRegex": self.pattern_regex,
            "atomicTimings": self.atomic_timings,
            "description": self.description,
            "cdiscCode": self.cdisc_code,
        }


@dataclass
class TimingDecision:
    """
    LLM decision for how to expand a timing modifier.

    This is what gets cached - the full decision with rationale.

    Example:
        decision = TimingDecision(
            timing_modifier="BI/EOI",
            should_expand=True,
            expanded_timings=["BI", "EOI"],
            confidence=0.98,
            rationale="Standard BI/EOI split for PK sampling",
        )
    """
    timing_modifier: str
    should_expand: bool
    expanded_timings: List[str] = field(default_factory=list)
    confidence: float = 1.0
    rationale: Optional[str] = None
    source: str = "llm"  # "llm", "cache", "validation"
    cached_at: Optional[str] = None
    model_name: Optional[str] = None

    def __post_init__(self):
        """Set cached_at timestamp if not provided."""
        if self.cached_at is None:
            self.cached_at = datetime.utcnow().isoformat() + "Z"

    def get_cache_key(self) -> str:
        """Generate cache key from timing modifier."""
        normalized = self.timing_modifier.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "timingModifier": self.timing_modifier,
            "shouldExpand": self.should_expand,
            "expandedTimings": self.expanded_timings,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "source": self.source,
            "cachedAt": self.cached_at,
            "modelName": self.model_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimingDecision":
        """Create from dictionary representation."""
        return cls(
            timing_modifier=data.get("timingModifier", ""),
            should_expand=data.get("shouldExpand", False),
            expanded_timings=data.get("expandedTimings", []),
            confidence=data.get("confidence", 1.0),
            rationale=data.get("rationale"),
            source=data.get("source", "cache"),
            cached_at=data.get("cachedAt"),
            model_name=data.get("modelName"),
        )


@dataclass
class TimingExpansion:
    """
    Result of expanding a single SAI's timing modifier.

    Tracks lineage from original SAI to expanded SAIs for audit trail.

    Example:
        expansion = TimingExpansion(
            original_sai_id="SAI-042",
            original_timing_modifier="BI/EOI",
            expanded_sais=[
                {"id": "SAI-042-BI", "timingModifier": "BI", ...},
                {"id": "SAI-042-EOI", "timingModifier": "EOI", ...},
            ],
            decision=decision,
        )
    """
    id: str = field(default_factory=lambda: f"TEXP-{uuid.uuid4().hex[:8].upper()}")
    original_sai_id: str = ""
    original_timing_modifier: str = ""
    expanded_sais: List[Dict[str, Any]] = field(default_factory=list)
    decision: Optional[TimingDecision] = None
    requires_review: bool = False
    review_reason: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None

    @property
    def expansion_count(self) -> int:
        """Number of expanded SAIs created."""
        return len(self.expanded_sais)

    @property
    def confidence(self) -> float:
        """Confidence from the decision."""
        return self.decision.confidence if self.decision else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "originalSaiId": self.original_sai_id,
            "originalTimingModifier": self.original_timing_modifier,
            "expandedSaiCount": self.expansion_count,
            "expandedSaiIds": [sai.get("id", "") for sai in self.expanded_sais],
            "confidence": self.confidence,
            "source": self.decision.source if self.decision else None,
            "rationale": self.decision.rationale if self.decision else None,
            "requiresReview": self.requires_review,
            "reviewReason": self.review_reason,
            "provenance": self.provenance,
        }


@dataclass
class ValidationDiscrepancy:
    """
    A discrepancy between LLM decision and known validation pattern.

    Used for flagging and human review.
    """
    timing_modifier: str
    llm_decision: List[str]  # What LLM said
    pattern_decision: List[str]  # What pattern says
    pattern_id: str
    severity: str = "warning"  # "info", "warning", "error"
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "timingModifier": self.timing_modifier,
            "llmDecision": self.llm_decision,
            "patternDecision": self.pattern_decision,
            "patternId": self.pattern_id,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class Stage7Result:
    """
    Result of Stage 7 timing distribution processing.

    Contains all expansions, review items, and metrics.
    """
    expansions: List[TimingExpansion] = field(default_factory=list)
    decisions: Dict[str, TimingDecision] = field(default_factory=dict)  # timing_modifier -> decision
    discrepancies: List[ValidationDiscrepancy] = field(default_factory=list)

    # Review items for human decision
    review_items: List[Any] = field(default_factory=list)  # HumanReviewItem from expansion_proposal

    # Metrics
    unique_timings_analyzed: int = 0  # Unique timing modifiers sent to LLM
    sais_processed: int = 0           # Total SAIs checked
    sais_with_timing: int = 0         # SAIs that have a timingModifier
    sais_expanded: int = 0            # SAIs that were expanded
    sais_created: int = 0             # New SAIs created (total expanded count)
    sais_unchanged: int = 0           # SAIs not needing expansion
    cache_hits: int = 0               # Timing patterns found in cache
    llm_calls: int = 0                # LLM API calls made (usually 1)
    validation_flags: int = 0         # LLM vs library discrepancies

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of timing distribution."""
        return {
            "uniqueTimingsAnalyzed": self.unique_timings_analyzed,
            "saisProcessed": self.sais_processed,
            "saisWithTiming": self.sais_with_timing,
            "saisExpanded": self.sais_expanded,
            "saisCreated": self.sais_created,
            "saisUnchanged": self.sais_unchanged,
            "cacheHits": self.cache_hits,
            "llmCalls": self.llm_calls,
            "validationFlags": self.validation_flags,
            "reviewItemsCount": len(self.review_items),
            "expansionRate": self.sais_expanded / max(self.sais_with_timing, 1),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "stage": 7,
            "stageName": "Timing Distribution",
            "success": True,
            "expansions": [e.to_dict() for e in self.expansions],
            "decisions": {k: v.to_dict() for k, v in self.decisions.items()},
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "reviewItems": [r.to_dict() if hasattr(r, 'to_dict') else r for r in self.review_items],
            "metrics": self.get_summary(),
        }


@dataclass
class TimingDistributionConfig:
    """
    Configuration for Stage 7 timing distribution.
    """
    # LLM settings
    use_llm: bool = True
    model_name: str = "gemini-2.5-pro"
    fallback_model: str = "gpt-5-mini"
    max_output_tokens: int = 8192
    temperature: float = 0.1

    # Confidence thresholds
    confidence_threshold_auto: float = 0.90  # Auto-apply if >= this
    confidence_threshold_review: float = 0.70  # Flag for review if below this

    # Expansion limits
    max_expansions_per_sai: int = 10  # Safety limit

    # Validation
    validate_against_patterns: bool = True  # Cross-check with known patterns
    flag_discrepancies: bool = True  # Add to review if LLM differs from pattern

    # Caching
    use_cache: bool = True
    cache_dir: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "useLlm": self.use_llm,
            "modelName": self.model_name,
            "fallbackModel": self.fallback_model,
            "confidenceThresholdAuto": self.confidence_threshold_auto,
            "confidenceThresholdReview": self.confidence_threshold_review,
            "maxExpansionsPerSai": self.max_expansions_per_sai,
            "validateAgainstPatterns": self.validate_against_patterns,
            "useCache": self.use_cache,
        }
