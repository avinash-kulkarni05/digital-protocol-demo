"""
Database Adapters for QEB Funnel Execution

Provides abstract and concrete database adapters for executing QEB SQL queries
against patient databases. Supports mock database for testing and development,
with extensibility for real OMOP CDM connections.

Key Design Decision:
- Mock adapter uses PROBABILISTIC FILTERING rather than SQL parsing
- This avoids complex SQL parser implementation
- Provides realistic elimination patterns
- Is configurable via match_rates dictionary
- Uses seeded random for reproducible results
"""

import logging
import random
from abc import ABC, abstractmethod
from typing import Dict, List, Set, Optional

logger = logging.getLogger(__name__)


class DatabaseAdapter(ABC):
    """Abstract adapter for mock or real OMOP CDM."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable database name."""
        ...

    @abstractmethod
    def get_base_population(self) -> Set[int]:
        """Get the full base population of patient IDs."""
        ...

    @abstractmethod
    def filter_cohort_by_concepts(
        self,
        cohort: Set[int],
        concept_ids: List[int],
        is_inclusion: bool,
    ) -> Set[int]:
        """
        Filter cohort by OMOP concept IDs.

        Args:
            cohort: Current patient cohort (set of patient IDs).
            concept_ids: OMOP concept IDs to filter by.
            is_inclusion: If True, return patients WITH concepts.
                         If False, return patients WITHOUT concepts.

        Returns:
            Set of patient IDs matching the filter.
        """
        ...


class MockDatabaseAdapter(DatabaseAdapter):
    """
    Mock adapter using probabilistic filtering.

    NO SQL PARSING - uses concept IDs directly with configurable match rates.
    This design decision was made because:
    1. Avoids complex SQL parser implementation
    2. Provides realistic elimination patterns
    3. Is configurable via match_rates dictionary
    4. Uses seeded random for reproducible results

    At the feasibility stage, we prioritize RECALL over PRECISION:
    - Results represent UPPER BOUND estimates
    - False positives are acceptable (filtered at screening)
    - False negatives are problematic (missed enrollment potential)
    """

    # Default match rates by clinical domain
    DEFAULT_MATCH_RATES = {
        "disease": 0.01,       # 1% have any specific disease
        "lab_abnormal": 0.15,  # 15% have any specific lab abnormality
        "medication": 0.10,    # 10% on any specific medication
        "procedure": 0.05,     # 5% had any specific procedure
        "default": 0.20,       # 20% default match rate
    }

    def __init__(
        self,
        patient_count: int = 10000,
        seed: int = 42,
        match_rates: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize mock database adapter.

        Args:
            patient_count: Number of synthetic patients in base population.
            seed: Random seed for reproducible results.
            match_rates: Optional custom match rates by domain.
        """
        self.patient_count = patient_count
        self._base_population = set(range(1, patient_count + 1))
        self._seed = seed
        self._rng = random.Random(seed)

        # Merge custom match rates with defaults
        self.match_rates = self.DEFAULT_MATCH_RATES.copy()
        if match_rates:
            self.match_rates.update(match_rates)

        logger.info(
            f"MockDatabaseAdapter initialized with {patient_count:,} patients, "
            f"seed={seed}"
        )

    @property
    def name(self) -> str:
        """Human-readable database name."""
        return f"Mock OMOP CDM ({self.patient_count:,} patients)"

    def get_base_population(self) -> Set[int]:
        """Get the full base population of patient IDs."""
        return self._base_population.copy()

    def filter_cohort_by_concepts(
        self,
        cohort: Set[int],
        concept_ids: List[int],
        is_inclusion: bool,
    ) -> Set[int]:
        """
        Probabilistic filtering based on number of concepts.

        More concepts = slightly higher match rate (OR logic approximation).
        The match rate is adjusted based on concept count to simulate
        broader recall when more related codes are included.

        Args:
            cohort: Current patient cohort (set of patient IDs).
            concept_ids: OMOP concept IDs to filter by.
            is_inclusion: If True, return patients WITH concepts.
                         If False, return patients WITHOUT concepts.

        Returns:
            Set of patient IDs matching the filter.
        """
        if not concept_ids:
            # No concepts to filter by
            return cohort if is_inclusion else set()

        # Base match rate - slightly higher for multiple concepts (OR effect)
        # This approximates the recall-oriented SQL philosophy
        base_rate = self.match_rates["default"]
        or_bonus = 0.1 * (len(concept_ids) - 1)  # +10% per additional concept
        adjusted_rate = min(base_rate * (1 + or_bonus), 0.95)

        # Create deterministic but varied matching based on concept IDs
        # This ensures same concept always matches same patients
        concept_hash = sum(concept_ids) % 1000
        concept_rng = random.Random(self._seed + concept_hash)

        # Return subset of cohort based on adjusted match rate
        matching = {
            pid for pid in cohort
            if concept_rng.random() < adjusted_rate
        }

        logger.debug(
            f"MockDB filter: {len(concept_ids)} concepts, "
            f"rate={adjusted_rate:.2%}, matched={len(matching)}/{len(cohort)}"
        )

        return matching

    def filter_cohort_by_domain(
        self,
        cohort: Set[int],
        domain: str,
        concept_ids: List[int],
    ) -> Set[int]:
        """
        Filter cohort using domain-specific match rates.

        Args:
            cohort: Current patient cohort.
            domain: OMOP domain (Condition, Drug, Measurement, Procedure).
            concept_ids: OMOP concept IDs to filter by.

        Returns:
            Set of patient IDs matching the domain filter.
        """
        if not concept_ids:
            return set()

        # Get domain-specific base rate
        domain_key = {
            "Condition": "disease",
            "Drug": "medication",
            "Measurement": "lab_abnormal",
            "Procedure": "procedure",
        }.get(domain, "default")

        base_rate = self.match_rates.get(domain_key, self.match_rates["default"])

        # Apply OR bonus for multiple concepts
        or_bonus = 0.1 * (len(concept_ids) - 1)
        adjusted_rate = min(base_rate * (1 + or_bonus), 0.95)

        # Deterministic matching
        concept_hash = sum(concept_ids) % 1000
        concept_rng = random.Random(self._seed + concept_hash)

        matching = {
            pid for pid in cohort
            if concept_rng.random() < adjusted_rate
        }

        logger.debug(
            f"MockDB domain filter [{domain}]: {len(concept_ids)} concepts, "
            f"rate={adjusted_rate:.2%}, matched={len(matching)}/{len(cohort)}"
        )

        return matching

    def simulate_killer_criterion(
        self,
        cohort: Set[int],
        elimination_rate: float,
    ) -> Set[int]:
        """
        Simulate a killer criterion with specific elimination rate.

        Killer criteria have very high elimination rates (>70%).
        This method allows explicit control for known killers.

        Args:
            cohort: Current patient cohort.
            elimination_rate: Target elimination rate (0.0-1.0).

        Returns:
            Set of patient IDs remaining after elimination.
        """
        survival_rate = 1.0 - elimination_rate

        # Deterministic selection
        sorted_cohort = sorted(cohort)
        keep_count = int(len(sorted_cohort) * survival_rate)
        remaining = set(sorted_cohort[:keep_count])

        logger.debug(
            f"MockDB killer criterion: elimination={elimination_rate:.2%}, "
            f"remaining={len(remaining)}/{len(cohort)}"
        )

        return remaining

    def reset_random_state(self) -> None:
        """Reset random number generator to initial seed."""
        self._rng = random.Random(self._seed)
        logger.debug("MockDB random state reset")


class OMOPDatabaseAdapter(DatabaseAdapter):
    """
    Real OMOP CDM database adapter (stub for future implementation).

    This adapter will connect to actual OMOP CDM databases
    and execute real SQL queries for patient filtering.

    NOT IMPLEMENTED IN MVP - use MockDatabaseAdapter instead.
    """

    def __init__(
        self,
        connection_string: str,
        schema: str = "cdm",
    ):
        """
        Initialize OMOP CDM database adapter.

        Args:
            connection_string: Database connection string.
            schema: OMOP CDM schema name.
        """
        self.connection_string = connection_string
        self.schema = schema
        raise NotImplementedError(
            "OMOPDatabaseAdapter is not yet implemented. "
            "Use MockDatabaseAdapter for development and testing."
        )

    @property
    def name(self) -> str:
        """Human-readable database name."""
        return f"OMOP CDM ({self.schema})"

    def get_base_population(self) -> Set[int]:
        """Get the full base population of patient IDs."""
        raise NotImplementedError("Real OMOP CDM support coming in future release")

    def filter_cohort_by_concepts(
        self,
        cohort: Set[int],
        concept_ids: List[int],
        is_inclusion: bool,
    ) -> Set[int]:
        """Filter cohort by OMOP concept IDs using real SQL."""
        raise NotImplementedError("Real OMOP CDM support coming in future release")
