"""
Term Normalizer for OMOP Concept Mapping

This module normalizes clinical trial eligibility terms to improve OMOP concept matching.
Uses LLM-based concept expansion for comprehensive medical terminology coverage.

Key Features:
1. LLM-powered term expansion (abbreviations, synonyms, domain hints)
2. Batch processing for efficiency (50 terms per LLM call)
3. Persistent caching (30-day TTL)
4. Fallback to basic text normalization when LLM unavailable

Usage:
    from eligibility_analyzer.interpretation.term_normalizer import TermNormalizer

    normalizer = TermNormalizer()

    # Async batch method (recommended for multiple terms)
    expansions = await normalizer.normalize_batch_async(["NSCLC", "EGFR mutation", "age >= 18"])

    # Sync method (uses cache only, fallback if uncached)
    variants = normalizer.normalize("NSCLC")
"""

import re
import logging
import asyncio
from typing import List, Set, Dict, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# Lazy-loaded reflection service
_reflection_service = None


def _get_reflection_service():
    """Lazy-load the reflection service."""
    global _reflection_service
    if _reflection_service is None:
        try:
            from ..services.llm_reflection import LLMReflectionService
            _reflection_service = LLMReflectionService()
        except Exception as e:
            logger.warning(f"Failed to initialize reflection service: {e}")
    return _reflection_service


class TermNormalizer:
    """
    Normalizes clinical terms for improved OMOP concept matching.

    Uses LLM-based expansion for comprehensive coverage, with fallback
    to basic text normalization when LLM is unavailable.
    """

    def __init__(self, use_llm: bool = True):
        """
        Initialize the normalizer.

        Args:
            use_llm: Whether to use LLM for concept expansion (default True)
        """
        self._use_llm = use_llm
        self._llm_expander = None

        # Patterns for numeric constraints (used in fallback)
        self.numeric_patterns = [
            r"[≥≤><]=?\s*\d+\.?\d*",  # >= 18, > 5.0
            r"\d+\.?\d*\s*(?:to|-)\s*\d+\.?\d*",  # 18 to 65, 0-1
            r"\d+\.?\d*\s*(?:years?|months?|weeks?|days?|mg|kg|g|ml|L|%)",  # 18 years
        ]

    def _get_llm_expander(self):
        """Lazy-load the LLM expander."""
        if self._llm_expander is None and self._use_llm:
            try:
                from .llm_concept_expander import get_concept_expander
                self._llm_expander = get_concept_expander()
            except Exception as e:
                logger.warning(f"Failed to initialize LLM expander: {e}. Using fallback.")
                self._use_llm = False
        return self._llm_expander

    async def normalize_batch_async(
        self,
        terms: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Batch normalize terms using LLM expansion (async).

        This is the recommended method for multiple terms as it:
        - Uses efficient batching (50 terms per LLM call)
        - Leverages LLM knowledge of medical terminology
        - Provides domain and vocabulary hints for OMOP search

        Args:
            terms: List of clinical terms to normalize

        Returns:
            Dict mapping original term to expansion result:
            {
                "NSCLC": {
                    "original": "NSCLC",
                    "primary": "non-small cell lung cancer",
                    "variants": ["NSCLC", "non-small cell lung cancer", ...],
                    "abbreviation_expansion": "non-small cell lung cancer",
                    "core_concept": "nsclc",
                    "omop_domain_hint": "Condition",
                    "vocabulary_hints": ["SNOMED", "ICD10CM"],
                    "confidence": 0.95,
                    "source": "llm"
                },
                ...
            }
        """
        if not terms:
            return {}

        results: Dict[str, Dict[str, Any]] = {}

        if self._use_llm:
            try:
                expander = self._get_llm_expander()
                if expander:
                    batch_result = await expander.expand_batch(terms)

                    for term, expansion in batch_result.expansions.items():
                        results[term] = {
                            "original": term,
                            "primary": expansion.abbreviation_expansion or self._extract_core_concept(term),
                            "variants": expansion.synonyms or [term],
                            "abbreviation_expansion": expansion.abbreviation_expansion,
                            "core_concept": self._extract_core_concept(term),
                            "omop_domain_hint": expansion.omop_domain_hint,
                            "vocabulary_hints": expansion.vocabulary_hints,
                            "confidence": expansion.confidence,
                            "source": expansion.source,
                        }

                    logger.info(
                        f"LLM batch normalization: {len(results)} terms expanded "
                        f"({batch_result.cache_hits} cached, {batch_result.llm_calls} LLM calls)"
                    )

            except Exception as e:
                logger.error(f"LLM batch normalization failed: {e}. Using fallback.")

        # Fallback for any terms not processed by LLM
        for term in terms:
            if term not in results:
                results[term] = self._normalize_fallback(term)

        return results

    def normalize(self, term: str) -> List[str]:
        """
        Normalize a clinical term and return variant forms for OMOP lookup (sync).

        Uses cached LLM results if available, otherwise falls back to
        basic text normalization.

        Args:
            term: Original clinical term (e.g., "NSCLC with EGFR mutation")

        Returns:
            List of normalized terms to search for in OMOP
        """
        if not term or not term.strip():
            return []

        # Try to get cached LLM expansion first
        if self._use_llm:
            try:
                expander = self._get_llm_expander()
                if expander:
                    cached = expander.get_cached(term)
                    if cached:
                        # Return synonyms from cache
                        return cached.synonyms or [term]
            except Exception as e:
                logger.debug(f"Cache lookup failed: {e}")

        # Fallback to basic normalization
        return self._normalize_basic(term)

    def normalize_for_omop_lookup(self, term: str) -> Dict[str, Any]:
        """
        Normalize term and return structured result for OMOP lookup (sync).

        Uses cached LLM results if available, otherwise falls back to
        basic text normalization.

        Args:
            term: Clinical term to normalize

        Returns:
            Dict with normalization results including domain hints
        """
        if not term or not term.strip():
            return {"original": term, "primary": "", "variants": [], "core_concept": ""}

        # Try cached LLM expansion first
        if self._use_llm:
            try:
                expander = self._get_llm_expander()
                if expander:
                    cached = expander.get_cached(term)
                    if cached:
                        return {
                            "original": term,
                            "primary": cached.abbreviation_expansion or self._extract_core_concept(term),
                            "variants": cached.synonyms or [term],
                            "abbreviation_expansion": cached.abbreviation_expansion,
                            "core_concept": self._extract_core_concept(term),
                            "omop_domain_hint": cached.omop_domain_hint,
                            "vocabulary_hints": cached.vocabulary_hints,
                            "confidence": cached.confidence,
                            "source": "cache",
                        }
            except Exception as e:
                logger.debug(f"Cache lookup failed: {e}")

        # Fallback
        return self._normalize_fallback(term)

    def _normalize_fallback(self, term: str) -> Dict[str, Any]:
        """Generate fallback normalization result (sync, uses keyword patterns)."""
        core = self._extract_core_concept(term)
        variants = self._normalize_basic(term)
        domain = self._infer_domain_keyword_fallback(term)

        return {
            "original": term,
            "primary": core or term.lower(),
            "variants": variants,
            "abbreviation_expansion": None,
            "core_concept": core,
            "omop_domain_hint": domain,
            "vocabulary_hints": self._get_default_vocab_hints(domain),
            "confidence": 0.3,
            "source": "fallback",
        }

    def _normalize_basic(self, term: str) -> List[str]:
        """
        Basic text normalization fallback (no LLM).

        Performs:
        1. Text cleaning
        2. Core concept extraction
        3. Compound term splitting
        4. Pattern-based extraction
        """
        results: Set[str] = set()

        # 1. Basic cleaning
        cleaned = self._clean_text(term)
        if cleaned:
            results.add(cleaned)

        # 2. Extract core concept (remove numeric constraints)
        core = self._extract_core_concept(term)
        if core and core != cleaned:
            results.add(core)

        # 3. Split compound terms
        parts = self._split_compound_term(term)
        results.update(parts)

        # 4. Handle specific patterns (fallback regex)
        specific = self._handle_specific_patterns_fallback(term)
        results.update(specific)

        # Remove empty strings and very short terms
        return [t for t in results if t and len(t) > 1]

    def _clean_text(self, text: str) -> str:
        """Basic text cleaning."""
        # Remove excess whitespace
        text = " ".join(text.split())

        # Remove certain punctuation but keep hyphens in compound words
        text = re.sub(r'["\'\[\]\(\)]', '', text)

        # Standardize hyphens
        text = re.sub(r'\s*[-–—]\s*', '-', text)

        return text.strip()

    def _extract_core_concept(self, text: str) -> str:
        """Extract the core medical concept by removing numeric constraints."""
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

        # Remove "at least", "no more than", etc.
        result = re.sub(
            r'\b(?:at least|no more than|less than|greater than|more than|minimum|maximum|within)\b',
            '', result, flags=re.IGNORECASE
        )

        # Clean up result
        result = " ".join(result.split())
        return result.strip()

    def _split_compound_term(self, text: str) -> Set[str]:
        """Split compound terms into components."""
        results: Set[str] = set()
        text_lower = text.lower()

        # Split on common conjunctions
        parts = re.split(r'\s+(?:and|or|with|without|including|excluding)\s+', text_lower)

        for part in parts:
            part = part.strip()
            if len(part) > 2:
                results.add(part)

                # Also extract core concept from each part
                core = self._extract_core_concept(part)
                if core and len(core) > 2:
                    results.add(core)

        return results

    def _handle_specific_patterns_fallback(self, text: str) -> Set[str]:
        """FALLBACK: Handle specific clinical patterns using regex."""
        results: Set[str] = set()
        text_lower = text.lower()

        # Pattern: "History of X" -> extract X
        match = re.search(r'history of\s+(.+)', text_lower)
        if match:
            results.add(match.group(1).strip())

        # Pattern: "Prior X" -> extract X
        match = re.search(r'prior\s+(.+)', text_lower)
        if match:
            results.add(match.group(1).strip())

        # Pattern: "X mutation/rearrangement/alteration" -> extract gene name
        match = re.search(
            r'(\w+)\s+(?:mutation|rearrangement|alteration|amplification|deletion|fusion)',
            text_lower
        )
        if match:
            gene = match.group(1)
            results.add(f"{gene} mutation")
            results.add(f"{gene} gene")
            results.add(gene)

        # Pattern: "Positive/Negative X" -> extract X
        match = re.search(r'(?:positive|negative)\s+(.+)', text_lower)
        if match:
            results.add(match.group(1).strip())

        # Pattern: "X positive/negative" -> extract X
        match = re.search(r'(.+?)\s+(?:positive|negative)', text_lower)
        if match:
            results.add(match.group(1).strip())

        return results

    async def _infer_domain_with_reflection_async(self, term: str) -> Tuple[str, float, str]:
        """
        LLM-FIRST: Infer OMOP domain using reflection service.

        Returns:
            Tuple of (domain, confidence, rationale)
        """
        reflection = _get_reflection_service()
        if reflection:
            try:
                domain, confidence, rationale = await reflection.infer_omop_domain(term)
                logger.debug(f"Reflection inferred domain '{domain}' for '{term}' (confidence: {confidence})")
                return domain, confidence, rationale
            except Exception as e:
                logger.warning(f"Reflection domain inference failed for '{term}': {e}")

        # Fall back to keyword patterns
        domain = self._infer_domain_keyword_fallback(term)
        return domain, 0.5, "keyword pattern fallback"

    def _infer_domain_fallback(self, term: str) -> str:
        """
        Infer OMOP domain - tries reflection service first, then keyword patterns.

        For async contexts, prefer using _infer_domain_with_reflection_async() directly.
        """
        # Try to use reflection service via asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in async context - can't use run()
                # Fall back to keyword patterns
                return self._infer_domain_keyword_fallback(term)
            else:
                domain, _, _ = loop.run_until_complete(
                    self._infer_domain_with_reflection_async(term)
                )
                return domain
        except RuntimeError:
            # No event loop - fall back to keyword patterns
            return self._infer_domain_keyword_fallback(term)

    def _infer_domain_keyword_fallback(self, term: str) -> str:
        """
        LAST-RESORT FALLBACK: Infer OMOP domain from term keywords.

        Only used when:
        1. Reflection service is unavailable
        2. LLM inference fails
        3. Running in sync context without event loop
        """
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

    def _get_default_vocab_hints(self, domain: str) -> List[str]:
        """Get default vocabulary hints for a domain (fallback)."""
        vocab_map = {
            "Condition": ["SNOMED", "ICD10CM"],
            "Drug": ["RxNorm", "RxNorm Extension"],
            "Measurement": ["LOINC", "SNOMED"],
            "Procedure": ["CPT4", "SNOMED"],
            "Observation": ["SNOMED", "NCIt"],
            "Device": ["SNOMED", "HCPCS"],
        }
        return vocab_map.get(domain, ["SNOMED"])

    # =========================================================================
    # LLM-FIRST METHODS (Async)
    # =========================================================================

    async def infer_domains_batch_async(
        self,
        terms: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Use LLM to infer OMOP domains for clinical terms (async).

        This method provides semantic domain inference using clinical reasoning,
        replacing keyword-based patterns with LLM understanding.

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

        if not self._use_llm:
            return {
                term: {"domain": self._infer_domain_fallback(term), "confidence": 0.5}
                for term in terms
            }

        try:
            expander = self._get_llm_expander()
            if expander:
                return await expander.infer_domains_batch_llm(terms)
        except Exception as e:
            logger.error(f"LLM domain inference failed: {e}. Trying reflection service.")

        # Second-tier fallback: Use reflection service for semantic inference
        reflection = _get_reflection_service()
        if reflection:
            try:
                results = {}
                for term in terms:
                    domain, confidence, rationale = await reflection.infer_omop_domain(term)
                    results[term] = {
                        "domain": domain,
                        "confidence": confidence,
                        "rationale": rationale,
                    }
                logger.info(f"Reflection service inferred domains for {len(results)} terms")
                return results
            except Exception as e:
                logger.warning(f"Reflection service domain inference failed: {e}. Using keyword fallback.")

        # Last-resort fallback: keyword patterns
        return {
            term: {
                "domain": self._infer_domain_keyword_fallback(term),
                "confidence": 0.3,
                "rationale": "keyword pattern fallback",
            }
            for term in terms
        }

    async def extract_clinical_entities_batch_async(
        self,
        terms: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Use LLM to extract clinical entities from text (async).

        This method provides semantic entity extraction using clinical reasoning,
        handling complex patterns like:
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

        if not self._use_llm:
            return {term: self._extract_entities_fallback(term) for term in terms}

        try:
            expander = self._get_llm_expander()
            if expander:
                return await expander.extract_clinical_entities_batch_llm(terms)
        except Exception as e:
            logger.error(f"LLM entity extraction failed: {e}. Using fallback.")

        # Fallback
        return {term: self._extract_entities_fallback(term) for term in terms}

    def _extract_entities_fallback(self, term: str) -> Dict[str, Any]:
        """
        Fallback entity extraction using regex patterns.
        """
        entities = []
        term_lower = term.lower()

        # Pattern: "History of X"
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
            "domain": self._infer_domain_keyword_fallback(term),
            "domain_confidence": 0.3,
            "domain_rationale": "keyword pattern fallback",
            "entities": entities,
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def normalize_term(term: str) -> List[str]:
    """Convenience function to normalize a term (sync, uses cache/fallback)."""
    normalizer = TermNormalizer()
    return normalizer.normalize(term)


async def normalize_terms_async(terms: List[str]) -> Dict[str, Dict[str, Any]]:
    """Convenience function to batch normalize terms (async, uses LLM)."""
    normalizer = TermNormalizer()
    return await normalizer.normalize_batch_async(terms)
