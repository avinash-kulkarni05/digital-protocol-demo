"""
FHIR R4 Data Adapter - Query FHIR R4 servers for patient populations.

This adapter supports querying patient populations from FHIR R4 servers
using standard FHIR search parameters.
"""

import logging
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode
import requests

from .base_adapter import BaseDataAdapter, ConnectionConfig, QueryResult

logger = logging.getLogger(__name__)


# OMOP to FHIR code system mappings
CODE_SYSTEM_MAPPINGS = {
    "SNOMED": "http://snomed.info/sct",
    "ICD10CM": "http://hl7.org/fhir/sid/icd-10-cm",
    "ICD10": "http://hl7.org/fhir/sid/icd-10",
    "LOINC": "http://loinc.org",
    "RxNorm": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "CPT4": "http://www.ama-assn.org/go/cpt",
    "HCPCS": "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets",
}

# FHIR gender codes
GENDER_CODES = {
    8507: "male",    # OMOP male concept
    8532: "female",  # OMOP female concept
}


class FhirAdapter(BaseDataAdapter):
    """
    FHIR R4 data adapter for patient population queries.

    Supports FHIR R4 servers with SMART on FHIR authentication.
    Uses FHIR search parameters for patient identification.
    """

    def __init__(
        self,
        base_url: str,
        auth_token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        timeout_seconds: int = 30,
    ):
        """
        Initialize FHIR adapter.

        Args:
            base_url: FHIR server base URL (e.g., https://fhir.example.com/r4).
            auth_token: Bearer token for authentication.
            client_id: SMART on FHIR client ID.
            client_secret: SMART on FHIR client secret.
            timeout_seconds: Request timeout.
        """
        # Create config from parameters
        config = ConnectionConfig(
            host=base_url,
            port=443,
            database="fhir",
            username=client_id or "",
            password=client_secret or "",
            timeout_seconds=timeout_seconds,
        )
        super().__init__(config)

        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout_seconds

        self._session = None
        self._total_population = None

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers including authentication."""
        headers = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def connect(self) -> bool:
        """
        Establish connection to FHIR server.

        Returns:
            True if connection successful.
        """
        try:
            self._session = requests.Session()
            self._session.headers.update(self._get_headers())

            # Test connection with capability statement
            response = self._session.get(
                f"{self.base_url}/metadata",
                timeout=self.timeout,
            )
            response.raise_for_status()

            self._connected = True
            logger.info(f"Connected to FHIR server at {self.base_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to FHIR server: {e}")
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Close FHIR server connection."""
        if self._session:
            self._session.close()
            self._session = None
        self._connected = False
        logger.info("Disconnected from FHIR server")

    def _search(
        self,
        resource_type: str,
        params: Dict[str, Any],
        count_only: bool = True,
    ) -> QueryResult:
        """
        Execute FHIR search.

        Args:
            resource_type: FHIR resource type (e.g., Patient, Condition).
            params: Search parameters.
            count_only: If True, only return count (faster).

        Returns:
            QueryResult with patient count.
        """
        if not self._connected:
            return QueryResult(
                patient_count=0,
                error="Not connected to FHIR server",
            )

        start_time = time.time()
        try:
            if count_only:
                params["_summary"] = "count"

            url = f"{self.base_url}/{resource_type}"
            query_string = urlencode(params, doseq=True)

            response = self._session.get(
                f"{url}?{query_string}",
                timeout=self.timeout,
            )
            response.raise_for_status()
            bundle = response.json()

            count = bundle.get("total", 0)
            execution_time = (time.time() - start_time) * 1000

            return QueryResult(
                patient_count=count,
                query_executed=f"GET {url}?{query_string}",
                execution_time_ms=execution_time,
            )

        except Exception as e:
            logger.error(f"FHIR search failed: {e}")
            return QueryResult(
                patient_count=0,
                error=str(e),
            )

    def _build_code_token(
        self,
        code_system: str,
        code: str,
    ) -> str:
        """Build FHIR code token for search."""
        system_url = CODE_SYSTEM_MAPPINGS.get(code_system, code_system)
        return f"{system_url}|{code}"

    def get_total_population(self) -> int:
        """Get total patient count in FHIR server."""
        if self._total_population is not None:
            return self._total_population

        result = self._search("Patient", {})
        self._total_population = result.patient_count
        return self._total_population

    def query_condition(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
    ) -> QueryResult:
        """
        Query patients with specific conditions.

        Note: FHIR doesn't directly support OMOP concept IDs.
        This method expects SNOMED codes or uses OMOP-to-FHIR mapping.
        """
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        # For now, search by code if we have SNOMED codes
        # In production, would translate OMOP concept IDs to SNOMED
        codes = [str(c) for c in concept_ids]
        code_tokens = [self._build_code_token("SNOMED", c) for c in codes]

        params = {
            "code": ",".join(code_tokens),
            "_include": "Condition:subject",
        }

        return self._search("Condition", params)

    def query_measurement(
        self,
        concept_ids: List[int],
        value_operator: str = ">=",
        value_threshold: float = 0.0,
        unit_concept_id: Optional[int] = None,
    ) -> QueryResult:
        """Query patients with specific measurements (Observations)."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        # Map OMOP concept IDs to LOINC codes
        codes = [str(c) for c in concept_ids]
        code_tokens = [self._build_code_token("LOINC", c) for c in codes]

        # FHIR comparison operators
        operator_map = {
            ">=": "ge",
            "<=": "le",
            ">": "gt",
            "<": "lt",
            "=": "eq",
            "!=": "ne",
        }
        fhir_op = operator_map.get(value_operator, "ge")

        params = {
            "code": ",".join(code_tokens),
            "value-quantity": f"{fhir_op}{value_threshold}",
        }

        return self._search("Observation", params)

    def query_drug_exposure(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
        days_supply_min: Optional[int] = None,
    ) -> QueryResult:
        """Query patients with specific drug exposures (MedicationRequest)."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        codes = [str(c) for c in concept_ids]
        code_tokens = [self._build_code_token("RxNorm", c) for c in codes]

        params = {
            "code": ",".join(code_tokens),
            "status": "active,completed",
        }

        return self._search("MedicationRequest", params)

    def query_procedure(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
    ) -> QueryResult:
        """Query patients with specific procedures."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        codes = [str(c) for c in concept_ids]
        # Try both SNOMED and CPT4
        code_tokens = [self._build_code_token("SNOMED", c) for c in codes]
        code_tokens.extend([self._build_code_token("CPT4", c) for c in codes])

        params = {
            "code": ",".join(code_tokens),
            "status": "completed",
        }

        return self._search("Procedure", params)

    def query_observation(
        self,
        concept_ids: List[int],
        value_as_concept_id: Optional[int] = None,
        value_as_string: Optional[str] = None,
    ) -> QueryResult:
        """Query patients with specific observations."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        codes = [str(c) for c in concept_ids]
        code_tokens = [self._build_code_token("LOINC", c) for c in codes]

        params = {
            "code": ",".join(code_tokens),
        }

        if value_as_string:
            params["value-string"] = value_as_string

        return self._search("Observation", params)

    def query_demographics(
        self,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None,
        gender_concept_id: Optional[int] = None,
    ) -> QueryResult:
        """Query patients by demographics."""
        params = {}

        # Calculate birthdate range from age
        from datetime import date, timedelta

        today = date.today()
        if max_age is not None:
            # Born after this date (younger than max_age)
            min_birthdate = today - timedelta(days=max_age * 365)
            params["birthdate"] = f"ge{min_birthdate.isoformat()}"
        if min_age is not None:
            # Born before this date (older than min_age)
            max_birthdate = today - timedelta(days=min_age * 365)
            if "birthdate" in params:
                # Need to use list for multiple values
                params["birthdate"] = [params["birthdate"], f"le{max_birthdate.isoformat()}"]
            else:
                params["birthdate"] = f"le{max_birthdate.isoformat()}"

        if gender_concept_id:
            gender = GENDER_CODES.get(gender_concept_id)
            if gender:
                params["gender"] = gender

        return self._search("Patient", params)

    def get_adapter_info(self) -> Dict[str, Any]:
        """Get adapter metadata."""
        info = super().get_adapter_info()
        info.update({
            "base_url": self.base_url,
            "fhir_version": "R4",
            "total_population": self._total_population,
        })
        return info
