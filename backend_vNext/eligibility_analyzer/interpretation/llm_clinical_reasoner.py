"""
LLM Clinical Reasoner for Unmapped Terms (Stage 5.5)

Second-pass clinical reasoning for eligibility terms that failed OMOP mapping.
Uses LLM clinical knowledge to interpret the intent of complex eligibility criteria
and suggest simpler, mappable clinical concepts.
"""

import os
import re
import json
import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import google.generativeai as genai
from openai import AzureOpenAI
from dotenv import load_dotenv

from .concept_expansion_cache import ConceptExpansionCache, get_concept_expansion_cache

load_dotenv()
logger = logging.getLogger(__name__)

# Configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0

# Prompt file path
PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "clinical_reasoning_unmapped.txt"


@dataclass
class MappableConcept:
    """A single mappable concept extracted from clinical reasoning."""
    concept: str
    domain: str
    vocabulary_hints: List[str] = field(default_factory=list)
    relationship: str = "primary"


@dataclass
class ClinicalReasoning:
    """Result of LLM clinical reasoning for an unmapped term."""
    original_term: str
    clinical_interpretation: str
    mappable_concepts: List[MappableConcept] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "llm_clinical_reasoning"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "original_term": self.original_term,
            "clinical_interpretation": self.clinical_interpretation,
            "mappable_concepts": [
                {
                    "concept": mc.concept,
                    "domain": mc.domain,
                    "vocabulary_hints": mc.vocabulary_hints,
                    "relationship": mc.relationship,
                }
                for mc in self.mappable_concepts
            ],
            "confidence": self.confidence,
            "source": self.source,
        }


@dataclass
class ClinicalReasoningResult:
    """Result of batch clinical reasoning."""
    reasonings: Dict[str, ClinicalReasoning] = field(default_factory=dict)
    llm_calls: int = 0
    cache_hits: int = 0
    total_terms: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)


class LLMClinicalReasoner:
    """
    LLM-based clinical reasoning for unmapped eligibility terms.

    Uses Gemini to interpret the clinical intent of complex eligibility criteria
    and break them into simpler, standard medical concepts for OMOP mapping.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-pro",
        use_cache: bool = False,
    ):
        """
        Initialize the clinical reasoner.

        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            model: Gemini model to use
            use_cache: Whether to cache reasoning results
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model)
        self.model_name = model

        # Use same cache as concept expander with different prefix
        self._cache = get_concept_expansion_cache() if use_cache else None
        self._prompt_template = self._load_prompt_template()

        # Initialize Azure OpenAI fallback client
        self._azure_client: Optional[AzureOpenAI] = None
        self._azure_deployment: Optional[str] = None
        self._init_azure_fallback()

        logger.info(f"LLMClinicalReasoner initialized with model: {model}")

    def _init_azure_fallback(self) -> None:
        """Initialize Azure OpenAI client for fallback."""
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview")

        if azure_key and azure_endpoint:
            try:
                self._azure_client = AzureOpenAI(
                    api_key=azure_key,
                    api_version=azure_version,
                    azure_endpoint=azure_endpoint,
                    timeout=120.0
                )
                self._azure_deployment = azure_deployment
                logger.info(f"Azure OpenAI fallback initialized: {azure_deployment}")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure OpenAI fallback: {e}")
        else:
            logger.info("Azure OpenAI credentials not found - fallback disabled")

    def _load_prompt_template(self) -> str:
        """Load prompt template from file."""
        if not PROMPT_FILE.exists():
            raise FileNotFoundError(f"Prompt file not found: {PROMPT_FILE}")

        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()

    def _get_cache_key(self, term: str) -> str:
        """Generate cache key for clinical reasoning."""
        return f"reasoning:{term.lower().strip()}"

    async def reason_unmapped_terms(
        self,
        unmapped_terms: List[Dict[str, Any]],
    ) -> ClinicalReasoningResult:
        """
        Apply clinical reasoning to unmapped terms.

        Args:
            unmapped_terms: List of unmapped term dicts from Stage 5 with format:
                {
                    "criterionId": str,
                    "atomicId": str,
                    "term": str,
                    "domain": str,
                    "reason": str
                }

        Returns:
            ClinicalReasoningResult with reasoning for each term
        """
        start_time = time.time()
        result = ClinicalReasoningResult(total_terms=len(unmapped_terms))

        if not unmapped_terms:
            return result

        # Extract unique terms
        unique_terms = list({t.get("term", ""): t for t in unmapped_terms if t.get("term")}.values())
        term_strings = [t["term"] for t in unique_terms]

        logger.info(f"Stage 5.5: Clinical reasoning for {len(term_strings)} unmapped terms")

        # Check cache first
        cached_terms = []
        uncached_terms = []
        for term in term_strings:
            cache_key = self._get_cache_key(term)
            if self._cache:
                cached = self._cache.get(cache_key)
                if cached:
                    # Convert cached ConceptExpansion to ClinicalReasoning
                    result.reasonings[term] = ClinicalReasoning(
                        original_term=term,
                        clinical_interpretation=cached.abbreviation_expansion or "",
                        mappable_concepts=[
                            MappableConcept(
                                concept=s,
                                domain=cached.omop_domain_hint or "Observation",
                                vocabulary_hints=cached.vocabulary_hints,
                            )
                            for s in (cached.synonyms or [])[:3]
                        ],
                        confidence=cached.confidence,
                        source="cache",
                    )
                    result.cache_hits += 1
                    cached_terms.append(term)
                else:
                    uncached_terms.append(term)
            else:
                uncached_terms.append(term)

        logger.info(f"Clinical reasoning: {result.cache_hits} cached, {len(uncached_terms)} to reason")

        # Call LLM for uncached terms
        if uncached_terms:
            try:
                llm_reasonings = await self._call_llm_reasoning(uncached_terms)
                result.llm_calls += 1

                for term, reasoning in llm_reasonings.items():
                    result.reasonings[term] = reasoning

                    # Cache the result (as ConceptExpansion format for compatibility)
                    if self._cache:
                        from .concept_expansion_cache import ConceptExpansion
                        cache_key = self._get_cache_key(term)
                        # Store as ConceptExpansion with clinical_interpretation in abbreviation_expansion
                        cache_entry = ConceptExpansion(
                            original_term=term,
                            abbreviation_expansion=reasoning.clinical_interpretation,
                            synonyms=[mc.concept for mc in reasoning.mappable_concepts],
                            omop_domain_hint=reasoning.mappable_concepts[0].domain if reasoning.mappable_concepts else "Observation",
                            vocabulary_hints=reasoning.mappable_concepts[0].vocabulary_hints if reasoning.mappable_concepts else [],
                            confidence=reasoning.confidence,
                            source="llm_clinical_reasoning",
                        )
                        self._cache.set(cache_key, cache_entry)

            except Exception as e:
                logger.error(f"Clinical reasoning LLM call failed: {e}")
                result.errors.append(str(e))

        # Save cache
        if self._cache:
            self._cache.flush()

        result.duration_seconds = time.time() - start_time
        logger.info(
            f"Stage 5.5 complete: {len(result.reasonings)} terms reasoned, "
            f"{result.cache_hits} cached, {result.llm_calls} LLM calls, "
            f"{result.duration_seconds:.1f}s"
        )

        return result

    async def _call_llm_reasoning(
        self,
        terms: List[str],
    ) -> Dict[str, ClinicalReasoning]:
        """
        Call LLM for clinical reasoning on terms.

        Args:
            terms: List of unmapped terms to reason about

        Returns:
            Dict mapping terms to ClinicalReasoning objects
        """
        # Build prompt
        terms_json = json.dumps(terms, indent=2)
        prompt = self._prompt_template.replace("{unmapped_terms_json}", terms_json)
        prompt = prompt.replace("{term_count}", str(len(terms)))

        # Retry with exponential backoff
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    prompt,
                    generation_config=genai.GenerationConfig(
                        max_output_tokens=65536,
                        temperature=0.1,
                        response_mime_type="application/json",
                    ),
                )

                # Extract text from response
                response_text = self._extract_response_text(response)
                if not response_text:
                    logger.warning(f"Empty response from LLM on attempt {attempt + 1}")
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_BASE_DELAY * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue

                # Parse response
                return self._parse_llm_response(response_text, terms)

            except Exception as e:
                last_error = e
                if self._is_retryable_error(e):
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Clinical reasoning attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        # All Gemini retries failed - try Azure OpenAI fallback
        logger.warning(f"Gemini failed after {MAX_RETRIES} retries. Trying Azure OpenAI fallback...")
        azure_result = await self._call_azure_openai_fallback(prompt, terms)
        if azure_result is not None:
            return azure_result

        raise last_error or RuntimeError("Clinical reasoning failed after all retries and Azure fallback")

    async def _call_azure_openai_fallback(
        self,
        prompt: str,
        terms: List[str]
    ) -> Optional[Dict[str, ClinicalReasoning]]:
        """
        Call Azure OpenAI as fallback when Gemini fails.

        Args:
            prompt: The prompt to send
            terms: Original terms for fallback parsing

        Returns:
            Dict mapping terms to ClinicalReasoning, or None if fallback fails
        """
        if not self._azure_client or not self._azure_deployment:
            logger.warning("Azure OpenAI fallback not available")
            return None

        try:
            logger.info(f"Calling Azure OpenAI fallback ({self._azure_deployment})...")
            response = await asyncio.to_thread(
                self._azure_client.chat.completions.create,
                model=self._azure_deployment,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a clinical terminology expert. Return only valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=16384,
                response_format={"type": "json_object"}
            )

            if response and response.choices:
                content = response.choices[0].message.content
                if content:
                    logger.info("Azure OpenAI fallback succeeded")
                    return self._parse_llm_response(content, terms)

        except Exception as e:
            logger.error(f"Azure OpenAI fallback failed: {e}")

        return None

    def _extract_response_text(self, response) -> Optional[str]:
        """Extract text from Gemini response."""
        try:
            if hasattr(response, 'text') and response.text:
                return response.text.strip()

            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    content = candidate.content
                    if hasattr(content, 'parts') and content.parts:
                        texts = []
                        for part in content.parts:
                            if hasattr(part, 'text') and part.text:
                                texts.append(part.text)
                        if texts:
                            return "\n".join(texts).strip()

            return None
        except Exception as e:
            logger.error(f"Error extracting response text: {e}")
            return None

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if error is retryable."""
        error_str = str(error).lower()
        retryable_patterns = [
            "503", "serviceUnavailable",
            "429", "resourceexhausted", "rate limit",
            "504", "deadline",
            "timeout", "timed out",
            "connection", "network",
        ]
        return any(pattern in error_str for pattern in retryable_patterns)

    def _parse_llm_response(
        self,
        response_text: Optional[str],
        original_terms: List[str],
    ) -> Dict[str, ClinicalReasoning]:
        """Parse LLM JSON response into ClinicalReasoning objects."""
        reasonings: Dict[str, ClinicalReasoning] = {}

        if not response_text or not response_text.strip():
            logger.error("Empty response text from clinical reasoning")
            return reasonings

        try:
            # Extract JSON
            json_str = self._extract_json_from_response(response_text)
            if not json_str:
                logger.error(f"Could not extract JSON. First 500 chars: {response_text[:500]}")
                return reasonings

            parsed = json.loads(json_str)

            if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
                parsed = parsed[0]

            if not isinstance(parsed, dict):
                logger.error(f"Parsed JSON is not a dict: {type(parsed)}")
                return reasonings

            logger.info(f"Successfully parsed clinical reasoning JSON with {len(parsed)} terms")

            for term in original_terms:
                # Try exact match first
                if term in parsed:
                    data = parsed[term]
                else:
                    # Try case-insensitive match
                    term_lower = term.lower()
                    data = None
                    for key, value in parsed.items():
                        if key.lower() == term_lower:
                            data = value
                            break

                if data and isinstance(data, dict):
                    mappable_concepts = []
                    for mc in data.get("mappable_concepts", []):
                        if isinstance(mc, dict):
                            mappable_concepts.append(MappableConcept(
                                concept=mc.get("concept", ""),
                                domain=mc.get("domain", "Observation"),
                                vocabulary_hints=mc.get("vocabulary_hints", []),
                                relationship=mc.get("relationship", "primary"),
                            ))

                    reasonings[term] = ClinicalReasoning(
                        original_term=term,
                        clinical_interpretation=data.get("clinical_interpretation", ""),
                        mappable_concepts=mappable_concepts,
                        confidence=float(data.get("confidence", 0.8)),
                        source="llm_clinical_reasoning",
                    )
                else:
                    logger.debug(f"Term not in clinical reasoning response: {term}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse clinical reasoning JSON: {e}")
            logger.error(f"Response text (first 1000 chars): {response_text[:1000]}")

        return reasonings

    def _extract_json_from_response(self, response_text: str) -> Optional[str]:
        """Extract JSON from LLM response."""
        # Method 1: Look for ```json code block
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text)
        if json_match:
            return json_match.group(1).strip()

        # Method 2: Look for any ``` code block
        code_match = re.search(r"```\s*([\s\S]*?)\s*```", response_text)
        if code_match:
            content = code_match.group(1).strip()
            if content.startswith(('json\n', 'JSON\n')):
                content = content[5:]
            return content

        # Method 3: Response is raw JSON
        stripped = response_text.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            return stripped

        # Method 4: Find first { and last }
        first_brace = response_text.find('{')
        last_brace = response_text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return response_text[first_brace:last_brace + 1]

        return None


# Singleton instance
_reasoner_instance: Optional[LLMClinicalReasoner] = None


def get_clinical_reasoner() -> LLMClinicalReasoner:
    """Get or create singleton clinical reasoner instance."""
    global _reasoner_instance
    if _reasoner_instance is None:
        _reasoner_instance = LLMClinicalReasoner()
    return _reasoner_instance


def reset_clinical_reasoner() -> None:
    """Reset singleton instance (for testing)."""
    global _reasoner_instance
    _reasoner_instance = None
