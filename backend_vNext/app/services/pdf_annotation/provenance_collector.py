"""
Provenance Collector

Traverses USDM 4.0 JSON to extract all provenance objects with their
page numbers and text snippets for PDF annotation.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProvenanceItem:
    """Represents a single provenance reference extracted from USDM JSON."""

    page_number: int
    text_snippet: str
    field_path: str  # JSON path (e.g., "$.studyPhase.provenance")
    module_name: str  # Source module (e.g., "study_metadata")
    section_number: str | None = None
    field_name: str = ""  # Short field name for display (e.g., "studyPhase")

    def __hash__(self):
        """Hash by page_number and text_snippet for deduplication."""
        return hash((self.page_number, self.text_snippet))

    def __eq__(self, other):
        """Equality check for deduplication."""
        if not isinstance(other, ProvenanceItem):
            return False
        return self.page_number == other.page_number and self.text_snippet == other.text_snippet


@dataclass
class CollectionStats:
    """Statistics from provenance collection."""

    total_found: int = 0
    unique_after_dedup: int = 0
    pages_covered: int = 0
    by_module: dict = field(default_factory=dict)


class ProvenanceCollector:
    """
    Collects provenance objects from USDM 4.0 JSON structure.

    Handles all four provenance patterns:
    1. Nested provenance (object.provenance)
    2. Value + provenance pattern (field: {value, provenance})
    3. Array + provenance pattern (field: {values, provenance})
    4. Array items with individual provenance
    """

    # Fields that should be ignored during traversal
    SKIP_FIELDS = {
        "id", "instanceType", "schemaVersion", "_metadata",
        "extractedAt", "modelVersion", "extensionAttributes"
    }

    # Module mapping from USDM sections to module names
    MODULE_MAPPING = {
        "study": "study_metadata",
        "studyMetadata": "study_metadata",
        "studyDesign": "arms_design",
        "endpointsEstimandsSAP": "endpoints_estimands_sap",
        "adverseEvents": "adverse_events",
        "safetyDecisionPoints": "safety_decision_points",
        "concomitantMedications": "concomitant_medications",
        "biospecimenHandling": "biospecimen_handling",
        "laboratorySpecifications": "laboratory_specifications",
        "informedConsent": "informed_consent",
        "proSpecifications": "pro_specifications",
        "dataManagement": "data_management",
        "siteOperationsLogistics": "site_operations_logistics",
        "qualityManagement": "quality_management",
        "withdrawalProcedures": "withdrawal_procedures",
        "imagingCentralReading": "imaging_central_reading",
        "pkpdSampling": "pkpd_sampling",
    }

    def __init__(self):
        self._items: list[ProvenanceItem] = []
        self._stats = CollectionStats()

    def collect(self, usdm_json: dict) -> list[ProvenanceItem]:
        """
        Recursively traverse USDM JSON to extract all provenance objects.

        Args:
            usdm_json: The complete USDM 4.0 JSON document

        Returns:
            List of ProvenanceItem objects
        """
        self._items = []
        self._stats = CollectionStats()

        # Start traversal from root
        self._traverse(usdm_json, path="$", module_name="root")

        self._stats.total_found = len(self._items)
        logger.info(f"Collected {self._stats.total_found} provenance items from USDM JSON")

        return self._items

    def deduplicate(self, items: list[ProvenanceItem]) -> list[ProvenanceItem]:
        """
        Remove duplicate provenance items by (page_number, text_snippet).

        Keeps the first occurrence of each unique item.

        Args:
            items: List of provenance items to deduplicate

        Returns:
            Deduplicated list of provenance items
        """
        seen = set()
        unique_items = []

        for item in items:
            key = (item.page_number, item.text_snippet)
            if key not in seen:
                seen.add(key)
                unique_items.append(item)

        self._stats.unique_after_dedup = len(unique_items)
        removed_count = len(items) - len(unique_items)

        if removed_count > 0:
            logger.info(f"Removed {removed_count} duplicate provenance items")

        return unique_items

    def group_by_page(self, items: list[ProvenanceItem]) -> dict[int, list[ProvenanceItem]]:
        """
        Group provenance items by page number for efficient page-by-page processing.

        Args:
            items: List of provenance items

        Returns:
            Dictionary mapping page numbers to lists of provenance items
        """
        grouped: dict[int, list[ProvenanceItem]] = {}

        for item in items:
            if item.page_number not in grouped:
                grouped[item.page_number] = []
            grouped[item.page_number].append(item)

        self._stats.pages_covered = len(grouped)
        logger.info(f"Provenance items span {self._stats.pages_covered} pages")

        return grouped

    def group_by_module(self, items: list[ProvenanceItem]) -> dict[str, list[ProvenanceItem]]:
        """
        Group provenance items by module name for bookmark generation.

        Args:
            items: List of provenance items

        Returns:
            Dictionary mapping module names to lists of provenance items
        """
        grouped: dict[str, list[ProvenanceItem]] = {}

        for item in items:
            if item.module_name not in grouped:
                grouped[item.module_name] = []
            grouped[item.module_name].append(item)

        self._stats.by_module = {k: len(v) for k, v in grouped.items()}

        return grouped

    def get_stats(self) -> CollectionStats:
        """Return collection statistics."""
        return self._stats

    def _traverse(self, obj: Any, path: str, module_name: str) -> None:
        """
        Recursively traverse JSON structure to find provenance objects.

        Args:
            obj: Current JSON object/value being traversed
            path: Current JSON path (e.g., "$.studyPhase")
            module_name: Current module context
        """
        if obj is None:
            return

        if isinstance(obj, dict):
            self._traverse_dict(obj, path, module_name)
        elif isinstance(obj, list):
            self._traverse_list(obj, path, module_name)

    def _traverse_dict(self, obj: dict, path: str, module_name: str) -> None:
        """Traverse a dictionary object."""
        # Update module context if we're entering a domain section
        if "domainSections" in path:
            for section_key in self.MODULE_MAPPING:
                if section_key in obj:
                    module_name = self.MODULE_MAPPING[section_key]
                    break

        # Check if this object has a provenance field
        if "provenance" in obj:
            provenance = obj["provenance"]
            if self._is_valid_provenance(provenance):
                field_name = self._extract_field_name(path)
                item = self._create_provenance_item(provenance, path, module_name, field_name)
                if item:
                    self._items.append(item)

        # Continue traversing child objects
        for key, value in obj.items():
            if key in self.SKIP_FIELDS:
                continue

            # Update module context for top-level domain sections
            new_module = module_name
            if key in self.MODULE_MAPPING:
                new_module = self.MODULE_MAPPING[key]

            child_path = f"{path}.{key}"
            self._traverse(value, child_path, new_module)

    def _traverse_list(self, obj: list, path: str, module_name: str) -> None:
        """Traverse a list/array object."""
        for idx, item in enumerate(obj):
            child_path = f"{path}[{idx}]"
            self._traverse(item, child_path, module_name)

    def _is_valid_provenance(self, provenance: Any) -> bool:
        """
        Check if a provenance object has the required fields.

        Args:
            provenance: The provenance object to validate

        Returns:
            True if provenance has page_number and text_snippet
        """
        if not isinstance(provenance, dict):
            return False

        has_page = "page_number" in provenance and provenance["page_number"] is not None
        has_snippet = "text_snippet" in provenance and provenance["text_snippet"]

        return has_page and has_snippet

    def _create_provenance_item(
        self,
        provenance: dict,
        path: str,
        module_name: str,
        field_name: str
    ) -> ProvenanceItem | None:
        """
        Create a ProvenanceItem from a provenance object.

        Args:
            provenance: The provenance dictionary
            path: JSON path to this provenance
            module_name: The extraction module that produced this
            field_name: Short field name for display

        Returns:
            ProvenanceItem or None if invalid
        """
        try:
            page_number = int(provenance["page_number"])
            text_snippet = str(provenance["text_snippet"]).strip()

            # Validate page number
            if page_number < 1:
                logger.warning(f"Invalid page number {page_number} at {path}")
                return None

            # Validate snippet length
            if len(text_snippet) < 5:
                logger.warning(f"Text snippet too short at {path}: '{text_snippet}'")
                return None

            section_number = provenance.get("section_number")
            if section_number:
                section_number = str(section_number)

            return ProvenanceItem(
                page_number=page_number,
                text_snippet=text_snippet,
                field_path=f"{path}.provenance",
                module_name=module_name,
                section_number=section_number,
                field_name=field_name
            )

        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to create provenance item at {path}: {e}")
            return None

    def _extract_field_name(self, path: str) -> str:
        """
        Extract a short field name from a JSON path.

        Examples:
            "$.studyPhase" -> "studyPhase"
            "$.studyIdentifiers[0]" -> "studyIdentifiers[0]"
            "$.domainSections.studyDesign.studyArms[0].interventions[1]" -> "interventions[1]"

        Args:
            path: Full JSON path

        Returns:
            Short field name for display
        """
        # Split by dots and get last part
        parts = path.split(".")
        if not parts:
            return "unknown"

        last_part = parts[-1]

        # Clean up any trailing provenance reference
        if last_part == "provenance":
            if len(parts) > 1:
                last_part = parts[-2]

        return last_part
