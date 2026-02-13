"""
SOA Page Detector v2 - Simplified detection returning only page numbers.

This is the HTML-First architecture version that only detects:
- Table page boundaries (start, end)
- Table category (MAIN_SOA, PK_SOA, etc.)
- Continuation relationships

All content extraction (visits, activities, footnotes) is deferred to
LandingAI HTML extraction + Claude interpretation.

Usage:
    from soa_analyzer.soa_page_detector import detect_soa_pages_v2

    result = detect_soa_pages_v2("/path/to/protocol.pdf")
    for soa in result["soaTables"]:
        print(f"SOA: pages {soa['pageStart']}-{soa['pageEnd']}")
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _clean_json(text: str) -> str:
    """Strip markdown code fences from LLM response."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def detect_soa_pages_v2(pdf_path: str, api_key: Optional[str] = None) -> dict:
    """
    Detect Schedule of Activities (SOA) tables in a protocol PDF.

    SIMPLIFIED VERSION (v2): Only returns page numbers and table categories.
    No visit/activity extraction - that's handled by LandingAI + Claude.

    Args:
        pdf_path: Path to the protocol PDF file
        api_key: Optional Gemini API key (falls back to GEMINI_API_KEY env var)

    Returns:
        dict with structure:
        {
            "totalSOAs": int,
            "soaTables": [
                {
                    "id": str,
                    "pageStart": int,
                    "pageEnd": int,
                    "tableCategory": str,  # MAIN_SOA, PK_SOA, PD_SOA, etc.
                    "isContinuation": bool,
                    "continuationOf": str|null
                }
            ]
        }

    Raises:
        FileNotFoundError: If PDF doesn't exist
        ValueError: If no API key available
        RuntimeError: If API call fails
    """
    # Validate PDF exists
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Get API key
    load_dotenv()
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("No API key provided. Set GEMINI_API_KEY env var or pass api_key param.")

    # Configure Gemini
    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-3-pro-preview")

    # Upload PDF
    logger.info(f"Uploading PDF to Gemini: {pdf_path}")
    uploaded = genai.upload_file(str(pdf_file))

    # Simplified SOA detection prompt - ONLY page numbers
    prompt = """Analyze this clinical trial protocol PDF and find ALL Schedule of Activities (SOA) tables.

## TASK

Find the PAGE NUMBERS where SOA tables are located. Do NOT extract table content - just locations.

## WHAT TO LOOK FOR

SOA tables typically:
- Have titles like "Schedule of Activities", "Schedule of Events", "Schedule of Assessments"
- Are large tables with visits/timepoints as columns and procedures/assessments as rows
- Have X marks or checkmarks indicating when activities occur
- May have footnotes below the table

Protocol may have multiple SOAs:
- MAIN_SOA: Main study schedule (most important)
- PK_SOA: Pharmacokinetic sampling
- PD_SOA: Pharmacodynamic assessments
- FOLLOW_UP: Follow-up period schedule
- OTHER: Any other schedule tables

## CONTINUATION DETECTION

Tables spanning multiple pages:
- Same table continued with "(Continued)" or "(Cont'd)" in title
- Assign same logical ID, mark as continuation
- Continuations have isContinuation: true and continuationOf pointing to parent

## OUTPUT FORMAT

Return ONLY JSON:
{
  "totalSOAs": <number of INDEPENDENT tables (not counting continuations)>,
  "soaTables": [
    {
      "id": "SOA-1",
      "pageStart": <first page number>,
      "pageEnd": <last page number including footnotes>,
      "tableCategory": "MAIN_SOA|PK_SOA|PD_SOA|FOLLOW_UP|OTHER",
      "isContinuation": false,
      "continuationOf": null
    },
    {
      "id": "SOA-1-cont",
      "pageStart": <page number>,
      "pageEnd": <page number>,
      "tableCategory": "MAIN_SOA",
      "isContinuation": true,
      "continuationOf": "SOA-1"
    }
  ]
}

IMPORTANT:
- Page numbers are 1-indexed (first page = 1)
- Include footnote pages in pageEnd
- Do NOT extract visits, activities, or footnote text
- Just find WHERE the tables are located

Now analyze the protocol and return the JSON with table locations."""

    try:
        logger.info("Calling Gemini for simplified SOA detection...")
        response = model.generate_content([uploaded, prompt])
        raw_text = response.text

        logger.debug(f"Raw Gemini response: {raw_text[:500]}...")
        results = json.loads(_clean_json(raw_text))

        # Post-process to ensure minimal required fields
        results = _post_process_v2(results)

        # Include Gemini file URI for downstream stages (Stage 2 Activity Expansion)
        results["geminiFileUri"] = uploaded.uri

        logger.info(f"Detection complete: {results.get('totalSOAs', 0)} SOAs found")
        return results


    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        logger.error(f"Raw response: {raw_text[:1000]}")
        raise RuntimeError(f"Failed to parse Gemini response as JSON: {e}")
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        raise RuntimeError(f"Gemini API call failed: {e}")


def _post_process_v2(results: dict) -> dict:
    """
    Post-process detection results to ensure minimal required fields.

    v2 is much simpler - just validate required fields exist.
    """
    if "soaTables" not in results:
        results["soaTables"] = []

    if "totalSOAs" not in results:
        # Count independent tables
        independent = [t for t in results["soaTables"] if not t.get("isContinuation")]
        results["totalSOAs"] = len(independent)

    for table in results.get("soaTables", []):
        # Ensure required fields with defaults
        table.setdefault("id", f"SOA-{results['soaTables'].index(table) + 1}")
        table.setdefault("pageStart", 1)
        table.setdefault("pageEnd", table.get("pageStart", 1))
        table.setdefault("tableCategory", "MAIN_SOA")
        table.setdefault("isContinuation", False)
        table.setdefault("continuationOf", None)

    return results


def get_merged_table_pages(detection_result: dict) -> list:
    """
    Get list of logical tables with their page ranges (continuations merged).

    Returns list of dicts with:
    - id: Primary table ID
    - pages: All pages (primary + continuations merged)
    - pageStart: First page
    - pageEnd: Last page
    - tableCategory: Category of the table
    """
    tables = detection_result.get("soaTables", [])

    # Build lookup
    table_lookup = {t["id"]: t for t in tables}

    # Group continuations with their parent
    continuation_groups = {}  # parent_id -> [continuation_ids]
    primary_tables = []

    for table in tables:
        if table.get("isContinuation"):
            parent_id = table.get("continuationOf")
            if parent_id:
                if parent_id not in continuation_groups:
                    continuation_groups[parent_id] = []
                continuation_groups[parent_id].append(table["id"])
        else:
            primary_tables.append(table["id"])

    merged = []
    processed_ids = set()

    for primary_id in primary_tables:
        if primary_id in processed_ids:
            continue

        primary = table_lookup.get(primary_id)
        if not primary:
            continue

        # Get all related tables
        continuation_ids = continuation_groups.get(primary_id, [])
        all_tables = [primary] + [table_lookup[cid] for cid in continuation_ids if cid in table_lookup]

        # Collect all pages
        all_pages = []
        for t in all_tables:
            for p in range(t.get("pageStart", 0), t.get("pageEnd", 0) + 1):
                if p not in all_pages:
                    all_pages.append(p)
        all_pages.sort()

        merged.append({
            "id": primary_id,
            "pages": all_pages,
            "pageStart": min(all_pages) if all_pages else 0,
            "pageEnd": max(all_pages) if all_pages else 0,
            "tableCategory": primary.get("tableCategory", "MAIN_SOA"),
        })

        processed_ids.add(primary_id)
        processed_ids.update(continuation_ids)

    # Add orphaned tables
    for table in tables:
        if table["id"] not in processed_ids:
            merged.append({
                "id": table["id"],
                "pages": list(range(table.get("pageStart", 0), table.get("pageEnd", 0) + 1)),
                "pageStart": table.get("pageStart", 0),
                "pageEnd": table.get("pageEnd", 0),
                "tableCategory": table.get("tableCategory", "MAIN_SOA"),
            })

    return merged


# CLI support
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python soa_page_detector.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"Detecting SOA tables in: {pdf_path}")

    try:
        result = detect_soa_pages_v2(pdf_path)

        print(f"\n=== Detection Results (v2 Simplified) ===")
        print(f"Total SOAs: {result.get('totalSOAs', 0)}")

        for table in result.get("soaTables", []):
            cont = " (continuation)" if table.get("isContinuation") else ""
            print(f"  {table['id']}: pages {table['pageStart']}-{table['pageEnd']} [{table['tableCategory']}]{cont}")

        print(f"\n=== Merged Page Ranges ===")
        merged = get_merged_table_pages(result)
        for m in merged:
            print(f"  {m['id']}: pages {m['pageStart']}-{m['pageEnd']} [{m['tableCategory']}]")

        print(f"\n=== Full JSON ===")
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
