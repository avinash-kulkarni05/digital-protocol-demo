"""
Timing Models for Protocol-Agnostic SOA Visit Schedule Generation

This module defines the core data structures for representing visit schedules,
timing windows, recurrence patterns, and footnote rules across all protocol types:
- Fixed Duration (Day 1, Day 8, Day 15...)
- Cycle-Based (Cycle 1 Day 1, C2D1...)
- Event-Driven (Screening, Baseline, EOT, Follow-up)
- Adaptive (conditional visits, interim analyses)
- Window-Based (Week 4 ±3 days)
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# ENUMERATIONS
# =============================================================================


class TimingReferencePoint(str, Enum):
    """All possible timing anchors across protocol types.

    These represent the reference point from which visit timing is calculated.
    Different protocol types use different primary anchors.
    """
    STUDY_START = "study_start"                 # Day 1 of study
    SCREENING = "screening"                     # Screening visit
    RANDOMIZATION = "randomization"             # Randomization date
    BASELINE = "baseline"                       # Baseline visit (may = Day 1)
    FIRST_DOSE = "first_dose"                   # First study drug administration
    LAST_DOSE = "last_dose"                     # Last study drug administration
    CYCLE_START = "cycle_start"                 # Start of treatment cycle (oncology)
    END_OF_TREATMENT = "end_of_treatment"       # EOT visit
    INTERIM_ANALYSIS = "interim_analysis"       # For adaptive trials
    DISEASE_PROGRESSION = "disease_progression" # Event-driven oncology
    PREVIOUS_VISIT = "previous_visit"           # Relative to last completed visit
    CUSTOM = "custom"                           # Protocol-specific anchor

    @classmethod
    def from_text(cls, text: str) -> "TimingReferencePoint":
        """Parse reference point from footnote text."""
        text_lower = text.lower()

        if "randomization" in text_lower or "randomiz" in text_lower:
            return cls.RANDOMIZATION
        elif "first dose" in text_lower or "first drug" in text_lower:
            return cls.FIRST_DOSE
        elif "last dose" in text_lower or "final dose" in text_lower:
            return cls.LAST_DOSE
        elif "baseline" in text_lower:
            return cls.BASELINE
        elif "screening" in text_lower:
            return cls.SCREENING
        elif "day 1" in text_lower or "day1" in text_lower:
            return cls.STUDY_START
        elif "cycle" in text_lower:
            return cls.CYCLE_START
        elif "end of treatment" in text_lower or "eot" in text_lower:
            return cls.END_OF_TREATMENT
        elif "progression" in text_lower:
            return cls.DISEASE_PROGRESSION
        elif "interim" in text_lower:
            return cls.INTERIM_ANALYSIS
        else:
            return cls.STUDY_START  # Default


class WindowType(str, Enum):
    """Types of visit windows."""
    EXACT = "exact"           # Visit must occur on exact day
    BILATERAL = "bilateral"   # Visit can occur ±N days (symmetric)
    EARLY_ONLY = "early_only" # Visit can occur up to N days early, not late
    LATE_ONLY = "late_only"   # Visit can occur up to N days late, not early
    ASYMMETRIC = "asymmetric" # Different early and late bounds


class VisitType(str, Enum):
    """Clinical visit type classification."""
    SCREENING = "screening"
    BASELINE = "baseline"
    TREATMENT = "treatment"
    FOLLOW_UP = "follow_up"
    END_OF_TREATMENT = "end_of_treatment"
    UNSCHEDULED = "unscheduled"
    INTERIM = "interim"
    SAFETY = "safety"
    PHARMACOKINETIC = "pharmacokinetic"
    SURVIVAL = "survival"
    MAINTENANCE = "maintenance"

    @classmethod
    def from_visit_name(cls, name: str) -> "VisitType":
        """Infer visit type from visit name."""
        name_lower = name.lower()

        if "screen" in name_lower or "scr" == name_lower:
            return cls.SCREENING
        elif "baseline" in name_lower:
            return cls.BASELINE
        elif "follow" in name_lower or "fu" in name_lower:
            return cls.FOLLOW_UP
        elif "end of treatment" in name_lower or "eot" in name_lower or "final" in name_lower:
            return cls.END_OF_TREATMENT
        elif "unscheduled" in name_lower:
            return cls.UNSCHEDULED
        elif "interim" in name_lower:
            return cls.INTERIM
        elif "safety" in name_lower:
            return cls.SAFETY
        elif "pk" in name_lower or "pharmacokinetic" in name_lower:
            return cls.PHARMACOKINETIC
        elif "survival" in name_lower:
            return cls.SURVIVAL
        elif "maintenance" in name_lower:
            return cls.MAINTENANCE
        elif "cycle" in name_lower or "day" in name_lower or "week" in name_lower:
            return cls.TREATMENT
        else:
            return cls.TREATMENT  # Default


class RecurrenceType(str, Enum):
    """How a visit repeats across the study."""
    NONE = "none"                   # Single occurrence
    PER_CYCLE = "per_cycle"         # Repeats each treatment cycle
    FIXED_INTERVAL = "fixed_interval"  # Repeats every N days/weeks
    AT_EVENT = "at_event"           # Triggered by clinical event
    CONDITIONAL = "conditional"     # Occurs only if condition met


class ProtocolType(str, Enum):
    """Protocol type classification for visit schedule patterns."""
    FIXED_DURATION = "fixed_duration"   # Day 1, Day 8, Day 15...
    CYCLE_BASED = "cycle_based"         # Cycle 1 Day 1, C2D1...
    EVENT_DRIVEN = "event_driven"       # Screening, Baseline, EOT, Follow-up
    ADAPTIVE = "adaptive"               # Conditional visits, interim analyses
    HYBRID = "hybrid"                   # Combination of patterns


class FootnoteRuleType(str, Enum):
    """Types of rules extracted from SOA table footnotes."""
    VISIT_WINDOW = "visit_window"           # "within 28 days", "±3 days"
    CONDITIONAL_TRIGGER = "conditional"     # "if clinically indicated", "if female"
    SPECIMEN_VARIANT = "specimen_variant"   # "12mL at V1, 6mL at V2"
    TIMING_CONSTRAINT = "timing_constraint" # "pre-dose", "2h post-dose", "fasting"
    FREQUENCY_MODIFIER = "frequency"        # "every 2 cycles", "q3 weeks"
    ABBREVIATION = "abbreviation"           # "SCR = Screening" (ignore for rules)
    GENERAL_NOTE = "general_note"           # Non-actionable informational text


class FootnoteLinkingStrategy(str, Enum):
    """Strategy used for linking footnotes to cells."""
    LLM_CELL_LEVEL = "llm_cell"        # Best: LLM-based precise cell linking
    LLM_SEMANTIC = "llm_semantic"      # Good: LLM semantic matching without cell coords
    EXISTING_HEURISTIC = "heuristic"   # Fallback: Current text pattern matching
    NONE = "none"                      # Failed: No linking possible


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class Provenance:
    """Source tracking for extracted data."""
    page_number: Optional[int] = None
    text_snippet: Optional[str] = None
    table_id: Optional[int] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pageNumber": self.page_number,
            "textSnippet": self.text_snippet[:150] if self.text_snippet else None,
            "tableId": self.table_id,
            "confidence": self.confidence,
        }


# =============================================================================
# CELL-LEVEL TRACKING STRUCTURES
# =============================================================================


@dataclass
class CellPosition:
    """Exact cell location in SOA table grid.

    Provides precise coordinates for cell-level provenance tracking
    and footnote marker linking.
    """
    table_id: str
    page_number: int
    row_idx: int
    col_idx: int
    row_span: int = 1
    col_span: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tableId": self.table_id,
            "pageNumber": self.page_number,
            "row": self.row_idx,
            "col": self.col_idx,
            "rowSpan": self.row_span,
            "colSpan": self.col_span,
        }

    @property
    def cell_id(self) -> str:
        """Unique identifier for this cell."""
        return f"{self.table_id}_r{self.row_idx}_c{self.col_idx}"


@dataclass
class CellContent:
    """Parsed content of a single table cell.

    Contains both raw and normalized text, extracted footnote markers,
    and cell type classification.
    """
    position: CellPosition
    raw_text: str
    normalized_text: str
    footnote_markers: List[str] = field(default_factory=list)
    is_header: bool = False
    is_activity_label: bool = False
    cell_type: str = "data"  # header|activity|checkmark|empty

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": self.position.to_dict(),
            "rawText": self.raw_text,
            "normalizedText": self.normalized_text,
            "footnoteMarkers": self.footnote_markers,
            "isHeader": self.is_header,
            "isActivityLabel": self.is_activity_label,
            "cellType": self.cell_type,
        }


@dataclass
class TableGrid:
    """Parsed SOA table with cell coordinates.

    Represents a complete SOA table as a grid with row/column mappings
    to activities and visits, plus a marker-to-cell index for linking.
    """
    table_id: str
    page_number: int
    cells: List[CellContent] = field(default_factory=list)
    num_rows: int = 0
    num_cols: int = 0
    row_to_activity: Dict[int, str] = field(default_factory=dict)
    col_to_visit: Dict[int, str] = field(default_factory=dict)
    marker_to_cells: Dict[str, List[CellPosition]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tableId": self.table_id,
            "pageNumber": self.page_number,
            "numRows": self.num_rows,
            "numCols": self.num_cols,
            "rowToActivity": self.row_to_activity,
            "colToVisit": self.col_to_visit,
            "markerToCells": {
                m: [c.to_dict() for c in cells]
                for m, cells in self.marker_to_cells.items()
            },
            "cells": [c.to_dict() for c in self.cells],
        }

    def get_cell(self, row: int, col: int) -> Optional[CellContent]:
        """Get cell at specified row/column."""
        for cell in self.cells:
            if cell.position.row_idx == row and cell.position.col_idx == col:
                return cell
        return None

    def get_header_row(self) -> List[CellContent]:
        """Get all cells in the header row(s)."""
        return [c for c in self.cells if c.is_header]

    def get_activity_column(self) -> List[CellContent]:
        """Get all cells in the activity label column."""
        return [c for c in self.cells if c.is_activity_label]


@dataclass
class LinkedFootnote:
    """Footnote with precise cell linkage.

    Links a footnote marker to specific table cells and determines
    the scope (column-wide, row-wide, or cell-specific).
    """
    footnote_id: str
    marker: str
    rule_type: FootnoteRuleType
    structured_rule: Dict[str, Any] = field(default_factory=dict)
    linked_cells: List[CellPosition] = field(default_factory=list)
    applies_to_activities: List[str] = field(default_factory=list)
    applies_to_visits: List[str] = field(default_factory=list)
    is_column_wide: bool = False
    is_row_wide: bool = False
    linkage_confidence: float = 1.0
    needs_review: bool = False
    review_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "footnoteId": self.footnote_id,
            "marker": self.marker,
            "ruleType": self.rule_type.value,
            "structuredRule": self.structured_rule,
            "linkedCells": [c.to_dict() for c in self.linked_cells],
            "appliesToActivities": self.applies_to_activities,
            "appliesToVisits": self.applies_to_visits,
            "isColumnWide": self.is_column_wide,
            "isRowWide": self.is_row_wide,
            "linkageConfidence": self.linkage_confidence,
            "needsReview": self.needs_review,
            "reviewReason": self.review_reason,
        }

    @property
    def scope(self) -> str:
        """Return the linking scope as a string."""
        if self.is_column_wide:
            return "column_wide"
        elif self.is_row_wide:
            return "row_wide"
        else:
            return "cell_specific"


@dataclass
class FootnoteLinkageResult:
    """Result of cell-level footnote linking.

    Contains linked footnotes, quality metrics, and the strategy used.
    """
    linked_footnotes: List[LinkedFootnote] = field(default_factory=list)
    total_markers: int = 0
    markers_linked: int = 0
    ambiguous_markers: int = 0
    column_wide_count: int = 0
    row_wide_count: int = 0
    cell_specific_count: int = 0
    strategy_used: FootnoteLinkingStrategy = FootnoteLinkingStrategy.NONE
    use_fallback: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "linkedFootnotes": [f.to_dict() for f in self.linked_footnotes],
            "totalMarkers": self.total_markers,
            "markersLinked": self.markers_linked,
            "ambiguousMarkers": self.ambiguous_markers,
            "columnWideCount": self.column_wide_count,
            "rowWideCount": self.row_wide_count,
            "cellSpecificCount": self.cell_specific_count,
            "strategyUsed": self.strategy_used.value,
            "useFallback": self.use_fallback,
            "linkingQuality": self.linking_quality,
        }

    @property
    def linking_quality(self) -> float:
        """Calculate overall linking quality score (0-1)."""
        if self.total_markers == 0:
            return 1.0  # No markers to link

        coverage_score = (self.markers_linked / self.total_markers) * 0.4
        precision_score = (1 - self.ambiguous_markers / max(self.markers_linked, 1)) * 0.3

        # Calculate high confidence ratio
        high_conf = sum(1 for f in self.linked_footnotes if f.linkage_confidence >= 0.8)
        confidence_score = (high_conf / max(self.markers_linked, 1)) * 0.3

        return coverage_score + precision_score + confidence_score

    @property
    def linked_markers(self) -> set:
        """Set of successfully linked markers."""
        return {f.marker for f in self.linked_footnotes if f.linked_cells}


# =============================================================================
# TIMING STRUCTURES
# =============================================================================


@dataclass
class TimingWindow:
    """Structured visit window specification.

    Represents when a visit can occur relative to its nominal timing.

    Examples:
        - "Day 28 ±3 days" → target_value=28, early_bound=3, late_bound=3
        - "Within 28 days prior to randomization" → target_value=0, early_bound=28, late_bound=0
        - "No later than 30 days after last dose" → target_value=30, early_bound=0, late_bound=0
    """
    type: WindowType = WindowType.EXACT
    target_value: int = 0               # Nominal timing value (e.g., 28 for Day 28)
    target_unit: str = "days"           # days, weeks, cycles
    early_bound: Optional[int] = None   # How early can occur (None = no limit)
    late_bound: Optional[int] = None    # How late can occur (None = no limit)
    relative_to: TimingReferencePoint = TimingReferencePoint.STUDY_START
    description: Optional[str] = None   # Original text for reference

    def to_date_range(self, anchor_date: date) -> Tuple[date, date]:
        """Calculate actual date range given an anchor date.

        Args:
            anchor_date: The reference date (e.g., randomization date)

        Returns:
            Tuple of (earliest_date, latest_date)
        """
        # Convert target to days
        days = self.target_value
        if self.target_unit == "weeks":
            days = self.target_value * 7
        elif self.target_unit == "cycles":
            # Assume 21-day cycles by default (can be overridden)
            days = self.target_value * 21

        target_date = anchor_date + timedelta(days=days)

        early_days = self.early_bound or 0
        late_days = self.late_bound or 0

        earliest_date = target_date - timedelta(days=early_days)
        latest_date = target_date + timedelta(days=late_days)

        return (earliest_date, latest_date)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "targetValue": self.target_value,
            "targetUnit": self.target_unit,
            "earlyBound": self.early_bound,
            "lateBound": self.late_bound,
            "relativeTo": self.relative_to.value,
            "description": self.description,
        }

    @classmethod
    def from_bilateral(
        cls,
        target: int,
        tolerance: int,
        unit: str = "days",
        relative_to: TimingReferencePoint = TimingReferencePoint.STUDY_START,
    ) -> "TimingWindow":
        """Create a bilateral window (±N days)."""
        return cls(
            type=WindowType.BILATERAL,
            target_value=target,
            target_unit=unit,
            early_bound=tolerance,
            late_bound=tolerance,
            relative_to=relative_to,
            description=f"{target} {unit} ±{tolerance} {unit}",
        )

    @classmethod
    def from_within(
        cls,
        days: int,
        relative_to: TimingReferencePoint,
        before: bool = True,
    ) -> "TimingWindow":
        """Create a 'within N days of X' window."""
        if before:
            return cls(
                type=WindowType.EARLY_ONLY,
                target_value=0,
                target_unit="days",
                early_bound=days,
                late_bound=0,
                relative_to=relative_to,
                description=f"within {days} days prior to {relative_to.value}",
            )
        else:
            return cls(
                type=WindowType.LATE_ONLY,
                target_value=0,
                target_unit="days",
                early_bound=0,
                late_bound=days,
                relative_to=relative_to,
                description=f"within {days} days after {relative_to.value}",
            )


@dataclass
class RecurrenceRule:
    """How a visit repeats throughout the study.

    Examples:
        - Per-cycle: Visit occurs on Day 1 of each treatment cycle
        - Fixed-interval: Visit occurs every 3 weeks
        - At-event: Visit triggered by disease progression
    """
    type: RecurrenceType = RecurrenceType.NONE

    # For PER_CYCLE: which day within each cycle
    cycle_day: Optional[int] = None
    max_cycles: Optional[int] = None

    # For FIXED_INTERVAL: every N units
    interval_value: Optional[int] = None
    interval_unit: Optional[str] = None  # days, weeks, months

    # For AT_EVENT: triggered by what
    trigger_event: Optional[str] = None

    # For CONDITIONAL
    condition: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "cycleDay": self.cycle_day,
            "maxCycles": self.max_cycles,
            "intervalValue": self.interval_value,
            "intervalUnit": self.interval_unit,
            "triggerEvent": self.trigger_event,
            "condition": self.condition,
        }

    @classmethod
    def per_cycle(cls, day: int, max_cycles: Optional[int] = None) -> "RecurrenceRule":
        """Create a per-cycle recurrence rule."""
        return cls(
            type=RecurrenceType.PER_CYCLE,
            cycle_day=day,
            max_cycles=max_cycles,
        )

    @classmethod
    def fixed_interval(cls, value: int, unit: str) -> "RecurrenceRule":
        """Create a fixed-interval recurrence rule."""
        return cls(
            type=RecurrenceType.FIXED_INTERVAL,
            interval_value=value,
            interval_unit=unit,
        )


@dataclass
class VisitClassification:
    """Extended visit classification for protocol-agnostic handling.

    Captures not just the visit type, but also recurrence patterns,
    applicability rules, and review flags.
    """
    # Basic type
    visit_type: VisitType = VisitType.TREATMENT

    # Recurrence
    is_required: bool = True
    is_repeating: bool = False
    recurrence_rule: Optional[RecurrenceRule] = None

    # Applicability
    applies_to_arms: List[str] = field(default_factory=lambda: ["all"])
    applies_to_populations: List[str] = field(default_factory=lambda: ["all"])
    conditional_logic: Optional[str] = None  # Free text for complex conditions

    # Review flags
    needs_review: bool = False
    review_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "visitType": self.visit_type.value,
            "isRequired": self.is_required,
            "isRepeating": self.is_repeating,
            "recurrenceRule": self.recurrence_rule.to_dict() if self.recurrence_rule else None,
            "appliesToArms": self.applies_to_arms,
            "appliesToPopulations": self.applies_to_populations,
            "conditionalLogic": self.conditional_logic,
            "needsReview": self.needs_review,
            "reviewReason": self.review_reason,
        }


@dataclass
class CanonicalVisit:
    """Canonical representation of a visit parsed from SOA table.

    This is the intermediate representation between raw SOA extraction
    and the final USDM Encounter structure.
    """
    id: str
    name: str
    original_name: str  # As it appeared in SOA table

    # Type classification
    visit_type: VisitType = VisitType.TREATMENT

    # Timing
    timing_value: Optional[int] = None
    timing_unit: str = "days"
    relative_to: TimingReferencePoint = TimingReferencePoint.STUDY_START
    window: Optional[TimingWindow] = None

    # For cycle-based visits
    cycle_number: Optional[int] = None
    day_in_cycle: Optional[int] = None

    # Classification
    classification: Optional[VisitClassification] = None

    # Footnote linkage
    footnote_markers: List[str] = field(default_factory=list)
    footnote_ids: List[str] = field(default_factory=list)

    # Provenance
    provenance: Optional[Provenance] = None

    # Review flags
    needs_review: bool = False
    review_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "originalName": self.original_name,
            "visitType": self.visit_type.value,
            "timing": {
                "value": self.timing_value,
                "unit": self.timing_unit,
                "relativeTo": self.relative_to.value,
                "window": self.window.to_dict() if self.window else None,
            },
            "cycleNumber": self.cycle_number,
            "dayInCycle": self.day_in_cycle,
            "classification": self.classification.to_dict() if self.classification else None,
            "footnoteMarkers": self.footnote_markers,
            "footnoteIds": self.footnote_ids,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "needsReview": self.needs_review,
            "reviewReason": self.review_reason,
        }

    def to_usdm_encounter(self) -> Dict[str, Any]:
        """Convert to USDM 4.0 Encounter format."""
        # CDISC visit type codes
        visit_type_codes = {
            VisitType.SCREENING: ("C48262", "Screening"),
            VisitType.BASELINE: ("C25213", "Baseline"),
            VisitType.TREATMENT: ("C71738", "Treatment"),
            VisitType.FOLLOW_UP: ("C99158", "Follow-up"),
            VisitType.END_OF_TREATMENT: ("C99159", "End of Treatment"),
            VisitType.UNSCHEDULED: ("C99160", "Unscheduled"),
            VisitType.SAFETY: ("C99161", "Safety"),
        }

        code, decode = visit_type_codes.get(
            self.visit_type,
            ("C71738", "Treatment")  # Default
        )

        encounter = {
            "id": self.id,
            "name": self.name,
            "instanceType": "Encounter",
            "type": {
                "code": code,
                "decode": decode,
            },
            "timing": {
                "value": self.timing_value,
                "unit": self.timing_unit,
                "relativeTo": self.relative_to.value,
            },
            "classification": self.classification.to_dict() if self.classification else None,
            "footnoteReferences": self.footnote_ids,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "needsReview": self.needs_review,
            "reviewReason": self.review_reason,
        }

        if self.window:
            encounter["timing"]["window"] = self.window.to_dict()

        return encounter


@dataclass
class FootnoteRule:
    """Structured rule extracted from a SOA table footnote.

    Footnotes contain critical information for visit scheduling:
    - Visit windows (±N days)
    - Conditional triggers (if clinically indicated)
    - Specimen variants (12mL at V1, 6mL at V2)
    - Timing constraints (pre-dose, fasting)
    """
    id: str
    marker: str  # a, b, c, 1, 2, *, etc.
    raw_text: str
    rule_type: FootnoteRuleType

    # Page reference
    page_number: Optional[int] = None
    source_table_id: Optional[int] = None

    # Structured rule (varies by type)
    structured_rule: Dict[str, Any] = field(default_factory=dict)

    # What this rule applies to
    applies_to_type: str = "visit"  # visit, activity, both
    applies_to_names: List[str] = field(default_factory=list)
    applies_to_ids: List[str] = field(default_factory=list)

    # Quality
    confidence: float = 1.0
    needs_review: bool = False
    review_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "marker": self.marker,
            "rawText": self.raw_text,
            "ruleType": self.rule_type.value,
            "pageNumber": self.page_number,
            "sourceTableId": self.source_table_id,
            "structuredRule": self.structured_rule,
            "appliesTo": {
                "type": self.applies_to_type,
                "names": self.applies_to_names,
                "ids": self.applies_to_ids,
            },
            "confidence": self.confidence,
            "needsReview": self.needs_review,
            "reviewReason": self.review_reason,
        }


# =============================================================================
# RESULT CONTAINERS
# =============================================================================


@dataclass
class FootnoteExtractionResult:
    """Result of Phase 2: Footnote Extraction."""
    footnotes: List[FootnoteRule] = field(default_factory=list)
    total_footnotes: int = 0
    successfully_parsed: int = 0
    flagged_for_review: int = 0
    by_rule_type: Dict[str, int] = field(default_factory=dict)
    extraction_quality: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "footnotes": [f.to_dict() for f in self.footnotes],
            "totalFootnotes": self.total_footnotes,
            "successfullyParsed": self.successfully_parsed,
            "flaggedForReview": self.flagged_for_review,
            "byRuleType": self.by_rule_type,
            "extractionQuality": self.extraction_quality,
        }


@dataclass
class VisitScheduleResult:
    """Result of Phase 3: Visit Schedule Generation."""
    visits: List[CanonicalVisit] = field(default_factory=list)
    protocol_type: ProtocolType = ProtocolType.HYBRID
    primary_reference_point: TimingReferencePoint = TimingReferencePoint.STUDY_START
    total_visits: int = 0
    visits_with_windows: int = 0
    flagged_for_review: int = 0
    generation_quality: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "visits": [v.to_dict() for v in self.visits],
            "protocolType": self.protocol_type.value,
            "primaryReferencePoint": self.primary_reference_point.value,
            "totalVisits": self.total_visits,
            "visitsWithWindows": self.visits_with_windows,
            "flaggedForReview": self.flagged_for_review,
            "generationQuality": self.generation_quality,
        }

    def to_usdm_encounters(self) -> List[Dict[str, Any]]:
        """Convert all visits to USDM Encounter format."""
        return [v.to_usdm_encounter() for v in self.visits]
