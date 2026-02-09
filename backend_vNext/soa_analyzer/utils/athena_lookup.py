"""
Athena Lookup Service for validated NCI/CDISC code lookups.

This service queries the Athena database (with NCIt_Full concepts loaded)
to provide validated code lookups for specimen types, tube types, purposes, etc.

Usage:
    from soa_analyzer.utils.athena_lookup import AthenaLookupService, Concept

    lookup = AthenaLookupService()

    # Lookup by code
    concept = lookup.lookup_by_code('C41067')  # Whole Blood
    print(f"{concept.concept_code}: {concept.concept_name}")

    # Search by name
    concepts = lookup.search_by_name('Serum', exact=True)

    # Validate a code exists
    is_valid = lookup.validate_code('C41067')  # True

    # Get pre-validated specimen codes
    specimen_codes = lookup.get_specimen_codes()
"""

import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional
import os


@dataclass
class Concept:
    """Represents an Athena concept."""
    concept_id: int
    concept_code: str
    concept_name: str
    vocabulary_id: str
    domain_id: str
    concept_class_id: str

    def to_usdm_code(self, code_system_version: str = "25.11d") -> Dict:
        """Convert to USDM 4.0 Code object."""
        return {
            "code": self.concept_code,
            "decode": self.concept_name,
            "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
            "codeSystemVersion": code_system_version,
            "instanceType": "Code",
        }


class AthenaLookupService:
    """
    Service for looking up validated codes from Athena database.

    Prioritizes NCIt_Full and CDISC vocabularies for specimen-related codes.
    """

    # Default path to Athena database (relative to backend_vNext/)
    DEFAULT_DB_PATH = str(Path(__file__).parent.parent.parent / "athena_concepts_full.db")

    # Preferred vocabularies in priority order
    PREFERRED_VOCABULARIES = ['NCIt_Full', 'CDISC', 'SNOMED', 'LOINC']

    # Pre-validated specimen type mappings (key -> NCI code)
    # These are validated against Athena DB with NCIt_Full loaded
    SPECIMEN_TYPES = {
        # Category-level body fluids
        'blood': 'C12434',  # Blood
        'whole_blood': 'C41067',  # Whole Blood
        'serum': 'C13325',  # Serum
        'plasma': 'C13356',  # Plasma
        'urine': 'C13283',  # Urine
        'csf': 'C12692',  # Cerebrospinal Fluid
        'cerebrospinal_fluid': 'C12692',  # Cerebrospinal Fluid (alias)
        'saliva': 'C13275',  # Saliva
        'bone_marrow': 'C12431',  # Bone Marrow
        'stool': 'C13234',  # Feces
        'feces': 'C13234',  # Feces (alias)
        'sputum': 'C13278',  # Sputum
        'breath': 'C126053',  # Exhaled Breath Condensate
        # Solid specimens
        'tissue': 'C12801',  # Tissue
        'biopsy': 'C15189',  # Biopsy
        'swab': 'C17627',  # Swab
        'hair': 'C32705',  # Hair
        'nail': 'C33156',  # Nail
        # Plasma subtypes (map to parent Plasma code)
        'edta_plasma': 'C13356',  # Plasma
        'citrate_plasma': 'C13356',  # Plasma
        'lithium_heparin_plasma': 'C13356',  # Plasma
        'heparin_plasma': 'C13356',  # Plasma
        # Urine subtypes (map to parent Urine code)
        'urine_spot': 'C13283',  # Urine (spot collection)
        'urine_24h': 'C13283',  # Urine (24-hour collection)
        'random_urine': 'C13283',  # Urine (random)
        # Generic
        'other': 'C17998',  # Unknown
    }

    # Pre-validated tube type mappings
    TUBE_TYPES = {
        'serum_tube': 'C113675',  # Serum Collection Tube (Red Top)
        'sst': 'C113675',  # Serum Separator Tube (alias)
        'edta_tube': 'C113676',  # CBC Collection Tube (Lavender/Purple - EDTA)
        'edta': 'C113676',  # EDTA (alias)
        'whole_blood_tube': 'C113392',  # Whole Blood Collection Tube (Yellow)
        'k2edta_tube': 'C167172',  # Vacutainer with K2EDTA
        'k2edta': 'C167172',  # K2EDTA (alias)
        'k3edta_tube': 'C167172',  # K3EDTA (maps to K2EDTA)
        'cfdna_tube': 'C156117',  # Cell-Free DNA BCT
        'ppt_tube': 'C153167',  # Plasma Preparation Tube
        # Citrate tubes (coagulation)
        'sodium_citrate': 'C200493',  # Sodium Citrate Blood Collection Tube (Blue Top)
        'sodium_citrate_tube': 'C200493',  # Sodium Citrate tube (alias)
        'citrate_tube': 'C200493',  # Citrate tube (alias)
        'blue_top': 'C200493',  # Blue top (alias)
        # Heparin tubes
        'lithium_heparin': 'C200492',  # Lithium Heparin Blood Collection Tube (Green Top)
        'lithium_heparin_tube': 'C200492',  # Lithium Heparin tube (alias)
        'sodium_heparin': 'C174429',  # Sodium Heparin Green-Top Tube
        'heparin_tube': 'C200492',  # Heparin tube (maps to lithium heparin)
        'green_top': 'C200492',  # Green top (alias)
    }

    # Pre-validated purpose mappings
    PURPOSE_CODES = {
        'safety': 'C49667',
        'efficacy': 'C49666',
        'pharmacokinetic': 'C49663',
        'biomarker': 'C16342',
        'exploratory': 'C170559',
    }

    # Pre-validated storage condition mappings
    STORAGE_CONDITIONS = {
        'frozen': 'C70717',
        'refrigerated': 'C70718',
        'room_temperature': 'C70719',
    }

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the lookup service.

        Args:
            db_path: Path to Athena SQLite database. Defaults to standard location.
        """
        self.db_path = db_path or os.environ.get('ATHENA_DB_PATH', self.DEFAULT_DB_PATH)
        if not Path(self.db_path).exists():
            raise FileNotFoundError(f"Athena database not found: {self.db_path}")

        self._conn = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @lru_cache(maxsize=1000)
    def lookup_by_code(self, code: str, vocabulary: Optional[str] = None) -> Optional[Concept]:
        """
        Lookup a concept by its NCI code.

        Args:
            code: NCI code (e.g., 'C41067')
            vocabulary: Optional vocabulary to filter by (e.g., 'NCIt_Full', 'CDISC')

        Returns:
            Concept if found, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if vocabulary:
            cursor.execute("""
                SELECT concept_id, concept_code, concept_name, vocabulary_id, domain_id, concept_class_id
                FROM concept
                WHERE concept_code = ? AND vocabulary_id = ?
            """, (code, vocabulary))
        else:
            # Try preferred vocabularies in order
            for vocab in self.PREFERRED_VOCABULARIES:
                cursor.execute("""
                    SELECT concept_id, concept_code, concept_name, vocabulary_id, domain_id, concept_class_id
                    FROM concept
                    WHERE concept_code = ? AND vocabulary_id = ?
                """, (code, vocab))
                row = cursor.fetchone()
                if row:
                    return Concept(
                        concept_id=row['concept_id'],
                        concept_code=row['concept_code'],
                        concept_name=row['concept_name'],
                        vocabulary_id=row['vocabulary_id'],
                        domain_id=row['domain_id'],
                        concept_class_id=row['concept_class_id'],
                    )

            # Fallback to any vocabulary
            cursor.execute("""
                SELECT concept_id, concept_code, concept_name, vocabulary_id, domain_id, concept_class_id
                FROM concept
                WHERE concept_code = ?
                LIMIT 1
            """, (code,))

        row = cursor.fetchone()
        if row:
            return Concept(
                concept_id=row['concept_id'],
                concept_code=row['concept_code'],
                concept_name=row['concept_name'],
                vocabulary_id=row['vocabulary_id'],
                domain_id=row['domain_id'],
                concept_class_id=row['concept_class_id'],
            )
        return None

    def search_by_name(
        self,
        name: str,
        exact: bool = True,
        vocabulary: Optional[str] = None,
        limit: int = 10
    ) -> List[Concept]:
        """
        Search for concepts by name.

        Args:
            name: Concept name to search for
            exact: If True, exact match; if False, partial match (LIKE)
            vocabulary: Optional vocabulary to filter by
            limit: Maximum number of results

        Returns:
            List of matching Concepts
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if exact:
            if vocabulary:
                cursor.execute("""
                    SELECT concept_id, concept_code, concept_name, vocabulary_id, domain_id, concept_class_id
                    FROM concept
                    WHERE UPPER(concept_name) = UPPER(?) AND vocabulary_id = ?
                    LIMIT ?
                """, (name, vocabulary, limit))
            else:
                cursor.execute("""
                    SELECT concept_id, concept_code, concept_name, vocabulary_id, domain_id, concept_class_id
                    FROM concept
                    WHERE UPPER(concept_name) = UPPER(?)
                    LIMIT ?
                """, (name, limit))
        else:
            search_pattern = f'%{name}%'
            if vocabulary:
                cursor.execute("""
                    SELECT concept_id, concept_code, concept_name, vocabulary_id, domain_id, concept_class_id
                    FROM concept
                    WHERE LOWER(concept_name) LIKE LOWER(?) AND vocabulary_id = ?
                    LIMIT ?
                """, (search_pattern, vocabulary, limit))
            else:
                cursor.execute("""
                    SELECT concept_id, concept_code, concept_name, vocabulary_id, domain_id, concept_class_id
                    FROM concept
                    WHERE LOWER(concept_name) LIKE LOWER(?)
                    LIMIT ?
                """, (search_pattern, limit))

        results = []
        for row in cursor.fetchall():
            results.append(Concept(
                concept_id=row['concept_id'],
                concept_code=row['concept_code'],
                concept_name=row['concept_name'],
                vocabulary_id=row['vocabulary_id'],
                domain_id=row['domain_id'],
                concept_class_id=row['concept_class_id'],
            ))

        # Sort by preferred vocabulary
        def vocab_priority(concept):
            try:
                return self.PREFERRED_VOCABULARIES.index(concept.vocabulary_id)
            except ValueError:
                return 999

        results.sort(key=vocab_priority)
        return results

    def validate_code(self, code: str) -> bool:
        """Check if a code exists in the database."""
        return self.lookup_by_code(code) is not None

    def get_specimen_code(self, specimen_type: str) -> Optional[Concept]:
        """
        Get pre-validated specimen type code.

        Args:
            specimen_type: Specimen type key (e.g., 'whole_blood', 'serum', 'plasma')

        Returns:
            Concept if found, None otherwise
        """
        code = self.SPECIMEN_TYPES.get(specimen_type.lower().replace(' ', '_'))
        if code:
            return self.lookup_by_code(code)
        return None

    def get_tube_code(self, tube_type: str) -> Optional[Concept]:
        """
        Get pre-validated tube type code.

        Args:
            tube_type: Tube type key (e.g., 'edta_tube', 'serum_tube')

        Returns:
            Concept if found, None otherwise
        """
        code = self.TUBE_TYPES.get(tube_type.lower().replace(' ', '_'))
        if code:
            return self.lookup_by_code(code)
        return None

    def get_purpose_code(self, purpose: str) -> Optional[Concept]:
        """
        Get pre-validated purpose code.

        Args:
            purpose: Purpose key (e.g., 'safety', 'efficacy', 'biomarker')

        Returns:
            Concept if found, None otherwise
        """
        code = self.PURPOSE_CODES.get(purpose.lower().replace(' ', '_'))
        if code:
            return self.lookup_by_code(code)
        return None

    def get_storage_code(self, condition: str) -> Optional[Concept]:
        """
        Get pre-validated storage condition code.

        Args:
            condition: Storage condition key (e.g., 'frozen', 'refrigerated')

        Returns:
            Concept if found, None otherwise
        """
        code = self.STORAGE_CONDITIONS.get(condition.lower().replace(' ', '_'))
        if code:
            return self.lookup_by_code(code)
        return None

    def get_specimen_codes(self) -> Dict[str, Concept]:
        """Get all pre-validated specimen type codes."""
        return {key: self.lookup_by_code(code) for key, code in self.SPECIMEN_TYPES.items()}

    def get_tube_codes(self) -> Dict[str, Concept]:
        """Get all pre-validated tube type codes."""
        return {key: self.lookup_by_code(code) for key, code in self.TUBE_TYPES.items()}

    def close(self):
        """Close the database connection."""
        if hasattr(self, '_conn') and self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()
