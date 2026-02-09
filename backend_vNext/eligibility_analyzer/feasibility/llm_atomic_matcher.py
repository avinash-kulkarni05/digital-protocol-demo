"""
LLM-based Atomic Matcher for V2 Patient Funnel.

This module replaces keyword matching and Jaccard similarity with LLM-powered
semantic reasoning for:
1. Matching atomics to OMOP mappings
2. Classifying atomics into funnel categories
3. Matching atomics to key criteria for elimination rate propagation

Follows the same patterns as CriterionClassifier for consistency.
"""

import os
import json
import logging
import asyncio
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# LLM configuration
LLM_TIMEOUT_SECONDS = 120
LLM_MAX_RETRIES = 3
DEFAULT_MODEL = "gemini-2.5-pro"
BATCH_SIZE = 20  # Match CriterionClassifier pattern
CONFIDENCE_THRESHOLD = 0.7

# Max output tokens per model
MODEL_MAX_TOKENS = {
    "gemini-2.5-pro": 65536,
    "gemini-2.5-flash": 65536,
    "gemini-2.5-flash-lite": 65536,
    "gemini-2.0-flash-exp": 8192,
    "gemini-1.5-flash": 8192,
    "gemini-1.5-pro": 8192,
}


class LLMAtomicMatcher:
    """
    LLM-based matcher for atomic criteria.

    Replaces brittle keyword matching with semantic reasoning that generalizes
    across all protocol types without code changes.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        prompts_dir: Optional[Path] = None,
        use_azure_fallback: bool = True,
        use_cache: bool = False,
    ):
        """
        Initialize the LLM atomic matcher.

        Args:
            api_key: Gemini API key. Defaults to GEMINI_API_KEY env var.
            model: Gemini model to use. Defaults to GEMINI_MODEL env var or gemini-2.5-pro.
            prompts_dir: Directory containing prompt files.
            use_azure_fallback: Whether to fallback to Azure OpenAI on Gemini failure.
            use_cache: Whether to cache LLM results by atomic text hash.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")

        # Use GEMINI_MODEL env var if set, otherwise default
        model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model)
        self.model_name = model
        self.max_output_tokens = MODEL_MAX_TOKENS.get(model, 8192)
        self.use_azure_fallback = use_azure_fallback
        self.use_cache = use_cache

        # Azure OpenAI configuration (fallback)
        self.azure_client = None
        if use_azure_fallback:
            self._init_azure_client()

        # Load prompts
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent / "prompts"
        self.prompts_dir = prompts_dir

        self.omop_matching_prompt = self._load_prompt("atomic_omop_matching.txt")
        self.classification_prompt = self._load_prompt("atomic_classification.txt")
        self.key_criteria_prompt = self._load_prompt("atomic_key_criteria_matching.txt")
        self.domain_validation_prompt = self._load_prompt("atomic_domain_validation.txt")
        self.semantic_validation_prompt = self._load_prompt("atomic_semantic_validation.txt")

        # Simple in-memory cache (keyed by content hash)
        self._cache: Dict[str, Dict] = {}

        logger.info(
            f"LLMAtomicMatcher initialized with model: {model} "
            f"(max_tokens: {self.max_output_tokens}, cache: {use_cache})"
        )

    def _init_azure_client(self) -> None:
        """Initialize Azure OpenAI client for fallback."""
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

        if azure_key and azure_endpoint and azure_deployment:
            try:
                from openai import AzureOpenAI
                self.azure_client = AzureOpenAI(
                    api_key=azure_key,
                    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
                    azure_endpoint=azure_endpoint,
                )
                self.azure_deployment = azure_deployment
                logger.info("Azure OpenAI fallback initialized")
            except ImportError:
                logger.warning("openai package not installed, Azure fallback disabled")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure OpenAI: {e}")

    def _load_prompt(self, filename: str) -> str:
        """Load prompt template from file."""
        prompt_path = self.prompts_dir / filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

    def _get_cache_key(self, content: str) -> str:
        """Generate cache key from content hash."""
        return hashlib.md5(content.encode()).hexdigest()

    @retry(
        stop=stop_after_attempt(LLM_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=lambda retry_state: (
            retry_state.outcome.exception() is not None and
            any(p in str(retry_state.outcome.exception()).lower()
                for p in ["503", "504", "429", "rate limit", "overloaded", "resource exhausted"])
        ),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying LLM call after error: {retry_state.outcome.exception()}"
        )
    )
    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API with retry logic."""
        response = await asyncio.to_thread(
            self.model.generate_content,
            prompt,
            generation_config={
                "max_output_tokens": self.max_output_tokens,
                "temperature": 0.1,
                "response_mime_type": "application/json"
            }
        )
        if not response or not response.text:
            raise ValueError("Empty response from Gemini API")
        return response.text

    async def _call_azure(self, prompt: str) -> str:
        """Call Azure OpenAI API as fallback."""
        if not self.azure_client:
            raise ValueError("Azure OpenAI client not initialized")

        response = await asyncio.to_thread(
            self.azure_client.chat.completions.create,
            model=self.azure_deployment,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.1,
        )

        if not response.choices or not response.choices[0].message.content:
            raise ValueError("Empty response from Azure OpenAI")
        return response.choices[0].message.content

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with Gemini primary and Azure fallback."""
        try:
            return await self._call_gemini(prompt)
        except Exception as e:
            if self.use_azure_fallback and self.azure_client:
                logger.warning(f"Gemini failed, falling back to Azure: {e}")
                return await self._call_azure(prompt)
            raise

    def _extract_json(self, response_text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response."""
        # Try direct parse first
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Look for JSON in markdown code block
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end > start:
                try:
                    return json.loads(response_text[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # Look for any code block
        if "```" in response_text:
            start = response_text.find("```") + 3
            # Skip language identifier if present
            if response_text[start:start+10].strip().isalpha():
                start = response_text.find("\n", start) + 1
            end = response_text.find("```", start)
            if end > start:
                try:
                    return json.loads(response_text[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # Find first { and last }
        first_brace = response_text.find("{")
        last_brace = response_text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(response_text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        logger.error(f"Failed to extract JSON from response: {response_text[:500]}")
        return {}

    # =========================================================================
    # OMOP Mapping Matching
    # =========================================================================

    async def match_atomics_to_mappings(
        self,
        atomics: List[Dict[str, Any]],
        omop_index: Dict[Tuple[str, str], List[Dict[str, Any]]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Use LLM to semantically match each atomic to the best OMOP mapping.

        Args:
            atomics: List of atomic dicts with atomic_id, atomic_text, criterion_id
            omop_index: Index of OMOP mappings by (criterion_id, atomic_id)

        Returns:
            Dict mapping atomic_id to selected OMOP mapping (or None if rejected)
        """
        results: Dict[str, Optional[Dict[str, Any]]] = {}

        # Prepare batches with their candidate mappings
        batches = []
        current_batch = []

        for atomic in atomics:
            atomic_id = atomic.get("atomic_id", "")
            criterion_id = atomic.get("criterion_id", "")
            atomic_text = atomic.get("atomic_text", "")

            # Collect all candidate mappings for this atomic
            candidates = []

            # Try direct key
            key = (criterion_id, atomic_id)
            if key in omop_index:
                candidates.extend(omop_index[key])

            # Try criterion-level key
            key = (criterion_id, criterion_id)
            if key in omop_index:
                candidates.extend(omop_index[key])

            # Try root key
            key = (criterion_id, "root")
            if key in omop_index:
                candidates.extend(omop_index[key])

            if not candidates:
                # No candidates, skip LLM call
                results[atomic_id] = None
                continue

            current_batch.append({
                "atomic_id": atomic_id,
                "atomic_text": atomic_text,
                "candidate_mappings": [
                    {
                        "mapping_id": f"M{i}",
                        "term": m.get("term", ""),
                        "concepts": [
                            {
                                "concept_id": c.get("concept_id"),
                                "concept_name": c.get("concept_name", ""),
                                "domain_id": c.get("domain_id", ""),
                            }
                            for c in m.get("concepts", [])[:5]  # Limit concepts per mapping
                        ]
                    }
                    for i, m in enumerate(candidates[:10])  # Limit candidates
                ],
                "_original_mappings": candidates[:10],  # Keep for result lookup
            })

            if len(current_batch) >= BATCH_SIZE:
                batches.append(current_batch)
                current_batch = []

        if current_batch:
            batches.append(current_batch)

        # Process batches
        for batch in batches:
            batch_results = await self._match_omop_batch(batch)
            results.update(batch_results)

        logger.info(
            f"LLM OMOP matching: {len(atomics)} atomics, "
            f"{sum(1 for v in results.values() if v is not None)} matched"
        )
        return results

    async def _match_omop_batch(
        self,
        batch: List[Dict[str, Any]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Process a batch of atomics for OMOP matching."""
        results: Dict[str, Optional[Dict[str, Any]]] = {}

        # Prepare input for LLM (exclude _original_mappings)
        llm_input = [
            {k: v for k, v in item.items() if not k.startswith("_")}
            for item in batch
        ]

        prompt = self.omop_matching_prompt.replace(
            "{atomic_mappings_json}",
            json.dumps(llm_input, indent=2)
        )

        # Check cache
        cache_key = self._get_cache_key(prompt)
        if self.use_cache and cache_key in self._cache:
            response_data = self._cache[cache_key]
        else:
            response = await self._call_llm(prompt)
            response_data = self._extract_json(response)
            if self.use_cache:
                self._cache[cache_key] = response_data

        matches = response_data.get("matches", {})

        # Build results
        for item in batch:
            atomic_id = item["atomic_id"]
            match_info = matches.get(atomic_id, {})
            selected_id = match_info.get("selected_mapping_id")
            confidence = match_info.get("confidence", 0.0)

            if selected_id and confidence >= CONFIDENCE_THRESHOLD:
                # Find the original mapping
                mapping_idx = int(selected_id.replace("M", ""))
                original_mappings = item.get("_original_mappings", [])
                if 0 <= mapping_idx < len(original_mappings):
                    results[atomic_id] = original_mappings[mapping_idx]
                else:
                    results[atomic_id] = None
            else:
                results[atomic_id] = None

        return results

    # =========================================================================
    # Category Classification
    # =========================================================================

    async def classify_atomics_batch(
        self,
        atomics: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Use LLM to classify atomics into funnel categories.

        Args:
            atomics: List of atomic dicts with atomic_id, atomic_text

        Returns:
            Dict mapping atomic_id to classification dict with category, rationale
        """
        results: Dict[str, Dict[str, Any]] = {}

        # Split into batches
        batches = [
            atomics[i:i + BATCH_SIZE]
            for i in range(0, len(atomics), BATCH_SIZE)
        ]

        for batch in batches:
            batch_results = await self._classify_batch(batch)
            results.update(batch_results)

        logger.info(f"LLM classification: {len(atomics)} atomics classified")
        return results

    async def _classify_batch(
        self,
        batch: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Process a batch of atomics for classification."""
        results: Dict[str, Dict[str, Any]] = {}

        # Prepare input
        llm_input = [
            {
                "atomic_id": item.get("atomic_id", ""),
                "atomic_text": item.get("atomic_text", ""),
                "criterion_type": item.get("criterion_type", "inclusion"),
            }
            for item in batch
        ]

        prompt = self.classification_prompt.replace(
            "{atomics_json}",
            json.dumps(llm_input, indent=2)
        )

        # Check cache
        cache_key = self._get_cache_key(prompt)
        if self.use_cache and cache_key in self._cache:
            response_data = self._cache[cache_key]
        else:
            response = await self._call_llm(prompt)
            response_data = self._extract_json(response)
            if self.use_cache:
                self._cache[cache_key] = response_data

        classifications = response_data.get("classifications", [])

        # Build results
        for item in classifications:
            atomic_id = item.get("atomic_id", "")
            results[atomic_id] = {
                "category": item.get("category", "other"),
                "rationale": item.get("rationale", ""),
            }

        # Default any missing atomics to "other"
        for item in batch:
            atomic_id = item.get("atomic_id", "")
            if atomic_id not in results:
                results[atomic_id] = {
                    "category": "other",
                    "rationale": "Classification not returned by LLM",
                }

        return results

    # =========================================================================
    # Key Criteria Matching
    # =========================================================================

    async def match_atomics_to_key_criteria(
        self,
        atomics: List[Dict[str, Any]],
        key_criteria: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Use LLM to match atomics to key criteria for elimination rate propagation.

        Args:
            atomics: List of atomic dicts with atomic_id, atomic_text
            key_criteria: List of key criteria with key_id, text, elimination_rate, is_killer

        Returns:
            Dict mapping atomic_id to match info with matched_key_id, confidence
        """
        if not key_criteria:
            return {}

        results: Dict[str, Dict[str, Any]] = {}

        # Split into batches
        batches = [
            atomics[i:i + BATCH_SIZE]
            for i in range(0, len(atomics), BATCH_SIZE)
        ]

        for batch in batches:
            batch_results = await self._match_key_criteria_batch(batch, key_criteria)
            results.update(batch_results)

        matched_count = sum(1 for v in results.values() if v.get("matched_key_id"))
        logger.info(
            f"LLM key criteria matching: {len(atomics)} atomics, "
            f"{matched_count} matched to key criteria"
        )
        return results

    async def _match_key_criteria_batch(
        self,
        batch: List[Dict[str, Any]],
        key_criteria: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Process a batch of atomics for key criteria matching."""
        results: Dict[str, Dict[str, Any]] = {}

        # Prepare inputs
        atomics_input = [
            {
                "atomic_id": item.get("atomic_id", ""),
                "atomic_text": item.get("atomic_text", ""),
            }
            for item in batch
        ]

        key_criteria_input = [
            {
                "key_id": kc.get("key_id", ""),
                "text": kc.get("text", kc.get("normalizedText", "")),
                "category": kc.get("category", ""),
                "elimination_rate": kc.get("elimination_rate", 0.0),
                "is_killer": kc.get("is_killer", False),
            }
            for kc in key_criteria
        ]

        prompt = self.key_criteria_prompt.replace(
            "{atomics_json}", json.dumps(atomics_input, indent=2)
        ).replace(
            "{key_criteria_json}", json.dumps(key_criteria_input, indent=2)
        )

        # Check cache
        cache_key = self._get_cache_key(prompt)
        if self.use_cache and cache_key in self._cache:
            response_data = self._cache[cache_key]
        else:
            response = await self._call_llm(prompt)
            response_data = self._extract_json(response)
            if self.use_cache:
                self._cache[cache_key] = response_data

        matches = response_data.get("matches", {})

        # Build results
        for item in batch:
            atomic_id = item.get("atomic_id", "")
            match_info = matches.get(atomic_id, {})

            matched_key_id = match_info.get("matched_key_id")
            confidence = match_info.get("confidence", 0.0)

            if matched_key_id and confidence >= CONFIDENCE_THRESHOLD:
                results[atomic_id] = {
                    "matched_key_id": matched_key_id,
                    "confidence": confidence,
                    "rationale": match_info.get("rationale", ""),
                }
            else:
                results[atomic_id] = {
                    "matched_key_id": None,
                    "confidence": confidence,
                    "rationale": match_info.get("rationale", "No match found"),
                }

        return results

    # =========================================================================
    # Domain Validation
    # =========================================================================

    async def validate_concept_domains_batch(
        self,
        atomics_with_mappings: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, bool]]:
        """
        Use LLM to validate if OMOP concept domains are semantically appropriate.

        This replaces the hardcoded domain_patterns dictionary with LLM reasoning.

        Args:
            atomics_with_mappings: List of dicts with:
                - atomic_id: Unique identifier
                - atomic_text: The criterion text
                - mappings: List of candidate mappings with domain info

        Returns:
            Dict mapping atomic_id -> {mapping_id: is_valid}
        """
        results: Dict[str, Dict[str, bool]] = {}

        # Split into batches
        batches = [
            atomics_with_mappings[i:i + BATCH_SIZE]
            for i in range(0, len(atomics_with_mappings), BATCH_SIZE)
        ]

        for batch in batches:
            batch_results = await self._validate_domains_batch(batch)
            results.update(batch_results)

        valid_count = sum(
            sum(1 for v in mapping_results.values() if v)
            for mapping_results in results.values()
        )
        total_count = sum(len(mapping_results) for mapping_results in results.values())

        logger.info(
            f"LLM domain validation: {len(atomics_with_mappings)} atomics, "
            f"{valid_count}/{total_count} mappings validated"
        )
        return results

    async def _validate_domains_batch(
        self,
        batch: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, bool]]:
        """Process a batch of atomics for domain validation."""
        results: Dict[str, Dict[str, bool]] = {}

        # Prepare input for LLM
        llm_input = []
        for item in batch:
            atomic_id = item.get("atomic_id", "")
            atomic_text = item.get("atomic_text", "")
            mappings = item.get("mappings", [])

            candidate_mappings = []
            for i, mapping in enumerate(mappings[:10]):  # Limit candidates
                # Extract domains from concepts
                concepts = mapping.get("concepts", [])
                domains = list(set(
                    c.get("domain_id", "") for c in concepts if c.get("domain_id")
                ))

                candidate_mappings.append({
                    "mapping_id": f"M{i}",
                    "term": mapping.get("term", ""),
                    "domains": domains,
                })

            llm_input.append({
                "atomic_id": atomic_id,
                "atomic_text": atomic_text,
                "candidate_mappings": candidate_mappings,
            })

        prompt = self.domain_validation_prompt.replace(
            "{atomic_domains_json}",
            json.dumps(llm_input, indent=2)
        )

        # Check cache
        cache_key = self._get_cache_key(prompt)
        if self.use_cache and cache_key in self._cache:
            response_data = self._cache[cache_key]
        else:
            response = await self._call_llm(prompt)
            response_data = self._extract_json(response)
            if self.use_cache:
                self._cache[cache_key] = response_data

        validations = response_data.get("validations", {})

        # Build results
        for item in batch:
            atomic_id = item.get("atomic_id", "")
            mappings = item.get("mappings", [])

            atomic_validations = validations.get(atomic_id, {}).get("mappings", {})
            mapping_results: Dict[str, bool] = {}

            for i, mapping in enumerate(mappings[:10]):
                mapping_id = f"M{i}"
                validation = atomic_validations.get(mapping_id, {})
                is_valid = validation.get("is_valid", True)  # Default to valid if not specified
                mapping_results[mapping_id] = is_valid

            results[atomic_id] = mapping_results

        return results

    async def select_best_omop_mapping_llm(
        self,
        atomic_text: str,
        candidate_mappings: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to select the best OMOP mapping from candidates.

        Combines semantic matching (from match_atomics_to_mappings) with
        domain validation (from validate_concept_domains_batch).

        Args:
            atomic_text: The atomic criterion text
            candidate_mappings: List of candidate OMOP mappings

        Returns:
            Best mapping or None if all rejected
        """
        if not candidate_mappings:
            return None

        if len(candidate_mappings) == 1:
            # For single mapping, just validate domain
            validation = await self.validate_concept_domains_batch([{
                "atomic_id": "single",
                "atomic_text": atomic_text,
                "mappings": candidate_mappings,
            }])

            single_results = validation.get("single", {})
            if single_results.get("M0", True):
                return candidate_mappings[0]
            else:
                logger.debug(f"Single mapping rejected for '{atomic_text[:50]}...'")
                return None

        # For multiple mappings, use OMOP matching to select best
        result = await self.match_atomics_to_mappings(
            atomics=[{
                "atomic_id": "select",
                "criterion_id": "select",
                "atomic_text": atomic_text,
            }],
            omop_index={("select", "select"): candidate_mappings},
        )

        return result.get("select")

    # =========================================================================
    # Semantic Validation (validates concept NAMES match atomic MEANING)
    # =========================================================================

    async def validate_concept_semantics_batch(
        self,
        atomics_with_concepts: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Use LLM to validate if OMOP concept NAMES semantically match atomic text.

        This is DIFFERENT from domain validation:
        - Domain validation: "Is Measurement domain appropriate for this criterion?"
        - Semantic validation: "Does 'Grade Cancer' mean the same as 'neutrophil count'?" → NO

        This validation catches pattern matching artifacts where database LIKE '%term%'
        returns concepts that only match due to substring coincidence (e.g., 'anc' in 'Cancer').

        Args:
            atomics_with_concepts: List of dicts with:
                - atomic_id: Unique identifier
                - atomic_text: The criterion text
                - concepts: List of OMOP concepts with concept_name, domain_id

        Returns:
            Dict mapping atomic_id -> {
                "validations": {mapping_id: is_valid},
                "best_valid_mapping_id": str or None
            }
        """
        results: Dict[str, Dict[str, Any]] = {}

        if not atomics_with_concepts:
            return results

        # Split into batches (performance optimization)
        batches = [
            atomics_with_concepts[i:i + BATCH_SIZE]
            for i in range(0, len(atomics_with_concepts), BATCH_SIZE)
        ]

        for batch in batches:
            batch_results = await self._validate_semantics_batch(batch)
            results.update(batch_results)

        valid_count = sum(
            1 for r in results.values() if r.get("best_valid_mapping_id")
        )
        logger.info(
            f"LLM semantic validation: {len(atomics_with_concepts)} atomics, "
            f"{valid_count} have valid mappings"
        )
        return results

    async def _validate_semantics_batch(
        self,
        batch: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Process a batch of atomics for semantic validation."""
        results: Dict[str, Dict[str, Any]] = {}

        # Prepare input for LLM
        llm_input = []
        for item in batch:
            atomic_id = item.get("atomic_id", "")
            atomic_text = item.get("atomic_text", "")
            concepts = item.get("concepts", [])

            candidate_concepts = []
            for i, concept in enumerate(concepts[:10]):  # Limit to 10 concepts
                candidate_concepts.append({
                    "mapping_id": f"M{i}",
                    "concept_name": concept.get("concept_name", ""),
                    "domain_id": concept.get("domain_id", ""),
                })

            if candidate_concepts:
                llm_input.append({
                    "atomic_id": atomic_id,
                    "atomic_text": atomic_text,
                    "candidate_concepts": candidate_concepts,
                })

        if not llm_input:
            return results

        prompt = self.semantic_validation_prompt.replace(
            "{atomic_concepts_json}",
            json.dumps(llm_input, indent=2)
        )

        # Check cache (performance optimization)
        cache_key = self._get_cache_key(prompt)
        if self.use_cache and cache_key in self._cache:
            response_data = self._cache[cache_key]
            logger.debug(f"Cache hit for semantic validation batch")
        else:
            try:
                response = await self._call_llm(prompt)
                response_data = self._extract_json(response)
                if self.use_cache:
                    self._cache[cache_key] = response_data
            except Exception as e:
                logger.warning(f"LLM semantic validation failed: {e}")
                # Return empty validations - let caller handle as unmapped
                for item in batch:
                    atomic_id = item.get("atomic_id", "")
                    results[atomic_id] = {
                        "validations": {},
                        "best_valid_mapping_id": None,
                    }
                return results

        validations = response_data.get("validations", {})

        # Build results
        for item in batch:
            atomic_id = item.get("atomic_id", "")
            concepts = item.get("concepts", [])

            atomic_validation = validations.get(atomic_id, {})
            concept_validations = atomic_validation.get("concepts", {})
            best_mapping_id = atomic_validation.get("best_valid_mapping_id")

            # Build validation map
            validation_map: Dict[str, bool] = {}
            for i, concept in enumerate(concepts[:10]):
                mapping_id = f"M{i}"
                validation = concept_validations.get(mapping_id, {})
                is_valid = validation.get("is_semantically_valid", False)
                validation_map[mapping_id] = is_valid

            results[atomic_id] = {
                "validations": validation_map,
                "best_valid_mapping_id": best_mapping_id,
            }

        return results
