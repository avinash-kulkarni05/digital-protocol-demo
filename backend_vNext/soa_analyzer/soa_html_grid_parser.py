"""
SOA HTML Grid Parser

Parses HTML tables into structured grids with cell coordinates.
Uses LLM for intelligent marker extraction instead of regex.

Design Principle: Deterministic code for structural parsing (HTML → grid),
LLM for intelligent decisions (marker extraction, context-dependent parsing).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from .models import (
    CellContent,
    CellPosition,
    TableGrid,
)

logger = logging.getLogger(__name__)


class HTMLGridParser:
    """Parse HTML tables into TableGrid with cell coordinates.

    Provides deterministic HTML parsing for table structure, with optional
    LLM-assisted marker extraction for intelligent footnote identification.
    """

    def __init__(self, llm_client=None):
        """Initialize parser with optional LLM client.

        Args:
            llm_client: Optional LLM client for marker extraction.
                        If not provided, markers must be extracted separately.
        """
        self.llm_client = llm_client
        self._prompt_cache: Dict[str, str] = {}

    def parse(self, html: str, table_id: str, page_number: int) -> TableGrid:
        """Parse HTML table into structured grid.

        This is deterministic parsing - no LLM calls. Handles:
        - rowspan/colspan expansion
        - Header row detection
        - Activity column detection

        Args:
            html: HTML string containing a table
            table_id: Unique identifier for this table
            page_number: PDF page number where table appears

        Returns:
            TableGrid with cells, but without footnote markers extracted
        """
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')

        if not table:
            logger.warning(f"No table found in HTML for {table_id}")
            return TableGrid(
                table_id=table_id,
                page_number=page_number,
            )

        cells = []
        occupation_map: Dict[Tuple[int, int], bool] = {}
        row_idx = 0
        max_col = 0

        for row in table.find_all('tr'):
            col_idx = 0

            for cell in row.find_all(['td', 'th']):
                # Skip occupied cells (from rowspan/colspan)
                while (row_idx, col_idx) in occupation_map:
                    col_idx += 1

                raw_text = cell.get_text(strip=True)
                rowspan = int(cell.get('rowspan', 1))
                colspan = int(cell.get('colspan', 1))

                # Mark occupied cells for rowspan/colspan
                for r in range(rowspan):
                    for c in range(colspan):
                        occupation_map[(row_idx + r, col_idx + c)] = True

                # Determine cell type heuristically
                is_header = cell.name == 'th' or row_idx == 0
                is_activity_label = col_idx == 0 and row_idx > 0

                cell_type = self._classify_cell_type(raw_text, is_header, is_activity_label)

                cells.append(CellContent(
                    position=CellPosition(
                        table_id=table_id,
                        page_number=page_number,
                        row_idx=row_idx,
                        col_idx=col_idx,
                        row_span=rowspan,
                        col_span=colspan,
                    ),
                    raw_text=raw_text,
                    normalized_text=raw_text,  # LLM will normalize later if needed
                    footnote_markers=[],       # LLM will extract later
                    is_header=is_header,
                    is_activity_label=is_activity_label,
                    cell_type=cell_type,
                ))

                max_col = max(max_col, col_idx + colspan)
                col_idx += colspan

            row_idx += 1

        # Build the grid with mappings
        return self._build_grid(cells, table_id, page_number, row_idx, max_col)

    def _classify_cell_type(self, text: str, is_header: bool, is_activity: bool) -> str:
        """Classify cell type based on content."""
        if is_header:
            return "header"
        if is_activity:
            return "activity"
        if not text.strip():
            return "empty"
        # Check for common checkmark indicators
        check_indicators = {"X", "x", "✓", "✔", "●", "•", "Y", "Yes", "YES"}
        if text.strip() in check_indicators:
            return "checkmark"
        return "data"

    def _build_grid(
        self,
        cells: List[CellContent],
        table_id: str,
        page_number: int,
        num_rows: int,
        num_cols: int,
    ) -> TableGrid:
        """Build TableGrid from parsed cells."""
        # Build row_to_activity mapping (activity labels in first column)
        row_to_activity: Dict[int, str] = {}
        for cell in cells:
            if cell.is_activity_label and cell.normalized_text.strip():
                row_to_activity[cell.position.row_idx] = cell.normalized_text.strip()

        # Build col_to_visit mapping (visit names in header row)
        col_to_visit: Dict[int, str] = {}
        for cell in cells:
            if cell.is_header and cell.position.col_idx > 0:  # Skip first column (usually "Activity" label)
                col_to_visit[cell.position.col_idx] = cell.normalized_text.strip()

        return TableGrid(
            table_id=table_id,
            page_number=page_number,
            cells=cells,
            num_rows=num_rows,
            num_cols=num_cols,
            row_to_activity=row_to_activity,
            col_to_visit=col_to_visit,
            marker_to_cells={},  # Will be populated by LLM marker extraction
        )

    async def extract_markers_with_llm(self, grid: TableGrid) -> TableGrid:
        """Use LLM to extract footnote markers from all cells (batch call).

        This is an intelligent operation - uses LLM to:
        - Identify context-dependent markers (e.g., "Visit 1a" where "a" is a marker)
        - Normalize OCR errors and Unicode variants
        - Handle multi-character markers

        Args:
            grid: TableGrid with cells to process

        Returns:
            Updated TableGrid with footnote_markers populated
        """
        if not self.llm_client:
            raise ValueError("LLM client required for marker extraction")

        # Filter cells with text content
        cells_to_process = [
            (i, c) for i, c in enumerate(grid.cells)
            if c.raw_text.strip() and c.cell_type != "empty"
        ]

        if not cells_to_process:
            return grid

        # Build prompt with cell texts
        cell_data = [
            {"idx": i, "text": c.raw_text, "type": c.cell_type}
            for i, c in cells_to_process
        ]

        prompt = self._load_prompt("marker_extraction.txt").format(
            cell_data=json.dumps(cell_data, indent=2)
        )

        try:
            response = await self.llm_client.generate(
                prompt,
                response_format="json",
            )

            # Parse response and update cells
            if isinstance(response, str):
                response = json.loads(response)

            self._apply_marker_results(grid, response)

        except Exception as e:
            logger.error(f"LLM marker extraction failed: {e}")
            # Continue with empty markers rather than failing

        return grid

    def _apply_marker_results(self, grid: TableGrid, results: List[Dict]) -> None:
        """Apply LLM extraction results to grid cells."""
        marker_to_cells: Dict[str, List[CellPosition]] = {}

        for item in results:
            try:
                cell_idx = item.get("idx")
                markers = item.get("markers", [])
                normalized = item.get("normalized", "")

                if cell_idx is None or cell_idx >= len(grid.cells):
                    continue

                cell = grid.cells[cell_idx]
                cell.footnote_markers = markers
                if normalized:
                    cell.normalized_text = normalized

                # Build marker-to-cells index
                for marker in markers:
                    if marker not in marker_to_cells:
                        marker_to_cells[marker] = []
                    marker_to_cells[marker].append(cell.position)

            except Exception as e:
                logger.warning(f"Error applying marker result: {e}")

        grid.marker_to_cells = marker_to_cells

    def _load_prompt(self, filename: str) -> str:
        """Load prompt template from file."""
        if filename in self._prompt_cache:
            return self._prompt_cache[filename]

        prompt_path = Path(__file__).parent / "prompts" / filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

        prompt = prompt_path.read_text(encoding='utf-8')
        self._prompt_cache[filename] = prompt
        return prompt

    def build_table_context(self, grids: List[TableGrid]) -> str:
        """Build compact table representation for LLM context.

        Used when providing table structure to LLM for linking decisions.

        Args:
            grids: List of parsed TableGrid objects

        Returns:
            Compact string representation of table structures
        """
        context_parts = []
        for grid in grids:
            headers = [c for c in grid.cells if c.is_header]
            activities = [c for c in grid.cells if c.is_activity_label]

            # Build cells with markers summary
            cells_with_markers = [
                (c.position.row_idx, c.position.col_idx, c.footnote_markers)
                for c in grid.cells if c.footnote_markers
            ]

            context_parts.append(f"""
Table: {grid.table_id} (Page {grid.page_number})
Size: {grid.num_rows} rows x {grid.num_cols} cols
Columns (visits): {[h.raw_text for h in headers]}
Rows (activities): {[a.raw_text for a in activities][:20]}  # Limit for context
Cells with markers: {cells_with_markers}""")

        return "\n".join(context_parts)


def parse_html_tables(
    html_tables: List[Dict[str, Any]],
    llm_client=None,
) -> List[TableGrid]:
    """Convenience function to parse multiple HTML tables.

    Args:
        html_tables: List of dicts with 'html_content', 'table_name', 'page_start'
        llm_client: Optional LLM client for marker extraction

    Returns:
        List of parsed TableGrid objects
    """
    parser = HTMLGridParser(llm_client)
    grids = []

    for table in html_tables:
        grid = parser.parse(
            html=table.get("html_content", ""),
            table_id=table.get("table_name", f"table_{len(grids)}"),
            page_number=table.get("page_start", 0),
        )
        grids.append(grid)

    return grids
