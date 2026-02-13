"""
Extraction Review Generator - Phase 1 UI JSON

Transforms raw SOA extraction output into a user-friendly JSON format
for extraction validation ("Did we read the PDF correctly?").

This generator produces the _extraction_review.json file that powers:
- Side-by-side PDF image vs extracted grid comparison
- Editable activity-visit matrix
- Footnote linkage panel
- Validation checklist

Usage:
    from soa_analyzer.output.extraction_review_generator import (
        ExtractionReviewGenerator,
        generate_extraction_review,
    )

    generator = ExtractionReviewGenerator()
    review_json = generator.generate(soa_extraction_output, protocol_id)
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"

# =============================================================================
# SECTION DESCRIPTIONS
# =============================================================================
# These descriptions explain the purpose and downstream usage of each section.
# They are inserted into the JSON output to provide context for reviewers.

FOOTNOTES_SECTION_DESCRIPTION = """
## Footnotes Section

This section contains all footnotes extracted from the Schedule of Activities (SOA) table.
Each footnote has been classified into a high-level category based on its downstream automation impact.

### Footnote Categories

| Category | Description | EDC Impact | Downstream Usage |
|----------|-------------|------------|------------------|
| **CONDITIONAL** | Rules that create branch logic | Triggers show/hide fields, skip patterns | • EDC edit checks<br>• Conditional form display<br>• Population-specific data collection |
| **SCHEDULING** | Rules affecting visit timing | Drives visit schedule generation | • Visit window calculations<br>• Calendar exports<br>• Patient reminder systems |
| **OPERATIONAL** | Site procedures | Informational annotations | • Site instructions<br>• Training documentation<br>• Monitoring checklists |

### Subcategories

**CONDITIONAL:**
- `population_subset`: Only for specific populations (e.g., females, subjects with CNS metastases)
- `clinical_indication`: Triggered by clinical findings (e.g., if clinically indicated)
- `prior_event`: Depends on prior study events (e.g., if Final Visit < 30 days from last dose)
- `triggered`: Activated by specific conditions (e.g., discontinuation, adverse event)

**SCHEDULING:**
- `visit_window`: Defines acceptable time range (e.g., within 28 days of randomization)
- `recurrence`: Defines repeating schedule (e.g., every 9 weeks, q3 weeks)
- `timing_constraint`: Defines intra-visit timing (e.g., pre-dose, before infusion)
- `relative_timing`: Timing relative to another event (e.g., within 72 hours)

**OPERATIONAL:**
- `specimen_handling`: Collection/processing/storage instructions (e.g., 12 mL blood, centrifuge)
- `consent_procedure`: Informed consent requirements
- `documentation`: What to document/collect (e.g., all anti-cancer therapy)
- `site_instruction`: General site operational guidance

### Multi-Label Footnotes

Some footnotes may have BOTH a condition AND timing constraint. These are assigned multiple categories
(e.g., ["CONDITIONAL", "SCHEDULING"]) and affect both EDC branching logic AND scheduling.

### EDC Impact Flags

Each footnote includes `edcImpact` flags for quick filtering:
- `affectsScheduling`: true if footnote affects visit calendar/timing
- `affectsBranching`: true if footnote creates conditional show/hide logic
- `isInformational`: true if footnote is purely informational (no EDC automation impact)
"""

VISITS_SECTION_DESCRIPTION = """
## Visits Section

This section contains all visits (encounters) extracted from the SOA table column headers.
Each visit represents a scheduled timepoint in the study.

### Key Fields
- **displayName**: Clean visit name for display
- **originalText**: Exact text from the table header
- **timing**: Day/week number relative to study reference point
- **window**: Visit window (e.g., ±3 days)
- **footnoteRefs**: Footnote markers associated with this visit

### Downstream Usage
- **EDC Build**: Creates Visit Forms structure
- **Schedule Generation**: Drives patient visit calendar
- **CDISC Mapping**: Maps to SDTM TV (Trial Visits) domain
"""

ACTIVITIES_SECTION_DESCRIPTION = """
## Activities Section

This section contains all activities (assessments/procedures) extracted from the SOA table row headers.
Each activity represents a clinical procedure or assessment performed at one or more visits.

### Key Fields
- **displayName**: Clean activity name for display
- **originalText**: Exact text from the table row
- **category**: CDISC domain category (e.g., VITAL_SIGNS, LABORATORY, IMAGING)
- **footnoteRefs**: Footnote markers associated with this activity

### Downstream Usage
- **EDC Build**: Creates CRF pages and forms
- **CDISC Mapping**: Maps to SDTM domains (VS, LB, EG, PE, etc.)
- **Protocol Mining**: Links to lab specs, PK/PD, safety parameters
"""

MATRIX_SECTION_DESCRIPTION = """
## Activity-Visit Matrix Section

This section contains the activity-visit matrix showing which activities are scheduled at each visit.
Each cell indicates whether an activity is required (X), optional (O), or not scheduled (-).

### Legend
- **X**: Required assessment - must be completed at this visit
- **O**: Optional assessment - may be completed at site discretion
- **-**: Not scheduled - activity does not occur at this visit
- **(empty)**: Not applicable - typically for merged cells or section headers

### Downstream Usage
- **EDC Build**: Creates scheduled forms per visit
- **SAI Generation**: Each X mark becomes a ScheduledActivityInstance
- **Protocol Compliance**: Baseline for monitoring deviations
"""


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class ExtractionValidationItem:
    """Single validation checklist item."""
    id: str
    category: str  # COMPLETENESS, ACCURACY, FOOTNOTES
    question: str
    auto_status: str  # PASS, FAIL, REVIEW
    confidence: float
    details: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "question": self.question,
            "autoStatus": self.auto_status,
            "confidence": self.confidence,
            "details": self.details,
        }


@dataclass
class CellProvenance:
    """Provenance for a matrix cell."""
    table_id: str
    page_number: Optional[int]
    row_index: int
    col_index: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tableId": self.table_id,
            "pageNumber": self.page_number,
            "cellCoords": [self.row_index, self.col_index],
        }


@dataclass
class CellValue:
    """Single cell in the activity-visit matrix."""
    visit_id: str
    value: str  # "X", "O", "-", ""
    footnote_refs: List[str] = field(default_factory=list)
    raw_content: str = ""
    provenance: Optional[CellProvenance] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "visitId": self.visit_id,
            "value": self.value,
            "footnoteRefs": self.footnote_refs,
            "rawContent": self.raw_content,
        }
        if self.provenance:
            result["provenance"] = self.provenance.to_dict()
        return result


@dataclass
class MatrixRow:
    """Single row in the activity-visit matrix."""
    activity_id: str
    activity_name: str
    cells: List[CellValue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "cells": [c.to_dict() for c in self.cells],
        }


@dataclass
class ExtractedVisit:
    """Extracted visit from SOA table."""
    id: str
    column_index: int
    display_name: str
    original_text: str
    timing: Optional[Dict[str, Any]] = None
    window: Optional[Dict[str, Any]] = None
    footnote_refs: List[str] = field(default_factory=list)
    provenance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "columnIndex": self.column_index,
            "displayName": self.display_name,
            "originalText": self.original_text,
            "timing": self.timing,
            "window": self.window,
            "footnoteRefs": self.footnote_refs,
            "provenance": self.provenance,
        }


@dataclass
class ExtractedActivity:
    """Extracted activity from SOA table."""
    id: str
    row_index: int
    display_name: str
    original_text: str
    category: Optional[str] = None
    footnote_refs: List[str] = field(default_factory=list)
    provenance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "rowIndex": self.row_index,
            "displayName": self.display_name,
            "originalText": self.original_text,
            "category": self.category,
            "footnoteRefs": self.footnote_refs,
            "provenance": self.provenance,
        }


@dataclass
class ExtractedFootnote:
    """Extracted footnote from SOA table."""
    id: str
    marker: str
    text: str
    applies_to: Dict[str, List] = field(default_factory=lambda: {
        "visits": [], "activities": [], "cells": []
    })
    provenance: Optional[Dict[str, Any]] = None
    # Category classification fields
    rule_type: str = "reference"
    category: Any = "OPERATIONAL"  # str or List[str] for multi-label
    subcategory: Optional[str] = None
    classification_reasoning: str = ""
    edc_impact: Optional[Dict[str, bool]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "marker": self.marker,
            "text": self.text,
            "ruleType": self.rule_type,
            "category": self.category,
            "subcategory": self.subcategory,
            "classificationReasoning": self.classification_reasoning,
            "edcImpact": self.edc_impact or {
                "affectsScheduling": False,
                "affectsBranching": False,
                "isInformational": True,
            },
            "appliesTo": self.applies_to,
            "provenance": self.provenance,
        }


# =============================================================================
# MAIN GENERATOR CLASS
# =============================================================================


class ExtractionReviewGenerator:
    """
    Generates Phase 1 Extraction Review JSON for UI.

    Transforms raw SOA extraction output into a structured format
    optimized for user validation of extraction accuracy.
    """

    def __init__(self):
        self._warnings: List[str] = []
        self._confidence_sum: float = 0.0
        self._confidence_count: int = 0

    def generate(
        self,
        soa_output: Dict[str, Any],
        protocol_id: str,
        protocol_title: str = "",
        pdf_image_base_url: str = "/api/soa/images",
    ) -> Dict[str, Any]:
        """
        Generate extraction review JSON from SOA extraction output.

        Args:
            soa_output: Raw SOA extraction output (from extraction pipeline)
            protocol_id: Protocol identifier
            protocol_title: Protocol display title
            pdf_image_base_url: Base URL for PDF page images

        Returns:
            Extraction review JSON for UI
        """
        self._warnings = []
        self._confidence_sum = 0.0
        self._confidence_count = 0

        logger.info(f"Generating extraction review for {protocol_id}")

        # Extract tables from SOA output
        # Handle different input formats:
        # 1. scheduleOfActivities structure (from full SOA schedule output)
        # 2. Direct USDM structure with visits/activities (from raw HTML interpretation)
        soa_tables = soa_output.get("scheduleOfActivities", [])
        if not soa_tables:
            soa_tables = soa_output.get("tables", [])

        # If no tables but has visits/activities directly, wrap as single table
        if not soa_tables and (soa_output.get("visits") or soa_output.get("activities")):
            # Create synthetic table from raw USDM structure
            soa_tables = [{
                "id": "SOA-1",
                "table_title": "Schedule of Activities",
                "table_type": "MAIN_SOA",
                "pages": [],  # Will be populated from provenance
                "visits": soa_output.get("visits", []),
                "activities": soa_output.get("activities", []),
                "scheduledActivityInstances": soa_output.get("scheduledActivityInstances", []),
                "footnotes": soa_output.get("footnotes", []),
                "_is_synthetic": True,  # Flag for different processing
            }]

        # Process each table
        tables_json = []
        total_visits = 0
        total_activities = 0
        total_sais = 0
        total_footnotes = 0

        for idx, table in enumerate(soa_tables):
            table_json = self._process_table(table, idx, pdf_image_base_url)
            tables_json.append(table_json)

            # Accumulate counts - handle both old (array) and new (object with items) formats
            visits_section = table_json.get("visits", {})
            activities_section = table_json.get("activities", {})
            footnotes_section = table_json.get("footnotes", {})

            total_visits += len(visits_section.get("items", []) if isinstance(visits_section, dict) else visits_section)
            total_activities += len(activities_section.get("items", []) if isinstance(activities_section, dict) else activities_section)
            total_sais += self._count_scheduled_instances(table_json.get("matrix", {}))
            total_footnotes += len(footnotes_section.get("items", []) if isinstance(footnotes_section, dict) else footnotes_section)

        # Calculate overall confidence
        overall_confidence = (
            self._confidence_sum / self._confidence_count
            if self._confidence_count > 0 else 0.0
        )

        # Generate validation checklist
        checklist = self._generate_validation_checklist(
            tables_json, total_visits, total_activities, total_sais, total_footnotes
        )

        # Build final JSON
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "reviewType": "EXTRACTION_VALIDATION",
            "protocolId": protocol_id,
            "protocolTitle": protocol_title or protocol_id,
            "generatedAt": datetime.utcnow().isoformat() + "Z",
            "extractionSummary": {
                "totalTables": len(tables_json),
                "totalVisits": total_visits,
                "totalActivities": total_activities,
                "totalScheduledInstances": total_sais,
                "totalFootnotes": total_footnotes,
                "confidence": round(overall_confidence, 2),
                "warnings": self._warnings,
            },
            "tables": tables_json,
            "validationChecklist": {
                "description": "Items for user to verify before approving extraction",
                "items": [item.to_dict() for item in checklist],
            },
            "userActions": {
                "allowedOperations": [
                    "APPROVE_ALL",
                    "EDIT_VISIT",
                    "EDIT_ACTIVITY",
                    "EDIT_CELL",
                    "ADD_VISIT",
                    "ADD_ACTIVITY",
                    "DELETE_VISIT",
                    "DELETE_ACTIVITY",
                    "EDIT_FOOTNOTE",
                    "LINK_FOOTNOTE",
                    "UNLINK_FOOTNOTE",
                ],
                "approvalRequired": True,
                "nextStep": "INTERPRETATION_WIZARD",
            },
        }

        logger.info(
            f"Extraction review generated: {len(tables_json)} tables, "
            f"{total_visits} visits, {total_activities} activities, "
            f"{total_sais} SAIs, confidence={overall_confidence:.2f}"
        )

        return result

    def _process_table(
        self,
        table: Dict[str, Any],
        index: int,
        pdf_image_base_url: str,
    ) -> Dict[str, Any]:
        """Process a single SOA table into review format."""
        table_id = table.get("id") or table.get("table_id") or f"SOA-{index + 1}"
        table_name = table.get("table_title") or table.get("name") or f"Table {index + 1}"
        category = table.get("table_type") or table.get("category") or "MAIN_SOA"

        # Get page range
        pages = table.get("pages", [])
        provenance = table.get("provenance", {})
        if not pages and provenance:
            pages = provenance.get("pages", [])

        # Check if this is a synthetic table (from raw USDM structure)
        is_synthetic = table.get("_is_synthetic", False)

        if is_synthetic:
            # Process pre-parsed visits/activities/SAIs from USDM structure
            visits, activities, matrix = self._process_usdm_structure(table, table_id)

            # Extract pages from provenance in visits/activities FIRST
            for v in table.get("visits", []):
                prov = v.get("provenance", {})
                if prov and prov.get("pageNumber"):
                    pages.append(prov.get("pageNumber"))
            for a in table.get("activities", []):
                prov = a.get("provenance", {})
                if prov and prov.get("pageNumber"):
                    pages.append(prov.get("pageNumber"))

            pages = list(set(pages))
            default_page = min(pages) if pages else None

            # Now process footnotes with page context
            footnotes = self._process_usdm_footnotes(
                table.get("footnotes", []), visits, activities, table_id, default_page
            )
        else:
            # Parse HTML to extract grid structure
            html_content = table.get("html_content") or table.get("html") or ""
            footnotes_text = table.get("footnotes") or ""

            # Get page number for provenance
            page_number = pages[0] if pages else provenance.get("pageNumber")

            visits, activities, matrix = self._parse_html_grid(html_content, table_id, page_number)
            footnotes = self._parse_footnotes(footnotes_text, visits, activities, table_id)

        page_start = min(pages) if pages else 0
        page_end = max(pages) if pages else 0

        # Generate PDF image URLs
        pdf_image_urls = [
            f"{pdf_image_base_url}/page{p}.png" for p in sorted(pages)
        ] if pages else []

        # Link footnotes to cells based on markers in cell content
        self._link_footnotes_to_cells(matrix, footnotes)

        # Update confidence
        confidence = provenance.get("ocr_confidence", 0.9)
        self._confidence_sum += confidence
        self._confidence_count += 1

        # Track multi-page tables
        if len(pages) > 1:
            self._warnings.append(
                f"Table on pages {page_start}-{page_end} spans multiple pages - verify continuity"
            )

        # Calculate footnote category distribution for this table
        footnote_category_counts = {"CONDITIONAL": 0, "SCHEDULING": 0, "OPERATIONAL": 0, "multiLabel": 0}
        for fn in footnotes:
            fn_dict = fn.to_dict()
            cats = fn_dict.get("category", "OPERATIONAL")
            cats = cats if isinstance(cats, list) else [cats]
            for cat in cats:
                if cat in footnote_category_counts:
                    footnote_category_counts[cat] += 1
            if len(cats) > 1:
                footnote_category_counts["multiLabel"] += 1

        return {
            "tableId": table_id,
            "tableName": table_name,
            "category": category.upper(),
            "pageRange": {"start": page_start, "end": page_end},
            "pdfImageUrls": pdf_image_urls,
            "visits": {
                "sectionDescription": VISITS_SECTION_DESCRIPTION.strip(),
                "items": [v.to_dict() for v in visits],
            },
            "activities": {
                "sectionDescription": ACTIVITIES_SECTION_DESCRIPTION.strip(),
                "items": [a.to_dict() for a in activities],
            },
            "matrix": {
                "sectionDescription": MATRIX_SECTION_DESCRIPTION.strip(),
                "legend": {
                    "X": "Required assessment",
                    "O": "Optional assessment",
                    "-": "Not scheduled",
                    "": "Empty cell (not applicable)",
                },
                "grid": [row.to_dict() for row in matrix],
            },
            "footnotes": {
                "sectionDescription": FOOTNOTES_SECTION_DESCRIPTION.strip(),
                "categoryDistribution": footnote_category_counts,
                "items": [f.to_dict() for f in footnotes],
            },
        }

    def _process_usdm_structure(
        self,
        table: Dict[str, Any],
        table_id: str,
    ) -> Tuple[List[ExtractedVisit], List[ExtractedActivity], List[MatrixRow]]:
        """Process visits/activities from USDM structure into review format."""
        visits: List[ExtractedVisit] = []
        activities: List[ExtractedActivity] = []
        matrix: List[MatrixRow] = []

        raw_visits = table.get("visits", [])
        raw_activities = table.get("activities", [])
        raw_sais = table.get("scheduledActivityInstances", [])

        # Build visit lookup
        visit_id_map = {}
        for idx, v in enumerate(raw_visits):
            visit_id = v.get("id", f"V-{idx + 1:03d}")
            visit_name = v.get("name") or v.get("originalName", f"Visit {idx + 1}")
            prov = v.get("provenance", {})

            visit = ExtractedVisit(
                id=visit_id,
                column_index=idx,
                display_name=visit_name,
                original_text=visit_name,
                timing=v.get("timing"),
                window=v.get("window"),
                footnote_refs=[],
                provenance={
                    "tableId": table_id,
                    "pageNumber": prov.get("pageNumber"),
                    "cellCoords": [0, idx + 1],
                },
            )
            visits.append(visit)
            visit_id_map[visit_id] = visit

        # Build activity lookup and SAI index
        activity_id_map = {}
        sai_by_activity_visit = {}  # {activity_id: {visit_id: SAI}}

        for sai in raw_sais:
            # Handle both activityRef/visitRef and activityId/visitId formats
            act_ref = sai.get("activityRef") or sai.get("activityId") or ""
            visit_ref = sai.get("visitRef") or sai.get("visitId") or sai.get("encounterId") or ""
            if act_ref not in sai_by_activity_visit:
                sai_by_activity_visit[act_ref] = {}
            sai_by_activity_visit[act_ref][visit_ref] = sai

        for idx, a in enumerate(raw_activities):
            activity_id = a.get("id", f"A-{idx + 1:03d}")
            activity_name = a.get("name", f"Activity {idx + 1}")
            prov = a.get("provenance", {})

            activity = ExtractedActivity(
                id=activity_id,
                row_index=idx,
                display_name=activity_name,
                original_text=activity_name,
                category=a.get("cdiscDomain"),
                footnote_refs=[],
                provenance={
                    "tableId": table_id,
                    "pageNumber": prov.get("pageNumber"),
                    "cellCoords": [idx + 1, 0],
                },
            )
            activities.append(activity)
            activity_id_map[activity_id] = activity

            # Build matrix row
            cells: List[CellValue] = []
            for col_idx, visit in enumerate(visits):
                sai = sai_by_activity_visit.get(activity_id, {}).get(visit.id)
                value = "X" if sai else ""
                # Get provenance from SAI if available
                sai_prov = sai.get("provenance", {}) if sai else {}
                cell_page = sai_prov.get("pageNumber") or prov.get("pageNumber")
                # Get footnote markers from SAI
                footnote_markers = sai.get("footnoteMarkers", []) if sai else []
                # Also check for 'm' field (compact format from matrix extraction)
                if not footnote_markers and sai:
                    footnote_markers = sai.get("m", [])
                cells.append(CellValue(
                    visit_id=visit.id,
                    value=value,
                    footnote_refs=footnote_markers,
                    raw_content=value,
                    provenance=CellProvenance(
                        table_id=table_id,
                        page_number=cell_page,
                        row_index=idx + 1,
                        col_index=col_idx + 1,
                    ),
                ))

            matrix.append(MatrixRow(
                activity_id=activity_id,
                activity_name=activity_name,
                cells=cells,
            ))

        return visits, activities, matrix

    def _process_usdm_footnotes(
        self,
        raw_footnotes: List[Dict[str, Any]],
        visits: List[ExtractedVisit],
        activities: List[ExtractedActivity],
        table_id: str,
        default_page: Optional[int] = None,
    ) -> List[ExtractedFootnote]:
        """Process footnotes from USDM structure."""
        footnotes: List[ExtractedFootnote] = []

        for idx, fn in enumerate(raw_footnotes):
            marker = fn.get("marker", str(idx + 1))
            text = fn.get("text", "")
            prov = fn.get("provenance", {})

            # Use provenance page or fall back to default page from table
            page_num = prov.get("pageNumber") or default_page

            # Extract category classification fields (passed through from LLM extraction)
            category = fn.get("category", "OPERATIONAL")
            subcategory = fn.get("subcategory")
            classification_reasoning = fn.get("classificationReasoning", "")
            edc_impact = fn.get("edcImpact")

            footnote = ExtractedFootnote(
                id=fn.get("id", f"FN-{idx + 1:03d}"),
                marker=marker,
                text=text,
                rule_type=fn.get("ruleType", "reference"),
                category=category,
                subcategory=subcategory,
                classification_reasoning=classification_reasoning,
                edc_impact=edc_impact,
                provenance={
                    "tableId": table_id,
                    "pageNumber": page_num,
                    "location": "table_footer",
                },
            )
            footnotes.append(footnote)

        return footnotes

    def _parse_html_grid(
        self,
        html_content: str,
        table_id: str,
        page_number: Optional[int] = None,
    ) -> Tuple[List[ExtractedVisit], List[ExtractedActivity], List[MatrixRow]]:
        """
        Parse HTML table to extract visits, activities, and matrix.

        Returns:
            Tuple of (visits, activities, matrix_rows)
        """
        visits: List[ExtractedVisit] = []
        activities: List[ExtractedActivity] = []
        matrix: List[MatrixRow] = []

        if not html_content:
            return visits, activities, matrix

        # Extract page numbers from <!-- Page X --> comments
        # For multi-page tables, we split by page markers and track each section
        import re

        # Find all page markers and their positions
        page_markers = list(re.finditer(r'<!--\s*Page\s+(\d+)\s*-->', html_content))

        # Build a list of (start_pos, end_pos, page_number) for each page section
        page_sections: List[Tuple[int, int, int]] = []
        for i, match in enumerate(page_markers):
            start_pos = match.end()
            end_pos = page_markers[i + 1].start() if i + 1 < len(page_markers) else len(html_content)
            page_sections.append((start_pos, end_pos, int(match.group(1))))

        def get_page_for_html_segment(segment_start: int) -> Optional[int]:
            """Get the page number for a given position in HTML content."""
            for start_pos, end_pos, pg in page_sections:
                if start_pos <= segment_start < end_pos:
                    return pg
            return page_number  # Default fallback

        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Find all tables and determine their page numbers
            all_tables = soup.find_all("table")
            if not all_tables:
                logger.warning(f"No table found in HTML for {table_id}")
                return visits, activities, matrix

            # For each table, find its approximate position in original HTML
            # and determine which page it's on
            table_pages: Dict[int, int] = {}  # table_index -> page_number
            for idx, tbl in enumerate(all_tables):
                # Get the table's string representation to find its position
                tbl_str = str(tbl)[:100]  # First 100 chars for matching
                tbl_pos = html_content.find(tbl_str)
                table_pages[idx] = get_page_for_html_segment(tbl_pos) if tbl_pos >= 0 else page_number

            # Use first table for now (can be extended for multi-table support)
            table = all_tables[0]
            current_table_page = table_pages.get(0, page_number)

            rows = table.find_all("tr")
            if not rows:
                return visits, activities, matrix

            # First row is typically the header with visits
            header_row = rows[0]
            header_cells = header_row.find_all(["td", "th"])

            # Extract visits from header (skip first cell which is usually "Activity")
            for col_idx, cell in enumerate(header_cells[1:], start=0):
                cell_text = cell.get_text(strip=True)
                if cell_text:
                    footnote_refs = self._extract_footnote_refs(cell_text)
                    clean_text = self._clean_footnote_markers(cell_text)

                    visit = ExtractedVisit(
                        id=f"V-{col_idx + 1:03d}",
                        column_index=col_idx,
                        display_name=clean_text,
                        original_text=cell_text,
                        footnote_refs=footnote_refs,
                        provenance={
                            "tableId": table_id,
                            "cellCoords": [0, col_idx + 1],
                        },
                    )
                    visits.append(visit)

            # Process remaining rows as activities
            for row_idx, row in enumerate(rows[1:], start=0):
                cells = row.find_all(["td", "th"])
                if not cells:
                    continue

                # First cell is activity name
                activity_cell = cells[0]
                activity_text = activity_cell.get_text(strip=True)

                if not activity_text:
                    continue

                footnote_refs = self._extract_footnote_refs(activity_text)
                clean_name = self._clean_footnote_markers(activity_text)

                activity = ExtractedActivity(
                    id=f"A-{row_idx + 1:03d}",
                    row_index=row_idx,
                    display_name=clean_name,
                    original_text=activity_text,
                    footnote_refs=footnote_refs,
                    provenance={
                        "tableId": table_id,
                        "cellCoords": [row_idx + 1, 0],
                    },
                )
                activities.append(activity)

                # Process matrix cells
                matrix_cells: List[CellValue] = []
                for col_idx, cell in enumerate(cells[1:], start=0):
                    cell_text = cell.get_text(strip=True)
                    value = self._normalize_cell_value(cell_text)
                    cell_footnotes = self._extract_footnote_refs(cell_text)

                    visit_id = visits[col_idx].id if col_idx < len(visits) else f"V-{col_idx + 1:03d}"

                    matrix_cells.append(CellValue(
                        visit_id=visit_id,
                        value=value,
                        footnote_refs=cell_footnotes,
                        raw_content=cell_text,
                        provenance=CellProvenance(
                            table_id=table_id,
                            page_number=current_table_page,
                            row_index=row_idx + 1,
                            col_index=col_idx + 1,
                        ),
                    ))

                matrix.append(MatrixRow(
                    activity_id=activity.id,
                    activity_name=clean_name,
                    cells=matrix_cells,
                ))

        except Exception as e:
            logger.error(f"Failed to parse HTML grid for {table_id}: {e}")

        return visits, activities, matrix

    def _extract_footnote_refs(self, text: str) -> List[str]:
        """Extract footnote markers from text."""
        # Match common footnote patterns: superscript letters/numbers, symbols
        patterns = [
            r'[⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᵍʳˢᵗᵘᵛʷˣʸᶻ]+',  # Unicode superscripts
            r'\*+',  # Asterisks
            r'[†‡§¶]+',  # Symbols
        ]

        refs = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            refs.extend(matches)

        # Also look for letter/number markers at end
        trailing = re.search(r'([a-z,]+|\d+)$', text.lower())
        if trailing and len(trailing.group()) <= 3:
            # Check if it looks like a footnote marker
            marker = trailing.group()
            if marker not in ['x', 'y', 'z', 'mg', 'ml', 'iv']:  # Exclude common suffixes
                refs.append(marker)

        return list(set(refs))

    def _clean_footnote_markers(self, text: str) -> str:
        """Remove footnote markers from text."""
        # Remove Unicode superscripts
        text = re.sub(r'[⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᵍʳˢᵗᵘᵛʷˣʸᶻ]+', '', text)
        # Remove trailing asterisks
        text = re.sub(r'\*+$', '', text)
        # Remove symbols
        text = re.sub(r'[†‡§¶]+', '', text)
        return text.strip()

    def _normalize_cell_value(self, text: str) -> str:
        """Normalize cell value to X, O, -, or empty."""
        text = text.strip().upper()

        # Remove footnote markers for value detection
        clean = re.sub(r'[⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᵍʳˢᵗᵘᵛʷˣʸᶻ*†‡§¶]+', '', text)
        clean = clean.strip()

        if 'X' in clean or '✓' in clean or '✔' in clean:
            return "X"
        elif 'O' in clean and len(clean) <= 2:
            return "O"
        elif clean == '-' or clean == '–':
            return "-"
        elif not clean:
            return ""
        else:
            # Has some other content - treat as X (scheduled)
            return "X"

    def _parse_footnotes(
        self,
        footnotes_text: str,
        visits: List[ExtractedVisit],
        activities: List[ExtractedActivity],
        table_id: str,
    ) -> List[ExtractedFootnote]:
        """Parse footnotes from text."""
        footnotes: List[ExtractedFootnote] = []

        if not footnotes_text:
            return footnotes

        # Split by common patterns
        lines = footnotes_text.split('\n')

        # Pattern to detect footnote starts
        footnote_pattern = re.compile(
            r'^([a-z]|[0-9]+|\*+|†|‡|§)\.\s*(.+)',
            re.IGNORECASE
        )

        current_marker = None
        current_text = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = footnote_pattern.match(line)
            if match:
                # Save previous footnote
                if current_marker:
                    footnotes.append(ExtractedFootnote(
                        id=f"FN-{len(footnotes) + 1:03d}",
                        marker=current_marker,
                        text=' '.join(current_text),
                        provenance={"tableId": table_id, "location": "table_footer"},
                    ))

                current_marker = match.group(1).lower()
                current_text = [match.group(2)]
            elif current_marker:
                # Continuation of current footnote
                current_text.append(line)
            else:
                # Abbreviation line or other text
                if '=' in line:
                    # Likely abbreviation definition, create as footnote
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        footnotes.append(ExtractedFootnote(
                            id=f"FN-{len(footnotes) + 1:03d}",
                            marker=parts[0].strip(),
                            text=parts[1].strip(),
                            provenance={"tableId": table_id, "location": "abbreviations"},
                        ))

        # Don't forget last footnote
        if current_marker:
            footnotes.append(ExtractedFootnote(
                id=f"FN-{len(footnotes) + 1:03d}",
                marker=current_marker,
                text=' '.join(current_text),
                provenance={"tableId": table_id, "location": "table_footer"},
            ))

        # Link footnotes to visits/activities based on marker matching
        self._link_footnotes_to_entities(footnotes, visits, activities)

        return footnotes

    def _link_footnotes_to_entities(
        self,
        footnotes: List[ExtractedFootnote],
        visits: List[ExtractedVisit],
        activities: List[ExtractedActivity],
    ) -> None:
        """Link footnotes to visits and activities based on markers."""
        footnote_by_marker = {fn.marker.lower(): fn for fn in footnotes}

        for visit in visits:
            for ref in visit.footnote_refs:
                marker = ref.lower().strip('*†‡§¶')
                if marker in footnote_by_marker:
                    if visit.id not in footnote_by_marker[marker].applies_to["visits"]:
                        footnote_by_marker[marker].applies_to["visits"].append(visit.id)

        for activity in activities:
            for ref in activity.footnote_refs:
                marker = ref.lower().strip('*†‡§¶')
                if marker in footnote_by_marker:
                    if activity.id not in footnote_by_marker[marker].applies_to["activities"]:
                        footnote_by_marker[marker].applies_to["activities"].append(activity.id)

    def _link_footnotes_to_cells(
        self,
        matrix: List[MatrixRow],
        footnotes: List[ExtractedFootnote],
    ) -> None:
        """Link footnotes to specific cells in the matrix."""
        footnote_by_marker = {fn.marker.lower(): fn for fn in footnotes}

        for row in matrix:
            for cell in row.cells:
                for ref in cell.footnote_refs:
                    marker = ref.lower().strip('*†‡§¶')
                    if marker in footnote_by_marker:
                        cell_ref = {"activityId": row.activity_id, "visitId": cell.visit_id}
                        if cell_ref not in footnote_by_marker[marker].applies_to["cells"]:
                            footnote_by_marker[marker].applies_to["cells"].append(cell_ref)

    def _count_scheduled_instances(self, matrix: Dict[str, Any]) -> int:
        """Count total scheduled instances (X marks) in matrix."""
        count = 0
        for row in matrix.get("grid", []):
            for cell in row.get("cells", []):
                if cell.get("value") == "X":
                    count += 1
        return count

    def _generate_validation_checklist(
        self,
        tables: List[Dict[str, Any]],
        total_visits: int,
        total_activities: int,
        total_sais: int,
        total_footnotes: int,
    ) -> List[ExtractionValidationItem]:
        """Generate validation checklist items."""
        items = []

        # Visit completeness
        visit_status = "PASS" if total_visits > 0 else "REVIEW"
        visit_confidence = 0.98 if total_visits > 5 else 0.85
        items.append(ExtractionValidationItem(
            id="CHK-001",
            category="COMPLETENESS",
            question="Are all visits/columns captured correctly?",
            auto_status=visit_status,
            confidence=visit_confidence,
            details=f"Found {total_visits} visits across {len(tables)} tables",
        ))

        # Activity completeness
        activity_status = "PASS" if total_activities > 5 else "REVIEW"
        activity_confidence = 0.95 if total_activities > 10 else 0.80
        items.append(ExtractionValidationItem(
            id="CHK-002",
            category="COMPLETENESS",
            question="Are all activities/rows captured correctly?",
            auto_status=activity_status,
            confidence=activity_confidence,
            details=f"Found {total_activities} activities",
        ))

        # Matrix accuracy
        matrix_status = "REVIEW" if total_sais > 0 else "FAIL"
        matrix_confidence = 0.89  # Always needs review
        items.append(ExtractionValidationItem(
            id="CHK-003",
            category="ACCURACY",
            question="Are X marks correctly placed in the matrix?",
            auto_status=matrix_status,
            confidence=matrix_confidence,
            details=f"{total_sais} scheduled instances found",
        ))

        # Footnote linkage
        footnote_status = "REVIEW" if total_footnotes > 0 else "PASS"
        footnote_confidence = 0.85 if total_footnotes > 0 else 1.0
        items.append(ExtractionValidationItem(
            id="CHK-004",
            category="FOOTNOTES",
            question="Are all footnotes linked to correct activities/visits?",
            auto_status=footnote_status,
            confidence=footnote_confidence,
            details=f"{total_footnotes} footnotes found",
        ))

        # Multi-page tables
        multi_page_count = sum(
            1 for t in tables
            if t.get("pageRange", {}).get("end", 0) > t.get("pageRange", {}).get("start", 0)
        )
        if multi_page_count > 0:
            items.append(ExtractionValidationItem(
                id="CHK-005",
                category="ACCURACY",
                question="Are multi-page tables merged correctly?",
                auto_status="REVIEW",
                confidence=0.75,
                details=f"{multi_page_count} tables span multiple pages",
            ))

        return items


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


def generate_extraction_review(
    soa_output: Dict[str, Any],
    protocol_id: str,
    protocol_title: str = "",
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Convenience function to generate extraction review JSON.

    Args:
        soa_output: Raw SOA extraction output
        protocol_id: Protocol identifier
        protocol_title: Protocol display title
        output_path: Optional path to save JSON file

    Returns:
        Extraction review JSON
    """
    generator = ExtractionReviewGenerator()
    review_json = generator.generate(soa_output, protocol_id, protocol_title)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(review_json, f, indent=2)
        logger.info(f"Extraction review saved to {output_path}")

    return review_json
