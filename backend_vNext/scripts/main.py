#!/usr/bin/env python3
"""
Main extraction pipeline entry point.

Usage:
    python scripts/main.py --pdf /path/to/protocol.pdf [options]

Agent Configuration:
    Agents are controlled via config.yaml in the project root.
    Edit config.yaml to enable/disable specific agents.
    No runtime parameters needed for agent selection.

Options:
    --pdf PATH          Path to protocol PDF (required)
    --output DIR        Output directory (default: adjacent to PDF)
    --no-cache          Disable extraction cache
    --show-agents       Show agent configuration and exit
    --log-level LEVEL   Logging level (DEBUG, INFO, WARNING, ERROR)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.module_registry import (
    get_enabled_modules,
    get_modules_by_wave,
    print_agent_status,
    reload_agent_config,
    get_config_yaml_path,
)
from app.services.two_phase_extractor import TwoPhaseExtractor
from app.services.usdm_combiner import combine_agent_outputs
from app.utils.quality_checker import QualityChecker
from app.utils.extraction_cache import get_cache

# Configure logging
def setup_logging(level: str = "INFO"):
    """Configure logging with specified level."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    return logging.getLogger(__name__)


async def run_extraction(
    pdf_path: str,
    output_dir: str,
    use_cache: bool = True,
    model_name: str = None,
    logger: logging.Logger = None,
):
    """
    Run extraction for all enabled agents.

    Args:
        pdf_path: Path to protocol PDF
        output_dir: Output directory for results
        use_cache: Whether to use extraction cache
        model_name: LLM model to use (default from env)
        logger: Logger instance
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # Get model from environment or default
    if model_name is None:
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    # Get enabled modules
    enabled_modules = get_enabled_modules()
    modules_by_wave = get_modules_by_wave()

    if not enabled_modules:
        logger.error("No agents enabled in config.yaml!")
        return None

    logger.info("=" * 60)
    logger.info("PROTOCOL EXTRACTION PIPELINE")
    logger.info("=" * 60)
    logger.info(f"PDF: {Path(pdf_path).name}")
    logger.info(f"Model: {model_name}")
    logger.info(f"Cache: {'ENABLED' if use_cache else 'DISABLED'}")
    logger.info(f"Enabled Agents: {len(enabled_modules)}")
    logger.info(f"Config: {get_config_yaml_path()}")
    logger.info("=" * 60)

    # Show cache stats
    cache = get_cache()
    try:
        stats = cache.stats()
        if stats and 'total_entries' in stats:
            logger.info(f"Cache: {stats['total_entries']} entries, {stats.get('total_size_mb', 0)} MB")
    except Exception:
        pass  # Skip cache stats if not available

    # Upload PDF to Gemini
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

    logger.info("\nUploading PDF to Gemini File API...")
    upload_start = time.time()

    gemini_file = genai.upload_file(
        path=pdf_path,
        display_name=Path(pdf_path).name,
    )

    # Wait for processing
    while gemini_file.state.name == "PROCESSING":
        logger.info("Waiting for Gemini to process file...")
        time.sleep(2)
        gemini_file = genai.get_file(gemini_file.name)

    if gemini_file.state.name == "FAILED":
        raise RuntimeError(f"Gemini file processing failed: {gemini_file.name}")

    upload_duration = time.time() - upload_start
    logger.info(f"Upload complete in {upload_duration:.2f}s. URI: {gemini_file.uri}")

    # Results storage
    all_results = {}
    all_quality = {}
    extraction_start = time.time()
    protocol_id = Path(pdf_path).stem

    try:
        extractor = TwoPhaseExtractor()
        quality_checker = QualityChecker()

        # Concurrency limit for parallel extraction (avoid rate limits)
        max_parallel = 3
        semaphore = asyncio.Semaphore(max_parallel)

        async def extract_module(module):
            """Extract a single module with semaphore-based concurrency control."""
            async with semaphore:
                module_start = time.time()
                logger.info(f"[{module.module_id}] Starting extraction...")

                try:
                    result, quality, from_cache = await extractor.extract_with_cache(
                        module_id=module.module_id,
                        gemini_file_uri=gemini_file.uri,
                        protocol_id=protocol_id,
                        pdf_path=pdf_path,
                        model_name=model_name,
                        use_cache=use_cache,
                    )

                    module_duration = time.time() - module_start
                    cache_status = "CACHE HIT" if from_cache else "EXTRACTED"

                    logger.info(f"[{module.module_id}] {cache_status} in {module_duration:.2f}s")
                    logger.info(f"[{module.module_id}] Quality: {quality.overall_score:.1%}")

                    return module.module_id, result, {
                        "accuracy": quality.accuracy,
                        "completeness": quality.completeness,
                        "usdm_adherence": quality.usdm_adherence,
                        "provenance": quality.provenance,
                        "terminology": quality.terminology,
                        "overall": quality.overall_score,
                        "from_cache": from_cache,
                        "duration_seconds": module_duration,
                    }

                except Exception as e:
                    logger.error(f"[{module.module_id}] FAILED: {e}")
                    return module.module_id, None, {
                        "error": str(e),
                        "overall": 0.0,
                    }

        # Process by wave (waves run sequentially, agents within wave run in parallel)
        for wave_num in sorted(modules_by_wave.keys()):
            wave_modules = modules_by_wave[wave_num]
            logger.info(f"\n{'='*60}")
            logger.info(f"WAVE {wave_num}: Processing {len(wave_modules)} agents IN PARALLEL (max {max_parallel})")
            logger.info(f"{'='*60}")

            # Run all modules in this wave in parallel
            wave_start = time.time()
            tasks = [extract_module(module) for module in wave_modules]
            results = await asyncio.gather(*tasks)

            # Collect results
            for module_id, result, quality_info in results:
                all_results[module_id] = result
                all_quality[module_id] = quality_info

            wave_duration = time.time() - wave_start
            successful = sum(1 for _, r, _ in results if r is not None)
            logger.info(f"\nWave {wave_num} complete: {successful}/{len(wave_modules)} succeeded in {wave_duration:.2f}s")

        total_duration = time.time() - extraction_start

        # Save results
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save raw agent results (for debugging/reference)
        results_file = output_path / f"{protocol_id}_extraction_results.json"
        with open(results_file, 'w') as f:
            json.dump(all_results, f, indent=2, default=str)

        # Save quality report
        quality_file = output_path / f"{protocol_id}_quality_report.json"
        with open(quality_file, 'w') as f:
            json.dump({
                "protocol_id": protocol_id,
                "extraction_timestamp": datetime.now().isoformat(),
                "total_duration_seconds": total_duration,
                "model": model_name,
                "cache_enabled": use_cache,
                "agents": all_quality,
            }, f, indent=2)

        # Combine all agent outputs into USDM 4.0 compliant document
        logger.info("\nCombining agent outputs into USDM 4.0 document...")
        usdm_document = combine_agent_outputs(
            agent_results=all_results,
            pdf_path=pdf_path,
            model_name=model_name,
            quality_report=all_quality,
        )

        # Save USDM 4.0 document
        usdm_file = output_path / f"{protocol_id}_usdm_4.0.json"
        with open(usdm_file, 'w') as f:
            json.dump(usdm_document, f, indent=2, default=str)

        logger.info(f"USDM 4.0 document saved: {usdm_file}")

        # PDF Annotation: Highlight provenance in source PDF
        annotation_result = None
        try:
            from app.services.pdf_annotation import PDFAnnotatorService

            # Load annotation config
            import yaml
            config_path = get_config_yaml_path()
            with open(config_path, 'r') as f:
                full_config = yaml.safe_load(f)
            annotation_config = full_config.get("annotation", {})

            if annotation_config.get("enabled", True):
                logger.info("\n" + "-" * 60)
                logger.info("PDF ANNOTATION: Highlighting provenance in source PDF")
                logger.info("-" * 60)

                annotator = PDFAnnotatorService(config=annotation_config)
                annotation_result = annotator.annotate(
                    pdf_path=pdf_path,
                    usdm_json=usdm_document,
                    output_dir=output_path,
                    protocol_id=protocol_id
                )

                if annotation_result.success:
                    logger.info(f"Annotated PDF: {annotation_result.annotated_pdf_path}")
                    logger.info(f"Annotation Report: {annotation_result.report_path}")
                    logger.info(
                        f"Annotation Success: {annotation_result.successful_annotations}/"
                        f"{annotation_result.total_annotations} "
                        f"({annotation_result.success_rate:.1f}%)"
                    )
                else:
                    logger.warning(f"PDF annotation encountered issues: {annotation_result.error}")
            else:
                logger.info("PDF annotation disabled in config.yaml")

        except ImportError as e:
            logger.warning(f"PDF annotation skipped - missing dependencies: {e}")
        except Exception as e:
            logger.warning(f"PDF annotation failed (non-blocking): {e}")

        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("EXTRACTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total Duration: {total_duration:.2f}s")
        logger.info(f"Raw Results: {results_file}")
        logger.info(f"Quality Report: {quality_file}")
        logger.info(f"USDM 4.0: {usdm_file}")
        if annotation_result and annotation_result.annotated_pdf_path:
            logger.info(f"Annotated PDF: {annotation_result.annotated_pdf_path}")
            logger.info(f"Annotation Report: {annotation_result.report_path}")

        # Quality summary
        successful = [m for m, q in all_quality.items() if 'error' not in q]
        failed = [m for m, q in all_quality.items() if 'error' in q]

        logger.info(f"\nAgents: {len(successful)} succeeded, {len(failed)} failed")

        if successful:
            avg_quality = sum(all_quality[m]['overall'] for m in successful) / len(successful)
            logger.info(f"Average Quality: {avg_quality:.1%}")

        if failed:
            logger.warning(f"Failed agents: {', '.join(failed)}")

        return all_results, all_quality

    finally:
        # Cleanup Gemini file
        try:
            genai.delete_file(gemini_file.name)
            logger.info(f"\nCleaned up Gemini file: {gemini_file.name}")
        except Exception as e:
            logger.warning(f"Could not delete Gemini file: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Protocol Extraction Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run extraction with all enabled agents
  python scripts/main.py --pdf protocol.pdf

  # Show agent configuration
  python scripts/main.py --show-agents

  # Run without cache
  python scripts/main.py --pdf protocol.pdf --no-cache

Agent Configuration:
  Edit config.yaml in the project root to enable/disable agents.
  Changes take effect on next run (no restart required).
        """
    )
    parser.add_argument("--pdf", help="Path to protocol PDF")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--no-cache", action="store_true", help="Disable cache")
    parser.add_argument("--show-agents", action="store_true", help="Show agent config and exit")
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging(args.log_level)

    # Reload config to pick up any changes
    reload_agent_config()

    # Show agents only
    if args.show_agents:
        print_agent_status()
        return

    # Require PDF for extraction
    if not args.pdf:
        print("Error: --pdf is required for extraction")
        print("Use --show-agents to view agent configuration")
        print("Use --help for more options")
        sys.exit(1)

    # Validate PDF exists
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}")
        sys.exit(1)

    # Set output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        # Default: create output dir in backend_vNext/outputs/{protocol_name}/{timestamp}
        protocol_name = pdf_path.stem
        project_root = Path(__file__).parent.parent  # backend_vNext/
        output_dir = project_root / "outputs" / protocol_name / datetime.now().strftime("%Y%m%d_%H%M%S")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Print agent status
    print_agent_status()
    print()

    # Run extraction
    try:
        results, quality = asyncio.run(
            run_extraction(
                pdf_path=str(pdf_path),
                output_dir=str(output_dir),
                use_cache=not args.no_cache,
                logger=logger,
            )
        )

        if results:
            protocol_id = Path(pdf_path).stem
            usdm_file = output_dir / f"{protocol_id}_usdm_4.0.json"
            print(f"\nExtraction complete!")
            print(f"  Output directory: {output_dir}")
            print(f"  USDM 4.0 document: {usdm_file}")
        else:
            print("\nExtraction failed. Check logs for details.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nExtraction cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Extraction failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
