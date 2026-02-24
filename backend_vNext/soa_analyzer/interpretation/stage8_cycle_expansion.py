"""
Stage 8: Cycle Expansion (v2 — LLM-Driven, No Hardcoded Filters)

Expands encounters with repeating cycle patterns (e.g., "Cycles 1-6, Day 1 of each cycle")
into individual cycle-specific encounters.

v2 Changes from v1:
─────────────────────
1. REMOVED all hardcoded name-based skip logic ("Screening", "Baseline", etc.)
2. REMOVED regex pattern matching as a gate — patterns are now advisory only
3. ALL encounters go to the LLM — the LLM decides what to expand, what to skip
4. Added dosing/study-drug context injection into LLM prompt
5. Added delta-based visit analysis as CONTEXT for LLM (not as a filter)
6. The LLM response is the single source of truth for expansion decisions

Design Principles:
1. LLM-First — LLM sees ALL encounters + protocol context and decides everything
2. Cache-Heavy — Cache LLM decisions by pattern for reuse
3. Confidence-Based — Auto-apply ≥0.90, escalate <0.90 to review
4. Audit Trail — Full provenance for every expanded entity
5. USDM Compliant — Proper ID generation, cycleNumber Code objects
6. No Hardcoding — Zero name-based filters; LLM drives all routing

Usage:
    from soa_analyzer.interpretation.stage8_cycle_expansion import CycleExpander

    expander = CycleExpander()
    result = await expander.expand_cycles(usdm_output, extraction_outputs=extraction_outputs)
    updated_output = expander.apply_expansions_to_usdm(usdm_output, result)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..models.cycle_expansion import (
    CycleDecision,
    CycleExpansion,
    CycleExpansionConfig,
    CyclePattern,
    CyclePatternType,
    CycleValidationDiscrepancy,
    HumanReviewItem,
    Stage8Result,
    is_already_expanded,
    parse_cycle_range,
)
from ..models.code_object import (
    CodeObject,
    NCI_EVS_CODE_SYSTEM,
    NCI_EVS_VERSION,
)

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "cycle_expansion"

# Prompt file path
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "cycle_expansion.txt"

# Validation patterns config (advisory only — NOT used for filtering)
PATTERNS_PATH = Path(__file__).parent.parent / "config" / "cycle_patterns.json"

# CDISC cycle codes config
CYCLE_CODES_PATH = Path(__file__).parent.parent / "config" / "cycle_codes.json"


# ===========================================================================
# Visit Delta Analyzer — provides context to LLM, does NOT filter
# ===========================================================================

class VisitDeltaAnalyzer:
    """
    Analyzes visit day-number patterns to detect potential repeating intervals.

    This is purely informational — results are passed as CONTEXT to the LLM,
    which then decides whether the pattern represents actual cycles.

    Handles protocols with linear visit naming (Day 1, Day 22, Day 43)
    that may actually represent repeating cycle structures.
    """

    DAY_PATTERN = re.compile(
        r"(?:^|\b)(?:day|d)\s*[-:]?\s*(\d+)(?:\s|$|[,;/\)])",
        re.IGNORECASE,
    )

    @classmethod
    def _deduplicate_by_parent_visit(
        cls,
        encounters: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Collapse encounters sharing the same parentVisit into one representative.

        Encounters with timingModifier and shared parentVisit are sub-visit
        timepoints (e.g., hourly PK samples on Day 1). Only the first encounter
        per unique parentVisit contributes to delta analysis. Encounters without
        parentVisit pass through unchanged.

        For M21-195: [Day 1 x7 (Hour 0-6), Day 7, Day 14] → [Day 1, Day 7, Day 14]
        """
        deduplicated = []
        seen_parents: Set[str] = set()

        for enc in encounters:
            parent = enc.get("parentVisit")
            if parent:
                if parent in seen_parents:
                    continue
                seen_parents.add(parent)
                # Use the parent visit name for delta analysis
                representative = dict(enc)
                representative["name"] = parent
                deduplicated.append(representative)
            else:
                deduplicated.append(enc)

        return deduplicated

    @classmethod
    def analyze(
        cls,
        encounters: List[Dict[str, Any]],
        tolerance_days: int = 3,
    ) -> Dict[str, Any]:
        """
        Analyze encounters for repeating visit-day patterns.

        Returns a context dict describing any detected patterns.
        This dict is passed to the LLM as supplemental context.
        """
        # Deduplicate timepoints that share a parentVisit before delta analysis
        encounters = cls._deduplicate_by_parent_visit(encounters)

        # Extract day numbers from encounter names
        day_encounters = []
        for enc in encounters:
            name = enc.get("name", "")
            match = cls.DAY_PATTERN.search(name)
            if match:
                day_encounters.append((int(match.group(1)), enc.get("id", ""), name))

        if len(day_encounters) < 3:
            return {"hasPattern": False, "reason": "fewer_than_3_day_visits"}

        day_encounters.sort(key=lambda x: x[0])
        days = [d for d, _, _ in day_encounters]

        # Compute deltas
        deltas = [days[i + 1] - days[i] for i in range(len(days) - 1)]

        # Find most common delta
        delta_counts: Dict[int, int] = defaultdict(int)
        for d in deltas:
            matched = False
            for existing in list(delta_counts.keys()):
                if abs(d - existing) <= tolerance_days:
                    delta_counts[existing] += 1
                    matched = True
                    break
            if not matched:
                delta_counts[d] += 1

        if not delta_counts:
            return {"hasPattern": False, "reason": "no_consistent_deltas"}

        dominant_delta = max(delta_counts, key=delta_counts.get)
        occurrences = delta_counts[dominant_delta]

        # Build context (informational only)
        return {
            "hasPattern": occurrences >= 2,
            "inferredIntervalDays": dominant_delta,
            "intervalOccurrences": occurrences,
            "totalVisitsAnalyzed": len(day_encounters),
            "visitDays": days,
            "deltas": deltas,
            "visits": [
                {"day": d, "id": eid, "name": n}
                for d, eid, n in day_encounters
            ],
            "note": (
                f"Detected repeating {dominant_delta}-day interval across "
                f"{occurrences + 1} visits. This MAY represent a cycle structure. "
                f"Use dosing context to confirm."
            ) if occurrences >= 2 else "No strong repeating interval detected.",
        }


# ===========================================================================
# Pattern Registry — advisory validation only, never blocks encounters
# ===========================================================================

class CyclePatternRegistry:
    """
    Registry of known cycle patterns for VALIDATION (post-LLM cross-check).

    NEVER used to filter or block encounters before LLM analysis.
    Only used to flag discrepancies after LLM has made its decision.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._patterns: Dict[str, CyclePattern] = {}
        self._known_cycle_expansions: Dict[str, Any] = {}
        self._known_interval_expansions: Dict[str, List[int]] = {}
        self._known_week_expansions: Dict[str, List[int]] = {}
        self._non_expandable_patterns: List[str] = []
        self._event_driven_patterns: List[str] = []
        self._steady_state_patterns: List[str] = []
        self._cycle_length_defaults: Dict[str, int] = {}
        self._load_config(config_path or PATTERNS_PATH)

    def _load_config(self, config_path: Path) -> None:
        """Load patterns from JSON config."""
        if not config_path.exists():
            logger.warning(f"Cycle patterns config not found: {config_path}")
            return

        try:
            with open(config_path) as f:
                data = json.load(f)

            self._known_cycle_expansions = data.get("known_cycle_expansions", {})
            self._known_interval_expansions = data.get("known_interval_expansions", {})
            self._known_week_expansions = data.get("known_week_expansions", {})
            self._non_expandable_patterns = data.get("non_expandable_patterns", [])
            self._event_driven_patterns = data.get("event_driven_patterns", [])
            self._steady_state_patterns = data.get("steady_state_patterns", [])
            self._cycle_length_defaults = data.get("cycle_length_defaults", {})

            for pattern_id, pattern_data in data.get("patterns", {}).items():
                self._patterns[pattern_id] = CyclePattern(
                    id=pattern_id,
                    pattern_type=CyclePatternType.EXPLICIT_RANGE,
                    pattern_regex=pattern_data.get("pattern_regex", ""),
                    description=pattern_data.get("description"),
                )

            logger.info(
                f"Loaded {len(self._patterns)} cycle patterns (advisory), "
                f"{len(self._known_cycle_expansions)} known cycle expansions"
            )
        except Exception as e:
            logger.warning(f"Failed to load cycle patterns config: {e}")

    def get_known_expansion(self, pattern_text: str) -> Optional[List[int]]:
        """Get known expansion for a cycle pattern (if exists)."""
        normalized = pattern_text.strip()
        if normalized in self._known_cycle_expansions:
            result = self._known_cycle_expansions[normalized]
            return result if isinstance(result, list) else None
        if normalized in self._known_interval_expansions:
            return self._known_interval_expansions[normalized]
        if normalized in self._known_week_expansions:
            return self._known_week_expansions[normalized]
        return None

    def get_cycle_length(self, pattern_text: str) -> int:
        """Get cycle length in days for a pattern."""
        text_lower = pattern_text.lower()
        for key, days in self._cycle_length_defaults.items():
            if key.lower() in text_lower:
                return days
        return self._cycle_length_defaults.get("default", 21)


# ===========================================================================
# Main Expander
# ===========================================================================

class CycleExpander:
    """
    Stage 8: Cycle Expansion Handler (LLM-First, No Hardcoded Filters).

    ALL encounters are sent to the LLM with full protocol context.
    The LLM decides what to expand, what to skip, and what to flag.
    """

    def __init__(
        self,
        config: Optional[CycleExpansionConfig] = None,
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
    ):
        self.config = config or CycleExpansionConfig()
        self.use_cache = use_cache
        self.cache_dir = cache_dir or CACHE_DIR

        # Pattern registry — advisory only
        self._pattern_registry = CyclePatternRegistry()

        # CDISC cycle codes
        self._cycle_codes = self._load_cycle_codes()

        # In-memory cache
        self._cache: Dict[str, CycleDecision] = {}
        self._cache_loaded = False

        # LLM clients (lazy loaded)
        self._gemini_client = None
        self._azure_client = None
        self._azure_deployment = None
        self._claude_client = None

        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Protocol context
        self._extraction_outputs: Dict[str, Dict] = {}
        self._protocol_context: Dict[str, Any] = {}

    # =========== Protocol Context Extraction ===========

    def _extract_protocol_context(self) -> Dict[str, Any]:
        """
        Extract ALL relevant protocol context from extraction_outputs.

        This context is passed to the LLM so it can make informed decisions
        about encounters whose names alone are ambiguous.
        """
        context = {}

        study_metadata = self._extraction_outputs.get("study_metadata", {})
        if not study_metadata:
            return context

        # Treatment design/duration
        treatment_design = study_metadata.get("treatmentDesign", {})
        if treatment_design:
            context["treatmentDuration"] = treatment_design.get("duration")
            context["treatmentCycles"] = treatment_design.get("cycles")
            context["treatmentDescription"] = treatment_design.get("description")
            context["dosingSchedule"] = treatment_design.get("dosingSchedule")
            context["dosingFrequency"] = treatment_design.get("frequency")
            context["cycleLengthDays"] = treatment_design.get("cycleLengthDays")
            context["route"] = treatment_design.get("route")

        # Study periods
        for period in study_metadata.get("studyPeriods", []):
            if period.get("periodType") == "Treatment":
                context["treatmentPeriodDescription"] = period.get("description")

        # Study arms
        arms = study_metadata.get("arms", [])
        if arms:
            context["armCount"] = len(arms)
            context["arms"] = []
            for arm in arms:
                arm_info = {
                    "name": arm.get("name"),
                    "description": arm.get("description"),
                }
                # Extract dosing from interventions
                interventions = arm.get("interventions", [])
                if interventions:
                    arm_info["interventions"] = [
                        {
                            "dose": interv.get("dose"),
                            "frequency": interv.get("frequency"),
                            "schedule": interv.get("schedule"),
                        }
                        for interv in interventions
                    ]
                context["arms"].append(arm_info)

                arm_desc = arm.get("description", "").lower()
                if "until" in arm_desc or "discontinu" in arm_desc:
                    context["openEndedTreatment"] = True
                    context["treatmentTermination"] = arm.get("description")

        # Study drug extraction (if pipeline has a dedicated stage)
        study_drug = self._extraction_outputs.get("study_drug", {})
        if study_drug:
            context["studyDrug"] = {
                "dosingRegimen": study_drug.get("dosingRegimen"),
                "administrationSchedule": study_drug.get("administrationSchedule"),
            }

        # Duration signals — critical for resolving open-ended patterns
        context["studyDuration"] = study_metadata.get("studyDuration")
        context["primaryEndpointTimeline"] = study_metadata.get("primaryEndpointTimeline")
        context["maxCyclesFromProtocol"] = study_metadata.get("maxCycles") or treatment_design.get("maxCycles") if treatment_design else None
        context["studyPhase"] = study_metadata.get("studyPhase")
        context["therapeuticArea"] = study_metadata.get("therapeuticArea")
        context["primaryObjective"] = study_metadata.get("primaryObjective")

        # SOA footnotes — often contain critical cycle/dosing info
        soa_data = self._extraction_outputs.get("soa", {})
        footnotes = soa_data.get("footnotes", [])
        if footnotes:
            context["soaFootnotes"] = [
                fn.get("text", str(fn)) if isinstance(fn, dict) else str(fn)
                for fn in footnotes[:20]  # Cap at 20 to avoid token bloat
            ]

        return context

    # =========== CDISC Codes ===========

    def _load_cycle_codes(self) -> Dict[str, Any]:
        """Load CDISC cycle codes from config file."""
        cycle_codes = {}
        if CYCLE_CODES_PATH.exists():
            try:
                with open(CYCLE_CODES_PATH) as f:
                    data = json.load(f)
                cycle_codes = {
                    "base_code": data.get("cycle_base_code", {}),
                    "cycle_numbers": data.get("cycle_number_codes", {}),
                    "steady_state": data.get("steady_state_code", {}),
                    "recurrence_types": data.get("recurrence_type_codes", {}),
                    "interval_units": data.get("interval_unit_codes", {}),
                    "week_numbers": data.get("week_number_codes", {}),
                    "usdm": data.get("usdm_code_system", {}),
                }
                logger.info(f"Loaded CDISC cycle codes from {CYCLE_CODES_PATH}")
            except Exception as e:
                logger.warning(f"Failed to load cycle codes: {e}")
        return cycle_codes

    def _create_cycle_number_code(
        self,
        cycle_num: int,
        encounter_id: str,
        is_steady_state: bool = False,
    ) -> Dict[str, Any]:
        """Create USDM 4.0 compliant cycleNumber Code object."""
        if is_steady_state:
            code_data = self._cycle_codes.get("steady_state", {})
            decode = code_data.get("decode", "Steady State Cycle")
        else:
            code_data = self._cycle_codes.get("cycle_numbers", {}).get(
                str(cycle_num),
                self._cycle_codes.get("base_code", {}),
            )
            decode = code_data.get("decode", f"Cycle {cycle_num}")

        code = code_data.get("code", "C94535")

        return {
            "id": f"CODE-CYC-{encounter_id}-C{cycle_num}",
            "code": code,
            "decode": decode,
            "codeSystem": NCI_EVS_CODE_SYSTEM,
            "codeSystemVersion": NCI_EVS_VERSION,
            "instanceType": "Code",
        }

    # =========== Caching ===========

    def _load_cache(self) -> None:
        """Load cache from disk."""
        if self._cache_loaded:
            return
        cache_file = self.cache_dir / "decisions_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                for key, decision_data in data.get("decisions", {}).items():
                    self._cache[key] = CycleDecision.from_dict(decision_data)
                logger.info(f"Loaded {len(self._cache)} cached cycle decisions")
            except Exception as e:
                logger.warning(f"Failed to load cycle cache: {e}")
        self._cache_loaded = True

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if not self.use_cache:
            return
        cache_file = self.cache_dir / "decisions_cache.json"
        try:
            data = {
                "metadata": {
                    "model_name": self.config.model_name,
                    "version": "2.0.0",
                    "updated": datetime.utcnow().isoformat() + "Z",
                },
                "decisions": {
                    key: decision.to_dict()
                    for key, decision in self._cache.items()
                },
            }
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cycle cache: {e}")

    def _get_cache_key(self, encounter_name: str, recurrence_key: str) -> str:
        """Generate cache key from encounter name + recurrence key."""
        normalized = f"{encounter_name.lower().strip()}:{recurrence_key.lower().strip()}"
        return hashlib.md5(normalized.encode()).hexdigest()

    def _check_cache(self, encounter_name: str, recurrence_key: str) -> Optional[CycleDecision]:
        """Return cached decision if exists."""
        cache_key = self._get_cache_key(encounter_name, recurrence_key)
        if cache_key in self._cache:
            decision = self._cache[cache_key]
            decision.source = "cache"
            return decision
        return None

    def _update_cache(self, encounter_name: str, recurrence_key: str, decision: CycleDecision) -> None:
        """Store decision in cache."""
        cache_key = self._get_cache_key(encounter_name, recurrence_key)
        self._cache[cache_key] = decision

    # =========== LLM Clients ===========

    def _get_gemini_client(self):
        """Lazy load Gemini client."""
        if self._gemini_client is None:
            try:
                import google.generativeai as genai
                from google.generativeai.types import HarmCategory, HarmBlockThreshold

                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    safety_settings = {
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }
                    self._gemini_client = genai.GenerativeModel(
                        self.config.model_name,
                        safety_settings=safety_settings,
                    )
                    logger.info(f"Initialized Gemini client: {self.config.model_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
        return self._gemini_client

    def _get_azure_client(self):
        """Lazy load Azure OpenAI client (fallback)."""
        if self._azure_client is None:
            try:
                from openai import AzureOpenAI

                api_key = os.getenv("AZURE_OPENAI_API_KEY")
                endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", self.config.fallback_model)
                api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview")

                if api_key and endpoint:
                    self._azure_client = AzureOpenAI(
                        api_key=api_key,
                        api_version=api_version,
                        azure_endpoint=endpoint,
                        timeout=180.0,
                    )
                    self._azure_deployment = deployment
                    logger.info(f"Initialized Azure OpenAI fallback: {deployment}")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure OpenAI client: {e}")
        return self._azure_client

    def _get_claude_client(self):
        """Lazy load Anthropic Claude client (fallback)."""
        if self._claude_client is None:
            try:
                import anthropic

                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    self._claude_client = anthropic.Anthropic(api_key=api_key)
                    logger.info("Initialized Anthropic Claude client")
            except Exception as e:
                logger.warning(f"Failed to initialize Anthropic Claude client: {e}")
        return self._claude_client

    # =========== LLM Prompt Construction ===========

    def _build_llm_prompt(self, encounters_data: List[Dict[str, Any]]) -> str:
        """
        Build LLM prompt with FULL protocol context.

        The prompt template has three placeholders:
          {supplemental_context} — treatment design, dosing, arms, footnotes, delta analysis
          {encounter_count}      — number of encounters
          {encounters_json}      — full encounter data

        The LLM is the single decision-maker for what gets expanded.
        """
        # Load template
        if PROMPT_PATH.exists():
            with open(PROMPT_PATH) as f:
                template = f.read()
        else:
            raise FileNotFoundError(f"Prompt template not found: {PROMPT_PATH}")

        encounters_json = json.dumps(encounters_data, indent=2)

        # Build supplemental context from all available protocol data
        supplemental_context = self._build_supplemental_context(encounters_data)

        # Build table classification block for dedicated prompt section
        table_profile = getattr(self, "_table_profile", {})
        table_classification = ""
        if table_profile and table_profile.get("tableStructureType"):
            guidance = table_profile.get("stageGuidance", {}).get("stage8_cycles", "")
            table_classification = (
                f"Type: {table_profile.get('tableStructureType', 'unknown')}\n"
                f"Confidence: {table_profile.get('confidence', 0)}\n"
                f"Characteristics: {', '.join(table_profile.get('characteristics', []))}\n"
                f"Cycle Guidance: {guidance}"
            )

        # Format template — {table_classification} is optional for backward compat
        try:
            return template.format(
                supplemental_context=supplemental_context,
                encounter_count=len(encounters_data),
                encounters_json=encounters_json,
                table_classification=table_classification,
            )
        except KeyError:
            # Template doesn't have {table_classification} yet — use old format
            return template.format(
                supplemental_context=supplemental_context,
                encounter_count=len(encounters_data),
                encounters_json=encounters_json,
            )

    def _build_supplemental_context(self, encounters_data: List[Dict[str, Any]]) -> str:
        """
        Assemble all protocol context into a single string block.

        Pulls from:
        - extraction_outputs → study_metadata (treatment design, arms, dosing)
        - extraction_outputs → study_drug (regimen, schedule)
        - extraction_outputs → soa (footnotes)
        - VisitDeltaAnalyzer (auto-detected interval patterns)
        """
        sections = []

        # Table classification (from pre-stage classifier, if available)
        table_profile = getattr(self, "_table_profile", {})
        if table_profile and table_profile.get("tableStructureType"):
            guidance = table_profile.get("stageGuidance", {}).get("stage8_cycles", "")
            sections.append(
                f"TABLE CLASSIFICATION: {table_profile.get('tableStructureType', 'unknown')}\n"
                f"  confidence: {table_profile.get('confidence', 0)}\n"
                f"  characteristics: {', '.join(table_profile.get('characteristics', []))}\n"
                f"  CYCLE EXPANSION GUIDANCE: {guidance}"
            )

        if self._protocol_context:
            # Treatment design
            design_lines = []
            for key in [
                "treatmentDuration", "treatmentCycles", "treatmentDescription",
                "dosingSchedule", "dosingFrequency", "cycleLengthDays", "route",
                "treatmentPeriodDescription",
            ]:
                val = self._protocol_context.get(key)
                if val:
                    design_lines.append(f"  {key}: {val}")

            if self._protocol_context.get("openEndedTreatment"):
                design_lines.append("  openEndedTreatment: true")
                term = self._protocol_context.get("treatmentTermination")
                if term:
                    design_lines.append(f"  treatmentTermination: {term}")

            if design_lines:
                sections.append(
                    "TREATMENT DESIGN:\n" + "\n".join(design_lines)
                )

            # Study arms with dosing
            arms = self._protocol_context.get("arms", [])
            if arms:
                arm_lines = []
                for arm in arms:
                    parts = [f"  Arm: {arm.get('name', 'unknown')}"]
                    if arm.get("description"):
                        parts.append(f"    description: {arm['description']}")
                    for interv in arm.get("interventions", []):
                        interv_parts = []
                        for field in ("dose", "frequency", "schedule"):
                            if interv.get(field):
                                interv_parts.append(f"{field}={interv[field]}")
                        if interv_parts:
                            parts.append(f"    intervention: {', '.join(interv_parts)}")
                    arm_lines.extend(parts)
                if arm_lines:
                    sections.append("STUDY ARMS & DOSING:\n" + "\n".join(arm_lines))

            # Study drug
            sd = self._protocol_context.get("studyDrug", {})
            if sd and any(sd.values()):
                sd_lines = [f"  {k}: {v}" for k, v in sd.items() if v]
                sections.append("STUDY DRUG:\n" + "\n".join(sd_lines))

            # Duration signals — critical for resolving open-ended patterns
            duration_lines = []
            for key in [
                "studyDuration", "primaryEndpointTimeline", "maxCyclesFromProtocol",
                "studyPhase", "therapeuticArea", "primaryObjective",
            ]:
                val = self._protocol_context.get(key)
                if val:
                    duration_lines.append(f"  {key}: {val}")
            if duration_lines:
                sections.append(
                    "DURATION SIGNALS (use these to resolve open-ended patterns like 'C4+' or 'Every N Cycles'):\n"
                    + "\n".join(duration_lines)
                )

            # SOA footnotes
            footnotes = self._protocol_context.get("soaFootnotes", [])
            if footnotes:
                fn_lines = [f"  - {fn}" for fn in footnotes[:15]]
                sections.append(
                    "SOA FOOTNOTES (may contain cycle/dosing info):\n" + "\n".join(fn_lines)
                )

        # Visit delta analysis (informational — LLM cross-references with dosing)
        delta_analysis = VisitDeltaAnalyzer.analyze(
            [
                {
                    "name": e.get("name", ""),
                    "id": e.get("id", ""),
                    "parentVisit": e.get("parentVisit"),
                    "timingModifier": e.get("timingModifier"),
                }
                for e in encounters_data
            ]
        )
        if delta_analysis.get("hasPattern"):
            sections.append(
                "VISIT INTERVAL ANALYSIS (auto-detected — cross-reference with dosing above):\n"
                f"  inferredIntervalDays: {delta_analysis['inferredIntervalDays']}\n"
                f"  intervalOccurrences: {delta_analysis['intervalOccurrences']}\n"
                f"  visitDays: {delta_analysis['visitDays']}\n"
                f"  note: {delta_analysis['note']}"
            )

        # Timepoint grouping — alert LLM about sub-visit timepoints
        parent_groups: Dict[str, List[str]] = defaultdict(list)
        for e in encounters_data:
            parent = e.get("parentVisit")
            modifier = e.get("timingModifier")
            if parent and modifier:
                parent_groups[parent].append(modifier)

        if parent_groups:
            tp_lines = []
            for parent, modifiers in parent_groups.items():
                tp_lines.append(
                    f"  {parent}: {len(modifiers)} timepoints — {', '.join(modifiers)}"
                )
            tp_lines.append(
                "  NOTE: These are timepoint sub-columns within a single visit day."
            )
            tp_lines.append(
                "        They must NOT be treated as separate visits for cycle inference."
            )
            sections.append(
                "TIMEPOINT GROUPING (CRITICAL — sub-visit timepoints, NOT separate cycles):\n"
                + "\n".join(tp_lines)
            )

        if not sections:
            return "(No protocol context available — decide based on encounter data alone)"

        return "\n\n".join(sections)

    # =========== LLM Analysis ===========

    async def _analyze_with_gemini(self, prompt: str) -> Optional[Dict[str, Dict]]:
        """Try analysis with Gemini."""
        client = self._get_gemini_client()
        if not client:
            logger.warning("Gemini client not available")
            return None
        try:
            from google.generativeai.types import HarmCategory, HarmBlockThreshold

            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            response = await asyncio.to_thread(
                client.generate_content,
                prompt,
                generation_config={
                    "temperature": self.config.temperature,
                    "max_output_tokens": self.config.max_output_tokens,
                    "response_mime_type": "application/json",
                },
                safety_settings=safety_settings,
            )
            if response.candidates and response.candidates[0].finish_reason.name == "SAFETY":
                logger.warning("Gemini safety filter blocked request")
                return None
            if not response.text:
                logger.warning("Gemini returned empty response")
                return None
            return self._parse_llm_response(response.text)
        except Exception as e:
            logger.warning(f"Gemini cycle analysis failed: {e}")
            return None

    async def _analyze_with_azure(self, prompt: str) -> Optional[Dict[str, Dict]]:
        """Try analysis with Azure OpenAI (fallback)."""
        client = self._get_azure_client()
        if not client:
            logger.warning("Azure OpenAI client not available")
            return None
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=self._azure_deployment,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=self.config.max_output_tokens,
                temperature=self.config.temperature,
            )
            content = response.choices[0].message.content
            if not content:
                logger.warning("Azure OpenAI returned empty response")
                return None
            logger.info(f"Azure OpenAI responded ({len(content)} chars)")
            return self._parse_llm_response(content)
        except Exception as e:
            logger.error(f"Azure OpenAI cycle analysis failed: {e}")
            return None

    async def _analyze_with_claude(self, prompt: str) -> Optional[Dict[str, Dict]]:
        """Try analysis with Anthropic Claude (fallback)."""
        client = self._get_claude_client()
        if not client:
            logger.warning("Anthropic Claude client not available")
            return None
        try:
            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=self.config.max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text if response.content else None
            if not content:
                logger.warning("Anthropic Claude returned empty response")
                return None
            logger.info(f"Anthropic Claude responded ({len(content)} chars)")
            return self._parse_llm_response(content)
        except Exception as e:
            logger.error(f"Anthropic Claude cycle analysis failed: {e}")
            return None

    def _parse_llm_response(self, response_text: str) -> Dict[str, Dict]:
        """Parse LLM response into decision dictionaries."""
        results = {}
        try:
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            data = json.loads(text)
            if isinstance(data, dict):
                results = data
            logger.info(f"Parsed {len(results)} cycle decisions from LLM")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response text: {response_text[:500]}...")
        return results

    async def _analyze_cycles_batch(
        self,
        encounters_data: List[Dict[str, Any]],
    ) -> Dict[str, CycleDecision]:
        """
        Send ALL encounters to LLM for cycle analysis in batches.

        The LLM decides for each encounter:
        - shouldExpand: true/false
        - expandedCycles: [1, 2, 3, ...] if expanding
        - skipReason: why it chose not to expand
        - requiresHumanReview: true if ambiguous
        """
        if not encounters_data:
            return {}

        all_decisions = {}

        for i in range(0, len(encounters_data), self.config.max_patterns_per_batch):
            batch = encounters_data[i:i + self.config.max_patterns_per_batch]
            prompt = self._build_llm_prompt(batch)

            # LLM routing
            use_claude_primary = os.getenv("USE_CLAUDE_PRIMARY", "").lower() == "true"

            if use_claude_primary:
                logger.info("Using Claude as primary LLM (USE_CLAUDE_PRIMARY=true)")
                llm_results = await self._analyze_with_claude(prompt)
                if not llm_results:
                    logger.info("Claude failed — falling back to Gemini...")
                    llm_results = await self._analyze_with_gemini(prompt)
                if not llm_results:
                    logger.info("Gemini failed — falling back to Azure...")
                    llm_results = await self._analyze_with_azure(prompt)
            else:
                llm_results = await self._analyze_with_gemini(prompt)
                if not llm_results:
                    logger.info("Gemini failed — falling back to Azure OpenAI...")
                    llm_results = await self._analyze_with_azure(prompt)
                if not llm_results:
                    logger.info("Azure failed — falling back to Anthropic Claude...")
                    llm_results = await self._analyze_with_claude(prompt)

            if not llm_results:
                logger.error(f"All LLMs failed for batch starting at index {i}")
                # Create low-confidence "review" decisions for every encounter
                for enc_data in batch:
                    enc_id = enc_data.get("id", "")
                    enc_name = enc_data.get("name", "")
                    recurrence_key = CycleDecision.build_recurrence_key(enc_data.get("recurrence"))
                    all_decisions[enc_id] = CycleDecision(
                        encounter_name=enc_name,
                        recurrence_key=recurrence_key,
                        should_expand=False,
                        expanded_cycles=[],
                        confidence=0.0,
                        rationale="All LLMs failed — flagged for human review",
                        requires_human_review=True,
                        review_reason="LLM analysis failed for this batch",
                        source="fallback",
                    )
                continue

            # Convert LLM response to CycleDecision objects
            for enc_data in batch:
                enc_id = enc_data.get("id", "")
                enc_name = enc_data.get("name", "")
                recurrence_key = CycleDecision.build_recurrence_key(enc_data.get("recurrence"))

                if enc_id in llm_results:
                    item = llm_results[enc_id]

                    pattern_type = None
                    if item.get("patternType"):
                        try:
                            pattern_type = CyclePatternType(item["patternType"].lower())
                        except ValueError:
                            pass

                    all_decisions[enc_id] = CycleDecision(
                        encounter_name=enc_name,
                        recurrence_key=recurrence_key,
                        should_expand=item.get("shouldExpand", False),
                        expanded_cycles=item.get("expandedCycles", []),
                        pattern_type=pattern_type,
                        cycle_length_days=item.get("cycleLengthDays"),
                        confidence=float(item.get("confidence", 0.8)),
                        rationale=item.get("rationale"),
                        requires_human_review=item.get("requiresHumanReview", False),
                        review_reason=item.get("reviewReason"),
                        source="llm",
                        model_name=self.config.model_name,
                        suggested_encounter_names=item.get("suggestedEncounterNames"),
                        absolute_study_day=item.get("absoluteStudyDay"),
                        absolute_study_days=item.get("absoluteStudyDays"),
                    )
                else:
                    # LLM didn't mention this encounter — treat as "no expand"
                    all_decisions[enc_id] = CycleDecision(
                        encounter_name=enc_name,
                        recurrence_key=recurrence_key,
                        should_expand=False,
                        expanded_cycles=[],
                        confidence=0.5,
                        rationale="LLM did not return a decision for this encounter",
                        source="default",
                    )

        return all_decisions

    # =========== Validation (Post-LLM) ===========

    def _validate_against_patterns(
        self,
        decisions: Dict[str, CycleDecision],
    ) -> List[CycleValidationDiscrepancy]:
        """
        Cross-check LLM decisions against known patterns.

        This is a post-LLM advisory check. It flags discrepancies
        but NEVER overrides the LLM decision.
        """
        discrepancies = []

        for enc_id, decision in decisions.items():
            known = self._pattern_registry.get_known_expansion(decision.encounter_name)
            if known:
                if decision.should_expand:
                    if set(decision.expanded_cycles) != set(known):
                        discrepancies.append(CycleValidationDiscrepancy(
                            encounter_name=decision.encounter_name,
                            recurrence_key=decision.recurrence_key,
                            llm_cycles=decision.expanded_cycles,
                            pattern_cycles=known,
                            pattern_id="known_cycle_expansions",
                            severity="warning",
                            message=(
                                f"LLM expanded to {decision.expanded_cycles} "
                                f"but known pattern expects {known}"
                            ),
                        ))
                else:
                    discrepancies.append(CycleValidationDiscrepancy(
                        encounter_name=decision.encounter_name,
                        recurrence_key=decision.recurrence_key,
                        llm_cycles=[],
                        pattern_cycles=known,
                        pattern_id="known_cycle_expansions",
                        severity="warning",
                        message=f"LLM says no expansion but known pattern expects {known}",
                    ))

        if discrepancies:
            logger.warning(
                f"Found {len(discrepancies)} advisory discrepancies "
                f"(LLM decisions NOT overridden)"
            )

        return discrepancies

    # =========== Encounter Generation ===========

    def _get_max_encounter_number(self, encounters: List[Dict[str, Any]]) -> int:
        """Find the highest sequential encounter number (e.g. ENC-015 → 15)."""
        max_num = 0
        for enc in encounters:
            enc_id = enc.get("id", "")
            match = re.match(r"ENC-(\d+)", enc_id)
            if match:
                max_num = max(max_num, int(match.group(1)))
        return max_num

    def _generate_encounter_id(self, seq_number: int) -> str:
        """Generate sequential encounter ID (ENC-016, ENC-017, ...)."""
        return f"ENC-{seq_number:03d}"

    def _generate_encounter_name(self, original_name: str, cycle_number: int) -> str:
        """Generate cycle-specific encounter name."""
        name = original_name

        # Replace generic cycle references with specific cycle number
        replacements = [
            (r"each\s+cycle", f"Cycle {cycle_number}"),
            (r"all\s+cycles", f"Cycle {cycle_number}"),
            (r"every\s+cycle", f"Cycle {cycle_number}"),
        ]
        for pattern, replacement in replacements:
            if re.search(pattern, name, re.IGNORECASE):
                name = re.sub(pattern, replacement, name, flags=re.IGNORECASE)
                return name

        # If "day X of" exists without cycle context, prepend cycle
        if re.search(r"day\s+\d+\s+of", name, re.IGNORECASE) and "cycle" not in name.lower():
            return f"Cycle {cycle_number} {name}"

        # Default: prepend cycle if not already present
        if f"cycle {cycle_number}" not in name.lower():
            return f"Cycle {cycle_number} - {name}"

        return name

    def _generate_expanded_encounters(
        self,
        encounter: Dict[str, Any],
        decision: CycleDecision,
        next_seq: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Create expanded encounter objects with proper IDs, Code objects, and provenance.

        Args:
            next_seq: Next available sequential encounter number for ID generation.
        """
        expanded_encounters = []
        original_id = encounter.get("id", "")
        original_name = encounter.get("name", "")
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Extract day-in-cycle from original encounter's recurrence or name
        day_in_cycle = 1
        rec = encounter.get("recurrence") or {}
        if rec.get("cycleDay"):
            day_in_cycle = rec["cycleDay"]
        else:
            day_match = re.search(r'[Dd]ay\s*([+-]?\d+)', original_name)
            if day_match:
                day_in_cycle = int(day_match.group(1))

        for i, cycle_num in enumerate(decision.expanded_cycles):
            is_steady_state = cycle_num >= self.config.steady_state_threshold

            new_id = self._generate_encounter_id(next_seq + i)
            # Prefer LLM-suggested name, fall back to auto-generated
            if decision.suggested_encounter_names and str(cycle_num) in decision.suggested_encounter_names:
                new_name = decision.suggested_encounter_names[str(cycle_num)]
            else:
                new_name = self._generate_encounter_name(original_name, cycle_num)

            cycle_number_code = self._create_cycle_number_code(
                cycle_num, original_id, is_steady_state
            )

            new_encounter = {
                "id": new_id,
                "name": new_name,
                "instanceType": encounter.get("instanceType", "Encounter"),
                "type": encounter.get("type"),
                "window": encounter.get("window"),
                "footnoteMarkers": encounter.get("footnoteMarkers", []).copy(),
                "cycleNumber": cycle_number_code,
                "_cycleExpansion": {
                    "originalId": original_id,
                    "originalName": original_name,
                    "cycleNumber": cycle_num,
                    "isSteadyState": is_steady_state,
                    "confidence": decision.confidence,
                    "rationale": decision.rationale,
                    "stage": "Stage8CycleExpansion",
                    "model": decision.model_name or self.config.model_name,
                    "timestamp": timestamp,
                    "source": decision.source,
                    "cacheHit": decision.source == "cache",
                    "cacheKey": decision.get_cache_key(),
                    "originalRecurrence": encounter.get("recurrence"),
                    "dayInCycle": day_in_cycle,
                    "absoluteStudyDay": (
                        decision.absolute_study_days.get(str(cycle_num))
                        if decision.absolute_study_days else None
                    ),
                },
            }

            if encounter.get("provenance"):
                new_encounter["_cycleExpansion"]["originalProvenance"] = encounter["provenance"]

            if encounter.get("schedulingPattern"):
                new_encounter["schedulingPattern"] = encounter["schedulingPattern"]

            expanded_encounters.append(new_encounter)

        return expanded_encounters

    def _duplicate_sais_for_cycles(
        self,
        sais: List[Dict[str, Any]],
        original_encounter_id: str,
        expanded_encounters: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Create SAI copies for each expanded cycle encounter."""
        new_sais = []

        affected_sais = [
            sai for sai in sais
            if (sai.get("visitId") or sai.get("scheduledInstanceEncounterId", ""))
            == original_encounter_id
        ]

        if not affected_sais:
            return []

        for expanded_enc in expanded_encounters:
            cycle_num = expanded_enc.get("_cycleExpansion", {}).get("cycleNumber", 1)
            enc_id = expanded_enc.get("id", "")

            for sai in affected_sais:
                new_sai = {
                    **sai,
                    "id": f"{sai['id']}-C{cycle_num}",
                    "visitId": enc_id,
                    "scheduledInstanceEncounterId": enc_id,
                    "footnoteMarkers": sai.get("footnoteMarkers", []).copy(),
                    "_cycleExpansion": {
                        "originalSaiId": sai["id"],
                        "originalEncounterId": original_encounter_id,
                        "cycleNumber": cycle_num,
                        "stage": "Stage8CycleExpansion",
                    },
                }
                new_sais.append(new_sai)

        return new_sais

    # =========== Main Entry Point ===========

    async def expand_cycles(
        self,
        usdm_output: Dict[str, Any],
        extraction_outputs: Optional[Dict[str, Dict]] = None,
    ) -> Stage8Result:
        """
        Process ALL encounters through LLM for cycle expansion decisions.

        v2 changes:
        - No hardcoded skip logic. Every encounter goes to LLM.
        - Only skips already-expanded encounters (from prior runs).
        - Protocol context (dosing, study drug, footnotes) is injected into prompt.
        - Visit delta analysis is included as advisory context.

        Args:
            usdm_output: USDM output from previous stages
            extraction_outputs: Main pipeline extraction outputs
                               (study_metadata, soa, study_drug, etc.)

        Returns:
            Stage8Result with expansions and metrics
        """
        self._load_cache()

        result = Stage8Result()

        # Store extraction context for protocol-aware LLM prompting
        self._extraction_outputs = extraction_outputs or {}
        self._protocol_context = self._extract_protocol_context()

        # Store table profile from classifier (if available)
        self._table_profile = usdm_output.get("soaTableProfile", {})

        # 1. Extract encounters
        encounters = self._get_encounters(usdm_output)
        result.encounters_processed = len(encounters)
        logger.info(f"Stage 8: Processing {len(encounters)} encounters (no pre-filtering)")

        if not encounters:
            logger.info("No encounters found in USDM output")
            return result

        # 2. Only skip already-expanded encounters (from a prior run)
        encounters_for_llm = []
        for enc in encounters:
            if enc.get("_cycleExpansion"):
                result.encounters_skipped += 1
                logger.debug(f"Skipping already-expanded: {enc.get('id')}")
                continue
            encounters_for_llm.append(enc)

        if not encounters_for_llm:
            logger.info("All encounters already expanded in prior run")
            return result

        # 3. Check cache for each encounter
        #    Cache coherence: if ANY encounter in the batch is a cache miss,
        #    skip cache for ALL encounters and send the entire batch to the LLM.
        #    This prevents stale absoluteStudyDay values from cached encounters
        #    being mixed with fresh values from uncached ones (the root cause
        #    of visit misordering after cycle expansion recalculation).
        uncached_encounters = []
        cached_decisions = {}
        has_cache_miss = False
        for enc in encounters_for_llm:
            enc_name = enc.get("name", "")
            recurrence_key = CycleDecision.build_recurrence_key(enc.get("recurrence"))

            cached = self._check_cache(enc_name, recurrence_key)
            if cached:
                cached_decisions[enc.get("id", "")] = cached
            else:
                has_cache_miss = True
                uncached_encounters.append(enc)

        # Also check for stale cache entries missing absoluteStudyDays
        # (cached before the absoluteStudyDay feature was added)
        if not has_cache_miss:
            for enc_id, cached in cached_decisions.items():
                if cached.should_expand and not cached.absolute_study_days:
                    has_cache_miss = True
                    logger.info(
                        f"Cache coherence: cached decision for '{cached.encounter_name}' "
                        f"missing absolute_study_days — treating as stale"
                    )
                    break

        if has_cache_miss:
            # Cache miss detected — send ALL encounters to LLM for consistent
            # absoluteStudyDay values across the entire batch
            uncached_encounters = encounters_for_llm
            logger.info(
                f"Cache coherence: {len(cached_decisions)} cached decisions invalidated "
                f"because {len(encounters_for_llm) - len(cached_decisions)} encounters "
                f"were cache misses or stale — sending full batch to LLM"
            )
        else:
            # All encounters hit cache — use cached decisions
            for enc_id, cached in cached_decisions.items():
                result.decisions[enc_id] = cached
                result.cache_hits += 1

        # 4. LLM analysis for ALL uncached encounters (no pre-filtering)
        if uncached_encounters:
            logger.info(
                f"Sending {len(uncached_encounters)} encounters to LLM "
                f"(with protocol context: {bool(self._protocol_context)})"
            )

            encounters_data = []
            for enc in uncached_encounters:
                enc_data = {
                    "id": enc.get("id", ""),
                    "name": enc.get("name", ""),
                    "type": enc.get("type"),
                }
                # Include recurrence if it exists
                if enc.get("recurrence"):
                    enc_data["recurrence"] = enc["recurrence"]
                # Include any sub-encounters or timepoints as context
                if enc.get("subEncounters"):
                    enc_data["subEncounters"] = enc["subEncounters"]
                if enc.get("timepoints"):
                    enc_data["timepoints"] = enc["timepoints"]
                # Include scheduling pattern
                if enc.get("schedulingPattern"):
                    enc_data["schedulingPattern"] = enc["schedulingPattern"]
                # Include timing fields for timepoint awareness
                enc_data["timingModifier"] = enc.get("timingModifier")
                enc_data["parentVisit"] = enc.get("parentVisit")
                enc_data["visitType"] = enc.get("visitType")
                encounters_data.append(enc_data)

            llm_decisions = await self._analyze_cycles_batch(encounters_data)
            result.llm_calls = len(
                range(0, len(uncached_encounters), self.config.max_patterns_per_batch)
            )
            result.unique_patterns_analyzed = len(uncached_encounters)

            # Cache and store
            for enc in uncached_encounters:
                enc_id = enc.get("id", "")
                enc_name = enc.get("name", "")
                recurrence_key = CycleDecision.build_recurrence_key(enc.get("recurrence"))

                if enc_id in llm_decisions:
                    decision = llm_decisions[enc_id]
                    self._update_cache(enc_name, recurrence_key, decision)
                    result.decisions[enc_id] = decision

            self._save_cache()

        # 5. Count encounters with recurrence (for metrics, not filtering)
        for enc in encounters_for_llm:
            if enc.get("recurrence"):
                result.encounters_with_recurrence += 1

        # 6. Advisory validation against known patterns
        if self.config.validate_against_patterns:
            discrepancies = self._validate_against_patterns(result.decisions)
            result.discrepancies = discrepancies
            result.validation_flags = len(discrepancies)

        # 7. Generate expanded encounters and SAIs based on LLM decisions
        sais = self._get_sais(usdm_output)
        result.sais_processed = len(sais)

        # Sequential ID counter — starts after the highest existing encounter number
        all_encounters = self._get_encounters(usdm_output)
        next_seq = self._get_max_encounter_number(all_encounters) + 1

        for enc in encounters_for_llm:
            enc_id = enc.get("id", "")
            decision = result.decisions.get(enc_id)

            if not decision:
                continue

            # Handle human review items
            if decision.requires_human_review:
                result.add_event_driven_review(
                    enc,
                    decision.review_reason or "LLM flagged for human review",
                )

            if decision.should_expand and decision.expanded_cycles:
                expanded_encounters = self._generate_expanded_encounters(enc, decision, next_seq)
                next_seq += len(expanded_encounters)
                new_sais = self._duplicate_sais_for_cycles(sais, enc_id, expanded_encounters)

                expansion = CycleExpansion(
                    original_encounter_id=enc_id,
                    original_name=enc.get("name", ""),
                    original_recurrence=enc.get("recurrence"),
                    expanded_encounters=expanded_encounters,
                    expanded_sai_ids=[s["id"] for s in new_sais],
                    decision=decision,
                    requires_review=(
                        decision.requires_human_review
                        or decision.confidence < self.config.confidence_threshold_review
                    ),
                    review_reason=decision.review_reason,
                    provenance=enc.get("provenance"),
                )
                result.add_expansion(expansion)

        logger.info(
            f"Stage 8 complete: {result.encounters_processed} processed, "
            f"{result.encounters_expanded} expanded, {result.encounters_created} created, "
            f"{result.cache_hits} cache hits, {result.encounters_skipped} skipped (already expanded)"
        )

        return result

    # =========== USDM Accessors ===========

    def _get_encounters(self, usdm_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract encounters from USDM output (handles nested structure)."""
        encounters = usdm_output.get("encounters", [])
        if encounters:
            return encounters
        if "studyVersion" in usdm_output:
            study_version = usdm_output.get("studyVersion", [])
            if isinstance(study_version, list) and study_version:
                encounters = study_version[0].get("encounters", [])
        return encounters

    def _get_sais(self, usdm_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract SAIs from USDM output (handles nested structure)."""
        sais = usdm_output.get("scheduledActivityInstances", [])
        if sais:
            return sais
        if "studyVersion" in usdm_output:
            study_version = usdm_output.get("studyVersion", [])
            if isinstance(study_version, list) and study_version:
                sais = study_version[0].get("scheduledActivityInstances", [])
        return sais

    # =========== Apply Expansions ===========

    def apply_expansions_to_usdm(
        self,
        usdm_output: Dict[str, Any],
        result: Stage8Result,
    ) -> Dict[str, Any]:
        """
        Apply cycle expansions to USDM output.

        Replaces original encounters with expanded encounters.
        Adds duplicated SAIs for each cycle.
        """
        if not result.expansions:
            return usdm_output

        # Locate encounters and SAIs
        if "studyVersion" in usdm_output:
            study_version = usdm_output.get("studyVersion", [])
            if isinstance(study_version, list) and study_version:
                encounters = study_version[0].get("encounters", [])
                sais = study_version[0].get("scheduledActivityInstances", [])
                is_nested = True
            else:
                return usdm_output
        else:
            encounters = usdm_output.get("encounters", [])
            sais = usdm_output.get("scheduledActivityInstances", [])
            is_nested = False

        if not encounters:
            return usdm_output

        # Build set of IDs to replace
        ids_to_remove = {exp.original_encounter_id for exp in result.expansions}

        # Replace original encounters with expanded ones
        new_encounters = []
        for enc in encounters:
            enc_id = enc.get("id", "")
            if enc_id in ids_to_remove:
                for exp in result.expansions:
                    if exp.original_encounter_id == enc_id:
                        new_encounters.extend(exp.expanded_encounters)
                        break
            else:
                new_encounters.append(enc)

        # Sort ALL encounters by LLM-provided absoluteStudyDay for correct
        # chronological order (e.g., C2D1 → C2D15 → C3D1 instead of C2D1 → C3D1 → C2D15).
        # Also moves non-expanded terminal visits (EOT, Follow-up) to their correct position.

        # Build encounter_id → CycleDecision lookup for non-expanded encounters
        decision_by_enc_id = {}
        for exp in result.expansions:
            if exp.decision:
                decision_by_enc_id[exp.original_encounter_id] = exp.decision
        for _cache_key, dec in result.decisions.items():
            for enc in encounters:
                enc_id = enc.get("id", "")
                if enc_id not in ids_to_remove and enc.get("name", "") == dec.encounter_name:
                    decision_by_enc_id[enc_id] = dec
                    break

        # Build original position map for tiebreaking
        original_positions = {enc.get("id", ""): i for i, enc in enumerate(encounters)}

        # Build expansion decision lookup by original encounter ID
        expansion_decision_by_orig_id = {}
        for exp in result.expansions:
            if exp.decision:
                expansion_decision_by_orig_id[exp.original_encounter_id] = exp.decision

        def _clinical_sort_key(enc):
            enc_id = enc.get("id", "")

            # 1. Expanded encounters: use LLM-provided absoluteStudyDay
            ce = enc.get("_cycleExpansion", {})
            study_day = ce.get("absoluteStudyDay")
            if study_day is not None:
                orig_id = ce.get("originalId", "")
                orig_pos = original_positions.get(orig_id, 999)
                return (study_day, orig_pos)

            # 1b. Expanded encounters missing absoluteStudyDay: compute from cycle metadata
            #     This handles stale cache entries that lack absoluteStudyDays.
            cycle_num = ce.get("cycleNumber")
            if cycle_num is not None:
                orig_id = ce.get("originalId", "")
                day_in_cycle = ce.get("dayInCycle", 1)
                # Get cycle_length_days from the decision
                exp_dec = expansion_decision_by_orig_id.get(orig_id)
                cycle_len = (exp_dec.cycle_length_days if exp_dec else None) or self.config.default_cycle_length
                computed_day = (cycle_num - 1) * cycle_len + day_in_cycle
                orig_pos = original_positions.get(orig_id, 999)
                return (computed_day, orig_pos)

            # 2. Non-expanded encounters: use LLM-provided absoluteStudyDay from decision
            dec = decision_by_enc_id.get(enc_id)
            if dec and dec.absolute_study_day is not None:
                orig_pos = original_positions.get(enc_id, 999)
                return (dec.absolute_study_day, orig_pos)

            # 3. Fallback: sort after all day-based encounters, preserving original order
            orig_pos = original_positions.get(enc_id, 999)
            return (float('inf'), orig_pos)

        new_encounters.sort(key=_clinical_sort_key)

        # Replace original SAIs with expanded ones
        new_sais = list(sais)
        sai_ids_to_remove = set()

        for exp in result.expansions:
            for sai in sais:
                visit_id = sai.get("visitId") or sai.get("scheduledInstanceEncounterId", "")
                if visit_id == exp.original_encounter_id:
                    sai_ids_to_remove.add(sai.get("id", ""))

            all_expanded_sais = self._duplicate_sais_for_cycles(
                sais, exp.original_encounter_id, exp.expanded_encounters
            )
            new_sais.extend(all_expanded_sais)

        new_sais = [s for s in new_sais if s.get("id", "") not in sai_ids_to_remove]

        # Write back
        if is_nested:
            usdm_output["studyVersion"][0]["encounters"] = new_encounters
            usdm_output["studyVersion"][0]["scheduledActivityInstances"] = new_sais
        else:
            usdm_output["encounters"] = new_encounters
            usdm_output["scheduledActivityInstances"] = new_sais

        logger.info(
            f"Applied {len(result.expansions)} cycle expansions to USDM "
            f"({len(new_encounters)} encounters, {len(new_sais)} SAIs)"
        )

        return usdm_output


# ===========================================================================
# Convenience Function
# ===========================================================================

async def expand_cycles(
    usdm_output: Dict[str, Any],
    config: Optional[CycleExpansionConfig] = None,
    use_cache: bool = True,
    extraction_outputs: Optional[Dict[str, Dict]] = None,
) -> Tuple[Dict[str, Any], Stage8Result]:
    """
    Convenience function for cycle expansion.

    Args:
        usdm_output: USDM output from previous stages
        config: Optional configuration
        use_cache: Whether to use caching
        extraction_outputs: Main pipeline extraction outputs
                           for protocol-aware LLM decisions

    Returns:
        Tuple of (updated USDM output, Stage8Result)
    """
    expander = CycleExpander(config=config, use_cache=use_cache)
    result = await expander.expand_cycles(usdm_output, extraction_outputs=extraction_outputs)
    updated_output = expander.apply_expansions_to_usdm(usdm_output, result)
    return updated_output, result