"""Gemini Vision Table Extraction Adapter for SOA tables"""
import os
import logging
import io
from typing import Dict, Any, Optional
from PIL import Image

import google.generativeai as genai

logger = logging.getLogger(__name__)


class GeminiTableAdapter:
    """
    Adapter for extracting tables from images using Gemini Vision.

    This is an alternative to LandingAI when it fails to extract complete tables.
    Gemini has strong table understanding capabilities.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.0-flash"):
        """
        Initialize Gemini table adapter.

        Args:
            api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
            model_name: Gemini model to use (default: gemini-2.0-flash for speed)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model_name)
        self.logger = logging.getLogger(__name__)

    def extract_table(self, image: Image.Image) -> Dict[str, Any]:
        """
        Extract table structure from image using Gemini Vision.

        Args:
            image: PIL Image of the table

        Returns:
            Dictionary with:
            - 'html': HTML string of the table
            - 'markdown': Markdown string (alternative format)
            - 'text': Plain text (fallback)
        """
        try:
            # Create the prompt for table extraction
            prompt = """Extract the table from this image and convert it to HTML format.

IMPORTANT INSTRUCTIONS:
1. Extract EVERY row from the table - do not skip any rows
2. Preserve the exact text in each cell, including any superscript markers (a, b, c, 1, 2, etc.)
3. For cells with checkmarks, X marks, or bullets, use "X" as the value
4. For empty cells, use an empty <td></td>
5. Preserve the table structure including any merged cells (use colspan/rowspan)
6. Include ALL activities/rows, even if some cells contain redacted/blacked-out content
7. For redacted content, use "[REDACTED]" as placeholder

Output ONLY the HTML table, nothing else. Start with <table> and end with </table>.

Example format:
<table>
<tr><th>Activity</th><th>Visit 1</th><th>Visit 2</th></tr>
<tr><td>Informed Consent</td><td>X</td><td></td></tr>
<tr><td>Physical Exam</td><td>X</td><td>X</td></tr>
</table>
"""

            # Generate content using Gemini Vision
            response = self.model.generate_content([prompt, image])

            if not response.text:
                logger.warning("Gemini returned empty response")
                return {
                    "html": "<table><tr><td>No table detected</td></tr></table>",
                    "markdown": "",
                    "text": ""
                }

            # Extract HTML from response
            html = self._extract_html_from_response(response.text)

            return {
                "html": html,
                "markdown": "",  # Could convert HTML to markdown if needed
                "text": response.text
            }

        except Exception as e:
            logger.error(f"Gemini table extraction failed: {e}")
            return {
                "html": f"<table><tr><td>Error: {str(e)}</td></tr></table>",
                "markdown": "",
                "text": ""
            }

    def _extract_html_from_response(self, text: str) -> str:
        """Extract HTML table from Gemini response."""
        # Try to find HTML table in the response
        import re

        # Look for table tags
        match = re.search(r'<table[^>]*>.*?</table>', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(0)

        # If no table tags, try to wrap the content
        if '<tr>' in text.lower():
            return f"<table>{text}</table>"

        # Return as-is if it looks like HTML
        if '<' in text and '>' in text:
            return text

        # Convert plain text to simple table
        return f"<table><tr><td>{text}</td></tr></table>"

    async def extract_table_async(self, image: Image.Image) -> Dict[str, Any]:
        """Async version (calls sync for now)"""
        return self.extract_table(image)
