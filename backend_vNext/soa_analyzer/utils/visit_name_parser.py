"""
Visit Name Parser for Protocol-Agnostic SOA Processing

This module parses visit names from SOA tables into a canonical form,
regardless of protocol type. Supports 5 visit naming patterns:
1. cycle_day: "Cycle 1 Day -2", "C1D1", "C2D8", "Cycle 2-6 Day 1"
2. absolute_day: "Day 1", "Day 28", "D15"
3. week: "Week 4", "Week 12 ± 3 days", "Wk 8"
4. milestone: "Screening", "Baseline", "EOT", "Follow-up", "Final Visit"
5. timed_followup: "30-day Follow-up", "Week 4 Follow-up", "30-day FU Visit"
"""

import re
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from soa_analyzer.models import (
    CanonicalVisit,
    ProtocolType,
    RecurrenceRule,
    RecurrenceType,
    TimingReferencePoint,
    TimingWindow,
    VisitClassification,
    VisitType,
    WindowType,
)


@dataclass
class ParseResult:
    """Result of parsing a single visit name."""
    success: bool
    pattern_type: str  # cycle_day, absolute_day, week, milestone, timed_followup, unknown
    canonical_visit: Optional[CanonicalVisit] = None
    confidence: float = 1.0
    needs_review: bool = False
    review_reason: Optional[str] = None


class VisitNameParser:
    """Parse visit names into canonical form regardless of protocol type.

    This parser handles the variety of visit naming conventions found across
    clinical trial protocols, including oncology cycle-based visits, fixed
    duration day-based visits, week-based visits, and milestone visits.
    """

    # ==========================================================================
    # REGEX PATTERNS
    # ==========================================================================

    # Cycle-based patterns: "Cycle 1 Day -2", "C1D1", "C2D8", "Cycle 2-6 Day 1"
    CYCLE_DAY_PATTERNS = [
        # Full format: "Cycle 1 Day -2", "Cycle 1 Day 15"
        r"(?i)Cycle\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*Day\s*([+-]?\d+)",
        # Abbreviated: "C1D1", "C2D-2", "C1D15"
        r"(?i)C(\d+)D([+-]?\d+)",
        # With range: "Cycles 2-6 Day 1", "Cycle 2 – 6 Day 1"
        r"(?i)Cycles?\s*(\d+)\s*[-–]\s*(\d+)\s*Day\s*([+-]?\d+)",
    ]

    # Absolute day patterns: "Day 1", "Day 28", "D15"
    ABSOLUTE_DAY_PATTERNS = [
        # Full format: "Day 1", "Day 28", "Day -7"
        r"(?i)^Day\s*([+-]?\d+)$",
        # Abbreviated: "D1", "D28", "D-7"
        r"(?i)^D([+-]?\d+)$",
    ]

    # Week-based patterns: "Week 4", "Week 12 ± 3 days", "Wk 8"
    WEEK_PATTERNS = [
        # Full format with optional window: "Week 4", "Week 12 ± 3 days"
        r"(?i)Week\s*(\d+)(?:\s*[±+-]\s*(\d+)\s*days?)?",
        # Abbreviated: "Wk 4", "Wk 12"
        r"(?i)Wk\s*(\d+)",
    ]

    # Milestone patterns: keywords that indicate specific visit types
    MILESTONE_PATTERNS = {
        "screening": r"(?i)^(?:Screening|SCR)$",
        "baseline": r"(?i)^Baseline$",
        "randomization": r"(?i)^(?:Randomization|RAND)$",
        "end_of_treatment": r"(?i)^(?:End\s*of\s*Treatment|EOT|Final\s*Visit|End\s*of\s*Study|EOS)$",
        "follow_up": r"(?i)^(?:Follow[- ]?up|FU|Follow[- ]?up\s*Visit)$",
        "safety": r"(?i)^(?:Safety\s*Follow[- ]?up|Safety\s*Visit)$",
        "survival": r"(?i)^(?:Survival|Survival\s*Period|Long[- ]?term\s*Follow[- ]?up)$",
        "maintenance": r"(?i)^(?:Maintenance|Maintenance\s*Therapy|Maintenance\s*Phase)$",
        "post_treatment": r"(?i)^(?:Post[- ]?Treatment|Post[- ]?Treatment\s*Visits?)$",
        "unscheduled": r"(?i)^(?:Unscheduled|PRN|As\s*Needed)$",
    }

    # Timed follow-up patterns: "30-day Follow-up", "Week 4 Follow-up"
    TIMED_FOLLOWUP_PATTERNS = [
        # Days: "30-day Follow-up", "30 day FU Visit"
        r"(?i)(\d+)[- ]?day\s*(?:Follow[- ]?up|FU)(?:\s*Visit)?",
        # Weeks: "Week 4 Follow-up", "4-week Follow-up"
        r"(?i)(?:Week\s*)?(\d+)[- ]?week\s*(?:Follow[- ]?up|FU)(?:\s*Visit)?",
        # Months: "3-month Follow-up", "6 month FU"
        r"(?i)(\d+)[- ]?month\s*(?:Follow[- ]?up|FU)(?:\s*Visit)?",
    ]

    # NON-VISIT PATTERNS: Strings to reject as they're typically column/row headers
    # These are commonly extracted from SOA tables but are NOT actual visit names
    NON_VISIT_PATTERNS = [
        r"^Days?$",                      # Column header "Day" or "Days"
        r"^Visit\s*Schedule$",           # Row header
        r"^Before\s+Drug",               # Activity description "Before Drug Administration"
        r"^After\s+.*\s+Dose$",          # Timing description "After Veliparib AM Dose"
        r"^Sampling\s+Plan$",            # Row header
        r"^Specimen\s+Matrix$",          # Row header
        r"^−?\d+$",                      # Just a number (day offset like "-2", "1", "15")
        r"^[+-]?\d+$",                   # Just a signed number
        r"^\d+\s*[-–]\s*\d+$",           # Range like "6 - 19" or "2-6"
        r"^Visit$",                      # Generic "Visit" header
        r"^Procedure$",                  # Row header
        r"^Assessment$",                 # Row header
        r"^Activity$",                   # Row header
        r"^Treatment$",                  # Generic "Treatment" header (not a visit name)
        r"^Study\s+Procedures?$",        # Section header
        r"^Required$",                   # Header indicating required visits
        r"^Optional$",                   # Header indicating optional visits
    ]

    # ==========================================================================
    # CONSTRUCTOR
    # ==========================================================================

    def __init__(self):
        """Initialize the parser."""
        self._visit_counter = 0

    # ==========================================================================
    # MAIN PARSING METHOD
    # ==========================================================================

    def parse(self, visit_name: str, table_id: Optional[int] = None) -> ParseResult:
        """Parse any visit name format into canonical form.

        Args:
            visit_name: The visit name as it appears in the SOA table
            table_id: Optional source table ID for provenance

        Returns:
            ParseResult with canonical visit information and parsing metadata
        """
        # Clean the input
        clean_name = self._clean_visit_name(visit_name)

        if not clean_name:
            return ParseResult(
                success=False,
                pattern_type="unknown",
                needs_review=True,
                review_reason="Empty visit name",
            )

        # Check if this is a non-visit pattern (column/row header, etc.)
        if self._is_non_visit(clean_name):
            return ParseResult(
                success=False,
                pattern_type="non_visit",
                confidence=0.0,
                needs_review=False,  # Don't review - we're confident this is NOT a visit
                review_reason=f"'{visit_name}' is a non-visit pattern (header/label)",
            )

        # Try each pattern type in order of specificity

        # 1. Timed follow-up (most specific)
        result = self._parse_timed_followup(clean_name, visit_name, table_id)
        if result.success:
            return result

        # 2. Cycle-day pattern (oncology-specific)
        result = self._parse_cycle_day(clean_name, visit_name, table_id)
        if result.success:
            return result

        # 3. Week pattern
        result = self._parse_week(clean_name, visit_name, table_id)
        if result.success:
            return result

        # 4. Absolute day pattern
        result = self._parse_absolute_day(clean_name, visit_name, table_id)
        if result.success:
            return result

        # 5. Milestone pattern (most general)
        result = self._parse_milestone(clean_name, visit_name, table_id)
        if result.success:
            return result

        # If no pattern matched, flag for review
        return ParseResult(
            success=False,
            pattern_type="unknown",
            canonical_visit=self._create_unknown_visit(visit_name, table_id),
            confidence=0.3,
            needs_review=True,
            review_reason=f"Visit name '{visit_name}' did not match any known pattern",
        )

    def parse_all(
        self,
        visit_names: List[str],
        table_id: Optional[int] = None
    ) -> Tuple[List[CanonicalVisit], ProtocolType]:
        """Parse a list of visit names and detect protocol type.

        Args:
            visit_names: List of visit names from SOA table
            table_id: Optional source table ID for provenance

        Returns:
            Tuple of (list of canonical visits, detected protocol type)
        """
        visits = []
        pattern_counts = {
            "cycle_day": 0,
            "absolute_day": 0,
            "week": 0,
            "milestone": 0,
            "timed_followup": 0,
            "unknown": 0,
            "non_visit": 0,  # Rejected patterns (headers, labels, etc.)
        }

        for name in visit_names:
            result = self.parse(name, table_id)
            if result.canonical_visit:
                visits.append(result.canonical_visit)
            pattern_counts[result.pattern_type] += 1

        # Detect protocol type based on dominant pattern
        protocol_type = self._detect_protocol_type(pattern_counts)

        return visits, protocol_type

    # ==========================================================================
    # PATTERN-SPECIFIC PARSERS
    # ==========================================================================

    def _parse_cycle_day(
        self,
        clean_name: str,
        original_name: str,
        table_id: Optional[int]
    ) -> ParseResult:
        """Parse cycle-day format visits."""

        for pattern in self.CYCLE_DAY_PATTERNS:
            match = re.match(pattern, clean_name)
            if match:
                groups = match.groups()

                # Handle different pattern variations
                if len(groups) == 3 and groups[1] is not None:
                    # Range pattern: "Cycle 2-6 Day 1"
                    cycle_start = int(groups[0])
                    cycle_end = int(groups[1])
                    day = int(groups[2])
                    is_repeating = True
                    max_cycles = cycle_end
                elif len(groups) == 3:
                    # Full pattern without range: "Cycle 1 Day -2"
                    cycle_start = int(groups[0])
                    cycle_end = None
                    day = int(groups[2])
                    is_repeating = False
                    max_cycles = None
                elif len(groups) == 2:
                    # Abbreviated: "C1D1"
                    cycle_start = int(groups[0])
                    cycle_end = None
                    day = int(groups[1])
                    is_repeating = False
                    max_cycles = None
                else:
                    continue

                # Create canonical name
                if cycle_end:
                    canonical_name = f"Cycle {cycle_start}-{cycle_end} Day {day}"
                else:
                    canonical_name = f"Cycle {cycle_start} Day {day}"

                # Determine visit type
                visit_type = VisitType.TREATMENT
                if cycle_start == 1 and day <= 0:
                    # Pre-treatment in cycle 1
                    visit_type = VisitType.BASELINE

                # Create recurrence rule if repeating
                recurrence = None
                if is_repeating:
                    recurrence = RecurrenceRule(
                        type=RecurrenceType.PER_CYCLE,
                        cycle_day=day,
                        max_cycles=max_cycles,
                    )

                # Create classification
                classification = VisitClassification(
                    visit_type=visit_type,
                    is_required=True,
                    is_repeating=is_repeating,
                    recurrence_rule=recurrence,
                )

                visit = CanonicalVisit(
                    id=self._generate_id("ENC"),
                    name=canonical_name,
                    original_name=original_name,
                    visit_type=visit_type,
                    timing_value=day,
                    timing_unit="days",
                    relative_to=TimingReferencePoint.CYCLE_START,
                    cycle_number=cycle_start,
                    day_in_cycle=day,
                    classification=classification,
                )

                return ParseResult(
                    success=True,
                    pattern_type="cycle_day",
                    canonical_visit=visit,
                    confidence=0.95,
                )

        return ParseResult(success=False, pattern_type="cycle_day")

    def _parse_absolute_day(
        self,
        clean_name: str,
        original_name: str,
        table_id: Optional[int]
    ) -> ParseResult:
        """Parse absolute day format visits."""

        for pattern in self.ABSOLUTE_DAY_PATTERNS:
            match = re.match(pattern, clean_name)
            if match:
                day = int(match.group(1))

                # Determine visit type based on day number
                if day < 0:
                    visit_type = VisitType.SCREENING
                elif day == 0 or day == 1:
                    visit_type = VisitType.BASELINE
                else:
                    visit_type = VisitType.TREATMENT

                # Create classification
                classification = VisitClassification(
                    visit_type=visit_type,
                    is_required=True,
                    is_repeating=False,
                )

                visit = CanonicalVisit(
                    id=self._generate_id("ENC"),
                    name=f"Day {day}",
                    original_name=original_name,
                    visit_type=visit_type,
                    timing_value=day,
                    timing_unit="days",
                    relative_to=TimingReferencePoint.STUDY_START,
                    classification=classification,
                )

                return ParseResult(
                    success=True,
                    pattern_type="absolute_day",
                    canonical_visit=visit,
                    confidence=0.95,
                )

        return ParseResult(success=False, pattern_type="absolute_day")

    def _parse_week(
        self,
        clean_name: str,
        original_name: str,
        table_id: Optional[int]
    ) -> ParseResult:
        """Parse week-based format visits."""

        for pattern in self.WEEK_PATTERNS:
            match = re.match(pattern, clean_name)
            if match:
                groups = match.groups()
                week = int(groups[0])

                # Check for embedded window
                window = None
                if len(groups) > 1 and groups[1]:
                    tolerance = int(groups[1])
                    window = TimingWindow.from_bilateral(
                        target=week * 7,  # Convert to days
                        tolerance=tolerance,
                        unit="days",
                        relative_to=TimingReferencePoint.STUDY_START,
                    )

                # Create classification
                classification = VisitClassification(
                    visit_type=VisitType.TREATMENT,
                    is_required=True,
                    is_repeating=False,
                )

                visit = CanonicalVisit(
                    id=self._generate_id("ENC"),
                    name=f"Week {week}",
                    original_name=original_name,
                    visit_type=VisitType.TREATMENT,
                    timing_value=week,
                    timing_unit="weeks",
                    relative_to=TimingReferencePoint.STUDY_START,
                    window=window,
                    classification=classification,
                )

                return ParseResult(
                    success=True,
                    pattern_type="week",
                    canonical_visit=visit,
                    confidence=0.95,
                )

        return ParseResult(success=False, pattern_type="week")

    def _parse_milestone(
        self,
        clean_name: str,
        original_name: str,
        table_id: Optional[int]
    ) -> ParseResult:
        """Parse milestone visits (Screening, Baseline, EOT, etc.)."""

        for milestone_type, pattern in self.MILESTONE_PATTERNS.items():
            if re.match(pattern, clean_name):
                # Map milestone to visit type and reference point
                milestone_config = self._get_milestone_config(milestone_type)

                # Create classification
                classification = VisitClassification(
                    visit_type=milestone_config["visit_type"],
                    is_required=milestone_config.get("is_required", True),
                    is_repeating=milestone_config.get("is_repeating", False),
                )

                visit = CanonicalVisit(
                    id=self._generate_id("ENC"),
                    name=milestone_config["canonical_name"],
                    original_name=original_name,
                    visit_type=milestone_config["visit_type"],
                    timing_value=milestone_config.get("timing_value"),
                    timing_unit="days",
                    relative_to=milestone_config["relative_to"],
                    classification=classification,
                )

                return ParseResult(
                    success=True,
                    pattern_type="milestone",
                    canonical_visit=visit,
                    confidence=0.90,
                )

        return ParseResult(success=False, pattern_type="milestone")

    def _parse_timed_followup(
        self,
        clean_name: str,
        original_name: str,
        table_id: Optional[int]
    ) -> ParseResult:
        """Parse timed follow-up visits (30-day FU, Week 4 Follow-up, etc.)."""

        for i, pattern in enumerate(self.TIMED_FOLLOWUP_PATTERNS):
            match = re.match(pattern, clean_name)
            if match:
                value = int(match.group(1))

                # Determine unit based on which pattern matched
                if i == 0:  # Days pattern
                    unit = "days"
                    canonical_name = f"{value}-Day Follow-up"
                elif i == 1:  # Weeks pattern
                    unit = "weeks"
                    canonical_name = f"Week {value} Follow-up"
                else:  # Months pattern
                    unit = "months"
                    canonical_name = f"{value}-Month Follow-up"

                # Create classification
                classification = VisitClassification(
                    visit_type=VisitType.FOLLOW_UP,
                    is_required=True,
                    is_repeating=False,
                )

                visit = CanonicalVisit(
                    id=self._generate_id("ENC"),
                    name=canonical_name,
                    original_name=original_name,
                    visit_type=VisitType.FOLLOW_UP,
                    timing_value=value,
                    timing_unit=unit,
                    relative_to=TimingReferencePoint.LAST_DOSE,  # Follow-ups relative to last dose
                    classification=classification,
                )

                return ParseResult(
                    success=True,
                    pattern_type="timed_followup",
                    canonical_visit=visit,
                    confidence=0.95,
                )

        return ParseResult(success=False, pattern_type="timed_followup")

    # ==========================================================================
    # HELPER METHODS
    # ==========================================================================

    def _is_non_visit(self, clean_name: str) -> bool:
        """Check if the name matches a non-visit pattern (headers, labels, etc.).

        These are strings commonly extracted from SOA tables that are NOT
        actual visit names - like column headers ("Days"), row labels
        ("Procedure"), or standalone numbers ("-2", "15").

        Args:
            clean_name: The cleaned visit name to check

        Returns:
            True if this matches a non-visit pattern and should be rejected
        """
        for pattern in self.NON_VISIT_PATTERNS:
            if re.match(pattern, clean_name, re.IGNORECASE):
                return True
        return False

    def _clean_visit_name(self, name: str) -> str:
        """Clean and normalize a visit name for parsing."""
        if not name:
            return ""

        # Remove leading/trailing whitespace
        clean = name.strip()

        # Remove footnote markers (superscripts, asterisks, etc.)
        clean = re.sub(r"[\*†‡§¶#]+$", "", clean)
        clean = re.sub(r"\s*[\*†‡§¶#]+", "", clean)

        # Normalize whitespace
        clean = re.sub(r"\s+", " ", clean)

        # Normalize dashes (en-dash, em-dash)
        clean = re.sub(r"[–—]", "-", clean)

        # Normalize Unicode minus sign to regular minus
        clean = clean.replace("−", "-")  # Unicode minus U+2212

        return clean.strip()

    def _generate_id(self, prefix: str = "ENC") -> str:
        """Generate a unique visit ID."""
        self._visit_counter += 1
        return f"{prefix}-{self._visit_counter:03d}"

    def _get_milestone_config(self, milestone_type: str) -> Dict:
        """Get configuration for a milestone visit type."""
        configs = {
            "screening": {
                "canonical_name": "Screening",
                "visit_type": VisitType.SCREENING,
                "relative_to": TimingReferencePoint.RANDOMIZATION,
                "timing_value": None,  # Window-based, not fixed timing
            },
            "baseline": {
                "canonical_name": "Baseline",
                "visit_type": VisitType.BASELINE,
                "relative_to": TimingReferencePoint.STUDY_START,
                "timing_value": 0,
            },
            "randomization": {
                "canonical_name": "Randomization",
                "visit_type": VisitType.BASELINE,
                "relative_to": TimingReferencePoint.RANDOMIZATION,
                "timing_value": 0,
            },
            "end_of_treatment": {
                "canonical_name": "End of Treatment",
                "visit_type": VisitType.END_OF_TREATMENT,
                "relative_to": TimingReferencePoint.END_OF_TREATMENT,
                "timing_value": 0,
            },
            "follow_up": {
                "canonical_name": "Follow-up",
                "visit_type": VisitType.FOLLOW_UP,
                "relative_to": TimingReferencePoint.LAST_DOSE,
                "timing_value": None,  # Needs window from footnote
            },
            "safety": {
                "canonical_name": "Safety Follow-up",
                "visit_type": VisitType.SAFETY,
                "relative_to": TimingReferencePoint.LAST_DOSE,
                "timing_value": None,
            },
            "survival": {
                "canonical_name": "Survival Follow-up",
                "visit_type": VisitType.SURVIVAL,
                "relative_to": TimingReferencePoint.LAST_DOSE,
                "timing_value": None,
                "is_repeating": True,
            },
            "maintenance": {
                "canonical_name": "Maintenance Therapy",
                "visit_type": VisitType.MAINTENANCE,
                "relative_to": TimingReferencePoint.CYCLE_START,
                "timing_value": None,
                "is_repeating": True,
            },
            "post_treatment": {
                "canonical_name": "Post-Treatment",
                "visit_type": VisitType.FOLLOW_UP,
                "relative_to": TimingReferencePoint.END_OF_TREATMENT,
                "timing_value": None,
            },
            "unscheduled": {
                "canonical_name": "Unscheduled",
                "visit_type": VisitType.UNSCHEDULED,
                "relative_to": TimingReferencePoint.STUDY_START,
                "timing_value": None,
                "is_required": False,
            },
        }

        return configs.get(milestone_type, {
            "canonical_name": milestone_type.replace("_", " ").title(),
            "visit_type": VisitType.TREATMENT,
            "relative_to": TimingReferencePoint.STUDY_START,
        })

    def _create_unknown_visit(
        self,
        original_name: str,
        table_id: Optional[int]
    ) -> CanonicalVisit:
        """Create a canonical visit for an unknown pattern."""
        return CanonicalVisit(
            id=self._generate_id("ENC"),
            name=original_name,
            original_name=original_name,
            visit_type=VisitType.TREATMENT,
            relative_to=TimingReferencePoint.STUDY_START,
            needs_review=True,
            review_reason="Unknown visit name pattern",
        )

    def _detect_protocol_type(self, pattern_counts: Dict[str, int]) -> ProtocolType:
        """Detect protocol type based on visit naming patterns.

        Args:
            pattern_counts: Count of each pattern type found

        Returns:
            Detected protocol type
        """
        total = sum(pattern_counts.values())
        if total == 0:
            return ProtocolType.HYBRID

        # Calculate percentages
        cycle_pct = pattern_counts["cycle_day"] / total
        day_pct = pattern_counts["absolute_day"] / total
        week_pct = pattern_counts["week"] / total
        milestone_pct = pattern_counts["milestone"] / total

        # Decision logic
        if cycle_pct >= 0.5:
            return ProtocolType.CYCLE_BASED
        elif day_pct >= 0.5:
            return ProtocolType.FIXED_DURATION
        elif week_pct >= 0.3:
            return ProtocolType.FIXED_DURATION
        elif milestone_pct >= 0.6:
            return ProtocolType.EVENT_DRIVEN
        elif cycle_pct > 0 and milestone_pct > 0:
            return ProtocolType.HYBRID
        else:
            return ProtocolType.HYBRID


# =============================================================================
# TESTING / EXAMPLE USAGE
# =============================================================================


def test_parser():
    """Test the parser with real visit names from NCT02264990."""
    parser = VisitNameParser()

    # Test visit names from NCT02264990 (AbbVie oncology protocol)
    test_visits = [
        "SCR",                    # Screening
        "Cycle 1 Day −2",         # Pre-treatment (note Unicode minus)
        "Cycle 1 Day -2",         # Pre-treatment (regular minus)
        "Cycle 1 Day 1",          # Treatment start
        "Cycle 1 Day 15",         # Mid-cycle
        "Cycle 2 – 6 Day 1 *",    # Repeating cycle visits
        "Final Visit",            # EOT
        "30-day FU Visit",        # Timed follow-up
        "Maintenance Therapy",    # Maintenance phase
        "Post-Treatment Visits",  # Post-treatment
        "Survival Period",        # Survival follow-up
    ]

    # Additional test cases for other protocol types
    additional_tests = [
        # Fixed duration
        "Day 1",
        "Day 8",
        "Day 15",
        "D28",
        # Week-based
        "Week 4",
        "Week 12 ± 3 days",
        "Wk 8",
        # Abbreviated cycle
        "C1D1",
        "C2D8",
        "C3D15",
        # Milestones
        "Baseline",
        "EOT",
        "Unscheduled",
    ]

    all_tests = test_visits + additional_tests

    print("=" * 70)
    print("VISIT NAME PARSER TEST RESULTS")
    print("=" * 70)

    for name in all_tests:
        result = parser.parse(name)
        visit = result.canonical_visit

        if visit:
            print(f"\n'{name}':")
            print(f"  Pattern: {result.pattern_type}")
            print(f"  Canonical: {visit.name}")
            print(f"  Type: {visit.visit_type.value}")
            print(f"  Timing: {visit.timing_value} {visit.timing_unit}")
            print(f"  Reference: {visit.relative_to.value}")
            if visit.cycle_number:
                print(f"  Cycle: {visit.cycle_number}, Day: {visit.day_in_cycle}")
            print(f"  Confidence: {result.confidence:.0%}")
            if result.needs_review:
                print(f"  ⚠️  NEEDS REVIEW: {result.review_reason}")
        else:
            print(f"\n'{name}': FAILED TO PARSE")

    # Test protocol type detection
    print("\n" + "=" * 70)
    print("PROTOCOL TYPE DETECTION")
    print("=" * 70)

    visits, proto_type = parser.parse_all(test_visits)
    print(f"\nNCT02264990 visits → Protocol Type: {proto_type.value}")

    fixed_visits = ["Day 1", "Day 8", "Day 15", "Day 28", "Follow-up"]
    _, proto_type = parser.parse_all(fixed_visits)
    print(f"Fixed duration visits → Protocol Type: {proto_type.value}")

    event_visits = ["Screening", "Baseline", "EOT", "Follow-up", "Safety Follow-up"]
    _, proto_type = parser.parse_all(event_visits)
    print(f"Event-driven visits → Protocol Type: {proto_type.value}")


if __name__ == "__main__":
    test_parser()
