"""
LLM-Based Component Validator

Uses semantic reasoning to validate and deduplicate clinical component names
extracted from Schedule of Assessments (SOA) tables.

Design Principles:
1. Cache First - Check persistent cache before LLM calls
2. Batch Processing - Single LLM call for all uncertain components
3. Confidence-Based Decisions - Auto-accept, review, or reject based on thresholds
4. Full Provenance - Every decision includes rationale for audit

Follows patterns from:
- soa_llm_terminology_mapper.py (batch LLM calling, caching)
- stage1_domain_categorization.py (tiered validation)
- stage5_specimen_enrichment.py (confidence thresholds)

Usage:
    from soa_analyzer.interpretation.component_validator import ComponentValidator

    validator = ComponentValidator()
    result = await validator.validate_components(
        candidates=[{"name": "WBC"}, {"name": "per Table 2"}],
        activity_name="Chemistry/Hematology",
        cdash_domain="LB"
    )
    # result.valid_components = [{"name": "WBC", "canonical_form": "White Blood Cell Count", ...}]
    # result.rejected_components = [{"name": "per Table 2", ...}]
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "component_validation"


@dataclass
class ValidatedComponent:
    """Result of component validation."""
    name: str
    is_valid: bool
    confidence: float
    canonical_form: Optional[str] = None
    rationale: str = ""
    source: str = "llm"  # "cache", "llm"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "is_valid": self.is_valid,
            "confidence": self.confidence,
            "canonical_form": self.canonical_form,
            "rationale": self.rationale,
            "source": self.source,
        }


@dataclass
class DeduplicationGroup:
    """Group of semantically equivalent components."""
    canonical: str
    duplicates: List[str]
    confidence: float
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical": self.canonical,
            "duplicates": self.duplicates,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


@dataclass
class ComponentValidationResult:
    """Complete result of component validation."""
    valid_components: List[ValidatedComponent] = field(default_factory=list)
    rejected_components: List[ValidatedComponent] = field(default_factory=list)
    review_items: List[ValidatedComponent] = field(default_factory=list)
    deduplication_groups: List[DeduplicationGroup] = field(default_factory=list)
    llm_calls: int = 0
    cache_hits: int = 0
    total_candidates: int = 0

    def get_valid_names(self) -> Set[str]:
        """Get set of valid canonical component names."""
        names = set()
        for comp in self.valid_components:
            if comp.canonical_form:
                names.add(comp.canonical_form.lower())
            names.add(comp.name.lower())
        return names

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid_components": [c.to_dict() for c in self.valid_components],
            "rejected_components": [c.to_dict() for c in self.rejected_components],
            "review_items": [c.to_dict() for c in self.review_items],
            "deduplication_groups": [g.to_dict() for g in self.deduplication_groups],
            "metrics": {
                "llm_calls": self.llm_calls,
                "cache_hits": self.cache_hits,
                "total_candidates": self.total_candidates,
                "valid_count": len(self.valid_components),
                "rejected_count": len(self.rejected_components),
                "review_count": len(self.review_items),
            }
        }


class ComponentValidator:
    """
    Validates component names using LLM semantic reasoning.

    Three-tier architecture:
    1. Cache lookup (instant, free)
    2. LLM batch validation (semantic understanding)
    3. Confidence-based decision (auto-accept, review, reject)
    """

    # Confidence thresholds (following stage5_specimen_enrichment.py pattern)
    CONFIDENCE_AUTO_ACCEPT = 0.90
    CONFIDENCE_REVIEW = 0.70

    def __init__(
        self,
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
        model: str = "gemini-3-pro-preview",
    ):
        """
        Initialize component validator.

        Args:
            use_cache: Whether to use persistent caching
            cache_dir: Directory for cache files
            model: LLM model to use for validation
        """
        self.use_cache = use_cache
        self.cache_dir = cache_dir or CACHE_DIR
        self.model = model

        # In-memory cache
        self._cache: Dict[str, ValidatedComponent] = {}
        self._cache_loaded = False

        # LLM clients (lazy loaded)
        self._llm_client = None
        self._azure_client = None
        self._azure_deployment = None

        # Prompt template (lazy loaded)
        self._prompt_template: Optional[str] = None

        # Ensure cache directory exists
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_cache(self) -> None:
        """Load cache from disk."""
        if self._cache_loaded:
            return

        cache_file = self.cache_dir / "component_validation_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    for key, comp_data in data.items():
                        self._cache[key] = ValidatedComponent(**comp_data)
                logger.info(f"Loaded {len(self._cache)} cached component validations")
            except Exception as e:
                logger.warning(f"Failed to load component validation cache: {e}")

        self._cache_loaded = True

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if not self.use_cache:
            return

        cache_file = self.cache_dir / "component_validation_cache.json"
        try:
            data = {key: comp.to_dict() for key, comp in self._cache.items()}
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self._cache)} component validations to cache")
        except Exception as e:
            logger.warning(f"Failed to save component validation cache: {e}")

    def _load_prompt_template(self) -> str:
        """Load prompt template from file."""
        if self._prompt_template is not None:
            return self._prompt_template

        prompt_file = Path(__file__).parent.parent / "prompts" / "component_validation.txt"
        if prompt_file.exists():
            self._prompt_template = prompt_file.read_text(encoding='utf-8')
        else:
            logger.warning(f"Prompt file not found: {prompt_file}")
            self._prompt_template = self._get_fallback_prompt()

        return self._prompt_template

    def _get_fallback_prompt(self) -> str:
        """Fallback prompt if file not found."""
        return """Validate these clinical component names for activity "{activity_name}" (domain: {cdash_domain}).

Components to validate:
{component_list}

For each component, return JSON with:
- name: Original name
- is_valid: true if valid clinical component, false if garbage
- confidence: 0.0-1.0
- canonical_form: Standardized name (null if invalid)
- rationale: Brief explanation

Return JSON format:
{{"validated_components": [...], "deduplication_groups": []}}"""

    def _get_llm_client(self):
        """Lazy load Gemini client."""
        if self._llm_client is None:
            try:
                import google.generativeai as genai
                from google.generativeai.types import HarmCategory, HarmBlockThreshold

                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)

                    # Disable safety filters for clinical terminology
                    safety_settings = {
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }

                    self._llm_client = genai.GenerativeModel(
                        self.model,
                        safety_settings=safety_settings
                    )
                    logger.info(f"Initialized Gemini client: {self.model}")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
        return self._llm_client

    def _get_azure_client(self):
        """Lazy load Azure OpenAI client (fallback)."""
        if self._azure_client is None:
            try:
                from openai import AzureOpenAI

                api_key = os.getenv("AZURE_OPENAI_API_KEY")
                endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
                api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview")

                if api_key and endpoint:
                    self._azure_client = AzureOpenAI(
                        api_key=api_key,
                        api_version=api_version,
                        azure_endpoint=endpoint,
                        timeout=120.0
                    )
                    self._azure_deployment = deployment
                    logger.info(f"Initialized Azure OpenAI fallback: {deployment}")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure OpenAI client: {e}")
        return self._azure_client

    def _normalize_name(self, name: str) -> str:
        """Normalize component name for cache lookup."""
        return name.lower().strip()

    def _check_cache(
        self,
        candidates: List[Dict],
    ) -> Tuple[List[ValidatedComponent], List[Dict]]:
        """
        Check cache for known validations.

        Returns:
            Tuple of (cached results, uncached candidates)
        """
        if not self.use_cache:
            return [], candidates

        self._load_cache()

        cached = []
        uncached = []

        for candidate in candidates:
            name = candidate.get("name", "")
            key = self._normalize_name(name)

            if key in self._cache:
                cached_comp = self._cache[key]
                # Update source to indicate cache hit
                cached.append(ValidatedComponent(
                    name=name,
                    is_valid=cached_comp.is_valid,
                    confidence=cached_comp.confidence,
                    canonical_form=cached_comp.canonical_form,
                    rationale=cached_comp.rationale,
                    source="cache",
                ))
            else:
                uncached.append(candidate)

        return cached, uncached

    def _update_cache(
        self,
        valid: List[ValidatedComponent],
        rejected: List[ValidatedComponent],
    ) -> None:
        """Update cache with new validation decisions."""
        if not self.use_cache:
            return

        for comp in valid:
            key = self._normalize_name(comp.canonical_form or comp.name)
            self._cache[key] = comp
            # Also cache the original name if different
            orig_key = self._normalize_name(comp.name)
            if orig_key != key:
                self._cache[orig_key] = comp

        for comp in rejected:
            key = self._normalize_name(comp.name)
            self._cache[key] = comp

        self._save_cache()

    def _format_component_list(self, candidates: List[Dict]) -> str:
        """Format candidates for prompt."""
        lines = []
        for i, candidate in enumerate(candidates, 1):
            name = candidate.get("name", "")
            snippet = candidate.get("source_snippet", "")[:100] if candidate.get("source_snippet") else ""
            if snippet:
                lines.append(f"{i}. \"{name}\" (from: \"{snippet}...\")")
            else:
                lines.append(f"{i}. \"{name}\"")
        return "\n".join(lines)

    def _format_existing_components(self, existing: Optional[List[str]]) -> str:
        """Format existing component names for prompt."""
        if not existing:
            return "None (no existing components)"
        # Deduplicate and sort for consistent prompts
        unique = sorted(set(name.strip() for name in existing if name and name.strip()))
        if not unique:
            return "None (no existing components)"
        return "\n".join(f"- {name}" for name in unique)

    async def _validate_with_llm(
        self,
        candidates: List[Dict],
        activity_name: str,
        cdash_domain: str,
        existing_components: Optional[List[str]] = None,
    ) -> Dict:
        """
        Single batch LLM call for all uncertain components.

        Uses Gemini with Azure OpenAI fallback.

        Args:
            candidates: List of candidate components to validate
            activity_name: Parent activity name for context
            cdash_domain: CDISC domain (LB, VS, PE, etc.)
            existing_components: List of component names already in the activity
                                 (for semantic deduplication)
        """
        if not candidates:
            return {"validated_components": [], "deduplication_groups": []}

        # Build prompt with existing components for semantic deduplication
        prompt_template = self._load_prompt_template()
        prompt = prompt_template.format(
            activity_name=activity_name,
            cdash_domain=cdash_domain,
            component_list=self._format_component_list(candidates),
            existing_components=self._format_existing_components(existing_components),
        )

        # Try Gemini first
        result = await self._call_gemini(prompt)
        if result:
            return result

        # Fall back to Azure OpenAI
        logger.info("Gemini failed - falling back to Azure OpenAI...")
        result = await self._call_azure(prompt)
        if result:
            return result

        # Both failed - return conservative result
        logger.error("Both Gemini and Azure OpenAI failed for component validation")
        return self._conservative_fallback(candidates)

    async def _call_gemini(self, prompt: str) -> Optional[Dict]:
        """Try validation with Gemini."""
        client = self._get_llm_client()
        if not client:
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
                    "temperature": 0.1,  # Low temperature for consistency
                    "max_output_tokens": 8192,
                    "response_mime_type": "application/json",
                },
                safety_settings=safety_settings,
            )

            if response and response.text:
                return self._parse_response(response.text)

        except Exception as e:
            logger.warning(f"Gemini validation failed: {e}")

        return None

    async def _call_azure(self, prompt: str) -> Optional[Dict]:
        """Try validation with Azure OpenAI."""
        client = self._get_azure_client()
        if not client or not self._azure_deployment:
            return None

        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=self._azure_deployment,
                messages=[
                    {"role": "system", "content": "You are a clinical terminology expert validating component names from Schedule of Assessments. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=8192,
                response_format={"type": "json_object"},
            )

            if response and response.choices:
                content = response.choices[0].message.content
                if content:
                    return self._parse_response(content)

        except Exception as e:
            logger.warning(f"Azure OpenAI validation failed: {e}")

        return None

    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Parse LLM response into structured result."""
        try:
            # Handle markdown code blocks
            text = response_text.strip()
            if text.startswith("```"):
                # Remove markdown wrapping
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines)

            return json.loads(text)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response text: {response_text[:500]}")
            return None

    def _conservative_fallback(self, candidates: List[Dict]) -> Dict:
        """
        Conservative fallback when LLM fails.

        Marks all items for review rather than auto-accepting/rejecting.
        """
        return {
            "validated_components": [
                {
                    "name": c.get("name", ""),
                    "is_valid": True,  # Conservative: don't reject
                    "confidence": 0.75,  # In review range
                    "canonical_form": c.get("name", ""),
                    "rationale": "LLM validation unavailable - requires manual review",
                }
                for c in candidates
            ],
            "deduplication_groups": [],
        }

    def _apply_thresholds(
        self,
        llm_result: Dict,
    ) -> Tuple[List[ValidatedComponent], List[ValidatedComponent], List[ValidatedComponent]]:
        """
        Apply confidence thresholds to LLM validation results.

        Returns:
            Tuple of (valid, rejected, review) lists
        """
        valid = []
        rejected = []
        review = []

        for comp_data in llm_result.get("validated_components", []):
            confidence = comp_data.get("confidence", 0.0)
            is_valid = comp_data.get("is_valid", False)

            validated = ValidatedComponent(
                name=comp_data.get("name", ""),
                is_valid=is_valid,
                confidence=confidence,
                canonical_form=comp_data.get("canonical_form"),
                rationale=comp_data.get("rationale", ""),
                source="llm",
            )

            if not is_valid:
                # LLM says invalid - reject
                rejected.append(validated)
            elif confidence >= self.CONFIDENCE_AUTO_ACCEPT:
                # High confidence valid - auto-accept
                valid.append(validated)
            elif confidence >= self.CONFIDENCE_REVIEW:
                # Medium confidence - needs review
                review.append(validated)
            else:
                # Low confidence - reject
                rejected.append(validated)

        return valid, rejected, review

    def _build_deduplication_groups(
        self,
        llm_result: Dict,
    ) -> List[DeduplicationGroup]:
        """Extract deduplication groups from LLM result."""
        groups = []
        for group_data in llm_result.get("deduplication_groups", []):
            groups.append(DeduplicationGroup(
                canonical=group_data.get("canonical", ""),
                duplicates=group_data.get("duplicates", []),
                confidence=group_data.get("confidence", 0.9),
                rationale=group_data.get("rationale", ""),
            ))
        return groups

    async def validate_components(
        self,
        candidates: List[Dict],
        activity_name: str,
        cdash_domain: str,
        existing_components: Optional[List[str]] = None,
    ) -> ComponentValidationResult:
        """
        Validate and deduplicate components using LLM reasoning.

        Args:
            candidates: List of candidate components with 'name' field
            activity_name: Parent activity name for context
            cdash_domain: CDISC domain (LB, VS, PE, etc.)
            existing_components: List of component names already in the activity
                                 (for semantic deduplication against existing)

        Returns:
            ComponentValidationResult with valid, rejected, and review items
        """
        if not candidates:
            return ComponentValidationResult()

        result = ComponentValidationResult(total_candidates=len(candidates))

        # Tier 1: Check cache for known validations
        cached, uncached = self._check_cache(candidates)
        result.cache_hits = len(cached)

        # Distribute cached results
        for comp in cached:
            if not comp.is_valid:
                result.rejected_components.append(comp)
            elif comp.confidence >= self.CONFIDENCE_AUTO_ACCEPT:
                result.valid_components.append(comp)
            elif comp.confidence >= self.CONFIDENCE_REVIEW:
                result.review_items.append(comp)
            else:
                result.rejected_components.append(comp)

        if not uncached:
            logger.info(f"All {len(candidates)} candidates found in cache")
            return result

        # Tier 2: Batch LLM validation for uncached
        logger.info(
            f"Validating {len(uncached)} uncached components for '{activity_name}' "
            f"(domain: {cdash_domain}), checking against {len(existing_components or [])} existing"
        )
        llm_result = await self._validate_with_llm(
            uncached, activity_name, cdash_domain, existing_components
        )
        result.llm_calls = 1

        # Tier 3: Apply confidence thresholds
        valid, rejected, review = self._apply_thresholds(llm_result)
        result.valid_components.extend(valid)
        result.rejected_components.extend(rejected)
        result.review_items.extend(review)

        # Extract deduplication groups
        result.deduplication_groups = self._build_deduplication_groups(llm_result)

        # Update cache with new decisions
        self._update_cache(valid, rejected)

        logger.info(
            f"Component validation complete: {len(result.valid_components)} valid, "
            f"{len(result.rejected_components)} rejected, {len(result.review_items)} for review"
        )

        return result


# Convenience function for simple usage
async def validate_component_names(
    names: List[str],
    activity_name: str,
    cdash_domain: str,
) -> ComponentValidationResult:
    """
    Convenience function to validate a list of component names.

    Args:
        names: List of component names to validate
        activity_name: Parent activity name
        cdash_domain: CDISC domain

    Returns:
        ComponentValidationResult
    """
    candidates = [{"name": name} for name in names]
    validator = ComponentValidator()
    return await validator.validate_components(candidates, activity_name, cdash_domain)
