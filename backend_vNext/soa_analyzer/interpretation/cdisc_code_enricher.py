"""
CDISC Code Enrichment Service for SOA Pipeline

Provides intelligent CDISC code lookup for SOA activities using a multi-tier approach:
1. Exact/fuzzy match against curated activity mappings
2. Search NCI EVS concepts from cdisc_concepts.json
3. LLM-based inference for novel activities

Design Principles:
- Config-first: Leverage curated mappings before LLM
- Scalable: Cache results, batch LLM calls
- Generalizable: Works for any activity type

Usage:
    from soa_analyzer.interpretation.cdisc_code_enricher import CDISCCodeEnricher

    enricher = CDISCCodeEnricher()
    enriched_mapping = enricher.enrich_domain_mapping(domain_mapping)
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Config paths
CONFIG_DIR = Path(__file__).parent.parent / "config"
BACKEND_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


@dataclass
class CDISCCode:
    """Represents a CDISC code with metadata."""
    code: str  # NCI code (e.g., "C78713")
    decode: str  # Preferred term (e.g., "Complete Blood Count")
    vocabulary: str = "NCIt"  # NCI Thesaurus
    match_type: str = "exact"  # exact, fuzzy, nci_search, llm_inferred
    match_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "decode": self.decode,
            "vocabulary": self.vocabulary,
            "matchType": self.match_type,
            "matchScore": self.match_score,
        }


class CDISCCodeEnricher:
    """
    Multi-tier CDISC code enrichment service.

    Enriches SOA activities with accurate CDISC codes using:
    1. Curated activity mappings (activity_domain_map.json)
    2. NCI EVS search (cdisc_concepts.json)
    3. LLM inference (Gemini 2.5 Pro)
    """

    def __init__(self, use_llm_fallback: bool = True):
        """
        Initialize enricher with config files.

        Args:
            use_llm_fallback: Whether to use LLM for activities not found in configs
        """
        self.use_llm_fallback = use_llm_fallback
        self._gemini_model = None

        # Loaded config data
        self._activity_examples: Dict[str, Dict] = {}
        self._domain_codes: Dict[str, str] = {}
        self._domain_keywords: Dict[str, List[str]] = {}
        self._nci_concepts: Optional[Dict[str, Dict]] = None  # Lazy loaded
        self._synonym_index: Dict[str, str] = {}  # Normalized name → code

        # Load configs
        self._load_activity_domain_map()
        self._load_cdisc_codelists()
        self._init_gemini()

    def _load_activity_domain_map(self) -> None:
        """Load activity to domain mapping with CDISC codes."""
        config_path = CONFIG_DIR / "activity_domain_map.json"
        if not config_path.exists():
            logger.warning(f"activity_domain_map.json not found at {config_path}")
            return

        try:
            with open(config_path) as f:
                data = json.load(f)

            # Load domain codes
            for domain_code, domain_info in data.get("domains", {}).items():
                self._domain_codes[domain_code] = domain_info.get("cdisc_code", "")
                self._domain_keywords[domain_code] = domain_info.get("keywords", [])

            # Load activity examples with codes
            for activity_name, mapping in data.get("activity_examples", {}).items():
                # Skip comment entries
                if activity_name.startswith("_"):
                    continue
                if not isinstance(mapping, dict):
                    continue

                self._activity_examples[activity_name.lower()] = {
                    "domain": mapping.get("domain"),
                    "code": mapping.get("code"),
                    "decode": mapping.get("decode"),
                }
                # Index by normalized name
                self._synonym_index[self._normalize_name(activity_name)] = mapping.get("code", "")

            logger.info(
                f"Loaded {len(self._activity_examples)} activity examples, "
                f"{len(self._domain_codes)} domain codes"
            )
        except Exception as e:
            logger.error(f"Failed to load activity_domain_map.json: {e}")

    def _load_cdisc_codelists(self) -> None:
        """Load CDISC codelists for additional mappings."""
        codelist_path = BACKEND_CONFIG_DIR / "cdisc_codelists.json"
        if not codelist_path.exists():
            return

        try:
            with open(codelist_path) as f:
                data = json.load(f)

            # Index synonyms from codelists
            for codelist_name, codelist in data.get("codelists", {}).items():
                for pair in codelist.get("pairs", []):
                    code = pair.get("code", "")
                    decode = pair.get("decode", "")
                    synonyms = pair.get("synonyms", [])

                    # Index decode
                    self._synonym_index[self._normalize_name(decode)] = code

                    # Index synonyms
                    for syn in synonyms:
                        self._synonym_index[self._normalize_name(syn)] = code

            logger.info(f"Loaded {len(self._synonym_index)} CDISC synonyms")
        except Exception as e:
            logger.warning(f"Failed to load cdisc_codelists.json: {e}")

    def _load_nci_concepts(self) -> None:
        """Lazy load NCI EVS concepts (large file)."""
        if self._nci_concepts is not None:
            return

        concepts_path = BACKEND_CONFIG_DIR / "cdisc_concepts.json"
        if not concepts_path.exists():
            logger.warning("cdisc_concepts.json not found")
            self._nci_concepts = {}
            return

        try:
            logger.info("Loading NCI EVS concepts (this may take a moment)...")
            with open(concepts_path) as f:
                self._nci_concepts = json.load(f)
            logger.info(f"Loaded {len(self._nci_concepts)} NCI concepts")
        except Exception as e:
            logger.error(f"Failed to load NCI concepts: {e}")
            self._nci_concepts = {}

    def _init_gemini(self) -> None:
        """Initialize Gemini model for LLM fallback."""
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and self.use_llm_fallback:
            genai.configure(api_key=api_key)
            self._gemini_model = genai.GenerativeModel(
                model_name="gemini-2.5-pro",
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 4096,
                }
            )
            logger.info("Initialized Gemini 2.5 Pro for CDISC code inference")

    def _normalize_name(self, name: str) -> str:
        """Normalize activity name for matching."""
        if not name:
            return ""
        # Lowercase
        normalized = name.lower().strip()
        # Remove parenthetical notes
        normalized = re.sub(r'\s*\([^)]*\)\s*', ' ', normalized)
        # Remove special characters
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        # Collapse whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _lookup_from_config(
        self,
        activity_name: str,
        domain: str,
    ) -> Optional[CDISCCode]:
        """
        Tier 1: Lookup CDISC code from curated config files.

        Tries:
        1. Exact match on activity name
        2. Fuzzy match using normalized names
        3. Domain code fallback
        """
        normalized = self._normalize_name(activity_name)

        # 1. Exact match in activity examples
        if activity_name.lower() in self._activity_examples:
            example = self._activity_examples[activity_name.lower()]
            if example.get("code"):
                return CDISCCode(
                    code=example["code"],
                    decode=example.get("decode", activity_name),
                    match_type="exact",
                    match_score=1.0,
                )

        # 2. Normalized match in activity examples
        for example_name, example in self._activity_examples.items():
            if self._normalize_name(example_name) == normalized:
                if example.get("code"):
                    return CDISCCode(
                        code=example["code"],
                        decode=example.get("decode", activity_name),
                        match_type="exact",
                        match_score=0.95,
                    )

        # 3. Partial match (activity name contains example or vice versa)
        for example_name, example in self._activity_examples.items():
            example_normalized = self._normalize_name(example_name)
            if example_normalized in normalized or normalized in example_normalized:
                if example.get("code"):
                    return CDISCCode(
                        code=example["code"],
                        decode=example.get("decode", activity_name),
                        match_type="fuzzy",
                        match_score=0.85,
                    )

        # 4. Check synonym index
        if normalized in self._synonym_index:
            code = self._synonym_index[normalized]
            if code:
                return CDISCCode(
                    code=code,
                    decode=activity_name,
                    match_type="synonym",
                    match_score=0.90,
                )

        # 5. Keyword-based matching
        for domain_code, keywords in self._domain_keywords.items():
            if domain_code == domain:
                for keyword in keywords:
                    if keyword.lower() in normalized:
                        domain_cdisc = self._domain_codes.get(domain)
                        if domain_cdisc:
                            return CDISCCode(
                                code=domain_cdisc,
                                decode=f"{self._get_domain_name(domain)} Assessment",
                                match_type="keyword",
                                match_score=0.75,
                            )
                        break

        # 6. Domain code fallback
        if domain and domain in self._domain_codes:
            domain_code = self._domain_codes[domain]
            if domain_code:
                return CDISCCode(
                    code=domain_code,
                    decode=self._get_domain_name(domain),
                    match_type="domain_fallback",
                    match_score=0.70,
                )

        return None

    def _get_domain_name(self, domain: str) -> str:
        """Get human-readable domain name."""
        domain_names = {
            "LB": "Laboratory Test",
            "VS": "Vital Signs",
            "EG": "Electrocardiogram",
            "PE": "Physical Examination",
            "QS": "Questionnaire",
            "MI": "Medical Imaging",
            "CM": "Concomitant Medication",
            "AE": "Adverse Event",
            "EX": "Exposure",
            "BS": "Biospecimen Collection",
            "DM": "Demographics",
            "MH": "Medical History",
            "DS": "Disposition",
            "PR": "Procedure",
            "TU": "Tumor Assessment",
            "PC": "Pharmacokinetics",
        }
        return domain_names.get(domain, domain)

    def _search_nci_evs(
        self,
        activity_name: str,
        domain: str,
    ) -> Optional[CDISCCode]:
        """
        Tier 2: Search NCI EVS concepts for matching codes.

        Searches the cdisc_concepts.json file for relevant concepts.
        """
        self._load_nci_concepts()

        if not self._nci_concepts:
            return None

        normalized = self._normalize_name(activity_name)
        best_match = None
        best_score = 0.0

        # Search through concepts
        for concept_code, concept_data in self._nci_concepts.items():
            if not isinstance(concept_data, dict):
                continue

            concept_name = concept_data.get("name", "")
            concept_normalized = self._normalize_name(concept_name)

            # Exact match
            if concept_normalized == normalized:
                return CDISCCode(
                    code=concept_code,
                    decode=concept_name,
                    match_type="nci_exact",
                    match_score=0.95,
                )

            # Partial match
            if normalized in concept_normalized or concept_normalized in normalized:
                score = len(normalized) / max(len(concept_normalized), 1)
                if score > best_score and score > 0.5:
                    best_score = score
                    best_match = CDISCCode(
                        code=concept_code,
                        decode=concept_name,
                        match_type="nci_fuzzy",
                        match_score=0.80 * score,
                    )

            # Check synonyms
            for synonym in concept_data.get("synonyms", []):
                syn_normalized = self._normalize_name(synonym)
                if syn_normalized == normalized:
                    return CDISCCode(
                        code=concept_code,
                        decode=concept_name,
                        match_type="nci_synonym",
                        match_score=0.90,
                    )

        return best_match

    def _infer_with_llm(
        self,
        activities: List[Tuple[str, str, str]],  # (id, name, domain)
    ) -> Dict[str, CDISCCode]:
        """
        Tier 3: Use LLM to infer CDISC codes for unknown activities.

        Batches multiple activities for efficiency.
        """
        if not self._gemini_model or not activities:
            return {}

        # Build prompt
        activities_list = "\n".join([
            f"- {aid}: \"{name}\" (domain: {domain})"
            for aid, name, domain in activities
        ])

        prompt = f"""You are a CDISC terminology expert. For each clinical trial activity below, provide the most appropriate NCI Thesaurus code.

ACTIVITIES:
{activities_list}

For each activity, provide:
1. The NCI Thesaurus code (format: Cxxxxx) - MUST be a valid NCI code
2. The preferred term (CDISC decode)

Common CDISC codes for reference:
- C78713: Complete Blood Count (Hematology)
- C62637: Serum Chemistry (Chemistry Panel)
- C54706: Vital Signs
- C83167: Electrocardiogram (ECG)
- C62596: Physical Examination
- C62737: Questionnaire
- C38101: Computed Tomography
- C40678: Magnetic Resonance Imaging
- C41331: Adverse Event
- C62597: Exposure (Drug Administration)
- C63505: Biospecimen Collection
- C16735: Informed Consent
- C62599: Medical History
- C25717: Survival
- C62735: Pharmacokinetics
- C105721: ECOG Performance Status
- C71563: Pregnancy Test
- C62736: Urinalysis
- C94531: Tumor Assessment

Return JSON array:
[
  {{"activityId": "ACT-001", "code": "C78713", "decode": "Complete Blood Count"}},
  ...
]

IMPORTANT: Only return valid NCI codes. If truly uncertain, use the domain-level code from the reference list above.

JSON response:"""

        try:
            response = self._gemini_model.generate_content(prompt)
            text = response.text.strip()

            # Parse JSON
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            # Find JSON array
            json_match = re.search(r'\[[\s\S]*\]', text)
            if json_match:
                data = json.loads(json_match.group())
                results = {}
                for item in data:
                    aid = item.get("activityId")
                    code = item.get("code")
                    decode = item.get("decode")
                    if aid and code:
                        results[aid] = CDISCCode(
                            code=code,
                            decode=decode or "Unknown",
                            match_type="llm_inferred",
                            match_score=0.80,
                        )
                return results

        except Exception as e:
            logger.error(f"LLM CDISC code inference failed: {e}")

        return {}

    def enrich_domain_mapping(
        self,
        mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Enrich a single domain mapping with CDISC code.

        Args:
            mapping: Domain mapping dict with activityId, activityName, cdashDomain

        Returns:
            Enriched mapping with cdiscCode and cdiscDecode
        """
        activity_name = mapping.get("activityName", "")
        domain = mapping.get("cdashDomain", "")
        existing_code = mapping.get("cdiscCode")

        # Skip if already has code
        if existing_code:
            return mapping

        # Tier 1: Config lookup
        code = self._lookup_from_config(activity_name, domain)

        # Tier 2: NCI EVS search (if tier 1 failed or low confidence)
        if not code or code.match_score < 0.80:
            nci_code = self._search_nci_evs(activity_name, domain)
            if nci_code and (not code or nci_code.match_score > code.match_score):
                code = nci_code

        if code:
            mapping["cdiscCode"] = code.code
            mapping["cdiscDecode"] = code.decode
            mapping["_codeMetadata"] = {
                "matchType": code.match_type,
                "matchScore": code.match_score,
            }

        return mapping

    def enrich_batch(
        self,
        mappings: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Enrich multiple domain mappings with CDISC codes.

        Uses batched LLM inference for activities not found in configs.

        Args:
            mappings: List of domain mapping dicts

        Returns:
            List of enriched mappings
        """
        results = []
        needs_llm: List[Tuple[str, str, str]] = []

        # First pass: config-based lookup
        for mapping in mappings:
            enriched = self.enrich_domain_mapping(mapping.copy())
            results.append(enriched)

            # Track activities needing LLM
            if not enriched.get("cdiscCode"):
                needs_llm.append((
                    enriched.get("activityId", ""),
                    enriched.get("activityName", ""),
                    enriched.get("cdashDomain", ""),
                ))

        # Second pass: LLM inference for missing codes
        if needs_llm and self.use_llm_fallback:
            logger.info(f"Using LLM to infer CDISC codes for {len(needs_llm)} activities")
            llm_codes = self._infer_with_llm(needs_llm)

            for result in results:
                aid = result.get("activityId")
                if aid in llm_codes and not result.get("cdiscCode"):
                    code = llm_codes[aid]
                    result["cdiscCode"] = code.code
                    result["cdiscDecode"] = code.decode
                    result["_codeMetadata"] = {
                        "matchType": code.match_type,
                        "matchScore": code.match_score,
                    }

        # Stats
        with_code = sum(1 for r in results if r.get("cdiscCode"))
        logger.info(f"CDISC code enrichment: {with_code}/{len(results)} activities have codes")

        return results


def enrich_stage1_with_cdisc_codes(
    stage1_result: Dict[str, Any],
    use_llm_fallback: bool = True,
) -> Dict[str, Any]:
    """
    Convenience function to enrich Stage 1 results with CDISC codes.

    Args:
        stage1_result: Stage 1 domain categorization result
        use_llm_fallback: Whether to use LLM for unknown activities

    Returns:
        Enriched Stage 1 result
    """
    enricher = CDISCCodeEnricher(use_llm_fallback=use_llm_fallback)

    mappings = stage1_result.get("mappings", [])
    enriched_mappings = enricher.enrich_batch(mappings)

    stage1_result["mappings"] = enriched_mappings

    # Update metrics
    with_code = sum(1 for m in enriched_mappings if m.get("cdiscCode"))
    stage1_result["metrics"]["withCdiscCode"] = with_code
    stage1_result["metrics"]["cdiscCodeCoverage"] = with_code / max(len(enriched_mappings), 1)

    return stage1_result
