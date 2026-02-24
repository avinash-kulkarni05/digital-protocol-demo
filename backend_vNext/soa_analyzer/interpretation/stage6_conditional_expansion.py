"""
Stage 6: Conditional Expansion

Extracts conditions from SOA footnotes and links them to SAIs using LLM-first architecture.
Addresses the critical gap where SAIs have _hasFootnoteCondition: true but no actual
Condition objects are created.

Design Principles:
1. LLM-First - LLM analyzes ALL footnotes in batch (like Stages 1, 7)
2. Cache-Heavy - Cache LLM decisions by footnote text for reuse
3. Confidence-Based - Auto-apply ≥0.90, escalate <0.90 to review
4. Audit Trail - Full provenance for every condition
5. USDM Compliant - Proper Condition/ConditionAssignment objects

Usage:
    from soa_analyzer.interpretation.stage6_conditional_expansion import ConditionalExpander

    expander = ConditionalExpander()
    result = await expander.expand_conditions(usdm_output)
    updated_output = expander.apply_conditions_to_usdm(usdm_output, result)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models.condition import (
    Condition,
    ConditionAssignment,
    ConditionType,
    DEMOGRAPHIC_PATTERNS,
    CLINICAL_PATTERNS,
)
from ..models.expansion_proposal import HumanReviewItem, ReviewStatus

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "conditional_expansion"

# Prompt file path
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "conditional_expansion.txt"

# Validation patterns config
PATTERNS_PATH = Path(__file__).parent.parent / "config" / "condition_patterns.json"


@dataclass
class ConditionExtraction:
    """Result of extracting a condition from a footnote."""
    footnote_marker: str
    footnote_text: str
    has_condition: bool
    condition_type: Optional[str] = None
    condition_name: Optional[str] = None
    condition_text: Optional[str] = None
    criterion: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    rationale: Optional[str] = None
    source: str = "llm"  # "llm", "pattern", "cached"


@dataclass
class ConditionalExpansionConfig:
    """Configuration for conditional expansion stage."""
    use_llm: bool = True
    confidence_threshold_auto: float = 0.90
    confidence_threshold_review: float = 0.70
    use_cache: bool = True
    flag_discrepancies: bool = True
    model_name: str = "gemini-3-pro-preview"
    max_retries: int = 3


@dataclass
class Stage6Result:
    """Result of conditional expansion stage."""
    conditions: List[Condition] = field(default_factory=list)
    assignments: List[ConditionAssignment] = field(default_factory=list)
    marker_to_condition: Dict[str, str] = field(default_factory=dict)
    review_items: List[HumanReviewItem] = field(default_factory=list)

    # Metrics
    footnotes_analyzed: int = 0
    conditions_created: int = 0
    assignments_created: int = 0
    sais_linked: int = 0
    high_confidence: int = 0
    needs_review: int = 0
    cache_hits: int = 0
    llm_calls: int = 0

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        return {
            "footnotes_analyzed": self.footnotes_analyzed,
            "conditions_created": self.conditions_created,
            "assignments_created": self.assignments_created,
            "sais_linked": self.sais_linked,
            "high_confidence": self.high_confidence,
            "needs_review": self.needs_review,
            "cache_hits": self.cache_hits,
            "llm_calls": self.llm_calls,
            "condition_coverage": (
                self.conditions_created / max(self.footnotes_analyzed, 1)
            ),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary for stage output."""
        return {
            "stage": 6,
            "stageName": "Conditional Expansion",
            "success": True,
            "conditions": [c.to_dict() for c in self.conditions],
            "assignments": [a.to_dict() for a in self.assignments],
            "markerToCondition": self.marker_to_condition,
            "metrics": {
                "footnotesAnalyzed": self.footnotes_analyzed,
                "conditionsCreated": self.conditions_created,
                "assignmentsCreated": self.assignments_created,
                "saisLinked": self.sais_linked,
                "highConfidence": self.high_confidence,
                "needsReview": self.needs_review,
                "cacheHits": self.cache_hits,
                "llmCalls": self.llm_calls,
                "conditionCoverage": self.conditions_created / max(self.footnotes_analyzed, 1),
            },
            "reviewItems": [r.to_dict() for r in self.review_items],
        }


class ConditionPatternRegistry:
    """
    Registry of known condition patterns for validation (NOT primary routing).

    Used to cross-check LLM decisions, not to drive extraction.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._patterns: Dict[str, Any] = {}
        self._non_condition_patterns: List[str] = []
        self._criterion_mappings: Dict[str, Dict] = {}
        self._load_config(config_path or PATTERNS_PATH)

    def _load_config(self, config_path: Path) -> None:
        """Load patterns from JSON config."""
        if not config_path.exists():
            logger.warning(f"Condition patterns config not found: {config_path}")
            return

        try:
            with open(config_path) as f:
                data = json.load(f)

            self._patterns = {
                "demographic": data.get("demographic_patterns", {}),
                "clinical": data.get("clinical_patterns", {}),
                "temporal": data.get("temporal_patterns", {}),
                "visit": data.get("visit_patterns", {}),
            }
            self._non_condition_patterns = data.get("non_condition_patterns", [])
            self._criterion_mappings = data.get("criterion_mappings", {})

            logger.info(f"Loaded condition patterns from {config_path}")
        except Exception as e:
            logger.error(f"Error loading condition patterns: {e}")

    def is_likely_non_condition(self, text: str) -> bool:
        """Check if text matches non-condition patterns."""
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in self._non_condition_patterns)

    def get_pattern_match(self, text: str) -> Optional[Tuple[str, str]]:
        """
        Check if text matches any known condition pattern.

        Priority order ensures more specific patterns are checked first:
        1. DEMOGRAPHIC_FERTILITY (most specific - childbearing, WOCBP)
        2. DEMOGRAPHIC_AGE
        3. DEMOGRAPHIC_SEX (least specific - female, male)
        4. Clinical patterns
        5. Temporal patterns
        6. Visit patterns

        Returns: (condition_type, pattern_key) or None
        """
        text_lower = text.lower()

        # Priority order for demographic patterns (most specific first)
        demographic_priority = ["DEMOGRAPHIC_FERTILITY", "DEMOGRAPHIC_AGE", "DEMOGRAPHIC_SEX"]

        # Check demographic patterns in priority order
        demographic_patterns = self._patterns.get("demographic", {})
        for dtype in demographic_priority:
            if dtype in demographic_patterns:
                subpatterns = demographic_patterns[dtype]
                if isinstance(subpatterns, dict):
                    for subkey, patterns in subpatterns.items():
                        if any(p in text_lower for p in patterns):
                            return (dtype, subkey)

        # Check clinical patterns
        for ctype, patterns in self._patterns.get("clinical", {}).items():
            if isinstance(patterns, list):
                if any(p in text_lower for p in patterns):
                    return (ctype, ctype)

        # Check temporal patterns
        for ttype, patterns in self._patterns.get("temporal", {}).items():
            if isinstance(patterns, list):
                if any(p in text_lower for p in patterns):
                    return (ttype, ttype)

        # Check visit patterns
        for vtype, patterns in self._patterns.get("visit", {}).items():
            if isinstance(patterns, list):
                if any(p in text_lower for p in patterns):
                    return (vtype, vtype)

        return None

    def get_criterion(self, condition_type: str, pattern_key: str) -> Optional[Dict]:
        """Get criterion mapping for a condition type and pattern."""
        type_mappings = self._criterion_mappings.get(condition_type, {})
        return type_mappings.get(pattern_key)


class ConditionalExpander:
    """
    Stage 6: Conditional Expansion Handler (LLM-First Strategy).

    Extracts conditions from footnotes and links them to SAIs.
    """

    def __init__(self, config: Optional[ConditionalExpansionConfig] = None):
        """
        Initialize conditional expander.

        Args:
            config: Configuration options
        """
        self.config = config or ConditionalExpansionConfig()
        self._cache: Dict[str, ConditionExtraction] = {}
        self._cache_loaded = False
        self._pattern_registry = ConditionPatternRegistry()

        # LLM clients (lazy loaded)
        self._gemini_client = None
        self._claude_client = None
        self._azure_client = None

        # Load prompt template
        self._prompt_template = self._load_prompt()

        # Ensure cache directory exists
        if self.config.use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._load_cache()

    async def _get_azure_client(self):
        """Lazy load Azure OpenAI client as fallback."""
        if self._azure_client is None:
            try:
                from openai import AzureOpenAI
                api_key = os.getenv("AZURE_OPENAI_API_KEY")
                endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
                api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

                if api_key and endpoint and deployment:
                    self._azure_client = AzureOpenAI(
                        api_key=api_key,
                        api_version=api_version,
                        azure_endpoint=endpoint,
                    )
                    self._azure_deployment = deployment
                    logger.info(f"Initialized Azure OpenAI client: {deployment}")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure OpenAI: {e}")
        return self._azure_client

    async def _get_claude_client(self):
        """Lazy load Anthropic Claude client as fallback."""
        if self._claude_client is None:
            try:
                import anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    self._claude_client = anthropic.Anthropic(api_key=api_key)
                    logger.info("Initialized Anthropic Claude client: claude-sonnet-4-20250514")
            except Exception as e:
                logger.warning(f"Failed to initialize Anthropic Claude: {e}")
        return self._claude_client

    def _load_prompt(self) -> str:
        """Load prompt template from file."""
        if PROMPT_PATH.exists():
            with open(PROMPT_PATH) as f:
                return f.read()
        else:
            logger.warning(f"Prompt file not found: {PROMPT_PATH}")
            return ""

    def _load_cache(self) -> None:
        """Load cache from disk."""
        cache_file = CACHE_DIR / "extractions_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                # Convert dict to ConditionExtraction objects
                for key, value in data.items():
                    self._cache[key] = ConditionExtraction(
                        footnote_marker=value.get("footnote_marker", ""),
                        footnote_text=value.get("footnote_text", ""),
                        has_condition=value.get("has_condition", False),
                        condition_type=value.get("condition_type"),
                        condition_name=value.get("condition_name"),
                        condition_text=value.get("condition_text"),
                        criterion=value.get("criterion"),
                        confidence=value.get("confidence", 0.0),
                        rationale=value.get("rationale"),
                        source="cached",
                    )
                logger.info(f"Loaded {len(self._cache)} cached extractions")
            except Exception as e:
                logger.warning(f"Error loading cache: {e}")
        self._cache_loaded = True

    def _save_cache(self) -> None:
        """Save cache to disk."""
        cache_file = CACHE_DIR / "extractions_cache.json"
        try:
            data = {}
            for key, extraction in self._cache.items():
                data[key] = {
                    "footnote_marker": extraction.footnote_marker,
                    "footnote_text": extraction.footnote_text,
                    "has_condition": extraction.has_condition,
                    "condition_type": extraction.condition_type,
                    "condition_name": extraction.condition_name,
                    "condition_text": extraction.condition_text,
                    "criterion": extraction.criterion,
                    "confidence": extraction.confidence,
                    "rationale": extraction.rationale,
                }
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(data)} extractions to cache")
        except Exception as e:
            logger.warning(f"Error saving cache: {e}")

    def _get_cache_key(self, footnote_text: str) -> str:
        """Generate cache key from footnote text and model version."""
        normalized = footnote_text.lower().strip()
        # Include model name in cache key for invalidation on model upgrade
        key_content = f"{self.config.model_name}:{normalized}"
        return hashlib.md5(key_content.encode()).hexdigest()

    def _check_cache(self, footnote_text: str) -> Optional[ConditionExtraction]:
        """Check if footnote is in cache."""
        key = self._get_cache_key(footnote_text)
        return self._cache.get(key)

    def _update_cache(self, footnote_text: str, extraction: ConditionExtraction) -> None:
        """Update cache with extraction result."""
        key = self._get_cache_key(footnote_text)
        self._cache[key] = extraction

    async def _get_gemini_client(self):
        """Lazy load Gemini client."""
        if self._gemini_client is None:
            try:
                import google.generativeai as genai
                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    self._gemini_client = genai.GenerativeModel(self.config.model_name)
                    logger.info(f"Initialized Gemini client: {self.config.model_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
        return self._gemini_client

    async def expand_conditions(self, usdm_output: Dict[str, Any]) -> Stage6Result:
        """
        Extract conditions from footnotes and link to SAIs.

        Args:
            usdm_output: USDM output with footnotes and SAIs

        Returns:
            Stage6Result with conditions, assignments, and metrics
        """
        result = Stage6Result()

        # 1. Collect footnotes
        footnotes = usdm_output.get("footnotes", [])
        if not footnotes:
            logger.info("No footnotes found in USDM output")
            return result

        result.footnotes_analyzed = len(footnotes)
        logger.info(f"Analyzing {len(footnotes)} footnotes for conditions")

        # 2. Check cache for each footnote
        uncached_footnotes = []
        for fn in footnotes:
            text = fn.get("text", "") or fn.get("content", "")
            if not text:
                continue

            cached = self._check_cache(text)
            if cached:
                result.cache_hits += 1
                # Add to marker mapping if it has a condition
                if cached.has_condition:
                    marker = fn.get("marker", "")
                    result.marker_to_condition[marker] = None  # Will create condition later
            else:
                uncached_footnotes.append(fn)

        logger.info(f"Cache hits: {result.cache_hits}, uncached: {len(uncached_footnotes)}")

        # 3. Analyze uncached footnotes with LLM
        if uncached_footnotes and self.config.use_llm:
            extractions = await self._analyze_footnotes_batch(uncached_footnotes)
            result.llm_calls += 1

            # Update cache with results
            for marker, extraction in extractions.items():
                text = next(
                    (fn.get("text", "") or fn.get("content", "")
                     for fn in uncached_footnotes
                     if fn.get("marker", "") == marker),
                    ""
                )
                if text:
                    self._update_cache(text, extraction)

        # 4. Create Condition objects
        seen_conditions: Dict[str, Condition] = {}  # Deduplicate by type+criterion

        for fn in footnotes:
            marker = fn.get("marker", "")
            text = fn.get("text", "") or fn.get("content", "")
            # Check both camelCase (USDM) and snake_case (legacy) for page number
            provenance = fn.get("provenance", {})
            page = (
                provenance.get("pageNumber") or
                provenance.get("page_number") or
                fn.get("pageNumber") or
                fn.get("page_number")
            )

            if not text:
                continue

            # Get extraction (from cache or LLM results)
            extraction = self._check_cache(text)
            if not extraction:
                continue

            if extraction.has_condition:
                # Create unique key for deduplication
                criterion_str = json.dumps(extraction.criterion) if extraction.criterion else ""
                condition_key = f"{extraction.condition_type}:{criterion_str}"

                # Cross-check LLM result against pattern validation
                pattern_match = self._pattern_registry.get_pattern_match(text)
                validation_flags = []
                if pattern_match and self.config.flag_discrepancies:
                    expected_type = pattern_match[0]
                    if extraction.condition_type != expected_type:
                        validation_flags.append(
                            f"LLM returned {extraction.condition_type}, pattern expected {expected_type}"
                        )

                if condition_key in seen_conditions:
                    # Reuse existing condition
                    condition = seen_conditions[condition_key]
                else:
                    # Create new condition with enhanced provenance
                    condition_type = self._parse_condition_type(extraction.condition_type)
                    footnote_id = fn.get("id") or f"FN-{marker}"
                    is_cache_hit = extraction.source == "cached"

                    condition = Condition(
                        name=extraction.condition_name or "Unnamed Condition",
                        text=extraction.condition_text or text,
                        condition_type=condition_type,
                        criterion=extraction.criterion,
                        source_footnote_marker=marker,
                        source_footnote_text=text,
                        confidence=extraction.confidence,
                        provenance={
                            # Core provenance (include both camelCase and snake_case for compatibility)
                            "pageNumber": page,
                            "page_number": page,
                            "text_snippet": text[:200],
                            "source": "footnote",
                            "footnote_id": footnote_id,
                            "tableId": provenance.get("tableId", "SOA-1"),
                            # Extraction metadata
                            "extraction_stage": "Stage6ConditionalExpansion",
                            "model": self.config.model_name,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            # Cache and validation tracking
                            "cache_hit": is_cache_hit,
                            "confidence_source": extraction.source,
                            "validation_flags": validation_flags if validation_flags else None,
                            # Rationale for audit trail
                            "rationale": extraction.rationale,
                        },
                    )
                    seen_conditions[condition_key] = condition
                    result.conditions.append(condition)
                    result.conditions_created += 1

                    if extraction.confidence >= self.config.confidence_threshold_auto:
                        result.high_confidence += 1
                    else:
                        result.needs_review += 1

                # Map marker to condition ID
                result.marker_to_condition[marker] = condition.id

        # Save cache
        if self.config.use_cache:
            self._save_cache()

        logger.info(
            f"Stage 6 complete: {result.conditions_created} conditions created, "
            f"{result.high_confidence} high confidence, {result.needs_review} need review"
        )

        return result

    def _parse_condition_type(self, type_str: Optional[str]) -> Optional[ConditionType]:
        """Parse condition type string to enum."""
        if not type_str:
            return None

        type_mapping = {
            "DEMOGRAPHIC_SEX": ConditionType.DEMOGRAPHIC_SEX,
            "DEMOGRAPHIC_AGE": ConditionType.DEMOGRAPHIC_AGE,
            "DEMOGRAPHIC_FERTILITY": ConditionType.DEMOGRAPHIC_FERTILITY,
            "CLINICAL_INDICATION": ConditionType.CLINICAL_INDICATION,
            "CLINICAL_RESULT": ConditionType.CLINICAL_RESULT,
            "CLINICAL_EVENT": ConditionType.CLINICAL_EVENT,
            "TEMPORAL_PRIOR": ConditionType.TEMPORAL_PRIOR,
            "TEMPORAL_SEQUENCE": ConditionType.TEMPORAL_SEQUENCE,
            "VISIT_OPTIONAL": ConditionType.VISIT_OPTIONAL,
            "VISIT_TRIGGERED": ConditionType.VISIT_TRIGGERED,
        }
        return type_mapping.get(type_str)

    async def _analyze_footnotes_batch(
        self,
        footnotes: List[Dict[str, Any]]
    ) -> Dict[str, ConditionExtraction]:
        """
        Analyze footnotes in batch using LLM.

        Args:
            footnotes: List of footnote dicts with marker and text

        Returns:
            Dict mapping marker to ConditionExtraction
        """
        # Prepare footnotes for prompt
        footnotes_data = []
        for fn in footnotes:
            marker = fn.get("marker", "")
            text = fn.get("text", "") or fn.get("content", "")
            if marker and text:
                footnotes_data.append({
                    "marker": marker,
                    "text": text,
                })

        if not footnotes_data:
            return {}

        # Build prompt
        prompt = self._prompt_template.replace(
            "{footnotes_json}",
            json.dumps(footnotes_data, indent=2)
        )

        # Call LLM
        response_text = await self._call_llm(prompt)
        if not response_text:
            return {}

        # Parse response
        return self._parse_llm_response(response_text, footnotes)

    async def _call_llm(self, prompt: str) -> Optional[str]:
        """Call LLM with prompt and return response. Uses Gemini → Claude → Azure fallback."""
        last_error = None

        # Try Gemini first with retry logic
        for attempt in range(self.config.max_retries):
            gemini_client = await self._get_gemini_client()
            if gemini_client:
                try:
                    response = await asyncio.to_thread(
                        gemini_client.generate_content,
                        prompt,
                        generation_config={
                            "temperature": 0.1,
                            "max_output_tokens": 8192,
                        }
                    )
                    return response.text
                except Exception as e:
                    last_error = e
                    logger.warning(f"Gemini call failed (attempt {attempt + 1}): {e}")
                    # Wait before retry with exponential backoff
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)

        # Fallback to Claude
        logger.info("Gemini failed - falling back to Anthropic Claude...")
        for attempt in range(self.config.max_retries):
            claude_client = await self._get_claude_client()
            if claude_client:
                try:
                    response = await asyncio.to_thread(
                        claude_client.messages.create,
                        model="claude-sonnet-4-20250514",
                        max_tokens=8192,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    content = response.content[0].text if response.content else None
                    if content:
                        logger.info(f"Anthropic Claude responded ({len(content)} chars)")
                        return content
                except Exception as e:
                    last_error = e
                    logger.warning(f"Claude call failed (attempt {attempt + 1}): {e}")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)

        # Fallback to Azure OpenAI
        logger.info("Claude failed - falling back to Azure OpenAI...")
        for attempt in range(self.config.max_retries):
            azure_client = await self._get_azure_client()
            if azure_client:
                try:
                    response = await asyncio.to_thread(
                        azure_client.chat.completions.create,
                        model=self._azure_deployment,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        max_tokens=8192,
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    last_error = e
                    logger.warning(f"Azure OpenAI call failed (attempt {attempt + 1}): {e}")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    continue

        if last_error:
            logger.error(f"All LLMs failed after retries: {last_error}")
        else:
            logger.warning("No LLM client available")
        return None

    def _parse_llm_response(
        self,
        response_text: str,
        footnotes: List[Dict[str, Any]]
    ) -> Dict[str, ConditionExtraction]:
        """Parse LLM response into ConditionExtraction objects."""
        results: Dict[str, ConditionExtraction] = {}

        # Clean JSON from response
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            data = json.loads(text)
            conditions = data.get("conditions", [])

            for cond in conditions:
                marker = cond.get("footnote_marker", "")
                if not marker:
                    continue

                # Find original footnote text
                fn_text = next(
                    (fn.get("text", "") or fn.get("content", "")
                     for fn in footnotes
                     if fn.get("marker", "") == marker),
                    ""
                )

                extraction = ConditionExtraction(
                    footnote_marker=marker,
                    footnote_text=fn_text,
                    has_condition=cond.get("has_condition", False),
                    condition_type=cond.get("condition_type"),
                    condition_name=cond.get("condition_name"),
                    condition_text=cond.get("condition_text"),
                    criterion=cond.get("criterion"),
                    confidence=cond.get("confidence", 0.0),
                    rationale=cond.get("rationale"),
                    source="llm",
                )
                results[marker] = extraction

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Response text: {text[:500]}...")

        return results

    def apply_conditions_to_usdm(
        self,
        usdm_output: Dict[str, Any],
        result: Stage6Result
    ) -> Dict[str, Any]:
        """
        Apply extracted conditions to USDM output.

        Args:
            usdm_output: Original USDM output
            result: Stage6Result with conditions

        Returns:
            Updated USDM output with conditions and assignments
        """
        # Get or create conditions list
        conditions = usdm_output.get("conditions", [])
        assignments = usdm_output.get("conditionAssignments", [])

        # Add new conditions
        existing_ids = {c.get("id") for c in conditions}
        for condition in result.conditions:
            if condition.id not in existing_ids:
                conditions.append(condition.to_dict())
                existing_ids.add(condition.id)

        # Create assignments for SAIs with footnote conditions
        sais = usdm_output.get("scheduledActivityInstances", [])
        for sai in sais:
            # Check for Stage 7 footnote flags
            has_footnote_condition = sai.get("_hasFootnoteCondition", False)
            footnote_markers = sai.get("footnoteMarkers", [])

            if not footnote_markers:
                continue

            for marker in footnote_markers:
                condition_id = result.marker_to_condition.get(marker)
                if condition_id:
                    # Check if assignment already exists
                    existing = any(
                        a.get("conditionId") == condition_id and
                        a.get("conditionTargetId") == sai.get("id")
                        for a in assignments
                    )

                    if not existing:
                        # Create assignment
                        assignment = ConditionAssignment(
                            condition_id=condition_id,
                            target_id=sai.get("id", ""),
                            provenance={
                                "source": "Stage6ConditionalExpansion",
                                "footnote_marker": marker,
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                            }
                        )
                        assignments.append(assignment.to_dict())
                        result.assignments_created += 1
                        result.assignments.append(assignment)


                        # Set defaultConditionId if not set
                        if not sai.get("defaultConditionId"):
                            sai["defaultConditionId"] = condition_id

                        result.sais_linked += 1

            # Remove Stage 7 flags (now processed)
            if has_footnote_condition:
                sai.pop("_hasFootnoteCondition", None)
                sai.pop("_footnoteMarkersPreserved", None)

        # Update output
        usdm_output["conditions"] = conditions
        usdm_output["conditionAssignments"] = assignments

        logger.info(
            f"Applied {result.conditions_created} conditions, "
            f"created {result.assignments_created} assignments, "
            f"linked {result.sais_linked} SAIs"
        )

        return usdm_output


async def expand_conditions(
    usdm_output: Dict[str, Any],
    config: Optional[ConditionalExpansionConfig] = None
) -> Tuple[Dict[str, Any], Stage6Result]:
    """
    Convenience function to expand conditions and apply to USDM.

    Args:
        usdm_output: USDM output with footnotes and SAIs
        config: Optional configuration

    Returns:
        Tuple of (updated USDM output, Stage6Result)
    """
    expander = ConditionalExpander(config)
    result = await expander.expand_conditions(usdm_output)
    updated = expander.apply_conditions_to_usdm(usdm_output, result)
    return updated, result
