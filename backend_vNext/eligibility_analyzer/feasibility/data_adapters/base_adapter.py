"""
Base Data Adapter - Abstract interface for patient population queries.

This module defines the abstract base class for data adapters that query
patient populations for feasibility analysis.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of a patient population query."""
    patient_count: int
    patient_ids: Optional[Set[str]] = None  # Optional for privacy
    query_executed: str = ""
    execution_time_ms: float = 0.0
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ConnectionConfig:
    """Configuration for data source connection."""
    host: str
    port: int
    database: str
    username: str
    password: str
    schema: Optional[str] = None
    ssl_enabled: bool = True
    timeout_seconds: int = 30
    extra_params: Optional[Dict[str, Any]] = None


class BaseDataAdapter(ABC):
    """
    Abstract base class for data source adapters.

    Subclasses implement specific data source connections:
    - OMOP CDM (PostgreSQL, SQL Server, etc.)
    - FHIR R4 (REST API)
    - Synthetic (prevalence-based)
    """

    def __init__(self, config: Optional[ConnectionConfig] = None):
        """
        Initialize the adapter.

        Args:
            config: Connection configuration.
        """
        self.config = config
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if adapter is connected to data source."""
        return self._connected

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to data source.

        Returns:
            True if connection successful.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to data source."""
        pass

    @abstractmethod
    def get_total_population(self) -> int:
        """
        Get total patient count in data source.

        Returns:
            Total patient count.
        """
        pass

    @abstractmethod
    def query_condition(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
    ) -> QueryResult:
        """
        Query patients with specific conditions.

        Args:
            concept_ids: OMOP/SNOMED concept IDs.
            include_descendants: Include descendant concepts.

        Returns:
            QueryResult with patient count.
        """
        pass

    @abstractmethod
    def query_measurement(
        self,
        concept_ids: List[int],
        value_operator: str = ">=",
        value_threshold: float = 0.0,
        unit_concept_id: Optional[int] = None,
    ) -> QueryResult:
        """
        Query patients with specific measurement values.

        Args:
            concept_ids: Measurement concept IDs (e.g., lab tests).
            value_operator: Comparison operator (>=, <=, =, >, <).
            value_threshold: Threshold value.
            unit_concept_id: Unit concept ID for validation.

        Returns:
            QueryResult with patient count.
        """
        pass

    @abstractmethod
    def query_drug_exposure(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
        days_supply_min: Optional[int] = None,
    ) -> QueryResult:
        """
        Query patients with specific drug exposures.

        Args:
            concept_ids: Drug concept IDs.
            include_descendants: Include descendant concepts.
            days_supply_min: Minimum days of drug supply.

        Returns:
            QueryResult with patient count.
        """
        pass

    @abstractmethod
    def query_procedure(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
    ) -> QueryResult:
        """
        Query patients with specific procedures.

        Args:
            concept_ids: Procedure concept IDs.
            include_descendants: Include descendant concepts.

        Returns:
            QueryResult with patient count.
        """
        pass

    @abstractmethod
    def query_observation(
        self,
        concept_ids: List[int],
        value_as_concept_id: Optional[int] = None,
        value_as_string: Optional[str] = None,
    ) -> QueryResult:
        """
        Query patients with specific observations.

        Args:
            concept_ids: Observation concept IDs.
            value_as_concept_id: Expected value concept ID.
            value_as_string: Expected value string.

        Returns:
            QueryResult with patient count.
        """
        pass

    @abstractmethod
    def query_demographics(
        self,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None,
        gender_concept_id: Optional[int] = None,
    ) -> QueryResult:
        """
        Query patients by demographics.

        Args:
            min_age: Minimum age in years.
            max_age: Maximum age in years.
            gender_concept_id: Gender concept ID.

        Returns:
            QueryResult with patient count.
        """
        pass

    def query_intersection(
        self,
        results: List[QueryResult],
    ) -> int:
        """
        Calculate intersection of multiple query results.

        Default implementation returns minimum count (conservative estimate).
        Subclasses should override with actual set intersection if patient IDs available.

        Args:
            results: List of query results.

        Returns:
            Estimated patient count in intersection.
        """
        if not results:
            return 0
        # Conservative estimate: product of individual rates
        # This assumes independence, which may not be accurate
        total = self.get_total_population()
        if total == 0:
            return 0

        rate_product = 1.0
        for r in results:
            rate = r.patient_count / total
            rate_product *= rate

        return int(total * rate_product)

    def execute_sql(self, sql: str, params: Optional[Dict[str, Any]] = None) -> QueryResult:
        """
        Execute raw SQL query (OMOP adapters).

        Args:
            sql: SQL query string.
            params: Query parameters.

        Returns:
            QueryResult with patient count.

        Raises:
            NotImplementedError if not supported by adapter.
        """
        raise NotImplementedError("Raw SQL not supported by this adapter")

    def get_adapter_info(self) -> Dict[str, Any]:
        """
        Get adapter metadata.

        Returns:
            Dictionary with adapter information.
        """
        return {
            "adapter_type": self.__class__.__name__,
            "connected": self._connected,
            "config_host": self.config.host if self.config else None,
        }
