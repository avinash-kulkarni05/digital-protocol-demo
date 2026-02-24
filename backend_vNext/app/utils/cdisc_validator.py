"""
CDISC Controlled Terminology Validator.

Validates extracted data against official CDISC CT from NCI EVS.
Uses both official terminology files and curated synonyms.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import yaml

from .cdisc_ct_parser import CDISCTerminologyParser

logger = logging.getLogger(__name__)


class CDISCTerminologyValidator:
    """
    Validates codes against official CDISC Controlled Terminology.

    Uses two sources:
    1. Official NCI EVS Protocol Terminology (downloaded)
    2. Curated cdisc_vocab.yaml (for synonyms and additional domains)

    Features:
    - Recursive traversal to find all code/decode pairs
    - Domain inference from field names
    - Expanded field coverage (15+ domains)
    """

    # Mapping from extraction field domains to official codelist names
    DOMAIN_TO_CODELIST = {
        "study_phase": "Trial Phase Response",
        "trial_phase": "Trial Phase Response",
        "study_type": "Study Type Response",
        "trial_type": "Trial Type Response",
        "blinding": "Trial Blinding Schema Response",
        "intervention_model": "Intervention Model Response",
        "intervention_type": "Intervention Type Response",
        "endpoint_type": "Endpoint Type Value Set Terminology",
        # These are in curated vocab only (not in Protocol CT)
        "sex": None,  # Use curated vocab
        "arm_types": None,  # Use curated vocab
        "epoch_types": None,  # Use curated vocab
        "objective_level": None,  # Use curated vocab
        "endpoint_level": None,  # Use curated vocab
        "population_type": None,  # Use curated vocab
        "route_of_administration": None,  # Use curated vocab
        "outcome_type": None,  # Use curated vocab
        "ice_strategy": None,  # Use curated vocab
        "summary_measure": None,  # Use curated vocab
        "estimand_arm_type": None,  # Use curated vocab
        "dose_calculation_basis": None,  # Use curated vocab
    }

    # Mapping from domain names to centralized codelist keys (cdisc_codelists.json)
    # These domains use the new centralized config as primary source
    DOMAIN_TO_CENTRALIZED_CODELIST = {
        "arm_types": "arm_types",
        "epoch_types": "epoch_types",
        "design_types": "design_types",
        "study_phase": "study_phase",
        "study_type": "study_type",
        "sex": "sex",
        "blinding": "blinding",
        "objective_level": "objective_level",
        "endpoint_level": "endpoint_level",
        "outcome_type": "outcome_type",
        "population_type": "population_type",
        "route_of_administration": "route_of_administration",
        "ice_strategy": "ice_strategy",
        "summary_measure": "summary_measure",
        # Specimen domains (Stage 5)
        "specimen_category": "specimen_category",
        "specimen_subtype": "specimen_subtype",
        "tube_type": "tube_type",
        "specimen_purpose": "specimen_purpose",
    }

    # Mapping from field names to validation domains
    # Used for recursive domain inference
    FIELD_TO_DOMAIN = {
        # Study-level fields
        "studyPhase": "study_phase",
        "studyType": "study_type",
        "trialPhase": "trial_phase",
        "trialType": "trial_type",
        # Design fields
        "blindingType": "blinding",
        "blinding": "blinding",
        "interventionModel": "intervention_model",
        "interventionType": "intervention_type",
        # Arm fields
        "armType": "arm_types",
        "arm_type": "arm_types",
        # Endpoint/Objective fields
        "level": "endpoint_level",  # Context-dependent, could be objective_level
        "endpointLevel": "endpoint_level",
        "objectiveLevel": "objective_level",
        "endpointType": "endpoint_type",
        "outcomeType": "outcome_type",
        # Population fields
        "populationType": "population_type",
        "analysisPopulation": "population_type",
        "sex": "sex",
        # Treatment fields
        "route": "route_of_administration",
        "routeOfAdministration": "route_of_administration",
        "doseCalculationBasis": "dose_calculation_basis",
        "doseBasis": "dose_calculation_basis",
        # Epoch fields
        "epochType": "epoch_types",
        "epoch": "epoch_types",
        # Estimand fields
        "iceStrategy": "ice_strategy",
        "intercurrentEventStrategy": "ice_strategy",
        "summaryMeasure": "summary_measure",
        "estimandArmType": "estimand_arm_type",
        # Specimen fields (Stage 5)
        "specimenType": "specimen_subtype",
        "specimenCategory": "specimen_category",
        "collectionContainer": "tube_type",
        "tubeType": "tube_type",
        "purpose": "specimen_purpose",
        "specimenPurpose": "specimen_purpose",
    }

    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize the validator.

        Args:
            config_dir: Path to config directory containing vocabulary files
        """
        if config_dir is None:
            # Default to backend_vNext/config relative to this file
            config_dir = Path(__file__).parent.parent.parent / "config"
        else:
            config_dir = Path(config_dir)

        self.config_dir = config_dir
        self.parser = CDISCTerminologyParser()
        self.official_ct: Dict[str, Dict] = {}
        self.curated_vocab: Dict[str, Any] = {}
        self.centralized_codelists: Dict[str, Any] = {}  # New: cdisc_codelists.json

        self._load_vocabularies()

    def _load_vocabularies(self) -> None:
        """Load official CT, curated vocabulary, and centralized codelists files."""
        # Load centralized codelists (PRIMARY SOURCE for arms, epochs, design types)
        codelists_file = self.config_dir / "cdisc_codelists.json"
        if codelists_file.exists():
            with open(codelists_file, 'r') as f:
                self.centralized_codelists = json.load(f)
            codelist_count = len(self.centralized_codelists.get("codelists", {}))
            logger.info(f"Loaded {codelist_count} centralized CDISC codelists from {codelists_file}")
        else:
            logger.warning(f"Centralized codelists file not found: {codelists_file}")

        # Load official NCI EVS Protocol Terminology
        ct_file = self.config_dir / "cdisc_protocol_terminology.txt"
        if ct_file.exists():
            self.official_ct = self.parser.parse_file(str(ct_file))
            logger.info(f"Loaded {len(self.official_ct)} official CDISC codelists")
        else:
            logger.warning(f"Official CT file not found: {ct_file}")

        # Load curated vocabulary (DEPRECATED - being replaced by cdisc_codelists.json)
        vocab_file = self.config_dir / "cdisc_vocab.yaml"
        if vocab_file.exists():
            with open(vocab_file, 'r') as f:
                self.curated_vocab = yaml.safe_load(f)
            logger.info(f"Loaded curated vocabulary from {vocab_file}")
        else:
            logger.warning(f"Curated vocab file not found: {vocab_file}")

    def _get_centralized_codelist(self, domain: str) -> Optional[Dict]:
        """
        Get codelist from centralized cdisc_codelists.json.

        Args:
            domain: Domain name (e.g., "arm_types", "epoch_types")

        Returns:
            Codelist dict with 'pairs' array, or None if not found
        """
        codelist_key = self.DOMAIN_TO_CENTRALIZED_CODELIST.get(domain)
        if not codelist_key:
            return None

        codelists = self.centralized_codelists.get("codelists", {})
        return codelists.get(codelist_key)

    def validate_code(
        self,
        code: str,
        domain: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if an NCI code is valid for a domain.

        Args:
            code: NCI code (e.g., "C49686")
            domain: Domain name (e.g., "study_phase", "sex")

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check centralized codelists first (PRIMARY for arm_types, epoch_types, design_types)
        centralized = self._get_centralized_codelist(domain)
        if centralized:
            pairs = centralized.get("pairs", [])
            valid_codes = [p.get("code") for p in pairs]
            if code in valid_codes:
                return True, None
            return False, f"Invalid code '{code}' for domain '{domain}'. Valid codes: {valid_codes}"

        # Check official CT second
        codelist_name = self.DOMAIN_TO_CODELIST.get(domain)
        if codelist_name and self.official_ct:
            is_valid, error = self.parser.validate_code(code, codelist_name)
            if is_valid:
                return True, None
            # Fall through to check curated vocab

        # Check curated vocabulary (fallback)
        domain_vocab = self.curated_vocab.get(domain, {})
        valid_codes = domain_vocab.get("valid_codes", [])

        for vc in valid_codes:
            if vc.get("code") == code:
                return True, None

        # Check code synonyms in curated vocab
        code_synonyms = domain_vocab.get("code_synonyms", {})
        if code in code_synonyms:
            # Code is a synonym, valid but should use canonical
            canonical = code_synonyms[code]
            return True, f"Code '{code}' is valid but deprecated. Use '{canonical}' instead."

        # Build error message
        all_valid = [vc.get("code") for vc in valid_codes]
        if not all_valid and codelist_name:
            return False, f"Unknown domain '{domain}' and no official codelist found"

        return False, f"Invalid code '{code}' for domain '{domain}'. Valid codes: {all_valid[:5]}{'...' if len(all_valid) > 5 else ''}"

    def validate_decode(
        self,
        decode: str,
        domain: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate a decode value and return its canonical form.

        Args:
            decode: Decode value (e.g., "Phase 3", "Phase III")
            domain: Domain name

        Returns:
            Tuple of (is_valid, canonical_decode, error_message)
        """
        # Check centralized codelists first (PRIMARY for arm_types, epoch_types, design_types)
        centralized = self._get_centralized_codelist(domain)
        if centralized:
            pairs = centralized.get("pairs", [])
            # Check exact decode match
            for pair in pairs:
                if pair.get("decode", "").lower() == decode.lower():
                    return True, pair["decode"], None
            # Check synonyms
            for pair in pairs:
                for syn in pair.get("synonyms", []):
                    if syn.lower() == decode.lower():
                        return True, pair["decode"], None
            # Not found in centralized
            valid_decodes = [p.get("decode") for p in pairs]
            return False, None, f"Invalid decode '{decode}' for domain '{domain}'. Valid decodes: {valid_decodes}"

        # Check official CT second
        codelist_name = self.DOMAIN_TO_CODELIST.get(domain)
        if codelist_name and self.official_ct:
            codelist = self.parser.get_codelist_by_name(codelist_name)
            if codelist:
                for term in codelist.get("terms", []):
                    # Check submission value
                    if term["submission_value"].lower() == decode.lower():
                        return True, term["submission_value"], None
                    # Check synonyms
                    for syn in term.get("synonyms", []):
                        if syn.lower() == decode.lower():
                            return True, term["submission_value"], None
                    # Check NCI term
                    if term.get("nci_term", "").lower() == decode.lower():
                        return True, term["submission_value"], None

        # Check curated vocabulary (fallback)
        domain_vocab = self.curated_vocab.get(domain, {})

        # Check valid codes for exact decode match
        for vc in domain_vocab.get("valid_codes", []):
            if vc.get("decode", "").lower() == decode.lower():
                return True, vc["decode"], None

        # Check decode synonyms
        decode_synonyms = domain_vocab.get("decode_synonyms", {})
        if decode in decode_synonyms:
            canonical = decode_synonyms[decode]
            return True, canonical, None

        # Case-insensitive synonym check
        for syn, canonical in decode_synonyms.items():
            if syn.lower() == decode.lower():
                return True, canonical, None

        return False, None, f"Invalid decode '{decode}' for domain '{domain}'"

    def validate_code_decode_pair(
        self,
        code: str,
        decode: str,
        domain: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that a code/decode pair is consistent.

        Args:
            code: NCI code
            decode: Decode value
            domain: Domain name

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check centralized codelists first (PRIMARY for arm_types, epoch_types, design_types)
        centralized = self._get_centralized_codelist(domain)
        if centralized:
            pairs = centralized.get("pairs", [])
            for pair in pairs:
                if pair.get("code") == code:
                    expected_decode = pair.get("decode")
                    # Check exact match
                    if expected_decode.lower() == decode.lower():
                        return True, None
                    # Check if decode is a synonym
                    synonyms = pair.get("synonyms", [])
                    for syn in synonyms:
                        if syn.lower() == decode.lower():
                            return True, None
                    # Mismatch
                    return False, f"Code '{code}' has decode '{expected_decode}', not '{decode}'. Valid synonyms: {synonyms}"
            # Code not found in centralized
            valid_codes = [p.get("code") for p in pairs]
            return False, f"Code '{code}' not found in domain '{domain}'. Valid codes: {valid_codes}"

        # Get curated vocab decode_synonyms for normalization
        domain_vocab = self.curated_vocab.get(domain, {})
        decode_synonyms = domain_vocab.get("decode_synonyms", {})

        # Normalize decode using curated synonyms (e.g., "Phase 3" -> "PHASE III TRIAL")
        normalized_decode = decode
        for syn, canonical in decode_synonyms.items():
            if syn.lower() == decode.lower():
                normalized_decode = canonical
                break

        # Get expected decode for code from official CT
        codelist_name = self.DOMAIN_TO_CODELIST.get(domain)
        if codelist_name and self.official_ct:
            expected = self.parser.get_submission_value_for_code(code, codelist_name)
            if expected:
                # Check if decode matches expected (case-insensitive)
                if expected.lower() == decode.lower():
                    return True, None
                # Check if normalized decode matches expected
                if expected.lower() == normalized_decode.lower():
                    return True, None
                # Check if decode is a synonym in official CT
                codelist = self.parser.get_codelist_by_name(codelist_name)
                if codelist:
                    for term in codelist.get("terms", []):
                        if term["code"] == code:
                            synonyms_lower = [s.lower() for s in term.get("synonyms", [])]
                            if decode.lower() in synonyms_lower:
                                return True, None  # Valid synonym
                            if term.get("nci_term", "").lower() == decode.lower():
                                return True, None  # Valid NCI term

                # Check curated vocab decode for this code
                for vc in domain_vocab.get("valid_codes", []):
                    if vc.get("code") == code:
                        curated_decode = vc.get("decode")
                        if curated_decode:
                            # Check direct match or normalized match
                            if curated_decode.lower() == decode.lower():
                                return True, None
                            if curated_decode.lower() == normalized_decode.lower():
                                return True, None  # Synonym matches curated decode

                return False, f"Code '{code}' has decode '{expected}', not '{decode}'"

        # Check curated vocabulary only (no official CT for this domain)
        for vc in domain_vocab.get("valid_codes", []):
            if vc.get("code") == code:
                expected = vc.get("decode")
                if expected:
                    # Check exact match
                    if expected.lower() == decode.lower():
                        return True, None
                    # Check if decode is a synonym of expected
                    canonical = decode_synonyms.get(decode)
                    if canonical and canonical.lower() == expected.lower():
                        return True, None
                    return False, f"Code '{code}' has decode '{expected}', not '{decode}'"

        # Code not found
        return False, f"Code '{code}' not found in domain '{domain}'"

    def get_code_for_decode(
        self,
        decode: str,
        domain: str
    ) -> Optional[str]:
        """
        Find the NCI code for a given decode value.

        Args:
            decode: Decode value
            domain: Domain name

        Returns:
            NCI code or None
        """
        # Check centralized codelists first (PRIMARY for arm_types, epoch_types, design_types)
        centralized = self._get_centralized_codelist(domain)
        if centralized:
            pairs = centralized.get("pairs", [])
            # Check exact decode match
            for pair in pairs:
                if pair.get("decode", "").lower() == decode.lower():
                    return pair.get("code")
            # Check synonyms
            for pair in pairs:
                for syn in pair.get("synonyms", []):
                    if syn.lower() == decode.lower():
                        return pair.get("code")
            return None  # Not found in centralized

        # Check official CT second
        codelist_name = self.DOMAIN_TO_CODELIST.get(domain)
        if codelist_name and self.official_ct:
            code = self.parser.find_code_by_submission_value(decode, codelist_name)
            if code:
                return code

        # Check curated vocabulary (fallback)
        domain_vocab = self.curated_vocab.get(domain, {})

        # First normalize the decode using synonyms
        decode_synonyms = domain_vocab.get("decode_synonyms", {})
        canonical_decode = decode_synonyms.get(decode, decode)

        # Find code for canonical decode
        for vc in domain_vocab.get("valid_codes", []):
            if vc.get("decode", "").lower() == canonical_decode.lower():
                return vc.get("code")

        return None

    def _find_coded_fields(
        self,
        data: Any,
        path: str = "$",
        parent_key: Optional[str] = None,
        context: Optional[str] = None
    ) -> List[Tuple[str, str, Dict[str, Any], Optional[str]]]:
        """
        Recursively find all code/decode pairs in the data structure.

        Args:
            data: Data to traverse
            path: Current JSON path
            parent_key: Key name of parent field (for domain inference)
            context: Additional context (e.g., "endpoint", "objective")

        Yields:
            Tuples of (path, field_name, value_dict, inferred_domain)
        """
        results = []

        if isinstance(data, dict):
            # Check if this dict has code/decode pair
            if "code" in data and isinstance(data.get("code"), str):
                # Infer domain from parent key or context
                domain = self._infer_domain(parent_key, path, context)
                results.append((path, parent_key or "unknown", data, domain))

            # Check for decode-only fields (like blindingType)
            for key in ["blindingType", "interventionModel", "interventionType"]:
                if key in data and isinstance(data[key], str):
                    domain = self.FIELD_TO_DOMAIN.get(key)
                    if domain:
                        results.append((f"{path}.{key}", key, {"decode": data[key]}, domain))

            # Recurse into nested structures
            for key, value in data.items():
                if key in ("provenance", "extensionAttributes", "_metadata"):
                    continue  # Skip metadata fields

                new_path = f"{path}.{key}"

                # Update context based on key
                new_context = context
                if "endpoint" in key.lower():
                    new_context = "endpoint"
                elif "objective" in key.lower():
                    new_context = "objective"
                elif "arm" in key.lower():
                    new_context = "arm"
                elif "epoch" in key.lower():
                    new_context = "epoch"
                elif "estimand" in key.lower():
                    new_context = "estimand"

                if isinstance(value, dict):
                    results.extend(self._find_coded_fields(value, new_path, key, new_context))
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        item_path = f"{new_path}[{i}]"
                        if isinstance(item, dict):
                            results.extend(self._find_coded_fields(item, item_path, key, new_context))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                item_path = f"{path}[{i}]"
                if isinstance(item, dict):
                    results.extend(self._find_coded_fields(item, item_path, parent_key, context))

        return results

    # Fields that require context-aware domain inference
    CONTEXT_DEPENDENT_FIELDS = {"level", "arm_type", "armType"}

    def _infer_domain(
        self,
        field_name: Optional[str],
        path: str,
        context: Optional[str]
    ) -> Optional[str]:
        """
        Infer the validation domain from field name and context.

        Args:
            field_name: Name of the field containing the code
            path: JSON path to the field
            context: Contextual hint (endpoint, objective, arm, etc.)

        Returns:
            Domain name or None if cannot be inferred
        """
        if not field_name:
            return None

        # Handle context-dependent fields FIRST (before direct mapping)
        if field_name in self.CONTEXT_DEPENDENT_FIELDS:
            if field_name == "level":
                # Check context first
                if context == "endpoint":
                    return "endpoint_level"
                elif context == "objective":
                    return "objective_level"
                # Check path for hints
                path_lower = path.lower()
                if "endpoint" in path_lower:
                    return "endpoint_level"
                elif "objective" in path_lower:
                    return "objective_level"
                # Default to endpoint_level if no context
                return "endpoint_level"

            if field_name in ("arm_type", "armType"):
                # Estimand treatment arms use different codes than study arms
                path_lower = path.lower()
                if context == "estimand" or "estimand" in path_lower or "treatment" in path_lower:
                    return "estimand_arm_type"
                # Default to arm_types for study-level arms
                return "arm_types"

        # Direct field name mapping (for non-context-dependent fields)
        if field_name in self.FIELD_TO_DOMAIN:
            return self.FIELD_TO_DOMAIN[field_name]

        # Path-based inference for unrecognized field names
        path_lower = path.lower()
        if "studyphase" in path_lower or "trialphase" in path_lower:
            return "study_phase"
        if "studytype" in path_lower or "trialtype" in path_lower:
            return "study_type"
        if "armtype" in path_lower or ".arms[" in path_lower:
            # Check if this is within an estimand context
            if "estimand" in path_lower or "treatment" in path_lower:
                return "estimand_arm_type"
            return "arm_types"
        if "sex" in path_lower:
            return "sex"
        if "blinding" in path_lower:
            return "blinding"
        if "route" in path_lower:
            return "route_of_administration"
        if "epoch" in path_lower:
            return "epoch_types"
        if "population" in path_lower and field_name and "type" in field_name.lower():
            return "population_type"

        return None

    def validate_extraction_data(
        self,
        data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Validate CDISC terminology in extraction data.

        Uses recursive traversal to find all code/decode pairs anywhere
        in the data structure and validates them against the appropriate
        CDISC controlled terminology domain.

        Args:
            data: Extracted data dictionary

        Returns:
            List of validation issues
        """
        issues = []
        validated_paths = set()  # Track validated paths to avoid duplicates

        # Phase 1: Recursive traversal to find all coded fields
        coded_fields = self._find_coded_fields(data)

        for path, field_name, value, domain in coded_fields:
            if path in validated_paths:
                continue
            validated_paths.add(path)

            code = value.get("code")
            decode = value.get("decode")

            if not domain:
                # Log unrecognized coded field for debugging
                logger.debug(f"Skipping coded field at {path} - domain could not be inferred")
                continue

            # Validate code
            if code:
                is_valid, error = self.validate_code(code, domain)
                if not is_valid:
                    issues.append({
                        "path": f"{path}.code",
                        "code": code,
                        "issue": "invalid_nci_code",
                        "domain": domain,
                        "error": error
                    })

            # Validate code/decode pair
            if code and decode:
                is_valid, error = self.validate_code_decode_pair(code, decode, domain)
                if not is_valid:
                    issues.append({
                        "path": f"{path}.decode",
                        "code": code,
                        "decode": decode,
                        "issue": "decode_mismatch",
                        "domain": domain,
                        "error": error
                    })

            # Validate decode-only fields (like blindingType)
            if decode and not code:
                is_valid, canonical, error = self.validate_decode(decode, domain)
                if not is_valid:
                    issues.append({
                        "path": path,
                        "value": decode,
                        "issue": f"invalid_{domain}_value",
                        "domain": domain,
                        "error": error
                    })

        # Phase 2: Explicit checks for known paths (backward compatibility + catch-all)
        # These ensure validation even if recursive traversal misses something

        # Check sex codes in studyPopulation (special nested structure)
        population = data.get("studyPopulation", {})
        sex_info = population.get("sex", {})
        allowed_sex = sex_info.get("allowed", [])
        for i, sex_item in enumerate(allowed_sex):
            sex_path = f"$.studyPopulation.sex.allowed[{i}]"
            if sex_path not in validated_paths:
                code = sex_item.get("code")
                if code:
                    is_valid, error = self.validate_code(code, "sex")
                    if not is_valid:
                        issues.append({
                            "path": f"{sex_path}.code",
                            "code": code,
                            "issue": "invalid_nci_code",
                            "domain": "sex",
                            "error": error
                        })

        return issues

    def get_validation_stats(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get statistics about coded fields in the data.

        Useful for understanding validation coverage.

        Args:
            data: Extracted data dictionary

        Returns:
            Statistics dictionary
        """
        coded_fields = self._find_coded_fields(data)

        domains_found = {}
        unrecognized = []

        for path, field_name, value, domain in coded_fields:
            if domain:
                domains_found[domain] = domains_found.get(domain, 0) + 1
            else:
                unrecognized.append({"path": path, "field": field_name})

        return {
            "total_coded_fields": len(coded_fields),
            "domains_found": domains_found,
            "recognized_fields": len(coded_fields) - len(unrecognized),
            "unrecognized_fields": unrecognized,
            "coverage_percentage": (
                (len(coded_fields) - len(unrecognized)) / len(coded_fields) * 100
                if coded_fields else 100.0
            )
        }

    def get_available_domains(self) -> List[str]:
        """List all available validation domains."""
        domains = set(self.DOMAIN_TO_CODELIST.keys())
        domains.update(self.curated_vocab.keys())
        domains.discard("version")
        domains.discard("last_updated")
        domains.discard("source")
        domains.discard("code_system")
        return sorted(domains)

    def get_valid_codes_for_domain(self, domain: str) -> List[Dict[str, str]]:
        """
        Get all valid codes for a domain.

        Args:
            domain: Domain name

        Returns:
            List of {code, decode, description} dicts
        """
        results = []

        # From official CT
        codelist_name = self.DOMAIN_TO_CODELIST.get(domain)
        if codelist_name and self.official_ct:
            codelist = self.parser.get_codelist_by_name(codelist_name)
            if codelist:
                for term in codelist.get("terms", []):
                    results.append({
                        "code": term["code"],
                        "decode": term["submission_value"],
                        "description": term.get("definition", "")[:200]
                    })

        # From curated vocab (if not already covered)
        if not results:
            domain_vocab = self.curated_vocab.get(domain, {})
            for vc in domain_vocab.get("valid_codes", []):
                results.append({
                    "code": vc.get("code", ""),
                    "decode": vc.get("decode", ""),
                    "description": vc.get("description", "")
                })

        return results
