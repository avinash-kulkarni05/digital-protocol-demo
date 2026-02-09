"""
Criterion Classifier - LLM-based categorization for patient funnel.

This module classifies eligibility criteria into categories (primary_anchor,
biomarker, treatment_history, functional, safety_exclusion, administrative)
and assesses their queryability for EHR-based patient identification.
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from .data_models import (
    CriterionCategory,
    QueryableStatus,
    KeyCriterion,
    OmopMapping,
)

logger = logging.getLogger(__name__)

# LLM configuration
LLM_TIMEOUT_SECONDS = 120
LLM_MAX_RETRIES = 3
DEFAULT_MODEL = "gemini-2.5-pro"
# Max output tokens per model (from CLAUDE.md)
MODEL_MAX_TOKENS = {
    "gemini-2.5-pro": 65536,
    "gemini-2.5-flash": 65536,
    "gemini-2.5-flash-lite": 65536,
    "gemini-2.0-flash-exp": 8192,
    "gemini-1.5-flash": 8192,
    "gemini-1.5-pro": 8192,
}


class CriterionClassifier:
    """
    LLM-based criterion classifier for patient funnel categorization.

    Uses Gemini as primary LLM with Azure OpenAI fallback for classifying
    eligibility criteria into categories and assessing queryability.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        prompts_dir: Optional[Path] = None,
        use_azure_fallback: bool = True,
    ):
        """
        Initialize the criterion classifier.

        Args:
            api_key: Gemini API key. Defaults to GEMINI_API_KEY env var.
            model: Gemini model to use.
            prompts_dir: Directory containing prompt files.
            use_azure_fallback: Whether to fallback to Azure OpenAI on Gemini failure.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model)
        self.model_name = model
        self.max_output_tokens = MODEL_MAX_TOKENS.get(model, 8192)
        self.use_azure_fallback = use_azure_fallback

        # Azure OpenAI configuration (fallback)
        self.azure_client = None
        if use_azure_fallback:
            self._init_azure_client()

        # Load prompt
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent / "prompts"
        self.prompt_template = self._load_prompt(prompts_dir / "criterion_classification.txt")

        logger.info(f"CriterionClassifier initialized with model: {model} (max_tokens: {self.max_output_tokens})")

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

    def _load_prompt(self, prompt_path: Path) -> str:
        """Load prompt template from file."""
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

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
                "temperature": 0.1
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
            max_tokens=8192,
            temperature=0.1,
        )
        if not response.choices or not response.choices[0].message.content:
            raise ValueError("Empty response from Azure OpenAI")
        return response.choices[0].message.content

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with Gemini primary, Azure fallback."""
        try:
            return await self._call_gemini(prompt)
        except Exception as e:
            logger.warning(f"Gemini call failed: {e}")
            if self.use_azure_fallback and self.azure_client:
                logger.info("Falling back to Azure OpenAI")
                return await self._call_azure(prompt)
            raise

    def _prepare_criteria_for_llm(
        self,
        criteria: List[Dict[str, Any]],
        omop_mappings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Prepare criteria for LLM classification.

        Args:
            criteria: List of criterion dictionaries from extraction.
            omop_mappings: Optional OMOP mapping results.

        Returns:
            JSON string for LLM prompt.
        """
        prepared = []
        for c in criteria:
            criterion_id = c.get("criterion_id") or c.get("id") or c.get("criterionId", "")
            criterion_type = c.get("criterion_type") or c.get("type", "inclusion")
            text = (c.get("text") or c.get("criterion_text") or
                    c.get("criterionText") or c.get("originalText", ""))

            item = {
                "criterion_id": criterion_id,
                "criterion_type": criterion_type,
                "text": text,
            }

            # Add OMOP mappings if available
            if omop_mappings and criterion_id in omop_mappings:
                mapping = omop_mappings[criterion_id]
                item["omop_table"] = mapping.get("table_name", "")
                item["omop_concepts"] = mapping.get("concepts", [])

            prepared.append(item)

        return json.dumps(prepared, indent=2)

    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse LLM response into structured classification results.

        Args:
            response: Raw LLM response text.

        Returns:
            List of classification dictionaries.
        """
        # Clean response - remove markdown code blocks if present
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        try:
            results = json.loads(response)
            if not isinstance(results, list):
                raise ValueError("Expected JSON array")
            return results
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Raw response: {response[:500]}...")
            raise ValueError(f"Invalid JSON in LLM response: {e}")

    def _map_category(self, category_str: str) -> CriterionCategory:
        """Map string category to enum."""
        mapping = {
            "primary_anchor": CriterionCategory.PRIMARY_ANCHOR,
            "biomarker": CriterionCategory.BIOMARKER,
            "treatment_history": CriterionCategory.TREATMENT_HISTORY,
            "functional": CriterionCategory.FUNCTIONAL,
            "safety_exclusion": CriterionCategory.SAFETY_EXCLUSION,
            "administrative": CriterionCategory.ADMINISTRATIVE,
        }
        result = mapping.get(category_str.lower())
        if result is None:
            # Log unknown category - don't silently default
            logger.warning(
                f"Unknown category '{category_str}' from LLM - defaulting to ADMINISTRATIVE. "
                f"Consider adding this category to the mapping or investigating LLM prompt."
            )
            return CriterionCategory.ADMINISTRATIVE
        return result

    def _map_queryable_status(self, status_str: str) -> QueryableStatus:
        """Map string status to enum."""
        mapping = {
            "fully_queryable": QueryableStatus.FULLY_QUERYABLE,
            "partially_queryable": QueryableStatus.PARTIALLY_QUERYABLE,
            "non_queryable": QueryableStatus.NON_QUERYABLE,
            "reference_based": QueryableStatus.REFERENCE_BASED,
        }
        return mapping.get(status_str.lower(), QueryableStatus.NON_QUERYABLE)

    def _build_key_criterion(
        self,
        classification: Dict[str, Any],
        original_criterion: Dict[str, Any],
        key_id: str,
        omop_mappings: Optional[Dict[str, Any]] = None,
    ) -> KeyCriterion:
        """
        Build KeyCriterion from classification result.

        Args:
            classification: LLM classification result.
            original_criterion: Original criterion data.
            key_id: Unique key criterion ID.
            omop_mappings: Optional OMOP mappings.

        Returns:
            KeyCriterion instance.
        """
        criterion_id = (original_criterion.get("criterion_id") or
                        original_criterion.get("id") or
                        original_criterion.get("criterionId", ""))
        text = (original_criterion.get("text") or
                original_criterion.get("criterion_text") or
                original_criterion.get("originalText", ""))
        criterion_type = original_criterion.get("criterion_type") or original_criterion.get("type", "inclusion")

        # Build OMOP mappings if available
        omop_mapping_list = []
        if omop_mappings and criterion_id in omop_mappings:
            mapping_data = omop_mappings[criterion_id]
            for concept in mapping_data.get("concepts", []):
                omop_mapping_list.append(OmopMapping(
                    concept_id=concept.get("concept_id", 0),
                    concept_name=concept.get("concept_name", ""),
                    vocabulary_id=concept.get("vocabulary_id", ""),
                    domain_id=concept.get("domain_id", ""),
                    table_name=mapping_data.get("table_name", ""),
                    is_standard=concept.get("standard_concept") == "S",
                ))

        return KeyCriterion(
            key_id=key_id,
            original_criterion_ids=[criterion_id],
            category=self._map_category(classification.get("category", "administrative")),
            normalized_text=text,
            criterion_type=criterion_type,
            queryable_status=self._map_queryable_status(
                classification.get("queryable_status", "non_queryable")
            ),
            estimated_elimination_rate=classification.get("estimated_elimination_rate", 0.0),
            requires_manual_assessment=classification.get("requires_manual_assessment", False),
            funnel_priority=classification.get("funnel_priority", 99),
            source_text=text,
            omop_mappings=omop_mapping_list,
            data_availability_score=1.0 if omop_mapping_list else 0.0,
        )

    async def classify_criteria(
        self,
        criteria: List[Dict[str, Any]],
        omop_mappings: Optional[Dict[str, Any]] = None,
        batch_size: int = 20,
    ) -> Tuple[List[KeyCriterion], Dict[str, Any]]:
        """
        Classify criteria into categories for patient funnel.

        Args:
            criteria: List of criterion dictionaries from extraction.
            omop_mappings: Optional OMOP mapping results (keyed by criterion_id).
            batch_size: Number of criteria to process per LLM call.

        Returns:
            Tuple of (list of KeyCriterion, classification metadata).
        """
        logger.info(f"Classifying {len(criteria)} criteria into funnel categories")

        key_criteria = []
        all_classifications = []
        key_counter = 1

        # Process in batches
        for i in range(0, len(criteria), batch_size):
            batch = criteria[i:i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1} ({len(batch)} criteria)")

            # Prepare prompt
            criteria_json = self._prepare_criteria_for_llm(batch, omop_mappings)
            prompt = self.prompt_template.format(criteria_json=criteria_json)

            try:
                # Call LLM
                response = await self._call_llm(prompt)
                classifications = self._parse_llm_response(response)
                all_classifications.extend(classifications)

                # Build KeyCriterion objects
                for j, classification in enumerate(classifications):
                    if j < len(batch):
                        key_id = f"KC{key_counter:03d}"
                        key_criterion = self._build_key_criterion(
                            classification=classification,
                            original_criterion=batch[j],
                            key_id=key_id,
                            omop_mappings=omop_mappings,
                        )
                        key_criteria.append(key_criterion)
                        key_counter += 1

            except Exception as e:
                logger.error(f"Error classifying batch: {e}")
                # Create fallback classifications for failed batch
                for criterion in batch:
                    key_id = f"KC{key_counter:03d}"
                    crit_id = (criterion.get("criterion_id") or
                               criterion.get("id") or
                               criterion.get("criterionId", ""))
                    crit_text = (criterion.get("text") or
                                 criterion.get("criterion_text") or
                                 criterion.get("originalText", ""))
                    crit_type = (criterion.get("criterion_type") or
                                 criterion.get("type", "inclusion"))
                    key_criteria.append(KeyCriterion(
                        key_id=key_id,
                        original_criterion_ids=[crit_id],
                        category=CriterionCategory.ADMINISTRATIVE,
                        normalized_text=crit_text,
                        criterion_type=crit_type,
                        queryable_status=QueryableStatus.NON_QUERYABLE,
                        estimated_elimination_rate=0.0,
                        requires_manual_assessment=True,
                        funnel_priority=99,
                    ))
                    key_counter += 1

        # Calculate category distribution
        category_counts = {}
        queryable_counts = {}
        for kc in key_criteria:
            cat = kc.category.value
            qs = kc.queryable_status.value
            category_counts[cat] = category_counts.get(cat, 0) + 1
            queryable_counts[qs] = queryable_counts.get(qs, 0) + 1

        metadata = {
            "total_criteria": len(criteria),
            "key_criteria_generated": len(key_criteria),
            "category_distribution": category_counts,
            "queryability_distribution": queryable_counts,
            "model_used": self.model_name,
        }

        logger.info(f"Classification complete: {len(key_criteria)} key criteria generated")
        logger.info(f"Category distribution: {category_counts}")
        logger.info(f"Queryability distribution: {queryable_counts}")

        return key_criteria, metadata

    def classify_criteria_sync(
        self,
        criteria: List[Dict[str, Any]],
        omop_mappings: Optional[Dict[str, Any]] = None,
        batch_size: int = 20,
    ) -> Tuple[List[KeyCriterion], Dict[str, Any]]:
        """Synchronous wrapper for classify_criteria."""
        return asyncio.run(self.classify_criteria(criteria, omop_mappings, batch_size))


def load_criteria_from_extraction(
    eligibility_json_path: Path,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Load criteria from eligibility extraction output.

    Args:
        eligibility_json_path: Path to eligibility_criteria.json file.

    Returns:
        Tuple of (criteria list, omop_mappings dict or None).
    """
    if not eligibility_json_path.exists():
        raise FileNotFoundError(f"Eligibility file not found: {eligibility_json_path}")

    with open(eligibility_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Extract criteria
    criteria = data.get("criteria", [])
    if not criteria:
        # Try alternate structure
        criteria = data.get("inclusionCriteria", []) + data.get("exclusionCriteria", [])

    # Look for OMOP mappings file
    omop_path = eligibility_json_path.parent / eligibility_json_path.name.replace(
        "eligibility_criteria.json", "omop_mappings.json"
    )
    omop_mappings = None
    if omop_path.exists():
        with open(omop_path, "r", encoding="utf-8") as f:
            omop_data = json.load(f)
        # Convert to dict keyed by criterion_id
        if "mappings" in omop_data:
            omop_mappings = {
                m.get("criterion_id"): m for m in omop_data["mappings"]
            }

    return criteria, omop_mappings
