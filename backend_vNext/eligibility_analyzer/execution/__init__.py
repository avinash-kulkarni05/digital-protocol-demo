"""
QEB Execution Engine

Provides funnel execution capabilities against mock or real OMOP CDM databases.
Executes validated QEBs through sequential funnel stages to produce
patient cohort filtering results.

Key Components:
- funnel_executor: Core execution logic for running QEBs through funnel stages
- database_adapters: Mock and real database adapters for patient filtering
"""

from .funnel_executor import (
    FunnelExecutor,
)

from .database_adapters import (
    DatabaseAdapter,
    MockDatabaseAdapter,
)

__all__ = [
    "FunnelExecutor",
    "DatabaseAdapter",
    "MockDatabaseAdapter",
]
