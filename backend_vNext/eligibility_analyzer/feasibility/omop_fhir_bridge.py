"""
OMOP to FHIR Bridge Module.

Translates OMOP CDM concepts to FHIR R4 queries by:
1. Looking up SNOMED/LOINC/RxNorm codes from OMOP concept_ids via concept_relationship
2. Mapping OMOP domains to FHIR resource types
3. Generating FHIR search parameters from OMOP query specifications

This enables the Patient Funnel to be executed against both OMOP CDM databases
and FHIR R4 servers using the same atomic criteria definitions.
"""

import sqlite3
import os
import re
import json
import asyncio
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta

import google.generativeai as genai
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Prompt file path
TEMPORAL_PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "temporal_expression_parsing.txt"


# ============================================================================
# OMOP Domain → FHIR Resource Type Mapping
# ============================================================================

OMOP_DOMAIN_TO_FHIR_RESOURCE: Dict[str, str] = {
    # Core clinical domains
    "Condition": "Condition",
    "Drug": "MedicationRequest",
    "Drug Exposure": "MedicationRequest",
    "Procedure": "Procedure",
    "Measurement": "Observation",
    "Observation": "Observation",
    "Device": "Device",
    "Visit": "Encounter",
    "Specimen": "Specimen",

    # Demographics
    "Gender": "Patient",
    "Race": "Patient",
    "Ethnicity": "Patient",
    "Person": "Patient",

    # Provider/Location
    "Provider": "Practitioner",
    "Place of Service": "Location",

    # Payer
    "Payer": "Coverage",

    # Notes
    "Note": "DocumentReference",

    # Metadata (fallback)
    "Metadata": "Basic",
    "Type Concept": "Basic",
}

# FHIR Code Systems by Vocabulary
VOCABULARY_TO_FHIR_SYSTEM: Dict[str, str] = {
    "SNOMED": "http://snomed.info/sct",
    "LOINC": "http://loinc.org",
    "RxNorm": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "RxNorm Extension": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "ICD10CM": "http://hl7.org/fhir/sid/icd-10-cm",
    "ICD10PCS": "http://www.cms.gov/Medicare/Coding/ICD10",
    "ICD9CM": "http://hl7.org/fhir/sid/icd-9-cm",
    "CPT4": "http://www.ama-assn.org/go/cpt",
    "HCPCS": "http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets",
    "NDC": "http://hl7.org/fhir/sid/ndc",
    "CVX": "http://hl7.org/fhir/sid/cvx",
    "NCIt_Full": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
    "CDISC": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
}

# Preferred vocabularies for FHIR mapping (in priority order)
PREFERRED_FHIR_VOCABULARIES = ["SNOMED", "LOINC", "RxNorm", "ICD10CM", "CPT4"]


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class FhirCode:
    """A single FHIR code with system and display."""
    system: str
    code: str
    display: str

    def to_dict(self) -> Dict:
        return {
            "system": self.system,
            "code": self.code,
            "display": self.display
        }


@dataclass
class FhirQuerySpec:
    """FHIR R4 query specification."""
    resource_type: str
    codes: List[FhirCode]
    search_params: str
    query_executable: bool = True
    value_filter: Optional[str] = None  # For numeric/comparator filters
    date_filter: Optional[str] = None   # For temporal filters

    def to_dict(self) -> Dict:
        return {
            "resourceType": self.resource_type,
            "codes": [c.to_dict() for c in self.codes],
            "searchParams": self.search_params,
            "queryExecutable": self.query_executable,
            "valueFilter": self.value_filter,
            "dateFilter": self.date_filter,
        }


@dataclass
class OmopToFhirMapping:
    """Result of mapping an OMOP concept to FHIR."""
    omop_concept_id: int
    omop_concept_name: str
    omop_vocabulary_id: str
    omop_domain_id: str
    fhir_resource_type: str
    fhir_codes: List[FhirCode] = field(default_factory=list)
    mapping_confidence: float = 1.0
    mapping_notes: List[str] = field(default_factory=list)


# ============================================================================
# OMOP to FHIR Bridge Service
# ============================================================================

class OmopFhirBridge:
    """
    Service for translating OMOP concepts to FHIR queries.

    Uses the ATHENA database to:
    1. Look up concept details by concept_id
    2. Find equivalent codes in FHIR-compatible vocabularies (SNOMED, LOINC, RxNorm)
    3. Generate FHIR search parameters
    """

    # Use relative path from this file's location to backend_vNext/athena_concepts_full.db
    DEFAULT_DB_PATH = str(Path(__file__).parent.parent.parent / "athena_concepts_full.db")

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the bridge.

        Args:
            db_path: Path to ATHENA SQLite database. Defaults to env var or standard location.
        """
        self.db_path = db_path or os.environ.get('ATHENA_DB_PATH', self.DEFAULT_DB_PATH)
        if not Path(self.db_path).exists():
            logger.warning(f"ATHENA database not found: {self.db_path}")
            self._conn = None
        else:
            self._conn = None

    def _get_connection(self) -> Optional[sqlite3.Connection]:
        """Get or create database connection."""
        if not Path(self.db_path).exists():
            return None
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def get_concept(self, concept_id: int) -> Optional[Dict]:
        """
        Look up an OMOP concept by ID.

        Args:
            concept_id: OMOP concept_id

        Returns:
            Concept details dict or None
        """
        conn = self._get_connection()
        if not conn:
            return None

        cursor = conn.cursor()
        cursor.execute("""
            SELECT concept_id, concept_name, domain_id, vocabulary_id,
                   concept_class_id, standard_concept, concept_code
            FROM concept
            WHERE concept_id = ?
        """, (concept_id,))

        row = cursor.fetchone()
        if row:
            return {
                "concept_id": row["concept_id"],
                "concept_name": row["concept_name"],
                "domain_id": row["domain_id"],
                "vocabulary_id": row["vocabulary_id"],
                "concept_class_id": row["concept_class_id"],
                "standard_concept": row["standard_concept"],
                "concept_code": row["concept_code"],
            }
        return None

    def get_fhir_equivalent_codes(self, concept_id: int) -> List[FhirCode]:
        """
        Find FHIR-compatible codes (SNOMED, LOINC, RxNorm) for an OMOP concept.

        Uses concept_relationship table with 'Maps to' relationship to find
        equivalent codes in FHIR-friendly vocabularies.

        Args:
            concept_id: OMOP concept_id

        Returns:
            List of FhirCode objects
        """
        conn = self._get_connection()
        if not conn:
            return []

        fhir_codes: List[FhirCode] = []

        # First, check if the concept itself is in a FHIR-compatible vocabulary
        source_concept = self.get_concept(concept_id)
        if source_concept:
            vocab = source_concept["vocabulary_id"]
            if vocab in VOCABULARY_TO_FHIR_SYSTEM:
                fhir_codes.append(FhirCode(
                    system=VOCABULARY_TO_FHIR_SYSTEM[vocab],
                    code=source_concept["concept_code"],
                    display=source_concept["concept_name"]
                ))

        # Look for mappings to FHIR-compatible vocabularies
        cursor = conn.cursor()

        for vocab in PREFERRED_FHIR_VOCABULARIES:
            cursor.execute("""
                SELECT c.concept_id, c.concept_code, c.concept_name, c.vocabulary_id
                FROM concept_relationship cr
                JOIN concept c ON cr.concept_id_2 = c.concept_id
                WHERE cr.concept_id_1 = ?
                  AND cr.relationship_id = 'Maps to'
                  AND c.vocabulary_id = ?
                  AND c.standard_concept = 'S'
                  AND c.invalid_reason IS NULL
                LIMIT 5
            """, (concept_id, vocab))

            for row in cursor.fetchall():
                # Avoid duplicates
                existing_codes = {(c.system, c.code) for c in fhir_codes}
                system = VOCABULARY_TO_FHIR_SYSTEM.get(row["vocabulary_id"], "")
                if system and (system, row["concept_code"]) not in existing_codes:
                    fhir_codes.append(FhirCode(
                        system=system,
                        code=row["concept_code"],
                        display=row["concept_name"]
                    ))

        # Also check 'Mapped from' relationship (reverse mapping)
        if not fhir_codes:
            for vocab in PREFERRED_FHIR_VOCABULARIES:
                cursor.execute("""
                    SELECT c.concept_id, c.concept_code, c.concept_name, c.vocabulary_id
                    FROM concept_relationship cr
                    JOIN concept c ON cr.concept_id_1 = c.concept_id
                    WHERE cr.concept_id_2 = ?
                      AND cr.relationship_id = 'Mapped from'
                      AND c.vocabulary_id = ?
                      AND c.standard_concept = 'S'
                      AND c.invalid_reason IS NULL
                    LIMIT 5
                """, (concept_id, vocab))

                for row in cursor.fetchall():
                    existing_codes = {(c.system, c.code) for c in fhir_codes}
                    system = VOCABULARY_TO_FHIR_SYSTEM.get(row["vocabulary_id"], "")
                    if system and (system, row["concept_code"]) not in existing_codes:
                        fhir_codes.append(FhirCode(
                            system=system,
                            code=row["concept_code"],
                            display=row["concept_name"]
                        ))

        return fhir_codes

    def map_domain_to_fhir_resource(self, domain_id: str) -> str:
        """
        Map OMOP domain to FHIR resource type.

        Args:
            domain_id: OMOP domain_id

        Returns:
            FHIR resource type string
        """
        return OMOP_DOMAIN_TO_FHIR_RESOURCE.get(domain_id, "Observation")

    def map_omop_to_fhir(
        self,
        concept_ids: List[int],
        omop_table: Optional[str] = None,
        value_comparator: Optional[str] = None,
        value_numeric: Optional[float] = None,
        temporal_filter: Optional[str] = None
    ) -> Optional[FhirQuerySpec]:
        """
        Convert OMOP concept(s) to a FHIR query specification.

        Args:
            concept_ids: List of OMOP concept_ids
            omop_table: OMOP table name (helps determine resource type)
            value_comparator: Comparator for numeric values (>=, <=, >, <, =)
            value_numeric: Numeric value for comparison
            temporal_filter: Temporal filter (e.g., "within 12 months")

        Returns:
            FhirQuerySpec or None if mapping fails
        """
        if not concept_ids:
            return None

        # Collect all FHIR codes from all concept_ids
        all_fhir_codes: List[FhirCode] = []
        domain_ids: set = set()

        for cid in concept_ids:
            concept = self.get_concept(cid)
            if concept:
                domain_ids.add(concept["domain_id"])

            codes = self.get_fhir_equivalent_codes(cid)
            for code in codes:
                # Avoid duplicates
                if not any(c.system == code.system and c.code == code.code for c in all_fhir_codes):
                    all_fhir_codes.append(code)

        if not all_fhir_codes:
            logger.warning(f"No FHIR codes found for concept_ids: {concept_ids}")
            return FhirQuerySpec(
                resource_type=self._infer_resource_from_table(omop_table) or "Observation",
                codes=[],
                search_params="",
                query_executable=False
            )

        # Determine FHIR resource type
        resource_type = None
        if omop_table:
            resource_type = self._infer_resource_from_table(omop_table)

        if not resource_type and domain_ids:
            # Use most common domain
            for domain in domain_ids:
                resource_type = self.map_domain_to_fhir_resource(domain)
                if resource_type:
                    break

        if not resource_type:
            resource_type = "Observation"

        # Build search parameters
        search_params = self._build_search_params(
            resource_type=resource_type,
            codes=all_fhir_codes,
            value_comparator=value_comparator,
            value_numeric=value_numeric,
            temporal_filter=temporal_filter
        )

        # Build value filter string
        value_filter = None
        if value_comparator and value_numeric is not None:
            value_filter = f"{value_comparator}{value_numeric}"

        return FhirQuerySpec(
            resource_type=resource_type,
            codes=all_fhir_codes,
            search_params=search_params,
            query_executable=True,
            value_filter=value_filter,
            date_filter=temporal_filter
        )

    def _infer_resource_from_table(self, table_name: Optional[str]) -> Optional[str]:
        """Infer FHIR resource type from OMOP table name."""
        if not table_name:
            return None

        table_to_resource = {
            "condition_occurrence": "Condition",
            "drug_exposure": "MedicationRequest",
            "procedure_occurrence": "Procedure",
            "measurement": "Observation",
            "observation": "Observation",
            "device_exposure": "Device",
            "visit_occurrence": "Encounter",
            "specimen": "Specimen",
            "person": "Patient",
            "death": "Patient",
            "note": "DocumentReference",
        }
        return table_to_resource.get(table_name.lower())

    def _build_search_params(
        self,
        resource_type: str,
        codes: List[FhirCode],
        value_comparator: Optional[str] = None,
        value_numeric: Optional[float] = None,
        temporal_filter: Optional[str] = None
    ) -> str:
        """
        Build FHIR search parameter string.

        Args:
            resource_type: FHIR resource type
            codes: List of FHIR codes to search for
            value_comparator: Comparator for numeric values
            value_numeric: Numeric value for comparison
            temporal_filter: Temporal filter string

        Returns:
            FHIR search parameter string (e.g., "code=http://snomed.info/sct|12345")
        """
        params: List[str] = []

        # Determine the code parameter name based on resource type
        code_param = self._get_code_param_name(resource_type)

        # Build code search parameter
        if codes:
            code_parts = []
            for code in codes:
                code_parts.append(f"{code.system}|{code.code}")

            # Use comma for OR within codes
            params.append(f"{code_param}={','.join(code_parts)}")

        # Add value filter for Observation
        if resource_type == "Observation" and value_comparator and value_numeric is not None:
            fhir_prefix = self._convert_comparator_to_fhir(value_comparator)
            params.append(f"value-quantity={fhir_prefix}{value_numeric}")

        # Add date filter if provided (using fallback for sync compatibility)
        if temporal_filter:
            date_param = self._parse_temporal_filter_fallback(resource_type, temporal_filter)
            if date_param:
                params.append(date_param)

        return "&".join(params)

    def _get_code_param_name(self, resource_type: str) -> str:
        """Get the appropriate code search parameter name for a resource type."""
        code_params = {
            "Condition": "code",
            "MedicationRequest": "code",
            "Procedure": "code",
            "Observation": "code",
            "Device": "type",
            "Encounter": "type",
            "Specimen": "type",
            "Patient": "identifier",  # Usually not queried by code
            "DocumentReference": "type",
        }
        return code_params.get(resource_type, "code")

    def _convert_comparator_to_fhir(self, comparator: str) -> str:
        """Convert SQL comparator to FHIR prefix."""
        mapping = {
            ">=": "ge",
            ">": "gt",
            "<=": "le",
            "<": "lt",
            "=": "eq",
            "==": "eq",
            "!=": "ne",
            "<>": "ne",
        }
        return mapping.get(comparator, "eq")

    def _parse_temporal_filter_fallback(
        self,
        resource_type: str,
        temporal_filter: str
    ) -> Optional[str]:
        """
        FALLBACK: Parse a temporal filter string into FHIR date search parameter.

        Examples:
            "within 12 months" -> "date=ge2024-12-13"
            "past 30 days" -> "date=ge2024-11-13"
            "last 6 months" -> "date=ge2024-06-13"
        """
        # Get the date parameter name for the resource
        date_params = {
            "Condition": "onset-date",
            "MedicationRequest": "authoredon",
            "Procedure": "date",
            "Observation": "date",
            "Encounter": "date",
        }
        date_param = date_params.get(resource_type, "date")

        # Parse common temporal patterns
        temporal_filter_lower = temporal_filter.lower()

        # Extended patterns: "within|past|last|prior|preceding X months/years/days/weeks"
        match = re.search(
            r'(?:within|past|last|prior|preceding)\s+(\d+)\s+(month|year|day|week)s?',
            temporal_filter_lower
        )
        if match:
            value = int(match.group(1))
            unit = match.group(2)

            today = datetime.now()
            if unit == "month":
                ref_date = today - timedelta(days=value * 30)
            elif unit == "year":
                ref_date = today - timedelta(days=value * 365)
            elif unit == "week":
                ref_date = today - timedelta(weeks=value)
            else:  # day
                ref_date = today - timedelta(days=value)

            return f"{date_param}=ge{ref_date.strftime('%Y-%m-%d')}"

        return None

    def generate_fhir_from_omop_sql(
        self,
        sql_template: str,
        concept_ids: List[int]
    ) -> Optional[FhirQuerySpec]:
        """
        Generate FHIR query from an OMOP SQL template.

        Parses the SQL to extract:
        - Table name (maps to resource type)
        - Concept IDs (maps to FHIR codes)
        - Value comparisons (maps to value-quantity)
        - Date filters (maps to date parameters)

        Args:
            sql_template: OMOP CDM SQL template
            concept_ids: List of concept_ids used in the query

        Returns:
            FhirQuerySpec or None
        """
        import re

        # Extract table name
        table_match = re.search(r'FROM\s+(\w+)', sql_template, re.IGNORECASE)
        omop_table = table_match.group(1) if table_match else None

        # Extract value comparison
        value_comparator = None
        value_numeric = None
        value_match = re.search(
            r'value_as_number\s*(>=|<=|>|<|=)\s*(\d+(?:\.\d+)?)',
            sql_template,
            re.IGNORECASE
        )
        if value_match:
            value_comparator = value_match.group(1)
            value_numeric = float(value_match.group(2))

        # Extract temporal filter
        temporal_filter = None
        date_match = re.search(
            r"(condition_start_date|drug_exposure_start_date|procedure_date|measurement_date|observation_date)\s*(>=|<=|>|<)\s*@?\w+\s*-\s*INTERVAL\s*'(\d+)\s*(\w+)'",
            sql_template,
            re.IGNORECASE
        )
        if date_match:
            interval_value = date_match.group(3)
            interval_unit = date_match.group(4).lower()
            temporal_filter = f"within {interval_value} {interval_unit}"

        return self.map_omop_to_fhir(
            concept_ids=concept_ids,
            omop_table=omop_table,
            value_comparator=value_comparator,
            value_numeric=value_numeric,
            temporal_filter=temporal_filter
        )

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()


# ============================================================================
# LLM Temporal Parser (Async)
# ============================================================================

class LLMTemporalParser:
    """
    LLM-based temporal expression parser for eligibility criteria.

    Uses Gemini (with Azure fallback) to semantically parse complex temporal
    expressions that simple regex patterns cannot handle.
    """

    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 2.0

    def __init__(self):
        """Initialize the temporal parser."""
        self._prompt_template = self._load_prompt_template()
        self._model = None
        self._azure_client: Optional[AzureOpenAI] = None
        self._azure_deployment: Optional[str] = None

    def _load_prompt_template(self) -> Optional[str]:
        """Load the temporal parsing prompt."""
        if not TEMPORAL_PROMPT_FILE.exists():
            logger.warning(f"Temporal prompt not found: {TEMPORAL_PROMPT_FILE}")
            return None

        with open(TEMPORAL_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()

    def _get_model(self):
        """Lazy-load the Gemini model."""
        if self._model is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel("gemini-2.5-flash")
        return self._model

    def _init_azure_fallback(self) -> None:
        """Initialize Azure OpenAI client for fallback."""
        if self._azure_client is not None:
            return

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
                logger.debug("Azure OpenAI fallback initialized for temporal parsing")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure OpenAI fallback: {e}")

    async def parse_temporal_expressions_batch_llm(
        self,
        expressions: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Use LLM to parse temporal expressions from eligibility criteria.

        Handles complex patterns like:
        - "within 6 months of screening"
        - "prior to baseline"
        - "last 30 days"
        - "recent" (interpreted as ~3 months)

        Args:
            expressions: List of temporal expressions to parse

        Returns:
            Dict mapping expression to parsed result
        """
        if not expressions:
            return {}

        if not self._prompt_template:
            logger.warning("Temporal prompt not loaded, using fallback")
            return {expr: self._parse_fallback(expr) for expr in expressions}

        try:
            return await self._parse_with_llm(expressions)
        except Exception as e:
            logger.error(f"LLM temporal parsing failed: {e}. Using fallback.")
            return {expr: self._parse_fallback(expr) for expr in expressions}

    async def _parse_with_llm(
        self,
        expressions: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Call LLM for temporal parsing with retry logic."""
        # Build prompt
        expressions_json = json.dumps(expressions, indent=2)
        prompt = self._prompt_template.replace("{temporal_expressions_json}", expressions_json)
        prompt = prompt.replace("{expression_count}", str(len(expressions)))

        model = self._get_model()
        if not model:
            raise RuntimeError("Gemini model not available")

        # Retry with exponential backoff
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await asyncio.to_thread(
                    model.generate_content,
                    prompt,
                    generation_config=genai.GenerationConfig(
                        max_output_tokens=8192,
                        temperature=0.1,
                        response_mime_type="application/json",
                    ),
                )

                response_text = self._extract_response_text(response)
                if not response_text:
                    logger.warning(f"Empty response on attempt {attempt + 1}")
                    if attempt < self.MAX_RETRIES - 1:
                        delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue

                return self._parse_llm_response(response_text, expressions)

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                retryable = any(p in error_str for p in ["503", "429", "timeout", "rate limit"])
                if retryable:
                    delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f"LLM attempt {attempt + 1}/{self.MAX_RETRIES} failed: {e}. Retrying...")
                    await asyncio.sleep(delay)
                else:
                    raise

        # Try Azure fallback
        logger.warning("Gemini failed. Trying Azure OpenAI fallback...")
        self._init_azure_fallback()
        azure_result = await self._call_azure_fallback(prompt, expressions)
        if azure_result is not None:
            return azure_result

        raise last_error or RuntimeError("Temporal parsing failed after all retries")

    async def _call_azure_fallback(
        self,
        prompt: str,
        expressions: List[str]
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """Call Azure OpenAI as fallback."""
        if not self._azure_client or not self._azure_deployment:
            return None

        try:
            response = await asyncio.to_thread(
                self._azure_client.chat.completions.create,
                model=self._azure_deployment,
                messages=[
                    {"role": "system", "content": "You are a clinical trial protocol expert. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=8192,
                response_format={"type": "json_object"}
            )

            if response and response.choices:
                content = response.choices[0].message.content
                if content:
                    logger.info("Azure OpenAI temporal parsing succeeded")
                    return self._parse_llm_response(content, expressions)

        except Exception as e:
            logger.error(f"Azure OpenAI temporal parsing failed: {e}")

        return None

    def _extract_response_text(self, response) -> Optional[str]:
        """Extract text from Gemini response."""
        try:
            if hasattr(response, 'text') and response.text:
                return response.text.strip()

            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    if hasattr(candidate.content, 'parts') and candidate.content.parts:
                        texts = [p.text for p in candidate.content.parts if hasattr(p, 'text') and p.text]
                        if texts:
                            return "\n".join(texts).strip()

            return None
        except Exception as e:
            logger.error(f"Error extracting response text: {e}")
            return None

    def _parse_llm_response(
        self,
        response_text: Optional[str],
        original_expressions: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Parse LLM response for temporal parsing."""
        results: Dict[str, Dict[str, Any]] = {}

        if not response_text or not response_text.strip():
            logger.error("Empty temporal parsing response")
            for expr in original_expressions:
                results[expr] = self._parse_fallback(expr)
            return results

        try:
            # Extract JSON from response
            json_str = self._extract_json_from_response(response_text)
            if not json_str:
                for expr in original_expressions:
                    results[expr] = self._parse_fallback(expr)
                return results

            parsed = json.loads(json_str)

            # Handle nested "results" key
            if isinstance(parsed, dict) and "results" in parsed:
                parsed = parsed["results"]

            if not isinstance(parsed, dict):
                for expr in original_expressions:
                    results[expr] = self._parse_fallback(expr)
                return results

            for expr in original_expressions:
                if expr in parsed:
                    results[expr] = parsed[expr]
                else:
                    # Case-insensitive match
                    expr_lower = expr.lower()
                    found = False
                    for key, value in parsed.items():
                        if key.lower() == expr_lower:
                            results[expr] = value
                            found = True
                            break
                    if not found:
                        results[expr] = self._parse_fallback(expr)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse temporal LLM response: {e}")
            for expr in original_expressions:
                results[expr] = self._parse_fallback(expr)

        return results

    def _extract_json_from_response(self, response_text: str) -> Optional[str]:
        """Extract JSON from LLM response."""
        # Try code block
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text)
        if json_match:
            return json_match.group(1).strip()

        code_match = re.search(r"```\s*([\s\S]*?)\s*```", response_text)
        if code_match:
            content = code_match.group(1).strip()
            if content.startswith(('json\n', 'JSON\n')):
                content = content[5:]
            return content

        # Raw JSON
        stripped = response_text.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            return stripped

        # Find braces
        first_brace = response_text.find('{')
        last_brace = response_text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return response_text[first_brace:last_brace + 1]

        return None

    def _parse_fallback(self, expression: str) -> Dict[str, Any]:
        """
        LAST-RESORT fallback temporal parsing using regex.

        Only used when:
        1. LLM parsing fails completely
        2. Azure fallback also fails
        3. Prompt template not loaded

        Confidence scores are intentionally low (0.3-0.5) to indicate uncertainty.
        """
        expr_lower = expression.lower()
        logger.warning(f"Using regex fallback for temporal expression: '{expression[:50]}...'")

        # Pattern: "within|past|last|prior|preceding X months/years/days/weeks"
        match = re.search(
            r'(?:within|past|last|prior|preceding)\s+(\d+)\s+(month|year|day|week)s?',
            expr_lower
        )
        if match:
            return {
                "type": "relative",
                "direction": "past",
                "value": int(match.group(1)),
                "unit": match.group(2),
                "fhir_operator": "ge",
                "confidence": 0.5,  # Reduced from 0.7 - regex is unreliable
                "interpretation": "regex fallback - LLM unavailable"
            }

        # Check for common recency indicators
        if "current" in expr_lower:
            return {"type": "recency", "recency": "current", "confidence": 0.4}
        if "recent" in expr_lower:
            return {"type": "recency", "recency": "recent", "typical_value": 3, "typical_unit": "month", "confidence": 0.4}
        if "history of" in expr_lower:
            return {"type": "recency", "recency": "historical", "confidence": 0.4}

        return {"type": "unknown", "confidence": 0.2, "interpretation": "could not parse - LLM recommended"}


# Singleton instance
_temporal_parser_instance: Optional[LLMTemporalParser] = None


def get_temporal_parser() -> LLMTemporalParser:
    """Get or create singleton temporal parser instance."""
    global _temporal_parser_instance
    if _temporal_parser_instance is None:
        _temporal_parser_instance = LLMTemporalParser()
    return _temporal_parser_instance


# ============================================================================
# Utility Functions
# ============================================================================

def translate_omop_query_to_fhir(
    concept_ids: List[int],
    sql_template: Optional[str] = None,
    omop_table: Optional[str] = None,
    db_path: Optional[str] = None
) -> Optional[FhirQuerySpec]:
    """
    Convenience function to translate OMOP concepts to FHIR query.

    Args:
        concept_ids: OMOP concept IDs
        sql_template: Optional OMOP SQL template (helps extract filters)
        omop_table: Optional OMOP table name
        db_path: Optional path to ATHENA database

    Returns:
        FhirQuerySpec or None
    """
    bridge = OmopFhirBridge(db_path)

    try:
        if sql_template:
            return bridge.generate_fhir_from_omop_sql(sql_template, concept_ids)
        else:
            return bridge.map_omop_to_fhir(concept_ids, omop_table)
    finally:
        bridge.close()


def batch_translate_concepts(
    concept_ids: List[int],
    db_path: Optional[str] = None
) -> Dict[int, List[FhirCode]]:
    """
    Translate multiple OMOP concepts to FHIR codes in batch.

    Args:
        concept_ids: List of OMOP concept IDs
        db_path: Optional path to ATHENA database

    Returns:
        Dict mapping concept_id to list of FhirCode
    """
    bridge = OmopFhirBridge(db_path)
    results = {}

    try:
        for cid in concept_ids:
            results[cid] = bridge.get_fhir_equivalent_codes(cid)
        return results
    finally:
        bridge.close()
