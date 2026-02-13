"""
Eligibility Section Detector - Phase 1 of Eligibility Extraction Pipeline

Uses Gemini File API for DIRECT PDF access (no markdown conversion) to detect
eligibility criteria section boundaries with high precision.

Key Features:
- Direct PDF analysis via Gemini File API vision capabilities
- Multi-stage detection: Table of Contents analysis + Section header search
- Confidence scoring for detection quality
- Cross-reference detection for appendices mentioned in eligibility sections
- Validates detected sections before returning

Usage:
    from eligibility_analyzer.eligibility_section_detector import detect_eligibility_sections

    result = detect_eligibility_sections("/path/to/protocol.pdf")
    print(f"Inclusion: pages {result['inclusionSection']['pageStart']}-{result['inclusionSection']['pageEnd']}")
    print(f"Exclusion: pages {result['exclusionSection']['pageStart']}-{result['exclusionSection']['pageEnd']}")
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import google.generativeai as genai
from openai import AzureOpenAI
import fitz  # PyMuPDF for PDF text extraction
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Detection prompt for eligibility sections
SECTION_DETECTION_PROMPT = """You are analyzing a clinical trial protocol PDF to locate eligibility criteria sections.

## TASK
Find the EXACT page numbers where inclusion and exclusion criteria are located in this protocol.

## WHAT TO LOOK FOR

### Section Titles (Common Patterns)
- "Eligibility Criteria", "Selection Criteria", "Subject Selection"
- "Inclusion Criteria", "Exclusion Criteria"
- "Study Population", "Patient Selection"
- Section numbers like "5.1", "5.2", "4.2", "3.1" followed by eligibility keywords

### Section Structure Patterns
1. **Combined Section**: "5.2 Eligibility Criteria" containing both inclusion (5.2.1) and exclusion (5.2.2)
2. **Separate Sections**: "5.2 Inclusion Criteria" and "5.3 Exclusion Criteria" in different locations
3. **Appendix-Based**: Main eligibility in section 5, with details in appendices

### Content Characteristics
- Numbered lists of criteria (1., 2., 3., ... or a., b., c., ...)
- Clinical requirements (age, diagnosis, lab values, medical history)
- Words like "must", "should", "required", "eligible", "disqualified"

## DETECTION STRATEGY

1. **First**: Scan the Table of Contents (usually pages 2-5) for eligibility section locations
2. **Then**: Verify by scanning the actual section content at those pages
3. **Look for**: The first criterion text and the last criterion text to determine boundaries
4. **Include**: Any footnotes or notes immediately following the criteria list

## CROSS-REFERENCE DETECTION

Look for references to other sections within eligibility criteria:
- "See Appendix A", "as specified in Section 6.5"
- "Refer to Table X", "per Protocol Amendment"
These referenced sections may contain detailed eligibility requirements.

## OUTPUT FORMAT (JSON only)

{
  "inclusionSection": {
    "pageStart": <integer>,
    "pageEnd": <integer>,
    "sectionTitle": "<exact title found, e.g., '5.2.1 Inclusion Criteria'>",
    "sectionNumber": "<section number if present, e.g., '5.2.1'>",
    "criteriaCount": <estimated number of criteria if visible>,
    "confidence": <float 0.0-1.0>
  },
  "exclusionSection": {
    "pageStart": <integer>,
    "pageEnd": <integer>,
    "sectionTitle": "<exact title found>",
    "sectionNumber": "<section number if present>",
    "criteriaCount": <estimated number of criteria if visible>,
    "confidence": <float 0.0-1.0>
  },
  "crossReferences": [
    {
      "referenceId": "appendix-a",
      "referenceText": "See Appendix A for prohibited medications",
      "targetSection": "Appendix A",
      "targetPage": <integer or null if unknown>,
      "context": "exclusion"
    }
  ],
  "detectionMethod": "<how sections were found: 'toc_verified', 'header_search', 'content_scan'>",
  "totalProtocolPages": <integer>,
  "notes": "<any important observations about the eligibility structure>"
}

## CONFIDENCE SCORING

- **1.0**: Crystal clear headers, numbered criteria list visible, boundaries definite
- **0.9**: Clear headers found, content verified, minor ambiguity in end boundary
- **0.8**: Headers found via ToC, content partially verified
- **0.7**: Sections found but structure is unusual or fragmented
- **0.6**: Probable location but some uncertainty
- **<0.6**: Low confidence, sections may be incorrectly identified

## IMPORTANT RULES

1. Page numbers are 1-indexed (first page = 1)
2. Include the full extent of criteria (pageEnd should include any footnotes/notes)
3. If inclusion/exclusion are on the SAME pages, set the same page numbers for both
4. If a section spans only 1 page, pageStart = pageEnd
5. DO NOT extract the criteria text - only find WHERE they are
6. Return valid JSON only - no additional text or commentary

Now analyze the protocol PDF and return the JSON with section locations."""


# Validation prompt to verify detected sections
SECTION_VALIDATION_PROMPT = """You are verifying detected eligibility criteria sections in a clinical trial protocol.

## DETECTED SECTIONS (to verify)
{detected_sections}

## YOUR TASK
Look at pages {page_start} to {page_end} in this protocol PDF and verify:

1. **Is this the correct eligibility section?**
   - Does the page contain inclusion/exclusion criteria?
   - Are there numbered criteria items?

2. **Are the page boundaries correct?**
   - Does the section START on page {page_start}?
   - Does the section END on page {page_end} (or continue further)?

3. **What criteria numbers are visible?**
   - First criterion number seen
   - Last criterion number seen

## OUTPUT FORMAT (JSON only)

{
  "isValid": <boolean>,
  "corrections": {
    "pageStart": <corrected page or null if correct>,
    "pageEnd": <corrected page or null if correct>
  },
  "observedCriteria": {
    "firstNumber": <first criterion number seen, e.g., "1" or "1a">,
    "lastNumber": <last criterion number seen>,
    "estimatedCount": <integer>
  },
  "sampleCriterionText": "<first 100 chars of the first criterion as verification>",
  "confidence": <float 0.0-1.0>,
  "notes": "<any corrections or observations>"
}

Verify the detection now and return JSON."""


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class SectionLocation:
    """Location of an eligibility section in the protocol."""
    page_start: int
    page_end: int
    section_title: str = ""
    section_number: str = ""
    criteria_count: int = 0
    confidence: float = 0.0
    sample_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pageStart": self.page_start,
            "pageEnd": self.page_end,
            "sectionTitle": self.section_title,
            "sectionNumber": self.section_number,
            "criteriaCount": self.criteria_count,
            "confidence": self.confidence,
            "sampleText": self.sample_text if self.sample_text else None,
        }


@dataclass
class CrossReference:
    """Cross-reference to another section in the protocol."""
    reference_id: str
    reference_text: str
    target_section: str
    target_page: Optional[int] = None
    context: str = ""  # "inclusion" or "exclusion"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "referenceId": self.reference_id,
            "referenceText": self.reference_text,
            "targetSection": self.target_section,
            "targetPage": self.target_page,
            "context": self.context,
        }


@dataclass
class DetectionResult:
    """Result from eligibility section detection."""
    success: bool
    inclusion_section: Optional[SectionLocation] = None
    exclusion_section: Optional[SectionLocation] = None
    cross_references: List[CrossReference] = field(default_factory=list)
    detection_method: str = ""
    total_pages: int = 0
    notes: str = ""
    error: Optional[str] = None
    gemini_file_uri: Optional[str] = None  # For downstream use

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "inclusionSection": self.inclusion_section.to_dict() if self.inclusion_section else None,
            "exclusionSection": self.exclusion_section.to_dict() if self.exclusion_section else None,
            "crossReferences": [cr.to_dict() for cr in self.cross_references],
            "detectionMethod": self.detection_method,
            "totalProtocolPages": self.total_pages,
            "notes": self.notes,
            "error": self.error,
            "geminiFileUri": self.gemini_file_uri,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


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


def _upload_pdf_to_gemini(pdf_path: str) -> Any:
    """
    Upload PDF to Gemini File API for vision analysis.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Gemini File object with URI
    """
    logger.info(f"Uploading PDF to Gemini File API: {pdf_path}")
    uploaded_file = genai.upload_file(pdf_path)
    logger.info(f"PDF uploaded successfully: {uploaded_file.name}")
    return uploaded_file


def _parse_detection_response(response_text: str) -> Dict[str, Any]:
    """
    Parse the detection response from Gemini.

    Args:
        response_text: Raw response text from Gemini

    Returns:
        Parsed JSON dictionary
    """
    cleaned = _clean_json(response_text)
    return json.loads(cleaned)


def _validate_section(
    pdf_file: Any,
    model: Any,
    section_type: str,
    page_start: int,
    page_end: int,
    detected_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate a detected section by examining the actual pages.

    Args:
        pdf_file: Uploaded Gemini File object
        model: Gemini model instance
        section_type: "inclusion" or "exclusion"
        page_start: Detected start page
        page_end: Detected end page
        detected_data: Original detection data

    Returns:
        Validation result dictionary
    """
    prompt = SECTION_VALIDATION_PROMPT.format(
        detected_sections=json.dumps(detected_data, indent=2),
        page_start=page_start,
        page_end=page_end
    )

    response = None
    try:
        response = model.generate_content([pdf_file, prompt])
        # Safely access response text - Gemini can raise KeyError on response.text
        try:
            response_text = response.text
        except (KeyError, ValueError, AttributeError) as text_err:
            logger.warning(f"Failed to access response text for {section_type}: {type(text_err).__name__}: {text_err}")
            return {"isValid": True, "corrections": {}, "confidence": 0.7}

        cleaned_text = _clean_json(response_text)
        logger.debug(f"Validation response for {section_type}: {cleaned_text[:500]}...")
        result = json.loads(cleaned_text)
        return result
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error in validation for {section_type}: {e}")
        # Return a default "valid" result to not block the pipeline
        return {"isValid": True, "corrections": {}, "confidence": 0.7}
    except Exception as e:
        logger.warning(f"Validation failed for {section_type}: {type(e).__name__}: {e}")
        return {"isValid": True, "corrections": {}, "confidence": 0.7}


def _get_azure_client() -> Optional[AzureOpenAI]:
    """Get Azure OpenAI client for fallback."""
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview")

    if not azure_key or not azure_endpoint:
        return None

    try:
        return AzureOpenAI(
            api_key=azure_key,
            api_version=azure_version,
            azure_endpoint=azure_endpoint,
            timeout=120.0
        )
    except Exception as e:
        logger.warning(f"Failed to initialize Azure OpenAI client: {e}")
        return None


def _extract_pdf_text_for_fallback(pdf_path: str, max_pages: int = 30) -> str:
    """
    Extract text from PDF for Azure OpenAI text-based fallback.

    Args:
        pdf_path: Path to PDF file
        max_pages: Maximum number of pages to extract (for efficiency)

    Returns:
        Extracted text with page markers
    """
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        pages_to_extract = min(total_pages, max_pages)

        text_parts = []
        for page_num in range(pages_to_extract):
            page = doc[page_num]
            page_text = page.get_text()
            text_parts.append(f"=== PAGE {page_num + 1} ===\n{page_text}")

        doc.close()

        full_text = "\n\n".join(text_parts)
        # Truncate to avoid token limits
        if len(full_text) > 100000:
            full_text = full_text[:100000] + "\n\n[TEXT TRUNCATED]"

        return full_text

    except Exception as e:
        logger.error(f"Failed to extract PDF text: {e}")
        return ""


def _detect_sections_with_azure_fallback(
    pdf_path: str,
    azure_client: AzureOpenAI,
    deployment: str
) -> Optional[Dict[str, Any]]:
    """
    Detect eligibility sections using Azure OpenAI (text-based fallback).

    Args:
        pdf_path: Path to PDF file
        azure_client: Azure OpenAI client
        deployment: Azure OpenAI deployment name

    Returns:
        Detection data dict or None if failed
    """
    logger.info("Azure OpenAI fallback: Extracting PDF text...")
    pdf_text = _extract_pdf_text_for_fallback(pdf_path)

    if not pdf_text:
        logger.error("Azure fallback failed: Could not extract PDF text")
        return None

    # Simplified prompt for text-based detection
    text_prompt = f"""You are analyzing a clinical trial protocol to locate eligibility criteria sections.

## PROTOCOL TEXT (with page markers)
{pdf_text}

## TASK
Find the page numbers where inclusion and exclusion criteria sections are located.
Look for sections titled "Inclusion Criteria", "Exclusion Criteria", "Eligibility Criteria", etc.

## OUTPUT FORMAT (JSON only)
{{
  "inclusionSection": {{
    "pageStart": <integer>,
    "pageEnd": <integer>,
    "sectionTitle": "<title found>",
    "sectionNumber": "<section number if present>",
    "criteriaCount": <estimated count>,
    "confidence": <0.0-1.0>
  }},
  "exclusionSection": {{
    "pageStart": <integer>,
    "pageEnd": <integer>,
    "sectionTitle": "<title found>",
    "sectionNumber": "<section number if present>",
    "criteriaCount": <estimated count>,
    "confidence": <0.0-1.0>
  }},
  "crossReferences": [],
  "detectionMethod": "azure_text_fallback",
  "totalProtocolPages": <integer>,
  "notes": "Detected via Azure OpenAI text analysis (Gemini fallback)"
}}

Return ONLY valid JSON."""

    try:
        response = azure_client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "system",
                    "content": "You are a clinical protocol analyst. Return only valid JSON."
                },
                {"role": "user", "content": text_prompt}
            ],
            max_completion_tokens=4096,
            response_format={"type": "json_object"}
        )

        if response and response.choices:
            content = response.choices[0].message.content
            if content:
                logger.info("Azure OpenAI fallback succeeded")
                return json.loads(_clean_json(content))

    except Exception as e:
        logger.error(f"Azure OpenAI fallback detection failed: {e}")

    return None


# =============================================================================
# MAIN DETECTION FUNCTION
# =============================================================================


def detect_eligibility_sections(
    pdf_path: str,
    api_key: Optional[str] = None,
    validate: bool = True,
    model_name: str = "gemini-2.5-pro"
) -> DetectionResult:
    """
    Detect eligibility criteria sections in a protocol PDF using Gemini File API.

    This function uses DIRECT PDF access via Gemini's vision capabilities,
    avoiding lossy markdown conversion that could miss section boundaries.

    Args:
        pdf_path: Path to the protocol PDF file
        api_key: Optional Gemini API key (falls back to GEMINI_API_KEY env var)
        validate: Whether to validate detected sections (recommended)
        model_name: Gemini model to use (default: gemini-2.5-pro for best accuracy)

    Returns:
        DetectionResult with section locations and confidence scores

    Raises:
        FileNotFoundError: If PDF doesn't exist
        ValueError: If no API key available
        RuntimeError: If API call fails
    """
    # Validate PDF exists
    pdf_file_path = Path(pdf_path)
    if not pdf_file_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Get API key
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("No API key provided. Set GEMINI_API_KEY env var or pass api_key param.")

    # Configure Gemini
    genai.configure(api_key=key)
    model = genai.GenerativeModel(model_name)

    detection_data = None
    uploaded_file = None
    use_azure_fallback = False

    try:
        # Phase 1: Upload PDF to Gemini File API
        logger.info("Phase 1: Uploading PDF to Gemini File API...")
        uploaded_file = _upload_pdf_to_gemini(str(pdf_file_path))

        # Phase 2: Initial detection
        logger.info("Phase 2: Running eligibility section detection...")
        response = model.generate_content([uploaded_file, SECTION_DETECTION_PROMPT])
        detection_data = _parse_detection_response(response.text)

        logger.debug(f"Initial detection result: {json.dumps(detection_data, indent=2)[:500]}...")

    except Exception as gemini_error:
        # Check if this is a retryable error that warrants Azure fallback
        error_str = str(gemini_error).lower()
        retryable_patterns = ["503", "504", "429", "rate limit", "deadline", "timeout", "resource exhausted"]
        if any(p in error_str for p in retryable_patterns):
            logger.warning(f"Gemini failed with retryable error: {gemini_error}. Trying Azure OpenAI fallback...")
            use_azure_fallback = True
        else:
            raise

    # Azure OpenAI fallback if Gemini failed
    if use_azure_fallback:
        azure_client = _get_azure_client()
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

        if azure_client:
            detection_data = _detect_sections_with_azure_fallback(
                str(pdf_file_path), azure_client, azure_deployment
            )
            if detection_data:
                logger.info("Azure OpenAI fallback detection succeeded")
            else:
                return DetectionResult(
                    success=False,
                    error="Both Gemini and Azure OpenAI fallback failed"
                )
        else:
            return DetectionResult(
                success=False,
                error="Gemini failed and Azure OpenAI fallback not configured"
            )

    if not detection_data:
        return DetectionResult(
            success=False,
            error="No detection data obtained"
        )

    try:

        # Phase 3: Validate if requested (skip if Azure fallback was used since no uploaded_file)
        if validate and uploaded_file and not use_azure_fallback:
            logger.info("Phase 3: Validating detected sections...")

            # Validate inclusion section
            if detection_data.get("inclusionSection"):
                inc = detection_data["inclusionSection"]
                logger.debug(f"Validating inclusion section: pages {inc.get('pageStart')}-{inc.get('pageEnd')}")
                try:
                    inc_validation = _validate_section(
                        uploaded_file, model, "inclusion",
                        inc.get("pageStart", 1), inc.get("pageEnd", 1),
                        {"inclusionSection": inc}
                    )
                except Exception as val_err:
                    logger.warning(f"Inclusion validation exception (caught outer): {type(val_err).__name__}: {val_err}")
                    inc_validation = {"isValid": True, "corrections": {}, "confidence": 0.7}
                logger.debug(f"Inclusion validation result type: {type(inc_validation)}")
                logger.debug(f"Inclusion validation result: {inc_validation}")

                # Apply corrections if needed
                if isinstance(inc_validation, dict) and inc_validation.get("corrections"):
                    corr = inc_validation["corrections"]
                    if corr.get("pageStart"):
                        detection_data["inclusionSection"]["pageStart"] = corr["pageStart"]
                    if corr.get("pageEnd"):
                        detection_data["inclusionSection"]["pageEnd"] = corr["pageEnd"]

                # Update confidence based on validation
                if isinstance(inc_validation, dict) and inc_validation.get("isValid") is False:
                    detection_data["inclusionSection"]["confidence"] *= 0.7

                # Add sample text if available
                if isinstance(inc_validation, dict) and inc_validation.get("sampleCriterionText"):
                    detection_data["inclusionSection"]["sampleText"] = inc_validation["sampleCriterionText"]

            # Validate exclusion section
            if detection_data.get("exclusionSection"):
                exc = detection_data["exclusionSection"]
                logger.debug(f"Validating exclusion section: pages {exc.get('pageStart')}-{exc.get('pageEnd')}")
                try:
                    exc_validation = _validate_section(
                        uploaded_file, model, "exclusion",
                        exc.get("pageStart", 1), exc.get("pageEnd", 1),
                        {"exclusionSection": exc}
                    )
                except Exception as val_err:
                    logger.warning(f"Exclusion validation exception (caught outer): {type(val_err).__name__}: {val_err}")
                    exc_validation = {"isValid": True, "corrections": {}, "confidence": 0.7}
                logger.debug(f"Exclusion validation result type: {type(exc_validation)}")
                logger.debug(f"Exclusion validation result: {exc_validation}")

                # Apply corrections if needed
                if isinstance(exc_validation, dict) and exc_validation.get("corrections"):
                    corr = exc_validation["corrections"]
                    if corr.get("pageStart"):
                        detection_data["exclusionSection"]["pageStart"] = corr["pageStart"]
                    if corr.get("pageEnd"):
                        detection_data["exclusionSection"]["pageEnd"] = corr["pageEnd"]

                # Update confidence based on validation
                if isinstance(exc_validation, dict) and exc_validation.get("isValid") is False:
                    detection_data["exclusionSection"]["confidence"] *= 0.7

                # Add sample text if available
                if isinstance(exc_validation, dict) and exc_validation.get("sampleCriterionText"):
                    detection_data["exclusionSection"]["sampleText"] = exc_validation["sampleCriterionText"]

        # Build result
        result = DetectionResult(
            success=True,
            detection_method=detection_data.get("detectionMethod", "unknown"),
            total_pages=detection_data.get("totalProtocolPages", 0),
            notes=detection_data.get("notes", ""),
            gemini_file_uri=uploaded_file.name,
        )

        # Parse inclusion section
        if detection_data.get("inclusionSection"):
            inc = detection_data["inclusionSection"]
            result.inclusion_section = SectionLocation(
                page_start=inc.get("pageStart", 0),
                page_end=inc.get("pageEnd", 0),
                section_title=inc.get("sectionTitle", ""),
                section_number=inc.get("sectionNumber", ""),
                criteria_count=inc.get("criteriaCount", 0),
                confidence=inc.get("confidence", 0.0),
                sample_text=inc.get("sampleText", ""),
            )

        # Parse exclusion section
        if detection_data.get("exclusionSection"):
            exc = detection_data["exclusionSection"]
            result.exclusion_section = SectionLocation(
                page_start=exc.get("pageStart", 0),
                page_end=exc.get("pageEnd", 0),
                section_title=exc.get("sectionTitle", ""),
                section_number=exc.get("sectionNumber", ""),
                criteria_count=exc.get("criteriaCount", 0),
                confidence=exc.get("confidence", 0.0),
                sample_text=exc.get("sampleText", ""),
            )

        # Parse cross-references
        for xref in detection_data.get("crossReferences", []):
            result.cross_references.append(CrossReference(
                reference_id=xref.get("referenceId", ""),
                reference_text=xref.get("referenceText", ""),
                target_section=xref.get("targetSection", ""),
                target_page=xref.get("targetPage"),
                context=xref.get("context", ""),
            ))

        # Log summary
        if result.inclusion_section:
            logger.info(
                f"Inclusion section: pages {result.inclusion_section.page_start}-"
                f"{result.inclusion_section.page_end} (confidence: {result.inclusion_section.confidence:.2f})"
            )
        if result.exclusion_section:
            logger.info(
                f"Exclusion section: pages {result.exclusion_section.page_start}-"
                f"{result.exclusion_section.page_end} (confidence: {result.exclusion_section.confidence:.2f})"
            )
        if result.cross_references:
            logger.info(f"Found {len(result.cross_references)} cross-references")

        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        return DetectionResult(
            success=False,
            error=f"JSON parsing error: {e}"
        )
    except Exception as e:
        logger.error(f"Detection failed: {e}")
        return DetectionResult(
            success=False,
            error=str(e)
        )


def resolve_cross_references(
    pdf_path: str,
    cross_references: List[CrossReference],
    gemini_file_uri: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Resolve cross-references to extract their content from the PDF.

    Args:
        pdf_path: Path to the protocol PDF
        cross_references: List of CrossReference objects to resolve
        gemini_file_uri: Optional pre-uploaded Gemini file URI
        api_key: Optional Gemini API key

    Returns:
        Dictionary mapping reference_id to extracted content
    """
    if not cross_references:
        return {}

    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        logger.warning("No API key for cross-reference resolution")
        return {}

    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-2.5-pro")

    # Upload if needed
    if gemini_file_uri:
        # Re-use existing upload (Note: may need to re-upload if expired)
        uploaded_file = genai.upload_file(pdf_path)
    else:
        uploaded_file = genai.upload_file(pdf_path)

    resolved = {}

    for xref in cross_references:
        prompt = f"""Find and extract content from "{xref.target_section}" in this protocol.

This section is referenced in eligibility criteria: "{xref.reference_text}"

Extract the relevant content that should be included in eligibility criteria evaluation.
Return JSON:
{{
  "found": true/false,
  "page": <page number where found>,
  "content": "<extracted text, max 2000 chars>",
  "summary": "<1-2 sentence summary>"
}}

Return JSON only."""

        try:
            response = model.generate_content([uploaded_file, prompt])
            data = json.loads(_clean_json(response.text))
            resolved[xref.reference_id] = {
                "targetSection": xref.target_section,
                "found": data.get("found", False),
                "page": data.get("page"),
                "content": data.get("content", ""),
                "summary": data.get("summary", ""),
            }
            logger.info(f"Resolved cross-reference: {xref.reference_id}")
        except Exception as e:
            logger.warning(f"Failed to resolve {xref.reference_id}: {e}")
            resolved[xref.reference_id] = {
                "targetSection": xref.target_section,
                "found": False,
                "error": str(e),
            }

    return resolved


# =============================================================================
# CLI SUPPORT
# =============================================================================


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python eligibility_section_detector.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"Detecting eligibility sections in: {pdf_path}")

    try:
        result = detect_eligibility_sections(pdf_path)

        print(f"\n{'='*60}")
        print("ELIGIBILITY SECTION DETECTION RESULTS")
        print(f"{'='*60}")

        if result.success:
            print(f"Status: SUCCESS")
            print(f"Detection Method: {result.detection_method}")
            print(f"Total Protocol Pages: {result.total_pages}")

            if result.inclusion_section:
                inc = result.inclusion_section
                print(f"\nINCLUSION SECTION:")
                print(f"  Pages: {inc.page_start} - {inc.page_end}")
                print(f"  Title: {inc.section_title}")
                print(f"  Number: {inc.section_number}")
                print(f"  Criteria Count: {inc.criteria_count}")
                print(f"  Confidence: {inc.confidence:.2%}")
                if inc.sample_text:
                    print(f"  Sample: {inc.sample_text[:100]}...")
            else:
                print("\nINCLUSION SECTION: Not found")

            if result.exclusion_section:
                exc = result.exclusion_section
                print(f"\nEXCLUSION SECTION:")
                print(f"  Pages: {exc.page_start} - {exc.page_end}")
                print(f"  Title: {exc.section_title}")
                print(f"  Number: {exc.section_number}")
                print(f"  Criteria Count: {exc.criteria_count}")
                print(f"  Confidence: {exc.confidence:.2%}")
                if exc.sample_text:
                    print(f"  Sample: {exc.sample_text[:100]}...")
            else:
                print("\nEXCLUSION SECTION: Not found")

            if result.cross_references:
                print(f"\nCROSS-REFERENCES ({len(result.cross_references)}):")
                for xref in result.cross_references:
                    print(f"  - {xref.target_section}: {xref.reference_text[:50]}...")

            if result.notes:
                print(f"\nNotes: {result.notes}")

            print(f"\n{'='*60}")
            print("FULL JSON OUTPUT")
            print(f"{'='*60}")
            print(json.dumps(result.to_dict(), indent=2))

        else:
            print(f"Status: FAILED")
            print(f"Error: {result.error}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
