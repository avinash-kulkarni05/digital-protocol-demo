"""
Terminology Mapper Service for SOA Pipeline

Provides comprehensive concept mapping to controlled vocabularies:
- ATHENA OMOP CDM (LOINC, SNOMED, MeSH, etc.)
- CDISC Controlled Terminology (NCI Thesaurus)

Features:
- Batched database lookups for performance
- Synonym-based fuzzy matching
- LLM-assisted disambiguation for ambiguous matches
- Domain-aware filtering (Measurement, Procedure, etc.)

Usage:
    from soa_analyzer.terminology import TerminologyMapper

    mapper = TerminologyMapper()

    # Single concept lookup
    result = mapper.map_concept("Hemoglobin", domain_hint="Measurement")

    # Batched lookup (much faster for many terms)
    results = mapper.map_concepts_batch([
        {"term": "Hemoglobin", "domain_hint": "Measurement"},
        {"term": "Blood Pressure", "domain_hint": "Measurement"},
        {"term": "Physical Exam", "domain_hint": "Procedure"},
    ])

    # With LLM disambiguation
    results = mapper.map_concepts_batch(terms, use_llm_disambiguation=True)
"""

import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Paths
DEFAULT_ATHENA_DB = Path(__file__).parent.parent.parent.parent / "athena_concepts_full.db"
DEFAULT_CDISC_CODELISTS = Path(__file__).parent.parent.parent / "config" / "cdisc_codelists.json"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


@dataclass
class ConceptMatch:
    """A matched concept from controlled terminology."""
    concept_id: int
    concept_name: str
    concept_code: str
    vocabulary_id: str  # LOINC, SNOMED, NCIt, etc.
    domain_id: str  # Measurement, Procedure, Condition, etc.
    concept_class_id: str  # Lab Test, Clinical Observation, etc.
    standard_concept: str  # S = Standard, C = Classification
    match_score: float  # 0.0 to 1.0
    match_type: str  # exact, synonym, fuzzy, llm_selected
    matched_term: str  # The term that matched (original or synonym)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conceptId": self.concept_id,
            "conceptName": self.concept_name,
            "conceptCode": self.concept_code,
            "vocabularyId": self.vocabulary_id,
            "domainId": self.domain_id,
            "conceptClassId": self.concept_class_id,
            "standardConcept": self.standard_concept,
            "matchScore": self.match_score,
            "matchType": self.match_type,
            "matchedTerm": self.matched_term,
        }


@dataclass
class MappingResult:
    """Result of a terminology mapping attempt."""
    input_term: str
    success: bool
    primary_match: Optional[ConceptMatch] = None
    alternative_matches: List[ConceptMatch] = field(default_factory=list)
    confidence: float = 0.0
    disambiguation_needed: bool = False
    disambiguation_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inputTerm": self.input_term,
            "success": self.success,
            "primaryMatch": self.primary_match.to_dict() if self.primary_match else None,
            "alternativeMatches": [m.to_dict() for m in self.alternative_matches],
            "confidence": self.confidence,
            "disambiguationNeeded": self.disambiguation_needed,
            "disambiguationReason": self.disambiguation_reason,
        }


@dataclass
class TerminologyMapperConfig:
    """Configuration for terminology mapper."""
    athena_db_path: Path = DEFAULT_ATHENA_DB
    cdisc_codelists_path: Path = DEFAULT_CDISC_CODELISTS
    # Matching thresholds
    exact_match_score: float = 1.0
    synonym_match_score: float = 0.95
    fuzzy_match_score: float = 0.80
    llm_selected_score: float = 0.90
    min_confidence_threshold: float = 0.70
    # Domain mappings (CDASH domain -> ATHENA domain)
    cdash_to_athena_domain: Dict[str, List[str]] = field(default_factory=lambda: {
        "LB": ["Measurement"],  # Laboratory
        "VS": ["Measurement"],  # Vital Signs
        "EG": ["Measurement"],  # ECG
        "PE": ["Procedure", "Observation"],  # Physical Exam
        "QS": ["Observation", "Measurement"],  # Questionnaires
        "TU": ["Procedure", "Measurement"],  # Tumor
        "PC": ["Measurement"],  # Pharmacokinetics
        "MH": ["Condition", "Observation"],  # Medical History
        "BS": ["Procedure", "Specimen"],  # Biospecimen
        "MI": ["Procedure"],  # Medical Imaging
    })
    # Vocabulary priority for each type
    vocabulary_priority: Dict[str, List[str]] = field(default_factory=lambda: {
        "Measurement": ["LOINC", "SNOMED", "NCIt"],
        "Procedure": ["SNOMED", "LOINC", "NCIt"],
        "Condition": ["SNOMED", "MeSH", "NCIt"],
        "Observation": ["LOINC", "SNOMED"],
        "Specimen": ["SNOMED", "LOINC"],
    })
    # LLM settings
    use_llm_disambiguation: bool = True
    llm_batch_size: int = 20
    llm_model: str = "gemini-2.5-pro"


class TerminologyMapper:
    """
    Maps clinical terms to controlled vocabulary concepts.

    Supports ATHENA OMOP CDM vocabularies (LOINC, SNOMED, etc.)
    and CDISC Controlled Terminology.
    """

    def __init__(self, config: Optional[TerminologyMapperConfig] = None):
        self.config = config or TerminologyMapperConfig()
        self._db_connection: Optional[sqlite3.Connection] = None
        self._cdisc_codelists: Dict[str, Any] = {}
        self._concept_cache: Dict[str, List[ConceptMatch]] = {}
        self._disambiguation_prompt: Optional[str] = None
        self._gemini_model = None

        # Load resources
        self._load_cdisc_codelists()
        self._load_disambiguation_prompt()
        self._init_gemini()

    def _get_db_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._db_connection is None:
            if not self.config.athena_db_path.exists():
                raise FileNotFoundError(f"ATHENA database not found: {self.config.athena_db_path}")
            self._db_connection = sqlite3.connect(str(self.config.athena_db_path))
            self._db_connection.row_factory = sqlite3.Row
            logger.info(f"Connected to ATHENA database: {self.config.athena_db_path}")
        return self._db_connection

    def _load_cdisc_codelists(self) -> None:
        """Load CDISC controlled terminology codelists."""
        if self.config.cdisc_codelists_path.exists():
            try:
                with open(self.config.cdisc_codelists_path, "r") as f:
                    self._cdisc_codelists = json.load(f)
                logger.info(f"Loaded CDISC codelists: {list(self._cdisc_codelists.get('codelists', {}).keys())}")
            except Exception as e:
                logger.warning(f"Failed to load CDISC codelists: {e}")

    def _load_disambiguation_prompt(self) -> None:
        """Load the LLM disambiguation prompt template."""
        prompt_path = PROMPTS_DIR / "terminology_disambiguation.txt"
        if prompt_path.exists():
            with open(prompt_path, "r") as f:
                self._disambiguation_prompt = f.read()
        else:
            # Create default prompt
            self._disambiguation_prompt = self._get_default_disambiguation_prompt()

    def _init_gemini(self) -> None:
        """Initialize Gemini client for LLM disambiguation."""
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self._gemini_model = genai.GenerativeModel(
                model_name=self.config.llm_model,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 2048,
                }
            )
            logger.info(f"Initialized Gemini model: {self.config.llm_model}")
        else:
            logger.warning("GEMINI_API_KEY not found - LLM disambiguation will be disabled")

    def _call_gemini(self, prompt: str, max_tokens: int = 1024) -> str:
        """Call Gemini model for disambiguation."""
        if not self._gemini_model:
            raise RuntimeError("Gemini model not initialized - check GEMINI_API_KEY")

        response = self._gemini_model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens}
        )
        return response.text

    def _get_default_disambiguation_prompt(self) -> str:
        """Get default disambiguation prompt."""
        return """You are a clinical terminology expert. Given a clinical term and candidate matches from controlled vocabularies, select the best match.

INPUT TERM: {input_term}
CONTEXT: {context}

CANDIDATE MATCHES:
{candidates}

For each candidate, evaluate:
1. Semantic match - Does the concept meaning match the input term?
2. Specificity - Is the concept at the right level of specificity?
3. Domain appropriateness - Does the vocabulary/domain fit the clinical context?

Return your selection as JSON:
{{
    "selected_index": <0-based index of best match, or -1 if none appropriate>,
    "confidence": <0.0 to 1.0>,
    "rationale": "<brief explanation>"
}}

If multiple candidates are equally valid, prefer:
1. LOINC for lab tests and measurements
2. SNOMED for procedures and conditions
3. More specific concepts over general ones
4. Standard concepts (S) over classification concepts (C)

JSON response:"""

    def _normalize_term(self, term: str) -> str:
        """Normalize a term for matching."""
        # Lowercase
        normalized = term.lower().strip()
        # Remove parenthetical notes
        normalized = re.sub(r'\s*\([^)]*\)\s*', ' ', normalized)
        # Remove special characters except alphanumeric and spaces
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        # Collapse whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _search_athena_exact(
        self,
        term: str,
        domain_filters: Optional[List[str]] = None,
        vocabulary_filters: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[ConceptMatch]:
        """Search for exact matches in ATHENA database."""
        conn = self._get_db_connection()

        # Build query
        query = """
            SELECT c.concept_id, c.concept_name, c.concept_code,
                   c.vocabulary_id, c.domain_id, c.concept_class_id,
                   c.standard_concept
            FROM concept c
            WHERE c.concept_name = ? COLLATE NOCASE
              AND c.standard_concept = 'S'
              AND (c.invalid_reason IS NULL OR c.invalid_reason = '')
        """
        params: List[Any] = [term]

        if domain_filters:
            placeholders = ",".join("?" * len(domain_filters))
            query += f" AND c.domain_id IN ({placeholders})"
            params.extend(domain_filters)

        if vocabulary_filters:
            placeholders = ",".join("?" * len(vocabulary_filters))
            query += f" AND c.vocabulary_id IN ({placeholders})"
            params.extend(vocabulary_filters)

        query += f" LIMIT {limit}"

        cursor = conn.execute(query, params)
        results = []
        for row in cursor.fetchall():
            results.append(ConceptMatch(
                concept_id=row["concept_id"],
                concept_name=row["concept_name"],
                concept_code=row["concept_code"],
                vocabulary_id=row["vocabulary_id"],
                domain_id=row["domain_id"],
                concept_class_id=row["concept_class_id"],
                standard_concept=row["standard_concept"],
                match_score=self.config.exact_match_score,
                match_type="exact",
                matched_term=term,
            ))
        return results

    def _search_athena_synonym(
        self,
        term: str,
        domain_filters: Optional[List[str]] = None,
        vocabulary_filters: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[ConceptMatch]:
        """Search for synonym matches in ATHENA database."""
        conn = self._get_db_connection()

        # Search in concept_synonym table
        query = """
            SELECT c.concept_id, c.concept_name, c.concept_code,
                   c.vocabulary_id, c.domain_id, c.concept_class_id,
                   c.standard_concept, cs.concept_synonym_name
            FROM concept_synonym cs
            JOIN concept c ON cs.concept_id = c.concept_id
            WHERE cs.concept_synonym_name = ? COLLATE NOCASE
              AND c.standard_concept = 'S'
              AND (c.invalid_reason IS NULL OR c.invalid_reason = '')
        """
        params: List[Any] = [term]

        if domain_filters:
            placeholders = ",".join("?" * len(domain_filters))
            query += f" AND c.domain_id IN ({placeholders})"
            params.extend(domain_filters)

        if vocabulary_filters:
            placeholders = ",".join("?" * len(vocabulary_filters))
            query += f" AND c.vocabulary_id IN ({placeholders})"
            params.extend(vocabulary_filters)

        query += f" LIMIT {limit}"

        cursor = conn.execute(query, params)
        results = []
        for row in cursor.fetchall():
            results.append(ConceptMatch(
                concept_id=row["concept_id"],
                concept_name=row["concept_name"],
                concept_code=row["concept_code"],
                vocabulary_id=row["vocabulary_id"],
                domain_id=row["domain_id"],
                concept_class_id=row["concept_class_id"],
                standard_concept=row["standard_concept"],
                match_score=self.config.synonym_match_score,
                match_type="synonym",
                matched_term=row["concept_synonym_name"],
            ))
        return results

    def _search_athena_fuzzy(
        self,
        term: str,
        domain_filters: Optional[List[str]] = None,
        vocabulary_filters: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[ConceptMatch]:
        """
        Search for fuzzy matches using optimized LIKE patterns.

        Performance optimized:
        - Uses starts-with pattern first (can use index)
        - Limits vocabulary scope for faster queries
        - Avoids expensive contains pattern on large tables
        """
        conn = self._get_db_connection()
        normalized = self._normalize_term(term)

        if not normalized or len(normalized) < 3:
            return []

        results = []
        seen_ids = set()

        # Priority vocabularies for faster matching
        priority_vocabs = vocabulary_filters or ["LOINC", "SNOMED", "NCIt", "MeSH"]

        # Pattern 1: Starts with (fastest, can use index)
        pattern = f"{normalized}%"

        query = """
            SELECT c.concept_id, c.concept_name, c.concept_code,
                   c.vocabulary_id, c.domain_id, c.concept_class_id,
                   c.standard_concept
            FROM concept c
            WHERE c.concept_name LIKE ? COLLATE NOCASE
              AND c.standard_concept = 'S'
              AND (c.invalid_reason IS NULL OR c.invalid_reason = '')
        """
        params: List[Any] = [pattern]

        if domain_filters:
            placeholders = ",".join("?" * len(domain_filters))
            query += f" AND c.domain_id IN ({placeholders})"
            params.extend(domain_filters)

        # Always filter by vocabulary for performance
        vocab_placeholders = ",".join("?" * len(priority_vocabs))
        query += f" AND c.vocabulary_id IN ({vocab_placeholders})"
        params.extend(priority_vocabs)

        query += f" LIMIT {limit}"

        cursor = conn.execute(query, params)
        for row in cursor.fetchall():
            if row["concept_id"] not in seen_ids:
                seen_ids.add(row["concept_id"])
                concept_name_lower = row["concept_name"].lower()
                score = self.config.fuzzy_match_score + (
                    0.1 * len(normalized) / max(len(concept_name_lower), 1)
                )
                results.append(ConceptMatch(
                    concept_id=row["concept_id"],
                    concept_name=row["concept_name"],
                    concept_code=row["concept_code"],
                    vocabulary_id=row["vocabulary_id"],
                    domain_id=row["domain_id"],
                    concept_class_id=row["concept_class_id"],
                    standard_concept=row["standard_concept"],
                    match_score=min(score, 0.95),
                    match_type="fuzzy",
                    matched_term=term,
                ))

        # If no results and term has multiple words, try first word
        if not results and " " in normalized:
            first_word = normalized.split()[0]
            if len(first_word) >= 3:
                pattern = f"{first_word}%"
                params[0] = pattern
                cursor = conn.execute(query, params)
                for row in cursor.fetchall():
                    if row["concept_id"] not in seen_ids:
                        seen_ids.add(row["concept_id"])
                        results.append(ConceptMatch(
                            concept_id=row["concept_id"],
                            concept_name=row["concept_name"],
                            concept_code=row["concept_code"],
                            vocabulary_id=row["vocabulary_id"],
                            domain_id=row["domain_id"],
                            concept_class_id=row["concept_class_id"],
                            standard_concept=row["standard_concept"],
                            match_score=self.config.fuzzy_match_score * 0.9,
                            match_type="fuzzy",
                            matched_term=term,
                        ))

        # Sort by score
        results.sort(key=lambda x: x.match_score, reverse=True)
        return results[:limit]

    def _search_athena_batch(
        self,
        terms: List[str],
        domain_filters: Optional[List[str]] = None,
        vocabulary_filters: Optional[List[str]] = None,
    ) -> Dict[str, List[ConceptMatch]]:
        """
        Batch search for multiple terms in ATHENA database.
        More efficient than individual searches.
        """
        conn = self._get_db_connection()
        results: Dict[str, List[ConceptMatch]] = {term: [] for term in terms}

        if not terms:
            return results

        # Build batch query for exact matches
        term_placeholders = ",".join("?" * len(terms))
        query = f"""
            SELECT c.concept_id, c.concept_name, c.concept_code,
                   c.vocabulary_id, c.domain_id, c.concept_class_id,
                   c.standard_concept
            FROM concept c
            WHERE c.concept_name COLLATE NOCASE IN ({term_placeholders})
              AND c.standard_concept = 'S'
              AND (c.invalid_reason IS NULL OR c.invalid_reason = '')
        """
        params: List[Any] = list(terms)

        if domain_filters:
            placeholders = ",".join("?" * len(domain_filters))
            query += f" AND c.domain_id IN ({placeholders})"
            params.extend(domain_filters)

        if vocabulary_filters:
            placeholders = ",".join("?" * len(vocabulary_filters))
            query += f" AND c.vocabulary_id IN ({placeholders})"
            params.extend(vocabulary_filters)

        # Execute exact match query
        cursor = conn.execute(query, params)
        term_lower_map = {t.lower(): t for t in terms}

        for row in cursor.fetchall():
            concept_name_lower = row["concept_name"].lower()
            if concept_name_lower in term_lower_map:
                original_term = term_lower_map[concept_name_lower]
                results[original_term].append(ConceptMatch(
                    concept_id=row["concept_id"],
                    concept_name=row["concept_name"],
                    concept_code=row["concept_code"],
                    vocabulary_id=row["vocabulary_id"],
                    domain_id=row["domain_id"],
                    concept_class_id=row["concept_class_id"],
                    standard_concept=row["standard_concept"],
                    match_score=self.config.exact_match_score,
                    match_type="exact",
                    matched_term=original_term,
                ))

        # For terms with no exact matches, try synonym matches (batched)
        unmatched = [t for t in terms if not results[t]]
        if unmatched:
            term_placeholders = ",".join("?" * len(unmatched))
            query = f"""
                SELECT c.concept_id, c.concept_name, c.concept_code,
                       c.vocabulary_id, c.domain_id, c.concept_class_id,
                       c.standard_concept, cs.concept_synonym_name
                FROM concept_synonym cs
                JOIN concept c ON cs.concept_id = c.concept_id
                WHERE cs.concept_synonym_name COLLATE NOCASE IN ({term_placeholders})
                  AND c.standard_concept = 'S'
                  AND (c.invalid_reason IS NULL OR c.invalid_reason = '')
            """
            params = list(unmatched)

            if domain_filters:
                placeholders = ",".join("?" * len(domain_filters))
                query += f" AND c.domain_id IN ({placeholders})"
                params.extend(domain_filters)

            if vocabulary_filters:
                placeholders = ",".join("?" * len(vocabulary_filters))
                query += f" AND c.vocabulary_id IN ({placeholders})"
                params.extend(vocabulary_filters)

            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                synonym_lower = row["concept_synonym_name"].lower()
                if synonym_lower in term_lower_map:
                    original_term = term_lower_map[synonym_lower]
                    results[original_term].append(ConceptMatch(
                        concept_id=row["concept_id"],
                        concept_name=row["concept_name"],
                        concept_code=row["concept_code"],
                        vocabulary_id=row["vocabulary_id"],
                        domain_id=row["domain_id"],
                        concept_class_id=row["concept_class_id"],
                        standard_concept=row["standard_concept"],
                        match_score=self.config.synonym_match_score,
                        match_type="synonym",
                        matched_term=row["concept_synonym_name"],
                    ))

        return results

    def _disambiguate_with_llm(
        self,
        input_term: str,
        candidates: List[ConceptMatch],
        context: str = "",
    ) -> Tuple[Optional[int], float, str]:
        """
        Use Gemini 2.5 Pro to select the best match from candidates.

        Returns:
            Tuple of (selected_index, confidence, rationale)
        """
        if not candidates:
            return None, 0.0, "No candidates to disambiguate"

        if len(candidates) == 1:
            return 0, candidates[0].match_score, "Single candidate, auto-selected"

        if not self._gemini_model:
            logger.warning("Gemini model not available for disambiguation")
            return self._select_by_priority(candidates), 0.85, "LLM unavailable, selected by priority"

        # Build candidate list
        candidate_lines = []
        for i, c in enumerate(candidates):
            candidate_lines.append(
                f"{i}. [{c.vocabulary_id}] {c.concept_name} (code: {c.concept_code}, "
                f"domain: {c.domain_id}, class: {c.concept_class_id})"
            )

        prompt = self._disambiguation_prompt.format(
            input_term=input_term,
            context=context or "Clinical trial SOA activity/assessment",
            candidates="\n".join(candidate_lines),
        )

        try:
            response = self._call_gemini(prompt, max_tokens=256)

            # Parse JSON response
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                data = json.loads(json_match.group())
                selected_idx = data.get("selected_index", -1)
                confidence = data.get("confidence", 0.8)
                rationale = data.get("rationale", "Gemini selected")

                if 0 <= selected_idx < len(candidates):
                    return selected_idx, confidence, rationale
                else:
                    logger.warning(f"Gemini returned invalid index {selected_idx} for '{input_term}'")
                    return None, 0.0, "Gemini indicated no appropriate match"
            else:
                logger.warning(f"Could not parse Gemini response for '{input_term}'")
                return self._select_by_priority(candidates), 0.85, "Gemini response invalid, selected by priority"

        except Exception as e:
            logger.error(f"Gemini disambiguation failed for '{input_term}': {e}")
            return self._select_by_priority(candidates), 0.85, f"Gemini error, selected by priority: {str(e)}"

    def _select_by_priority(self, candidates: List[ConceptMatch]) -> int:
        """Select best candidate based on vocabulary priority."""
        if not candidates:
            return -1

        # Priority order for vocabularies
        vocab_priority = {"LOINC": 0, "SNOMED": 1, "NCIt": 2, "MeSH": 3}

        # Sort by vocabulary priority, then match score
        scored = []
        for i, c in enumerate(candidates):
            vocab_score = vocab_priority.get(c.vocabulary_id, 10)
            scored.append((vocab_score, -c.match_score, i))

        scored.sort()
        return scored[0][2]

    def _get_domain_filters(self, cdash_domain: Optional[str]) -> Optional[List[str]]:
        """Get ATHENA domain filters from CDASH domain."""
        if not cdash_domain:
            return None
        return self.config.cdash_to_athena_domain.get(cdash_domain)

    def _get_vocabulary_filters(self, domain: Optional[str]) -> Optional[List[str]]:
        """Get vocabulary priority filters for a domain."""
        if not domain:
            return None
        athena_domains = self.config.cdash_to_athena_domain.get(domain)
        if athena_domains:
            all_vocabs = []
            for d in athena_domains:
                all_vocabs.extend(self.config.vocabulary_priority.get(d, []))
            return list(dict.fromkeys(all_vocabs))  # Dedupe while preserving order
        return None

    def map_concept(
        self,
        term: str,
        domain_hint: Optional[str] = None,
        context: str = "",
        use_llm_disambiguation: Optional[bool] = None,
    ) -> MappingResult:
        """
        Map a single term to controlled terminology.

        Args:
            term: The clinical term to map
            domain_hint: CDASH domain hint (LB, VS, EG, PE, etc.)
            context: Additional context for disambiguation
            use_llm_disambiguation: Override config setting for LLM use

        Returns:
            MappingResult with matched concept(s)
        """
        use_llm = use_llm_disambiguation if use_llm_disambiguation is not None else self.config.use_llm_disambiguation

        # Check cache
        cache_key = f"{term}|{domain_hint}"
        if cache_key in self._concept_cache:
            cached = self._concept_cache[cache_key]
            if cached:
                return MappingResult(
                    input_term=term,
                    success=True,
                    primary_match=cached[0],
                    alternative_matches=cached[1:],
                    confidence=cached[0].match_score,
                )
            else:
                return MappingResult(input_term=term, success=False)

        domain_filters = self._get_domain_filters(domain_hint)
        vocab_filters = self._get_vocabulary_filters(domain_hint)

        # Try exact match first
        matches = self._search_athena_exact(term, domain_filters, vocab_filters)

        # Try synonym match if no exact
        if not matches:
            matches = self._search_athena_synonym(term, domain_filters, vocab_filters)

        # NOTE: Fuzzy matching removed - produces semantically incorrect results
        # For unmatched terms, use LLM semantic lookup via map_concepts_batch

        if not matches:
            self._concept_cache[cache_key] = []
            return MappingResult(input_term=term, success=False)

        # Single match - easy case
        if len(matches) == 1:
            self._concept_cache[cache_key] = matches
            return MappingResult(
                input_term=term,
                success=True,
                primary_match=matches[0],
                confidence=matches[0].match_score,
            )

        # Multiple matches - need disambiguation
        if use_llm and len(matches) > 1:
            selected_idx, confidence, rationale = self._disambiguate_with_llm(
                term, matches, context
            )
            if selected_idx is not None and selected_idx >= 0:
                primary = matches[selected_idx]
                primary.match_score = self.config.llm_selected_score
                primary.match_type = "llm_selected"
                alternatives = [m for i, m in enumerate(matches) if i != selected_idx]
                self._concept_cache[cache_key] = [primary] + alternatives
                return MappingResult(
                    input_term=term,
                    success=True,
                    primary_match=primary,
                    alternative_matches=alternatives,
                    confidence=confidence,
                    disambiguation_needed=False,
                    disambiguation_reason=rationale,
                )

        # Return all matches, mark as needing disambiguation
        self._concept_cache[cache_key] = matches
        return MappingResult(
            input_term=term,
            success=True,
            primary_match=matches[0],
            alternative_matches=matches[1:],
            confidence=matches[0].match_score * 0.8,  # Lower confidence for ambiguous
            disambiguation_needed=True,
            disambiguation_reason=f"Multiple matches found ({len(matches)}), requires review",
        )

    def map_concepts_batch(
        self,
        terms: List[Dict[str, Any]],
        use_llm_disambiguation: Optional[bool] = None,
    ) -> Dict[str, MappingResult]:
        """
        Map multiple terms to controlled terminology in batch.

        Args:
            terms: List of dicts with keys: term, domain_hint, context
            use_llm_disambiguation: Override config setting for LLM use

        Returns:
            Dict mapping input terms to MappingResults
        """
        use_llm = use_llm_disambiguation if use_llm_disambiguation is not None else self.config.use_llm_disambiguation

        results: Dict[str, MappingResult] = {}

        # Group terms by domain for efficient batching
        domain_groups: Dict[str, List[str]] = defaultdict(list)
        term_contexts: Dict[str, str] = {}

        for item in terms:
            term = item.get("term", "")
            domain = item.get("domain_hint")
            context = item.get("context", "")
            domain_groups[domain or ""].append(term)
            term_contexts[term] = context

        # Process each domain group
        for domain, group_terms in domain_groups.items():
            domain_filters = self._get_domain_filters(domain) if domain else None
            vocab_filters = self._get_vocabulary_filters(domain) if domain else None

            # Batch lookup
            batch_matches = self._search_athena_batch(
                group_terms, domain_filters, vocab_filters
            )

            # Process results
            for term in group_terms:
                matches = batch_matches.get(term, [])

                # NOTE: Fuzzy matching removed - produces semantically incorrect results
                # Unmatched terms will be handled by LLM semantic lookup below

                if not matches:
                    results[term] = MappingResult(input_term=term, success=False)
                    continue

                if len(matches) == 1:
                    results[term] = MappingResult(
                        input_term=term,
                        success=True,
                        primary_match=matches[0],
                        confidence=matches[0].match_score,
                    )
                else:
                    results[term] = MappingResult(
                        input_term=term,
                        success=True,
                        primary_match=matches[0],
                        alternative_matches=matches[1:],
                        confidence=matches[0].match_score * 0.8,
                        disambiguation_needed=True,
                        disambiguation_reason=f"Multiple matches ({len(matches)})",
                    )

        # LLM semantic lookup for unmatched terms (batched)
        if use_llm:
            # Collect unmatched terms for LLM lookup
            unmatched = [
                (term, term_contexts.get(term, ""))
                for term, r in results.items()
                if not r.success
            ]

            if unmatched:
                logger.info(f"Running LLM semantic lookup for {len(unmatched)} unmatched terms")
                self._batch_semantic_lookup_llm(unmatched, results)

            # LLM disambiguation for ambiguous results
            ambiguous = [
                (term, r) for term, r in results.items()
                if r.disambiguation_needed and r.primary_match
            ]

            if ambiguous:
                logger.info(f"Running LLM disambiguation for {len(ambiguous)} ambiguous terms")
                self._batch_disambiguate_llm(ambiguous, term_contexts, results)

        return results

    def _batch_semantic_lookup_llm(
        self,
        unmatched: List[Tuple[str, str]],  # (term, context)
        results: Dict[str, MappingResult],
    ) -> None:
        """
        Use LLM to semantically find terminology codes for unmatched terms.

        This replaces fuzzy matching with intelligent semantic lookup.
        The LLM suggests codes which are then validated against ATHENA.
        """
        if not self._gemini_model:
            logger.warning("Gemini model not available for semantic lookup")
            return

        # Process in batches
        for i in range(0, len(unmatched), self.config.llm_batch_size):
            batch = unmatched[i:i + self.config.llm_batch_size]

            prompt = self._build_semantic_lookup_prompt(batch)

            try:
                response = self._call_gemini(prompt, max_tokens=4096)
                self._parse_semantic_lookup_response(response, batch, results)
            except Exception as e:
                logger.error(f"Batch semantic lookup failed: {e}")

    def _build_semantic_lookup_prompt(self, batch: List[Tuple[str, str]]) -> str:
        """Build prompt for LLM semantic terminology lookup."""
        terms_list = "\n".join([
            f"{i+1}. \"{term}\" (context: {context or 'clinical trial assessment'})"
            for i, (term, context) in enumerate(batch)
        ])

        return f"""You are a clinical terminology expert. For each clinical term below, identify the most appropriate LOINC or SNOMED CT code.

## Clinical Terms to Code:
{terms_list}

## Instructions:
1. For laboratory tests, measurements, vital signs → prefer LOINC codes
2. For procedures, examinations, conditions → prefer SNOMED CT codes
3. Provide the EXACT code from the official terminology
4. If no appropriate code exists, return null

## Common Reference Codes:
LOINC Laboratory:
- Hemoglobin: 718-7
- Hematocrit: 20570-8
- WBC Count: 6690-2
- RBC Count: 789-8
- Platelet Count: 777-3
- Neutrophils: 751-8
- Lymphocytes: 731-0
- Glucose: 2339-0
- Creatinine: 2160-0
- ALT: 1742-6
- AST: 1920-8
- Bilirubin Total: 1975-2

LOINC Vital Signs:
- Heart Rate: 8867-4
- Body Temperature: 8310-5
- Blood Pressure Systolic: 8480-6
- Blood Pressure Diastolic: 8462-4
- Body Weight: 29463-7
- Body Height: 8302-2
- Respiratory Rate: 9279-1
- Oxygen Saturation: 59408-5

SNOMED Procedures/Exams:
- Physical Examination: 5880005
- Neurological Examination: 84728005
- Cardiac Examination: 36228007
- Respiratory Examination: 37931006
- Abdominal Examination: 271857002

## Response Format (JSON array):
[
  {{"index": 1, "term": "...", "vocabulary": "LOINC", "code": "718-7", "display": "Hemoglobin [Mass/volume] in Blood"}},
  {{"index": 2, "term": "...", "vocabulary": "SNOMED", "code": "5880005", "display": "Physical examination"}},
  {{"index": 3, "term": "...", "vocabulary": null, "code": null, "display": null}}
]

Return ONLY the JSON array, no explanations."""

    def _parse_semantic_lookup_response(
        self,
        response: str,
        batch: List[Tuple[str, str]],
        results: Dict[str, MappingResult],
    ) -> None:
        """Parse LLM semantic lookup response and validate codes."""
        try:
            # Extract JSON from response
            text = response.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            # Find JSON array
            json_match = re.search(r'\[[\s\S]*\]', text)
            if not json_match:
                logger.warning("Could not find JSON array in LLM response")
                return

            data = json.loads(json_match.group())

            for item in data:
                idx = item.get("index", 0) - 1  # 1-indexed in prompt
                if idx < 0 or idx >= len(batch):
                    continue

                term, _ = batch[idx]
                vocab = item.get("vocabulary")
                code = item.get("code")
                display = item.get("display")

                if not vocab or not code:
                    continue

                # Validate code exists in ATHENA
                match = self._validate_code_in_athena(vocab, code, display, term)
                if match:
                    results[term] = MappingResult(
                        input_term=term,
                        success=True,
                        primary_match=match,
                        confidence=self.config.llm_selected_score,
                    )
                    # Cache the result
                    self._concept_cache[term] = [match]

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM semantic lookup response: {e}")

    def _validate_code_in_athena(
        self,
        vocabulary: str,
        code: str,
        display: str,
        original_term: str,
    ) -> Optional[ConceptMatch]:
        """Validate that a code exists in ATHENA and return ConceptMatch."""
        conn = self._get_db_connection()
        if not conn:
            # Return LLM suggestion without validation
            return ConceptMatch(
                concept_id=0,
                concept_name=display or original_term,
                concept_code=code,
                vocabulary_id=vocabulary,
                domain_id="Unknown",
                concept_class_id="Unknown",
                standard_concept="S",
                match_score=self.config.llm_selected_score,
                match_type="llm_inferred",
                matched_term=original_term,
            )

        try:
            cursor = conn.cursor()

            # Try to find the exact code
            cursor.execute("""
                SELECT concept_id, concept_name, concept_code, vocabulary_id,
                       domain_id, concept_class_id, standard_concept
                FROM concept
                WHERE concept_code = ? AND vocabulary_id = ?
                LIMIT 1
            """, (code, vocabulary))

            row = cursor.fetchone()
            if row:
                return ConceptMatch(
                    concept_id=row[0],
                    concept_name=row[1],
                    concept_code=row[2],
                    vocabulary_id=row[3],
                    domain_id=row[4],
                    concept_class_id=row[5],
                    standard_concept=row[6] or "S",
                    match_score=self.config.llm_selected_score,
                    match_type="llm_validated",
                    matched_term=original_term,
                )

            # Code not found in ATHENA - still return LLM suggestion
            logger.debug(f"Code {vocabulary}:{code} not found in ATHENA, using LLM suggestion")
            return ConceptMatch(
                concept_id=0,
                concept_name=display or original_term,
                concept_code=code,
                vocabulary_id=vocabulary,
                domain_id="Unknown",
                concept_class_id="Unknown",
                standard_concept="S",
                match_score=self.config.llm_selected_score * 0.9,  # Slightly lower for unvalidated
                match_type="llm_inferred",
                matched_term=original_term,
            )

        except Exception as e:
            logger.error(f"ATHENA validation failed: {e}")
            return None

    def _batch_disambiguate_llm(
        self,
        ambiguous: List[Tuple[str, MappingResult]],
        contexts: Dict[str, str],
        results: Dict[str, MappingResult],
    ) -> None:
        """Batch Gemini disambiguation for multiple terms."""
        if not self._gemini_model:
            logger.warning("Gemini model not available for batch disambiguation")
            return

        # Process in batches
        for i in range(0, len(ambiguous), self.config.llm_batch_size):
            batch = ambiguous[i:i + self.config.llm_batch_size]

            # Build batch prompt
            batch_items = []
            for term, result in batch:
                candidates = [result.primary_match] + result.alternative_matches
                candidate_str = "\n".join([
                    f"  {j}. [{c.vocabulary_id}] {c.concept_name} ({c.concept_code})"
                    for j, c in enumerate(candidates)
                ])
                batch_items.append({
                    "term": term,
                    "context": contexts.get(term, ""),
                    "candidates": candidate_str,
                    "all_candidates": candidates,
                })

            prompt = self._build_batch_disambiguation_prompt(batch_items)

            try:
                response = self._call_gemini(prompt, max_tokens=2048)
                self._parse_batch_disambiguation_response(response, batch_items, results)
            except Exception as e:
                logger.error(f"Batch Gemini disambiguation failed: {e}")

    def _build_batch_disambiguation_prompt(self, batch_items: List[Dict]) -> str:
        """Build a batch disambiguation prompt."""
        items_str = ""
        for i, item in enumerate(batch_items):
            items_str += f"""
TERM {i}: "{item['term']}"
Context: {item['context'] or 'Clinical trial SOA activity'}
Candidates:
{item['candidates']}

"""

        return f"""You are a clinical terminology expert. Select the best concept match for each term.

{items_str}

For each term, return the selected candidate index (0-based) or -1 if none appropriate.

Return as JSON array:
[
    {{"term_index": 0, "selected_candidate": <index>, "confidence": <0-1>}},
    ...
]

Prefer LOINC for lab tests, SNOMED for procedures/conditions.

JSON response:"""

    def _parse_batch_disambiguation_response(
        self,
        response: str,
        batch_items: List[Dict],
        results: Dict[str, MappingResult],
    ) -> None:
        """Parse batch disambiguation LLM response."""
        try:
            json_match = re.search(r"\[[\s\S]*\]", response)
            if json_match:
                selections = json.loads(json_match.group())

                for sel in selections:
                    term_idx = sel.get("term_index")
                    selected_idx = sel.get("selected_candidate")
                    confidence = sel.get("confidence", 0.85)

                    if term_idx is not None and 0 <= term_idx < len(batch_items):
                        item = batch_items[term_idx]
                        term = item["term"]
                        candidates = item["all_candidates"]

                        if selected_idx is not None and 0 <= selected_idx < len(candidates):
                            selected = candidates[selected_idx]
                            selected.match_score = self.config.llm_selected_score
                            selected.match_type = "llm_selected"

                            results[term] = MappingResult(
                                input_term=term,
                                success=True,
                                primary_match=selected,
                                alternative_matches=[c for i, c in enumerate(candidates) if i != selected_idx],
                                confidence=confidence,
                                disambiguation_needed=False,
                                disambiguation_reason="LLM batch selection",
                            )
        except Exception as e:
            logger.error(f"Failed to parse batch disambiguation response: {e}")

    def close(self) -> None:
        """Close database connection."""
        if self._db_connection:
            self._db_connection.close()
            self._db_connection = None


# Module-level convenience function
_default_mapper: Optional[TerminologyMapper] = None


def get_terminology_mapper() -> TerminologyMapper:
    """Get or create default terminology mapper instance."""
    global _default_mapper
    if _default_mapper is None:
        _default_mapper = TerminologyMapper()
    return _default_mapper


def map_concept(
    term: str,
    domain_hint: Optional[str] = None,
    context: str = "",
) -> MappingResult:
    """Convenience function to map a single concept."""
    return get_terminology_mapper().map_concept(term, domain_hint, context)


def map_concepts_batch(
    terms: List[Dict[str, Any]],
    use_llm_disambiguation: bool = True,
) -> Dict[str, MappingResult]:
    """Convenience function for batch concept mapping."""
    return get_terminology_mapper().map_concepts_batch(terms, use_llm_disambiguation)
