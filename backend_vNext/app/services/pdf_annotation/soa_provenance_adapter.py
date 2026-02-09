"""
SOA Provenance Adapter

Converts SOA USDM provenance format to the PDF annotator format.

SOA format: {"pageNumber": 41, "tableId": "SOA-2", "rowIdx": 5, "colIdx": 2}
Annotator format: {"page_number": 41, "text_snippet": "Activity Name @ Visit Name"}
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .provenance_collector import ProvenanceItem, CollectionStats

logger = logging.getLogger(__name__)


@dataclass
class SOAAnnotationContext:
    """Context for SOA annotations - used to generate descriptive text snippets."""

    activity_name: str
    visit_name: str = ""
    table_id: str = ""
    element_type: str = ""  # "visit", "activity", "instance", "footnote"
    domain_code: str = ""


class SOAProvenanceAdapter:
    """
    Adapts SOA USDM provenance to PDF annotator format.

    SOA provenance uses camelCase (pageNumber, tableId, rowIdx, colIdx)
    while the main pipeline uses snake_case (page_number, text_snippet).

    For SOA, we generate text snippets from activity/visit names since
    SOA provenance tracks table cell coordinates rather than text excerpts.
    """

    def __init__(self):
        self._items: list[ProvenanceItem] = []
        self._stats = CollectionStats()

    def collect_from_soa_usdm(self, soa_usdm: dict) -> list[ProvenanceItem]:
        """
        Extract provenance items from SOA USDM structure.

        Args:
            soa_usdm: SOA USDM JSON with visits, activities, scheduledActivityInstances

        Returns:
            List of ProvenanceItem objects for PDF annotation
        """
        self._items = []
        self._stats = CollectionStats()

        # Build lookup maps for context
        visits_by_id = {}
        activities_by_id = {}

        # Process visits
        for visit in soa_usdm.get("visits", []):
            visit_id = visit.get("id", "")
            visit_name = visit.get("name") or visit.get("originalName", "Unknown Visit")
            visits_by_id[visit_id] = visit_name

            prov = visit.get("provenance", {})
            if self._is_valid_soa_provenance(prov):
                item = self._create_item(
                    prov,
                    context=SOAAnnotationContext(
                        activity_name="",
                        visit_name=visit_name,
                        table_id=prov.get("tableId", ""),
                        element_type="visit"
                    ),
                    field_path=f"$.visits[{visit_id}]"
                )
                if item:
                    self._items.append(item)

        # Process activities
        for activity in soa_usdm.get("activities", []):
            activity_id = activity.get("id", "")
            activity_name = activity.get("name", "Unknown Activity")
            activities_by_id[activity_id] = activity_name

            # Get domain code if available
            domain_code = ""
            if "cdiscCode" in activity:
                cdisc = activity["cdiscCode"]
                if isinstance(cdisc, dict):
                    domain_code = cdisc.get("code", "")

            prov = activity.get("provenance", {})
            if self._is_valid_soa_provenance(prov):
                item = self._create_item(
                    prov,
                    context=SOAAnnotationContext(
                        activity_name=activity_name,
                        visit_name="",
                        table_id=prov.get("tableId", ""),
                        element_type="activity",
                        domain_code=domain_code
                    ),
                    field_path=f"$.activities[{activity_id}]"
                )
                if item:
                    self._items.append(item)

        # Process scheduledActivityInstances
        for sai in soa_usdm.get("scheduledActivityInstances", []):
            visit_ref = sai.get("visitRef", "")
            activity_ref = sai.get("activityRef", "")

            visit_name = visits_by_id.get(visit_ref, "Unknown Visit")
            activity_name = activities_by_id.get(activity_ref, "Unknown Activity")

            prov = sai.get("provenance", {})
            if self._is_valid_soa_provenance(prov):
                item = self._create_item(
                    prov,
                    context=SOAAnnotationContext(
                        activity_name=activity_name,
                        visit_name=visit_name,
                        table_id=prov.get("tableId", ""),
                        element_type="instance"
                    ),
                    field_path=f"$.scheduledActivityInstances[{sai.get('id', '')}]"
                )
                if item:
                    self._items.append(item)

        # Process footnotes
        for idx, footnote in enumerate(soa_usdm.get("footnotes", [])):
            marker = footnote.get("marker", str(idx + 1))
            text = footnote.get("text", "")[:100]  # Truncate long footnote text

            prov = footnote.get("provenance", {})
            if self._is_valid_soa_provenance(prov):
                item = self._create_item(
                    prov,
                    context=SOAAnnotationContext(
                        activity_name=f"Footnote {marker}: {text}",
                        visit_name="",
                        table_id=prov.get("tableId", ""),
                        element_type="footnote"
                    ),
                    field_path=f"$.footnotes[{idx}]"
                )
                if item:
                    self._items.append(item)

        self._stats.total_found = len(self._items)
        logger.info(f"Collected {self._stats.total_found} SOA provenance items")

        return self._items

    def _is_valid_soa_provenance(self, prov: Any) -> bool:
        """Check if SOA provenance has required pageNumber."""
        if not isinstance(prov, dict):
            return False
        return "pageNumber" in prov and prov["pageNumber"] is not None

    def _create_item(
        self,
        prov: dict,
        context: SOAAnnotationContext,
        field_path: str
    ) -> ProvenanceItem | None:
        """
        Create a ProvenanceItem from SOA provenance.

        Args:
            prov: SOA provenance dict with pageNumber, tableId, etc.
            context: Annotation context with activity/visit names
            field_path: JSON path for this element

        Returns:
            ProvenanceItem or None if invalid
        """
        try:
            page_number = int(prov["pageNumber"])
            if page_number < 1:
                return None

            # Generate text snippet from context
            text_snippet = self._generate_text_snippet(context)
            if not text_snippet or len(text_snippet) < 3:
                return None

            # Generate display field name
            field_name = self._generate_field_name(context)

            return ProvenanceItem(
                page_number=page_number,
                text_snippet=text_snippet,
                field_path=field_path,
                module_name="soa_schedule",
                section_number=context.table_id,
                field_name=field_name
            )

        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to create SOA provenance item: {e}")
            return None

    def _generate_text_snippet(self, context: SOAAnnotationContext) -> str:
        """
        Generate a text snippet for annotation popup from context.

        For visits: "Visit: Screening"
        For activities: "Activity: Vital Signs [VS]"
        For instances: "Vital Signs @ Screening"
        For footnotes: "Footnote a: Some text..."
        """
        if context.element_type == "visit":
            return f"Visit: {context.visit_name}"
        elif context.element_type == "activity":
            if context.domain_code:
                return f"Activity: {context.activity_name} [{context.domain_code}]"
            return f"Activity: {context.activity_name}"
        elif context.element_type == "instance":
            return f"{context.activity_name} @ {context.visit_name}"
        elif context.element_type == "footnote":
            return context.activity_name  # Already formatted as "Footnote X: text"
        else:
            return context.activity_name or context.visit_name

    def _generate_field_name(self, context: SOAAnnotationContext) -> str:
        """Generate short field name for bookmark display."""
        if context.element_type == "visit":
            return f"Visit: {context.visit_name[:30]}"
        elif context.element_type == "activity":
            return f"Activity: {context.activity_name[:30]}"
        elif context.element_type == "instance":
            return f"{context.activity_name[:15]}@{context.visit_name[:15]}"
        elif context.element_type == "footnote":
            return context.activity_name[:40]
        else:
            return "SOA Element"

    def deduplicate(self, items: list[ProvenanceItem]) -> list[ProvenanceItem]:
        """Remove duplicate items by (page_number, text_snippet)."""
        seen = set()
        unique = []

        for item in items:
            key = (item.page_number, item.text_snippet)
            if key not in seen:
                seen.add(key)
                unique.append(item)

        self._stats.unique_after_dedup = len(unique)
        removed = len(items) - len(unique)

        if removed > 0:
            logger.info(f"Removed {removed} duplicate SOA provenance items")

        return unique

    def group_by_page(self, items: list[ProvenanceItem]) -> dict[int, list[ProvenanceItem]]:
        """Group items by page number."""
        grouped = {}
        for item in items:
            if item.page_number not in grouped:
                grouped[item.page_number] = []
            grouped[item.page_number].append(item)

        self._stats.pages_covered = len(grouped)
        return grouped

    def group_by_module(self, items: list[ProvenanceItem]) -> dict[str, list[ProvenanceItem]]:
        """Group items by module (all SOA items are in soa_schedule module)."""
        return {"soa_schedule": items}

    def get_stats(self) -> CollectionStats:
        """Return collection statistics."""
        return self._stats


def load_soa_usdm(soa_usdm_path: Path | str) -> dict | None:
    """
    Load SOA USDM JSON from file.

    Args:
        soa_usdm_path: Path to SOA USDM JSON file

    Returns:
        Parsed JSON dict or None if failed
    """
    import json

    path = Path(soa_usdm_path)
    if not path.exists():
        logger.error(f"SOA USDM file not found: {path}")
        return None

    try:
        with open(path, 'r') as f:
            data = json.load(f)

        # Handle wrapper if present (stage output has "usdm" key)
        if "usdm" in data:
            return data["usdm"]
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse SOA USDM JSON: {e}")
        return None
