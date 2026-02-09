"""
Stage 7: Timing Distribution

Expands SAIs with merged/complex timing modifiers into separate SAI objects,
each with a single atomic timing modifier.

Design Principles:
1. LLM-First - LLM analyzes ALL timing modifiers in batch (like Stage 1)
2. Cache-Heavy - Cache LLM decisions by timing pattern for reuse
3. Confidence-Based - Auto-apply ≥0.90, escalate <0.90 to review
4. Audit Trail - Full provenance for every expanded entity
5. USDM Compliant - Proper ID generation, referential integrity

Usage:
    from soa_analyzer.interpretation.stage7_timing_distribution import TimingDistributor

    distributor = TimingDistributor()
    result = await distributor.distribute_timing(usdm_output)
    updated_output = distributor.apply_expansions_to_usdm(usdm_output, result)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models.timing_expansion import (
    TimingDecision,
    TimingDistributionConfig,
    TimingExpansion,
    TimingPattern,
    Stage7Result,
    ValidationDiscrepancy,
)
from ..models.expansion_proposal import HumanReviewItem, ReviewStatus
from ..models.code_object import (
    CodeObject,
    NCI_EVS_CODE_SYSTEM,
    NCI_EVS_VERSION,
)

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "timing_distribution"

# Prompt file path
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "timing_distribution.txt"

# Validation patterns config
PATTERNS_PATH = Path(__file__).parent.parent / "config" / "timing_patterns.json"

# CDISC timing codes config
TIMING_CODES_PATH = Path(__file__).parent.parent / "config" / "timing_codes.json"


class TimingPatternRegistry:
    """
    Registry of known timing patterns for validation (NOT primary routing).

    Used to cross-check LLM decisions, not to drive expansion.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._patterns: Dict[str, TimingPattern] = {}
        self._atomic_timings: set = set()
        self._known_expansions: Dict[str, List[str]] = {}
        self._load_config(config_path or PATTERNS_PATH)

    def _load_config(self, config_path: Path) -> None:
        """Load patterns from JSON config."""
        if not config_path.exists():
            logger.warning(f"Timing patterns config not found: {config_path}")
            return

        try:
            with open(config_path) as f:
                data = json.load(f)

            # Load atomic timings
            self._atomic_timings = set(data.get("atomic_timings", []))

            # Load known expansions
            self._known_expansions = data.get("known_expansions", {})

            # Load patterns
            for pattern_id, pattern_data in data.get("patterns", {}).items():
                self._patterns[pattern_id] = TimingPattern(
                    id=pattern_id,
                    pattern_regex=pattern_data.get("pattern_regex", ""),
                    atomic_timings=pattern_data.get("atomic_timings", []),
                    description=pattern_data.get("description"),
                )

            logger.info(
                f"Loaded {len(self._patterns)} timing patterns, "
                f"{len(self._atomic_timings)} atomic timings"
            )
        except Exception as e:
            logger.warning(f"Failed to load timing patterns config: {e}")

    def is_atomic(self, timing_modifier: str) -> bool:
        """Check if timing modifier is already atomic (no expansion needed)."""
        if not timing_modifier:
            return True
        normalized = timing_modifier.lower().strip()
        return normalized in {t.lower() for t in self._atomic_timings}

    def get_known_expansion(self, timing_modifier: str) -> Optional[List[str]]:
        """Get known expansion for a timing modifier (if exists)."""
        normalized = timing_modifier.strip()
        return self._known_expansions.get(normalized)

    def find_matching_pattern(self, timing_modifier: str) -> Optional[TimingPattern]:
        """Find a pattern that matches the timing modifier."""
        if not timing_modifier:
            return None

        for pattern in self._patterns.values():
            if pattern.matches(timing_modifier):
                return pattern
        return None


class TimingDistributor:
    """
    Stage 7: Timing Distribution Handler (LLM-First Strategy).

    Expands SAIs with merged/complex timing modifiers into separate SAIs.
    Uses LLM-first approach with caching and pattern validation.
    """

    def __init__(
        self,
        config: Optional[TimingDistributionConfig] = None,
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
    ):
        """
        Initialize timing distributor.

        Args:
            config: Configuration for timing distribution
            use_cache: Whether to use persistent caching
            cache_dir: Directory for cache files
        """
        self.config = config or TimingDistributionConfig()
        self.use_cache = use_cache
        self.cache_dir = cache_dir or CACHE_DIR

        # Pattern registry for validation
        self._pattern_registry = TimingPatternRegistry()

        # Load CDISC timing codes for Code object creation
        self._timing_codes = self._load_timing_codes()

        # In-memory cache: timing_modifier -> TimingDecision
        self._cache: Dict[str, TimingDecision] = {}
        self._cache_loaded = False

        # LLM clients (lazy loaded)
        self._gemini_client = None
        self._azure_client = None
        self._azure_deployment = None

        # Ensure cache directory exists
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_timing_codes(self) -> Dict[str, Dict[str, Any]]:
        """Load CDISC timing codes from config file."""
        timing_codes = {}
        if TIMING_CODES_PATH.exists():
            try:
                with open(TIMING_CODES_PATH) as f:
                    data = json.load(f)

                # Load all code categories
                for category in ["atomic_timing_codes", "hour_offset_codes", "composite_timing_codes"]:
                    if category in data:
                        for key, code_data in data[category].items():
                            # Normalize key to lowercase for lookup
                            timing_codes[key.lower()] = code_data

                logger.info(f"Loaded {len(timing_codes)} CDISC timing codes")
            except Exception as e:
                logger.warning(f"Failed to load timing codes: {e}")

        return timing_codes

    def _get_timing_code(self, timing: str) -> Dict[str, Any]:
        """
        Get USDM 4.0 compliant Code object for a timing modifier.

        Args:
            timing: Atomic timing string (e.g., "BI", "EOI", "2h post-dose")

        Returns:
            USDM 4.0 compliant Code object dictionary
        """
        normalized = timing.lower().strip()

        # Check timing codes registry
        if normalized in self._timing_codes:
            code_data = self._timing_codes[normalized]
            return CodeObject.from_simple_pair(
                code_data["code"],
                code_data["decode"],
                id_prefix="CODE-TIM",
            ).to_dict()

        # Also check with hyphenated variants (predose -> pre-dose)
        hyphenated = normalized.replace("predose", "pre-dose").replace("postdose", "post-dose")
        if hyphenated in self._timing_codes:
            code_data = self._timing_codes[hyphenated]
            return CodeObject.from_simple_pair(
                code_data["code"],
                code_data["decode"],
                id_prefix="CODE-TIM",
            ).to_dict()

        # Fallback: Create Code object with timing as decode, no CDISC code
        # This preserves the timing information even without a known CDISC mapping
        code_id = f"CODE-TIM-{hashlib.md5(timing.encode()).hexdigest()[:8].upper()}"
        return {
            "id": code_id,
            "code": None,  # No known CDISC code
            "decode": timing,  # Use original timing as decode
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
                        self._cache[key] = TimingDecision.from_dict(decision_data)
                logger.info(f"Loaded {len(self._cache)} cached timing decisions")
            except Exception as e:
                logger.warning(f"Failed to load timing cache: {e}")

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
                },
                "decisions": {key: decision.to_dict() for key, decision in self._cache.items()},
            }
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save timing cache: {e}")

    def _get_cache_key(self, timing_modifier: str) -> str:
        """Generate cache key from timing modifier."""
        normalized = timing_modifier.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()

    def _check_cache(self, timing_modifier: str) -> Optional[TimingDecision]:
        """Return cached decision if exists."""
        cache_key = self._get_cache_key(timing_modifier)
        if cache_key in self._cache:
            decision = self._cache[cache_key]
            # Update source to indicate it came from cache
            decision.source = "cache"
            return decision
        return None

    def _update_cache(self, timing_modifier: str, decision: TimingDecision) -> None:
        """Store decision in cache."""
        cache_key = self._get_cache_key(timing_modifier)
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

    # =========== LLM Analysis ===========

    def _build_llm_prompt(self, timing_modifiers: List[str]) -> str:
        """Build prompt for LLM timing analysis."""
        if PROMPT_PATH.exists():
            with open(PROMPT_PATH) as f:
                template = f.read()
        else:
            raise FileNotFoundError(f"Prompt template not found: {PROMPT_PATH}")

        timing_modifiers_json = json.dumps(timing_modifiers, indent=2)

        return template.format(
            timing_modifiers_json=timing_modifiers_json,
            timing_count=len(timing_modifiers),
        )

    async def _analyze_with_gemini(
        self,
        prompt: str,
    ) -> Optional[Dict[str, Dict]]:
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
            logger.warning(f"Gemini timing analysis failed: {e}")
            return None

    async def _analyze_with_azure(
        self,
        prompt: str,
    ) -> Optional[Dict[str, Dict]]:
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
            logger.error(f"Azure OpenAI timing analysis failed: {e}")
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

            # Handle both dict and list formats
            if isinstance(data, list):
                # Convert list to dict
                for item in data:
                    timing_mod = item.get("timingModifier") or item.get("timing_modifier", "")
                    if timing_mod:
                        results[timing_mod] = item
            else:
                results = data

            logger.info(f"Parsed {len(results)} timing decisions from LLM")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response text: {response_text[:500]}...")

        return results

    async def _analyze_timing_batch(
        self,
        timing_modifiers: List[str],
    ) -> Dict[str, TimingDecision]:
        """
        Send ALL timing modifiers to LLM for analysis.

        Returns: {timing_modifier: TimingDecision}
        """
        if not timing_modifiers:
            return {}

        prompt = self._build_llm_prompt(timing_modifiers)

        # Try Gemini first
        llm_results = await self._analyze_with_gemini(prompt)

        # Fall back to Azure if Gemini fails
        if not llm_results:
            logger.info("Gemini failed - falling back to Azure OpenAI...")
            llm_results = await self._analyze_with_azure(prompt)

        if not llm_results:
            logger.error("Both Gemini and Azure OpenAI failed for timing analysis")
            return {}

        # Convert to TimingDecision objects
        decisions = {}
        for timing_mod in timing_modifiers:
            if timing_mod in llm_results:
                item = llm_results[timing_mod]
                decisions[timing_mod] = TimingDecision(
                    timing_modifier=timing_mod,
                    should_expand=item.get("shouldExpand", False),
                    expanded_timings=item.get("expandedTimings", []),
                    confidence=float(item.get("confidence", 0.8)),
                    rationale=item.get("rationale"),
                    source="llm",
                    model_name=self.config.model_name,
                )
            else:
                # LLM didn't return this modifier - assume no expansion
                decisions[timing_mod] = TimingDecision(
                    timing_modifier=timing_mod,
                    should_expand=False,
                    expanded_timings=[],
                    confidence=0.5,
                    rationale="LLM did not provide decision",
                    source="default",
                )

        return decisions

    # =========== Validation ===========

    def _validate_against_patterns(
        self,
        decisions: Dict[str, TimingDecision],
    ) -> List[ValidationDiscrepancy]:
        """
        Cross-check LLM decisions against known patterns.

        Returns list of discrepancies for logging/review.
        """
        discrepancies = []

        for timing_mod, decision in decisions.items():
            # Check against known expansions
            known = self._pattern_registry.get_known_expansion(timing_mod)
            if known:
                # Compare with LLM decision
                if decision.should_expand:
                    llm_set = set(decision.expanded_timings)
                    known_set = set(known)
                    if llm_set != known_set:
                        discrepancies.append(ValidationDiscrepancy(
                            timing_modifier=timing_mod,
                            llm_decision=decision.expanded_timings,
                            pattern_decision=known,
                            pattern_id="known_expansions",
                            severity="warning",
                            message=f"LLM expanded to {decision.expanded_timings} but pattern expects {known}",
                        ))
                else:
                    # LLM says don't expand but we have known expansion
                    discrepancies.append(ValidationDiscrepancy(
                        timing_modifier=timing_mod,
                        llm_decision=[],
                        pattern_decision=known,
                        pattern_id="known_expansions",
                        severity="warning",
                        message=f"LLM says no expansion but pattern expects {known}",
                    ))

            # Check if LLM says expand but it's atomic
            if decision.should_expand and self._pattern_registry.is_atomic(timing_mod):
                discrepancies.append(ValidationDiscrepancy(
                    timing_modifier=timing_mod,
                    llm_decision=decision.expanded_timings,
                    pattern_decision=[],
                    pattern_id="atomic_timings",
                    severity="info",
                    message=f"LLM expanded '{timing_mod}' but it's listed as atomic",
                ))

        if discrepancies:
            logger.warning(f"Found {len(discrepancies)} validation discrepancies")

        return discrepancies

    # =========== SAI Generation ===========

    def _generate_sai_id(self, original_id: str, timing_suffix: str) -> str:
        """
        Generate ID for expanded SAI.

        Format: {original_id}-{timing_suffix}
        Examples: SAI-042-BI, SAI-042-EOI, SAI-015-0H
        """
        # Normalize suffix (remove spaces, uppercase)
        suffix = timing_suffix.replace(" ", "").replace("-", "").upper()
        # Limit suffix length
        if len(suffix) > 10:
            suffix = suffix[:10]
        return f"{original_id}-{suffix}"

    def _generate_expanded_sais(
        self,
        sai: Dict[str, Any],
        decision: TimingDecision,
    ) -> List[Dict[str, Any]]:
        """
        Create expanded SAI objects with proper IDs, Code objects, and full provenance.

        Each expanded SAI gets:
        - USDM 4.0 compliant Code object for timingModifier
        - Full provenance tracking in _timingExpansion metadata
        - Footnote condition flagging when applicable
        """
        expanded_sais = []
        original_id = sai.get("id", "")
        footnote_markers = sai.get("footnoteMarkers", [])
        timestamp = datetime.utcnow().isoformat() + "Z"

        for timing in decision.expanded_timings:
            new_id = self._generate_sai_id(original_id, timing)

            # Create USDM 4.0 compliant Code object for timing modifier
            timing_code = self._get_timing_code(timing)

            # Copy original SAI and update
            new_sai = {
                "id": new_id,
                "instanceType": sai.get("instanceType", "ScheduledActivityInstance"),
                "activityId": sai.get("activityId", ""),
                "scheduledInstanceEncounterId": sai.get("scheduledInstanceEncounterId", sai.get("visitId", "")),
                "timingModifier": timing_code,  # Now a USDM 4.0 Code object
                "footnoteMarkers": footnote_markers.copy(),
                "isRequired": sai.get("isRequired", True),
                # Add expansion metadata with full provenance for audit trail
                "_timingExpansion": {
                    "originalId": original_id,
                    "originalTimingModifier": decision.timing_modifier,
                    "expandedTiming": timing,
                    "confidence": decision.confidence,
                    "rationale": decision.rationale,
                    # Enhanced provenance fields
                    "stage": "Stage7TimingDistribution",
                    "model": decision.model_name or self.config.model_name,
                    "timestamp": timestamp,
                    "source": decision.source,  # "llm", "cache", "default"
                    "cacheHit": decision.source == "cache",
                },
            }

            # Flag if footnotes present - may indicate conditional timing
            if footnote_markers:
                new_sai["_hasFootnoteCondition"] = True
                new_sai["_footnoteMarkersPreserved"] = footnote_markers.copy()

            # Copy provenance if exists
            if "provenance" in sai:
                new_sai["provenance"] = sai["provenance"].copy()

            # Copy condition if exists
            if "defaultConditionId" in sai:
                new_sai["defaultConditionId"] = sai["defaultConditionId"]

            expanded_sais.append(new_sai)

        return expanded_sais

    # =========== Main Entry Point ===========

    async def distribute_timing(
        self,
        usdm_output: Dict[str, Any],
    ) -> Stage7Result:
        """
        Process all SAIs and expand timing modifiers.

        Args:
            usdm_output: USDM output from previous stages

        Returns:
            Stage7Result with expansions and metrics
        """
        self._load_cache()

        result = Stage7Result()

        # 1. Extract SAIs
        sais = self._get_sais(usdm_output)
        result.sais_processed = len(sais)

        # 2. Build mapping of timing_modifier -> [SAI IDs]
        timing_to_sais: Dict[str, List[Dict[str, Any]]] = {}
        for sai in sais:
            timing_mod = sai.get("timingModifier")
            if timing_mod:
                result.sais_with_timing += 1
                if timing_mod not in timing_to_sais:
                    timing_to_sais[timing_mod] = []
                timing_to_sais[timing_mod].append(sai)

        unique_timings = list(timing_to_sais.keys())
        result.unique_timings_analyzed = len(unique_timings)

        if not unique_timings:
            logger.info("No timing modifiers found - nothing to expand")
            return result

        # 3. Check cache for each timing modifier
        uncached_timings = []
        for timing_mod in unique_timings:
            cached = self._check_cache(timing_mod)
            if cached:
                result.decisions[timing_mod] = cached
                result.cache_hits += 1
            else:
                uncached_timings.append(timing_mod)

        # 4. LLM analysis for uncached modifiers
        if uncached_timings:
            logger.info(f"Analyzing {len(uncached_timings)} timing modifiers with LLM...")
            llm_decisions = await self._analyze_timing_batch(uncached_timings)
            result.llm_calls = 1

            # Cache and store results
            for timing_mod, decision in llm_decisions.items():
                self._update_cache(timing_mod, decision)
                result.decisions[timing_mod] = decision

            self._save_cache()

        # 5. Validate against patterns (optional)
        if self.config.validate_against_patterns:
            discrepancies = self._validate_against_patterns(result.decisions)
            result.discrepancies = discrepancies
            result.validation_flags = len(discrepancies)

        # 6. Generate expanded SAIs
        for timing_mod, sai_list in timing_to_sais.items():
            decision = result.decisions.get(timing_mod)
            if not decision:
                continue

            for sai in sai_list:
                if decision.should_expand and decision.expanded_timings:
                    # Create expansion
                    expanded_sais = self._generate_expanded_sais(sai, decision)

                    # Check if footnotes present - may indicate conditional timing
                    footnote_markers = sai.get("footnoteMarkers", [])
                    needs_footnote_review = bool(footnote_markers) and self.config.flag_discrepancies
                    review_reason = None

                    if decision.confidence < self.config.confidence_threshold_review:
                        review_reason = "Low confidence timing expansion"
                    elif needs_footnote_review:
                        review_reason = f"SAI has footnotes {footnote_markers} - verify timing conditions apply equally to all expanded timings"

                    expansion = TimingExpansion(
                        original_sai_id=sai.get("id", ""),
                        original_timing_modifier=timing_mod,
                        expanded_sais=expanded_sais,
                        decision=decision,
                        requires_review=(decision.confidence < self.config.confidence_threshold_review) or needs_footnote_review,
                        review_reason=review_reason,
                    )

                    result.expansions.append(expansion)
                    result.sais_expanded += 1
                    result.sais_created += len(expanded_sais)

                    # Add to review items if needed
                    if expansion.requires_review and self.config.flag_discrepancies:
                        priority = "high" if needs_footnote_review else "medium"
                        description = f"Expanded '{timing_mod}' to {decision.expanded_timings}. Confidence: {decision.confidence:.2f}"
                        if needs_footnote_review:
                            description += f". Has footnotes {footnote_markers} - verify conditions."

                        result.review_items.append(HumanReviewItem(
                            item_type="timing_expansion",
                            title=f"Review timing expansion: {timing_mod}",
                            description=description,
                            source_entity_id=sai.get("id", ""),
                            source_entity_type="ScheduledActivityInstance",
                            priority=priority,
                            status=ReviewStatus.PENDING,
                            confidence=decision.confidence,
                        ))
                else:
                    result.sais_unchanged += 1

        logger.info(
            f"Timing distribution complete: {result.sais_processed} SAIs processed, "
            f"{result.sais_expanded} expanded, {result.sais_created} created, "
            f"{result.cache_hits} cache hits"
        )

        return result

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
        result: Stage7Result,
    ) -> Dict[str, Any]:
        """
        Apply timing expansions to USDM output.

        Replaces original SAIs with expanded SAIs.
        """
        if not result.expansions:
            return usdm_output

        # Get SAIs list (handle nested structure)
        if "studyVersion" in usdm_output:
            study_version = usdm_output.get("studyVersion", [])
            if isinstance(study_version, list) and study_version:
                sais = study_version[0].get("scheduledActivityInstances", [])
                sais_key = ("studyVersion", 0, "scheduledActivityInstances")
            else:
                return usdm_output
        else:
            sais = usdm_output.get("scheduledActivityInstances", [])
            sais_key = ("scheduledActivityInstances",)

        if not sais:
            return usdm_output

        # Build set of SAI IDs to remove
        ids_to_remove = {exp.original_sai_id for exp in result.expansions}

        # Build new SAI list
        new_sais = []
        for sai in sais:
            sai_id = sai.get("id", "")
            if sai_id in ids_to_remove:
                # Find expansion and insert expanded SAIs
                for exp in result.expansions:
                    if exp.original_sai_id == sai_id:
                        new_sais.extend(exp.expanded_sais)
                        break
            else:
                new_sais.append(sai)

        # Update USDM output
        if sais_key[0] == "studyVersion":
            usdm_output["studyVersion"][0]["scheduledActivityInstances"] = new_sais
        else:
            usdm_output["scheduledActivityInstances"] = new_sais

        logger.info(f"Applied {len(result.expansions)} timing expansions to USDM output")

        return usdm_output


# =========== Convenience Function ===========

async def distribute_timing(
    usdm_output: Dict[str, Any],
    config: Optional[TimingDistributionConfig] = None,
    use_cache: bool = True,
) -> Tuple[Dict[str, Any], Stage7Result]:
    """
    Convenience function for timing distribution.

    Args:
        usdm_output: USDM output from previous stages
        config: Optional configuration
        use_cache: Whether to use caching

    Returns:
        Tuple of (updated USDM output, Stage7Result)
    """
    distributor = TimingDistributor(config=config, use_cache=use_cache)
    result = await distributor.distribute_timing(usdm_output)
    updated_output = distributor.apply_expansions_to_usdm(usdm_output, result)
    return updated_output, result
