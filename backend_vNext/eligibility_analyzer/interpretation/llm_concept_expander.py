"""
LLM-Based Concept Expander

Replaces hardcoded medical dictionaries with LLM-powered concept expansion.
Uses Gemini for batch expansion with tiered lookup (cache → LLM → fallback).
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

from .concept_expansion_cache import (
    ConceptExpansion,
    ConceptExpansionCache,
    get_concept_expansion_cache,
)

load_dotenv()
logger = logging.getLogger(__name__)

# Configuration
BATCH_SIZE = 50  # Terms per LLM call
MAX_PARALLEL_BATCHES = 3  # Parallel API calls
MAX_RETRIES = 3  # Retry attempts for failed LLM calls
RETRY_BASE_DELAY = 2.0  # Base delay for exponential backoff

# Prompt file paths
PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "concept_expansion_batch.txt"
ENTITY_EXTRACTION_PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "clinical_entity_extraction.txt"


@dataclass
class BatchExpansionResult:
    """Result of batch concept expansion."""
    expansions: Dict[str, ConceptExpansion] = field(default_factory=dict)
    llm_calls: int = 0
    cache_hits: int = 0
    fallback_count: int = 0
    total_terms: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)


class LLMConceptExpander:
    """
    LLM-based clinical concept expansion with tiered lookup.

    Strategy:
    1. Cache lookup (instant, free)
    2. LLM batch inference (batched for efficiency)
    3. Basic text normalization (fallback if LLM fails)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-pro",
        use_cache: bool = False,
    ):
        """
        Initialize the expander.

        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            model: Gemini model to use
            use_cache: Whether to use persistent cache
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model)
        self.model_name = model

        self._cache = get_concept_expansion_cache() if use_cache else None
        self._prompt_template = self._load_prompt_template()
        self._entity_extraction_prompt = self._load_entity_extraction_prompt()

        # Initialize Azure OpenAI fallback client
        self._azure_client: Optional[AzureOpenAI] = None
        self._azure_deployment: Optional[str] = None
        self._init_azure_fallback()

        logger.info(f"LLMConceptExpander initialized with model: {model}")

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

    def _load_entity_extraction_prompt(self) -> Optional[str]:
        """Load entity extraction prompt template from file."""
        if not ENTITY_EXTRACTION_PROMPT_FILE.exists():
            logger.warning(f"Entity extraction prompt not found: {ENTITY_EXTRACTION_PROMPT_FILE}")
            return None

        with open(ENTITY_EXTRACTION_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()

    async def expand_batch(self, terms: List[str]) -> BatchExpansionResult:
        """
        Expand a batch of clinical terms using tiered lookup.

        Args:
            terms: List of clinical terms to expand

        Returns:
            BatchExpansionResult with expansions and metrics
        """
        start_time = time.time()
        result = BatchExpansionResult(total_terms=len(terms))

        if not terms:
            return result

        # Deduplicate while preserving order
        unique_terms = list(dict.fromkeys(terms))

        # Tier 1: Cache lookup
        if self._cache:
            cached, uncached = self._cache.get_batch(unique_terms)
            result.expansions.update(cached)
            result.cache_hits = len(cached)
            terms_to_process = uncached
        else:
            terms_to_process = unique_terms

        logger.info(
            f"Concept expansion: {len(terms)} terms, "
            f"{result.cache_hits} cached, {len(terms_to_process)} to expand"
        )

        # Tier 2: LLM batch expansion for uncached terms
        if terms_to_process:
            llm_expansions = await self._expand_with_llm(terms_to_process, result)
            result.expansions.update(llm_expansions)

            # Cache new expansions
            if self._cache and llm_expansions:
                self._cache.set_batch(llm_expansions)

        result.duration_seconds = time.time() - start_time
        logger.info(
            f"Concept expansion complete: {len(result.expansions)} expanded, "
            f"{result.llm_calls} LLM calls, {result.fallback_count} fallbacks, "
            f"{result.duration_seconds:.1f}s"
        )

        return result

    async def _expand_with_llm(
        self,
        terms: List[str],
        result: BatchExpansionResult,
    ) -> Dict[str, ConceptExpansion]:
        """
        Expand terms using LLM in batches.

        Args:
            terms: Terms to expand
            result: Result object to update metrics

        Returns:
            Dict mapping terms to expansions
        """
        expansions: Dict[str, ConceptExpansion] = {}

        # Split into batches
        batches = [
            terms[i:i + BATCH_SIZE]
            for i in range(0, len(terms), BATCH_SIZE)
        ]

        logger.info(f"Processing {len(terms)} terms in {len(batches)} batches")

        # Process batches (with limited parallelism)
        for batch_idx, batch in enumerate(batches):
            logger.debug(f"Processing batch {batch_idx + 1}/{len(batches)} ({len(batch)} terms)")

            try:
                batch_result = await self._call_llm_batch(batch)
                result.llm_calls += 1

                for term, expansion in batch_result.items():
                    expansions[term] = expansion

            except Exception as e:
                logger.error(f"LLM batch {batch_idx + 1} failed: {e}")
                result.errors.append(f"Batch {batch_idx + 1}: {str(e)}")

                # Tier 3: Fallback for failed batch
                for term in batch:
                    if term not in expansions:
                        expansions[term] = self._basic_normalize(term)
                        result.fallback_count += 1

        return expansions

    async def _call_llm_batch(self, terms: List[str]) -> Dict[str, ConceptExpansion]:
        """
        Call LLM for a single batch with retry logic.

        Args:
            terms: Batch of terms to expand

        Returns:
            Dict mapping terms to expansions
        """
        # Build prompt
        terms_json = json.dumps(terms, indent=2)
        prompt = self._prompt_template.replace("{terms_json}", terms_json)
        prompt = prompt.replace("{term_count}", str(len(terms)))

        # Retry with exponential backoff
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    prompt,
                    generation_config=genai.GenerationConfig(
                        max_output_tokens=65536,  # Maximum for gemini-2.5-flash
                        temperature=0.1,
                        response_mime_type="application/json",  # Request JSON directly
                    ),
                )

                # Extract text from response with robust handling
                response_text = self._extract_response_text(response)
                if not response_text:
                    logger.warning(f"Empty response from LLM on attempt {attempt + 1}")
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_BASE_DELAY * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
                    # Fall through to fallback on last attempt

                # Parse response
                return self._parse_llm_response(response_text, terms)

            except Exception as e:
                last_error = e
                if self._is_retryable_error(e):
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"LLM call attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. "
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

        raise last_error or RuntimeError("LLM call failed after all retries and Azure fallback")

    async def _call_azure_openai_fallback(
        self,
        prompt: str,
        terms: List[str]
    ) -> Optional[Dict[str, ConceptExpansion]]:
        """
        Call Azure OpenAI as fallback when Gemini fails.

        Args:
            prompt: The prompt to send
            terms: Original terms for fallback parsing

        Returns:
            Dict mapping terms to expansions, or None if fallback fails
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
        """
        Extract text from Gemini response with robust handling.

        Handles various response formats and edge cases.
        """
        try:
            # Try direct text access first
            if hasattr(response, 'text') and response.text:
                return response.text.strip()

            # Try candidates array
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    content = candidate.content
                    if hasattr(content, 'parts') and content.parts:
                        # Concatenate all text parts
                        texts = []
                        for part in content.parts:
                            if hasattr(part, 'text') and part.text:
                                texts.append(part.text)
                        if texts:
                            return "\n".join(texts).strip()

            # Check for blocked response
            if hasattr(response, 'prompt_feedback'):
                feedback = response.prompt_feedback
                if hasattr(feedback, 'block_reason') and feedback.block_reason:
                    logger.error(f"Response blocked: {feedback.block_reason}")
                    return None

            logger.warning(f"Could not extract text from response: {type(response)}")
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
    ) -> Dict[str, ConceptExpansion]:
        """
        Parse LLM JSON response into ConceptExpansion objects.

        Args:
            response_text: Raw LLM response (may be None or empty)
            original_terms: Original terms for fallback

        Returns:
            Dict mapping terms to expansions
        """
        expansions: Dict[str, ConceptExpansion] = {}

        # Handle empty response
        if not response_text or not response_text.strip():
            logger.error("Empty response text, using fallback for all terms")
            for term in original_terms:
                expansions[term] = self._basic_normalize(term)
            return expansions

        try:
            # Extract JSON from response - try multiple methods
            json_str = self._extract_json_from_response(response_text)

            if not json_str:
                logger.error(f"Could not extract JSON from response. First 500 chars: {response_text[:500]}")
                for term in original_terms:
                    expansions[term] = self._basic_normalize(term)
                return expansions

            parsed = json.loads(json_str)

            # Handle case where response is wrapped in an array
            if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
                parsed = parsed[0]

            if not isinstance(parsed, dict):
                logger.error(f"Parsed JSON is not a dict: {type(parsed)}")
                for term in original_terms:
                    expansions[term] = self._basic_normalize(term)
                return expansions

            logger.info(f"Successfully parsed JSON with {len(parsed)} terms")

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
                    expansions[term] = ConceptExpansion(
                        original_term=term,
                        abbreviation_expansion=data.get("abbreviation_expansion"),
                        synonyms=data.get("synonyms", [term]),
                        omop_domain_hint=data.get("omop_domain"),
                        vocabulary_hints=data.get("vocabulary_hints", []),
                        confidence=float(data.get("confidence", 0.8)),
                        source="llm",
                    )
                else:
                    # Term not in response - use fallback
                    logger.debug(f"Term not in LLM response: {term}")
                    expansions[term] = self._basic_normalize(term)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response text (first 1000 chars): {response_text[:1000]}")
            # Fallback for all terms
            for term in original_terms:
                expansions[term] = self._basic_normalize(term)

        return expansions

    def _extract_json_from_response(self, response_text: str) -> Optional[str]:
        """
        Extract JSON from LLM response, handling various formats.

        Args:
            response_text: Raw response text

        Returns:
            JSON string or None if not found
        """
        # Method 1: Look for ```json code block
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text)
        if json_match:
            return json_match.group(1).strip()

        # Method 2: Look for any ``` code block
        code_match = re.search(r"```\s*([\s\S]*?)\s*```", response_text)
        if code_match:
            content = code_match.group(1).strip()
            # Remove language identifier if present (e.g., "json\n")
            if content.startswith(('json\n', 'JSON\n')):
                content = content[5:]
            return content

        # Method 3: Response is raw JSON (starts with { or [)
        stripped = response_text.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            return stripped

        # Method 4: Find first { and last }
        first_brace = response_text.find('{')
        last_brace = response_text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return response_text[first_brace:last_brace + 1]

        return None

    def _basic_normalize(self, term: str) -> ConceptExpansion:
        """
        Basic text normalization fallback when LLM is unavailable.

        Args:
            term: Term to normalize

        Returns:
            ConceptExpansion with basic normalization
        """
        cleaned = self._clean_text(term)
        core = self._extract_core_concept(term)

        synonyms = [term]  # Always include original
        if cleaned and cleaned.lower() != term.lower():
            synonyms.append(cleaned)
        if core and core.lower() not in [s.lower() for s in synonyms]:
            synonyms.append(core)

        # Basic domain inference from keywords (fallback)
        domain = self._infer_domain_fallback(term)

        return ConceptExpansion(
            original_term=term,
            abbreviation_expansion=None,
            synonyms=synonyms,
            omop_domain_hint=domain,
            vocabulary_hints=self._get_default_vocab_hints(domain),
            confidence=0.5,
            source="fallback",
        )

    def _clean_text(self, text: str) -> str:
        """Basic text cleaning."""
        # Remove excess whitespace
        text = " ".join(text.split())
        # Remove certain punctuation
        text = re.sub(r'["\'\[\]\(\)]', '', text)
        return text.strip()

    def _extract_core_concept(self, text: str) -> str:
        """Extract core medical concept by removing numeric constraints."""
        result = text.lower()

        # Remove numeric comparisons
        result = re.sub(r'[≥≤><]=?\s*\d+\.?\d*', '', result)

        # Remove number ranges
        result = re.sub(r'\d+\.?\d*\s*(?:to|-)\s*\d+\.?\d*', '', result)

        # Remove standalone numbers with units
        result = re.sub(
            r'\b\d+\.?\d*\s*(?:years?|months?|weeks?|days?|hours?|mg|kg|g|ml|L|%|x10\^9/L)\b',
            '', result, flags=re.IGNORECASE
        )

        # Remove common phrases
        result = re.sub(
            r'\b(?:at least|no more than|less than|greater than|more than|minimum|maximum|within)\b',
            '', result, flags=re.IGNORECASE
        )

        return " ".join(result.split()).strip()

    def _get_default_vocab_hints(self, domain: str) -> List[str]:
        """Get default vocabulary hints for a domain."""
        vocab_map = {
            "Condition": ["SNOMED", "ICD10CM"],
            "Drug": ["RxNorm", "RxNorm Extension"],
            "Measurement": ["LOINC", "SNOMED"],
            "Procedure": ["CPT4", "SNOMED"],
            "Observation": ["SNOMED", "NCIt"],
            "Device": ["SNOMED", "HCPCS"],
        }
        return vocab_map.get(domain, ["SNOMED"])

    def get_cached(self, term: str) -> Optional[ConceptExpansion]:
        """Get cached expansion for a single term (sync)."""
        if self._cache:
            return self._cache.get(term)
        return None

    # =========================================================================
    # LLM-FIRST DOMAIN INFERENCE AND ENTITY EXTRACTION
    # =========================================================================

    async def infer_domains_batch_llm(
        self,
        terms: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Use LLM to infer OMOP domains for clinical terms.

        Replaces keyword-based domain inference with semantic understanding.

        Args:
            terms: List of clinical terms to classify

        Returns:
            Dict mapping term to domain info:
            {
                "term": {
                    "domain": "Condition",
                    "confidence": 0.95,
                    "rationale": "NSCLC is a disease diagnosis"
                }
            }
        """
        if not terms:
            return {}

        if not self._entity_extraction_prompt:
            logger.warning("Entity extraction prompt not loaded, using fallback")
            return {term: {"domain": self._infer_domain_fallback(term), "confidence": 0.5} for term in terms}

        try:
            # Use entity extraction prompt for domain inference
            result = await self._extract_entities_llm_batch(terms)

            domain_results: Dict[str, Dict[str, Any]] = {}
            for term in terms:
                if term in result:
                    domain_results[term] = {
                        "domain": result[term].get("domain", "Condition"),
                        "confidence": result[term].get("domain_confidence", 0.8),
                        "rationale": result[term].get("domain_rationale", ""),
                    }
                else:
                    # Fallback for missing terms
                    domain_results[term] = {
                        "domain": self._infer_domain_fallback(term),
                        "confidence": 0.5,
                        "rationale": "fallback inference",
                    }

            return domain_results

        except Exception as e:
            logger.error(f"LLM domain inference failed: {e}. Using fallback.")
            return {term: {"domain": self._infer_domain_fallback(term), "confidence": 0.5} for term in terms}

    async def extract_clinical_entities_batch_llm(
        self,
        terms: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Use LLM to extract clinical entities from text.

        Replaces regex-based pattern extraction with semantic understanding.
        Handles complex patterns like:
        - "History of X" -> entity with history modifier
        - "EGFR L858R mutation positive" -> biomarker with variant and status
        - Multi-word entities and parenthetical groupings

        Args:
            terms: List of clinical terms to process

        Returns:
            Dict mapping term to extraction result:
            {
                "term": {
                    "domain": "Condition",
                    "entities": [
                        {
                            "text": "NSCLC",
                            "type": "disease",
                            "modifiers": {"history": true},
                            "normalized_form": "non-small cell lung cancer"
                        }
                    ]
                }
            }
        """
        if not terms:
            return {}

        if not self._entity_extraction_prompt:
            logger.warning("Entity extraction prompt not loaded, using fallback")
            return {term: self._extract_entities_fallback(term) for term in terms}

        try:
            return await self._extract_entities_llm_batch(terms)

        except Exception as e:
            logger.error(f"LLM entity extraction failed: {e}. Using fallback.")
            return {term: self._extract_entities_fallback(term) for term in terms}

    async def _extract_entities_llm_batch(
        self,
        terms: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Call LLM for entity extraction with retry logic.

        Args:
            terms: Terms to process

        Returns:
            Dict mapping terms to extraction results
        """
        # Build prompt
        terms_json = json.dumps(terms, indent=2)
        prompt = self._entity_extraction_prompt.replace("{terms_json}", terms_json)
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

                response_text = self._extract_response_text(response)
                if not response_text:
                    logger.warning(f"Empty response on attempt {attempt + 1}")
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_BASE_DELAY * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue

                return self._parse_entity_extraction_response(response_text, terms)

            except Exception as e:
                last_error = e
                if self._is_retryable_error(e):
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f"LLM call attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. Retrying...")
                    await asyncio.sleep(delay)
                else:
                    raise

        # Try Azure fallback
        logger.warning("Gemini failed. Trying Azure OpenAI fallback...")
        azure_result = await self._call_azure_entity_extraction_fallback(prompt, terms)
        if azure_result is not None:
            return azure_result

        raise last_error or RuntimeError("Entity extraction failed after all retries")

    async def _call_azure_entity_extraction_fallback(
        self,
        prompt: str,
        terms: List[str]
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        Call Azure OpenAI for entity extraction as fallback.
        """
        if not self._azure_client or not self._azure_deployment:
            return None

        try:
            logger.info(f"Calling Azure OpenAI fallback for entity extraction...")
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
                    logger.info("Azure OpenAI entity extraction succeeded")
                    return self._parse_entity_extraction_response(content, terms)

        except Exception as e:
            logger.error(f"Azure OpenAI entity extraction fallback failed: {e}")

        return None

    def _parse_entity_extraction_response(
        self,
        response_text: Optional[str],
        original_terms: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Parse LLM response for entity extraction.
        """
        results: Dict[str, Dict[str, Any]] = {}

        if not response_text or not response_text.strip():
            logger.error("Empty entity extraction response, using fallback")
            for term in original_terms:
                results[term] = self._extract_entities_fallback(term)
            return results

        try:
            json_str = self._extract_json_from_response(response_text)

            if not json_str:
                logger.error(f"Could not extract JSON from entity extraction response")
                for term in original_terms:
                    results[term] = self._extract_entities_fallback(term)
                return results

            parsed = json.loads(json_str)

            # Handle nested "results" key
            if isinstance(parsed, dict) and "results" in parsed:
                parsed = parsed["results"]

            if not isinstance(parsed, dict):
                logger.error(f"Parsed JSON is not a dict: {type(parsed)}")
                for term in original_terms:
                    results[term] = self._extract_entities_fallback(term)
                return results

            for term in original_terms:
                # Try exact match first
                if term in parsed:
                    results[term] = parsed[term]
                else:
                    # Try case-insensitive match
                    term_lower = term.lower()
                    found = False
                    for key, value in parsed.items():
                        if key.lower() == term_lower:
                            results[term] = value
                            found = True
                            break
                    if not found:
                        results[term] = self._extract_entities_fallback(term)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse entity extraction response: {e}")
            for term in original_terms:
                results[term] = self._extract_entities_fallback(term)

        return results

    def _extract_entities_fallback(self, term: str) -> Dict[str, Any]:
        """
        Fallback entity extraction using regex patterns.
        """
        entities = []
        term_lower = term.lower()

        # Pattern: "History of X"
        import re
        match = re.search(r'history of\s+(.+)', term_lower)
        if match:
            entities.append({
                "text": match.group(1).strip(),
                "type": "condition",
                "modifiers": {"history": True},
                "normalized_form": match.group(1).strip(),
            })

        # Pattern: "Prior X"
        match = re.search(r'prior\s+(.+)', term_lower)
        if match:
            entities.append({
                "text": match.group(1).strip(),
                "type": "condition",
                "modifiers": {"prior": True},
                "normalized_form": match.group(1).strip(),
            })

        # Pattern: "X mutation/rearrangement"
        match = re.search(
            r'(\w+)\s+(?:mutation|rearrangement|alteration|amplification|deletion|fusion)',
            term_lower
        )
        if match:
            gene = match.group(1)
            entities.append({
                "text": match.group(0),
                "type": "biomarker",
                "modifiers": {"gene": gene},
                "normalized_form": f"{gene} gene mutation",
            })

        # Pattern: "X positive/negative"
        match = re.search(r'(.+?)\s+(positive|negative)', term_lower)
        if match:
            entities.append({
                "text": match.group(1).strip(),
                "type": "biomarker",
                "modifiers": {"status": match.group(2)},
                "normalized_form": match.group(1).strip(),
            })

        # If no patterns matched, use the whole term
        if not entities:
            entities.append({
                "text": term,
                "type": "unknown",
                "modifiers": {},
                "normalized_form": term.lower(),
            })

        return {
            "domain": self._infer_domain_fallback(term),
            "domain_confidence": 0.5,
            "domain_rationale": "fallback pattern matching",
            "entities": entities,
        }

    def _infer_domain_fallback(self, term: str) -> str:
        """FALLBACK: Infer OMOP domain from term keywords."""
        term_lower = term.lower()

        # Drug indicators
        if any(kw in term_lower for kw in ["drug", "medication", "dose", "mg"]):
            return "Drug"

        # Measurement indicators
        if any(kw in term_lower for kw in ["level", "count", "test", "g/dl", "mg/dl", "u/l", ">=", "<=", ">", "<"]):
            return "Measurement"

        # Procedure indicators
        if any(kw in term_lower for kw in ["surgery", "procedure", "biopsy", "resection", "transplant", "radiation therapy"]):
            return "Procedure"

        # Observation indicators
        if any(kw in term_lower for kw in ["age", "sex", "gender", "ecog", "kps", "status", "pregnancy"]):
            return "Observation"

        # Default to Condition for diseases/disorders
        return "Condition"


# Singleton instance
_expander_instance: Optional[LLMConceptExpander] = None


def get_concept_expander() -> LLMConceptExpander:
    """Get or create singleton expander instance."""
    global _expander_instance
    if _expander_instance is None:
        _expander_instance = LLMConceptExpander()
    return _expander_instance


def reset_expander() -> None:
    """Reset singleton expander instance (for testing)."""
    global _expander_instance
    _expander_instance = None
