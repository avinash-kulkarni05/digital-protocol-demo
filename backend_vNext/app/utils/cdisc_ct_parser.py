"""
CDISC Controlled Terminology Parser.

Parses official NCI EVS CDISC CT files (tab-delimited format).
Download source: https://evs.nci.nih.gov/ftp1/CDISC/Protocol/
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class CDISCTerminologyParser:
    """
    Parse NCI EVS CDISC Controlled Terminology files.

    File format (tab-delimited):
    - Column 0: Code (NCI code)
    - Column 1: Codelist Code (parent codelist code, empty for headers)
    - Column 2: Codelist Extensible (Yes/No)
    - Column 3: Codelist Name
    - Column 4: CDISC Submission Value
    - Column 5: CDISC Synonym(s) (semicolon-separated)
    - Column 6: CDISC Definition
    - Column 7: NCI Preferred Term
    """

    # Column indices
    COL_CODE = 0
    COL_CODELIST_CODE = 1
    COL_EXTENSIBLE = 2
    COL_CODELIST_NAME = 3
    COL_SUBMISSION_VALUE = 4
    COL_SYNONYMS = 5
    COL_DEFINITION = 6
    COL_NCI_TERM = 7

    def __init__(self):
        self.codelists: Dict[str, Dict[str, Any]] = {}
        self.codelist_by_name: Dict[str, str] = {}  # name -> code mapping

    def parse_file(self, filepath: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse tab-delimited NCI EVS format.

        Args:
            filepath: Path to the terminology file

        Returns:
            Dict of codelists keyed by codelist code:
            {
                "C66737": {
                    "code": "C66737",
                    "name": "Trial Phase Response",
                    "submission_value": "TPHASE",
                    "extensible": True,
                    "definition": "...",
                    "terms": [
                        {
                            "code": "C49686",
                            "submission_value": "PHASE IIA TRIAL",
                            "synonyms": ["2A", "Trial Phase 2A"],
                            "definition": "...",
                            "nci_term": "Phase IIa Trial"
                        },
                        ...
                    ]
                }
            }
        """
        filepath = Path(filepath)
        if not filepath.exists():
            logger.error(f"CDISC CT file not found: {filepath}")
            return {}

        self.codelists = {}
        self.codelist_by_name = {}

        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Skip header line
        for line in lines[1:]:
            self._parse_line(line.strip())

        logger.info(f"Parsed {len(self.codelists)} codelists from {filepath}")
        return self.codelists

    def _parse_line(self, line: str) -> None:
        """Parse a single line from the CT file."""
        if not line:
            return

        cols = line.split('\t')
        if len(cols) < 8:
            return

        code = cols[self.COL_CODE].strip()
        codelist_code = cols[self.COL_CODELIST_CODE].strip()
        extensible = cols[self.COL_EXTENSIBLE].strip().upper() == 'YES'
        codelist_name = cols[self.COL_CODELIST_NAME].strip()
        submission_value = cols[self.COL_SUBMISSION_VALUE].strip()
        synonyms_str = cols[self.COL_SYNONYMS].strip()
        definition = cols[self.COL_DEFINITION].strip()
        nci_term = cols[self.COL_NCI_TERM].strip()

        # Parse synonyms (semicolon-separated)
        synonyms = [s.strip() for s in synonyms_str.split(';') if s.strip()]

        if not codelist_code:
            # This is a codelist header
            self.codelists[code] = {
                "code": code,
                "name": codelist_name,
                "submission_value": submission_value,
                "extensible": extensible,
                "definition": definition,
                "nci_term": nci_term,
                "terms": []
            }
            # Map name to code for lookup
            self.codelist_by_name[codelist_name.lower()] = code
            if submission_value:
                self.codelist_by_name[submission_value.lower()] = code
        else:
            # This is a term within a codelist
            if codelist_code in self.codelists:
                self.codelists[codelist_code]["terms"].append({
                    "code": code,
                    "submission_value": submission_value,
                    "synonyms": synonyms,
                    "definition": definition,
                    "nci_term": nci_term
                })

    def get_codelist_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get codelist by name or submission value.

        Args:
            name: Codelist name (e.g., "Trial Phase Response", "TPHASE")

        Returns:
            Codelist dict or None if not found
        """
        code = self.codelist_by_name.get(name.lower())
        if code:
            return self.codelists.get(code)
        return None

    def get_codelist_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Get codelist by NCI code."""
        return self.codelists.get(code)

    def validate_code(self, nci_code: str, codelist_name: str) -> tuple[bool, Optional[str]]:
        """
        Validate if an NCI code belongs to a codelist.

        Args:
            nci_code: The NCI code to validate (e.g., "C49686")
            codelist_name: The codelist name (e.g., "Trial Phase Response")

        Returns:
            Tuple of (is_valid, error_message)
        """
        codelist = self.get_codelist_by_name(codelist_name)
        if not codelist:
            return False, f"Unknown codelist: {codelist_name}"

        valid_codes = [term["code"] for term in codelist["terms"]]
        if nci_code in valid_codes:
            return True, None

        return False, f"Invalid code '{nci_code}' for codelist '{codelist_name}'. Valid codes: {valid_codes[:5]}..."

    def get_submission_value_for_code(self, nci_code: str, codelist_name: str) -> Optional[str]:
        """
        Get the CDISC submission value for an NCI code.

        Args:
            nci_code: The NCI code (e.g., "C49686")
            codelist_name: The codelist name

        Returns:
            Submission value or None
        """
        codelist = self.get_codelist_by_name(codelist_name)
        if not codelist:
            return None

        for term in codelist["terms"]:
            if term["code"] == nci_code:
                return term["submission_value"]

        return None

    def find_code_by_submission_value(
        self,
        value: str,
        codelist_name: str
    ) -> Optional[str]:
        """
        Find NCI code by submission value or synonym.

        Args:
            value: The submission value or synonym (e.g., "PHASE III TRIAL", "Phase 3")
            codelist_name: The codelist name

        Returns:
            NCI code or None
        """
        codelist = self.get_codelist_by_name(codelist_name)
        if not codelist:
            return None

        value_lower = value.lower().strip()

        for term in codelist["terms"]:
            # Check submission value
            if term["submission_value"].lower() == value_lower:
                return term["code"]

            # Check synonyms
            for synonym in term["synonyms"]:
                if synonym.lower() == value_lower:
                    return term["code"]

            # Check NCI term
            if term["nci_term"].lower() == value_lower:
                return term["code"]

        return None

    def list_codelists(self) -> List[Dict[str, str]]:
        """List all available codelists."""
        return [
            {
                "code": cl["code"],
                "name": cl["name"],
                "submission_value": cl["submission_value"],
                "term_count": len(cl["terms"])
            }
            for cl in self.codelists.values()
        ]
