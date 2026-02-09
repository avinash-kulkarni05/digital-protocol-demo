"""
Data models for Stage 4: Alternative Resolution.

Handles choice points in SOA tables like "CT scan or MRI", "Blood / urine sample".

Design principles:
- USDM 4.0 compliant (6-field Code objects, no ScheduledDecisionInstance)
- Full provenance tracking on all generated entities
- M:N activity→SAI expansion support
- Multi-way alternatives (3+ options) support
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
import hashlib


class AlternativeType(str, Enum):
    """Types of alternative patterns in SOA tables."""
    MUTUALLY_EXCLUSIVE = "mutually_exclusive"  # Only ONE option performed (CT or MRI)
    DISCRETIONARY = "discretionary"            # Investigator/site chooses
    CONDITIONAL = "conditional"                # Based on patient/clinical state
    PREFERRED_WITH_FALLBACK = "preferred_with_fallback"  # One preferred, other if unavailable
    UNCERTAIN = "uncertain"                    # Unclear, needs human review


class ResolutionAction(str, Enum):
    """Actions for resolving an alternative."""
    EXPAND = "expand"        # Create separate activities/SAIs
    CONDITION = "condition"  # Link to existing or create Condition
    KEEP = "keep"            # Not an alternative, preserve original
    REVIEW = "review"        # Flag for human review


@dataclass
class AlternativeOption:
    """A single option within an alternative."""
    name: str
    order: int  # Position in alternatives list (1-indexed)
    confidence: float = 1.0
    cdisc_domain: Optional[str] = None
    is_preferred: bool = False  # For PREFERRED_WITH_FALLBACK type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "order": self.order,
            "confidence": self.confidence,
            "cdiscDomain": self.cdisc_domain,
            "isPreferred": self.is_preferred,
        }


@dataclass
class AlternativeDecision:
    """
    LLM decision for an alternative choice point.

    This is what gets cached - the decision for a specific activity text.
    """
    activity_id: str
    activity_name: str
    is_alternative: bool
    alternative_type: Optional[AlternativeType] = None
    alternatives: List[AlternativeOption] = field(default_factory=list)
    recommended_action: ResolutionAction = ResolutionAction.KEEP
    confidence: float = 1.0
    rationale: Optional[str] = None
    source: str = "llm"  # "llm", "cache", "pattern"
    requires_human_review: bool = False
    review_reason: Optional[str] = None
    cached_at: Optional[str] = None
    model_name: Optional[str] = None

    def get_cache_key(self, model_name: str) -> str:
        """Generate cache key including model version for invalidation."""
        normalized = self.activity_name.lower().strip()
        key_source = f"{normalized}:{model_name}"
        return hashlib.md5(key_source.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "isAlternative": self.is_alternative,
            "alternativeType": self.alternative_type.value if self.alternative_type else None,
            "alternatives": [alt.to_dict() for alt in self.alternatives],
            "recommendedAction": self.recommended_action.value,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "source": self.source,
            "requiresHumanReview": self.requires_human_review,
            "reviewReason": self.review_reason,
            "cachedAt": self.cached_at,
            "modelName": self.model_name,
        }

    @classmethod
    def from_llm_response(cls, activity_id: str, response_data: Dict[str, Any], model_name: str) -> "AlternativeDecision":
        """Create from LLM JSON response."""
        alternatives = []
        for i, alt_data in enumerate(response_data.get("alternatives", []), 1):
            alternatives.append(AlternativeOption(
                name=alt_data.get("name", ""),
                order=alt_data.get("order", i),
                confidence=alt_data.get("confidence", 1.0),
                cdisc_domain=alt_data.get("cdiscDomain"),
                is_preferred=alt_data.get("isPreferred", False),
            ))

        alt_type_str = response_data.get("alternativeType")
        alt_type = AlternativeType(alt_type_str.lower()) if alt_type_str else None

        action_str = response_data.get("recommendedResolution", "keep")
        action = ResolutionAction(action_str.lower()) if action_str else ResolutionAction.KEEP

        confidence = response_data.get("confidence", 1.0)

        return cls(
            activity_id=activity_id,
            activity_name=response_data.get("activityName", ""),
            is_alternative=response_data.get("isAlternative", False),
            alternative_type=alt_type,
            alternatives=alternatives,
            recommended_action=action,
            confidence=confidence,
            rationale=response_data.get("rationale"),
            source="llm",
            requires_human_review=confidence < 0.70 or action == ResolutionAction.REVIEW,
            review_reason=response_data.get("reviewReason"),
            model_name=model_name,
            cached_at=datetime.utcnow().isoformat() + "Z",
        )


@dataclass
class AlternativeProvenance:
    """Full provenance metadata for alternative resolution."""
    original_activity_id: str
    original_activity_name: str
    alternative_type: str
    alternative_index: int  # 1-indexed
    alternative_count: int
    confidence: float
    rationale: Optional[str]
    stage: str = "Stage4AlternativeResolution"
    model: Optional[str] = None
    timestamp: Optional[str] = None
    source: str = "llm"  # "llm", "cache", "pattern"
    cache_hit: bool = False
    cache_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "originalActivityId": self.original_activity_id,
            "originalActivityName": self.original_activity_name,
            "alternativeType": self.alternative_type,
            "alternativeIndex": self.alternative_index,
            "alternativeCount": self.alternative_count,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "stage": self.stage,
            "model": self.model,
            "timestamp": self.timestamp,
            "source": self.source,
            "cacheHit": self.cache_hit,
            "cacheKey": self.cache_key,
        }


@dataclass
class AlternativeExpansion:
    """
    Result of expanding an alternative into separate entities.

    Tracks all created activities, SAIs, conditions, and assignments.
    """
    id: str  # Expansion ID: EXP-{original_activity_id}
    original_activity_id: str
    original_activity_name: str
    expanded_activities: List[Dict[str, Any]] = field(default_factory=list)
    expanded_sais: List[Dict[str, Any]] = field(default_factory=list)
    conditions_created: List[Dict[str, Any]] = field(default_factory=list)
    assignments_created: List[Dict[str, Any]] = field(default_factory=list)
    decision: Optional[AlternativeDecision] = None
    confidence: float = 1.0
    alternative_type: AlternativeType = AlternativeType.MUTUALLY_EXCLUSIVE
    requires_review: bool = False
    review_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "originalActivityId": self.original_activity_id,
            "originalActivityName": self.original_activity_name,
            "expandedActivities": self.expanded_activities,
            "expandedSais": self.expanded_sais,
            "conditionsCreated": self.conditions_created,
            "assignmentsCreated": self.assignments_created,
            "confidence": self.confidence,
            "alternativeType": self.alternative_type.value,
            "requiresReview": self.requires_review,
            "reviewReason": self.review_reason,
        }


@dataclass
class HumanReviewItem:
    """Item flagged for human review."""
    id: str
    item_type: str  # "alternative", "condition", "expansion"
    activity_id: str
    activity_name: str
    reason: str
    confidence: float
    proposed_resolution: Optional[Dict[str, Any]] = None
    alternatives: List[str] = field(default_factory=list)
    context: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "itemType": self.item_type,
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "reason": self.reason,
            "confidence": self.confidence,
            "proposedResolution": self.proposed_resolution,
            "alternatives": self.alternatives,
            "context": self.context,
        }


@dataclass
class Stage4Result:
    """
    Result of Stage 4: Alternative Resolution.

    Contains all expansions, decisions, review items, and metrics.
    """
    expansions: List[AlternativeExpansion] = field(default_factory=list)
    decisions: Dict[str, AlternativeDecision] = field(default_factory=dict)
    review_items: List[HumanReviewItem] = field(default_factory=list)

    # Metrics
    activities_analyzed: int = 0
    alternatives_detected: int = 0
    activities_expanded: int = 0
    sais_created: int = 0
    conditions_created: int = 0
    assignments_created: int = 0
    auto_applied: int = 0
    needs_review: int = 0
    timing_patterns_filtered: int = 0  # BI/EOI, pre/post-dose filtered
    unit_patterns_filtered: int = 0    # mg/kg, mL/min filtered
    cache_hits: int = 0
    llm_calls: int = 0
    validation_discrepancies: int = 0
    referential_integrity_errors: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": 4,
            "stageName": "Alternative Resolution",
            "success": True,
            "expansions": [exp.to_dict() for exp in self.expansions],
            "decisions": {k: v.to_dict() for k, v in self.decisions.items()},
            "reviewItems": [item.to_dict() for item in self.review_items],
            "metrics": {
                "activitiesAnalyzed": self.activities_analyzed,
                "alternativesDetected": self.alternatives_detected,
                "activitiesExpanded": self.activities_expanded,
                "saisCreated": self.sais_created,
                "conditionsCreated": self.conditions_created,
                "assignmentsCreated": self.assignments_created,
                "autoApplied": self.auto_applied,
                "needsReview": self.needs_review,
                "timingPatternsFiltered": self.timing_patterns_filtered,
                "unitPatternsFiltered": self.unit_patterns_filtered,
                "cacheHits": self.cache_hits,
                "llmCalls": self.llm_calls,
                "validationDiscrepancies": self.validation_discrepancies,
                "referentialIntegrityErrors": self.referential_integrity_errors,
            },
        }

    def add_expansion(self, expansion: AlternativeExpansion) -> None:
        """Add an expansion and update metrics."""
        self.expansions.append(expansion)
        self.activities_expanded += 1
        self.sais_created += len(expansion.expanded_sais)
        self.conditions_created += len(expansion.conditions_created)
        self.assignments_created += len(expansion.assignments_created)

        if expansion.requires_review:
            self.needs_review += 1
        else:
            self.auto_applied += 1


@dataclass
class AlternativeResolutionConfig:
    """Configuration for Stage 4: Alternative Resolution."""
    # Confidence thresholds
    confidence_threshold_auto: float = 0.90  # Auto-apply if ≥ this
    confidence_threshold_review: float = 0.70  # Flag for review if < this

    # Expansion limits
    max_alternatives_per_activity: int = 5  # Prevent explosion
    max_batch_size: int = 20  # Activities per LLM call

    # Feature flags
    expand_mutually_exclusive: bool = True
    create_conditions: bool = True
    handle_footnote_alternatives: bool = True
    validate_referential_integrity: bool = True

    # LLM settings
    model_name: str = "gemini-2.5-pro"
    azure_model_name: str = "gpt-5-mini"
    timeout_seconds: int = 30
    max_retries: int = 3

    # Cache settings
    use_cache: bool = True
    cache_ttl_hours: int = 168  # 1 week

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confidenceThresholdAuto": self.confidence_threshold_auto,
            "confidenceThresholdReview": self.confidence_threshold_review,
            "maxAlternativesPerActivity": self.max_alternatives_per_activity,
            "maxBatchSize": self.max_batch_size,
            "expandMutuallyExclusive": self.expand_mutually_exclusive,
            "createConditions": self.create_conditions,
            "handleFootnoteAlternatives": self.handle_footnote_alternatives,
            "validateReferentialIntegrity": self.validate_referential_integrity,
            "modelName": self.model_name,
            "azureModelName": self.azure_model_name,
            "timeoutSeconds": self.timeout_seconds,
            "maxRetries": self.max_retries,
            "useCache": self.use_cache,
            "cacheTtlHours": self.cache_ttl_hours,
        }


# Helper functions

def is_timing_pattern(text: str) -> bool:
    """Check if text is a timing pattern (handled by Stage 7)."""
    normalized = text.lower().strip()
    timing_patterns = [
        "bi/eoi", "bi / eoi", "bi, eoi",
        "eoi/bi", "eoi / bi",
        "pre-dose", "post-dose", "predose", "postdose",
        "pre-dose/post-dose", "predose/postdose",
        "trough/peak", "peak/trough",
        "trough", "peak",
        "fasting/fed", "fed/fasting",
    ]
    return any(pattern in normalized for pattern in timing_patterns)


def is_unit_pattern(text: str) -> bool:
    """Check if text contains dosing units (NOT alternatives)."""
    import re
    normalized = text.lower().strip()
    unit_patterns = [
        r"\d+\s*mg/kg",
        r"\d+\s*mg/m[²2]",
        r"\d+\s*mg/dl",
        r"\d+\s*ml/min",
        r"\d+\s*g/l",
        r"\d+\s*iu/l",
        r"\d+\s*nmol/l",
        r"\d+\s*mcg/kg",
        r"\d+\s*µg/kg",
        r"\d+\s*u/ml",
        r"\d+\s*ng/ml",
        r"\d+\s*pg/ml",
    ]
    return any(re.search(pattern, normalized) for pattern in unit_patterns)


def is_and_pattern(text: str) -> bool:
    """
    Check if text uses 'and' (both required, NOT alternatives).

    IMPORTANT: If the text also contains alternative markers (/, or),
    it should NOT be filtered out - let the LLM analyze it.

    Examples:
    - "Informed Consent and Demographics" -> True (pure and, no alternatives)
    - "CT/MRI of the chest, abdomen, and pelvis" -> False (has / alternative)
    - "ECHO or MUGA and other tests" -> False (has 'or' alternative)
    """
    normalized = text.lower().strip()

    # Check for "and" but not "and/or" which IS an alternative
    if " and " not in normalized or "and/or" in normalized:
        return False

    # If text ALSO contains alternative markers, do NOT filter it out
    # The "/" or "or" takes precedence - let LLM analyze it
    alternative_markers = [" or ", "/"]
    has_alternative_marker = any(m in normalized for m in alternative_markers)

    if has_alternative_marker:
        return False  # Don't filter - contains alternatives worth analyzing

    return True  # Pure "and" pattern with no alternatives


def should_analyze_for_alternatives(text: str) -> bool:
    """
    Determine if activity text should be analyzed for alternatives.

    Priority order:
    1. Timing patterns (handled by Stage 7) -> skip
    2. Unit patterns (dosing units) -> skip
    3. Pure "and" patterns (no alternatives) -> skip
    4. Has alternative markers (/, or, either) -> ANALYZE
    """
    if is_timing_pattern(text):
        return False
    if is_unit_pattern(text):
        return False
    if is_and_pattern(text):
        return False

    # Check for potential alternative markers
    markers = [" or ", "/", "either", "one of"]
    normalized = text.lower()
    return any(marker in normalized for marker in markers)


def generate_activity_id(original_id: str, alternative_index: int, total_alternatives: int) -> str:
    """
    Generate deterministic activity ID for alternative expansion.

    Uses letter suffixes: ACT-001-A, ACT-001-B, ACT-001-C, etc.
    Falls back to numeric if > 26 alternatives.
    """
    if alternative_index <= 26:
        suffix = chr(ord('A') + alternative_index - 1)
    else:
        suffix = str(alternative_index)
    return f"{original_id}-{suffix}"


def generate_sai_id(original_id: str, alternative_suffix: str) -> str:
    """Generate deterministic SAI ID for alternative expansion."""
    return f"{original_id}-{alternative_suffix}"


def generate_condition_id(original_activity_id: str, alternative_index: int) -> str:
    """Generate deterministic Condition ID for alternative."""
    suffix = chr(ord('A') + alternative_index - 1) if alternative_index <= 26 else str(alternative_index)
    return f"COND-ALT-{original_activity_id.replace('ACT-', '')}-{suffix}"


def generate_assignment_id(condition_id: str, sai_id: str) -> str:
    """Generate deterministic ConditionAssignment ID."""
    # Use hash to keep ID short but deterministic
    key = f"{condition_id}:{sai_id}"
    hash_suffix = hashlib.md5(key.encode()).hexdigest()[:6].upper()
    return f"CA-ALT-{hash_suffix}"


# Note: Nested alternative resolution is handled by LLM in Stage 4.
# Pattern matching helpers were removed in favor of LLM-based analysis
# which provides better semantic understanding of compound terms
# (e.g., "PET/CT" is a single modality, "CT/MRI" is an alternative).
