"""
LLM Reflection Service for Eligibility Analysis.

Implements the generate → validate → reflect → correct pattern for all LLM outputs.
When validation fails, the error is passed back to the LLM for self-correction.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# OMOP schema constants for SQL validation
TABLES_WITH_VALUE_COLUMN = {"measurement", "observation"}
TABLE_CONCEPT_COLUMNS = {
    "condition_occurrence": "condition_concept_id",
    "drug_exposure": "drug_concept_id",
    "measurement": "measurement_concept_id",
    "observation": "observation_concept_id",
    "procedure_occurrence": "procedure_concept_id",
    "device_exposure": "device_concept_id",
    "visit_occurrence": "visit_concept_id",
    "specimen": "specimen_concept_id",
}
DOMAIN_TO_TABLE = {
    "Measurement": "measurement",
    "Condition": "condition_occurrence",
    "Drug": "drug_exposure",
    "Procedure": "procedure_occurrence",
    "Observation": "observation",
    "Device": "device_exposure",
    "Specimen": "specimen",
}


class LLMReflectionService:
    """
    Service for LLM-based reflection and self-correction.

    Pattern:
        1. Generate output (done externally)
        2. Validate against schema/rules
        3. If invalid, reflect error back to LLM
        4. Return corrected output (max 1 retry)
    """

    def __init__(self, model_name: str = None):
        """Initialize with Gemini model."""
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(self.model_name)

        # Load prompts
        self.prompts_dir = Path(__file__).parent.parent / "prompts"
        self._reflection_prompt = self._load_prompt("llm_reflection.txt")

    def _load_prompt(self, filename: str) -> str:
        """Load prompt from file."""
        prompt_path = self.prompts_dir / filename
        if prompt_path.exists():
            return prompt_path.read_text(encoding='utf-8')
        # Return default prompt if file doesn't exist
        return """You are correcting an output that failed validation.

ORIGINAL OUTPUT:
{original_output}

VALIDATION ERROR:
{validation_error}

CONTEXT:
{context}

Provide a corrected output that addresses the validation error.
Return ONLY the corrected value, nothing else."""

    # =========================================================================
    # SQL Validation
    # =========================================================================

    def validate_sql_schema(self, sql: str, table_name: str) -> Optional[str]:
        """
        Validate SQL against OMOP schema constraints.

        Returns error message if invalid, None if valid.
        """
        if not sql or not table_name:
            return None

        sql_lower = sql.lower()

        # Check for value_as_number on tables that don't support it
        if "value_as_number" in sql_lower:
            if table_name not in TABLES_WITH_VALUE_COLUMN:
                return f"Table '{table_name}' does not have a value_as_number column. Only measurement and observation tables support value constraints."

        # Check for value_as_concept_id on tables that don't support it
        if "value_as_concept_id" in sql_lower:
            if table_name not in TABLES_WITH_VALUE_COLUMN:
                return f"Table '{table_name}' does not have a value_as_concept_id column."

        # Check if using correct concept column for table
        expected_column = TABLE_CONCEPT_COLUMNS.get(table_name)
        if expected_column and expected_column not in sql_lower:
            # Check if using wrong concept column
            for other_table, other_column in TABLE_CONCEPT_COLUMNS.items():
                if other_column in sql_lower and other_table != table_name:
                    return f"SQL uses '{other_column}' but table is '{table_name}'. Should use '{expected_column}'."

        return None

    def validate_domain_table(self, domain: str, table_name: str) -> Optional[str]:
        """
        Validate that domain maps to correct table.

        Returns error message if mismatch, None if valid.
        """
        expected_table = DOMAIN_TO_TABLE.get(domain)
        if expected_table and expected_table != table_name:
            return f"Domain '{domain}' should map to table '{expected_table}', not '{table_name}'."
        return None

    # =========================================================================
    # Reflection Methods
    # =========================================================================

    async def reflect_and_correct(
        self,
        original_output: Any,
        validation_error: str,
        context: Dict[str, Any],
    ) -> Tuple[Any, bool]:
        """
        Reflect on a validation error and attempt correction.

        Args:
            original_output: The output that failed validation
            validation_error: Description of what went wrong
            context: Additional context (atomic_text, concept_name, etc.)

        Returns:
            Tuple of (corrected_output, was_corrected)
        """
        try:
            prompt = self._reflection_prompt.format(
                original_output=original_output,
                validation_error=validation_error,
                context=json.dumps(context, indent=2) if isinstance(context, dict) else str(context),
            )

            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=1024,
                )
            )

            corrected = response.text.strip()

            # If response is different from original, consider it corrected
            if corrected and corrected != str(original_output):
                logger.info(f"Reflection corrected output: '{original_output}' -> '{corrected}'")
                return corrected, True

            return original_output, False

        except Exception as e:
            logger.warning(f"Reflection failed: {e}")
            return original_output, False

    async def correct_sql_for_table(
        self,
        sql: str,
        table_name: str,
        atomic_text: str,
        validation_error: str,
    ) -> Tuple[str, bool]:
        """
        Correct SQL that has schema violations.

        Args:
            sql: Original SQL with errors
            table_name: Target OMOP table
            atomic_text: The clinical criterion text
            validation_error: What's wrong with the SQL

        Returns:
            Tuple of (corrected_sql, was_corrected)
        """
        prompt = f"""You are correcting an OMOP CDM SQL query that has a schema violation.

ORIGINAL SQL:
{sql}

ERROR:
{validation_error}

CLINICAL CRITERION:
{atomic_text}

TARGET TABLE:
{table_name}

OMOP SCHEMA RULES:
- Only 'measurement' and 'observation' tables have value_as_number column
- Each table has a specific concept_id column:
  - condition_occurrence: condition_concept_id
  - drug_exposure: drug_concept_id
  - measurement: measurement_concept_id
  - observation: observation_concept_id
  - procedure_occurrence: procedure_concept_id

Provide a corrected SQL query that:
1. Removes any columns that don't exist on the target table
2. Uses the correct concept_id column for the table
3. Preserves the intent of the original query

Return ONLY the corrected SQL, nothing else."""

        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=512,
                )
            )

            corrected_sql = response.text.strip()

            # Clean up any markdown formatting
            if corrected_sql.startswith("```"):
                lines = corrected_sql.split("\n")
                corrected_sql = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            if corrected_sql and corrected_sql != sql:
                logger.info(f"SQL corrected for {table_name}")
                return corrected_sql, True

            return sql, False

        except Exception as e:
            logger.warning(f"SQL correction failed: {e}")
            return sql, False

    async def suggest_alternative_terms(
        self,
        atomic_text: str,
        failed_concepts: List[str],
    ) -> List[str]:
        """
        Suggest alternative search terms for UNMAPPED criteria.

        Args:
            atomic_text: The criterion that couldn't be mapped
            failed_concepts: Concepts that were tried but rejected

        Returns:
            List of alternative terms to try
        """
        prompt = f"""A clinical eligibility criterion could not be mapped to OMOP concepts.

CRITERION:
{atomic_text}

REJECTED CONCEPTS (semantically didn't match):
{', '.join(failed_concepts[:5]) if failed_concepts else 'None'}

Suggest 3 alternative medical/clinical terms that could be used to search for OMOP concepts.
Consider:
- Synonyms
- Related concepts
- Broader or narrower terms
- Standard medical terminology (SNOMED, LOINC, etc.)

Return ONLY a JSON array of strings, like: ["term1", "term2", "term3"]"""

        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=256,
                )
            )

            text = response.text.strip()

            # Parse JSON array
            if text.startswith("["):
                alternatives = json.loads(text)
                if isinstance(alternatives, list):
                    return [str(a) for a in alternatives[:3]]

            return []

        except Exception as e:
            logger.warning(f"Alternative term suggestion failed: {e}")
            return []

    async def infer_omop_table(
        self,
        atomic_text: str,
        domain_hint: Optional[str] = None,
    ) -> str:
        """
        Infer the correct OMOP table for a criterion.

        Args:
            atomic_text: The clinical criterion
            domain_hint: Optional domain hint from upstream

        Returns:
            OMOP table name
        """
        prompt = f"""Determine the correct OMOP CDM table for this clinical eligibility criterion.

CRITERION:
{atomic_text}

{f"DOMAIN HINT: {domain_hint}" if domain_hint else ""}

OMOP TABLES:
- condition_occurrence: Diagnoses, diseases, conditions
- drug_exposure: Medications, drugs, treatments
- measurement: Lab tests, vital signs, quantitative results
- observation: Clinical observations, assessments, scores (ECOG, etc.)
- procedure_occurrence: Medical procedures, surgeries

Return ONLY the table name (one of: condition_occurrence, drug_exposure, measurement, observation, procedure_occurrence)."""

        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=64,
                )
            )

            table = response.text.strip().lower()

            # Validate response
            valid_tables = {"condition_occurrence", "drug_exposure", "measurement", "observation", "procedure_occurrence"}
            if table in valid_tables:
                return table

            # Default to observation for unknown
            return "observation"

        except Exception as e:
            logger.warning(f"Table inference failed: {e}")
            return "observation"

    # =========================================================================
    # LLM-First Classification Methods
    # =========================================================================

    async def classify_criterion_category(
        self,
        atomic_text: str,
    ) -> Tuple[str, float]:
        """
        LLM-first: Classify an atomic criterion into a funnel category.

        Replaces keyword-based _infer_category_fallback with semantic understanding.

        Args:
            atomic_text: The clinical criterion text

        Returns:
            Tuple of (category, confidence)
            Category is one of: demographics, disease_indication, biomarker,
            treatment_history, functional_status, lab_criteria, safety_exclusion, other
        """
        prompt = f"""Classify this clinical trial eligibility criterion into exactly one category.

CRITERION:
{atomic_text}

CATEGORIES:
- demographics: Age, sex, gender, race, ethnicity, geographic criteria
- disease_indication: Cancer type, diagnosis, staging, histology, disease characteristics
- biomarker: Molecular markers, mutations (EGFR, ALK, KRAS), protein expression, genetic testing
- treatment_history: Prior therapies, chemotherapy, radiation, surgery, washout periods
- functional_status: ECOG, Karnofsky, performance status, ability to perform activities
- lab_criteria: Laboratory values (hemoglobin, platelets, creatinine, liver function tests)
- safety_exclusion: Contraindications, allergies, comorbidities, pregnancy, organ dysfunction
- other: Administrative, consent, compliance, protocol requirements

Respond with JSON only:
{{"category": "<category_name>", "confidence": <0.0-1.0>, "reasoning": "<brief explanation>"}}"""

        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=256,
                )
            )

            text = response.text.strip()

            # Parse JSON response
            if text.startswith("{"):
                result = json.loads(text)
                category = result.get("category", "other").lower()
                confidence = float(result.get("confidence", 0.8))

                # Validate category
                valid_categories = {
                    "demographics", "disease_indication", "biomarker",
                    "treatment_history", "functional_status", "lab_criteria",
                    "safety_exclusion", "other"
                }
                if category in valid_categories:
                    logger.debug(f"LLM classified '{atomic_text[:50]}...' as '{category}' (conf={confidence:.2f})")
                    return category, confidence

            logger.warning(f"Invalid category response for '{atomic_text[:50]}...', defaulting to 'other'")
            return "other", 0.5

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse category JSON: {e}")
            return "other", 0.5
        except Exception as e:
            logger.warning(f"Category classification failed: {e}")
            return "other", 0.5

    async def classify_criteria_batch(
        self,
        atomic_texts: List[str],
        batch_size: int = 10,
    ) -> Dict[str, Tuple[str, float]]:
        """
        Classify multiple criteria in batches for efficiency.

        Args:
            atomic_texts: List of criterion texts
            batch_size: Number of criteria per LLM call

        Returns:
            Dict mapping atomic_text to (category, confidence)
        """
        import asyncio

        results = {}

        # Process in parallel batches
        for i in range(0, len(atomic_texts), batch_size):
            batch = atomic_texts[i:i + batch_size]
            tasks = [self.classify_criterion_category(text) for text in batch]
            batch_results = await asyncio.gather(*tasks)

            for text, (category, confidence) in zip(batch, batch_results):
                results[text] = (category, confidence)

        return results

    async def validate_domain_semantic(
        self,
        atomic_text: str,
        concept_name: str,
        domain: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        LLM-first: Validate that a concept's domain semantically matches the criterion.

        Replaces keyword-based _validate_concept_domain_fallback with semantic understanding.

        Args:
            atomic_text: The clinical criterion text
            concept_name: Name of the mapped OMOP concept
            domain: Domain of the OMOP concept (e.g., "Condition", "Measurement")

        Returns:
            Tuple of (is_valid, suggested_domain_if_invalid)
        """
        prompt = f"""Validate whether this OMOP concept correctly matches the clinical criterion.

CRITERION:
{atomic_text}

MAPPED CONCEPT:
- Name: {concept_name}
- Domain: {domain}

OMOP DOMAINS:
- Condition: Diagnoses, diseases, disorders
- Drug: Medications, pharmaceutical products
- Measurement: Lab tests, vital signs with numeric values
- Observation: Clinical observations, assessments, scores
- Procedure: Medical procedures, surgeries

QUESTION: Does the domain "{domain}" correctly represent the clinical meaning of this criterion?

Consider semantic matches:
- "Age >= 18 years" should be Observation (not Drug/Condition)
- "NSCLC diagnosis" should be Condition
- "Hemoglobin >= 9 g/dL" should be Measurement
- "ECOG 0-1" should be Observation (performance score)
- "Prior chemotherapy" should be Drug or Procedure

Respond with JSON only:
{{"is_valid": true/false, "correct_domain": "<domain if invalid>", "reasoning": "<brief explanation>"}}"""

        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=256,
                )
            )

            text = response.text.strip()

            if text.startswith("{"):
                result = json.loads(text)
                is_valid = result.get("is_valid", True)

                if is_valid:
                    return True, None
                else:
                    correct_domain = result.get("correct_domain", domain)
                    logger.info(
                        f"Domain mismatch: '{atomic_text[:40]}...' mapped to {domain}, "
                        f"should be {correct_domain}"
                    )
                    return False, correct_domain

            return True, None  # Default to valid if can't parse

        except Exception as e:
            logger.warning(f"Domain validation failed: {e}")
            return True, None  # Default to valid on error

    async def infer_omop_domain(
        self,
        term: str,
    ) -> Tuple[str, float, str]:
        """
        LLM-first: Infer OMOP domain for a clinical term.

        Replaces keyword-based _infer_domain_fallback with semantic understanding.

        Args:
            term: Clinical term to classify

        Returns:
            Tuple of (domain, confidence, rationale)
        """
        prompt = f"""Determine the correct OMOP CDM domain for this clinical term.

TERM:
{term}

OMOP DOMAINS:
- Condition: Diseases, diagnoses, disorders (e.g., NSCLC, diabetes, hypertension)
- Drug: Medications, drugs, therapies (e.g., pembrolizumab, chemotherapy)
- Measurement: Lab tests with numeric values (e.g., hemoglobin, creatinine, platelet count)
- Observation: Clinical observations, scores, assessments (e.g., ECOG status, age, sex)
- Procedure: Medical procedures (e.g., surgery, biopsy, radiation therapy)

Respond with JSON only:
{{"domain": "<domain>", "confidence": <0.0-1.0>, "rationale": "<brief explanation>"}}"""

        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=256,
                )
            )

            text = response.text.strip()

            if text.startswith("{"):
                result = json.loads(text)
                domain = result.get("domain", "Condition")
                confidence = float(result.get("confidence", 0.8))
                rationale = result.get("rationale", "LLM inference")

                # Validate domain
                valid_domains = {"Condition", "Drug", "Measurement", "Observation", "Procedure", "Device", "Specimen"}
                if domain in valid_domains:
                    return domain, confidence, rationale

            return "Condition", 0.5, "default fallback"

        except Exception as e:
            logger.warning(f"Domain inference failed: {e}")
            return "Condition", 0.5, f"error: {e}"

    async def recover_unmapped_criterion(
        self,
        atomic_text: str,
        failed_concepts: List[Dict[str, Any]],
        search_function,  # Callable to retry OMOP search
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to recover an UNMAPPED criterion using LLM-suggested alternatives.

        Args:
            atomic_text: The criterion that couldn't be mapped
            failed_concepts: Concepts that were tried but rejected
            search_function: Async function to search OMOP (takes term, returns list of concepts)

        Returns:
            Valid mapping dict if recovered, None if still unmapped
        """
        # Step 1: Get alternative search terms
        failed_names = [c.get("concept_name", "") for c in failed_concepts[:5]]
        alternatives = await self.suggest_alternative_terms(atomic_text, failed_names)

        if not alternatives:
            logger.debug(f"No alternative terms suggested for '{atomic_text[:50]}...'")
            return None

        logger.info(f"Trying {len(alternatives)} alternatives for '{atomic_text[:50]}...': {alternatives}")

        # Step 2: Try each alternative
        for alt_term in alternatives:
            try:
                # Search OMOP with alternative term
                concepts = await search_function(alt_term)

                if not concepts:
                    continue

                # Validate the best match semantically
                best = concepts[0]
                is_valid, _ = await self.validate_domain_semantic(
                    atomic_text=atomic_text,
                    concept_name=best.get("concept_name", ""),
                    domain=best.get("domain_id", "Unknown"),
                )

                if is_valid:
                    logger.info(
                        f"Recovered UNMAPPED '{atomic_text[:40]}...' via '{alt_term}' -> "
                        f"{best.get('concept_name')}"
                    )
                    return {
                        "concept_id": best.get("concept_id"),
                        "concept_name": best.get("concept_name"),
                        "domain_id": best.get("domain_id"),
                        "vocabulary_id": best.get("vocabulary_id"),
                        "recovery_term": alt_term,
                        "recovery_method": "llm_alternative",
                    }

            except Exception as e:
                logger.debug(f"Alternative '{alt_term}' search failed: {e}")
                continue

        logger.info(f"Could not recover '{atomic_text[:40]}...' with any alternatives")
        return None
