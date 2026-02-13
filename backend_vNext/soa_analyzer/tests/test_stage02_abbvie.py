"""
Standalone Test for Stage 02: Activity Expansion

Tests the enhanced Activity Expansion module with the Abbvie protocol.
Uses existing stage01 results and extraction outputs.

Run with:
    cd backend_vNext
    source venv/bin/activate
    PYTHONPATH=. python soa_analyzer/tests/test_stage02_abbvie.py
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# =============================================================================
# PATH SETUP - MUST BE BEFORE ANY SOA_ANALYZER IMPORTS
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Add .archive/soa_schedule_analyzer_agent for adapters module
# This MUST be done BEFORE any soa_analyzer imports
ARCHIVE_PATH = PROJECT_ROOT.parent / ".archive" / "soa_schedule_analyzer_agent"
if ARCHIVE_PATH.exists():
    sys.path.insert(0, str(ARCHIVE_PATH))
    print(f"Added adapters path: {ARCHIVE_PATH}")
else:
    print(f"WARNING: Archive path not found: {ARCHIVE_PATH}")

# =============================================================================
# NOW SAFE TO IMPORT FROM SOA_ANALYZER
# =============================================================================

from soa_analyzer.interpretation.stage2_activity_expansion import (
    ActivityExpander,
    ExpansionConfig,
)

# Import gemini for PDF upload
try:
    import google.generativeai as genai
    from dotenv import load_dotenv
    load_dotenv()
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    GEMINI_AVAILABLE = True
except Exception as e:
    GEMINI_AVAILABLE = False
    print(f"Gemini not available: {e}")


async def upload_pdf_to_gemini(pdf_path: str) -> str:
    """Upload PDF to Gemini Files API."""
    if not GEMINI_AVAILABLE:
        raise RuntimeError("Gemini API not available")

    file = genai.upload_file(pdf_path, mime_type="application/pdf")
    return file.uri


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Abbvie protocol paths
ABBVIE_PDF = Path("/Users/angshuman.deb/Demos/protocol-digitalization-vNext/nsclc_protocols/protocols/abbvie/NCT02264990_M14-359.pdf")
ABBVIE_SOA_OUTPUT = Path("/Users/angshuman.deb/Demos/protocol-digitalization-vNext/nsclc_protocols/protocols/abbvie/soa_output/20251207_215740")
ABBVIE_EXTRACTION = Path("/Users/angshuman.deb/Demos/protocol-digitalization-vNext/nsclc_protocols/protocols/abbvie/extraction_output/20251207_210231/NCT02264990_M14-359_usdm_4.0.json")

# Output directory
OUTPUT_DIR = Path("/Users/angshuman.deb/Demos/protocol-digitalization-vNext/backend_vNext/soa_analyzer/test_output")


def load_stage01_result() -> dict:
    """Load the Stage 01 result from previous run."""
    stage01_file = ABBVIE_SOA_OUTPUT / "interpretation_stages" / "stage01_result.json"
    if not stage01_file.exists():
        raise FileNotFoundError(f"Stage 01 result not found: {stage01_file}")

    with open(stage01_file) as f:
        return json.load(f)


def load_extraction_outputs() -> dict:
    """Load the extraction outputs (USDM JSON)."""
    if not ABBVIE_EXTRACTION.exists():
        raise FileNotFoundError(f"Extraction output not found: {ABBVIE_EXTRACTION}")

    with open(ABBVIE_EXTRACTION) as f:
        usdm_data = json.load(f)

    # Extract individual module outputs from domainSections
    extraction_outputs = {}
    domain_sections = usdm_data.get("domainSections", {})

    for module_name, module_data in domain_sections.items():
        if isinstance(module_data, dict):
            extraction_outputs[module_name] = module_data

    logger.info(f"Loaded extraction outputs: {list(extraction_outputs.keys())}")
    return extraction_outputs


def get_activities_from_stage01(stage01_result: dict) -> dict:
    """
    Create a USDM-like structure with activities from Stage 01 result.
    Stage 01 returns mappings with domain categorization.
    """
    # Stage 01 uses "mappings" not "categorizedActivities"
    mappings = stage01_result.get("mappings", [])

    if not mappings:
        logger.warning("No mappings in stage01 result")
        return {"studyVersion": [{"activities": []}]}

    # Convert mappings to activity format expected by Stage 02
    activities = []
    for mapping in mappings:
        activity = {
            "id": mapping.get("activityId"),
            "name": mapping.get("activityName"),
            "cdashDomain": mapping.get("cdashDomain"),
            "cdiscCode": mapping.get("cdiscCode"),
            "cdiscDecode": mapping.get("cdiscDecode"),
            "confidence": mapping.get("confidence", 0.0),
            "category": mapping.get("category"),
        }
        activities.append(activity)

    logger.info(f"Converted {len(activities)} mappings to activity format")
    return {
        "studyVersion": [{"activities": activities}]
    }


async def run_stage02_test():
    """Run Stage 02 Activity Expansion test."""
    logger.info("=" * 60)
    logger.info("Stage 02 Activity Expansion Test - Abbvie Protocol")
    logger.info("=" * 60)

    # 1. Load Stage 01 result
    logger.info("\n[1] Loading Stage 01 result...")
    stage01_result = load_stage01_result()
    logger.info(f"    Loaded {len(stage01_result.get('mappings', []))} mappings from Stage 01")

    # 2. Load extraction outputs
    logger.info("\n[2] Loading extraction outputs...")
    extraction_outputs = load_extraction_outputs()

    # 3. Upload PDF to Gemini
    logger.info("\n[3] Uploading PDF to Gemini Files API...")
    gemini_file_uri = None
    try:
        gemini_file_uri = await upload_pdf_to_gemini(str(ABBVIE_PDF))
        logger.info(f"    Uploaded: {gemini_file_uri}")
    except Exception as e:
        logger.warning(f"    Failed to upload PDF: {e}")
        logger.warning("    Continuing without PDF context (JSON only)")

    # 4. Prepare USDM structure with activities
    logger.info("\n[4] Preparing activity input...")
    usdm_output = get_activities_from_stage01(stage01_result)
    activities = usdm_output.get("studyVersion", [{}])[0].get("activities", [])
    logger.info(f"    {len(activities)} activities ready for expansion")

    # Log activity names and domains
    for act in activities[:10]:  # First 10
        logger.info(f"      - {act.get('name', 'N/A')} ({act.get('cdashDomain', 'N/A')})")
    if len(activities) > 10:
        logger.info(f"      ... and {len(activities) - 10} more")

    # 5. Run Activity Expansion
    logger.info("\n[5] Running Stage 02 Activity Expansion...")
    start_time = datetime.now()

    expander = ActivityExpander()
    stage02_result = expander.expand_activities(
        usdm_output,
        extraction_outputs=extraction_outputs,
        gemini_file_uri=gemini_file_uri,
    )

    duration = (datetime.now() - start_time).total_seconds()

    # 6. Report results
    logger.info("\n[6] Stage 02 Results:")
    logger.info(f"    Duration: {duration:.2f}s")
    logger.info(f"    Activities Processed: {stage02_result.activities_processed}")
    logger.info(f"    Activities Expanded: {stage02_result.activities_expanded}")
    logger.info(f"    Activities Skipped: {stage02_result.skipped}")
    logger.info(f"    Components Created: {stage02_result.components_created}")
    logger.info(f"    LLM Expansions: {stage02_result.llm_expansions}")

    # 7. Log expansion details
    logger.info("\n[7] Expansion Details:")
    for expansion in stage02_result.expansions:
        logger.info(f"\n    === {expansion.parent_activity_name} ===")
        logger.info(f"    Components: {len(expansion.components)}")
        logger.info(f"    Confidence: {expansion.confidence:.2f}")
        rationale = expansion.rationale[:100] if expansion.rationale else "N/A"
        logger.info(f"    Rationale: {rationale}...")

        # First 5 components
        for comp in expansion.components[:5]:
            source = comp.source or "N/A"
            page = comp.page_number or "N/A"
            logger.info(f"      - {comp.name} (source={source}, page={page})")
        if len(expansion.components) > 5:
            logger.info(f"      ... and {len(expansion.components) - 5} more")

    # 8. Save result
    logger.info("\n[8] Saving result...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"stage02_test_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_file, "w") as f:
        json.dump(stage02_result.to_dict(), f, indent=2, default=str)

    logger.info(f"    Saved to: {output_file}")

    # 9. Summary comparison
    logger.info("\n[9] Summary Comparison:")
    logger.info(f"    BEFORE (previous run): 5 activities expanded, 46 components")
    logger.info(f"    AFTER  (this run):     {stage02_result.activities_expanded} activities expanded, {stage02_result.components_created} components")

    improvement = stage02_result.activities_expanded - 5
    if improvement > 0:
        logger.info(f"    IMPROVEMENT: +{improvement} activities expanded")
    elif improvement < 0:
        logger.info(f"    REGRESSION: {improvement} activities expanded")
    else:
        logger.info(f"    NO CHANGE in expansion count")

    logger.info("\n" + "=" * 60)
    logger.info("Test Complete!")
    logger.info("=" * 60)

    return stage02_result


if __name__ == "__main__":
    asyncio.run(run_stage02_test())
