"""
Context Assembler for LLM-based Activity Expansion

Assembles relevant extraction module JSON outputs for LLM queries.
No hardcoded field paths - the LLM analyzes the JSON structure.

This approach is more scalable than hardcoded field indexing because:
1. No code changes when schemas evolve
2. Works across different protocol structures
3. LLM finds relevant data intelligently

Usage:
    from soa_analyzer.interpretation.context_assembler import ContextAssembler

    assembler = ContextAssembler(extraction_outputs)
    context = assembler.get_context_for_activity("Hematology", "LB")
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ContextAssembler:
    """
    Assemble context for LLM-based activity expansion.

    Loads extraction JSON files and prepares them for LLM queries.
    No hardcoded field paths - LLM analyzes the JSON structure.
    """

    # Mapping of CDASH domain to relevant extraction modules
    # These determine which JSON files are passed to the LLM for each domain
    # Empty lists mean the activity will rely on PDF search (no extraction JSON context)
    DOMAIN_TO_MODULES = {
        "LB": ["laboratory_specifications", "biospecimen_handling", "pkpd_sampling"],
        "VS": ["laboratory_specifications", "study_metadata"],  # Vital signs may be in metadata
        "IM": ["imaging_central_reading"],
        "PR": ["imaging_central_reading"],    # Procedures
        "QS": ["pro_specifications"],          # Questionnaires/PRO
        "PC": ["pkpd_sampling"],               # Pharmacokinetics
        "EG": ["laboratory_specifications"],   # ECG/Cardiac may be in lab specs
        "BS": ["biospecimen_handling"],        # Biospecimen collection
        # Additional domains for procedure expansion (rely on PDF search)
        "PE": [],                              # Physical exam - PDF search only
        "TU": ["imaging_central_reading"],    # Tumor assessments
        "SC": ["biospecimen_handling", "pkpd_sampling"],  # Specimen collection
        "MH": [],                              # Medical history - PDF search only
    }

    # Module display names for logging
    MODULE_NAMES = {
        "laboratory_specifications": "Laboratory Specifications",
        "biospecimen_handling": "Biospecimen Handling",
        "pkpd_sampling": "PK/PD Sampling",
        "imaging_central_reading": "Imaging & Central Reading",
        "pro_specifications": "PRO Specifications",
    }

    def __init__(self, extraction_outputs: Optional[Dict[str, Dict]] = None):
        """
        Initialize the context assembler.

        Args:
            extraction_outputs: Dict mapping module names to their extracted JSON data
                e.g., {"laboratory_specifications": {...}, "biospecimen_handling": {...}}
        """
        self.extraction_outputs = extraction_outputs or {}
        self._log_available_modules()

    def _log_available_modules(self) -> None:
        """Log which extraction modules are available."""
        available = [m for m in self.extraction_outputs.keys() if self.extraction_outputs.get(m)]
        if available:
            logger.info(f"ContextAssembler: {len(available)} extraction modules available: {available}")
        else:
            logger.warning("ContextAssembler: No extraction modules available")

    def get_context_for_activity(
        self,
        activity_name: str,
        cdash_domain: str,
    ) -> Dict[str, Any]:
        """
        Get relevant extraction JSON context for an activity.

        The context includes all extraction module data that might be relevant
        for the given activity based on its CDASH domain.

        Args:
            activity_name: Name of the activity (e.g., "Hematology", "Vital Signs")
            cdash_domain: CDISC CDASH domain code (e.g., "LB", "VS", "IM")

        Returns:
            Dict with:
            - activity_name: The activity name
            - cdash_domain: The CDASH domain
            - extraction_data: Dict mapping module names to their JSON data
            - modules_found: List of modules that had data
        """
        relevant_modules = self.DOMAIN_TO_MODULES.get(cdash_domain, [])
        context = {}
        modules_found = []

        for module in relevant_modules:
            module_data = self.extraction_outputs.get(module)
            if module_data:
                context[module] = module_data
                modules_found.append(module)

        if modules_found:
            logger.debug(
                f"Context for '{activity_name}' ({cdash_domain}): "
                f"found data in {modules_found}"
            )
        else:
            logger.debug(
                f"Context for '{activity_name}' ({cdash_domain}): "
                f"no relevant extraction data found"
            )

        return {
            "activity_name": activity_name,
            "cdash_domain": cdash_domain,
            "extraction_data": context,
            "modules_found": modules_found,
        }

    def get_all_context(self) -> Dict[str, Any]:
        """
        Get all extraction data as context.

        Useful when searching across all modules regardless of domain.

        Returns:
            Dict with all extraction module data
        """
        return {
            "extraction_data": self.extraction_outputs,
            "modules_available": list(self.extraction_outputs.keys()),
        }

    def has_context_for_domain(self, cdash_domain: str) -> bool:
        """
        Check if there's any extraction data relevant to a domain.

        Args:
            cdash_domain: CDISC CDASH domain code

        Returns:
            True if at least one relevant module has data
        """
        relevant_modules = self.DOMAIN_TO_MODULES.get(cdash_domain, [])
        return any(
            self.extraction_outputs.get(module)
            for module in relevant_modules
        )

    def get_relevant_modules_for_domain(self, cdash_domain: str) -> List[str]:
        """
        Get list of modules relevant to a domain that have data.

        Args:
            cdash_domain: CDISC CDASH domain code

        Returns:
            List of module names that have data
        """
        relevant_modules = self.DOMAIN_TO_MODULES.get(cdash_domain, [])
        return [
            module for module in relevant_modules
            if self.extraction_outputs.get(module)
        ]
