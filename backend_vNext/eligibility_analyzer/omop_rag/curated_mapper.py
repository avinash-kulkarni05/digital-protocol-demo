"""
Curated OMOP Concept Mapper (PostgreSQL-Driven)

Provides deterministic (100% accurate) mappings for well-known terms like:
- Demographics: Gender, Race, Ethnicity
- Common conditions: Diabetes, Hypertension, etc.
- Common measurements: BMI, Hemoglobin, etc.

This is Tier 1 of the RAG approach - checked BEFORE semantic search.
If a term matches a curated mapping, it's returned immediately with confidence=1.0.

IMPORTANT: All concept data (IDs, names, codes) are loaded from the PostgreSQL
omop_concepts table (via POSTGRE_DATABASE_URL). Nothing is hardcoded.
When the database updates, mappings automatically update on reload.

Design Principles:
1. All concept data loaded from PostgreSQL omop_concepts table at initialization
2. Pattern-based matching for demographics (handles variations like "woman" -> female)
3. Exact matching for clinical terms (prevents false positives)
4. Case-insensitive matching
5. Cached for performance after first load
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


@dataclass
class CuratedMapping:
    """Result from curated mapping lookup."""
    concept_id: int
    concept_name: str
    concept_code: str
    vocabulary_id: str
    domain_id: str
    standard_concept: str = "S"
    confidence: float = 1.0
    source: str = "curated"
    match_type: str = "exact"  # exact, pattern, synonym

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "concept_name": self.concept_name,
            "concept_code": self.concept_code,
            "vocabulary_id": self.vocabulary_id,
            "domain_id": self.domain_id,
            "standard_concept": self.standard_concept,
            "confidence": self.confidence,
            "source": self.source,
            "match_type": self.match_type,
        }


# Pattern definitions for demographic term variations
# These map natural language variations to canonical concept names from ATHENA
# The canonical names (e.g., "FEMALE", "White") must exist in ATHENA

GENDER_PATTERN_MAPPINGS = {
    # Maps to ATHENA concept_name "FEMALE"
    "FEMALE": [
        r"\bfemale\b",
        r"\bwoman\b",
        r"\bwomen\b",
        r"\bgirl\b",
        r"\bfeminine\b",
        r"\bsex\s*(?:is\s*)?f\b",
        r"\bgender\s*(?:is\s*)?f\b",
        r"\bpatient\s+is\s+(?:a\s+)?female\b",
        r"\bfemale\s+patient\b",
        r"\bfemale\s+sex\b",
        r"\bfemale\s+gender\b",
    ],
    # Maps to ATHENA concept_name "MALE"
    "MALE": [
        r"\bmale\b",
        r"\bman\b",
        r"\bmen\b",
        r"\bboy\b",
        r"\bmasculine\b",
        r"\bsex\s*(?:is\s*)?m\b",
        r"\bgender\s*(?:is\s*)?m\b",
        r"\bpatient\s+is\s+(?:a\s+)?male\b",
        r"\bmale\s+patient\b",
        r"\bmale\s+sex\b",
        r"\bmale\s+gender\b",
    ],
}

RACE_PATTERN_MAPPINGS = {
    # Maps to ATHENA concept_name "White"
    "White": [r"\bwhite\b", r"\bcaucasian\b"],
    # Maps to ATHENA concept_name "Black or African American"
    "Black or African American": [r"\bblack\b", r"\bafrican\s*american\b", r"\bafrican\b"],
    # Maps to ATHENA concept_name "Asian"
    "Asian": [r"\basian\b", r"\boriental\b"],
    # Maps to ATHENA concept_name "American Indian or Alaska Native"
    "American Indian or Alaska Native": [
        r"\bamerican\s*indian\b",
        r"\balaska\s*native\b",
        r"\bnative\s*american\b",
        r"\bindigenous\b",
    ],
    # Maps to ATHENA concept_name "Native Hawaiian or Other Pacific Islander"
    "Native Hawaiian or Other Pacific Islander": [
        r"\bpacific\s*islander\b",
        r"\bhawaiian\b",
        r"\bsamoan\b",
        r"\bpolynesian\b",
    ],
}

ETHNICITY_PATTERN_MAPPINGS = {
    # Maps to ATHENA concept_name "Hispanic or Latino"
    "Hispanic or Latino": [r"\bhispanic\b", r"\blatino\b", r"\blatina\b"],
    # Maps to ATHENA concept_name "Not Hispanic or Latino"
    "Not Hispanic or Latino": [r"\bnon[\-\s]?hispanic\b", r"\bnot\s+hispanic\b"],
}

# Common clinical terms to load from ATHENA (by concept_name)
# These are loaded at initialization and cached
CLINICAL_TERMS_TO_LOAD = [
    # Conditions (SNOMED)
    "Diabetes mellitus",
    "Type 2 diabetes mellitus",
    "Type 1 diabetes mellitus",
    "Hypertensive disorder",
    "Malignant tumor of breast",
    "Primary malignant neoplasm of lung",
    "COVID-19",
    "Pregnancy",
    "Heart failure",
    "Chronic kidney disease",
    "Asthma",
    "Chronic obstructive lung disease",
    "Atrial fibrillation",
    "Myocardial infarction",
    "Stroke",
    # Measurements (LOINC)
    "Hemoglobin A1c/Hemoglobin.total in Blood",
    "Creatinine [Mass/volume] in Serum or Plasma",
    "Body mass index",
    "Glomerular filtration rate/1.73 sq M.predicted",
    "Glucose [Mass/volume] in Blood",
    "Cholesterol [Mass/volume] in Serum or Plasma",
]

# Aliases for clinical terms (maps common names to ATHENA concept names)
CLINICAL_TERM_ALIASES = {
    "diabetes": "Diabetes mellitus",
    "diabetes mellitus": "Diabetes mellitus",
    "type 2 diabetes": "Type 2 diabetes mellitus",
    "type 1 diabetes": "Type 1 diabetes mellitus",
    "hypertension": "Hypertensive disorder",
    "high blood pressure": "Hypertensive disorder",
    "breast cancer": "Malignant tumor of breast",
    "lung cancer": "Primary malignant neoplasm of lung",
    "covid-19": "COVID-19",
    "covid": "COVID-19",
    "coronavirus": "COVID-19",
    "pregnancy": "Pregnancy",
    "pregnant": "Pregnancy",
    "heart failure": "Heart failure",
    "chf": "Heart failure",
    "ckd": "Chronic kidney disease",
    "chronic kidney disease": "Chronic kidney disease",
    "asthma": "Asthma",
    "copd": "Chronic obstructive lung disease",
    "atrial fibrillation": "Atrial fibrillation",
    "afib": "Atrial fibrillation",
    "a-fib": "Atrial fibrillation",
    "myocardial infarction": "Myocardial infarction",
    "heart attack": "Myocardial infarction",
    "mi": "Myocardial infarction",
    "stroke": "Stroke",
    "cva": "Stroke",
    "hemoglobin a1c": "Hemoglobin A1c/Hemoglobin.total in Blood",
    "hba1c": "Hemoglobin A1c/Hemoglobin.total in Blood",
    "a1c": "Hemoglobin A1c/Hemoglobin.total in Blood",
    "creatinine": "Creatinine [Mass/volume] in Serum or Plasma",
    "bmi": "Body mass index",
    "body mass index": "Body mass index",
    "egfr": "Glomerular filtration rate/1.73 sq M.predicted",
    "gfr": "Glomerular filtration rate/1.73 sq M.predicted",
    "glucose": "Glucose [Mass/volume] in Blood",
    "blood glucose": "Glucose [Mass/volume] in Blood",
    "cholesterol": "Cholesterol [Mass/volume] in Serum or Plasma",
}


class CuratedMapper:
    """
    Tier 1 mapper for deterministic OMOP concept mappings.

    All concept data is loaded from PostgreSQL omop_concepts table - nothing is hardcoded.
    Only pattern matching logic (which maps variations like "woman" to "female") is in code.

    Handles:
    - Gender terms (male, female, and variations)
    - Race terms (white, black, asian, etc.)
    - Ethnicity terms (hispanic, non-hispanic)
    - Common clinical terms (diabetes, hypertension, etc.)
    """

    def __init__(self, database_url: Optional[str] = None, custom_mappings_path: Optional[str] = None):
        """
        Initialize curated mapper by loading concepts from PostgreSQL.

        Args:
            database_url: PostgreSQL connection URL (defaults to POSTGRE_DATABASE_URL env var)
            custom_mappings_path: Optional path to additional JSON mappings file
        """
        # Load environment
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        if env_path.exists():
            from dotenv import load_dotenv
            load_dotenv(env_path)

        # Get PostgreSQL database URL
        self._database_url = database_url or os.environ.get("POSTGRE_DATABASE_URL", "")

        # Initialize concept caches
        self._gender_concepts: Dict[str, CuratedMapping] = {}
        self._race_concepts: Dict[str, CuratedMapping] = {}
        self._ethnicity_concepts: Dict[str, CuratedMapping] = {}
        self._clinical_concepts: Dict[str, CuratedMapping] = {}
        self._custom_mappings: Dict[str, CuratedMapping] = {}

        # Load concepts from PostgreSQL
        if self._database_url:
            self._load_from_database()
        else:
            logger.warning(
                "POSTGRE_DATABASE_URL not configured. "
                "Curated mappings will be empty until database URL is set."
            )

        # Compile regex patterns for efficient matching
        self._compiled_gender_patterns = self._compile_patterns(GENDER_PATTERN_MAPPINGS)
        self._compiled_race_patterns = self._compile_patterns(RACE_PATTERN_MAPPINGS)
        self._compiled_ethnicity_patterns = self._compile_patterns(ETHNICITY_PATTERN_MAPPINGS)

        # Load custom mappings if provided
        if custom_mappings_path:
            self._load_custom_mappings(custom_mappings_path)

        logger.info(
            f"CuratedMapper initialized: "
            f"{len(self._gender_concepts)} genders, "
            f"{len(self._race_concepts)} races, "
            f"{len(self._ethnicity_concepts)} ethnicities, "
            f"{len(self._clinical_concepts)} clinical terms, "
            f"{len(self._custom_mappings)} custom mappings"
        )

    def _load_from_database(self) -> None:
        """Load all curated concepts from PostgreSQL omop_concepts table."""
        conn = None
        try:
            conn = psycopg2.connect(self._database_url)
            conn.autocommit = True

            # Load Gender concepts
            self._gender_concepts = self._load_domain_concepts(conn, "Gender", "Gender")

            # Load Race concepts
            self._race_concepts = self._load_domain_concepts(conn, "Race", "Race")

            # Load Ethnicity concepts
            self._ethnicity_concepts = self._load_domain_concepts(conn, "Ethnicity", "Ethnicity")

            # Load clinical concepts by name
            self._clinical_concepts = self._load_clinical_concepts(conn)

            logger.info("Loaded curated concepts from PostgreSQL omop_concepts table")

        except Exception as e:
            logger.error(f"Failed to load concepts from PostgreSQL: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def _load_domain_concepts(
        self,
        conn,
        domain_id: str,
        vocabulary_id: str
    ) -> Dict[str, CuratedMapping]:
        """
        Load all standard concepts from a specific domain/vocabulary.

        Args:
            conn: psycopg2 connection
            domain_id: Domain to filter (e.g., "Gender")
            vocabulary_id: Vocabulary to filter (e.g., "Gender")

        Returns:
            Dict mapping concept_name to CuratedMapping
        """
        query = """
            SELECT concept_id, concept_name, concept_code, vocabulary_id,
                   domain_id, standard_concept
            FROM omop_concepts
            WHERE domain_id = %s
              AND vocabulary_id = %s
              AND standard_concept = 'S'
        """

        concepts = {}
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, (domain_id, vocabulary_id))

        for row in cur.fetchall():
            concept_name = row["concept_name"]
            concepts[concept_name] = CuratedMapping(
                concept_id=row["concept_id"],
                concept_name=concept_name,
                concept_code=row["concept_code"] or "",
                vocabulary_id=row["vocabulary_id"],
                domain_id=row["domain_id"],
                standard_concept=row["standard_concept"] or "S",
            )

        cur.close()
        logger.debug(f"Loaded {len(concepts)} concepts from {domain_id}/{vocabulary_id}")
        return concepts

    def _load_clinical_concepts(self, conn) -> Dict[str, CuratedMapping]:
        """
        Load clinical concepts by name from PostgreSQL.

        Prioritizes:
        - SNOMED for conditions
        - LOINC for measurements
        - Condition/Measurement domains over other domains

        Returns:
            Dict mapping lowercase concept_name to CuratedMapping
        """
        concepts = {}

        # Build query to fetch concepts by name with priority ranking
        # Lower rank = higher priority
        placeholders = ", ".join(["%s"] * len(CLINICAL_TERMS_TO_LOAD))
        query = f"""
            SELECT concept_id, concept_name, concept_code, vocabulary_id,
                   domain_id, standard_concept,
                   CASE
                       WHEN vocabulary_id = 'SNOMED' AND domain_id = 'Condition' THEN 1
                       WHEN vocabulary_id = 'LOINC' AND domain_id = 'Measurement' THEN 1
                       WHEN domain_id = 'Condition' THEN 2
                       WHEN domain_id = 'Measurement' THEN 2
                       WHEN vocabulary_id = 'SNOMED' THEN 3
                       WHEN vocabulary_id = 'LOINC' THEN 3
                       ELSE 4
                   END as priority_rank
            FROM omop_concepts
            WHERE concept_name IN ({placeholders})
              AND standard_concept = 'S'
            ORDER BY priority_rank ASC
        """

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, CLINICAL_TERMS_TO_LOAD)

        for row in cur.fetchall():
            concept_name = row["concept_name"]
            name_lower = concept_name.lower()

            # Only store first match (highest priority) for each name
            if name_lower not in concepts:
                concepts[name_lower] = CuratedMapping(
                    concept_id=row["concept_id"],
                    concept_name=concept_name,
                    concept_code=row["concept_code"] or "",
                    vocabulary_id=row["vocabulary_id"],
                    domain_id=row["domain_id"],
                    standard_concept=row["standard_concept"] or "S",
                )

        cur.close()
        logger.debug(f"Loaded {len(concepts)} clinical concepts from PostgreSQL")
        return concepts

    def _compile_patterns(self, pattern_dict: Dict[str, List[str]]) -> Dict[str, List[re.Pattern]]:
        """Compile regex patterns for efficient matching."""
        compiled = {}
        for key, patterns in pattern_dict.items():
            compiled[key] = [re.compile(p, re.IGNORECASE) for p in patterns]
        return compiled

    def _load_custom_mappings(self, path: str) -> None:
        """Load additional mappings from JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for term, mapping in data.items():
                self._custom_mappings[term.lower()] = CuratedMapping(
                    concept_id=mapping["concept_id"],
                    concept_name=mapping["concept_name"],
                    concept_code=mapping.get("concept_code", ""),
                    vocabulary_id=mapping["vocabulary_id"],
                    domain_id=mapping["domain_id"],
                    standard_concept=mapping.get("standard_concept", "S"),
                )
            logger.info(f"Loaded {len(self._custom_mappings)} custom mappings from {path}")
        except Exception as e:
            logger.warning(f"Failed to load custom mappings from {path}: {e}")

    def lookup(self, term: str, domain_hint: Optional[str] = None) -> Optional[CuratedMapping]:
        """
        Look up a term in curated mappings.

        Args:
            term: The term to look up
            domain_hint: Optional domain hint (e.g., "Gender", "Condition")

        Returns:
            CuratedMapping if found, None otherwise
        """
        if not term:
            return None

        term_lower = term.lower().strip()

        # 1. Check gender patterns first (handles "Patient is female", "Sex is male", etc.)
        gender_match = self._match_gender(term_lower)
        if gender_match:
            return gender_match

        # 2. Check race patterns
        race_match = self._match_race(term_lower)
        if race_match:
            return race_match

        # 3. Check ethnicity patterns
        ethnicity_match = self._match_ethnicity(term_lower)
        if ethnicity_match:
            return ethnicity_match

        # 4. Check exact clinical term matches
        clinical_match = self._match_clinical(term_lower)
        if clinical_match:
            return clinical_match

        # 5. Check custom mappings
        custom_match = self._custom_mappings.get(term_lower)
        if custom_match:
            return custom_match

        return None

    def _match_gender(self, term: str) -> Optional[CuratedMapping]:
        """Match gender patterns and return concept from ATHENA."""
        for concept_name, patterns in self._compiled_gender_patterns.items():
            for pattern in patterns:
                if pattern.search(term):
                    # Look up the actual concept from ATHENA-loaded data
                    if concept_name in self._gender_concepts:
                        mapping = self._gender_concepts[concept_name]
                        return CuratedMapping(
                            concept_id=mapping.concept_id,
                            concept_name=mapping.concept_name,
                            concept_code=mapping.concept_code,
                            vocabulary_id=mapping.vocabulary_id,
                            domain_id=mapping.domain_id,
                            standard_concept=mapping.standard_concept,
                            confidence=1.0,
                            source="curated",
                            match_type="pattern",
                        )
                    else:
                        logger.warning(f"Gender concept '{concept_name}' not found in ATHENA")
        return None

    def _match_race(self, term: str) -> Optional[CuratedMapping]:
        """Match race patterns and return concept from ATHENA."""
        for concept_name, patterns in self._compiled_race_patterns.items():
            for pattern in patterns:
                if pattern.search(term):
                    if concept_name in self._race_concepts:
                        mapping = self._race_concepts[concept_name]
                        return CuratedMapping(
                            concept_id=mapping.concept_id,
                            concept_name=mapping.concept_name,
                            concept_code=mapping.concept_code,
                            vocabulary_id=mapping.vocabulary_id,
                            domain_id=mapping.domain_id,
                            standard_concept=mapping.standard_concept,
                            confidence=1.0,
                            source="curated",
                            match_type="pattern",
                        )
                    else:
                        logger.warning(f"Race concept '{concept_name}' not found in ATHENA")
        return None

    def _match_ethnicity(self, term: str) -> Optional[CuratedMapping]:
        """
        Match ethnicity patterns and return concept from ATHENA.

        Note: Check "Not Hispanic or Latino" BEFORE "Hispanic or Latino" to avoid false positives
        (e.g., "non-hispanic" should not match "hispanic")
        """
        # Check more specific patterns first
        check_order = ["Not Hispanic or Latino", "Hispanic or Latino"]

        for concept_name in check_order:
            if concept_name not in self._compiled_ethnicity_patterns:
                continue
            patterns = self._compiled_ethnicity_patterns[concept_name]
            for pattern in patterns:
                if pattern.search(term):
                    if concept_name in self._ethnicity_concepts:
                        mapping = self._ethnicity_concepts[concept_name]
                        return CuratedMapping(
                            concept_id=mapping.concept_id,
                            concept_name=mapping.concept_name,
                            concept_code=mapping.concept_code,
                            vocabulary_id=mapping.vocabulary_id,
                            domain_id=mapping.domain_id,
                            standard_concept=mapping.standard_concept,
                            confidence=1.0,
                            source="curated",
                            match_type="pattern",
                        )
                    else:
                        logger.warning(f"Ethnicity concept '{concept_name}' not found in ATHENA")
        return None

    def _match_clinical(self, term: str) -> Optional[CuratedMapping]:
        """Match clinical terms using aliases and exact matches."""
        # First check if term is an alias
        canonical_name = CLINICAL_TERM_ALIASES.get(term)

        if canonical_name:
            # Look up by canonical name (lowercase)
            mapping = self._clinical_concepts.get(canonical_name.lower())
            if mapping:
                return CuratedMapping(
                    concept_id=mapping.concept_id,
                    concept_name=mapping.concept_name,
                    concept_code=mapping.concept_code,
                    vocabulary_id=mapping.vocabulary_id,
                    domain_id=mapping.domain_id,
                    standard_concept=mapping.standard_concept,
                    confidence=1.0,
                    source="curated",
                    match_type="alias",
                )

        # Try direct lookup by term
        mapping = self._clinical_concepts.get(term)
        if mapping:
            return CuratedMapping(
                concept_id=mapping.concept_id,
                concept_name=mapping.concept_name,
                concept_code=mapping.concept_code,
                vocabulary_id=mapping.vocabulary_id,
                domain_id=mapping.domain_id,
                standard_concept=mapping.standard_concept,
                confidence=1.0,
                source="curated",
                match_type="exact",
            )

        return None

    def is_demographic_term(self, term: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a term is a demographic criterion.

        Args:
            term: The term to check

        Returns:
            Tuple of (is_demographic, demographic_type)
            demographic_type is one of: "gender", "race", "ethnicity", or None
        """
        term_lower = term.lower().strip()

        # Check gender
        for patterns in self._compiled_gender_patterns.values():
            for pattern in patterns:
                if pattern.search(term_lower):
                    return True, "gender"

        # Check race
        for patterns in self._compiled_race_patterns.values():
            for pattern in patterns:
                if pattern.search(term_lower):
                    return True, "race"

        # Check ethnicity
        for patterns in self._compiled_ethnicity_patterns.values():
            for pattern in patterns:
                if pattern.search(term_lower):
                    return True, "ethnicity"

        return False, None

    def get_all_gender_concepts(self) -> Dict[str, CuratedMapping]:
        """Get all gender concepts loaded from ATHENA."""
        return self._gender_concepts.copy()

    def get_all_race_concepts(self) -> Dict[str, CuratedMapping]:
        """Get all race concepts loaded from ATHENA."""
        return self._race_concepts.copy()

    def get_all_ethnicity_concepts(self) -> Dict[str, CuratedMapping]:
        """Get all ethnicity concepts loaded from ATHENA."""
        return self._ethnicity_concepts.copy()

    def get_all_clinical_concepts(self) -> Dict[str, CuratedMapping]:
        """Get all clinical concepts loaded from ATHENA."""
        return self._clinical_concepts.copy()

    def reload(self) -> None:
        """
        Reload all concepts from PostgreSQL.

        Call this after the database is updated to refresh mappings.
        """
        if self._database_url:
            logger.info("Reloading concepts from PostgreSQL...")
            self._load_from_database()
            logger.info(
                f"Reloaded: {len(self._gender_concepts)} genders, "
                f"{len(self._race_concepts)} races, "
                f"{len(self._ethnicity_concepts)} ethnicities, "
                f"{len(self._clinical_concepts)} clinical terms"
            )
        else:
            logger.error("Cannot reload: POSTGRE_DATABASE_URL not configured")

    # Keep backward-compatible alias
    reload_from_athena = reload


# Singleton instance
_curated_mapper: Optional[CuratedMapper] = None


def get_curated_mapper(
    database_url: Optional[str] = None,
    custom_mappings_path: Optional[str] = None,
    force_reload: bool = False
) -> CuratedMapper:
    """
    Get or create the curated mapper singleton.

    Args:
        database_url: PostgreSQL connection URL (defaults to POSTGRE_DATABASE_URL env var)
        custom_mappings_path: Optional path to additional JSON mappings
        force_reload: If True, recreate the mapper even if it exists

    Returns:
        CuratedMapper instance
    """
    global _curated_mapper
    if _curated_mapper is None or force_reload:
        _curated_mapper = CuratedMapper(database_url, custom_mappings_path)
    return _curated_mapper


# CLI for testing
if __name__ == "__main__":
    import sys

    mapper = get_curated_mapper()

    # Test cases
    test_terms = [
        "Patient is female",
        "Sex is male",
        "female",
        "male patient",
        "woman",
        "men",
        "White",
        "Black or African American",
        "Asian",
        "Hispanic",
        "Non-Hispanic",
        "diabetes mellitus",
        "type 2 diabetes",
        "hypertension",
        "breast cancer",
        "hemoglobin a1c",
        "hba1c",
        "creatinine",
        "bmi",
        "egfr",
        "unknown term xyz",
    ]

    print("\n" + "=" * 70)
    print(" Curated Mapper Test (PostgreSQL-Driven)")
    print("=" * 70)

    print("\n  Loaded Concepts from PostgreSQL:")
    print(f"    Genders: {list(mapper.get_all_gender_concepts().keys())}")
    print(f"    Races: {list(mapper.get_all_race_concepts().keys())}")
    print(f"    Ethnicities: {list(mapper.get_all_ethnicity_concepts().keys())}")
    print(f"    Clinical: {len(mapper.get_all_clinical_concepts())} terms")

    print("\n  Test Results:")
    print("-" * 70)

    for term in test_terms:
        result = mapper.lookup(term)
        if result:
            print(f"\n  Term: '{term}'")
            print(f"    -> {result.concept_name} (ID: {result.concept_id})")
            print(f"       Vocabulary: {result.vocabulary_id}, Domain: {result.domain_id}")
            print(f"       Confidence: {result.confidence}, Match: {result.match_type}")
        else:
            print(f"\n  Term: '{term}'")
            print(f"    -> No curated mapping found")

    print("\n" + "=" * 70)
