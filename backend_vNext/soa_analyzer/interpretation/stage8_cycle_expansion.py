"""
Stage 8: Cycle Expansion

Expands encounters with repeating cycle patterns (e.g., "Cycles 1-6, Day 1 of each cycle")
into individual cycle-specific encounters.

Design Principles:
1. LLM-First - LLM analyzes ALL recurrence patterns in batch
2. Cache-Heavy - Cache LLM decisions by pattern for reuse
3. Confidence-Based - Auto-apply ≥0.90, escalate <0.90 to review
4. Audit Trail - Full provenance for every expanded entity
5. USDM Compliant - Proper ID generation, cycleNumber Code objects

Handles ALL RecurrenceTypes:
- PER_CYCLE: Oncology cycle-based (Cycles 1-6)
- FIXED_INTERVAL: Time-based (Every 3 weeks x 6)
- AT_EVENT: Event-driven (Until progression) → Flags for review
- CONDITIONAL: Conditional visits → May expand with conditions

Usage:
    from soa_analyzer.interpretation.stage8_cycle_expansion import CycleExpander

    expander = CycleExpander()
    result = await expander.expand_cycles(usdm_output)
    updated_output = expander.apply_expansions_to_usdm(usdm_output, result)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
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
    should_skip_expansion,
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

# Validation patterns config
PATTERNS_PATH = Path(__file__).parent.parent / "config" / "cycle_patterns.json"

# CDISC cycle codes config
CYCLE_CODES_PATH = Path(__file__).parent.parent / "config" / "cycle_codes.json"


class CyclePatternRegistry:
    """
    Registry of known cycle patterns for validation (NOT primary routing).

    Used to cross-check LLM decisions, not to drive expansion.
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

            # Load known expansions
            self._known_cycle_expansions = data.get("known_cycle_expansions", {})
            self._known_interval_expansions = data.get("known_interval_expansions", {})
            self._known_week_expansions = data.get("known_week_expansions", {})

            # Load pattern lists
            self._non_expandable_patterns = data.get("non_expandable_patterns", [])
            self._event_driven_patterns = data.get("event_driven_patterns", [])
            self._steady_state_patterns = data.get("steady_state_patterns", [])

            # Load cycle length defaults
            self._cycle_length_defaults = data.get("cycle_length_defaults", {})

            # Load regex patterns
            for pattern_id, pattern_data in data.get("patterns", {}).items():
                self._patterns[pattern_id] = CyclePattern(
                    id=pattern_id,
                    pattern_type=CyclePatternType.EXPLICIT_RANGE,  # Default
                    pattern_regex=pattern_data.get("pattern_regex", ""),
                    description=pattern_data.get("description"),
                )

            logger.info(
                f"Loaded {len(self._patterns)} cycle patterns, "
                f"{len(self._known_cycle_expansions)} known cycle expansions"
            )
        except Exception as e:
            logger.warning(f"Failed to load cycle patterns config: {e}")

    def is_non_expandable(self, encounter_name: str) -> bool:
        """Check if encounter matches a non-expandable pattern."""
        name_lower = encounter_name.lower()
        for pattern in self._non_expandable_patterns:
            if pattern.lower() in name_lower:
                return True
        return False

    def is_event_driven(self, encounter_name: str) -> bool:
        """Check if encounter matches an event-driven pattern."""
        name_lower = encounter_name.lower()
        for pattern in self._event_driven_patterns:
            if pattern.lower() in name_lower:
                return True
        return False

    def is_steady_state(self, encounter_name: str) -> bool:
        """Check if encounter matches a steady-state pattern."""
        name_lower = encounter_name.lower()
        for pattern in self._steady_state_patterns:
            if pattern.lower() in name_lower:
                return True
        return False

    def get_known_expansion(self, pattern_text: str) -> Optional[List[int]]:
        """Get known expansion for a cycle pattern (if exists)."""
        normalized = pattern_text.strip()

        # Check cycle expansions
        if normalized in self._known_cycle_expansions:
            result = self._known_cycle_expansions[normalized]
            if isinstance(result, list):
                return result
            return None  # Special values like "use_max_cycles"

        # Check interval expansions
        if normalized in self._known_interval_expansions:
            return self._known_interval_expansions[normalized]

        # Check week expansions
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

    def find_matching_pattern(self, text: str) -> Optional[CyclePattern]:
        """Find a pattern that matches the text."""
        if not text:
            return None

        for pattern in self._patterns.values():
            if pattern.matches(text):
                return pattern
        return None


class CycleExpander:
    """
    Stage 8: Cycle Expansion Handler (LLM-First Strategy).

    Expands encounters with repeating cycle patterns into individual
    cycle-specific encounters.
    """

    def __init__(
        self,
        config: Optional[CycleExpansionConfig] = None,
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
    ):
        """
        Initialize cycle expander.

        Args:
            config: Configuration for cycle expansion
            use_cache: Whether to use persistent caching
            cache_dir: Directory for cache files
        """
        self.config = config or CycleExpansionConfig()
        self.use_cache = use_cache
        self.cache_dir = cache_dir or CACHE_DIR

        # Pattern registry for validation
        self._pattern_registry = CyclePatternRegistry()

        # Load CDISC cycle codes for Code object creation
        self._cycle_codes = self._load_cycle_codes()

        # In-memory cache: cache_key -> CycleDecision
        self._cache: Dict[str, CycleDecision] = {}
        self._cache_loaded = False

        # LLM clients (lazy loaded)
        self._gemini_client = None
        self._azure_client = None
        self._azure_deployment = None
        self._claude_client = None

        # Ensure cache directory exists
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Protocol context from extraction_outputs
        self._extraction_outputs: Dict[str, Dict] = {}
        self._protocol_context: Dict[str, Any] = {}

    # =========== Open-Ended Pattern Handling ===========

    def _is_open_ended_pattern(self, encounter: Dict[str, Any]) -> bool:
        """
        Check if an encounter has an open-ended cycle pattern.

        Open-ended patterns include:
        - "Cycle 4 and Subsequent Cycles" (no fixed max)
        - "Until progression" (event-driven)
        - "From Cycle 4 onwards" (no end)
        - Recurrence pattern with startCycle but no maxCycles
        """
        enc_name = encounter.get("name", "")

        # Check encounter name against open-ended patterns
        if self.config.is_open_ended_pattern(enc_name):
            return True

        # Check pattern registry
        if self._pattern_registry.is_steady_state(enc_name):
            return True

        # Check recurrence for open-ended indicators
        recurrence = encounter.get("recurrence", {})
        if recurrence:
            pattern = recurrence.get("pattern", "")
            # Pattern like "CYCLE:4+" indicates open-ended
            if "+" in pattern:
                return True
            # Check if truly open-ended: has startCycle but no end boundary
            # A bounded range like "CYCLE:2-6" has endCycle, so is NOT open-ended
            start_cycle = recurrence.get("startCycle")
            end_cycle = recurrence.get("endCycle")
            max_cycles = recurrence.get("maxCycles")
            if start_cycle and not end_cycle and not max_cycles:
                # Only truly open-ended if no end boundary is specified
                return True

        return False

    def _create_open_ended_decision(self, encounter: Dict[str, Any]) -> CycleDecision:
        """
        Create a CycleDecision for open-ended patterns.

        DO NOT auto-expand with arbitrary defaults.
        Instead, flag for human review with protocol context.
        """
        enc_name = encounter.get("name", "")
        recurrence = encounter.get("recurrence", {})
        recurrence_key = CycleDecision.build_recurrence_key(recurrence)

        # Extract start cycle from recurrence or name
        start_cycle = recurrence.get("startCycle", 4)
        if not start_cycle:
            # Try to parse from name (e.g., "Cycle 4 and Subsequent")
            import re
            match = re.search(r"[Cc]ycle\s*(\d+)", enc_name)
            if match:
                start_cycle = int(match.group(1))

        # Get cycle length from recurrence or default
        cycle_length = recurrence.get("cycleLengthDays")
        if not cycle_length:
            cycle_length = self._pattern_registry.get_cycle_length(enc_name)

        # Get provenance from encounter
        provenance = encounter.get("provenance")

        return CycleDecision.create_open_ended_review(
            encounter_name=enc_name,
            recurrence_key=recurrence_key,
            start_cycle=start_cycle,
            cycle_length_days=cycle_length,
            provenance=provenance,
            protocol_context=self._protocol_context,
        )

    def _extract_protocol_context(self) -> Dict[str, Any]:
        """
        Extract relevant protocol context from study_metadata extraction.

        This provides protocol-aware information for cycle expansion decisions.
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

        # Study periods
        periods = study_metadata.get("studyPeriods", [])
        for period in periods:
            if period.get("periodType") == "Treatment":
                context["treatmentPeriodDescription"] = period.get("description")

        # Study arms for context
        arms = study_metadata.get("arms", [])
        if arms:
            context["armCount"] = len(arms)
            # Check if any arm has cycle info
            for arm in arms:
                arm_desc = arm.get("description", "")
                if "until" in arm_desc.lower() or "discontinu" in arm_desc.lower():
                    context["openEndedTreatment"] = True
                    context["treatmentTermination"] = arm_desc

        return context

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
        """
        Create USDM 4.0 compliant 6-field cycleNumber Code object.

        Args:
            cycle_num: The cycle number (1, 2, 3, etc.)
            encounter_id: Original encounter ID for Code object ID generation
            is_steady_state: Whether this is a steady-state cycle

        Returns:
            USDM 4.0 compliant Code object dictionary
        """
        # Get code data
        if is_steady_state:
            code_data = self._cycle_codes.get("steady_state", {})
            decode = code_data.get("decode", "Steady State Cycle")
        else:
            code_data = self._cycle_codes.get("cycle_numbers", {}).get(
                str(cycle_num),
                self._cycle_codes.get("base_code", {})
            )
            decode = code_data.get("decode", f"Cycle {cycle_num}")

        code = code_data.get("code", "C94535")  # Default cycle code

        # Generate unique ID
        code_id = f"CODE-CYC-{encounter_id}-C{cycle_num}"

        return {
            "id": code_id,
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
                    "version": "1.0.0",
                    "updated": datetime.utcnow().isoformat() + "Z",
                },
                "decisions": {key: decision.to_dict() for key, decision in self._cache.items()},
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
                    logger.info("Initialized Anthropic Claude client: claude-sonnet-4-20250514")
            except Exception as e:
                logger.warning(f"Failed to initialize Anthropic Claude client: {e}")
        return self._claude_client

    # =========== LLM Analysis ===========

    def _build_llm_prompt(self, encounters_data: List[Dict[str, Any]]) -> str:
        """Build prompt for LLM cycle analysis."""
        if PROMPT_PATH.exists():
            with open(PROMPT_PATH) as f:
                template = f.read()
        else:
            raise FileNotFoundError(f"Prompt template not found: {PROMPT_PATH}")

        encounters_json = json.dumps(encounters_data, indent=2)

        return template.format(
            encounters_json=encounters_json,
            encounter_count=len(encounters_data),
        )

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
            # Clean response
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)

            # Handle dict format (encounter_id -> decision)
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
        Send encounters to LLM for cycle analysis in batches.

        Returns: {encounter_id: CycleDecision}
        """
        if not encounters_data:
            return {}

        all_decisions = {}

        # Process in batches to avoid token limits
        for i in range(0, len(encounters_data), self.config.max_patterns_per_batch):
            batch = encounters_data[i:i + self.config.max_patterns_per_batch]
            prompt = self._build_llm_prompt(batch)

            # Check if Claude should be primary (for testing)
            use_claude_primary = os.getenv("USE_CLAUDE_PRIMARY", "").lower() == "true"

            if use_claude_primary:
                # Claude-first mode for testing
                logger.info("Using Claude as primary LLM (USE_CLAUDE_PRIMARY=true)")
                llm_results = await self._analyze_with_claude(prompt)

                if not llm_results:
                    logger.info("Claude failed - falling back to Gemini...")
                    llm_results = await self._analyze_with_gemini(prompt)

                if not llm_results:
                    logger.info("Gemini failed - falling back to Azure...")
                    llm_results = await self._analyze_with_azure(prompt)
            else:
                # Default: Gemini-first mode
                llm_results = await self._analyze_with_gemini(prompt)

                # Fall back to Azure if Gemini fails
                if not llm_results:
                    logger.info("Gemini failed - falling back to Azure OpenAI...")
                    llm_results = await self._analyze_with_azure(prompt)

                # Fall back to Claude if Azure fails
                if not llm_results:
                    logger.info("Azure failed - falling back to Anthropic Claude...")
                    llm_results = await self._analyze_with_claude(prompt)

            if not llm_results:
                logger.error(f"All LLMs (Gemini, Azure, Claude) failed for batch {i}")
                continue

            # Convert to CycleDecision objects
            for enc_data in batch:
                enc_id = enc_data.get("id", "")
                enc_name = enc_data.get("name", "")
                recurrence_key = CycleDecision.build_recurrence_key(enc_data.get("recurrence"))

                if enc_id in llm_results:
                    item = llm_results[enc_id]

                    # Parse pattern type
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
                    )
                else:
                    # LLM didn't return this encounter
                    all_decisions[enc_id] = CycleDecision(
                        encounter_name=enc_name,
                        recurrence_key=recurrence_key,
                        should_expand=False,
                        expanded_cycles=[],
                        confidence=0.5,
                        rationale="LLM did not provide decision",
                        source="default",
                    )

        return all_decisions

    # =========== Validation ===========

    def _validate_against_patterns(
        self,
        decisions: Dict[str, CycleDecision],
    ) -> List[CycleValidationDiscrepancy]:
        """Cross-check LLM decisions against known patterns."""
        discrepancies = []

        for enc_id, decision in decisions.items():
            # Check against known cycle expansions
            known = self._pattern_registry.get_known_expansion(decision.encounter_name)
            if known:
                if decision.should_expand:
                    llm_set = set(decision.expanded_cycles)
                    known_set = set(known)
                    if llm_set != known_set:
                        discrepancies.append(CycleValidationDiscrepancy(
                            encounter_name=decision.encounter_name,
                            recurrence_key=decision.recurrence_key,
                            llm_cycles=decision.expanded_cycles,
                            pattern_cycles=known,
                            pattern_id="known_cycle_expansions",
                            severity="warning",
                            message=f"LLM expanded to {decision.expanded_cycles} but pattern expects {known}",
                        ))
                else:
                    discrepancies.append(CycleValidationDiscrepancy(
                        encounter_name=decision.encounter_name,
                        recurrence_key=decision.recurrence_key,
                        llm_cycles=[],
                        pattern_cycles=known,
                        pattern_id="known_cycle_expansions",
                        severity="warning",
                        message=f"LLM says no expansion but pattern expects {known}",
                    ))

            # Check if LLM says expand but it's non-expandable
            if decision.should_expand and self._pattern_registry.is_non_expandable(decision.encounter_name):
                discrepancies.append(CycleValidationDiscrepancy(
                    encounter_name=decision.encounter_name,
                    recurrence_key=decision.recurrence_key,
                    llm_cycles=decision.expanded_cycles,
                    pattern_cycles=[],
                    pattern_id="non_expandable_patterns",
                    severity="error",
                    message=f"LLM expanded '{decision.encounter_name}' but it's non-expandable",
                ))

        if discrepancies:
            logger.warning(f"Found {len(discrepancies)} cycle validation discrepancies")

        return discrepancies

    # =========== Encounter Generation ===========

    def _generate_encounter_id(self, original_id: str, cycle_number: int) -> str:
        """Generate deterministic encounter ID for cycle expansion."""
        return f"{original_id}-C{cycle_number}"

    def _generate_encounter_name(self, original_name: str, cycle_number: int) -> str:
        """Generate cycle-specific encounter name."""
        # Try to replace generic cycle references
        name = original_name

        # Replace "Each Cycle" with specific cycle
        if "each cycle" in name.lower():
            name = re.sub(r"each cycle", f"Cycle {cycle_number}", name, flags=re.IGNORECASE)
        elif "all cycles" in name.lower():
            name = re.sub(r"all cycles", f"Cycle {cycle_number}", name, flags=re.IGNORECASE)
        elif "every cycle" in name.lower():
            name = re.sub(r"every cycle", f"Cycle {cycle_number}", name, flags=re.IGNORECASE)
        elif "day 1 of" in name.lower() and "cycle" not in name.lower():
            name = f"Cycle {cycle_number} {name}"
        else:
            # Append cycle number if not already present
            if f"cycle {cycle_number}" not in name.lower():
                name = f"Cycle {cycle_number} - {name}"

        return name

    def _generate_expanded_encounters(
        self,
        encounter: Dict[str, Any],
        decision: CycleDecision,
    ) -> List[Dict[str, Any]]:
        """
        Create expanded encounter objects with proper IDs, Code objects, and provenance.
        """
        expanded_encounters = []
        original_id = encounter.get("id", "")
        original_name = encounter.get("name", "")
        timestamp = datetime.utcnow().isoformat() + "Z"

        for cycle_num in decision.expanded_cycles:
            is_steady_state = cycle_num >= self.config.steady_state_threshold

            new_id = self._generate_encounter_id(original_id, cycle_num)
            new_name = self._generate_encounter_name(original_name, cycle_num)

            # Create USDM 4.0 compliant cycleNumber Code object
            cycle_number_code = self._create_cycle_number_code(
                cycle_num, original_id, is_steady_state
            )

            # Create expanded encounter preserving ALL original fields
            new_encounter = {
                "id": new_id,
                "name": new_name,
                "instanceType": encounter.get("instanceType", "Encounter"),
                "type": encounter.get("type"),  # Preserve encounter type
                "window": encounter.get("window"),  # Preserve visit window
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
                },
            }

            # Preserve original provenance if exists
            if encounter.get("provenance"):
                new_encounter["_cycleExpansion"]["originalProvenance"] = encounter["provenance"]

            # Preserve scheduling
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

        # Find SAIs referencing the original encounter
        affected_sais = []
        for sai in sais:
            visit_id = sai.get("visitId") or sai.get("scheduledInstanceEncounterId", "")
            if visit_id == original_encounter_id:
                affected_sais.append(sai)

        if not affected_sais:
            return []

        # Create duplicates for each expanded encounter
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
        Process all encounters and expand cycle patterns.

        Args:
            usdm_output: USDM output from previous stages
            extraction_outputs: Optional main pipeline extraction outputs
                               (e.g., study_metadata for protocol context)

        Returns:
            Stage8Result with expansions and metrics
        """
        self._load_cache()

        result = Stage8Result()

        # Store extraction context for protocol-aware decisions
        self._extraction_outputs = extraction_outputs or {}
        self._protocol_context = self._extract_protocol_context()

        # 1. Extract encounters
        encounters = self._get_encounters(usdm_output)
        result.encounters_processed = len(encounters)

        # 2. Filter encounters needing expansion
        encounters_to_expand = []
        for enc in encounters:
            should_skip, reason = should_skip_expansion(enc, self.config)
            if should_skip:
                result.encounters_skipped += 1
                logger.debug(f"Skipping encounter {enc.get('id')}: {reason}")
                continue

            # Check for event-driven patterns (flag for review)
            if self._pattern_registry.is_event_driven(enc.get("name", "")):
                result.add_event_driven_review(
                    enc,
                    "Event-driven cycle pattern cannot be auto-expanded"
                )
                result.encounters_skipped += 1
                continue

            # Check for open-ended patterns (Cycle 4+, "subsequent", etc.)
            if self._is_open_ended_pattern(enc):
                decision = self._create_open_ended_decision(enc)
                result.decisions[enc.get("id", "")] = decision
                result.add_event_driven_review(
                    enc,
                    decision.review_reason or "Open-ended pattern requires human input"
                )
                result.encounters_skipped += 1
                logger.info(f"Open-ended pattern detected: {enc.get('name')} - flagged for review")
                continue

            result.encounters_with_recurrence += 1
            encounters_to_expand.append(enc)

        if not encounters_to_expand:
            logger.info("No encounters need cycle expansion")
            return result

        # 3. Check cache for each encounter
        uncached_encounters = []
        for enc in encounters_to_expand:
            enc_name = enc.get("name", "")
            recurrence_key = CycleDecision.build_recurrence_key(enc.get("recurrence"))

            cached = self._check_cache(enc_name, recurrence_key)
            if cached:
                result.decisions[enc.get("id", "")] = cached
                result.cache_hits += 1
            else:
                uncached_encounters.append(enc)

        # 4. LLM analysis for uncached encounters
        if uncached_encounters:
            logger.info(f"Analyzing {len(uncached_encounters)} encounters with LLM...")

            # Prepare encounter data for LLM
            encounters_data = []
            for enc in uncached_encounters:
                encounters_data.append({
                    "id": enc.get("id", ""),
                    "name": enc.get("name", ""),
                    "recurrence": enc.get("recurrence"),
                    "type": enc.get("type"),
                })

            llm_decisions = await self._analyze_cycles_batch(encounters_data)
            result.llm_calls = len(range(0, len(uncached_encounters), self.config.max_patterns_per_batch))
            result.unique_patterns_analyzed = len(uncached_encounters)

            # Cache and store results
            for enc in uncached_encounters:
                enc_id = enc.get("id", "")
                enc_name = enc.get("name", "")
                recurrence_key = CycleDecision.build_recurrence_key(enc.get("recurrence"))

                if enc_id in llm_decisions:
                    decision = llm_decisions[enc_id]
                    self._update_cache(enc_name, recurrence_key, decision)
                    result.decisions[enc_id] = decision

            self._save_cache()

        # 5. Validate against patterns (optional)
        if self.config.validate_against_patterns:
            discrepancies = self._validate_against_patterns(result.decisions)
            result.discrepancies = discrepancies
            result.validation_flags = len(discrepancies)

        # 6. Generate expanded encounters and SAIs
        sais = self._get_sais(usdm_output)
        result.sais_processed = len(sais)

        for enc in encounters_to_expand:
            enc_id = enc.get("id", "")
            decision = result.decisions.get(enc_id)

            if not decision:
                continue

            if decision.should_expand and decision.expanded_cycles:
                # Generate expanded encounters
                expanded_encounters = self._generate_expanded_encounters(enc, decision)

                # Duplicate SAIs for each cycle
                new_sais = self._duplicate_sais_for_cycles(sais, enc_id, expanded_encounters)

                # Get provenance from original encounter
                original_provenance = enc.get("provenance")

                expansion = CycleExpansion(
                    original_encounter_id=enc_id,
                    original_name=enc.get("name", ""),
                    original_recurrence=enc.get("recurrence"),
                    expanded_encounters=expanded_encounters,
                    expanded_sai_ids=[s["id"] for s in new_sais],
                    decision=decision,
                    requires_review=decision.requires_human_review or decision.confidence < self.config.confidence_threshold_review,
                    review_reason=decision.review_reason,
                    provenance=original_provenance,
                )

                result.add_expansion(expansion)

        logger.info(
            f"Cycle expansion complete: {result.encounters_processed} encounters processed, "
            f"{result.encounters_expanded} expanded, {result.encounters_created} created, "
            f"{result.cache_hits} cache hits"
        )

        return result

    def _get_encounters(self, usdm_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract encounters from USDM output (handles nested structure)."""
        # Try direct
        encounters = usdm_output.get("encounters", [])
        if encounters:
            return encounters

        # Try nested
        if "studyVersion" in usdm_output:
            study_version = usdm_output.get("studyVersion", [])
            if isinstance(study_version, list) and study_version:
                encounters = study_version[0].get("encounters", [])

        return encounters

    def _get_sais(self, usdm_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract SAIs from USDM output (handles nested structure)."""
        # Try direct
        sais = usdm_output.get("scheduledActivityInstances", [])
        if sais:
            return sais

        # Try nested
        if "studyVersion" in usdm_output:
            study_version = usdm_output.get("studyVersion", [])
            if isinstance(study_version, list) and study_version:
                sais = study_version[0].get("scheduledActivityInstances", [])

        return sais

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

        # Get encounters and SAIs lists
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

        # Build set of encounter IDs to remove
        ids_to_remove = {exp.original_encounter_id for exp in result.expansions}

        # Build new encounter list
        new_encounters = []
        for enc in encounters:
            enc_id = enc.get("id", "")
            if enc_id in ids_to_remove:
                # Find expansion and insert expanded encounters
                for exp in result.expansions:
                    if exp.original_encounter_id == enc_id:
                        new_encounters.extend(exp.expanded_encounters)
                        break
            else:
                new_encounters.append(enc)

        # Build new SAI list (add duplicated SAIs)
        new_sais = list(sais)  # Keep original SAIs
        sai_ids_to_remove = set()

        for exp in result.expansions:
            # Remove SAIs referencing original encounter
            for sai in sais:
                visit_id = sai.get("visitId") or sai.get("scheduledInstanceEncounterId", "")
                if visit_id == exp.original_encounter_id:
                    sai_ids_to_remove.add(sai.get("id", ""))

            # Add duplicated SAIs
            all_expanded_sais = self._duplicate_sais_for_cycles(
                sais, exp.original_encounter_id, exp.expanded_encounters
            )
            new_sais.extend(all_expanded_sais)

        # Remove original SAIs that were expanded
        new_sais = [s for s in new_sais if s.get("id", "") not in sai_ids_to_remove]

        # Update USDM output
        if is_nested:
            usdm_output["studyVersion"][0]["encounters"] = new_encounters
            usdm_output["studyVersion"][0]["scheduledActivityInstances"] = new_sais
        else:
            usdm_output["encounters"] = new_encounters
            usdm_output["scheduledActivityInstances"] = new_sais

        logger.info(
            f"Applied {len(result.expansions)} cycle expansions to USDM output "
            f"({len(new_encounters)} encounters, {len(new_sais)} SAIs)"
        )

        return usdm_output


# =========== Convenience Function ===========

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
        extraction_outputs: Optional main pipeline extraction outputs
                           for protocol-aware decisions

    Returns:
        Tuple of (updated USDM output, Stage8Result)
    """
    expander = CycleExpander(config=config, use_cache=use_cache)
    result = await expander.expand_cycles(usdm_output, extraction_outputs=extraction_outputs)
    updated_output = expander.apply_expansions_to_usdm(usdm_output, result)
    return updated_output, result
