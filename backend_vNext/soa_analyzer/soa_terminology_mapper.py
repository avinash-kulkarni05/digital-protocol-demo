"""
SOA Terminology Mapper

Maps clinical procedure names to standardized terminologies:
- CDISC COSMoS concepts (5,148 concepts across 14 domains)
- OMOP/ATHENA concepts (9.7M concepts - LOINC, SNOMED, RxNorm)

Features:
- Exact and fuzzy matching with configurable thresholds
- Domain-specific vocabulary prioritization
- Synonym support from both CDISC alternativeNames and OMOP synonyms
- In-memory CDISC index for fast lookups
- Lazy-loaded OMOP connection (only when needed)

Usage:
    from soa_analyzer.soa_terminology_mapper import TerminologyMapper, get_mapper

    mapper = get_mapper()

    # Map a procedure name
    result = mapper.map("Hemoglobin")
    print(result.cdisc_code)   # "HGB"
    print(result.omop_concept_id)  # 3004501

    # Batch mapping
    results = mapper.map_batch(["Hemoglobin", "Blood Pressure", "ECG"])
"""

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default paths relative to soa_analyzer
DEFAULT_CDISC_PATH = Path(__file__).parent.parent / "config" / "cdisc_concepts.json"
DEFAULT_CODELISTS_PATH = Path(__file__).parent.parent / "config" / "cdisc_codelists.json"

# ATHENA database path - check multiple locations
_athena_candidates = [
    Path(__file__).parent.parent / "athena_concepts_full.db",  # backend_vNext/
    Path(__file__).parent.parent.parent / "athena_concepts_full.db",  # project root
]

DEFAULT_ATHENA_PATH = None
for candidate in _athena_candidates:
    if candidate.exists():
        # Verify it has the concept table
        try:
            import sqlite3
            conn = sqlite3.connect(str(candidate))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='concept'")
            if cursor.fetchone():
                DEFAULT_ATHENA_PATH = candidate
                conn.close()
                break
            conn.close()
        except:
            pass

if DEFAULT_ATHENA_PATH is None:
    # Fallback to parent directory if no valid database found
    DEFAULT_ATHENA_PATH = Path(__file__).parent.parent.parent / "athena_concepts_full.db"

# Default thresholds
DEFAULT_CDISC_THRESHOLD = 0.85
DEFAULT_OMOP_THRESHOLD = 0.80

# OMOP vocabulary priority by domain
VOCABULARY_PRIORITY = {
    "LB": ["LOINC", "SNOMED", "CDISC"],           # Labs
    "VS": ["LOINC", "SNOMED", "CDISC"],           # Vitals
    "EG": ["LOINC", "SNOMED", "CDISC"],           # ECG
    "PE": ["SNOMED", "LOINC", "CDISC"],           # Physical Exam
    "PR": ["SNOMED", "CPT4", "HCPCS", "CDISC"],   # Procedures
    "QS": ["SNOMED", "LOINC", "CDISC"],           # Questionnaires
    "PC": ["LOINC", "SNOMED", "CDISC"],           # Pharmacokinetics
    "PP": ["LOINC", "SNOMED", "CDISC"],           # Pharmacodynamics
}


@dataclass
class CDISCConcept:
    """Represents a CDISC COSMoS concept."""
    standardized_name: str
    cdisc_code: str
    domain: str
    concept_name: str
    specimen: Optional[str] = None
    method: Optional[str] = None
    alternative_names: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CDISCConcept":
        return cls(
            standardized_name=data.get("standardizedName", ""),
            cdisc_code=data.get("cdiscCode", ""),
            domain=data.get("domain", ""),
            concept_name=data.get("conceptName", ""),
            specimen=data.get("specimen"),
            method=data.get("method"),
            alternative_names=data.get("alternativeNames", []),
        )


@dataclass
class OMOPConcept:
    """Represents an OMOP/ATHENA concept."""
    concept_id: int
    concept_name: str
    domain_id: str
    vocabulary_id: str
    concept_class_id: Optional[str] = None
    concept_code: Optional[str] = None
    standard_concept: Optional[str] = None


@dataclass
class CodelistEntry:
    """Represents a CDISC Controlled Terminology codelist entry."""
    code: str
    decode: str
    codelist_name: str
    code_system: str
    synonyms: List[str] = field(default_factory=list)


@dataclass
class MappingResult:
    """Result of terminology mapping."""
    input_term: str
    normalized_term: str
    match_score: float
    match_type: str  # "exact", "fuzzy", "none"

    # CDISC mapping
    cdisc_code: Optional[str] = None
    cdisc_domain: Optional[str] = None
    cdisc_name: Optional[str] = None
    cdisc_specimen: Optional[str] = None
    cdisc_method: Optional[str] = None

    # OMOP mapping
    omop_concept_id: Optional[int] = None
    omop_concept_name: Optional[str] = None
    omop_vocabulary_id: Optional[str] = None
    omop_domain_id: Optional[str] = None
    omop_concept_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "input_term": self.input_term,
            "normalized_term": self.normalized_term,
            "match_score": self.match_score,
            "match_type": self.match_type,
            "cdisc": {
                "code": self.cdisc_code,
                "domain": self.cdisc_domain,
                "name": self.cdisc_name,
                "specimen": self.cdisc_specimen,
                "method": self.cdisc_method,
            } if self.cdisc_code else None,
            "omop": {
                "concept_id": self.omop_concept_id,
                "concept_name": self.omop_concept_name,
                "vocabulary_id": self.omop_vocabulary_id,
                "domain_id": self.omop_domain_id,
                "concept_code": self.omop_concept_code,
            } if self.omop_concept_id else None,
        }


def normalize_term(term: str) -> str:
    """Normalize a term for comparison."""
    if not term:
        return ""
    # Lowercase, strip, collapse whitespace
    normalized = " ".join(term.lower().strip().split())
    # Remove common suffixes that don't affect meaning
    suffixes = [" test", " measurement", " level", " value", " result", " exam"]
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
    return normalized


def fuzzy_match(term1: str, term2: str) -> float:
    """Compute fuzzy match score between two terms."""
    if not term1 or not term2:
        return 0.0
    return SequenceMatcher(None, normalize_term(term1), normalize_term(term2)).ratio()


class TerminologyMapper:
    """
    Maps clinical procedure names to CDISC and OMOP terminologies.

    Features:
    - Loads CDISC concepts into memory for fast lookups
    - Lazy-loads OMOP database connection
    - Supports exact and fuzzy matching
    - Domain-specific vocabulary prioritization
    """

    def __init__(
        self,
        cdisc_path: Optional[Path] = None,
        athena_path: Optional[Path] = None,
        cdisc_threshold: float = DEFAULT_CDISC_THRESHOLD,
        omop_threshold: float = DEFAULT_OMOP_THRESHOLD,
    ):
        """
        Initialize mapper.

        Args:
            cdisc_path: Path to cdisc_concepts.json
            athena_path: Path to athena_concepts_full.db
            cdisc_threshold: Fuzzy match threshold for CDISC (0.0-1.0)
            omop_threshold: Fuzzy match threshold for OMOP (0.0-1.0)
        """
        self.cdisc_path = cdisc_path or DEFAULT_CDISC_PATH
        self.athena_path = athena_path or DEFAULT_ATHENA_PATH
        self.cdisc_threshold = cdisc_threshold
        self.omop_threshold = omop_threshold

        # CDISC index (loaded on demand)
        self._cdisc_concepts: List[CDISCConcept] = []
        self._cdisc_index: Dict[str, CDISCConcept] = {}  # normalized name -> concept
        self._cdisc_loaded = False

        # CDISC Codelists index (loaded on demand)
        self._codelist_index: Dict[str, CodelistEntry] = {}  # normalized term -> entry
        self._codelists_loaded = False
        self.codelists_path = DEFAULT_CODELISTS_PATH

        # OMOP connection (lazy loaded)
        self._omop_conn: Optional[sqlite3.Connection] = None

        logger.info(f"TerminologyMapper initialized (CDISC: {self.cdisc_path}, OMOP: {self.athena_path})")

    def _load_cdisc(self):
        """Load CDISC concepts into memory."""
        if self._cdisc_loaded:
            return

        if not self.cdisc_path.exists():
            logger.warning(f"CDISC concepts file not found: {self.cdisc_path}")
            self._cdisc_loaded = True
            return

        try:
            with open(self.cdisc_path, 'r') as f:
                data = json.load(f)

            concepts_data = data.get("concepts", [])
            self._cdisc_concepts = [CDISCConcept.from_dict(c) for c in concepts_data]

            # Build index on normalized standardizedName + alternativeNames
            for concept in self._cdisc_concepts:
                # Index standardized name
                key = normalize_term(concept.standardized_name)
                if key:
                    self._cdisc_index[key] = concept

                # Index alternative names
                for alt in concept.alternative_names:
                    key = normalize_term(alt)
                    if key and key not in self._cdisc_index:
                        self._cdisc_index[key] = concept

            self._cdisc_loaded = True
            logger.info(f"Loaded {len(self._cdisc_concepts)} CDISC concepts ({len(self._cdisc_index)} indexed terms)")

        except Exception as e:
            logger.error(f"Failed to load CDISC concepts: {e}")
            self._cdisc_loaded = True

    def _load_codelists(self):
        """Load CDISC Controlled Terminology codelists into memory.

        This loads epoch types, visit types, and other terminology used in
        schedule/timeline/encounter naming.
        """
        if self._codelists_loaded:
            return

        if not self.codelists_path.exists():
            logger.warning(f"CDISC codelists file not found: {self.codelists_path}")
            self._codelists_loaded = True
            return

        try:
            with open(self.codelists_path, 'r') as f:
                data = json.load(f)

            codelists = data.get("codelists", {})

            for codelist_name, codelist_data in codelists.items():
                code_system = codelist_data.get("codeSystem", "")
                pairs = codelist_data.get("pairs", [])

                for pair in pairs:
                    code = pair.get("code", "")
                    decode = pair.get("decode", "")
                    synonyms = pair.get("synonyms", [])

                    entry = CodelistEntry(
                        code=code,
                        decode=decode,
                        codelist_name=codelist_name,
                        code_system=code_system,
                        synonyms=synonyms,
                    )

                    # Index by decode
                    key = normalize_term(decode)
                    if key:
                        self._codelist_index[key] = entry

                    # Index by synonyms
                    for synonym in synonyms:
                        key = normalize_term(synonym)
                        if key and key not in self._codelist_index:
                            self._codelist_index[key] = entry

            # Add special patterns for cycle/day visits
            # These map to Treatment epoch (C101526)
            treatment_entry = CodelistEntry(
                code="C101526",
                decode="Treatment",
                codelist_name="epoch_types",
                code_system="http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
                synonyms=["Cycle", "Day", "Week"],
            )
            # Index common cycle patterns
            for pattern in ["cycle", "day 1", "week 1", "treatment visit"]:
                key = normalize_term(pattern)
                if key and key not in self._codelist_index:
                    self._codelist_index[key] = treatment_entry

            # Add End of Treatment pattern
            eot_entry = CodelistEntry(
                code="C64917",
                decode="End of Treatment",
                codelist_name="epoch_types",
                code_system="http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
                synonyms=["EOT", "End Treatment", "Treatment End"],
            )
            for term in ["end of treatment", "eot", "end treatment", "treatment end"]:
                key = normalize_term(term)
                if key and key not in self._codelist_index:
                    self._codelist_index[key] = eot_entry

            # Add common SOA procedure/assessment terms not in COSMoS
            soa_terms = [
                # Vital Signs domain (VS)
                ("C54706", "Vital Signs", ["vitals", "vital signs measurement", "vital signs and oxygen saturation", "vital signs assessment"]),
                ("C49676", "Oxygen Saturation", ["spo2", "pulse oximetry", "oxygen saturation by pulse oximeter", "o2 sat"]),
                ("C38042", "Pulse Rate", ["pulse", "heart rate"]),
                ("C25299", "Body Temperature", ["temperature"]),
                # Eye Examinations (OE)
                ("C38101", "Visual Acuity", ["visual acuity test", "eye examination", "visual acuity and eye examination", "comprehensive eye examination"]),
                ("C62107", "Intraocular Pressure", ["iop", "intraocular pressure test"]),
                ("C51841", "Ophthalmologic Examination", ["ophthalmologic assessment", "fundoscopy", "slit-lamp examination", "slit lamp", "fundus examination"]),
                ("C96655", "Fluorescein Staining", ["fluorescein"]),
                # Infectious Disease Testing (MB)
                ("C16672", "HIV Testing", ["hiv test", "hiv, hbsag, hcv testing", "infectious disease testing", "hiv antibody"]),
                ("C16558", "Hepatitis B Testing", ["hbsag", "hepatitis b surface antigen"]),
                ("C16674", "Hepatitis C Testing", ["hcv", "hepatitis c antibody"]),
                # Patient Reported Outcomes (QS)
                ("C20993", "Patient Reported Outcome", ["pro", "pro questionnaire", "patient reported outcomes", "questionnaire collection"]),
                # Tumor Assessment (TU)
                ("C48612", "Tumor Biopsy", ["biopsy", "tumor biopsy", "pre-treatment tumor biopsy", "tissue biopsy"]),
                ("C18000", "Tumor Assessment", ["tumor imaging", "tumor evaluation", "ct scan", "mri scan", "brain imaging", "brain mri", "brain ct scan", "bone scan", "bone imaging", "pet scan", "18f fdg pet scan", "fdg pet"]),
                # Pregnancy Testing (PE)
                ("C92949", "Pregnancy Test", ["serum pregnancy test", "urine pregnancy test", "serum/urine pregnancy test"]),
                # Pharmacokinetics (PC)
                ("C62126", "Pharmacokinetic Sampling", ["pk sampling", "pk blood collection", "pk sample", "pharmacokinetic blood sample collection", "pharmacokinetic sampling collection timeline", "full sampling pharmacokinetic collection", "sparse sampling pharmacokinetic collection"]),
                # Drug Administration (EX)
                ("C38288", "Drug Administration", ["drug infusion", "study product administration", "docetaxel administration", "ds-1062a or docetaxel infusion", "study drug administration"]),
                # Adverse Events (AE)
                ("C41331", "Adverse Event", ["ae", "sae", "ae/sae", "adverse event monitoring", "ae/sae monitoring", "ae assessment"]),
                # ECG (EG)
                ("C38053", "ECG", ["electrocardiogram", "12-lead ecg", "ecg at screening"]),
                # Follow-up (MH/DS)
                ("C99158", "Survival Follow-up", ["survival follow-up", "survival contact", "long-term survival contact", "long-term survival", "safety follow-up"]),
            ]

            for code, decode, synonyms in soa_terms:
                entry = CodelistEntry(
                    code=code,
                    decode=decode,
                    codelist_name="soa_procedures",
                    code_system="http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
                    synonyms=synonyms,
                )
                # Index by decode
                key = normalize_term(decode)
                if key and key not in self._codelist_index:
                    self._codelist_index[key] = entry
                # Index by synonyms
                for syn in synonyms:
                    key = normalize_term(syn)
                    if key and key not in self._codelist_index:
                        self._codelist_index[key] = entry

            self._codelists_loaded = True
            logger.info(f"Loaded {len(self._codelist_index)} codelist terms")

        except Exception as e:
            logger.error(f"Failed to load CDISC codelists: {e}")
            self._codelists_loaded = True

    def _match_codelist(self, term: str) -> Optional[Tuple[CodelistEntry, float]]:
        """Try to match term against CDISC codelists.

        Handles:
        - Exact matches to epoch types (Screening, Follow-up, etc.)
        - Pattern matching for cycle/day visits
        - Synonym matching
        - Stripping timing suffixes (at Screening, at C1D1, etc.)
        """
        self._load_codelists()

        normalized = normalize_term(term)
        if not normalized:
            return None

        # Exact match
        if normalized in self._codelist_index:
            return self._codelist_index[normalized], 1.0

        # Strip timing suffixes and try again
        # Common patterns: "X at Screening", "X at C1D1", "X at End of Treatment", etc.
        timing_suffixes = [
            " at screening", " at baseline", " at end of treatment", " at eot",
            " at follow-up", " at follow up", " at followup",
            " at c1d1", " at c1d2", " at c1d4", " at c1d8", " at c1d15",
            " at c2d1", " at c3d1", " at c4d1",
            " collection", " assessment", " monitoring",
        ]
        stripped = normalized
        for suffix in timing_suffixes:
            if stripped.endswith(suffix):
                stripped = stripped[:-len(suffix)].strip()
                break

        if stripped != normalized and stripped in self._codelist_index:
            return self._codelist_index[stripped], 0.90

        # Pattern matching for cycle/day visits
        # "Cycle 1 Day 1", "Cycle 2 Day 8", etc. → Treatment
        if "cycle" in normalized:
            if "cycle" in self._codelist_index:
                return self._codelist_index["cycle"], 0.90

        # "Day 1", "Day 8", etc. → Treatment
        if normalized.startswith("day ") and len(normalized) < 10:
            if "day 1" in self._codelist_index:
                return self._codelist_index["day 1"], 0.85

        # "Week 1", "Week 4", etc. → Treatment
        if normalized.startswith("week "):
            if "week 1" in self._codelist_index:
                return self._codelist_index["week 1"], 0.85

        # Pattern matching for compound procedure names
        # E.g., "Full Sampling Pharmacokinetic Collection" → "Pharmacokinetic Sampling"
        # E.g., "AE/SAE Monitoring" → "Adverse Event"
        compound_patterns = [
            ("adverse event", ["ae", "sae", "ae/sae", "adverse event monitoring", "ae assessment"]),
            ("pharmacokinetic sampling", ["pk sampling", "pharmacokinetic collection", "full sampling pharmacokinetic", "sparse sampling pharmacokinetic"]),
            ("drug administration", ["study drug administration", "drug infusion", "infusion"]),
            ("survival follow-up", ["survival follow-up", "survival contact", "long-term survival"]),
            ("tumor assessment", ["brain imaging", "brain mri", "brain ct", "bone scan", "bone imaging", "pet scan", "fdg pet"]),
            ("ecg", ["ecg at", "12-lead ecg"]),
            ("pregnancy test", ["pregnancy test at"]),
            ("ophthalmologic examination", ["ophthalmologic assessment at"]),
            ("vital signs", ["vital signs assessment"]),
            ("tumor biopsy", ["tumor biopsy at"]),
            ("pro questionnaire", ["pro collection at"]),
        ]

        for base_term, patterns in compound_patterns:
            for pattern in patterns:
                if pattern in normalized:
                    if base_term in self._codelist_index:
                        return self._codelist_index[base_term], 0.85

        # Fuzzy match against codelist entries
        best_match = None
        best_score = 0.0

        for key, entry in self._codelist_index.items():
            score = fuzzy_match(term, entry.decode)
            if score > best_score:
                best_score = score
                best_match = entry

            for syn in entry.synonyms:
                score = fuzzy_match(term, syn)
                if score > best_score:
                    best_score = score
                    best_match = entry

        if best_match and best_score >= 0.75:  # Lowered threshold for better matching
            return best_match, best_score

        return None

    def _get_omop_connection(self) -> Optional[sqlite3.Connection]:
        """Get or create OMOP database connection."""
        if self._omop_conn is not None:
            return self._omop_conn

        if not self.athena_path.exists():
            logger.warning(f"ATHENA database not found: {self.athena_path}")
            return None

        try:
            self._omop_conn = sqlite3.connect(str(self.athena_path))
            self._omop_conn.row_factory = sqlite3.Row
            logger.info(f"Connected to ATHENA database: {self.athena_path}")
            return self._omop_conn
        except Exception as e:
            logger.error(f"Failed to connect to ATHENA database: {e}")
            return None

    def _match_cdisc_exact(self, term: str) -> Optional[Tuple[CDISCConcept, float]]:
        """Try exact match against CDISC index."""
        self._load_cdisc()
        key = normalize_term(term)
        if key in self._cdisc_index:
            return self._cdisc_index[key], 1.0
        return None

    def _match_cdisc_fuzzy(self, term: str) -> Optional[Tuple[CDISCConcept, float]]:
        """Try fuzzy match against CDISC concepts."""
        self._load_cdisc()
        if not self._cdisc_concepts:
            return None

        normalized = normalize_term(term)
        best_match = None
        best_score = 0.0

        for concept in self._cdisc_concepts:
            # Check standardized name
            score = fuzzy_match(term, concept.standardized_name)
            if score > best_score:
                best_score = score
                best_match = concept

            # Check alternative names
            for alt in concept.alternative_names:
                score = fuzzy_match(term, alt)
                if score > best_score:
                    best_score = score
                    best_match = concept

        if best_match and best_score >= self.cdisc_threshold:
            return best_match, best_score
        return None

    def _match_omop(
        self,
        term: str,
        domain: Optional[str] = None,
        limit: int = 5
    ) -> List[Tuple[OMOPConcept, float]]:
        """Search OMOP database for matching concepts."""
        conn = self._get_omop_connection()
        if not conn:
            return []

        cursor = conn.cursor()
        matches = []

        # Determine vocabulary priority
        vocabs = VOCABULARY_PRIORITY.get(domain, ["LOINC", "SNOMED", "CDISC"])

        try:
            # Search concept table directly
            normalized = normalize_term(term)
            search_term = f"%{normalized}%"

            # Priority-ordered search
            for vocab in vocabs:
                cursor.execute("""
                    SELECT concept_id, concept_name, domain_id, vocabulary_id,
                           concept_class_id, concept_code, standard_concept
                    FROM concept
                    WHERE vocabulary_id = ?
                      AND (LOWER(concept_name) LIKE ? OR concept_code = ?)
                      AND (standard_concept = 'S' OR standard_concept IS NULL)
                    ORDER BY LENGTH(concept_name)
                    LIMIT ?
                """, (vocab, search_term, term.upper(), limit))

                for row in cursor.fetchall():
                    concept = OMOPConcept(
                        concept_id=row["concept_id"],
                        concept_name=row["concept_name"],
                        domain_id=row["domain_id"],
                        vocabulary_id=row["vocabulary_id"],
                        concept_class_id=row["concept_class_id"],
                        concept_code=row["concept_code"],
                        standard_concept=row["standard_concept"],
                    )
                    score = fuzzy_match(term, concept.concept_name)
                    if score >= self.omop_threshold:
                        matches.append((concept, score))

                if matches:
                    break  # Stop at first vocabulary with matches

            # Also search synonyms if no matches yet
            if not matches:
                cursor.execute("""
                    SELECT c.concept_id, c.concept_name, c.domain_id, c.vocabulary_id,
                           c.concept_class_id, c.concept_code, c.standard_concept,
                           cs.concept_synonym_name
                    FROM concept_synonym cs
                    JOIN concept c ON cs.concept_id = c.concept_id
                    WHERE LOWER(cs.concept_synonym_name) LIKE ?
                      AND c.vocabulary_id IN (?, ?, ?)
                    LIMIT ?
                """, (search_term, *vocabs[:3], limit))

                for row in cursor.fetchall():
                    concept = OMOPConcept(
                        concept_id=row["concept_id"],
                        concept_name=row["concept_name"],
                        domain_id=row["domain_id"],
                        vocabulary_id=row["vocabulary_id"],
                        concept_class_id=row["concept_class_id"],
                        concept_code=row["concept_code"],
                        standard_concept=row["standard_concept"],
                    )
                    score = fuzzy_match(term, row["concept_synonym_name"])
                    if score >= self.omop_threshold:
                        matches.append((concept, score))

        except Exception as e:
            logger.error(f"OMOP search error for '{term}': {e}")

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:limit]

    def map(self, term: str, prefer_omop: bool = False) -> MappingResult:
        """
        Map a clinical term to CDISC and OMOP terminologies.

        Args:
            term: The clinical term to map (e.g., "Hemoglobin", "Blood Pressure")
            prefer_omop: If True, prioritize OMOP over CDISC for primary match

        Returns:
            MappingResult with CDISC and OMOP mappings
        """
        if not term:
            return MappingResult(
                input_term="",
                normalized_term="",
                match_score=0.0,
                match_type="none",
            )

        normalized = normalize_term(term)
        result = MappingResult(
            input_term=term,
            normalized_term=normalized,
            match_score=0.0,
            match_type="none",
        )

        # Step 1: Try CDISC exact match
        cdisc_match = self._match_cdisc_exact(term)
        if cdisc_match:
            concept, score = cdisc_match
            result.cdisc_code = concept.cdisc_code
            result.cdisc_domain = concept.domain
            result.cdisc_name = concept.standardized_name
            result.cdisc_specimen = concept.specimen
            result.cdisc_method = concept.method
            result.match_score = score
            result.match_type = "exact"

        # Step 2: Try CDISC fuzzy match if no exact match
        if not result.cdisc_code:
            cdisc_match = self._match_cdisc_fuzzy(term)
            if cdisc_match:
                concept, score = cdisc_match
                result.cdisc_code = concept.cdisc_code
                result.cdisc_domain = concept.domain
                result.cdisc_name = concept.standardized_name
                result.cdisc_specimen = concept.specimen
                result.cdisc_method = concept.method
                if score > result.match_score:
                    result.match_score = score
                    result.match_type = "fuzzy"

        # Step 3: Try OMOP lookup
        omop_matches = self._match_omop(term, domain=result.cdisc_domain)
        if omop_matches:
            concept, score = omop_matches[0]
            result.omop_concept_id = concept.concept_id
            result.omop_concept_name = concept.concept_name
            result.omop_vocabulary_id = concept.vocabulary_id
            result.omop_domain_id = concept.domain_id
            result.omop_concept_code = concept.concept_code

            # Update overall score if OMOP is better or preferred
            if prefer_omop or score > result.match_score:
                result.match_score = score
                result.match_type = "fuzzy" if score < 1.0 else "exact"

        return result

    def map_batch(
        self,
        terms: List[str],
        prefer_omop: bool = False
    ) -> List[MappingResult]:
        """
        Map multiple terms in batch.

        Args:
            terms: List of clinical terms to map
            prefer_omop: If True, prioritize OMOP over CDISC

        Returns:
            List of MappingResult objects
        """
        return [self.map(term, prefer_omop) for term in terms]

    def get_cdisc_domains(self) -> List[str]:
        """Get list of available CDISC domains."""
        self._load_cdisc()
        domains = set()
        for concept in self._cdisc_concepts:
            if concept.domain:
                domains.add(concept.domain)
        return sorted(domains)

    def get_cdisc_concepts_by_domain(self, domain: str) -> List[CDISCConcept]:
        """Get all CDISC concepts for a specific domain."""
        self._load_cdisc()
        return [c for c in self._cdisc_concepts if c.domain == domain]

    def search_cdisc(
        self,
        query: str,
        domain: Optional[str] = None,
        limit: int = 10
    ) -> List[Tuple[CDISCConcept, float]]:
        """
        Search CDISC concepts.

        Args:
            query: Search query
            domain: Optional domain filter
            limit: Maximum results

        Returns:
            List of (concept, score) tuples sorted by relevance
        """
        self._load_cdisc()
        results = []

        for concept in self._cdisc_concepts:
            if domain and concept.domain != domain:
                continue

            # Check standardized name
            score = fuzzy_match(query, concept.standardized_name)

            # Check alternatives
            for alt in concept.alternative_names:
                alt_score = fuzzy_match(query, alt)
                if alt_score > score:
                    score = alt_score

            if score >= self.cdisc_threshold:
                results.append((concept, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def search_omop(
        self,
        query: str,
        vocabulary: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 10
    ) -> List[Tuple[OMOPConcept, float]]:
        """
        Search OMOP concepts.

        Args:
            query: Search query
            vocabulary: Optional vocabulary filter (LOINC, SNOMED, etc.)
            domain: Optional domain filter
            limit: Maximum results

        Returns:
            List of (concept, score) tuples sorted by relevance
        """
        conn = self._get_omop_connection()
        if not conn:
            return []

        cursor = conn.cursor()
        results = []
        search_term = f"%{normalize_term(query)}%"

        try:
            sql = """
                SELECT concept_id, concept_name, domain_id, vocabulary_id,
                       concept_class_id, concept_code, standard_concept
                FROM concept
                WHERE LOWER(concept_name) LIKE ?
            """
            params = [search_term]

            if vocabulary:
                sql += " AND vocabulary_id = ?"
                params.append(vocabulary)

            if domain:
                sql += " AND domain_id = ?"
                params.append(domain)

            sql += " ORDER BY LENGTH(concept_name) LIMIT ?"
            params.append(limit * 2)  # Fetch more, then filter

            cursor.execute(sql, params)

            for row in cursor.fetchall():
                concept = OMOPConcept(
                    concept_id=row["concept_id"],
                    concept_name=row["concept_name"],
                    domain_id=row["domain_id"],
                    vocabulary_id=row["vocabulary_id"],
                    concept_class_id=row["concept_class_id"],
                    concept_code=row["concept_code"],
                    standard_concept=row["standard_concept"],
                )
                score = fuzzy_match(query, concept.concept_name)
                if score >= self.omop_threshold:
                    results.append((concept, score))

        except Exception as e:
            logger.error(f"OMOP search error: {e}")

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def stats(self) -> Dict[str, Any]:
        """Get mapper statistics."""
        self._load_cdisc()

        # Count by domain
        domains = {}
        for concept in self._cdisc_concepts:
            domain = concept.domain or "Unknown"
            domains[domain] = domains.get(domain, 0) + 1

        stats = {
            "cdisc_concepts": len(self._cdisc_concepts),
            "cdisc_indexed_terms": len(self._cdisc_index),
            "cdisc_domains": domains,
            "cdisc_threshold": self.cdisc_threshold,
            "omop_threshold": self.omop_threshold,
            "omop_connected": self._omop_conn is not None,
        }

        # Get OMOP stats if connected
        conn = self._get_omop_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM concept")
            stats["omop_total_concepts"] = cursor.fetchone()[0]

            cursor.execute("SELECT vocabulary_id, COUNT(*) FROM concept GROUP BY vocabulary_id ORDER BY COUNT(*) DESC LIMIT 10")
            stats["omop_top_vocabularies"] = {row[0]: row[1] for row in cursor.fetchall()}

        return stats

    def close(self):
        """Close database connection."""
        if self._omop_conn:
            self._omop_conn.close()
            self._omop_conn = None
            logger.info("Closed ATHENA database connection")


# Singleton instance
_mapper_instance: Optional[TerminologyMapper] = None


def get_mapper(
    cdisc_threshold: float = DEFAULT_CDISC_THRESHOLD,
    omop_threshold: float = DEFAULT_OMOP_THRESHOLD,
) -> TerminologyMapper:
    """
    Get the singleton mapper instance.

    Args:
        cdisc_threshold: Fuzzy match threshold for CDISC
        omop_threshold: Fuzzy match threshold for OMOP

    Returns:
        TerminologyMapper instance
    """
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = TerminologyMapper(
            cdisc_threshold=cdisc_threshold,
            omop_threshold=omop_threshold,
        )
    return _mapper_instance


def reset_mapper_instance():
    """Reset the singleton mapper instance."""
    global _mapper_instance
    if _mapper_instance:
        _mapper_instance.close()
    _mapper_instance = None


# CLI support
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    def print_usage():
        print("Usage: python soa_terminology_mapper.py [command] [args]")
        print("\nCommands:")
        print("  map TERM        Map a clinical term")
        print("  search QUERY    Search for concepts")
        print("  stats           Show mapper statistics")
        print("\nExamples:")
        print("  python soa_terminology_mapper.py map 'Hemoglobin'")
        print("  python soa_terminology_mapper.py search 'blood pressure'")
        sys.exit(1)

    if len(sys.argv) < 2:
        print_usage()

    mapper = get_mapper()
    command = sys.argv[1].lower()

    if command == "map":
        if len(sys.argv) < 3:
            print("Error: Term required")
            sys.exit(1)
        term = sys.argv[2]
        result = mapper.map(term)
        print(f"\nMapping: '{term}'")
        print("=" * 50)
        print(f"Match Score: {result.match_score:.2%}")
        print(f"Match Type: {result.match_type}")
        print(f"\nCDISC:")
        if result.cdisc_code:
            print(f"  Code: {result.cdisc_code}")
            print(f"  Domain: {result.cdisc_domain}")
            print(f"  Name: {result.cdisc_name}")
            print(f"  Specimen: {result.cdisc_specimen}")
            print(f"  Method: {result.cdisc_method}")
        else:
            print("  No match")
        print(f"\nOMOP:")
        if result.omop_concept_id:
            print(f"  Concept ID: {result.omop_concept_id}")
            print(f"  Name: {result.omop_concept_name}")
            print(f"  Vocabulary: {result.omop_vocabulary_id}")
            print(f"  Domain: {result.omop_domain_id}")
            print(f"  Code: {result.omop_concept_code}")
        else:
            print("  No match")

    elif command == "search":
        if len(sys.argv) < 3:
            print("Error: Query required")
            sys.exit(1)
        query = sys.argv[2]
        print(f"\nSearching CDISC for: '{query}'")
        print("=" * 50)
        cdisc_results = mapper.search_cdisc(query, limit=5)
        for concept, score in cdisc_results:
            print(f"  [{score:.2%}] {concept.cdisc_code} - {concept.standardized_name} ({concept.domain})")

        print(f"\nSearching OMOP for: '{query}'")
        print("=" * 50)
        omop_results = mapper.search_omop(query, limit=5)
        for concept, score in omop_results:
            print(f"  [{score:.2%}] {concept.concept_id} - {concept.concept_name} ({concept.vocabulary_id})")

    elif command == "stats":
        stats = mapper.stats()
        print("\nTerminology Mapper Statistics")
        print("=" * 50)
        print(f"CDISC Concepts: {stats['cdisc_concepts']:,}")
        print(f"CDISC Indexed Terms: {stats['cdisc_indexed_terms']:,}")
        print(f"CDISC Threshold: {stats['cdisc_threshold']}")
        print(f"OMOP Threshold: {stats['omop_threshold']}")
        if 'omop_total_concepts' in stats:
            print(f"OMOP Total Concepts: {stats['omop_total_concepts']:,}")
            print("\nTop OMOP Vocabularies:")
            for vocab, count in list(stats['omop_top_vocabularies'].items())[:5]:
                print(f"  {vocab}: {count:,}")
        print("\nCDISC Domains:")
        for domain, count in sorted(stats['cdisc_domains'].items()):
            print(f"  {domain}: {count}")

    else:
        print(f"Unknown command: {command}")
        print_usage()

    mapper.close()
