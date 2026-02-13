"""
SOA Extraction Pipeline - Full End-to-End Pipeline

Complete pipeline for extracting Schedule of Assessments from clinical trial protocol PDFs
and transforming them into USDM 4.0 compliant JSON.

Pipeline Phases:
    Phase 1: Detection - Find SOA pages in PDF (Gemini Vision)
    Phase 2: Extraction - PDF → HTML tables (LandingAI, 7x zoom)
    Phase 3: Interpretation - HTML → USDM structure (12-stage pipeline)
    Phase 4: Validation - Quality checks (5-dimensional scoring)
    Phase 5: Output - Save results (USDM JSON, quality report)

Usage:
    from soa_analyzer.soa_extraction_pipeline import SOAExtractionPipeline, run_soa_extraction

    # Option 1: Class-based
    pipeline = SOAExtractionPipeline()
    result = await pipeline.run("/path/to/protocol.pdf")

    # Option 2: Convenience function
    result = await run_soa_extraction("/path/to/protocol.pdf")

    # Access results
    print(f"Success: {result.success}")
    print(f"Quality: {result.quality_score.overall_score:.1%}")
    print(f"Output files: {result.output_files}")
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for direct script execution
# This allows running: python soa_analyzer/soa_extraction_pipeline.py ...
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import fitz  # PyMuPDF
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# Import pipeline components
from soa_analyzer.soa_page_detector import detect_soa_pages_v2, get_merged_table_pages
from soa_analyzer.soa_html_interpreter import SOAHTMLInterpreter
from soa_analyzer.soa_quality_checker import SOAQualityChecker, QualityScore, get_quality_checker
from soa_analyzer.soa_cache import SOACache, get_soa_cache

# Import 12-stage interpretation pipeline
from soa_analyzer.interpretation import (
    InterpretationPipeline,
    PipelineConfig as InterpretationConfig,
    PipelineResult as InterpretationResult,
)

# Import table merge analyzer for Phase 3.5
from soa_analyzer.table_merge_analyzer import (
    TableMergeAnalyzer,
    MergePlan,
    MergeGroup,
    MergeType,
    combine_table_usdm,
)

# Import review generators for Phase 1 & 2 UX
from soa_analyzer.output import (
    generate_extraction_review,
    generate_interpretation_review,
)

# Import OCR adapters
from soa_analyzer.adapters.ocr.landingai_adapter import LandingAIOCRAdapter
from soa_analyzer.adapters.ocr.gemini_table_adapter import GeminiTableAdapter

logger = logging.getLogger(__name__)


# =============================================================================
# HTML ROW COUNTING UTILITY
# =============================================================================


def count_html_table_rows(html: str) -> int:
    """
    Count the number of data rows in HTML table(s).

    Args:
        html: HTML string containing table(s)

    Returns:
        Number of <tr> elements (excluding header rows)
    """
    import re
    # Count all <tr> tags
    all_rows = len(re.findall(r'<tr[^>]*>', html, re.IGNORECASE))
    # Count header rows (rows containing <th> elements)
    header_rows = len(re.findall(r'<tr[^>]*>(?:[^<]*<th)', html, re.IGNORECASE))
    # Data rows = all rows - header rows
    return max(0, all_rows - header_rows)


# =============================================================================
# HTML SANITIZER - Fix Malformed LandingAI Output
# =============================================================================


def sanitize_landingai_html(html: str) -> str:
    """
    Fix malformed HTML from LandingAI where each cell is in its own row.

    LandingAI sometimes produces HTML like:
        <tr><th><td>Cell1</td></th></tr>
        <tr><th><td>Cell2</td></th></tr>

    Instead of proper:
        <tr><td>Cell1</td><td>Cell2</td></tr>

    This function detects and repairs such malformed structures.

    Args:
        html: Raw HTML from LandingAI

    Returns:
        Sanitized HTML with proper table row structure
    """
    from bs4 import BeautifulSoup

    if not html or not html.strip():
        return html

    soup = BeautifulSoup(html, 'html.parser')
    modified = False

    # Find all tables
    for table in soup.find_all('table'):
        rows = table.find_all('tr', recursive=False)
        if not rows:
            # Check inside thead/tbody
            rows = table.find_all('tr')

        if len(rows) < 3:
            continue

        # Detect malformed pattern: rows with single <th> containing <td> or nested structure
        malformed_rows = []
        for row in rows:
            # Check if row has pattern: <tr><th><td>content</td></th></tr>
            # or <tr><th><th>content</th></th></tr>
            ths = row.find_all('th', recursive=False)
            tds = row.find_all('td', recursive=False)

            # Malformed if: single <th> containing a <td>, or odd nesting
            if len(ths) == 1 and len(tds) == 0:
                inner_td = ths[0].find('td')
                inner_th = ths[0].find('th')
                inner_tr = ths[0].find('tr')
                if inner_td or inner_th or inner_tr:
                    malformed_rows.append(row)
            elif len(ths) == 1 and len(tds) == 1:
                # Pattern: <tr><th></th><td>content</td></tr> is ok, but
                # <tr><th><td>content</td></th></tr> is malformed
                if ths[0].find('td'):
                    malformed_rows.append(row)

        # If more than 50% of rows are malformed, attempt repair
        if len(malformed_rows) > len(rows) * 0.5:
            logger.warning(f"  Detected malformed table structure ({len(malformed_rows)}/{len(rows)} rows). Attempting repair...")
            repaired_html = _repair_malformed_table(table)
            if repaired_html:
                table.replace_with(BeautifulSoup(repaired_html, 'html.parser'))
                modified = True
                logger.info(f"  Table structure repaired successfully")

    return str(soup) if modified else html


def _repair_malformed_table(table) -> Optional[str]:
    """
    Repair a malformed table by extracting cell contents and rebuilding rows.

    Strategy:
    1. Extract all cell contents in order
    2. Determine column count from header structure or first proper row
    3. Group cells into proper rows

    Args:
        table: BeautifulSoup table element

    Returns:
        Repaired HTML string or None if repair fails
    """
    from bs4 import BeautifulSoup, NavigableString

    try:
        # Extract all cell contents in document order
        cells = []
        rows = table.find_all('tr')

        for row in rows:
            # Extract content from various patterns
            # Pattern 1: <tr><th><td>content</td></th></tr>
            # Pattern 2: <tr><th>content</th></tr>
            # Pattern 3: <tr><td>content</td></tr>

            for th in row.find_all('th', recursive=False):
                inner_td = th.find('td')
                inner_th = th.find('th')
                if inner_td:
                    cells.append(('td', _get_cell_content(inner_td)))
                elif inner_th:
                    cells.append(('th', _get_cell_content(inner_th)))
                else:
                    # Check if this th just contains text or has meaningful content
                    content = _get_cell_content(th)
                    if content.strip():
                        cells.append(('th', content))

            for td in row.find_all('td', recursive=False):
                cells.append(('td', _get_cell_content(td)))

        if not cells:
            return None

        # Determine column count by looking for header-like patterns
        # Common SOA tables have 12-16 columns (visits)
        # Look for runs of header cells to determine column count
        column_count = _detect_column_count(cells)

        if column_count < 3:
            logger.warning(f"  Could not determine column count (detected: {column_count})")
            return None

        logger.info(f"  Detected {column_count} columns, {len(cells)} total cells")

        # Build repaired table
        repaired_rows = []
        current_row = []
        in_header = True

        for i, (cell_type, content) in enumerate(cells):
            current_row.append((cell_type, content))

            # Check if we've completed a row
            if len(current_row) >= column_count:
                # Determine if this is a header row
                th_count = sum(1 for ct, _ in current_row if ct == 'th')
                is_header_row = th_count > len(current_row) * 0.5

                repaired_rows.append((is_header_row, current_row))
                current_row = []

                if not is_header_row:
                    in_header = False

        # Handle remaining cells (incomplete last row)
        if current_row:
            # Pad with empty cells
            while len(current_row) < column_count:
                current_row.append(('td', ''))
            repaired_rows.append((False, current_row))

        # Generate HTML
        html_parts = ['<table>']
        in_thead = False
        in_tbody = False

        for is_header, row_cells in repaired_rows:
            if is_header and not in_thead:
                html_parts.append('<thead>')
                in_thead = True
            elif not is_header and in_thead:
                html_parts.append('</thead>')
                in_thead = False

            if not is_header and not in_tbody:
                html_parts.append('<tbody>')
                in_tbody = True

            html_parts.append('<tr>')
            for cell_type, content in row_cells:
                tag = 'th' if is_header else 'td'
                html_parts.append(f'<{tag}>{content}</{tag}>')
            html_parts.append('</tr>')

        if in_tbody:
            html_parts.append('</tbody>')
        if in_thead:
            html_parts.append('</thead>')
        html_parts.append('</table>')

        return '\n'.join(html_parts)

    except Exception as e:
        logger.error(f"  Table repair failed: {e}")
        return None


def _get_cell_content(element) -> str:
    """Extract the content of a cell element, preserving inner HTML."""
    from bs4 import NavigableString

    if element is None:
        return ''

    # Get inner HTML (excluding the element's own tags)
    contents = []
    for child in element.children:
        if isinstance(child, NavigableString):
            contents.append(str(child))
        else:
            contents.append(str(child))

    return ''.join(contents).strip()


def _detect_column_count(cells: list) -> int:
    """
    Detect the column count from a list of cells.

    Strategy:
    1. Look for repeating patterns of header cells
    2. Common SOA tables have 12-16 columns
    3. Find activity names (long text) to detect row boundaries
    """
    if not cells:
        return 0

    # Known SOA column headers
    soa_headers = {
        'visit', 'screening', 'cycle', 'day', 'baseline', 'treatment',
        'follow-up', 'safety', 'part 1', 'part 2', 'activity', 'window'
    }

    # Find cells that look like headers
    header_indices = []
    for i, (cell_type, content) in enumerate(cells):
        content_lower = content.lower().strip()
        if cell_type == 'th' or any(h in content_lower for h in soa_headers):
            header_indices.append(i)

    # Look for the first "Activity" or similar cell that starts data rows
    activity_markers = ['activity', 'informed consent', 'physical exam', 'vital signs', 'medical history']
    first_activity_idx = None
    for i, (_, content) in enumerate(cells):
        content_lower = content.lower().strip()
        if any(m in content_lower for m in activity_markers):
            first_activity_idx = i
            break

    # If we found an activity marker, assume columns = index where it appears
    # (since first column is activity name)
    if first_activity_idx and first_activity_idx > 5:
        # The cells before the first activity are likely header cells
        # Count unique header-like patterns
        potential_col_count = first_activity_idx

        # Validate: check if subsequent "rows" have similar length
        # by looking for other activity markers
        activity_positions = []
        for i, (_, content) in enumerate(cells):
            content_lower = content.lower().strip()
            if any(m in content_lower for m in activity_markers):
                activity_positions.append(i)

        if len(activity_positions) >= 2:
            gaps = [activity_positions[i+1] - activity_positions[i] for i in range(len(activity_positions)-1)]
            # Most common gap is likely the column count
            from collections import Counter
            gap_counts = Counter(gaps)
            most_common_gap = gap_counts.most_common(1)[0][0] if gap_counts else potential_col_count
            return most_common_gap

        return potential_col_count

    # Fallback: assume standard SOA with ~14 columns
    return 14


# =============================================================================
# PROVENANCE PROPAGATION
# =============================================================================


def propagate_provenance(data: Any, parent_provenance: Optional[Dict[str, Any]] = None) -> None:
    """
    Propagate provenance from parent objects to nested objects with value fields.

    This ensures that nested objects like `timing` and `window` have provenance
    information inherited from their parent (e.g., visit/encounter), which is
    required for quality scoring.

    Args:
        data: The data structure to process (dict, list, or primitive)
        parent_provenance: Provenance from the parent object to propagate

    Example:
        Before: {"timing": {"value": -14}, "provenance": {"pageNumber": 30}}
        After:  {"timing": {"value": -14, "provenance": {"pageNumber": 30}}, "provenance": {"pageNumber": 30}}
    """
    if isinstance(data, dict):
        # Get provenance from current level or inherit from parent
        current_provenance = data.get("provenance", parent_provenance)

        # Nested objects that need provenance propagation
        nested_keys = ["timing", "window", "recurrence", "structuredRule"]

        for key in nested_keys:
            if key in data and isinstance(data[key], dict):
                nested_obj = data[key]
                # Check if nested object has value-like fields that need provenance
                value_fields = ["value", "name", "description", "label", "earlyBound", "lateBound", "pattern"]
                has_value_field = any(f in nested_obj for f in value_fields)

                # Add provenance if missing and parent has provenance
                if has_value_field and "provenance" not in nested_obj and current_provenance:
                    nested_obj["provenance"] = current_provenance.copy() if isinstance(current_provenance, dict) else current_provenance

        # Recurse into all values
        for value in data.values():
            propagate_provenance(value, current_provenance)

    elif isinstance(data, list):
        for item in data:
            propagate_provenance(item, parent_provenance)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class PerTableResult:
    """Result for a single SOA table."""
    table_id: str
    category: str
    success: bool
    usdm: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tableId": self.table_id,
            "category": self.category,
            "success": self.success,
            "error": self.error,
            "counts": self.counts,
        }


@dataclass
class PhaseResult:
    """Result from a pipeline phase."""
    phase: str
    success: bool
    data: Any = None
    duration: float = 0.0
    from_cache: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "success": self.success,
            "duration_seconds": round(self.duration, 2),
            "from_cache": self.from_cache,
            "error": self.error,
        }


@dataclass
class ExtractionResult:
    """Result from the full extraction pipeline."""
    success: bool
    protocol_id: str
    phases: List[PhaseResult] = field(default_factory=list)

    # Core outputs
    usdm_data: Optional[Dict[str, Any]] = None
    interpretation_result: Optional[InterpretationResult] = None
    quality_score: Optional[QualityScore] = None
    raw_soa_extraction: Optional[Dict[str, Any]] = None  # Raw SOA from HTML interpreter

    # Per-table results (for skip_interpretation mode)
    per_table_results: List[PerTableResult] = field(default_factory=list)

    # Merge group results (for 12-stage interpretation)
    merge_group_results: List[Dict[str, Any]] = field(default_factory=list)

    # Review JSONs for UI
    extraction_review: Optional[Dict[str, Any]] = None  # Phase 1 extraction review
    interpretation_review: Optional[Dict[str, Any]] = None  # Phase 2 interpretation wizard

    # Files
    output_files: List[str] = field(default_factory=list)
    output_dir: Optional[str] = None

    # Metrics
    total_duration: float = 0.0
    errors: List[str] = field(default_factory=list)

    # Counts
    visits_count: int = 0
    activities_count: int = 0
    instances_count: int = 0
    footnotes_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "protocol_id": self.protocol_id,
            "phases": [p.to_dict() for p in self.phases],
            "quality": self.quality_score.to_dict() if self.quality_score else None,
            "counts": {
                "visits": self.visits_count,
                "activities": self.activities_count,
                "instances": self.instances_count,
                "footnotes": self.footnotes_count,
            },
            "output_dir": self.output_dir,
            "output_files": self.output_files,
            "total_duration_seconds": round(self.total_duration, 2),
            "errors": self.errors,
        }

    def get_summary(self) -> str:
        """Get summary string."""
        status = "SUCCESS" if self.success else "FAILED"
        quality = f"{self.quality_score.overall_score:.1%}" if self.quality_score else "N/A"
        return (
            f"SOA Extraction: {status} - {self.total_duration:.2f}s - "
            f"Quality: {quality} - "
            f"{self.visits_count} visits, {self.activities_count} activities, "
            f"{self.instances_count} instances, {self.footnotes_count} footnotes"
        )


# =============================================================================
# MAIN PIPELINE CLASS
# =============================================================================


class SOAExtractionPipeline:
    """
    SOA Extraction Pipeline - Full End-to-End.

    Phases:
        1. Detection - Find SOA pages in PDF
        2. Extraction - PDF → HTML tables (LandingAI)
        3. Interpretation - HTML → USDM (12-stage pipeline)
        4. Validation - Quality checks
        5. Output - Save results
    """

    # 7x zoom for LandingAI accuracy
    ZOOM_FACTOR = 7

    # Minimum expected rows per page - if fewer, trigger Gemini fallback
    MIN_EXPECTED_ROWS_PER_PAGE = 5

    def __init__(self, use_cache: bool = True, use_gemini_fallback: bool = True):
        """
        Initialize the extraction pipeline.

        Args:
            use_cache: Whether to use caching for detection and extraction
            use_gemini_fallback: Whether to use Gemini as fallback when LandingAI extraction is incomplete
        """
        self.use_cache = use_cache
        self.use_gemini_fallback = use_gemini_fallback
        self.cache = get_soa_cache() if use_cache else None
        self.quality_checker = get_quality_checker()

        # Initialize components
        self.ocr = LandingAIOCRAdapter()
        self.gemini_ocr = None  # Lazy initialization
        self.html_interpreter = SOAHTMLInterpreter()
        self.interpretation_pipeline = InterpretationPipeline()

        logger.info(f"SOAExtractionPipeline initialized (cache: {use_cache}, gemini_fallback: {use_gemini_fallback})")

    def _get_gemini_adapter(self) -> GeminiTableAdapter:
        """Lazy initialization of Gemini adapter."""
        if self.gemini_ocr is None:
            self.gemini_ocr = GeminiTableAdapter()
            logger.info("GeminiTableAdapter initialized for fallback extraction")
        return self.gemini_ocr

    async def run(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        protocol_id: Optional[str] = None,
        protocol_name: Optional[str] = None,
        run_interpretation: bool = True,
        skip_interpretation: bool = False,
        extraction_outputs: Optional[Dict[str, Dict]] = None,
        gemini_file_uri: Optional[str] = None,
        detected_pages: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """
        Run the full SOA extraction pipeline.

        Args:
            pdf_path: Path to protocol PDF
            output_dir: Output directory (default: adjacent to PDF)
            protocol_id: Protocol identifier (default: PDF filename stem)
            protocol_name: Protocol display name (default: protocol_id)
            run_interpretation: Whether to run 12-stage interpretation pipeline
            skip_interpretation: If True, skip 12-stage pipeline and return raw per-table USDM
            extraction_outputs: Module extraction results for Stage 9 protocol mining
            gemini_file_uri: Optional Gemini Files API URI for PDF access (enables LLM to search PDF)
            detected_pages: Optional pre-detected pages (skips Phase 1 if provided)

        Returns:
            ExtractionResult with all outputs
        """
        start_time = time.time()

        # Setup
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            return ExtractionResult(
                success=False,
                protocol_id=protocol_id or "UNKNOWN",
                errors=[f"PDF not found: {pdf_path}"],
            )

        protocol_id = protocol_id or pdf_file.stem
        protocol_name = protocol_name or protocol_id

        # Store pdf_path for auto-discovery in _phase_interpretation
        self._current_pdf_path = str(pdf_file)

        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if output_dir:
            output_path = Path(output_dir) / timestamp
        else:
            output_path = pdf_file.parent / "soa_output" / timestamp
        output_path.mkdir(parents=True, exist_ok=True)

        result = ExtractionResult(
            success=True,
            protocol_id=protocol_id,
            output_dir=str(output_path),
        )

        logger.info("=" * 70)
        logger.info(f"SOA EXTRACTION PIPELINE: {protocol_id}")
        logger.info("=" * 70)

        try:
            # Phase 1: Detection (skip if detected_pages provided)
            if detected_pages:
                logger.info("[Phase 1] DETECTION - Using pre-detected pages")
                soa_tables = detected_pages
                detection_result = PhaseResult(
                    phase="detection",
                    success=True,
                    data=detected_pages,
                    duration=0.0,
                    from_cache=True,
                )
            else:
                detection_result = await self._phase_detection(pdf_path, protocol_id)
                if not detection_result.success:
                    raise RuntimeError(f"Detection failed: {detection_result.error}")
                soa_tables = detection_result.data
            result.phases.append(detection_result)

            # Capture Gemini file URI from detection for Stage 2 activity expansion
            detected_gemini_uri = soa_tables.get("geminiFileUri")
            if detected_gemini_uri:
                logger.info(f"Gemini file URI available for Stage 2: {detected_gemini_uri[:50]}...")

            # Phase 2: Extraction (LandingAI)
            extraction_result = await self._phase_extraction(pdf_path, soa_tables, protocol_id)
            result.phases.append(extraction_result)
            if not extraction_result.success:
                raise RuntimeError(f"Extraction failed: {extraction_result.error}")

            html_tables = extraction_result.data

            # Phase 3: Interpretation (12-stage pipeline or raw per-table)
            effective_gemini_uri = gemini_file_uri or detected_gemini_uri
            effective_skip_interpretation = skip_interpretation or not run_interpretation

            interpretation_result = await self._phase_interpretation(
                html_tables,
                protocol_id,
                protocol_name,
                run_interpretation=not effective_skip_interpretation,
                extraction_outputs=extraction_outputs,
                output_path=output_path,
                gemini_file_uri=effective_gemini_uri,
                skip_interpretation=effective_skip_interpretation,
            )
            result.phases.append(interpretation_result)
            if not interpretation_result.success:
                raise RuntimeError(f"Interpretation failed: {interpretation_result.error}")

            # Store interpretation result
            result.usdm_data = interpretation_result.data.get("usdm")
            result.interpretation_result = interpretation_result.data.get("pipeline_result")
            result.raw_soa_extraction = interpretation_result.data.get("raw_interpretation")
            result.per_table_results = interpretation_result.data.get("per_table_results", [])

            # Update counts
            if result.usdm_data:
                result.visits_count = len(result.usdm_data.get("visits", result.usdm_data.get("encounters", [])))
                result.activities_count = len(result.usdm_data.get("activities", []))
                result.instances_count = len(result.usdm_data.get("scheduledActivityInstances", []))
                result.footnotes_count = len(result.usdm_data.get("footnotes", []))

            # Skip validation and output phases if skip_interpretation mode
            if effective_skip_interpretation:
                logger.info("[Phase 4] VALIDATION - Skipped (skip_interpretation mode)")
                logger.info("[Phase 5] OUTPUT - Skipped (skip_interpretation mode)")
            else:
                # Phase 4: Validation
                validation_result = await self._phase_validation(result.usdm_data, protocol_id)
                result.phases.append(validation_result)
                result.quality_score = validation_result.data

                # Phase 5: Output (including review JSONs)
                output_result = await self._phase_output(
                    result.usdm_data,
                    result.interpretation_result,
                    result.quality_score,
                    result.raw_soa_extraction,
                    output_path,
                    protocol_id,
                    protocol_name,
                )
                result.phases.append(output_result)
                result.output_files = output_result.data.get("files", []) if isinstance(output_result.data, dict) else (output_result.data or [])
                result.extraction_review = output_result.data.get("extraction_review") if isinstance(output_result.data, dict) else None
                result.interpretation_review = output_result.data.get("interpretation_review") if isinstance(output_result.data, dict) else None

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            logger.error(f"Pipeline failed: {e}")
            import traceback
            traceback.print_exc()

        result.total_duration = time.time() - start_time

        # Log summary
        self._log_summary(result)

        return result

    # =========================================================================
    # PHASE 1: DETECTION
    # =========================================================================

    async def _phase_detection(
        self,
        pdf_path: str,
        protocol_id: str,
    ) -> PhaseResult:
        """Phase 1: Detect SOA pages in PDF."""
        start = time.time()
        logger.info("\n[Phase 1] DETECTION - Finding SOA pages...")

        try:
            # Check cache
            if self.cache:
                cached = self.cache.get(pdf_path, "detection_v2")
                if cached:
                    logger.info("  Cache HIT")
                    return PhaseResult(
                        phase="detection",
                        success=True,
                        data=cached["data"],
                        duration=time.time() - start,
                        from_cache=True,
                    )

            # Run detection
            result = detect_soa_pages_v2(pdf_path)
            merged = get_merged_table_pages(result)

            output = {
                "totalSOAs": result.get("totalSOAs", 0),
                "soaTables": result.get("soaTables", []),
                "mergedTables": merged,
                "geminiFileUri": result.get("geminiFileUri"),  # <-- ADD THIS LINE

            }

            # Cache result
            if self.cache:
                self.cache.set(pdf_path, "detection_v2", output)

            logger.info(f"  Found {output['totalSOAs']} SOA table(s)")
            for table in output["mergedTables"]:
                logger.info(f"    {table['id']}: pages {table['pageStart']}-{table['pageEnd']} [{table['tableCategory']}]")

            return PhaseResult(
                phase="detection",
                success=True,
                data=output,
                duration=time.time() - start,
            )

        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return PhaseResult(
                phase="detection",
                success=False,
                error=str(e),
                duration=time.time() - start,
            )

    # =========================================================================
    # PHASE 2: EXTRACTION
    # =========================================================================

    async def _phase_extraction(
        self,
        pdf_path: str,
        detection_result: Dict[str, Any],
        protocol_id: str,
    ) -> PhaseResult:
        """Phase 2: Extract HTML tables using LandingAI."""
        start = time.time()
        logger.info("\n[Phase 2] EXTRACTION - PDF → HTML tables (LandingAI, 7x zoom)...")

        try:
            # Check cache (use different key for hybrid vs non-hybrid)
            cache_key = "extraction_html_v3_hybrid" if self.use_gemini_fallback else "extraction_html_v2"
            if self.cache:
                cached = self.cache.get(pdf_path, cache_key)
                if cached:
                    logger.info("  Cache HIT")
                    return PhaseResult(
                        phase="extraction",
                        success=True,
                        data=cached["data"],
                        duration=time.time() - start,
                        from_cache=True,
                    )

            pdf_doc = fitz.open(pdf_path)
            extracted_tables = []

            for table_info in detection_result.get("mergedTables", []):
                table_id = table_info.get("id", "SOA-1")
                page_start = table_info.get("pageStart", 1)
                page_end = table_info.get("pageEnd", page_start)
                category = table_info.get("tableCategory", "MAIN_SOA")

                logger.info(f"  Extracting {table_id}: pages {page_start}-{page_end}")

                html_parts = []

                for page_num in range(page_start, page_end + 1):
                    page = pdf_doc[page_num - 1]
                    pix = page.get_pixmap(matrix=fitz.Matrix(self.ZOOM_FACTOR, self.ZOOM_FACTOR))
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    logger.info(f"    Page {page_num}: {pix.width}x{pix.height}")

                    # Step 1: Try LandingAI extraction
                    ocr_result = self.ocr.extract_table(img)
                    html = ocr_result.get("html", "")
                    row_count = count_html_table_rows(html) if html else 0

                    logger.info(f"    Page {page_num}: LandingAI extracted {len(html)} chars, {row_count} data rows")

                    if html:
                        # Step 3: Sanitize malformed HTML structure
                        original_html = html
                        html = sanitize_landingai_html(html)
                        if html != original_html:
                            logger.info(f"    Page {page_num}: HTML structure sanitized")
                            row_count = count_html_table_rows(html)

                        html_with_marker = f"<!-- Page {page_num} -->\n{html}"
                        html_parts.append(html_with_marker)
                        logger.info(f"    Page {page_num}: Final extraction: {len(html)} chars, {row_count} data rows")
                    else:
                        logger.warning(f"    Page {page_num}: no HTML extracted from LandingAI")

                combined_html = "\n\n".join(html_parts)

                extracted_tables.append({
                    "id": table_id,
                    "html": combined_html,
                    "pages": list(range(page_start, page_end + 1)),
                    "pageStart": page_start,
                    "pageEnd": page_end,
                    "category": category,
                })

            pdf_doc.close()

            # Cache result
            if self.cache:
                self.cache.set(pdf_path, cache_key, extracted_tables)

            logger.info(f"  Extracted {len(extracted_tables)} table(s)")

            return PhaseResult(
                phase="extraction",
                success=True,
                data=extracted_tables,
                duration=time.time() - start,
            )

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return PhaseResult(
                phase="extraction",
                success=False,
                error=str(e),
                duration=time.time() - start,
            )

    # =========================================================================
    # PHASE 3: INTERPRETATION (12-Stage Pipeline)
    # =========================================================================

    async def _phase_interpretation(
        self,
        html_tables: List[Dict[str, Any]],
        protocol_id: str,
        protocol_name: str,
        run_interpretation: bool,
        extraction_outputs: Optional[Dict[str, Dict]],
        output_path: Path,
        gemini_file_uri: Optional[str] = None,
        skip_interpretation: bool = False,
    ) -> PhaseResult:
        """Phase 3: Interpret HTML tables using 12-stage pipeline or raw per-table extraction."""
        start = time.time()

        if skip_interpretation:
            logger.info("\n[Phase 3] INTERPRETATION - HTML → Raw USDM (per-table, no 12-stage)...")
        else:
            logger.info("\n[Phase 3] INTERPRETATION - HTML → USDM (12-stage pipeline)...")

        try:
            per_table_results = []

            # When skip_interpretation=True, extract each table separately
            if skip_interpretation:
                logger.info(f"  Processing {len(html_tables)} table(s) individually...")

                for table_info in html_tables:
                    table_id = table_info.get("id", "SOA-1")
                    category = table_info.get("category", "MAIN_SOA")

                    try:
                        logger.info(f"    Interpreting {table_id} ({category})...")

                        # Interpret single table
                        single_table_list = [table_info]
                        table_interpretation = await self.html_interpreter.interpret(
                            single_table_list, protocol_id
                        )

                        # Build USDM for this table
                        table_usdm = self._build_base_usdm(table_interpretation, protocol_id)

                        # Add table metadata
                        table_usdm["_tableMetadata"] = {
                            "tableId": table_id,
                            "category": category,
                            "pageStart": table_info.get("pageStart", 0),
                            "pageEnd": table_info.get("pageEnd", 0),
                        }

                        counts = {
                            "visits": len(table_usdm.get("visits", [])),
                            "activities": len(table_usdm.get("activities", [])),
                            "sais": len(table_usdm.get("scheduledActivityInstances", [])),
                            "footnotes": len(table_usdm.get("footnotes", [])),
                        }

                        logger.info(f"      {table_id}: {counts['visits']} visits, {counts['activities']} activities, {counts['sais']} SAIs")

                        per_table_results.append(PerTableResult(
                            table_id=table_id,
                            category=category,
                            success=True,
                            usdm=table_usdm,
                            counts=counts,
                        ))

                    except Exception as e:
                        logger.error(f"    Failed to interpret {table_id}: {e}")
                        per_table_results.append(PerTableResult(
                            table_id=table_id,
                            category=category,
                            success=False,
                            error=str(e),
                        ))

                # Build merged USDM from all tables (for backward compatibility)
                merged_usdm = self._merge_per_table_usdm(per_table_results, protocol_id)

                return PhaseResult(
                    phase="interpretation",
                    success=True,
                    data={
                        "usdm": merged_usdm,
                        "raw_interpretation": merged_usdm,
                        "pipeline_result": None,
                        "per_table_results": per_table_results,
                    },
                    duration=time.time() - start,
                )

            # Standard flow: merged interpretation with optional 12-stage pipeline
            logger.info("  Step 3a: Claude HTML interpretation...")
            raw_interpretation = await self.html_interpreter.interpret(html_tables, protocol_id)

            logger.info(f"    Visits: {len(raw_interpretation.get('visits', []))}")
            logger.info(f"    Activities: {len(raw_interpretation.get('activities', []))}")
            logger.info(f"    Instances: {len(raw_interpretation.get('scheduledActivityInstances', []))}")
            logger.info(f"    Footnotes: {len(raw_interpretation.get('footnotes', []))}")

            # Build base USDM from raw interpretation
            usdm = self._build_base_usdm(raw_interpretation, protocol_id)

            # Save foundational extraction for Phase 1 human review
            foundational_dir = output_path / "interpretation_stages"
            foundational_dir.mkdir(parents=True, exist_ok=True)
            foundational_file = foundational_dir / "00_foundational_extraction.json"

            foundational_data = {
                "stage": 0,
                "stageName": "Foundational Extraction",
                "description": "Raw USDM from HTML interpretation, before 12-stage enrichment",
                "success": True,
                "protocolId": protocol_id,
                "metrics": {
                    "visitsCount": len(usdm.get("visits", [])),
                    "activitiesCount": len(usdm.get("activities", [])),
                    "instancesCount": len(usdm.get("scheduledActivityInstances", [])),
                    "footnotesCount": len(usdm.get("footnotes", [])),
                },
                "usdm": usdm,
            }

            with open(foundational_file, "w") as f:
                json.dump(foundational_data, f, indent=2, default=str)
            logger.info(f"    Saved foundational extraction: {foundational_file}")

            # Step 3b: Run 12-stage interpretation pipeline
            pipeline_result = None
            if run_interpretation:
                logger.info("  Step 3b: 12-stage interpretation pipeline...")

                # Auto-discover extraction_outputs if not provided
                effective_extraction_outputs = extraction_outputs
                if effective_extraction_outputs is None:
                    logger.info("    No extraction_outputs provided, attempting auto-discovery...")
                    pdf_path = getattr(self, '_current_pdf_path', None)
                    if pdf_path:
                        effective_extraction_outputs = auto_discover_extraction_outputs(Path(pdf_path))
                        if effective_extraction_outputs:
                            logger.info(f"    Auto-discovered {len(effective_extraction_outputs)} extraction modules")
                        else:
                            logger.info("    No extraction outputs found - Stage 9 Protocol Mining will be limited")
                    else:
                        logger.debug("    Cannot auto-discover: no pdf_path available")

                interp_config = InterpretationConfig(
                    protocol_id=protocol_id,
                    protocol_name=protocol_name,
                    extraction_outputs=effective_extraction_outputs,
                    gemini_file_uri=gemini_file_uri,
                    skip_stage_11=True,
                    continue_on_non_critical_failure=True,
                    save_intermediate_results=True,
                    output_dir=output_path / "interpretation_stages",
                )

                pipeline_result = await self.interpretation_pipeline.run(usdm, interp_config)

                logger.info(f"    Pipeline: {pipeline_result.get_summary()}")

                if pipeline_result.final_usdm:
                    usdm = pipeline_result.final_usdm
                    propagate_provenance(usdm)

            return PhaseResult(
                phase="interpretation",
                success=True,
                data={
                    "usdm": usdm,
                    "raw_interpretation": raw_interpretation,
                    "pipeline_result": pipeline_result,
                    "per_table_results": per_table_results,
                },
                duration=time.time() - start,
            )

        except Exception as e:
            logger.error(f"Interpretation failed: {e}")
            import traceback
            traceback.print_exc()
            return PhaseResult(
                phase="interpretation",
                success=False,
                error=str(e),
                duration=time.time() - start,
            )

    # =========================================================================
    # PHASE 3.5: MERGE ANALYSIS
    # =========================================================================

    async def _phase_merge_analysis(
        self,
        per_table_results: List[PerTableResult],
        protocol_id: str,
        output_path: Path,
    ) -> PhaseResult:
        """
        Phase 3.5: Analyze tables and determine merge groups.

        This phase runs after per-table extraction but before interpretation.
        It analyzes which tables should be merged based on an 8-level decision tree.

        Args:
            per_table_results: List of PerTableResult from Phase 3
            protocol_id: Protocol identifier
            output_path: Output directory for saving merge plan

        Returns:
            PhaseResult with MergePlan data
        """
        start = time.time()
        logger.info("\n[Phase 3.5] MERGE ANALYSIS - Analyzing table relationships...")

        try:
            # Run merge analysis
            analyzer = TableMergeAnalyzer()
            merge_plan = await analyzer.analyze_merge_candidates(per_table_results, protocol_id)

            logger.info(f"  Total tables: {merge_plan.total_tables}")
            logger.info(f"  Suggested merge groups: {len(merge_plan.merge_groups)}")
            logger.info(f"  Standalone tables: {len(merge_plan.standalone_tables)}")

            # Log each merge group
            for mg in merge_plan.merge_groups:
                if len(mg.table_ids) > 1:
                    logger.info(f"    {mg.id}: {mg.table_ids} - {mg.merge_type.value} (conf={mg.confidence:.2f})")
                else:
                    logger.info(f"    {mg.id}: {mg.table_ids} - standalone")

            # Save merge plan to file
            merge_plan_file = output_path / f"{protocol_id}_merge_plan.json"
            with open(merge_plan_file, "w") as f:
                json.dump(merge_plan.to_dict(), f, indent=2, default=str)
            logger.info(f"  Saved merge plan: {merge_plan_file.name}")

            return PhaseResult(
                phase="merge_analysis",
                success=True,
                data=merge_plan,
                duration=time.time() - start,
            )

        except Exception as e:
            logger.error(f"Merge analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return PhaseResult(
                phase="merge_analysis",
                success=False,
                error=str(e),
                duration=time.time() - start,
            )

    async def run_with_merge_analysis(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        protocol_id: Optional[str] = None,
        protocol_name: Optional[str] = None,
        extraction_outputs: Optional[Dict[str, Dict]] = None,
        gemini_file_uri: Optional[str] = None,
        detected_pages: Optional[Dict[str, Any]] = None,
        auto_confirm_merges: bool = False,
    ) -> ExtractionResult:
        """
        Run SOA extraction with merge analysis (Phase 3.5).

        This is the new flow that includes merge analysis:
        Phase 1 -> Phase 2 -> Phase 3 (per-table) -> Phase 3.5 (merge analysis)
                -> [Human Confirmation] -> 12 stages (per group) -> Output

        Args:
            pdf_path: Path to protocol PDF
            output_dir: Output directory
            protocol_id: Protocol identifier
            protocol_name: Protocol display name
            extraction_outputs: Module extraction results for Stage 9
            gemini_file_uri: Gemini Files API URI for PDF access
            detected_pages: Pre-detected pages (skips Phase 1)
            auto_confirm_merges: If True, auto-confirm all suggested merges (for testing)

        Returns:
            ExtractionResult with merge plan and optionally final USDM
        """
        start_time = time.time()

        # Setup
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            return ExtractionResult(
                success=False,
                protocol_id=protocol_id or "UNKNOWN",
                errors=[f"PDF not found: {pdf_path}"],
            )

        protocol_id = protocol_id or pdf_file.stem
        protocol_name = protocol_name or protocol_id

        self._current_pdf_path = str(pdf_file)

        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if output_dir:
            output_path = Path(output_dir) / timestamp
        else:
            output_path = pdf_file.parent / "soa_output" / timestamp
        output_path.mkdir(parents=True, exist_ok=True)

        result = ExtractionResult(
            success=True,
            protocol_id=protocol_id,
            output_dir=str(output_path),
        )

        logger.info("=" * 70)
        logger.info(f"SOA EXTRACTION PIPELINE WITH MERGE ANALYSIS: {protocol_id}")
        logger.info("=" * 70)

        try:
            # Phase 1: Detection
            if detected_pages:
                logger.info("[Phase 1] DETECTION - Using pre-detected pages")
                soa_tables = detected_pages
                detection_result = PhaseResult(
                    phase="detection",
                    success=True,
                    data=detected_pages,
                    duration=0.0,
                    from_cache=True,
                )
            else:
                detection_result = await self._phase_detection(pdf_path, protocol_id)
                if not detection_result.success:
                    raise RuntimeError(f"Detection failed: {detection_result.error}")
                soa_tables = detection_result.data
            result.phases.append(detection_result)

            detected_gemini_uri = soa_tables.get("geminiFileUri")

            # Phase 2: Extraction
            extraction_result = await self._phase_extraction(pdf_path, soa_tables, protocol_id)
            result.phases.append(extraction_result)
            if not extraction_result.success:
                raise RuntimeError(f"Extraction failed: {extraction_result.error}")

            html_tables = extraction_result.data

            # Phase 3: Per-table USDM extraction (skip 12-stage interpretation)
            effective_gemini_uri = gemini_file_uri or detected_gemini_uri
            interpretation_result = await self._phase_interpretation(
                html_tables,
                protocol_id,
                protocol_name,
                run_interpretation=False,  # Don't run 12-stage yet
                extraction_outputs=extraction_outputs,
                output_path=output_path,
                gemini_file_uri=effective_gemini_uri,
                skip_interpretation=True,  # Get per-table USDM
            )
            result.phases.append(interpretation_result)
            if not interpretation_result.success:
                raise RuntimeError(f"Interpretation failed: {interpretation_result.error}")

            per_table_results = interpretation_result.data.get("per_table_results", [])
            result.per_table_results = per_table_results

            # Save per-table USDM to local JSON files
            per_table_output_dir = output_path / "per_table_usdm"
            per_table_output_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"  Saving per-table USDM to: {per_table_output_dir}")

            saved_files = []
            for ptr in per_table_results:
                if ptr.usdm:
                    table_file = per_table_output_dir / f"{protocol_id}_{ptr.table_id}_{ptr.category}.json"
                    with open(table_file, 'w') as f:
                        json.dump(ptr.usdm, f, indent=2, default=str)
                    saved_files.append(str(table_file))
                    logger.info(f"    Saved: {table_file.name}")

            # Save per-table summary
            summary = {
                "protocolId": protocol_id,
                "timestamp": timestamp,
                "totalTables": len(per_table_results),
                "successfulTables": sum(1 for ptr in per_table_results if ptr.success),
                "tables": [
                    {
                        "tableId": ptr.table_id,
                        "category": ptr.category,
                        "status": "success" if ptr.success else "failed",
                        "error": ptr.error,
                        "counts": ptr.counts,
                        "file": f"{protocol_id}_{ptr.table_id}_{ptr.category}.json" if ptr.usdm else None,
                    }
                    for ptr in per_table_results
                ],
                "outputDir": str(per_table_output_dir),
            }
            summary_file = per_table_output_dir / f"{protocol_id}_per_table_summary.json"
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
            logger.info(f"    Saved summary: {summary_file.name}")

            # Also save merged USDM (before interpretation)
            merged_usdm = interpretation_result.data.get("usdm")
            if merged_usdm:
                merged_file = output_path / f"{protocol_id}_merged_usdm_raw.json"
                with open(merged_file, 'w') as f:
                    json.dump(merged_usdm, f, indent=2, default=str)
                logger.info(f"    Saved merged USDM: {merged_file.name}")

            # Phase 3.5: Merge Analysis
            merge_result = await self._phase_merge_analysis(
                per_table_results,
                protocol_id,
                output_path,
            )
            result.phases.append(merge_result)

            if not merge_result.success:
                logger.warning(f"Merge analysis failed: {merge_result.error}")
                # Continue without merge analysis - fall back to single group
                merge_plan = MergePlan(
                    protocol_id=protocol_id,
                    total_tables=len(per_table_results),
                    merge_groups=[MergeGroup(
                        id="MG-001",
                        table_ids=[ptr.table_id for ptr in per_table_results],
                        merge_type=MergeType.STANDALONE,
                        confidence=0.5,
                        reasoning="Merge analysis failed - all tables grouped",
                    )],
                )
            else:
                merge_plan = merge_result.data

            # Store merge plan in result
            result.raw_soa_extraction = {
                "merge_plan": merge_plan.to_dict(),
                "per_table_results": [ptr.to_dict() for ptr in per_table_results],
            }

            # If auto_confirm_merges, continue with interpretation
            if auto_confirm_merges:
                logger.info("\n[Auto-Confirm] Running 12-stage interpretation on all merge groups...")

                # Run interpretation on each merge group
                all_usdm = []
                merge_group_results = []  # Store results for each merge group

                for mg in merge_plan.merge_groups:
                    logger.info(f"  Processing merge group {mg.id}: {mg.table_ids}")

                    # Combine USDM from tables in this group
                    combined_usdm = combine_table_usdm(per_table_results, mg.table_ids)

                    if not combined_usdm:
                        logger.warning(f"    No USDM for group {mg.id}, skipping")
                        merge_group_results.append({
                            "merge_group_id": mg.id,
                            "table_ids": mg.table_ids,
                            "merge_type": mg.merge_type.value if mg.merge_type else None,
                            "status": "skipped",
                            "error": "No USDM data available",
                            "merged_usdm": None,
                            "final_usdm": None,
                            "stage_results": {},
                            "interpretation_summary": None,
                        })
                        continue

                    # Run 12-stage interpretation
                    effective_extraction_outputs = extraction_outputs
                    if effective_extraction_outputs is None:
                        effective_extraction_outputs = auto_discover_extraction_outputs(pdf_file)

                    interp_config = InterpretationConfig(
                        protocol_id=f"{protocol_id}_{mg.id}",
                        protocol_name=protocol_name,
                        extraction_outputs=effective_extraction_outputs,
                        gemini_file_uri=effective_gemini_uri,
                        skip_stage_11=True,
                        continue_on_non_critical_failure=True,
                        save_intermediate_results=True,
                        output_dir=output_path / "interpretation_stages" / mg.id,
                    )

                    pipeline_result = await self.interpretation_pipeline.run(combined_usdm, interp_config)

                    # Serialize stage results for storage
                    serialized_stage_results = {}
                    for stage_num, stage_result in pipeline_result.stage_results.items():
                        if stage_result is not None:
                            if hasattr(stage_result, 'to_dict'):
                                serialized_stage_results[stage_num] = stage_result.to_dict()
                            elif hasattr(stage_result, '__dict__'):
                                serialized_stage_results[stage_num] = {
                                    k: v for k, v in stage_result.__dict__.items()
                                    if not k.startswith('_')
                                }
                            else:
                                serialized_stage_results[stage_num] = stage_result

                    # Build merge group result
                    mg_result = {
                        "merge_group_id": mg.id,
                        "table_ids": mg.table_ids,
                        "merge_type": mg.merge_type.value if mg.merge_type else None,
                        "status": "completed" if pipeline_result.success else "failed",
                        "error": pipeline_result.errors[0] if pipeline_result.errors else None,
                        "merged_usdm": combined_usdm,
                        "final_usdm": pipeline_result.final_usdm,
                        "stage_results": serialized_stage_results,
                        "interpretation_summary": {
                            "success": pipeline_result.success,
                            "stages_completed": pipeline_result.stages_completed,
                            "stages_failed": pipeline_result.stages_failed,
                            "stages_skipped": pipeline_result.stages_skipped,
                            "total_duration_seconds": pipeline_result.total_duration_seconds,
                            "stage_durations": pipeline_result.stage_durations,
                            "stage_statuses": pipeline_result.stage_statuses,
                            "warnings": pipeline_result.warnings,
                        },
                        "counts": {
                            "visits": len(pipeline_result.final_usdm.get("visits", [])) if pipeline_result.final_usdm else 0,
                            "activities": len(pipeline_result.final_usdm.get("activities", [])) if pipeline_result.final_usdm else 0,
                            "sais": len(pipeline_result.final_usdm.get("scheduledActivityInstances", [])) if pipeline_result.final_usdm else 0,
                            "footnotes": len(pipeline_result.final_usdm.get("footnotes", [])) if pipeline_result.final_usdm else 0,
                        },
                    }
                    merge_group_results.append(mg_result)

                    if pipeline_result.final_usdm:
                        propagate_provenance(pipeline_result.final_usdm)
                        all_usdm.append({
                            "merge_group_id": mg.id,
                            "table_ids": mg.table_ids,
                            "usdm": pipeline_result.final_usdm,
                        })

                    logger.info(f"    {mg.id}: {pipeline_result.get_summary()}")

                # Store merge group results in the result object
                result.merge_group_results = merge_group_results

                # Merge all group USDMs into final output
                if all_usdm:
                    final_usdm = self._merge_group_usdm(all_usdm, protocol_id)
                    result.usdm_data = final_usdm

                    # Update counts
                    result.visits_count = len(final_usdm.get("visits", []))
                    result.activities_count = len(final_usdm.get("activities", []))
                    result.instances_count = len(final_usdm.get("scheduledActivityInstances", []))
                    result.footnotes_count = len(final_usdm.get("footnotes", []))

                    # Phase 4: Validation
                    validation_result = await self._phase_validation(final_usdm, protocol_id)
                    result.phases.append(validation_result)
                    result.quality_score = validation_result.data

                    # Phase 5: Output
                    output_result = await self._phase_output(
                        final_usdm,
                        None,  # No single interpretation result
                        result.quality_score,
                        result.raw_soa_extraction,
                        output_path,
                        protocol_id,
                        protocol_name,
                    )
                    result.phases.append(output_result)
                    result.output_files = output_result.data.get("files", []) if isinstance(output_result.data, dict) else []

            else:
                # Stop here - human needs to confirm merge plan
                logger.info("\n[Checkpoint] Merge plan saved. Awaiting human confirmation.")
                logger.info(f"  Review merge plan at: {output_path / f'{protocol_id}_merge_plan.json'}")

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            logger.error(f"Pipeline failed: {e}")
            import traceback
            traceback.print_exc()

        result.total_duration = time.time() - start_time
        self._log_summary(result)

        return result

    def _merge_group_usdm(
        self,
        group_usdms: List[Dict[str, Any]],
        protocol_id: str,
    ) -> Dict[str, Any]:
        """Merge USDM from multiple interpretation groups into final output."""
        merged = {
            "protocolId": protocol_id,
            "visits": [],
            "encounters": [],
            "activities": [],
            "scheduledActivityInstances": [],
            "footnotes": [],
            "_mergeGroups": [g["merge_group_id"] for g in group_usdms],
        }

        seen_visit_names = set()
        seen_activity_names = set()
        seen_footnote_texts = set()

        for group_data in group_usdms:
            usdm = group_data["usdm"]

            # Merge visits
            for visit in usdm.get("visits", usdm.get("encounters", [])):
                name = visit.get("name")
                if name and name not in seen_visit_names:
                    merged["visits"].append(visit)
                    seen_visit_names.add(name)

            # Merge activities
            for activity in usdm.get("activities", []):
                name = activity.get("name")
                if name and name not in seen_activity_names:
                    merged["activities"].append(activity)
                    seen_activity_names.add(name)

            # Merge SAIs (all unique)
            merged["scheduledActivityInstances"].extend(
                usdm.get("scheduledActivityInstances", [])
            )

            # Merge footnotes
            for footnote in usdm.get("footnotes", []):
                text = footnote.get("text", footnote.get("footnoteText"))
                if text and text not in seen_footnote_texts:
                    merged["footnotes"].append(footnote)
                    seen_footnote_texts.add(text)

        merged["encounters"] = merged["visits"]
        return merged

    def _merge_per_table_usdm(
        self,
        per_table_results: List[PerTableResult],
        protocol_id: str,
    ) -> Dict[str, Any]:
        """Merge per-table USDM results into a single USDM structure."""
        merged = {
            "protocolId": protocol_id,
            "visits": [],
            "encounters": [],
            "activities": [],
            "scheduledActivityInstances": [],
            "footnotes": [],
        }

        for ptr in per_table_results:
            if not ptr.success or not ptr.usdm:
                continue

            # Merge visits (avoiding duplicates by name)
            existing_visit_names = {v.get("name") for v in merged["visits"]}
            for visit in ptr.usdm.get("visits", []):
                if visit.get("name") not in existing_visit_names:
                    merged["visits"].append(visit)
                    existing_visit_names.add(visit.get("name"))

            # Merge activities (avoiding duplicates by name)
            existing_activity_names = {a.get("name") for a in merged["activities"]}
            for activity in ptr.usdm.get("activities", []):
                if activity.get("name") not in existing_activity_names:
                    merged["activities"].append(activity)
                    existing_activity_names.add(activity.get("name"))

            # Merge SAIs (all are unique)
            merged["scheduledActivityInstances"].extend(
                ptr.usdm.get("scheduledActivityInstances", [])
            )

            # Merge footnotes (avoiding duplicates by text)
            existing_footnote_texts = {f.get("text", f.get("footnoteText")) for f in merged["footnotes"]}
            for footnote in ptr.usdm.get("footnotes", []):
                text = footnote.get("text", footnote.get("footnoteText"))
                if text not in existing_footnote_texts:
                    merged["footnotes"].append(footnote)
                    existing_footnote_texts.add(text)

        # Copy encounters from visits for compatibility
        merged["encounters"] = merged["visits"]

        return merged

    def _build_base_usdm(
        self,
        interpretation: Dict[str, Any],
        protocol_id: str,
    ) -> Dict[str, Any]:
        """Build base USDM 4.0 structure from HTML interpretation."""
        CDISC_CT_VERSION = "2024-12-20"

        # Keep the flat structure for interpretation pipeline compatibility
        # (visits, activities, scheduledActivityInstances at top level)

        usdm = {
            "protocolId": protocol_id,
            "protocolType": interpretation.get("protocolType", "hybrid"),
            "primaryReferencePoint": interpretation.get("primaryReferencePoint", "randomization"),
            "visits": interpretation.get("visits", []),
            "encounters": interpretation.get("visits", []),  # Alias for compatibility
            "activities": interpretation.get("activities", []),
            "scheduledActivityInstances": interpretation.get("scheduledActivityInstances", []),
            "footnotes": interpretation.get("footnotes", []),
            "qualityMetrics": interpretation.get("qualityMetrics", {}),
        }

        # Propagate provenance to nested objects (timing, window, etc.)
        # This ensures quality scoring finds provenance for nested value fields
        propagate_provenance(usdm)
        logger.debug("Provenance propagated to nested objects")

        return usdm

    # =========================================================================
    # PHASE 4: VALIDATION
    # =========================================================================

    async def _phase_validation(
        self,
        usdm_data: Dict[str, Any],
        protocol_id: str,
    ) -> PhaseResult:
        """Phase 4: Validate USDM structure with quality checks."""
        start = time.time()
        logger.info("\n[Phase 4] VALIDATION - Quality checks...")

        try:
            quality_score = await self.quality_checker.evaluate_with_llm(
                usdm_data,
                use_llm_fallback=True
            )

            logger.info(f"  Overall: {quality_score.overall_score:.1%} [{quality_score.status}]")
            logger.info(f"    Accuracy: {quality_score.accuracy:.1%}")
            logger.info(f"    Completeness: {quality_score.completeness:.1%}")
            logger.info(f"    Compliance: {quality_score.compliance:.1%}")
            logger.info(f"    Provenance: {quality_score.provenance:.1%}")
            logger.info(f"    Terminology: {quality_score.terminology:.1%}")

            return PhaseResult(
                phase="validation",
                success=True,
                data=quality_score,
                duration=time.time() - start,
            )

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return PhaseResult(
                phase="validation",
                success=False,
                error=str(e),
                duration=time.time() - start,
            )

    # =========================================================================
    # PHASE 5: OUTPUT
    # =========================================================================

    async def _phase_output(
        self,
        usdm_data: Dict[str, Any],
        interpretation_result: Optional[InterpretationResult],
        quality_score: Optional[QualityScore],
        raw_soa_extraction: Optional[Dict[str, Any]],
        output_path: Path,
        protocol_id: str,
        protocol_name: str = "",
    ) -> PhaseResult:
        """Phase 5: Save outputs including review JSONs for UI."""
        start = time.time()
        logger.info("\n[Phase 5] OUTPUT - Saving results...")

        try:
            output_files = []
            extraction_review = None
            interpretation_review = None

            # Check if this is a draft schedule
            is_draft = interpretation_result and getattr(interpretation_result, "is_draft", False)

            # Save USDM JSON (draft or final)
            if is_draft:
                # Save as draft file
                usdm_file = output_path / f"{protocol_id}_soa_usdm_draft.json"
            else:
                usdm_file = output_path / f"{protocol_id}_soa_usdm.json"

            with open(usdm_file, 'w') as f:
                json.dump(usdm_data, f, indent=2, default=str)
            output_files.append(str(usdm_file))
            logger.info(f"  Saved: {usdm_file.name}")

            # Save quality report
            if quality_score:
                quality_file = output_path / f"{protocol_id}_soa_quality.json"
                with open(quality_file, 'w') as f:
                    json.dump(quality_score.to_dict(), f, indent=2)
                output_files.append(str(quality_file))
                logger.info(f"  Saved: {quality_file.name}")

            # Generate Phase 1: Extraction Review JSON for UI
            logger.info("  Generating extraction review JSON (Phase 1)...")
            if raw_soa_extraction:
                try:
                    extraction_review = generate_extraction_review(
                        raw_soa_extraction,
                        protocol_id,
                        protocol_name or protocol_id,
                    )
                    extraction_review_file = output_path / f"{protocol_id}_extraction_review.json"
                    with open(extraction_review_file, 'w') as f:
                        json.dump(extraction_review, f, indent=2)
                    output_files.append(str(extraction_review_file))
                    logger.info(f"  Saved: {extraction_review_file.name}")
                except Exception as e:
                    logger.warning(f"  Failed to generate extraction review: {e}")

            # Generate Phase 2: Interpretation Review JSON for UI
            logger.info("  Generating interpretation review JSON (Phase 2)...")
            if interpretation_result:
                try:
                    interpretation_review = generate_interpretation_review(
                        interpretation_result,
                        protocol_id,
                        protocol_name or protocol_id,
                    )
                    interpretation_review_file = output_path / f"{protocol_id}_interpretation_review.json"
                    with open(interpretation_review_file, 'w') as f:
                        json.dump(interpretation_review, f, indent=2)
                    output_files.append(str(interpretation_review_file))
                    logger.info(f"  Saved: {interpretation_review_file.name}")
                except Exception as e:
                    logger.warning(f"  Failed to generate interpretation review: {e}")

            # Save pipeline summary
            summary_file = output_path / f"{protocol_id}_pipeline_summary.json"
            summary = {
                "timestamp": datetime.now().isoformat(),
                "protocol_id": protocol_id,
                "is_draft": is_draft,
                "counts": {
                    "visits": len(usdm_data.get("visits", [])),
                    "activities": len(usdm_data.get("activities", [])),
                    "instances": len(usdm_data.get("scheduledActivityInstances", [])),
                    "footnotes": len(usdm_data.get("footnotes", [])),
                },
                "quality": quality_score.to_dict() if quality_score else None,
                "interpretation_pipeline": interpretation_result.to_dict() if interpretation_result else None,
                "review_files": {
                    "extraction_review": f"{protocol_id}_extraction_review.json" if extraction_review else None,
                    "interpretation_review": f"{protocol_id}_interpretation_review.json" if interpretation_review else None,
                },
            }
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
            output_files.append(str(summary_file))
            logger.info(f"  Saved: {summary_file.name}")

            return PhaseResult(
                phase="output",
                success=True,
                data={
                    "files": output_files,
                    "extraction_review": extraction_review,
                    "interpretation_review": interpretation_review,
                },
                duration=time.time() - start,
            )

        except Exception as e:
            logger.error(f"Output failed: {e}")
            return PhaseResult(
                phase="output",
                success=False,
                error=str(e),
                duration=time.time() - start,
            )

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _log_summary(self, result: ExtractionResult) -> None:
        """Log pipeline summary."""
        logger.info("\n" + "=" * 70)
        logger.info("SOA EXTRACTION PIPELINE COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Protocol: {result.protocol_id}")
        logger.info(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
        logger.info(f"Duration: {result.total_duration:.2f}s")

        if result.quality_score:
            logger.info(f"Quality: {result.quality_score.overall_score:.1%} [{result.quality_score.status}]")

        logger.info(f"Counts: {result.visits_count} visits, {result.activities_count} activities, "
                   f"{result.instances_count} instances, {result.footnotes_count} footnotes")

        logger.info("\nPhases:")
        for phase in result.phases:
            status = "OK" if phase.success else "FAIL"
            cache = " (cache)" if phase.from_cache else ""
            logger.info(f"  {phase.phase}: {status} ({phase.duration:.2f}s){cache}")

        if result.output_dir:
            logger.info(f"\nOutput: {result.output_dir}")

        if result.errors:
            logger.info("\nErrors:")
            for e in result.errors:
                logger.info(f"  - {e}")


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


async def run_soa_extraction(
    pdf_path: str,
    output_dir: Optional[str] = None,
    protocol_id: Optional[str] = None,
    protocol_name: Optional[str] = None,
    use_cache: bool = True,
    run_interpretation: bool = True,
    skip_interpretation: bool = False,
    extraction_outputs: Optional[Dict[str, Dict]] = None,
    gemini_file_uri: Optional[str] = None,
    use_gemini_fallback: bool = True,
    detected_pages: Optional[Dict[str, Any]] = None,
) -> ExtractionResult:
    """
    Run full SOA extraction pipeline.

    Args:
        pdf_path: Path to protocol PDF
        output_dir: Output directory (default: adjacent to PDF)
        protocol_id: Protocol identifier (default: PDF filename stem)
        protocol_name: Protocol display name (default: protocol_id)
        use_cache: Whether to use caching
        run_interpretation: Whether to run 12-stage interpretation pipeline
        skip_interpretation: If True, skip 12-stage pipeline and return raw per-table USDM
        extraction_outputs: Module extraction results for Stage 9
        gemini_file_uri: Optional Gemini Files API URI for PDF access (enables LLM to search PDF)
        use_gemini_fallback: Whether to use Gemini as fallback when LandingAI extraction is incomplete
        detected_pages: Optional pre-detected pages (skips Phase 1 if provided)

    Returns:
        ExtractionResult with all outputs
    """
    pipeline = SOAExtractionPipeline(use_cache=use_cache, use_gemini_fallback=use_gemini_fallback)
    return await pipeline.run(
        pdf_path=pdf_path,
        output_dir=output_dir,
        protocol_id=protocol_id,
        protocol_name=protocol_name,
        run_interpretation=run_interpretation,
        skip_interpretation=skip_interpretation,
        extraction_outputs=extraction_outputs,
        gemini_file_uri=gemini_file_uri,
        detected_pages=detected_pages,
    )


# =============================================================================
# CLI SUPPORT
# =============================================================================


def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case for module key compatibility."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def load_extraction_outputs(usdm_path: str) -> dict:
    """
    Load extraction outputs from USDM 4.0 JSON file.

    Extracts domainSections from the USDM file and converts keys
    from camelCase to snake_case for Stage 9 compatibility.

    Args:
        usdm_path: Path to USDM 4.0 JSON from main pipeline

    Returns:
        Dictionary of extraction outputs keyed by snake_case module names
    """
    with open(usdm_path) as f:
        usdm_data = json.load(f)

    domain_sections = usdm_data.get("domainSections", {})
    # Unwrap the 'data' field from each domain section wrapper
    # USDM structure: {moduleId, instanceType, data: {...actual extraction data...}}
    # Stage 9 expects the inner 'data' dict directly for field access
    extraction_outputs = {
        camel_to_snake(k): v.get("data", v) if isinstance(v, dict) else v
        for k, v in domain_sections.items()
    }

    logger.info(f"Loaded {len(extraction_outputs)} domain sections from {usdm_path}")
    for key in extraction_outputs.keys():
        logger.debug(f"  - {key}")

    return extraction_outputs


def auto_discover_extraction_outputs(pdf_path: Path) -> Optional[Dict]:
    """
    Auto-discover and load extraction outputs from nearby extraction_output folder.

    Looks for the most recent extraction run in the same directory as the PDF,
    enabling Stage 9 Protocol Mining without explicit --extraction-outputs flag.

    Args:
        pdf_path: Path to the protocol PDF

    Returns:
        Dictionary of extraction outputs if found, None otherwise
    """
    pdf_path = Path(pdf_path)
    pdf_dir = pdf_path.parent
    pdf_stem = pdf_path.stem

    # Try extraction_output folder (standard location)
    extraction_dir = pdf_dir / "extraction_output"
    if not extraction_dir.exists():
        logger.debug(f"No extraction_output folder found at {extraction_dir}")
        return None

    # Find most recent timestamp folder
    try:
        timestamp_dirs = sorted(
            [d for d in extraction_dir.iterdir() if d.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
    except Exception as e:
        logger.warning(f"Error listing extraction_output folder: {e}")
        return None

    if not timestamp_dirs:
        logger.debug(f"No timestamp folders found in {extraction_dir}")
        return None

    # Try each timestamp folder (most recent first)
    for ts_dir in timestamp_dirs:
        # Try various naming patterns
        candidates = [
            ts_dir / f"{pdf_stem}_usdm_4.0.json",
            ts_dir / f"{pdf_stem}_usdm.json",
        ]

        # Also try any *_usdm*.json file in the folder
        try:
            usdm_files = list(ts_dir.glob("*_usdm*.json"))
            candidates.extend(usdm_files)
        except Exception:
            pass

        for usdm_file in candidates:
            if usdm_file.exists():
                try:
                    extraction_outputs = load_extraction_outputs(str(usdm_file))
                    logger.info(f"Auto-discovered extraction outputs from {usdm_file}")
                    return extraction_outputs
                except Exception as e:
                    logger.warning(f"Failed to load {usdm_file}: {e}")
                    continue

    logger.debug(f"No USDM file found in any timestamp folder under {extraction_dir}")
    return None


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(
        description="SOA Extraction Pipeline - Extract Schedule of Assessments from protocol PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic SOA extraction
  python soa_extraction_pipeline.py /path/to/protocol.pdf

  # SOA extraction with protocol mining (uses main pipeline outputs)
  python soa_extraction_pipeline.py /path/to/protocol.pdf \\
      --extraction-outputs /path/to/protocol_usdm_4.0.json

  # Skip interpretation pipeline (raw extraction only)
  python soa_extraction_pipeline.py /path/to/protocol.pdf --no-interpretation
        """
    )
    parser.add_argument("pdf_path", help="Path to protocol PDF")
    parser.add_argument(
        "--extraction-outputs",
        type=str,
        help="Path to USDM 4.0 JSON from main pipeline (enables Stage 9 protocol mining)"
    )
    parser.add_argument(
        "--no-interpretation",
        action="store_true",
        help="Skip 12-stage interpretation pipeline"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching"
    )
    parser.add_argument(
        "--no-gemini-fallback",
        action="store_true",
        help="Disable Gemini fallback for incomplete LandingAI extractions"
    )
    parser.add_argument(
        "--analyze-merges",
        action="store_true",
        help="Run with merge analysis (Phase 3.5) for multi-table protocols"
    )
    parser.add_argument(
        "--auto-confirm-merges",
        action="store_true",
        help="Auto-confirm all suggested merges (for testing with --analyze-merges)"
    )

    args = parser.parse_args()

    # Load extraction outputs if provided
    extraction_outputs = None
    if args.extraction_outputs:
        extraction_outputs = load_extraction_outputs(args.extraction_outputs)

    async def main():
        if args.analyze_merges:
            # Run with merge analysis
            pipeline = SOAExtractionPipeline(
                use_cache=not args.no_cache,
                use_gemini_fallback=not args.no_gemini_fallback,
            )
            result = await pipeline.run_with_merge_analysis(
                pdf_path=args.pdf_path,
                extraction_outputs=extraction_outputs,
                auto_confirm_merges=args.auto_confirm_merges,
            )
        else:
            # Standard run
            result = await run_soa_extraction(
                pdf_path=args.pdf_path,
                use_cache=not args.no_cache,
                run_interpretation=not args.no_interpretation,
                extraction_outputs=extraction_outputs,
                use_gemini_fallback=not args.no_gemini_fallback,
            )

        print("\n" + "=" * 70)
        print("RESULT SUMMARY")
        print("=" * 70)
        print(result.get_summary())
        print(f"\nOutput: {result.output_dir}")
        if result.errors:
            print(f"\nErrors: {result.errors}")

        # Print merge plan info if applicable
        if args.analyze_merges and result.raw_soa_extraction:
            merge_plan = result.raw_soa_extraction.get("merge_plan", {})
            if merge_plan:
                print(f"\nMerge Plan:")
                print(f"  Total tables: {merge_plan.get('totalTablesInput', 0)}")
                print(f"  Merge groups: {merge_plan.get('suggestedMergeGroups', 0)}")
                for mg in merge_plan.get("mergeGroups", []):
                    print(f"    {mg.get('id')}: {mg.get('tableIds')} - {mg.get('mergeType')}")

    asyncio.run(main())
