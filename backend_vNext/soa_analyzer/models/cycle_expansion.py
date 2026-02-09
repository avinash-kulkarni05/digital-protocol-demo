"""
Cycle Expansion Models for Stage 8: Cycle Expansion

Data models for representing cycle patterns, expansion decisions, and results.
Handles ALL recurrence types: PER_CYCLE, FIXED_INTERVAL, AT_EVENT, CONDITIONAL.

Usage:
    from soa_analyzer.models.cycle_expansion import (
        CyclePatternType,
        CycleDecision,
        CycleExpansion,
        Stage8Result,
        CycleExpansionConfig,
    )

    decision = CycleDecision(
        encounter_name="Day 1 of Each Cycle",
        recurrence_key="PER_CYCLE:day=1:max=6",
        should_expand=True,
        expanded_cycles=[1, 2, 3, 4, 5, 6],
        confidence=0.95,
        rationale="Oncology cycle-based dosing with 6 treatment cycles",
    )
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import hashlib
import re
import uuid


class CyclePatternType(str, Enum):
    """Types of cycle/recurrence patterns found in protocols.

    EXPLICIT_RANGE: "Cycles 1-6" - enumerable range
    EXPLICIT_LIST: "Cycles 1, 2, 3" - explicit list
    STEADY_STATE: "Cycle 4+" - open-ended after threshold
    EVERY_N_CYCLES: "Every 3 cycles" - periodic pattern
    FIRST_ONLY: "Cycle 1 only" - non-expanding single occurrence
    ALL_CYCLES: "All cycles", "Each cycle" - requires max_cycles
    CONDITIONAL: "Until progression" - event-driven, cannot auto-expand
    FIXED_INTERVAL: "Every 3 weeks" - time-based, not cycle-based
    WEEK_BASED: "Week 1, 4, 8" - week enumeration
    """
    EXPLICIT_RANGE = "explicit_range"
    EXPLICIT_LIST = "explicit_list"
    STEADY_STATE = "steady_state"
    EVERY_N_CYCLES = "every_n_cycles"
    FIRST_ONLY = "first_only"
    ALL_CYCLES = "all_cycles"
    CONDITIONAL = "conditional"
    FIXED_INTERVAL = "fixed_interval"
    WEEK_BASED = "week_based"


@dataclass
class CyclePattern:
    """
    A known cycle pattern for validation purposes.

    Used to cross-check LLM decisions, NOT for primary routing (LLM-first).

    Example:
        pattern = CyclePattern(
            id="cycles_1_6",
            pattern_type=CyclePatternType.EXPLICIT_RANGE,
            pattern_regex=r"[Cc]ycles?\s*1[\-–]\s*6",
            expanded_cycles=[1, 2, 3, 4, 5, 6],
        )
    """
    id: str
    pattern_type: CyclePatternType
    pattern_regex: str
    expanded_cycles: List[int] = field(default_factory=list)
    description: Optional[str] = None
    cycle_length_days: Optional[int] = None  # Default cycle length if known

    def matches(self, text: str) -> bool:
        """Check if this pattern matches the input text."""
        if not text:
            return False
        return bool(re.search(self.pattern_regex, text, re.IGNORECASE))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "patternType": self.pattern_type.value,
            "patternRegex": self.pattern_regex,
            "expandedCycles": self.expanded_cycles,
            "description": self.description,
            "cycleLengthDays": self.cycle_length_days,
        }


@dataclass
class CycleDecision:
    """
    LLM decision for how to expand a cycle/recurrence pattern.

    This is what gets cached - the full decision with rationale.
    Cache key is based on encounter_name + recurrence_key for deduplication.

    Example:
        decision = CycleDecision(
            encounter_name="Day 1 of Each Cycle",
            recurrence_key="PER_CYCLE:day=1:max=6",
            should_expand=True,
            expanded_cycles=[1, 2, 3, 4, 5, 6],
            confidence=0.95,
            rationale="Oncology protocol with 6 treatment cycles",
        )
    """
    encounter_name: str
    recurrence_key: str  # Normalized key: "PER_CYCLE:day=1:max=6"
    should_expand: bool
    expanded_cycles: List[int] = field(default_factory=list)
    pattern_type: Optional[CyclePatternType] = None
    cycle_length_days: Optional[int] = None  # 21 for q3w, 28 for q4w, etc.
    confidence: float = 1.0
    rationale: Optional[str] = None
    source: str = "llm"  # "llm", "cache", "pattern", "open_ended_review"
    requires_human_review: bool = False
    review_reason: Optional[str] = None
    cached_at: Optional[str] = None
    model_name: Optional[str] = None
    # Provenance from original encounter
    provenance: Optional[Dict[str, Any]] = None
    # Whether this is an open-ended pattern (Cycle 4+, until progression)
    is_open_ended: bool = False
    # Protocol context (treatment duration, max cycles from study_metadata)
    protocol_context: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Set cached_at timestamp if not provided."""
        if self.cached_at is None:
            self.cached_at = datetime.utcnow().isoformat() + "Z"

    def get_cache_key(self) -> str:
        """Generate cache key from encounter name + recurrence key."""
        normalized = f"{self.encounter_name.lower().strip()}:{self.recurrence_key.lower().strip()}"
        return hashlib.md5(normalized.encode()).hexdigest()

    @staticmethod
    def build_recurrence_key(recurrence: Optional[Dict]) -> str:
        """Build normalized recurrence key from recurrence dict."""
        if not recurrence:
            return "NONE"

        rec_type = recurrence.get("type", "none").upper()

        if rec_type == "PER_CYCLE":
            day = recurrence.get("cycleDay", 1)
            max_cycles = recurrence.get("maxCycles", "unknown")
            return f"PER_CYCLE:day={day}:max={max_cycles}"
        elif rec_type == "FIXED_INTERVAL":
            value = recurrence.get("intervalValue", 1)
            unit = recurrence.get("intervalUnit", "weeks")
            return f"FIXED_INTERVAL:{value}_{unit}"
        elif rec_type == "AT_EVENT":
            event = recurrence.get("triggerEvent", "unknown")
            return f"AT_EVENT:{event}"
        elif rec_type == "CONDITIONAL":
            condition = recurrence.get("condition", "unknown")
            return f"CONDITIONAL:{condition}"
        else:
            return "NONE"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "encounterName": self.encounter_name,
            "recurrenceKey": self.recurrence_key,
            "shouldExpand": self.should_expand,
            "expandedCycles": self.expanded_cycles,
            "patternType": self.pattern_type.value if self.pattern_type else None,
            "cycleLengthDays": self.cycle_length_days,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "source": self.source,
            "requiresHumanReview": self.requires_human_review,
            "reviewReason": self.review_reason,
            "cachedAt": self.cached_at,
            "modelName": self.model_name,
            "provenance": self.provenance,
            "isOpenEnded": self.is_open_ended,
            "protocolContext": self.protocol_context,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CycleDecision":
        """Create from dictionary representation."""
        pattern_type = None
        if data.get("patternType"):
            try:
                pattern_type = CyclePatternType(data["patternType"])
            except ValueError:
                pass

        return cls(
            encounter_name=data.get("encounterName", ""),
            recurrence_key=data.get("recurrenceKey", ""),
            should_expand=data.get("shouldExpand", False),
            expanded_cycles=data.get("expandedCycles", []),
            pattern_type=pattern_type,
            cycle_length_days=data.get("cycleLengthDays"),
            confidence=data.get("confidence", 1.0),
            rationale=data.get("rationale"),
            source=data.get("source", "cache"),
            requires_human_review=data.get("requiresHumanReview", False),
            review_reason=data.get("reviewReason"),
            cached_at=data.get("cachedAt"),
            model_name=data.get("modelName"),
            provenance=data.get("provenance"),
            is_open_ended=data.get("isOpenEnded", False),
            protocol_context=data.get("protocolContext"),
        )

    @classmethod
    def create_review_required(
        cls,
        encounter_name: str,
        recurrence_key: str,
        reason: str,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> "CycleDecision":
        """Create a decision that requires human review (e.g., event-driven)."""
        return cls(
            encounter_name=encounter_name,
            recurrence_key=recurrence_key,
            should_expand=False,
            requires_human_review=True,
            review_reason=reason,
            confidence=0.0,
            source="review_required",
            provenance=provenance,
        )

    @classmethod
    def create_open_ended_review(
        cls,
        encounter_name: str,
        recurrence_key: str,
        start_cycle: int,
        cycle_length_days: Optional[int] = None,
        provenance: Optional[Dict[str, Any]] = None,
        protocol_context: Optional[Dict[str, Any]] = None,
    ) -> "CycleDecision":
        """
        Create a decision for open-ended patterns (Cycle 4+, until progression).

        These patterns should NOT be auto-expanded with arbitrary defaults.
        Instead, flag for human review with suggested options.
        """
        return cls(
            encounter_name=encounter_name,
            recurrence_key=recurrence_key,
            should_expand=False,  # DO NOT auto-expand
            expanded_cycles=[],
            pattern_type=CyclePatternType.STEADY_STATE,
            cycle_length_days=cycle_length_days,
            confidence=0.0,  # Zero confidence - requires human input
            rationale=f"Open-ended pattern starting at Cycle {start_cycle}. "
                      "Protocol specifies treatment until discontinuation - "
                      "no fixed maximum. Human input required to determine expansion.",
            source="open_ended_review",
            requires_human_review=True,
            review_reason=f"Open-ended cycle pattern (Cycle {start_cycle}+) cannot be auto-expanded. "
                         "Protocol does not specify a maximum cycle count.",
            provenance=provenance,
            is_open_ended=True,
            protocol_context=protocol_context,
        )


@dataclass
class CycleExpansion:
    """
    Result of expanding a single encounter's cycle pattern.

    Tracks lineage from original encounter to expanded encounters for audit trail.

    Example:
        expansion = CycleExpansion(
            original_encounter_id="ENC-001",
            original_name="Day 1 of Each Cycle",
            expanded_encounters=[
                {"id": "ENC-001-C1", "name": "Cycle 1 Day 1", ...},
                {"id": "ENC-001-C2", "name": "Cycle 2 Day 1", ...},
            ],
            expanded_sai_ids=["SAI-001-C1", "SAI-001-C2", ...],
            decision=decision,
        )
    """
    id: str = field(default_factory=lambda: f"CEXP-{uuid.uuid4().hex[:8].upper()}")
    original_encounter_id: str = ""
    original_name: str = ""
    original_recurrence: Optional[Dict[str, Any]] = None
    expanded_encounters: List[Dict[str, Any]] = field(default_factory=list)
    expanded_sai_ids: List[str] = field(default_factory=list)  # SAIs duplicated for cycles
    decision: Optional[CycleDecision] = None
    requires_review: bool = False
    review_reason: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None

    @property
    def expansion_count(self) -> int:
        """Number of expanded encounters created."""
        return len(self.expanded_encounters)

    @property
    def sai_duplication_count(self) -> int:
        """Number of SAIs duplicated for cycle expansion."""
        return len(self.expanded_sai_ids)

    @property
    def confidence(self) -> float:
        """Confidence from the decision."""
        return self.decision.confidence if self.decision else 0.0

    @property
    def expanded_cycle_numbers(self) -> List[int]:
        """List of cycle numbers from expanded encounters."""
        if self.decision:
            return self.decision.expanded_cycles
        return []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "originalEncounterId": self.original_encounter_id,
            "originalName": self.original_name,
            "originalRecurrence": self.original_recurrence,
            "expandedEncounterCount": self.expansion_count,
            "expandedEncounterIds": [enc.get("id", "") for enc in self.expanded_encounters],
            "expandedCycleNumbers": self.expanded_cycle_numbers,
            "saiDuplicationCount": self.sai_duplication_count,
            "expandedSaiIds": self.expanded_sai_ids,
            "confidence": self.confidence,
            "source": self.decision.source if self.decision else None,
            "rationale": self.decision.rationale if self.decision else None,
            "requiresReview": self.requires_review,
            "reviewReason": self.review_reason,
            "provenance": self.provenance,
        }


@dataclass
class CycleValidationDiscrepancy:
    """
    A discrepancy between LLM decision and known validation pattern.

    Used for flagging and human review.
    """
    encounter_name: str
    recurrence_key: str
    llm_cycles: List[int]  # What LLM said
    pattern_cycles: List[int]  # What pattern says
    pattern_id: str
    severity: str = "warning"  # "info", "warning", "error"
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "encounterName": self.encounter_name,
            "recurrenceKey": self.recurrence_key,
            "llmCycles": self.llm_cycles,
            "patternCycles": self.pattern_cycles,
            "patternId": self.pattern_id,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class HumanReviewItem:
    """
    An item flagged for human review.

    Used for event-driven cycles, low-confidence decisions, etc.
    """
    id: str = field(default_factory=lambda: f"REV-{uuid.uuid4().hex[:8].upper()}")
    encounter_id: str = ""
    encounter_name: str = ""
    recurrence_key: str = ""
    reason: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    suggested_action: Optional[str] = None
    priority: str = "medium"  # "low", "medium", "high"
    stage: str = "Stage8CycleExpansion"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "encounterId": self.encounter_id,
            "encounterName": self.encounter_name,
            "recurrenceKey": self.recurrence_key,
            "reason": self.reason,
            "context": self.context,
            "suggestedAction": self.suggested_action,
            "priority": self.priority,
            "stage": self.stage,
            "createdAt": self.created_at,
        }


@dataclass
class Stage8Result:
    """
    Result of Stage 8 cycle expansion processing.

    Contains all expansions, review items, and metrics.
    """
    expansions: List[CycleExpansion] = field(default_factory=list)
    decisions: Dict[str, CycleDecision] = field(default_factory=dict)  # cache_key -> decision
    discrepancies: List[CycleValidationDiscrepancy] = field(default_factory=list)
    review_items: List[HumanReviewItem] = field(default_factory=list)

    # Metrics
    encounters_processed: int = 0          # Total encounters checked
    encounters_with_recurrence: int = 0    # Encounters with recurrence patterns
    encounters_expanded: int = 0           # Encounters that were expanded
    encounters_created: int = 0            # New encounters created (total)
    encounters_skipped: int = 0            # Encounters skipped (no recurrence, already expanded)
    sais_processed: int = 0                # SAIs checked for duplication
    sais_duplicated: int = 0               # SAIs that were duplicated
    sais_created: int = 0                  # New SAIs created from duplication
    unique_patterns_analyzed: int = 0      # Unique recurrence patterns sent to LLM
    cache_hits: int = 0                    # Patterns found in cache
    llm_calls: int = 0                     # LLM API calls made
    validation_flags: int = 0              # LLM vs pattern discrepancies
    event_driven_flagged: int = 0          # AT_EVENT encounters flagged for review

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of cycle expansion."""
        expansion_rate = (
            self.encounters_expanded / max(self.encounters_with_recurrence, 1)
        )
        return {
            "encountersProcessed": self.encounters_processed,
            "encountersWithRecurrence": self.encounters_with_recurrence,
            "encountersExpanded": self.encounters_expanded,
            "encountersCreated": self.encounters_created,
            "encountersSkipped": self.encounters_skipped,
            "saisProcessed": self.sais_processed,
            "saisDuplicated": self.sais_duplicated,
            "saisCreated": self.sais_created,
            "uniquePatternsAnalyzed": self.unique_patterns_analyzed,
            "cacheHits": self.cache_hits,
            "llmCalls": self.llm_calls,
            "validationFlags": self.validation_flags,
            "eventDrivenFlagged": self.event_driven_flagged,
            "reviewItemsCount": len(self.review_items),
            "expansionRate": round(expansion_rate, 3),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "stage": 8,
            "stageName": "Cycle Expansion",
            "success": True,
            "expansions": [e.to_dict() for e in self.expansions],
            "decisions": {k: v.to_dict() for k, v in self.decisions.items()},
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "reviewItems": [r.to_dict() for r in self.review_items],
            "metrics": self.get_summary(),
        }

    def add_expansion(self, expansion: CycleExpansion) -> None:
        """Add an expansion and update metrics."""
        self.expansions.append(expansion)
        self.encounters_expanded += 1
        self.encounters_created += expansion.expansion_count
        self.sais_duplicated += 1 if expansion.sai_duplication_count > 0 else 0
        self.sais_created += expansion.sai_duplication_count

        if expansion.requires_review:
            self.review_items.append(HumanReviewItem(
                encounter_id=expansion.original_encounter_id,
                encounter_name=expansion.original_name,
                recurrence_key=expansion.decision.recurrence_key if expansion.decision else "",
                reason=expansion.review_reason or "Low confidence expansion",
                priority="medium",
            ))

    def add_event_driven_review(
        self,
        encounter: Dict[str, Any],
        reason: str,
    ) -> None:
        """Add an event-driven encounter to review queue."""
        self.event_driven_flagged += 1
        self.review_items.append(HumanReviewItem(
            encounter_id=encounter.get("id", ""),
            encounter_name=encounter.get("name", ""),
            recurrence_key=CycleDecision.build_recurrence_key(encounter.get("recurrence")),
            reason=reason,
            context={
                "recurrence": encounter.get("recurrence"),
                "originalEncounter": {
                    k: v for k, v in encounter.items()
                    if k not in ("_cycleExpansion",)
                },
            },
            suggested_action="Manually specify max_cycles or convert to explicit cycle list",
            priority="high",
        ))


@dataclass
class CycleExpansionConfig:
    """
    Configuration for Stage 8 cycle expansion.
    """
    # LLM settings
    use_llm: bool = True
    model_name: str = "gemini-2.5-pro"
    fallback_model: str = "gpt-5-mini"
    max_output_tokens: int = 8192
    temperature: float = 0.1
    max_retries: int = 3

    # Batch processing
    max_patterns_per_batch: int = 15  # ~50 tokens per pattern, stay under token limit

    # Confidence thresholds
    confidence_threshold_auto: float = 0.90  # Auto-apply if >= this
    confidence_threshold_review: float = 0.70  # Flag for review if below this

    # Expansion limits
    max_cycles_if_unknown: int = 12  # Default max cycles when not specified (only used if auto_expand_open_ended=True)
    steady_state_threshold: int = 4  # Cycles 4+ become steady-state representative

    # Open-ended pattern handling (CRITICAL)
    auto_expand_open_ended: bool = False  # DO NOT auto-expand Cycle 4+, until progression, etc.

    # Cycle length defaults (days)
    default_cycle_length: int = 21  # 3-week cycles
    cycle_length_map: Dict[str, int] = field(default_factory=lambda: {
        "q3w": 21,
        "q4w": 28,
        "q2w": 14,
        "weekly": 7,
        "monthly": 28,
    })

    # Validation
    validate_against_patterns: bool = True
    flag_discrepancies: bool = True

    # Non-expandable visit types (skip these)
    non_expandable_visit_types: Set[str] = field(default_factory=lambda: {
        "Screening",
        "Baseline",
        "End of Treatment",
        "EOT",
        "Follow-up",
        "Early Termination",
        "Unscheduled",
    })

    # Open-ended patterns (DO NOT auto-expand these)
    open_ended_patterns: Set[str] = field(default_factory=lambda: {
        "subsequent",
        "and subsequent",
        "cycle 4+",
        "cycles 4+",
        "cycle 5+",
        "cycle 6+",
        "onwards",
        "and beyond",
        "until progression",
        "until discontinuation",
        "until pd",
        "as long as",
    })

    # Caching
    use_cache: bool = True
    cache_dir: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "useLlm": self.use_llm,
            "modelName": self.model_name,
            "fallbackModel": self.fallback_model,
            "maxPatternsPerBatch": self.max_patterns_per_batch,
            "confidenceThresholdAuto": self.confidence_threshold_auto,
            "confidenceThresholdReview": self.confidence_threshold_review,
            "maxCyclesIfUnknown": self.max_cycles_if_unknown,
            "steadyStateThreshold": self.steady_state_threshold,
            "autoExpandOpenEnded": self.auto_expand_open_ended,
            "defaultCycleLength": self.default_cycle_length,
            "validateAgainstPatterns": self.validate_against_patterns,
            "nonExpandableVisitTypes": list(self.non_expandable_visit_types),
            "openEndedPatterns": list(self.open_ended_patterns),
            "useCache": self.use_cache,
        }

    def is_open_ended_pattern(self, encounter_name: str) -> bool:
        """Check if an encounter name matches an open-ended pattern."""
        name_lower = encounter_name.lower()
        for pattern in self.open_ended_patterns:
            if pattern.lower() in name_lower:
                return True
        return False


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def is_already_expanded(encounter: Dict[str, Any]) -> bool:
    """Check if encounter has already been cycle-expanded."""
    # Check for expansion metadata
    if encounter.get("_cycleExpansion"):
        return True

    # Check for cycle suffix in ID (e.g., ENC-001-C3)
    enc_id = encounter.get("id", "")
    if re.match(r".*-C\d+$", enc_id):
        return True

    return False


def should_skip_expansion(
    encounter: Dict[str, Any],
    config: CycleExpansionConfig,
) -> tuple[bool, str]:
    """
    Determine if an encounter should be skipped for expansion.

    Returns:
        Tuple of (should_skip, reason)
    """
    # Already expanded
    if is_already_expanded(encounter):
        return True, "Already expanded"

    # No recurrence pattern
    recurrence = encounter.get("recurrence")
    if not recurrence:
        return True, "No recurrence pattern"

    rec_type = recurrence.get("type", "none").lower()
    if rec_type == "none":
        return True, "Recurrence type is none"

    # Non-expandable visit type
    enc_name = encounter.get("name", "")
    for skip_type in config.non_expandable_visit_types:
        if skip_type.lower() in enc_name.lower():
            return True, f"Non-expandable visit type: {skip_type}"

    # "Cycle 1 only" pattern
    if "only" in enc_name.lower() and ("cycle 1" in enc_name.lower() or "c1" in enc_name.lower()):
        return True, "Explicit 'Cycle 1 only' - single occurrence"

    return False, ""


def parse_cycle_range(range_str: str) -> List[int]:
    """
    Parse a cycle range string into list of cycle numbers.

    Examples:
        "Cycles 1-6" -> [1, 2, 3, 4, 5, 6]
        "Cycles 1, 2, 3" -> [1, 2, 3]
        "C1-C6" -> [1, 2, 3, 4, 5, 6]
    """
    cycles = []

    # Handle range notation (1-6, 1–6)
    range_match = re.search(r"(\d+)\s*[-–]\s*(\d+)", range_str)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        return list(range(start, end + 1))

    # Handle list notation (1, 2, 3)
    list_match = re.findall(r"\d+", range_str)
    if list_match:
        return [int(x) for x in list_match]

    return cycles
