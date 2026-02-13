"""
LLM-Based Terminology Mapper

Provides semantic terminology mapping using LLM reasoning as a fallback
when deterministic matching fails.

Design Principles:
1. Deterministic First - Try exact/fuzzy matches before LLM
2. Batch Processing - Single LLM call for all unmapped terms
3. Persistent Caching - Avoid repeated LLM calls across runs
4. Structured Output - Reliable JSON parsing with validation

Usage:
    from soa_analyzer.soa_llm_terminology_mapper import LLMTerminologyMapper

    mapper = LLMTerminologyMapper()
    results = await mapper.map_batch(["Vital Signs", "AE/SAE Monitoring", "PK Sampling"])
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent / ".cache" / "terminology"


@dataclass
class TerminologyMapping:
    """Result of terminology mapping."""
    input_term: str
    cdisc_code: Optional[str] = None
    cdisc_name: Optional[str] = None
    cdisc_domain: Optional[str] = None
    confidence: float = 0.0
    source: str = "unmapped"  # "exact", "fuzzy", "llm", "cached", "unmapped"

    def is_mapped(self) -> bool:
        return self.cdisc_code is not None and self.confidence >= 0.70


@dataclass
class BatchMappingResult:
    """Result of batch terminology mapping."""
    mappings: Dict[str, TerminologyMapping] = field(default_factory=dict)
    llm_calls: int = 0
    cache_hits: int = 0
    deterministic_hits: int = 0
    total_terms: int = 0

    def get_mapping(self, term: str) -> Optional[TerminologyMapping]:
        """Get mapping for a term (case-insensitive)."""
        key = term.lower().strip()
        return self.mappings.get(key)


class LLMTerminologyMapper:
    """
    LLM-based terminology mapper with tiered lookup strategy.

    Lookup order:
    1. Cache lookup (instant, free)
    2. Deterministic matching via existing mapper
    3. LLM batch inference (batched for efficiency)
    """

    # CDISC domains for SOA procedures
    CDISC_DOMAINS = {
        "VS": "Vital Signs",
        "LB": "Laboratory",
        "EG": "ECG",
        "PE": "Physical Examination",
        "AE": "Adverse Events",
        "CM": "Concomitant Medications",
        "PR": "Procedures",
        "TU": "Tumor",
        "RS": "Response",
        "TR": "Tumor Results",
        "QS": "Questionnaires",
        "FA": "Findings About",
        "OE": "Ophthalmic Examinations",
        "PC": "Pharmacokinetics",
        "PP": "Pharmacodynamics",
        "EX": "Exposure",
        "DS": "Disposition",
        "MH": "Medical History",
        "DM": "Demographics",
        "SV": "Subject Visits",
        "SE": "Subject Elements",
        "TA": "Trial Arms",
        "TE": "Trial Elements",
        "TV": "Trial Visits",
    }

    def __init__(
        self,
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
        model: str = "gemini-2.5-pro",
    ):
        """
        Initialize LLM terminology mapper.

        Args:
            use_cache: Whether to use persistent caching
            cache_dir: Directory for cache files
            model: LLM model to use for inference
        """
        self.use_cache = use_cache
        self.cache_dir = cache_dir or CACHE_DIR
        self.model = model

        # In-memory cache (loaded from disk)
        self._cache: Dict[str, TerminologyMapping] = {}
        self._cache_loaded = False

        # Deterministic mapper (lazy loaded)
        self._deterministic_mapper = None

        # LLM clients (lazy loaded)
        self._llm_client = None  # Gemini (primary)
        self._claude_client = None  # Claude (fallback)
        self._azure_client = None  # Azure OpenAI (last fallback)

        # Ensure cache directory exists
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_cache(self) -> None:
        """Load cache from disk."""
        if self._cache_loaded:
            return

        cache_file = self.cache_dir / "llm_terminology_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    for key, mapping_data in data.items():
                        self._cache[key] = TerminologyMapping(**mapping_data)
                logger.info(f"Loaded {len(self._cache)} cached terminology mappings")
            except Exception as e:
                logger.warning(f"Failed to load terminology cache: {e}")

        self._cache_loaded = True

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if not self.use_cache:
            return

        cache_file = self.cache_dir / "llm_terminology_cache.json"
        try:
            data = {}
            for key, mapping in self._cache.items():
                data[key] = {
                    "input_term": mapping.input_term,
                    "cdisc_code": mapping.cdisc_code,
                    "cdisc_name": mapping.cdisc_name,
                    "cdisc_domain": mapping.cdisc_domain,
                    "confidence": mapping.confidence,
                    "source": mapping.source,
                }
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save terminology cache: {e}")

    def _get_deterministic_mapper(self):
        """Lazy load deterministic terminology mapper."""
        if self._deterministic_mapper is None:
            try:
                from .soa_terminology_mapper import TerminologyMapper
                self._deterministic_mapper = TerminologyMapper()
            except Exception as e:
                logger.warning(f"Failed to load deterministic mapper: {e}")
        return self._deterministic_mapper

    def _get_llm_client(self):
        """Lazy load LLM client."""
        if self._llm_client is None:
            try:
                import google.generativeai as genai
                from google.generativeai.types import HarmCategory, HarmBlockThreshold

                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)

                    # Disable safety filters for clinical terminology mapping
                    # Clinical terms like "HIV", "AE/SAE", "HCV" can trigger false positives
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
                    logger.info(f"Initialized LLM client: {self.model} (safety filters disabled)")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM client: {e}")
        return self._llm_client

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
                        timeout=120.0
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

    def _normalize_term(self, term: str) -> str:
        """Normalize term for cache lookup."""
        return term.lower().strip()

    def _try_deterministic(self, term: str) -> Optional[TerminologyMapping]:
        """Try deterministic matching first."""
        mapper = self._get_deterministic_mapper()
        if not mapper:
            return None

        # Try CDISC concepts
        cdisc_match = mapper._match_cdisc_exact(term) or mapper._match_cdisc_fuzzy(term)
        if cdisc_match:
            concept, score = cdisc_match
            return TerminologyMapping(
                input_term=term,
                cdisc_code=concept.cdisc_code,
                cdisc_name=concept.standardized_name,
                cdisc_domain=concept.domain,
                confidence=score,
                source="exact" if score == 1.0 else "fuzzy",
            )

        # Try codelists
        codelist_match = mapper._match_codelist(term)
        if codelist_match:
            entry, score = codelist_match
            return TerminologyMapping(
                input_term=term,
                cdisc_code=entry.code,
                cdisc_name=entry.decode,
                cdisc_domain=entry.codelist_name,
                confidence=score,
                source="exact" if score == 1.0 else "fuzzy",
            )

        return None

    async def _map_with_llm(self, terms: List[str]) -> Dict[str, TerminologyMapping]:
        """
        Map terms using LLM in a single batch call.

        Strategy: Try Gemini first, fall back to Azure OpenAI if Gemini fails.

        Args:
            terms: List of unmapped terms

        Returns:
            Dictionary of term -> TerminologyMapping
        """
        if not terms:
            return {}

        # Build prompt
        prompt = self._build_mapping_prompt(terms)

        # Try Gemini first (primary)
        result = await self._map_with_gemini(prompt, terms)
        if result:
            return result

        # Fall back to Claude if Gemini fails
        logger.info("Gemini failed - falling back to Anthropic Claude...")
        result = await self._map_with_claude(prompt, terms)
        if result:
            return result

        # Fall back to Azure OpenAI if Claude fails
        logger.info("Claude failed - falling back to Azure OpenAI GPT-5-mini...")
        result = await self._map_with_azure(prompt, terms)
        if result:
            return result

        # All failed
        logger.error("All LLMs (Gemini, Claude, Azure) failed for terminology mapping")
        return {}

    async def _map_with_gemini(self, prompt: str, terms: List[str]) -> Optional[Dict[str, TerminologyMapping]]:
        """Try mapping with Gemini."""
        client = self._get_llm_client()
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
                    "max_output_tokens": 4096,
                    "response_mime_type": "application/json",
                },
                safety_settings=safety_settings,
            )

            # Check for safety block
            if response.candidates and response.candidates[0].finish_reason.name == "SAFETY":
                logger.warning("Gemini safety filter blocked request")
                return None

            # Check for valid response
            if not response.text:
                logger.warning("Gemini returned empty response")
                return None

            return self._parse_llm_response(response.text, terms)

        except Exception as e:
            logger.warning(f"Gemini terminology mapping failed: {e}")
            return None

    async def _map_with_claude(self, prompt: str, terms: List[str]) -> Optional[Dict[str, TerminologyMapping]]:
        """Try mapping with Anthropic Claude (fallback)."""
        client = self._get_claude_client()
        if not client:
            logger.warning("Anthropic Claude client not available")
            return None

        try:
            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text if response.content else None
            if not content:
                logger.warning("Anthropic Claude returned empty response")
                return None

            logger.info(f"Anthropic Claude responded ({len(content)} chars)")
            return self._parse_llm_response(content, terms)

        except Exception as e:
            logger.warning(f"Anthropic Claude terminology mapping failed: {e}")
            return None

    async def _map_with_azure(self, prompt: str, terms: List[str]) -> Optional[Dict[str, TerminologyMapping]]:
        """Try mapping with Azure OpenAI GPT-5-mini (fallback)."""
        client = self._get_azure_client()
        if not client:
            logger.warning("Azure OpenAI client not available")
            return None

        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=self._azure_deployment,
                messages=[{"role": "user", "content": prompt}],
             
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning("Azure OpenAI returned empty response")
                return None

            logger.info(f"Azure OpenAI GPT-5-mini responded ({len(content)} chars)")
            return self._parse_llm_response(content, terms)

        except Exception as e:
            logger.error(f"Azure OpenAI terminology mapping failed: {e}")
            return None

    def _build_mapping_prompt(self, terms: List[str]) -> str:
        """Build the LLM prompt for terminology mapping."""
        terms_json = json.dumps(terms, indent=2)
        domains_json = json.dumps(self.CDISC_DOMAINS, indent=2)

        return f"""You are a clinical terminology expert. Map the following clinical procedure/assessment terms to CDISC Controlled Terminology.

## Input Terms
{terms_json}

## CDISC Domains Reference
{domains_json}

## Instructions
For each term, determine:
1. The most appropriate CDISC NCI code (format: Cxxxxx)
2. The standardized CDISC name
3. The CDISC domain (2-letter code like VS, LB, AE, etc.)
4. Your confidence (0.0-1.0)

Consider:
- Synonyms and abbreviations (AE = Adverse Event, PK = Pharmacokinetics)
- Compound terms (split "Vital Signs and Oxygen Saturation" → Vital Signs)
- Timing qualifiers (ignore "at Screening", "at C1D1" suffixes)
- Common variations (ECG = Electrocardiogram = 12-Lead ECG)

## Response Format
Return a JSON object where keys are the EXACT input terms and values are mapping objects:

```json
{{
  "Vital Signs": {{
    "cdisc_code": "C54706",
    "cdisc_name": "Vital Signs",
    "cdisc_domain": "VS",
    "confidence": 0.95
  }},
  "AE/SAE Monitoring": {{
    "cdisc_code": "C41331",
    "cdisc_name": "Adverse Event",
    "cdisc_domain": "AE",
    "confidence": 0.90
  }}
}}
```

If you cannot confidently map a term, set confidence below 0.70 and use your best guess.

Map ALL {len(terms)} terms. Return ONLY valid JSON, no markdown or explanation."""

    def _parse_llm_response(
        self,
        response_text: str,
        original_terms: List[str]
    ) -> Dict[str, TerminologyMapping]:
        """Parse LLM response into TerminologyMapping objects."""
        results = {}

        try:
            # Clean response (remove markdown if present)
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            data = json.loads(text)

            for term in original_terms:
                key = self._normalize_term(term)

                # Try exact match first
                mapping_data = data.get(term)

                # Try normalized match
                if not mapping_data:
                    for k, v in data.items():
                        if self._normalize_term(k) == key:
                            mapping_data = v
                            break

                if mapping_data and isinstance(mapping_data, dict):
                    results[key] = TerminologyMapping(
                        input_term=term,
                        cdisc_code=mapping_data.get("cdisc_code"),
                        cdisc_name=mapping_data.get("cdisc_name"),
                        cdisc_domain=mapping_data.get("cdisc_domain"),
                        confidence=float(mapping_data.get("confidence", 0.0)),
                        source="llm",
                    )
                else:
                    # No mapping found
                    results[key] = TerminologyMapping(
                        input_term=term,
                        confidence=0.0,
                        source="unmapped",
                    )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            # Return unmapped for all terms
            for term in original_terms:
                key = self._normalize_term(term)
                results[key] = TerminologyMapping(
                    input_term=term,
                    confidence=0.0,
                    source="unmapped",
                )

        return results

    async def map_batch(self, terms: List[str]) -> BatchMappingResult:
        """
        Map a batch of terms using tiered strategy.

        Order:
        1. Cache lookup
        2. Deterministic matching
        3. LLM batch inference (single call for all remaining)

        Args:
            terms: List of clinical terms to map

        Returns:
            BatchMappingResult with all mappings
        """
        self._load_cache()

        result = BatchMappingResult(total_terms=len(terms))
        unmapped_terms: List[str] = []

        for term in terms:
            if not term or not term.strip():
                continue

            key = self._normalize_term(term)

            # 1. Check cache
            if key in self._cache:
                result.mappings[key] = self._cache[key]
                result.cache_hits += 1
                continue

            # 2. Try deterministic matching
            deterministic_result = self._try_deterministic(term)
            if deterministic_result and deterministic_result.is_mapped():
                result.mappings[key] = deterministic_result
                result.deterministic_hits += 1
                # Cache deterministic results too
                self._cache[key] = deterministic_result
                continue

            # 3. Queue for LLM
            unmapped_terms.append(term)

        # 4. Batch LLM call for all unmapped terms
        if unmapped_terms:
            logger.info(f"LLM terminology mapping for {len(unmapped_terms)} unmapped terms...")
            llm_results = await self._map_with_llm(unmapped_terms)
            result.llm_calls = 1  # Single batch call

            for term in unmapped_terms:
                key = self._normalize_term(term)
                if key in llm_results:
                    mapping = llm_results[key]
                    result.mappings[key] = mapping
                    # Cache LLM results
                    self._cache[key] = mapping
                else:
                    result.mappings[key] = TerminologyMapping(
                        input_term=term,
                        confidence=0.0,
                        source="unmapped",
                    )

            # Save updated cache
            self._save_cache()

        logger.info(
            f"Terminology mapping complete: {result.total_terms} terms, "
            f"{result.cache_hits} cached, {result.deterministic_hits} deterministic, "
            f"{len(unmapped_terms)} LLM ({result.llm_calls} call)"
        )

        return result

    def map_single(self, term: str) -> TerminologyMapping:
        """
        Map a single term synchronously.

        For single terms, uses cache and deterministic only (no LLM).
        Use map_batch for LLM-based mapping.
        """
        self._load_cache()
        key = self._normalize_term(term)

        # Check cache
        if key in self._cache:
            return self._cache[key]

        # Try deterministic
        result = self._try_deterministic(term)
        if result:
            self._cache[key] = result
            return result

        # Return unmapped (don't call LLM for single terms)
        return TerminologyMapping(
            input_term=term,
            confidence=0.0,
            source="unmapped",
        )

    def is_mapped(self, term: str) -> bool:
        """Check if a term has a valid mapping (cached or deterministic)."""
        mapping = self.map_single(term)
        return mapping.is_mapped()


# Singleton instance for efficiency
_mapper_instance: Optional[LLMTerminologyMapper] = None


def get_llm_mapper() -> LLMTerminologyMapper:
    """Get singleton LLM terminology mapper instance."""
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = LLMTerminologyMapper()
    return _mapper_instance
