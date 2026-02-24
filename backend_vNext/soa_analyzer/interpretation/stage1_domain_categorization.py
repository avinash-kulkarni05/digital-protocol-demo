"""
Stage 1: Activity Domain Categorization (CRITICAL)

Maps ALL activities to CDISC domains using LLM-first architecture.
Addresses the critical gap where 45/45 activities have category: "UNKNOWN".

Design Principles:
1. LLM-First - Use semantic reasoning over brittle regex patterns
2. Batch Processing - Single LLM call for all activities (efficiency)
3. Confidence-Based - High confidence auto-apply, low confidence flag for review
4. Caching - Cache results by (activity_name, model_version)

Target: 0% → 100% category coverage

Usage:
    from soa_analyzer.interpretation.stage1_domain_categorization import DomainCategorizer

    categorizer = DomainCategorizer()
    result = await categorizer.categorize_activities(activities)
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .cdisc_code_enricher import CDISCCodeEnricher

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "domain_categorization"

# Prompt file path
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "domain_categorization.txt"


@dataclass
class DomainMapping:
    """Result of domain categorization for a single activity."""
    activity_id: str
    activity_name: str
    category: str  # Human-readable (e.g., "LABORATORY")
    cdash_domain: str  # 2-letter code (e.g., "LB")
    cdisc_code: Optional[str] = None  # NCI code (e.g., "C78713")
    cdisc_decode: Optional[str] = None  # CDISC preferred term
    confidence: float = 0.0
    rationale: Optional[str] = None
    source: str = "llm"  # "llm", "cached", "default"
    # CDISC Biomedical Concept fields
    specimen: Optional[str] = None  # Specimen type if applicable
    method: Optional[str] = None  # Method/route if applicable

    def is_high_confidence(self) -> bool:
        """Check if mapping is high confidence (auto-apply)."""
        return self.confidence >= 0.90

    def needs_review(self) -> bool:
        """Check if mapping needs human review."""
        return 0.70 <= self.confidence < 0.90

    def is_uncertain(self) -> bool:
        """Check if mapping is too uncertain."""
        return self.confidence < 0.70

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        result = {
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "category": self.category,
            "cdashDomain": self.cdash_domain,
            "cdiscCode": self.cdisc_code,
            "cdiscDecode": self.cdisc_decode,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "source": self.source,
        }
        if self.specimen:
            result["specimen"] = self.specimen
        if self.method:
            result["method"] = self.method
        return result

    def to_biomedical_concept(self) -> Optional[Dict[str, Any]]:
        """Convert to CDISC Biomedical Concept object."""
        if not self.cdisc_decode or not self.cdash_domain:
            return None

        bc = {
            "conceptName": self.cdisc_decode or self.activity_name,
            "cdiscCode": self.cdisc_code or "CUSTOM",
            "domain": self.cdash_domain,
            "confidence": self.confidence,
        }
        if self.specimen:
            bc["specimen"] = self.specimen
        if self.method:
            bc["method"] = self.method
        if self.rationale:
            bc["rationale"] = f"Stage 1 auto-mapped: {self.rationale}"
        return bc


@dataclass
class CategorizationResult:
    """Result of batch domain categorization."""
    mappings: Dict[str, DomainMapping] = field(default_factory=dict)
    total_activities: int = 0
    high_confidence: int = 0
    needs_review: int = 0
    uncertain: int = 0
    cache_hits: int = 0
    llm_calls: int = 0

    def get_mapping(self, activity_id: str) -> Optional[DomainMapping]:
        """Get mapping for an activity by ID."""
        return self.mappings.get(activity_id)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        return {
            "total_activities": self.total_activities,
            "high_confidence": self.high_confidence,
            "needs_review": self.needs_review,
            "uncertain": self.uncertain,
            "cache_hits": self.cache_hits,
            "llm_calls": self.llm_calls,
            "coverage_rate": len(self.mappings) / max(self.total_activities, 1),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary for stage output."""
        return {
            "stage": 1,
            "stageName": "Domain Categorization",
            "success": True,
            "mappings": [m.to_dict() for m in self.mappings.values()],
            "metrics": {
                "totalActivities": self.total_activities,
                "highConfidence": self.high_confidence,
                "needsReview": self.needs_review,
                "uncertain": self.uncertain,
                "cacheHits": self.cache_hits,
                "llmCalls": self.llm_calls,
                "coverageRate": len(self.mappings) / max(self.total_activities, 1),
            },
            "reviewItems": [],
        }


# Valid CDASH domains
VALID_DOMAINS = {
    "LB": "Laboratory",
    "VS": "Vital Signs",
    "EG": "ECG",
    "PE": "Physical Examination",
    "QS": "Questionnaire",
    "MI": "Medical Imaging",
    "CM": "Concomitant Medications",
    "AE": "Adverse Events",
    "EX": "Exposure",
    "BS": "Biospecimen",
    "DM": "Demographics",
    "MH": "Medical History",
    "DS": "Disposition",
    "PR": "Procedures",
    "TU": "Tumor/Oncology",
    "PC": "Pharmacokinetics",
}


class DomainCategorizer:
    """
    LLM-based activity domain categorizer.

    Uses Gemini/Claude to semantically map activities to CDISC domains.
    """

    def __init__(
        self,
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
        model: str = "gemini-3-pro-preview",
        use_cdisc_enrichment: bool = True,
    ):
        """
        Initialize domain categorizer.

        Args:
            use_cache: Whether to use persistent caching
            cache_dir: Directory for cache files
            model: LLM model to use
            use_cdisc_enrichment: Whether to enrich with CDISC codes
        """
        self.use_cache = use_cache
        self.cache_dir = cache_dir or CACHE_DIR
        self.model = model
        self.use_cdisc_enrichment = use_cdisc_enrichment

        # In-memory cache
        self._cache: Dict[str, DomainMapping] = {}
        self._cache_loaded = False

        # LLM clients (lazy loaded)
        self._gemini_client = None
        self._claude_client = None
        self._azure_client = None

        # CDISC code enricher (lazy loaded)
        self._cdisc_enricher: Optional[CDISCCodeEnricher] = None

        # Ensure cache directory exists
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_cache(self) -> None:
        """Load cache from disk."""
        if self._cache_loaded:
            return

        cache_file = self.cache_dir / "domain_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    for key, mapping_data in data.items():
                        self._cache[key] = DomainMapping(**mapping_data)
                logger.info(f"Loaded {len(self._cache)} cached domain mappings")
            except Exception as e:
                logger.warning(f"Failed to load domain cache: {e}")

        self._cache_loaded = True

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if not self.use_cache:
            return

        cache_file = self.cache_dir / "domain_cache.json"
        try:
            data = {}
            for key, mapping in self._cache.items():
                data[key] = {
                    "activity_id": mapping.activity_id,
                    "activity_name": mapping.activity_name,
                    "category": mapping.category,
                    "cdash_domain": mapping.cdash_domain,
                    "cdisc_code": mapping.cdisc_code,
                    "cdisc_decode": mapping.cdisc_decode,
                    "confidence": mapping.confidence,
                    "rationale": mapping.rationale,
                    "source": mapping.source,
                    "specimen": mapping.specimen,
                    "method": mapping.method,
                }
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save domain cache: {e}")

    def _normalize_name(self, name: str) -> str:
        """Normalize activity name for cache lookup."""
        return name.lower().strip()

    def _get_cache_key(self, activity_name: str) -> str:
        """Generate cache key from activity name."""
        return hashlib.md5(self._normalize_name(activity_name).encode()).hexdigest()

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
                        self.model,
                        safety_settings=safety_settings,
                    )
                    logger.info(f"Initialized Gemini client: {self.model}")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
        return self._gemini_client

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

    def _get_azure_client(self):
        """Lazy load Azure OpenAI client (fallback)."""
        if self._azure_client is None:
            try:
                from openai import AzureOpenAI

                api_key = os.getenv("AZURE_OPENAI_API_KEY")
                endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")
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

    def _get_cdisc_enricher(self) -> CDISCCodeEnricher:
        """Lazy load CDISC code enricher."""
        if self._cdisc_enricher is None:
            self._cdisc_enricher = CDISCCodeEnricher(use_llm_fallback=True)
            logger.info("Initialized CDISC code enricher")
        return self._cdisc_enricher

    def _build_prompt(self, activities: List[Dict[str, Any]]) -> str:
        """Build LLM prompt for domain categorization."""
        # Load prompt template
        if PROMPT_PATH.exists():
            with open(PROMPT_PATH) as f:
                template = f.read()
        else:
            raise FileNotFoundError(f"Prompt template not found: {PROMPT_PATH}")

        # Format activities for prompt
        activities_json = json.dumps(
            [
                {"activityId": a.get("id", f"ACT-{i}"), "activityName": a.get("name", "")}
                for i, a in enumerate(activities)
            ],
            indent=2,
        )

        return template.format(
            activities_json=activities_json,
            activity_count=len(activities),
        )

    async def _categorize_with_gemini(
        self,
        prompt: str,
        activities: List[Dict[str, Any]],
    ) -> Optional[Dict[str, DomainMapping]]:
        """Try categorization with Gemini."""
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
                    "temperature": 0.1,
                    "max_output_tokens": 8192,
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

            return self._parse_response(response.text, activities)

        except Exception as e:
            logger.warning(f"Gemini domain categorization failed: {e}")
            return None

    async def _categorize_with_claude(
        self,
        prompt: str,
        activities: List[Dict[str, Any]],
    ) -> Optional[Dict[str, DomainMapping]]:
        """Try categorization with Anthropic Claude (fallback)."""
        client = self._get_claude_client()
        if not client:
            logger.warning("Anthropic Claude client not available")
            return None

        try:
            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text if response.content else None
            if not content:
                logger.warning("Anthropic Claude returned empty response")
                return None

            logger.info(f"Anthropic Claude responded ({len(content)} chars)")
            return self._parse_response(content, activities)

        except Exception as e:
            logger.warning(f"Anthropic Claude domain categorization failed: {e}")
            return None

    async def _categorize_with_azure(
        self,
        prompt: str,
        activities: List[Dict[str, Any]],
    ) -> Optional[Dict[str, DomainMapping]]:
        """Try categorization with Azure OpenAI (fallback)."""
        client = self._get_azure_client()
        if not client:
            logger.warning("Azure OpenAI client not available")
            return None

        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=self._azure_deployment,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=8192,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning("Azure OpenAI returned empty response")
                return None

            logger.info(f"Azure OpenAI responded ({len(content)} chars)")
            return self._parse_response(content, activities)

        except Exception as e:
            logger.error(f"Azure OpenAI domain categorization failed: {e}")
            return None

    def _parse_response(
        self,
        response_text: str,
        activities: List[Dict[str, Any]],
    ) -> Dict[str, DomainMapping]:
        """Parse LLM response into DomainMapping objects."""
        results = {}

        try:
            # Clean response
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            data = json.loads(text)

            # Build activity lookup
            activity_lookup = {a.get("id", f"ACT-{i}"): a for i, a in enumerate(activities)}
            activity_by_name = {a.get("name", "").lower(): a.get("id", f"ACT-{i}") for i, a in enumerate(activities)}

            for item in data:
                activity_id = item.get("activityId")
                activity_name = item.get("activityName", "")

                # Try to find activity by ID or name
                if activity_id not in activity_lookup:
                    # Try by name
                    activity_id = activity_by_name.get(activity_name.lower())

                if not activity_id:
                    continue

                # Validate domain
                cdash_domain = item.get("cdashDomain", "").upper()
                if cdash_domain not in VALID_DOMAINS:
                    logger.warning(f"Invalid domain '{cdash_domain}' for activity '{activity_name}'")
                    cdash_domain = "PR"  # Default to Procedures if invalid

                # Map category to standardized format
                category = item.get("category", "").upper()
                if not category:
                    category = VALID_DOMAINS.get(cdash_domain, "UNKNOWN")

                results[activity_id] = DomainMapping(
                    activity_id=activity_id,
                    activity_name=activity_name,
                    category=category,
                    cdash_domain=cdash_domain,
                    cdisc_code=item.get("cdiscCode"),
                    cdisc_decode=item.get("cdiscDecode"),
                    confidence=float(item.get("confidence", 0.8)),
                    rationale=item.get("rationale"),
                    source="llm",
                )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")

        return results

    async def categorize_activities(
        self,
        activities: List[Dict[str, Any]],
    ) -> CategorizationResult:
        """
        Categorize activities using LLM-first approach.

        Args:
            activities: List of activity dictionaries with 'id' and 'name' fields

        Returns:
            CategorizationResult with all mappings
        """
        self._load_cache()

        result = CategorizationResult(total_activities=len(activities))
        uncached_activities: List[Dict[str, Any]] = []

        # 1. Check cache for each activity
        for activity in activities:
            activity_id = activity.get("id", "")
            activity_name = activity.get("name", "")
            cache_key = self._get_cache_key(activity_name)

            if cache_key in self._cache:
                cached = self._cache[cache_key]
                # Update with current activity ID
                mapping = DomainMapping(
                    activity_id=activity_id,
                    activity_name=activity_name,
                    category=cached.category,
                    cdash_domain=cached.cdash_domain,
                    cdisc_code=cached.cdisc_code,
                    cdisc_decode=cached.cdisc_decode,
                    confidence=cached.confidence,
                    rationale=cached.rationale,
                    source="cached",
                )
                result.mappings[activity_id] = mapping
                result.cache_hits += 1
            else:
                uncached_activities.append(activity)

        # 2. LLM categorization for uncached activities
        if uncached_activities:
            logger.info(f"LLM domain categorization for {len(uncached_activities)} activities...")

            prompt = self._build_prompt(uncached_activities)

            # Try Gemini first
            llm_results = await self._categorize_with_gemini(prompt, uncached_activities)

            # Fall back to Claude if Gemini fails
            if not llm_results:
                logger.info("Gemini failed - falling back to Anthropic Claude...")
                llm_results = await self._categorize_with_claude(prompt, uncached_activities)

            # Fall back to Azure OpenAI if Claude also fails
            if not llm_results:
                logger.info("Claude failed - falling back to Azure OpenAI...")
                llm_results = await self._categorize_with_azure(prompt, uncached_activities)

            result.llm_calls = 1

            if llm_results:
                for activity in uncached_activities:
                    activity_id = activity.get("id", "")
                    activity_name = activity.get("name", "")

                    if activity_id in llm_results:
                        mapping = llm_results[activity_id]
                        result.mappings[activity_id] = mapping

                        # Cache by name for future lookups
                        cache_key = self._get_cache_key(activity_name)
                        self._cache[cache_key] = mapping
                    else:
                        # Default mapping if LLM didn't return this activity
                        result.mappings[activity_id] = DomainMapping(
                            activity_id=activity_id,
                            activity_name=activity_name,
                            category="UNKNOWN",
                            cdash_domain="PR",
                            confidence=0.5,
                            rationale="LLM did not provide mapping",
                            source="default",
                        )

                # Save updated cache
                self._save_cache()
            else:
                # All LLMs failed - use defaults
                logger.error("All LLMs (Gemini, Claude, Azure) failed for domain categorization")
                for activity in uncached_activities:
                    activity_id = activity.get("id", "")
                    result.mappings[activity_id] = DomainMapping(
                        activity_id=activity_id,
                        activity_name=activity.get("name", ""),
                        category="UNKNOWN",
                        cdash_domain="PR",
                        confidence=0.3,
                        rationale="LLM categorization failed",
                        source="default",
                    )

        # 3. Calculate statistics
        for mapping in result.mappings.values():
            if mapping.is_high_confidence():
                result.high_confidence += 1
            elif mapping.needs_review():
                result.needs_review += 1
            else:
                result.uncertain += 1

        # 4. CDISC code enrichment
        if self.use_cdisc_enrichment:
            logger.info("Running CDISC code enrichment...")
            enricher = self._get_cdisc_enricher()

            # Convert mappings to dicts for enricher
            mapping_dicts = [m.to_dict() for m in result.mappings.values()]

            # Enrich with CDISC codes
            enriched_dicts = enricher.enrich_batch(mapping_dicts)

            # Update mappings with enriched codes
            for enriched in enriched_dicts:
                activity_id = enriched.get("activityId")
                if activity_id and activity_id in result.mappings:
                    mapping = result.mappings[activity_id]
                    # Update CDISC code fields
                    if enriched.get("cdiscCode") and not mapping.cdisc_code:
                        mapping.cdisc_code = enriched.get("cdiscCode")
                        mapping.cdisc_decode = enriched.get("cdiscDecode")

                        # Update cache with enriched data
                        cache_key = self._get_cache_key(mapping.activity_name)
                        self._cache[cache_key] = mapping

            # Save updated cache
            self._save_cache()

            # Log enrichment stats
            with_code = sum(1 for m in result.mappings.values() if m.cdisc_code)
            logger.info(f"CDISC code enrichment: {with_code}/{len(result.mappings)} activities have codes")

        logger.info(
            f"Domain categorization complete: {result.total_activities} activities, "
            f"{result.high_confidence} high-confidence, {result.needs_review} needs review, "
            f"{result.uncertain} uncertain, {result.cache_hits} cached"
        )

        return result

    def apply_to_usdm(
        self,
        usdm_output: Dict[str, Any],
        categorization_result: CategorizationResult,
    ) -> Dict[str, Any]:
        """
        Apply domain categorization results to USDM output.

        Updates activities with category and cdashDomain fields.
        Respects existing values (biomedicalConceptId, activityType) if already set.

        Args:
            usdm_output: USDM output dictionary with 'activities' list
            categorization_result: Result from categorize_activities()

        Returns:
            Updated USDM output with populated domain fields
        """
        # Handle nested USDM structure (studyVersion[0].activities)
        if "studyVersion" in usdm_output:
            study_version = usdm_output.get("studyVersion", [])
            if isinstance(study_version, list) and study_version:
                activities = study_version[0].get("activities", [])
            else:
                activities = []
        else:
            activities = usdm_output.get("activities", [])

        for activity in activities:
            activity_id = activity.get("id", "")
            mapping = categorization_result.get_mapping(activity_id)

            if mapping:
                # Set category - always update from LLM result
                activity["category"] = mapping.category

                # Set cdashDomain - prefer existing biomedicalConceptId if valid
                existing_domain = activity.get("biomedicalConceptId", "")
                if existing_domain and existing_domain in VALID_DOMAINS:
                    activity["cdashDomain"] = existing_domain
                else:
                    activity["cdashDomain"] = mapping.cdash_domain

                # Add CDISC mapping only if not already present
                if not activity.get("cdiscMapping"):
                    if mapping.cdisc_code and mapping.cdisc_decode:
                        activity["cdiscMapping"] = {
                            "code": mapping.cdisc_code,
                            "decode": mapping.cdisc_decode,
                        }

                # Add CDISC Biomedical Concept object (USDM 4.0 compliant)
                if not activity.get("biomedicalConcept"):
                    bc = mapping.to_biomedical_concept()
                    if bc:
                        activity["biomedicalConcept"] = bc

                # Store categorization metadata separately (non-USDM extension)
                if mapping.confidence or mapping.rationale:
                    activity["_categorizationMetadata"] = {
                        "confidence": mapping.confidence,
                        "rationale": mapping.rationale,
                        "source": mapping.source,
                    }

        return usdm_output


# Convenience function for single-shot categorization
async def categorize_soa_activities(
    usdm_output: Dict[str, Any],
    use_cache: bool = True,
) -> Tuple[Dict[str, Any], CategorizationResult]:
    """
    Convenience function to categorize activities in USDM output.

    Args:
        usdm_output: USDM output with activities list
        use_cache: Whether to use caching

    Returns:
        Tuple of (updated USDM output, categorization result)
    """
    categorizer = DomainCategorizer(use_cache=use_cache)

    # Handle nested USDM structure (studyVersion[0].activities)
    if "studyVersion" in usdm_output:
        study_version = usdm_output.get("studyVersion", [])
        if isinstance(study_version, list) and study_version:
            activities = study_version[0].get("activities", [])
        else:
            activities = []
    else:
        activities = usdm_output.get("activities", [])

    result = await categorizer.categorize_activities(activities)

    updated_output = categorizer.apply_to_usdm(usdm_output, result)

    return updated_output, result
