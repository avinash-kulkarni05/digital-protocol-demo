"""
OMOP CDM Data Adapter - Query OMOP-compliant databases.

This adapter supports querying patient populations from OMOP CDM databases
(PostgreSQL, SQL Server, or other OMOP-compliant data sources).
"""

import logging
import time
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

from .base_adapter import BaseDataAdapter, ConnectionConfig, QueryResult

logger = logging.getLogger(__name__)


class OmopAdapter(BaseDataAdapter):
    """
    OMOP CDM data adapter for patient population queries.

    Supports PostgreSQL and SQL Server OMOP CDM implementations.
    Uses parameterized queries for security.
    """

    def __init__(
        self,
        config: ConnectionConfig,
        cdm_schema: str = "cdm",
        results_schema: str = "results",
    ):
        """
        Initialize OMOP adapter.

        Args:
            config: Database connection configuration.
            cdm_schema: Schema containing OMOP CDM tables.
            results_schema: Schema for query results (cohorts).
        """
        super().__init__(config)
        self.cdm_schema = cdm_schema
        self.results_schema = results_schema
        self._connection = None
        self._cursor = None
        self._total_population = None

    def connect(self) -> bool:
        """
        Establish connection to OMOP database.

        Returns:
            True if connection successful.
        """
        try:
            # Determine database type from config
            if self.config.extra_params and self.config.extra_params.get("db_type") == "sqlserver":
                import pyodbc
                conn_str = (
                    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                    f"SERVER={self.config.host},{self.config.port};"
                    f"DATABASE={self.config.database};"
                    f"UID={self.config.username};"
                    f"PWD={self.config.password};"
                )
                self._connection = pyodbc.connect(conn_str, timeout=self.config.timeout_seconds)
            else:
                # Default to PostgreSQL
                import psycopg2
                self._connection = psycopg2.connect(
                    host=self.config.host,
                    port=self.config.port,
                    database=self.config.database,
                    user=self.config.username,
                    password=self.config.password,
                    sslmode="require" if self.config.ssl_enabled else "disable",
                    connect_timeout=self.config.timeout_seconds,
                )

            self._cursor = self._connection.cursor()
            self._connected = True
            logger.info(f"Connected to OMOP database at {self.config.host}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to OMOP database: {e}")
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Close database connection."""
        if self._cursor:
            self._cursor.close()
            self._cursor = None
        if self._connection:
            self._connection.close()
            self._connection = None
        self._connected = False
        logger.info("Disconnected from OMOP database")

    def _execute_query(
        self,
        sql: str,
        params: Optional[tuple] = None,
    ) -> QueryResult:
        """
        Execute SQL query and return result.

        Args:
            sql: SQL query string.
            params: Query parameters.

        Returns:
            QueryResult with patient count.
        """
        if not self._connected:
            return QueryResult(
                patient_count=0,
                error="Not connected to database",
            )

        start_time = time.time()
        try:
            self._cursor.execute(sql, params or ())
            row = self._cursor.fetchone()
            count = row[0] if row else 0
            execution_time = (time.time() - start_time) * 1000

            return QueryResult(
                patient_count=count,
                query_executed=sql,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return QueryResult(
                patient_count=0,
                query_executed=sql,
                error=str(e),
            )

    def get_total_population(self) -> int:
        """Get total patient count in OMOP CDM."""
        if self._total_population is not None:
            return self._total_population

        sql = f"""
            SELECT COUNT(DISTINCT person_id)
            FROM {self.cdm_schema}.person
        """
        result = self._execute_query(sql)
        self._total_population = result.patient_count
        return self._total_population

    def query_condition(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
    ) -> QueryResult:
        """Query patients with specific conditions."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        if include_descendants:
            sql = f"""
                SELECT COUNT(DISTINCT co.person_id)
                FROM {self.cdm_schema}.condition_occurrence co
                JOIN {self.cdm_schema}.concept_ancestor ca
                    ON co.condition_concept_id = ca.descendant_concept_id
                WHERE ca.ancestor_concept_id IN ({','.join(['%s'] * len(concept_ids))})
            """
        else:
            sql = f"""
                SELECT COUNT(DISTINCT person_id)
                FROM {self.cdm_schema}.condition_occurrence
                WHERE condition_concept_id IN ({','.join(['%s'] * len(concept_ids))})
            """

        return self._execute_query(sql, tuple(concept_ids))

    def query_measurement(
        self,
        concept_ids: List[int],
        value_operator: str = ">=",
        value_threshold: float = 0.0,
        unit_concept_id: Optional[int] = None,
    ) -> QueryResult:
        """Query patients with specific measurement values."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        # Validate operator
        valid_operators = [">=", "<=", "=", ">", "<", "!="]
        if value_operator not in valid_operators:
            return QueryResult(patient_count=0, error=f"Invalid operator: {value_operator}")

        sql = f"""
            SELECT COUNT(DISTINCT person_id)
            FROM {self.cdm_schema}.measurement
            WHERE measurement_concept_id IN ({','.join(['%s'] * len(concept_ids))})
            AND value_as_number {value_operator} %s
        """
        params = list(concept_ids) + [value_threshold]

        if unit_concept_id:
            sql += " AND unit_concept_id = %s"
            params.append(unit_concept_id)

        return self._execute_query(sql, tuple(params))

    def query_drug_exposure(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
        days_supply_min: Optional[int] = None,
    ) -> QueryResult:
        """Query patients with specific drug exposures."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        if include_descendants:
            sql = f"""
                SELECT COUNT(DISTINCT de.person_id)
                FROM {self.cdm_schema}.drug_exposure de
                JOIN {self.cdm_schema}.concept_ancestor ca
                    ON de.drug_concept_id = ca.descendant_concept_id
                WHERE ca.ancestor_concept_id IN ({','.join(['%s'] * len(concept_ids))})
            """
        else:
            sql = f"""
                SELECT COUNT(DISTINCT person_id)
                FROM {self.cdm_schema}.drug_exposure
                WHERE drug_concept_id IN ({','.join(['%s'] * len(concept_ids))})
            """

        params = list(concept_ids)
        if days_supply_min:
            sql += " AND days_supply >= %s"
            params.append(days_supply_min)

        return self._execute_query(sql, tuple(params))

    def query_procedure(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
    ) -> QueryResult:
        """Query patients with specific procedures."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        if include_descendants:
            sql = f"""
                SELECT COUNT(DISTINCT po.person_id)
                FROM {self.cdm_schema}.procedure_occurrence po
                JOIN {self.cdm_schema}.concept_ancestor ca
                    ON po.procedure_concept_id = ca.descendant_concept_id
                WHERE ca.ancestor_concept_id IN ({','.join(['%s'] * len(concept_ids))})
            """
        else:
            sql = f"""
                SELECT COUNT(DISTINCT person_id)
                FROM {self.cdm_schema}.procedure_occurrence
                WHERE procedure_concept_id IN ({','.join(['%s'] * len(concept_ids))})
            """

        return self._execute_query(sql, tuple(concept_ids))

    def query_observation(
        self,
        concept_ids: List[int],
        value_as_concept_id: Optional[int] = None,
        value_as_string: Optional[str] = None,
    ) -> QueryResult:
        """Query patients with specific observations."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        sql = f"""
            SELECT COUNT(DISTINCT person_id)
            FROM {self.cdm_schema}.observation
            WHERE observation_concept_id IN ({','.join(['%s'] * len(concept_ids))})
        """
        params = list(concept_ids)

        if value_as_concept_id:
            sql += " AND value_as_concept_id = %s"
            params.append(value_as_concept_id)
        if value_as_string:
            sql += " AND value_as_string = %s"
            params.append(value_as_string)

        return self._execute_query(sql, tuple(params))

    def query_demographics(
        self,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None,
        gender_concept_id: Optional[int] = None,
    ) -> QueryResult:
        """Query patients by demographics."""
        conditions = []
        params = []

        if min_age is not None:
            conditions.append("EXTRACT(YEAR FROM CURRENT_DATE) - year_of_birth >= %s")
            params.append(min_age)
        if max_age is not None:
            conditions.append("EXTRACT(YEAR FROM CURRENT_DATE) - year_of_birth <= %s")
            params.append(max_age)
        if gender_concept_id:
            conditions.append("gender_concept_id = %s")
            params.append(gender_concept_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
            SELECT COUNT(DISTINCT person_id)
            FROM {self.cdm_schema}.person
            WHERE {where_clause}
        """

        return self._execute_query(sql, tuple(params))

    def execute_sql(self, sql: str, params: Optional[Dict[str, Any]] = None) -> QueryResult:
        """Execute raw SQL query."""
        param_tuple = tuple(params.values()) if params else None
        return self._execute_query(sql, param_tuple)

    def get_adapter_info(self) -> Dict[str, Any]:
        """Get adapter metadata."""
        info = super().get_adapter_info()
        info.update({
            "cdm_schema": self.cdm_schema,
            "results_schema": self.results_schema,
            "database": self.config.database if self.config else None,
            "total_population": self._total_population,
        })
        return info
