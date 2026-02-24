"""
LandingAI OCR Adapter for SOA Table Extraction

This adapter wraps the agentic-doc library to extract tables from PDF pages
and convert them to HTML format for the SOA interpretation pipeline.
"""

import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class TableExtractionResult:
    """Result of table extraction from a single page."""
    html: str
    confidence: float
    page_number: int
    raw_response: Optional[Dict[str, Any]] = None


class LandingAIOCRAdapter:
    """
    Adapter for LandingAI's Agentic Document Extraction API.

    Extracts tables from PDF pages and converts them to HTML format
    suitable for the SOA interpretation pipeline.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the LandingAI OCR adapter.

        Args:
            api_key: LandingAI API key. If not provided, will be read from
                     LANDINGAI_API_KEY environment variable.
        """
        self.api_key = api_key or os.getenv("LANDINGAI_API_KEY")
        if not self.api_key:
            logger.warning("LANDINGAI_API_KEY not set - table extraction may fail")

        # Set the API key in environment for agentic-doc
        if self.api_key:
            os.environ["VISION_AGENT_API_KEY"] = self.api_key

    def extract_table(self, image: Union[Image.Image, bytes, str, Path]) -> Dict[str, Any]:
        """
        Extract table from an image and return as HTML.

        Args:
            image: PIL Image, bytes, file path, or Path object

        Returns:
            Dictionary with:
                - html: HTML representation of extracted table
                - confidence: Confidence score (0-1)
                - raw_response: Full API response
        """
        try:
            from agentic_doc.parse import parse

            # Convert image to bytes if needed
            if isinstance(image, Image.Image):
                img_buffer = io.BytesIO()
                image.save(img_buffer, format="PNG")
                img_bytes = img_buffer.getvalue()
            elif isinstance(image, bytes):
                img_bytes = image
            elif isinstance(image, (str, Path)):
                with open(image, "rb") as f:
                    img_bytes = f.read()
            else:
                raise ValueError(f"Unsupported image type: {type(image)}")

            # Parse the image using agentic-doc
            results = parse(img_bytes)

            if not results:
                logger.warning("No results returned from LandingAI")
                return {
                    "html": "<table><tr><td>No table detected</td></tr></table>",
                    "confidence": 0.0,
                    "raw_response": None
                }

            # Get the first result
            result = results[0]

            # Extract tables from the parsed content
            html_tables = self._extract_tables_from_result(result)

            if not html_tables:
                # Fall back to markdown if no tables found
                html_content = self._markdown_to_html(result.markdown or "")
            else:
                html_content = "\n".join(html_tables)

            return {
                "html": html_content,
                "confidence": 0.95,  # agentic-doc doesn't provide confidence
                "raw_response": {
                    "markdown": result.markdown,
                    "chunks": len(result.chunks) if result.chunks else 0
                }
            }

        except ImportError:
            logger.error("agentic-doc not installed. Run: pip install agentic-doc")
            raise
        except Exception as e:
            logger.error(f"Error extracting table: {e}")
            return {
                "html": f"<table><tr><td>Error: {str(e)}</td></tr></table>",
                "confidence": 0.0,
                "raw_response": {"error": str(e)}
            }

    async def extract_table_async(self, image: Union[Image.Image, bytes, str, Path]) -> Dict[str, Any]:
        """
        Async version of extract_table.

        Note: agentic-doc is synchronous, so this wraps the sync call.
        """
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, self.extract_table, image
        )

    def extract_tables_from_pdf(
        self,
        pdf_path: Union[str, Path],
        page_numbers: Optional[List[int]] = None
    ) -> List[TableExtractionResult]:
        """
        Extract tables from specific pages of a PDF.

        Args:
            pdf_path: Path to the PDF file
            page_numbers: List of 1-indexed page numbers to extract.
                         If None, extracts from all pages.

        Returns:
            List of TableExtractionResult objects
        """
        try:
            from agentic_doc.parse import parse
            import fitz  # PyMuPDF

            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF not found: {pdf_path}")

            results = []
            doc = fitz.open(pdf_path)

            pages_to_process = page_numbers or list(range(1, len(doc) + 1))

            for page_num in pages_to_process:
                if page_num < 1 or page_num > len(doc):
                    logger.warning(f"Page {page_num} out of range, skipping")
                    continue

                # Render page at 7x zoom (504 DPI) for better table detection
                page = doc[page_num - 1]  # 0-indexed
                mat = fitz.Matrix(7, 7)  # 7x zoom
                pix = page.get_pixmap(matrix=mat)

                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # Extract table
                extraction = self.extract_table(img)

                results.append(TableExtractionResult(
                    html=extraction["html"],
                    confidence=extraction["confidence"],
                    page_number=page_num,
                    raw_response=extraction.get("raw_response")
                ))

            doc.close()
            return results

        except Exception as e:
            logger.error(f"Error extracting tables from PDF: {e}")
            raise

    def _extract_tables_from_result(self, result) -> List[str]:
        """
        Extract HTML tables from a ParsedDocument result.

        Args:
            result: ParsedDocument from agentic-doc

        Returns:
            List of HTML table strings
        """
        tables = []

        # Check chunks for table content
        if hasattr(result, 'chunks') and result.chunks:
            for chunk in result.chunks:
                if hasattr(chunk, 'chunk_type') and chunk.chunk_type == 'table':
                    if hasattr(chunk, 'html') and chunk.html:
                        tables.append(chunk.html)
                    elif hasattr(chunk, 'markdown') and chunk.markdown:
                        tables.append(self._markdown_to_html(chunk.markdown))

        # If no tables found in chunks, try to extract from markdown
        if not tables and hasattr(result, 'markdown') and result.markdown:
            # Look for markdown tables in the content
            md_tables = self._extract_markdown_tables(result.markdown)
            for md_table in md_tables:
                tables.append(self._markdown_to_html(md_table))

        return tables

    def _extract_markdown_tables(self, markdown: str) -> List[str]:
        """
        Extract markdown tables from content.

        Args:
            markdown: Markdown content

        Returns:
            List of markdown table strings
        """
        tables = []
        lines = markdown.split('\n')
        current_table = []
        in_table = False

        for line in lines:
            # Check if line looks like a table row
            if '|' in line and line.strip().startswith('|'):
                in_table = True
                current_table.append(line)
            elif in_table:
                if line.strip() == '' or not '|' in line:
                    # End of table
                    if current_table:
                        tables.append('\n'.join(current_table))
                        current_table = []
                    in_table = False
                else:
                    current_table.append(line)

        # Don't forget last table if document ends with table
        if current_table:
            tables.append('\n'.join(current_table))

        return tables

    def _markdown_to_html(self, markdown: str) -> str:
        """
        Convert markdown table to HTML.

        Args:
            markdown: Markdown table string

        Returns:
            HTML table string
        """
        lines = [l.strip() for l in markdown.strip().split('\n') if l.strip()]

        if not lines:
            return "<table><tr><td></td></tr></table>"

        html_rows = []
        is_header = True

        for line in lines:
            # Skip separator lines (e.g., |---|---|)
            if set(line.replace('|', '').replace('-', '').replace(':', '').strip()) == set():
                is_header = False
                continue

            # Parse cells
            cells = [c.strip() for c in line.split('|')]
            # Remove empty first/last cells from | borders
            if cells and cells[0] == '':
                cells = cells[1:]
            if cells and cells[-1] == '':
                cells = cells[:-1]

            if is_header:
                row = '<tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>'
            else:
                row = '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'

            html_rows.append(row)

        return '<table>\n' + '\n'.join(html_rows) + '\n</table>'
