"""
SOA Table Merge Analyzer - Intelligent table merge decision making.

This module implements an 8-level decision tree to analyze whether SOA tables
should be merged or kept separate during the interpretation phase.

Pipeline Position: Phase 3.5 (between Phase 3 per-table USDM and 12-stage interpretation)

Decision Levels:
    Level 1: Physical Continuation (rule-based) - Adjacent pages, continuation markers
    Level 2: Study Structure (Gemini) - Visit types, phase indicators
    Level 3: Subject Characteristics (Gemini) - Population/cohort from footnotes
    Level 4: Intervention Characteristics (Gemini) - Treatment regimen patterns
    Level 5: Table Purpose (Claude) - Activity mix, domain distribution
    Level 6: Temporal Characteristics (Claude) - Overlapping/sequential timeframes
    Level 7: Geographic/Regulatory (Claude) - Region-specific requirements
    Level 8: Operational Characteristics (Claude) - Collection methods, versions

Usage:
    from soa_analyzer.table_merge_analyzer import TableMergeAnalyzer

    analyzer = TableMergeAnalyzer()
    merge_plan = await analyzer.analyze_merge_candidates(per_table_results)

    # Review merge_plan.merge_groups and merge_plan.standalone_tables
    # After human confirmation, run 12-stage interpretation on each group
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================


class MergeDecisionType(str, Enum):
    """Types of merge decisions."""
    SUGGEST_MERGE = "SUGGEST_MERGE"
    KEEP_SEPARATE = "KEEP_SEPARATE"
    CONTINUE = "CONTINUE"  # Continue to next level


class MergeType(str, Enum):
    """Types of table merges."""
    PHYSICAL_CONTINUATION = "physical_continuation"
    SAME_SCHEDULE = "same_schedule"
    SEQUENTIAL_PHASES = "sequential_phases"
    COMPLEMENTARY_ASSESSMENTS = "complementary_assessments"
    STANDALONE = "standalone"


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class TableFeatures:
    """Features extracted from a table's USDM for comparison."""

    table_id: str
    category: str  # MAIN_SOA, PK_SOA, SAFETY_SOA, PD_SOA, etc.
    page_range: Tuple[int, int]

    # Level 1: Physical continuation
    visit_names: List[str] = field(default_factory=list)
    activity_names: List[str] = field(default_factory=list)
    has_continuation_markers: bool = False
    continuation_marker_text: Optional[str] = None

    # Level 2: Study structure
    study_phases: Set[str] = field(default_factory=set)  # Screening, Treatment, Follow-up
    study_periods: Set[str] = field(default_factory=set)  # Part 1, Part 2, Cycle, etc.
    visit_types: Set[str] = field(default_factory=set)  # Scheduled, Unscheduled, etc.

    # Level 3: Subject characteristics
    population_indicators: Set[str] = field(default_factory=set)  # From footnotes
    cohort_indicators: Set[str] = field(default_factory=set)  # Cohort A, Arm 1, etc.

    # Level 4: Intervention characteristics
    treatment_indicators: Set[str] = field(default_factory=set)  # Drug names, doses
    dosing_patterns: Set[str] = field(default_factory=set)  # QD, BID, weekly, etc.

    # Level 5: Table purpose
    table_type: str = "unknown"  # main_soa, pk_sampling, safety, pd, etc.
    activity_domains: Set[str] = field(default_factory=set)  # LB, VS, EG, PE, etc.
    assessment_categories: Set[str] = field(default_factory=set)

    # Level 6: Temporal characteristics
    time_range: Tuple[Optional[int], Optional[int]] = (None, None)  # Days from reference
    visit_frequency: Optional[str] = None
    has_cycles: bool = False
    cycle_count: int = 0

    # Level 7: Geographic/Regulatory
    geographic_indicators: Set[str] = field(default_factory=set)  # US, EU, Japan, etc.
    regulatory_indicators: Set[str] = field(default_factory=set)  # FDA, EMA, etc.

    # Level 8: Operational characteristics
    collection_methods: Set[str] = field(default_factory=set)
    required_optional_ratio: float = 0.0
    footnote_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for LLM prompts."""
        return {
            "tableId": self.table_id,
            "category": self.category,
            "pageRange": list(self.page_range),
            "visitNames": self.visit_names,
            "activityNames": self.activity_names[:20],  # Limit for prompt size
            "hasContinuationMarkers": self.has_continuation_markers,
            "continuationMarkerText": self.continuation_marker_text,
            "studyPhases": list(self.study_phases),
            "studyPeriods": list(self.study_periods),
            "visitTypes": list(self.visit_types),
            "populationIndicators": list(self.population_indicators),
            "cohortIndicators": list(self.cohort_indicators),
            "treatmentIndicators": list(self.treatment_indicators),
            "dosingPatterns": list(self.dosing_patterns),
            "tableType": self.table_type,
            "activityDomains": list(self.activity_domains),
            "assessmentCategories": list(self.assessment_categories),
            "timeRange": list(self.time_range),
            "visitFrequency": self.visit_frequency,
            "hasCycles": self.has_cycles,
            "cycleCount": self.cycle_count,
            "geographicIndicators": list(self.geographic_indicators),
            "regulatoryIndicators": list(self.regulatory_indicators),
            "collectionMethods": list(self.collection_methods),
            "requiredOptionalRatio": self.required_optional_ratio,
            "footnoteCount": self.footnote_count,
        }


@dataclass
class LevelResult:
    """Result from a single level of analysis."""

    level: int
    name: str
    decision: MergeDecisionType
    confidence: float  # 0.0 - 1.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "name": self.name,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "reasoning": self.reasoning,
        }


@dataclass
class MergeDecision:
    """Decision about merging a pair or group of tables."""

    table_ids: List[str]
    decision: MergeDecisionType
    merge_group_id: str  # "MG-001", "MG-002", etc.
    level_reached: int  # Which level made the final decision (1-8)
    level_results: List[LevelResult] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tableIds": self.table_ids,
            "decision": self.decision.value,
            "mergeGroupId": self.merge_group_id,
            "levelReached": self.level_reached,
            "levelResults": [lr.to_dict() for lr in self.level_results],
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


@dataclass
class MergeGroup:
    """A group of tables to be merged."""

    id: str  # "MG-001"
    table_ids: List[str]
    merge_type: MergeType
    combined_features: Optional[TableFeatures] = None
    decision_path: List[LevelResult] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    confirmed: Optional[bool] = None
    user_override: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tableIds": self.table_ids,
            "mergeType": self.merge_type.value,
            "decisionLevel": self.decision_path[-1].level if self.decision_path else 0,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "confirmed": self.confirmed,
            "userOverride": self.user_override,
        }


@dataclass
class MergePlan:
    """Complete merge plan for all tables in a protocol."""

    protocol_id: str
    total_tables: int
    merge_groups: List[MergeGroup] = field(default_factory=list)
    standalone_tables: List[str] = field(default_factory=list)
    analysis_summary: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending_confirmation"
    analysis_timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    confirmed_at: Optional[str] = None
    confirmed_by: Optional[str] = None
    confirmed_groups: List[MergeGroup] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocolId": self.protocol_id,
            "analysisTimestamp": self.analysis_timestamp,
            "status": self.status,
            "totalTablesInput": self.total_tables,
            "suggestedMergeGroups": len(self.merge_groups),
            "mergeGroups": [mg.to_dict() for mg in self.merge_groups],
            "standaloneTables": self.standalone_tables,
            "analysisDetails": self.analysis_summary,
            "confirmedAt": self.confirmed_at,
            "confirmedBy": self.confirmed_by,
        }


# =============================================================================
# FEATURE EXTRACTION
# =============================================================================


class FeatureExtractor:
    """Extracts features from per-table USDM for merge analysis."""

    # Continuation markers that indicate table spans multiple pages
    CONTINUATION_MARKERS = [
        "continued", "(cont'd)", "(cont.)", "continuation",
        "table continued", "continued from", "continues on"
    ]

    # Study phase keywords
    PHASE_KEYWORDS = {
        "screening": "Screening",
        "baseline": "Baseline",
        "treatment": "Treatment",
        "follow-up": "Follow-up",
        "follow up": "Follow-up",
        "post-treatment": "Post-treatment",
        "washout": "Washout",
        "run-in": "Run-in",
        "extension": "Extension",
    }

    # Period keywords
    PERIOD_KEYWORDS = {
        "part 1": "Part 1",
        "part 2": "Part 2",
        "part 3": "Part 3",
        "part a": "Part A",
        "part b": "Part B",
        "cycle": "Cycle",
        "period": "Period",
        "epoch": "Epoch",
    }

    # Domain mapping for activity categorization
    DOMAIN_KEYWORDS = {
        "laboratory": "LB",
        "lab": "LB",
        "blood": "LB",
        "serum": "LB",
        "urine": "LB",
        "hematology": "LB",
        "chemistry": "LB",
        "vital signs": "VS",
        "vitals": "VS",
        "blood pressure": "VS",
        "heart rate": "VS",
        "temperature": "VS",
        "weight": "VS",
        "ecg": "EG",
        "electrocardiogram": "EG",
        "physical exam": "PE",
        "physical examination": "PE",
        "pharmacokinetic": "PK",
        "pk": "PK",
        "pharmacodynamic": "PD",
        "pd": "PD",
        "biomarker": "PD",
        "efficacy": "EF",
        "tumor": "EF",
        "response": "EF",
        "adverse event": "AE",
        "ae": "AE",
        "concomitant": "CM",
        "medication": "CM",
        "questionnaire": "QS",
        "quality of life": "QS",
        "imaging": "MI",
        "ct scan": "MI",
        "mri": "MI",
        "x-ray": "MI",
    }

    # Geographic/regulatory keywords
    GEO_KEYWORDS = {
        "us": "US",
        "usa": "US",
        "united states": "US",
        "eu": "EU",
        "europe": "EU",
        "european": "EU",
        "japan": "Japan",
        "japanese": "Japan",
        "china": "China",
        "chinese": "China",
        "fda": "FDA",
        "ema": "EMA",
        "pmda": "PMDA",
    }

    def extract_features(self, usdm: Dict[str, Any], table_id: str) -> TableFeatures:
        """
        Extract features from a table's USDM for merge analysis.

        Args:
            usdm: USDM JSON for a single table
            table_id: Table identifier (SOA-1, SOA-2, etc.)

        Returns:
            TableFeatures with all extracted characteristics
        """
        metadata = usdm.get("_tableMetadata", {})
        visits = usdm.get("visits", usdm.get("encounters", []))
        activities = usdm.get("activities", [])
        sais = usdm.get("scheduledActivityInstances", [])
        footnotes = usdm.get("footnotes", [])

        features = TableFeatures(
            table_id=table_id,
            category=metadata.get("category", "MAIN_SOA"),
            page_range=(
                metadata.get("pageStart", 0),
                metadata.get("pageEnd", 0)
            ),
        )

        # Extract visit names and analyze
        features.visit_names = [v.get("name", "") for v in visits if v.get("name")]
        self._analyze_visits(features, visits)

        # Extract activity names and analyze
        features.activity_names = [a.get("name", "") for a in activities if a.get("name")]
        self._analyze_activities(features, activities)

        # Check for continuation markers
        self._check_continuation_markers(features, usdm)

        # Analyze footnotes for additional context
        self._analyze_footnotes(features, footnotes)

        # Calculate metrics
        features.footnote_count = len(footnotes)
        self._calculate_required_optional_ratio(features, sais)

        # Infer table type from category and activities
        features.table_type = self._infer_table_type(features)

        return features

    def _analyze_visits(self, features: TableFeatures, visits: List[Dict]) -> None:
        """Analyze visits for phase, period, and timing information."""
        for visit in visits:
            name = visit.get("name", "").lower()

            # Check study phases
            for keyword, phase in self.PHASE_KEYWORDS.items():
                if keyword in name:
                    features.study_phases.add(phase)

            # Check study periods
            for keyword, period in self.PERIOD_KEYWORDS.items():
                if keyword in name:
                    features.study_periods.add(period)

            # Check for cycles
            if "cycle" in name:
                features.has_cycles = True
                # Try to extract cycle number
                cycle_match = re.search(r'cycle\s*(\d+)', name, re.IGNORECASE)
                if cycle_match:
                    cycle_num = int(cycle_match.group(1))
                    features.cycle_count = max(features.cycle_count, cycle_num)

            # Extract timing if available
            timing = visit.get("timing", {})
            if isinstance(timing, dict):
                timing_val = timing.get("value")
                if timing_val is not None:
                    try:
                        day = int(timing_val)
                        current_min, current_max = features.time_range
                        new_min = min(day, current_min) if current_min is not None else day
                        new_max = max(day, current_max) if current_max is not None else day
                        features.time_range = (new_min, new_max)
                    except (ValueError, TypeError):
                        pass

    def _analyze_activities(self, features: TableFeatures, activities: List[Dict]) -> None:
        """Analyze activities for domain and assessment categorization."""
        for activity in activities:
            name = activity.get("name", "").lower()

            # Map to CDISC domains
            for keyword, domain in self.DOMAIN_KEYWORDS.items():
                if keyword in name:
                    features.activity_domains.add(domain)

            # Check for dosing patterns
            dosing_patterns = ["qd", "bid", "tid", "qod", "weekly", "daily", "monthly"]
            for pattern in dosing_patterns:
                if pattern in name:
                    features.dosing_patterns.add(pattern.upper())

            # Check for treatment indicators
            treatment_keywords = ["dose", "dosing", "administration", "infusion", "injection"]
            for keyword in treatment_keywords:
                if keyword in name:
                    features.treatment_indicators.add(name)
                    break

    def _check_continuation_markers(self, features: TableFeatures, usdm: Dict) -> None:
        """Check for continuation markers indicating multi-page table."""
        # Check in metadata
        metadata = usdm.get("_tableMetadata", {})
        raw_html = metadata.get("rawHtml", "")

        # Search for continuation markers
        text_to_search = json.dumps(usdm).lower()

        for marker in self.CONTINUATION_MARKERS:
            if marker in text_to_search:
                features.has_continuation_markers = True
                features.continuation_marker_text = marker
                break

        # Also check visit names for continuation patterns
        for visit_name in features.visit_names:
            if any(marker in visit_name.lower() for marker in self.CONTINUATION_MARKERS):
                features.has_continuation_markers = True
                features.continuation_marker_text = visit_name
                break

    def _analyze_footnotes(self, features: TableFeatures, footnotes: List[Dict]) -> None:
        """Analyze footnotes for population, cohort, and regulatory information."""
        for footnote in footnotes:
            text = footnote.get("text", footnote.get("footnoteText", "")).lower()

            # Check for population indicators
            population_keywords = [
                "patients", "subjects", "participants", "healthy volunteers",
                "adults", "pediatric", "elderly", "renally impaired"
            ]
            for keyword in population_keywords:
                if keyword in text:
                    features.population_indicators.add(keyword)

            # Check for cohort indicators
            cohort_patterns = [
                r'cohort\s*[a-z]', r'arm\s*\d', r'group\s*\d',
                r'dose\s*level', r'expansion', r'escalation'
            ]
            for pattern in cohort_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        features.cohort_indicators.add(match.group(0))

            # Check for geographic/regulatory indicators
            for keyword, indicator in self.GEO_KEYWORDS.items():
                if keyword in text:
                    if indicator in ["FDA", "EMA", "PMDA"]:
                        features.regulatory_indicators.add(indicator)
                    else:
                        features.geographic_indicators.add(indicator)

    def _calculate_required_optional_ratio(
        self, features: TableFeatures, sais: List[Dict]
    ) -> None:
        """Calculate ratio of required vs optional assessments."""
        if not sais:
            return

        required_count = 0
        total_count = len(sais)

        for sai in sais:
            # Check conditionality
            conditionality = sai.get("conditionality", "").lower()
            if conditionality in ["required", "mandatory", ""]:  # Empty often means required
                required_count += 1

        features.required_optional_ratio = required_count / total_count if total_count > 0 else 0.0

    def _infer_table_type(self, features: TableFeatures) -> str:
        """Infer the table type based on extracted features."""
        # Check category first
        category = features.category.upper()

        if "PK" in category or "PK" in features.activity_domains:
            return "pk_sampling"
        elif "PD" in category or "PD" in features.activity_domains:
            return "pharmacodynamic"
        elif "SAFETY" in category:
            return "safety_monitoring"
        elif "FOLLOW" in category:
            return "follow_up"

        # Infer from activity domains
        if len(features.activity_domains) == 1:
            domain = list(features.activity_domains)[0]
            if domain == "PK":
                return "pk_sampling"
            elif domain == "PD":
                return "pharmacodynamic"
            elif domain == "EG":
                return "ecg_schedule"
            elif domain == "MI":
                return "imaging_schedule"

        # Default to main SOA
        return "main_soa"


# =============================================================================
# TABLE MERGE ANALYZER
# =============================================================================


class TableMergeAnalyzer:
    """
    Analyzes tables and determines which should be merged.

    Uses an 8-level decision tree with hybrid LLM strategy:
    - Levels 1-4: Gemini (simpler semantic analysis)
    - Levels 5-8: Claude (complex reasoning)
    """

    def __init__(self):
        """Initialize the analyzer with LLM clients."""
        self.feature_extractor = FeatureExtractor()
        self._gemini_client = None
        self._claude_client = None
        self._merge_group_counter = 0

        # Load prompts
        self.prompts_dir = Path(__file__).parent / "prompts"

    @property
    def gemini_client(self):
        """Lazy initialization of Gemini client."""
        if self._gemini_client is None:
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            self._gemini_client = genai.GenerativeModel("gemini-2.0-flash")
        return self._gemini_client

    @property
    def claude_client(self):
        """Lazy initialization of Claude client."""
        if self._claude_client is None:
            import anthropic
            self._claude_client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        return self._claude_client

    def _next_merge_group_id(self) -> str:
        """Generate next merge group ID."""
        self._merge_group_counter += 1
        return f"MG-{self._merge_group_counter:03d}"

    async def analyze_merge_candidates(
        self,
        per_table_results: List[Any],  # List[PerTableResult]
        protocol_id: str,
    ) -> MergePlan:
        """
        Analyze all tables and determine merge groups.

        Args:
            per_table_results: List of PerTableResult from Phase 3
            protocol_id: Protocol identifier

        Returns:
            MergePlan with suggested merge groups
        """
        logger.info(f"Starting merge analysis for {len(per_table_results)} tables")

        # Reset counter for new analysis
        self._merge_group_counter = 0

        # Extract features from each table
        table_features: Dict[str, TableFeatures] = {}
        for ptr in per_table_results:
            if ptr.success and ptr.usdm:
                features = self.feature_extractor.extract_features(ptr.usdm, ptr.table_id)
                table_features[ptr.table_id] = features
                logger.debug(f"Extracted features for {ptr.table_id}: {features.category}")

        if len(table_features) < 2:
            # Only one table, nothing to merge
            logger.info("Only one table - no merge analysis needed")
            single_table_id = list(table_features.keys())[0] if table_features else None
            return MergePlan(
                protocol_id=protocol_id,
                total_tables=len(table_features),
                merge_groups=[
                    MergeGroup(
                        id=self._next_merge_group_id(),
                        table_ids=[single_table_id] if single_table_id else [],
                        merge_type=MergeType.STANDALONE,
                        confidence=1.0,
                        reasoning="Single table - no merge needed",
                    )
                ] if single_table_id else [],
                standalone_tables=[single_table_id] if single_table_id else [],
            )

        # Sort tables by page number for sequential analysis
        sorted_tables = sorted(
            table_features.items(),
            key=lambda x: x[1].page_range[0]
        )

        # Analyze pairwise relationships
        pairwise_decisions: List[MergeDecision] = []
        for i in range(len(sorted_tables) - 1):
            table_a_id, features_a = sorted_tables[i]
            table_b_id, features_b = sorted_tables[i + 1]

            decision = await self._analyze_pair(features_a, features_b)
            pairwise_decisions.append(decision)
            logger.info(
                f"  {table_a_id} + {table_b_id}: {decision.decision.value} "
                f"(Level {decision.level_reached}, conf={decision.confidence:.2f})"
            )

        # Build merge groups from pairwise decisions
        merge_groups = self._build_merge_groups(sorted_tables, pairwise_decisions)

        # Calculate analysis summary
        analysis_summary = self._build_analysis_summary(pairwise_decisions)

        # Identify standalone tables
        merged_table_ids = set()
        for mg in merge_groups:
            merged_table_ids.update(mg.table_ids)

        standalone = [
            tid for tid, _ in sorted_tables
            if tid not in merged_table_ids
        ]

        # Add standalone tables as single-table groups
        for tid in standalone:
            merge_groups.append(MergeGroup(
                id=self._next_merge_group_id(),
                table_ids=[tid],
                merge_type=MergeType.STANDALONE,
                confidence=1.0,
                reasoning=f"Table {tid} kept separate based on analysis",
            ))

        return MergePlan(
            protocol_id=protocol_id,
            total_tables=len(table_features),
            merge_groups=merge_groups,
            standalone_tables=standalone,
            analysis_summary=analysis_summary,
        )

    async def _analyze_pair(
        self,
        features_a: TableFeatures,
        features_b: TableFeatures,
    ) -> MergeDecision:
        """
        Analyze a pair of tables through the 8-level decision tree.

        Returns as soon as a definitive decision is reached.
        """
        level_results: List[LevelResult] = []

        # Level 1: Physical continuation (rule-based)
        level1_result = self._level1_physical_continuation(features_a, features_b)
        level_results.append(level1_result)

        if level1_result.decision != MergeDecisionType.CONTINUE:
            return MergeDecision(
                table_ids=[features_a.table_id, features_b.table_id],
                decision=level1_result.decision,
                merge_group_id=self._next_merge_group_id(),
                level_reached=1,
                level_results=level_results,
                confidence=level1_result.confidence,
                reasoning=level1_result.reasoning,
            )

        # Levels 2-4: Gemini analysis
        try:
            levels_2_4_results = await self._levels_2_4_gemini_analysis(features_a, features_b)
            level_results.extend(levels_2_4_results)

            for result in levels_2_4_results:
                if result.decision != MergeDecisionType.CONTINUE:
                    return MergeDecision(
                        table_ids=[features_a.table_id, features_b.table_id],
                        decision=result.decision,
                        merge_group_id=self._next_merge_group_id(),
                        level_reached=result.level,
                        level_results=level_results,
                        confidence=result.confidence,
                        reasoning=result.reasoning,
                    )
        except Exception as e:
            logger.warning(f"Gemini analysis failed: {e}, falling back to heuristics")
            # Add placeholder results
            for level in [2, 3, 4]:
                level_results.append(LevelResult(
                    level=level,
                    name=["", "Study Structure", "Subject Characteristics", "Intervention"][level - 1],
                    decision=MergeDecisionType.CONTINUE,
                    confidence=0.5,
                    reasoning=f"Analysis skipped due to error: {e}",
                ))

        # Levels 5-8: Claude analysis
        try:
            levels_5_8_results = await self._levels_5_8_claude_analysis(features_a, features_b)
            level_results.extend(levels_5_8_results)

            for result in levels_5_8_results:
                if result.decision != MergeDecisionType.CONTINUE:
                    return MergeDecision(
                        table_ids=[features_a.table_id, features_b.table_id],
                        decision=result.decision,
                        merge_group_id=self._next_merge_group_id(),
                        level_reached=result.level,
                        level_results=level_results,
                        confidence=result.confidence,
                        reasoning=result.reasoning,
                    )
        except Exception as e:
            logger.warning(f"Claude analysis failed: {e}, using heuristic fallback")
            # Fall back to heuristic decision
            return self._heuristic_fallback(features_a, features_b, level_results)

        # If we reach here, no definitive decision - default to keep separate
        return MergeDecision(
            table_ids=[features_a.table_id, features_b.table_id],
            decision=MergeDecisionType.KEEP_SEPARATE,
            merge_group_id=self._next_merge_group_id(),
            level_reached=8,
            level_results=level_results,
            confidence=0.6,
            reasoning="No strong evidence for merging after all levels",
        )

    def _level1_physical_continuation(
        self,
        table_a: TableFeatures,
        table_b: TableFeatures,
    ) -> LevelResult:
        """
        Level 1: Check for physical continuation.

        Rule-based detection of tables that are split across pages.
        """
        evidence = {}

        # Check if pages are adjacent
        pages_adjacent = table_a.page_range[1] + 1 >= table_b.page_range[0]
        evidence["pagesAdjacent"] = pages_adjacent
        evidence["tableAPages"] = list(table_a.page_range)
        evidence["tableBPages"] = list(table_b.page_range)

        # Check for continuation markers
        has_markers = table_b.has_continuation_markers
        evidence["hasContinuationMarkers"] = has_markers
        evidence["markerText"] = table_b.continuation_marker_text

        # Check activity overlap
        activity_set_a = set(table_a.activity_names)
        activity_set_b = set(table_b.activity_names)
        activity_overlap = len(activity_set_a & activity_set_b)
        activity_overlap_ratio = activity_overlap / max(len(activity_set_a), 1)
        evidence["activityOverlap"] = activity_overlap
        evidence["activityOverlapRatio"] = activity_overlap_ratio

        # Check visit sequence
        visits_sequential = self._check_visit_sequence(
            table_a.visit_names, table_b.visit_names
        )
        evidence["visitsSequential"] = visits_sequential

        # Check same category
        same_category = table_a.category == table_b.category
        evidence["sameCategory"] = same_category

        # Decision logic
        # Strong indicators of physical continuation:
        # 1. Adjacent pages + continuation markers
        # 2. Adjacent pages + same activities + sequential visits
        # 3. Same category + high activity overlap + sequential visits

        is_continuation = False
        confidence = 0.0
        reasoning = ""

        if pages_adjacent and has_markers:
            is_continuation = True
            confidence = 0.95
            reasoning = "Adjacent pages with continuation markers detected"
        elif pages_adjacent and activity_overlap_ratio > 0.7 and visits_sequential:
            is_continuation = True
            confidence = 0.90
            reasoning = "Adjacent pages with matching activities and sequential visits"
        elif pages_adjacent and same_category and visits_sequential:
            is_continuation = True
            confidence = 0.85
            reasoning = "Adjacent pages with same category and sequential visits"

        if is_continuation:
            return LevelResult(
                level=1,
                name="Physical Continuation",
                decision=MergeDecisionType.SUGGEST_MERGE,
                confidence=confidence,
                evidence=evidence,
                reasoning=reasoning,
            )

        return LevelResult(
            level=1,
            name="Physical Continuation",
            decision=MergeDecisionType.CONTINUE,
            confidence=0.0,
            evidence=evidence,
            reasoning="No physical continuation detected",
        )

    def _check_visit_sequence(
        self,
        visits_a: List[str],
        visits_b: List[str],
    ) -> bool:
        """Check if visits_b continues the sequence from visits_a."""
        if not visits_a or not visits_b:
            return False

        # Try to extract visit numbers/days
        def extract_number(visit_name: str) -> Optional[int]:
            match = re.search(r'(\d+)', visit_name)
            return int(match.group(1)) if match else None

        last_a = extract_number(visits_a[-1])
        first_b = extract_number(visits_b[0])

        if last_a is not None and first_b is not None:
            # Check if first_b follows last_a
            return first_b > last_a

        # Check by name patterns
        last_a_lower = visits_a[-1].lower()
        first_b_lower = visits_b[0].lower()

        # Common continuation patterns
        continuation_patterns = [
            ("week", r'week\s*(\d+)'),
            ("day", r'day\s*(\d+)'),
            ("visit", r'visit\s*(\d+)'),
            ("cycle", r'cycle\s*(\d+)'),
        ]

        for keyword, pattern in continuation_patterns:
            if keyword in last_a_lower and keyword in first_b_lower:
                match_a = re.search(pattern, last_a_lower)
                match_b = re.search(pattern, first_b_lower)
                if match_a and match_b:
                    num_a = int(match_a.group(1))
                    num_b = int(match_b.group(1))
                    return num_b > num_a

        return False

    async def _levels_2_4_gemini_analysis(
        self,
        features_a: TableFeatures,
        features_b: TableFeatures,
    ) -> List[LevelResult]:
        """
        Levels 2-4: Use Gemini for simpler semantic analysis.

        Level 2: Study Structure
        Level 3: Subject Characteristics
        Level 4: Intervention Characteristics
        """
        prompt = self._load_prompt("table_merge_levels_2_4.txt")
        if not prompt:
            # Fallback to heuristic analysis
            return self._heuristic_levels_2_4(features_a, features_b)

        formatted_prompt = prompt.format(
            table_a=json.dumps(features_a.to_dict(), indent=2),
            table_b=json.dumps(features_b.to_dict(), indent=2),
        )

        try:
            response = await asyncio.to_thread(
                self.gemini_client.generate_content,
                formatted_prompt,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                }
            )

            result_json = json.loads(response.text)
            return self._parse_level_results(result_json, levels=[2, 3, 4])

        except Exception as e:
            logger.warning(f"Gemini analysis failed: {e}")
            return self._heuristic_levels_2_4(features_a, features_b)

    def _heuristic_levels_2_4(
        self,
        features_a: TableFeatures,
        features_b: TableFeatures,
    ) -> List[LevelResult]:
        """Heuristic fallback for levels 2-4."""
        results = []

        # Level 2: Study Structure
        same_phases = features_a.study_phases == features_b.study_phases
        same_periods = features_a.study_periods == features_b.study_periods

        if not same_phases and features_a.study_phases and features_b.study_phases:
            results.append(LevelResult(
                level=2,
                name="Study Structure",
                decision=MergeDecisionType.KEEP_SEPARATE,
                confidence=0.75,
                evidence={
                    "phasesA": list(features_a.study_phases),
                    "phasesB": list(features_b.study_phases),
                },
                reasoning="Different study phases detected",
            ))
        else:
            results.append(LevelResult(
                level=2,
                name="Study Structure",
                decision=MergeDecisionType.CONTINUE,
                confidence=0.5,
                reasoning="Study structure analysis inconclusive",
            ))

        # Level 3: Subject Characteristics
        different_populations = (
            features_a.population_indicators != features_b.population_indicators
            and features_a.population_indicators
            and features_b.population_indicators
        )

        if different_populations:
            results.append(LevelResult(
                level=3,
                name="Subject Characteristics",
                decision=MergeDecisionType.KEEP_SEPARATE,
                confidence=0.70,
                evidence={
                    "populationA": list(features_a.population_indicators),
                    "populationB": list(features_b.population_indicators),
                },
                reasoning="Different subject populations detected",
            ))
        else:
            results.append(LevelResult(
                level=3,
                name="Subject Characteristics",
                decision=MergeDecisionType.CONTINUE,
                confidence=0.5,
                reasoning="Subject characteristics analysis inconclusive",
            ))

        # Level 4: Intervention Characteristics
        different_treatments = (
            features_a.treatment_indicators != features_b.treatment_indicators
            and features_a.treatment_indicators
            and features_b.treatment_indicators
        )

        if different_treatments:
            results.append(LevelResult(
                level=4,
                name="Intervention Characteristics",
                decision=MergeDecisionType.KEEP_SEPARATE,
                confidence=0.70,
                evidence={
                    "treatmentA": list(features_a.treatment_indicators),
                    "treatmentB": list(features_b.treatment_indicators),
                },
                reasoning="Different treatment regimens detected",
            ))
        else:
            results.append(LevelResult(
                level=4,
                name="Intervention Characteristics",
                decision=MergeDecisionType.CONTINUE,
                confidence=0.5,
                reasoning="Intervention characteristics analysis inconclusive",
            ))

        return results

    async def _levels_5_8_claude_analysis(
        self,
        features_a: TableFeatures,
        features_b: TableFeatures,
    ) -> List[LevelResult]:
        """
        Levels 5-8: Use Claude for complex semantic analysis.

        Level 5: Table Purpose
        Level 6: Temporal Characteristics
        Level 7: Geographic/Regulatory
        Level 8: Operational Characteristics
        """
        prompt = self._load_prompt("table_merge_levels_5_8.txt")
        if not prompt:
            return self._heuristic_levels_5_8(features_a, features_b)

        formatted_prompt = prompt.format(
            table_a=json.dumps(features_a.to_dict(), indent=2),
            table_b=json.dumps(features_b.to_dict(), indent=2),
        )

        try:
            response = await asyncio.to_thread(
                lambda: self.claude_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2000,
                    messages=[{"role": "user", "content": formatted_prompt}],
                )
            )

            # Parse JSON from response
            response_text = response.content[0].text

            # Extract JSON from response (may be wrapped in markdown code block)
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                result_json = json.loads(json_match.group(1))
            else:
                result_json = json.loads(response_text)

            return self._parse_level_results(result_json, levels=[5, 6, 7, 8])

        except Exception as e:
            logger.warning(f"Claude analysis failed: {e}")
            return self._heuristic_levels_5_8(features_a, features_b)

    def _heuristic_levels_5_8(
        self,
        features_a: TableFeatures,
        features_b: TableFeatures,
    ) -> List[LevelResult]:
        """Heuristic fallback for levels 5-8."""
        results = []

        # Level 5: Table Purpose
        different_purpose = features_a.table_type != features_b.table_type
        different_domains = (
            features_a.activity_domains != features_b.activity_domains
            and len(features_a.activity_domains) > 0
            and len(features_b.activity_domains) > 0
            and not features_a.activity_domains.intersection(features_b.activity_domains)
        )

        if different_purpose or different_domains:
            results.append(LevelResult(
                level=5,
                name="Table Purpose",
                decision=MergeDecisionType.KEEP_SEPARATE,
                confidence=0.80,
                evidence={
                    "typeA": features_a.table_type,
                    "typeB": features_b.table_type,
                    "domainsA": list(features_a.activity_domains),
                    "domainsB": list(features_b.activity_domains),
                },
                reasoning="Different table purposes or activity domains detected",
            ))
        else:
            results.append(LevelResult(
                level=5,
                name="Table Purpose",
                decision=MergeDecisionType.CONTINUE,
                confidence=0.5,
                reasoning="Table purpose analysis inconclusive",
            ))

        # Level 6: Temporal Characteristics
        overlapping_time = self._check_time_overlap(
            features_a.time_range, features_b.time_range
        )

        if not overlapping_time and features_a.time_range[0] is not None and features_b.time_range[0] is not None:
            # Non-overlapping but sequential could be a merge candidate
            if features_a.time_range[1] is not None and features_b.time_range[0] is not None:
                if features_b.time_range[0] > features_a.time_range[1]:
                    results.append(LevelResult(
                        level=6,
                        name="Temporal Characteristics",
                        decision=MergeDecisionType.SUGGEST_MERGE,
                        confidence=0.70,
                        evidence={
                            "timeRangeA": list(features_a.time_range),
                            "timeRangeB": list(features_b.time_range),
                        },
                        reasoning="Sequential non-overlapping time ranges suggest continuation",
                    ))
                else:
                    results.append(LevelResult(
                        level=6,
                        name="Temporal Characteristics",
                        decision=MergeDecisionType.CONTINUE,
                        confidence=0.5,
                        reasoning="Temporal analysis inconclusive",
                    ))
            else:
                results.append(LevelResult(
                    level=6,
                    name="Temporal Characteristics",
                    decision=MergeDecisionType.CONTINUE,
                    confidence=0.5,
                    reasoning="Temporal analysis inconclusive",
                ))
        else:
            results.append(LevelResult(
                level=6,
                name="Temporal Characteristics",
                decision=MergeDecisionType.CONTINUE,
                confidence=0.5,
                reasoning="Temporal analysis inconclusive",
            ))

        # Level 7: Geographic/Regulatory
        different_geo = (
            features_a.geographic_indicators != features_b.geographic_indicators
            and features_a.geographic_indicators
            and features_b.geographic_indicators
        )
        different_reg = (
            features_a.regulatory_indicators != features_b.regulatory_indicators
            and features_a.regulatory_indicators
            and features_b.regulatory_indicators
        )

        if different_geo or different_reg:
            results.append(LevelResult(
                level=7,
                name="Geographic/Regulatory",
                decision=MergeDecisionType.KEEP_SEPARATE,
                confidence=0.75,
                evidence={
                    "geoA": list(features_a.geographic_indicators),
                    "geoB": list(features_b.geographic_indicators),
                    "regA": list(features_a.regulatory_indicators),
                    "regB": list(features_b.regulatory_indicators),
                },
                reasoning="Different geographic or regulatory requirements detected",
            ))
        else:
            results.append(LevelResult(
                level=7,
                name="Geographic/Regulatory",
                decision=MergeDecisionType.CONTINUE,
                confidence=0.5,
                reasoning="Geographic/regulatory analysis inconclusive",
            ))

        # Level 8: Operational Characteristics
        results.append(LevelResult(
            level=8,
            name="Operational Characteristics",
            decision=MergeDecisionType.CONTINUE,
            confidence=0.5,
            reasoning="Operational characteristics analysis inconclusive",
        ))

        return results

    def _check_time_overlap(
        self,
        range_a: Tuple[Optional[int], Optional[int]],
        range_b: Tuple[Optional[int], Optional[int]],
    ) -> bool:
        """Check if two time ranges overlap."""
        if range_a[0] is None or range_b[0] is None:
            return False

        min_a, max_a = range_a
        min_b, max_b = range_b

        if max_a is None:
            max_a = min_a
        if max_b is None:
            max_b = min_b

        return not (max_a < min_b or max_b < min_a)

    def _load_prompt(self, filename: str) -> Optional[str]:
        """Load a prompt template from file."""
        prompt_path = self.prompts_dir / filename
        if prompt_path.exists():
            return prompt_path.read_text()
        logger.warning(f"Prompt file not found: {prompt_path}")
        return None

    def _parse_level_results(
        self,
        result_json: Dict[str, Any],
        levels: List[int],
    ) -> List[LevelResult]:
        """Parse LLM response into LevelResult objects."""
        results = []
        level_names = {
            2: "Study Structure",
            3: "Subject Characteristics",
            4: "Intervention Characteristics",
            5: "Table Purpose",
            6: "Temporal Characteristics",
            7: "Geographic/Regulatory",
            8: "Operational Characteristics",
        }

        for level in levels:
            level_key = f"level{level}"
            level_data = result_json.get(level_key, {})

            decision_str = level_data.get("decision", "CONTINUE")
            try:
                decision = MergeDecisionType(decision_str.upper())
            except ValueError:
                decision = MergeDecisionType.CONTINUE

            results.append(LevelResult(
                level=level,
                name=level_names.get(level, f"Level {level}"),
                decision=decision,
                confidence=float(level_data.get("confidence", 0.5)),
                evidence=level_data.get("evidence", {}),
                reasoning=level_data.get("reasoning", ""),
            ))

        return results

    def _heuristic_fallback(
        self,
        features_a: TableFeatures,
        features_b: TableFeatures,
        level_results: List[LevelResult],
    ) -> MergeDecision:
        """Fallback decision based on simple heuristics."""
        # If same category and similar activities, suggest merge
        same_category = features_a.category == features_b.category
        activity_overlap = len(
            set(features_a.activity_names) & set(features_b.activity_names)
        ) / max(len(features_a.activity_names), 1)

        if same_category and activity_overlap > 0.5:
            return MergeDecision(
                table_ids=[features_a.table_id, features_b.table_id],
                decision=MergeDecisionType.SUGGEST_MERGE,
                merge_group_id=self._next_merge_group_id(),
                level_reached=8,
                level_results=level_results,
                confidence=0.60,
                reasoning="Heuristic fallback: same category with overlapping activities",
            )

        return MergeDecision(
            table_ids=[features_a.table_id, features_b.table_id],
            decision=MergeDecisionType.KEEP_SEPARATE,
            merge_group_id=self._next_merge_group_id(),
            level_reached=8,
            level_results=level_results,
            confidence=0.55,
            reasoning="Heuristic fallback: insufficient evidence for merging",
        )

    def _build_merge_groups(
        self,
        sorted_tables: List[Tuple[str, TableFeatures]],
        pairwise_decisions: List[MergeDecision],
    ) -> List[MergeGroup]:
        """Build merge groups from pairwise decisions using union-find."""
        # Union-find for grouping
        parent = {tid: tid for tid, _ in sorted_tables}

        def find(x: str) -> str:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: str, y: str) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Process merge decisions
        decision_map = {}
        for i, decision in enumerate(pairwise_decisions):
            if decision.decision == MergeDecisionType.SUGGEST_MERGE:
                table_a = sorted_tables[i][0]
                table_b = sorted_tables[i + 1][0]
                union(table_a, table_b)
                decision_map[(table_a, table_b)] = decision

        # Build groups from union-find
        groups: Dict[str, List[str]] = {}
        for tid, _ in sorted_tables:
            root = find(tid)
            if root not in groups:
                groups[root] = []
            groups[root].append(tid)

        # Convert to MergeGroup objects
        merge_groups = []
        for root, table_ids in groups.items():
            if len(table_ids) > 1:
                # Find the decision that led to this merge
                decision_path = []
                merge_type = MergeType.PHYSICAL_CONTINUATION  # Default

                for i in range(len(table_ids) - 1):
                    pair_key = (table_ids[i], table_ids[i + 1])
                    if pair_key in decision_map:
                        decision = decision_map[pair_key]
                        decision_path.extend(decision.level_results)

                        # Determine merge type based on level
                        if decision.level_reached == 1:
                            merge_type = MergeType.PHYSICAL_CONTINUATION
                        elif decision.level_reached in [2, 3, 4]:
                            merge_type = MergeType.SAME_SCHEDULE
                        elif decision.level_reached == 6:
                            merge_type = MergeType.SEQUENTIAL_PHASES
                        else:
                            merge_type = MergeType.COMPLEMENTARY_ASSESSMENTS

                merge_groups.append(MergeGroup(
                    id=self._next_merge_group_id(),
                    table_ids=table_ids,
                    merge_type=merge_type,
                    decision_path=decision_path,
                    confidence=decision_path[-1].confidence if decision_path else 0.8,
                    reasoning=decision_path[-1].reasoning if decision_path else "Tables grouped for merging",
                ))

        return merge_groups

    def _build_analysis_summary(
        self,
        pairwise_decisions: List[MergeDecision],
    ) -> Dict[str, Any]:
        """Build summary statistics from analysis."""
        level_stats = {f"level{i}_decisions": 0 for i in range(1, 9)}
        merge_count = 0
        separate_count = 0

        for decision in pairwise_decisions:
            if decision.decision == MergeDecisionType.SUGGEST_MERGE:
                merge_count += 1
                level_stats[f"level{decision.level_reached}_decisions"] += 1
            elif decision.decision == MergeDecisionType.KEEP_SEPARATE:
                separate_count += 1
                level_stats[f"level{decision.level_reached}_decisions"] += 1

        return {
            "pairwiseComparisons": len(pairwise_decisions),
            "suggestedMerges": merge_count,
            "suggestedSeparate": separate_count,
            "levelStatistics": level_stats,
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


async def analyze_tables_for_merge(
    per_table_results: List[Any],
    protocol_id: str,
) -> MergePlan:
    """
    Convenience function to analyze tables for merging.

    Args:
        per_table_results: List of PerTableResult from Phase 3
        protocol_id: Protocol identifier

    Returns:
        MergePlan with suggested merge groups
    """
    analyzer = TableMergeAnalyzer()
    return await analyzer.analyze_merge_candidates(per_table_results, protocol_id)


def combine_table_usdm(
    per_table_results: List[Any],  # List[PerTableResult]
    table_ids: List[str],
) -> Dict[str, Any]:
    """
    Combine USDM from multiple tables into a single structure.

    Used after merge confirmation to prepare input for 12-stage interpretation.

    Args:
        per_table_results: List of all PerTableResult
        table_ids: IDs of tables to combine

    Returns:
        Combined USDM structure
    """
    # Filter to requested tables
    tables_to_merge = [
        ptr for ptr in per_table_results
        if ptr.table_id in table_ids and ptr.success and ptr.usdm
    ]

    if not tables_to_merge:
        return {}

    # Start with first table as base
    combined = dict(tables_to_merge[0].usdm)

    # Track seen items to avoid duplicates
    seen_visit_names = {v.get("name") for v in combined.get("visits", [])}
    seen_activity_names = {a.get("name") for a in combined.get("activities", [])}
    seen_footnote_texts = {
        f.get("text", f.get("footnoteText"))
        for f in combined.get("footnotes", [])
    }

    # Merge remaining tables
    for ptr in tables_to_merge[1:]:
        usdm = ptr.usdm

        # Merge visits (avoiding duplicates)
        for visit in usdm.get("visits", []):
            name = visit.get("name")
            if name and name not in seen_visit_names:
                combined.setdefault("visits", []).append(visit)
                seen_visit_names.add(name)

        # Merge activities (avoiding duplicates)
        for activity in usdm.get("activities", []):
            name = activity.get("name")
            if name and name not in seen_activity_names:
                combined.setdefault("activities", []).append(activity)
                seen_activity_names.add(name)

        # Merge SAIs (all unique by definition)
        combined.setdefault("scheduledActivityInstances", []).extend(
            usdm.get("scheduledActivityInstances", [])
        )

        # Merge footnotes (avoiding duplicates)
        for footnote in usdm.get("footnotes", []):
            text = footnote.get("text", footnote.get("footnoteText"))
            if text and text not in seen_footnote_texts:
                combined.setdefault("footnotes", []).append(footnote)
                seen_footnote_texts.add(text)

    # Update encounters alias
    combined["encounters"] = combined.get("visits", [])

    # Update metadata
    combined["_mergeMetadata"] = {
        "sourceTables": table_ids,
        "mergedAt": datetime.utcnow().isoformat(),
    }

    return combined
