"""
Two-phase extraction service for 100% provenance coverage.

Phase 1: Extract values only (no provenance)
Phase 2: Add provenance to all extracted values (CONDITIONAL)

This ensures complete provenance coverage by making provenance a separate,
focused extraction pass when needed.

OPTIMIZATION (v3.3): After Pass 1, provenance quality is checked. If the LLM
happens to include sufficient provenance in Pass 1 output (>= threshold),
Pass 2 is skipped entirely to save an API call. The output quality is
indistinguishable whether Pass 2 ran or was skipped.

OPTIMIZATION (v3.4): Surgical retry - when quality checks fail, only the
failing fields are re-extracted instead of regenerating the entire output.
Validated fields are preserved and merged with the fixed fields, reducing
token usage and eliminating regression risk.

Features:
- Quality-based feedback loop for targeted retry
- Five-dimension quality checks (accuracy, completeness, usdm_adherence, provenance, terminology)
- Dynamic prompt injection with specific failure details
- Version-aware caching for fast re-runs (v3.2)
- Pass 2 skip optimization when provenance threshold met in Pass 1 (v3.3)
- Surgical retry: preserve validated fields, only re-extract failures (v3.4)
"""

import asyncio
import copy
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.config import settings
from app.module_registry import ExtractionModuleConfig, get_module
from app.services.gemini_file_service import GeminiFileService
from app.utils.quality_checker import QualityChecker, QualityScore
from app.utils.extraction_cache import get_cache, ExtractionCache

logger = logging.getLogger(__name__)


class TwoPhaseExtractor:
    """
    Core extraction service implementing two-phase extraction.

    Pass 1: Values extraction - Focus on extracting accurate data
    Pass 2: Provenance extraction - Add source references to all data
    """

    def __init__(self, gemini_service: Optional[GeminiFileService] = None):
        """Initialize extractor with Gemini service."""
        self.gemini_service = gemini_service or GeminiFileService()

    async def extract_module(
        self,
        module_id: str,
        gemini_file_uri: str,
        protocol_id: str,
    ) -> Dict[str, Any]:
        """
        Execute two-phase extraction for a single module.

        Optimization: If Pass 1 output already has sufficient provenance,
        Pass 2 is skipped to save an LLM call.

        Args:
            module_id: ID of module to extract
            gemini_file_uri: URI of uploaded PDF in Gemini
            protocol_id: Protocol identifier for output

        Returns:
            Complete extraction result with provenance
        """
        module = get_module(module_id)
        if not module:
            raise ValueError(f"Unknown module: {module_id}")

        logger.info(f"Starting two-phase extraction for {module_id}")

        # Phase 1: Values extraction
        start_time = time.time()
        pass1_result = await self._execute_pass1(
            module=module,
            gemini_file_uri=gemini_file_uri,
            protocol_id=protocol_id,
        )
        pass1_duration = time.time() - start_time
        logger.info(f"Pass 1 completed in {pass1_duration:.2f}s")

        # Check if Pass 1 already has sufficient provenance (optimization)
        quality_checker = QualityChecker()
        thresholds = settings.quality_thresholds
        pass1_quality = quality_checker.evaluate(pass1_result, module_id)

        pass2_skipped = False
        pass2_duration = 0.0

        if pass1_quality.provenance >= thresholds.get("provenance", 0.95):
            # Pass 1 has sufficient provenance - skip Pass 2
            logger.info(
                f"Pass 1 provenance ({pass1_quality.provenance:.1%}) meets threshold "
                f"({thresholds.get('provenance', 0.95):.1%}) - skipping Pass 2"
            )
            pass2_skipped = True
            final_result = pass1_result
        else:
            # Phase 2: Provenance extraction (required)
            logger.info(
                f"Pass 1 provenance ({pass1_quality.provenance:.1%}) below threshold "
                f"({thresholds.get('provenance', 0.95):.1%}) - running Pass 2"
            )
            start_time = time.time()
            final_result = await self._execute_pass2(
                module=module,
                gemini_file_uri=gemini_file_uri,
                pass1_output=pass1_result,
            )
            pass2_duration = time.time() - start_time
            logger.info(f"Pass 2 completed in {pass2_duration:.2f}s")

        # Return flat JSON (no extracted_data wrapper)
        # Add metadata fields that don't interfere with schema
        result = final_result.copy()
        result["_metadata"] = {
            "module_id": module_id,
            "instance_type": module.instance_type,
            "pass1_duration_seconds": pass1_duration,
            "pass2_duration_seconds": pass2_duration,
            "pass2_skipped": pass2_skipped,
        }
        return result

    async def _execute_pass1(
        self,
        module: ExtractionModuleConfig,
        gemini_file_uri: str,
        protocol_id: str,
    ) -> Dict[str, Any]:
        """
        Execute Pass 1: Values extraction.

        Args:
            module: Module configuration
            gemini_file_uri: Gemini file URI
            protocol_id: Protocol identifier

        Returns:
            Extracted values (no provenance)
        """
        # Load Pass 1 prompt
        prompt_path = module.get_pass1_prompt_path()
        if not prompt_path or not prompt_path.exists():
            raise FileNotFoundError(f"Pass 1 prompt not found: {prompt_path}")

        prompt_template = prompt_path.read_text(encoding='utf-8')

        # Substitute any placeholders (e.g., protocol_id)
        prompt = prompt_template.replace("{protocol_id}", protocol_id)
        prompt = prompt.replace("{{ protocol_id }}", protocol_id)

        # Generate content
        logger.info(f"Executing Pass 1 for {module.module_id}")
        response = await self.gemini_service.generate_content(
            gemini_file_uri=gemini_file_uri,
            prompt=prompt,
        )

        # Parse JSON response
        result = self._parse_json_response(response)

        # Ensure mandatory fields are present
        if "id" not in result or not result["id"]:
            result["id"] = protocol_id
        if "instanceType" not in result:
            result["instanceType"] = module.instance_type

        return result

    async def _execute_pass2(
        self,
        module: ExtractionModuleConfig,
        gemini_file_uri: str,
        pass1_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute Pass 2: Provenance extraction.

        Args:
            module: Module configuration
            gemini_file_uri: Gemini file URI
            pass1_output: Output from Pass 1

        Returns:
            Complete result with provenance added
        """
        # Load Pass 2 prompt
        prompt_path = module.get_pass2_prompt_path()
        if not prompt_path or not prompt_path.exists():
            raise FileNotFoundError(f"Pass 2 prompt not found: {prompt_path}")

        prompt_template = prompt_path.read_text(encoding='utf-8')

        # Inject Pass 1 output into prompt
        pass1_json = json.dumps(pass1_output, indent=2)

        # Replace placeholders for Pass 1 output
        prompt = prompt_template.replace("{{ pass1_output }}", pass1_json)
        prompt = prompt.replace("{{ extracted_data }}", pass1_json)
        prompt = prompt.replace("{{ extracted_values }}", pass1_json)
        prompt = prompt.replace("{pass1_output}", pass1_json)

        # Generate content
        logger.info(f"Executing Pass 2 for {module.module_id}")
        response = await self.gemini_service.generate_content(
            gemini_file_uri=gemini_file_uri,
            prompt=prompt,
        )

        # Parse JSON response
        result = self._parse_json_response(response)

        # Ensure mandatory fields from Pass 1 are preserved
        if "id" not in result or not result["id"]:
            result["id"] = pass1_output.get("id", "")
        if "instanceType" not in result:
            result["instanceType"] = pass1_output.get("instanceType", module.instance_type)

        # Preserve other key fields from Pass 1 if missing
        for field in ["name", "officialTitle", "version"]:
            if field not in result and field in pass1_output:
                result[field] = pass1_output[field]

        return result

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response, handling common issues.

        Args:
            response: Raw response text from LLM

        Returns:
            Parsed JSON dictionary
        """
        # Clean response
        text = response.strip()

        # Remove markdown code fences if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        # Try to parse JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")

            # Try to extract JSON object from response
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            # Log the problematic response for debugging
            logger.error(f"Failed to parse JSON response: {text[:500]}...")
            raise ValueError(f"Failed to parse JSON response: {e}")

    # =========================================================================
    # SURGICAL RETRY HELPERS (v3.4)
    # =========================================================================

    def _extract_failed_paths(self, quality: QualityScore) -> Dict[str, list]:
        """
        Extract failed field paths from QualityScore issues.

        Returns dict with categorized failed paths:
        - accuracy: paths with accuracy issues (placeholders, invalid formats)
        - completeness: missing required field names
        - usdm_adherence: paths with schema violations
        - provenance: paths missing provenance
        - terminology: paths with CDISC code issues

        Args:
            quality: QualityScore with issue details

        Returns:
            Dict mapping issue category to list of failed paths/fields
        """
        failed = {
            "accuracy": [],
            "completeness": [],
            "usdm_adherence": [],
            "provenance": [],
            "terminology": [],
        }

        # Extract accuracy issue paths
        for issue in quality.accuracy_issues:
            path = issue.get("path", "")
            if path and path not in failed["accuracy"]:
                failed["accuracy"].append(path)

        # Extract completeness - these are field names, not paths
        for issue in quality.completeness_issues:
            field = issue.get("field", "")
            if field and field not in failed["completeness"]:
                failed["completeness"].append(field)

        # Extract USDM adherence issue paths
        for issue in quality.usdm_adherence_issues:
            path = issue.get("path", "")
            if path and path not in failed["usdm_adherence"]:
                failed["usdm_adherence"].append(path)

        # Extract provenance issue paths
        for issue in quality.provenance_issues:
            path = issue.get("path", "")
            if path and path not in failed["provenance"]:
                failed["provenance"].append(path)

        # Extract terminology issue paths
        for issue in quality.terminology_issues:
            path = issue.get("path", "")
            if path and path not in failed["terminology"]:
                failed["terminology"].append(path)

        return failed

    def _get_top_level_fields_from_paths(self, paths: list) -> set:
        """
        Extract top-level field names from JSON paths.

        E.g., "$.studyPhase.code" -> "studyPhase"
              "$.arms[0].name" -> "arms"

        Args:
            paths: List of JSON paths (e.g., ["$.field.subfield", "$.other[0]"])

        Returns:
            Set of top-level field names
        """
        top_level = set()
        for path in paths:
            # Remove leading "$." if present
            clean_path = path.lstrip("$.")
            # Get first segment (before . or [)
            match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)', clean_path)
            if match:
                top_level.add(match.group(1))
        return top_level

    def _build_surgical_prompt(
        self,
        failed_paths: Dict[str, list],
        previous_result: Dict[str, Any],
        pass_type: str = "pass1",
    ) -> str:
        """
        Build a surgical prompt that only asks for failed fields.

        Args:
            failed_paths: Dict of categorized failed paths from _extract_failed_paths
            previous_result: The previous extraction result
            pass_type: "pass1" or "pass2"

        Returns:
            Surgical prompt text to append to base prompt
        """
        # Get all unique failed top-level fields
        all_paths = []
        for category_paths in failed_paths.values():
            all_paths.extend(category_paths)

        if not all_paths:
            return ""

        # Get top-level fields that need re-extraction
        failed_fields = self._get_top_level_fields_from_paths(all_paths)
        failed_fields.update(failed_paths.get("completeness", []))  # These are already field names

        lines = [
            "\n\n## SURGICAL RETRY - ONLY RE-EXTRACT SPECIFIC FIELDS",
            "",
            "IMPORTANT: Your previous extraction was mostly correct. Only the following",
            "fields have issues and need to be re-extracted. Return ONLY these fields",
            "in your JSON response - do NOT include fields that were already correct.",
            "",
            "### FIELDS REQUIRING RE-EXTRACTION:",
        ]

        for field in sorted(failed_fields):
            lines.append(f"- `{field}`")

        lines.append("")
        lines.append("### SPECIFIC ISSUES TO FIX:")

        # Add accuracy issues
        if failed_paths.get("accuracy"):
            lines.append("\n**Accuracy Issues:**")
            for path in failed_paths["accuracy"][:10]:
                lines.append(f"- `{path}`: contains placeholder or invalid value")

        # Add completeness issues
        if failed_paths.get("completeness"):
            lines.append("\n**Missing Required Fields:**")
            for field in failed_paths["completeness"][:10]:
                lines.append(f"- `{field}`: REQUIRED but missing or empty")

        # Add USDM adherence issues
        if failed_paths.get("usdm_adherence"):
            lines.append("\n**Schema Adherence Issues:**")
            for path in failed_paths["usdm_adherence"][:10]:
                lines.append(f"- `{path}`: violates JSON schema")

        # Add provenance issues (mainly for pass2)
        if failed_paths.get("provenance") and pass_type == "pass2":
            lines.append("\n**Missing Provenance:**")
            for path in failed_paths["provenance"][:10]:
                lines.append(f"- `{path}`: needs page_number and text_snippet")

        # Add terminology issues
        if failed_paths.get("terminology"):
            lines.append("\n**CDISC Terminology Issues:**")
            for path in failed_paths["terminology"][:10]:
                lines.append(f"- `{path}`: invalid code/decode pair")

        lines.append("")
        lines.append("### RESPONSE FORMAT:")
        lines.append("Return a JSON object containing ONLY the fields listed above.")
        lines.append("Example structure:")
        lines.append("```json")
        lines.append("{")

        # Show example structure for failed fields
        example_fields = list(failed_fields)[:3]
        for i, field in enumerate(example_fields):
            comma = "," if i < len(example_fields) - 1 else ""
            lines.append(f'  "{field}": <corrected value>{comma}')

        lines.append("}")
        lines.append("```")
        lines.append("")
        lines.append("Do NOT include any fields that were already correct.")

        return "\n".join(lines)

    def _deep_merge(
        self,
        base: Dict[str, Any],
        updates: Dict[str, Any],
        failed_fields: set,
    ) -> Dict[str, Any]:
        """
        Deep merge updates into base, but ONLY for fields in failed_fields.

        Preserves all fields in base that are not in failed_fields.
        Only updates/adds fields that are in failed_fields.

        Args:
            base: The original result to preserve
            updates: The surgical retry result with fixed fields
            failed_fields: Set of top-level field names that were re-extracted

        Returns:
            Merged result with preserved valid fields and fixed failed fields
        """
        result = copy.deepcopy(base)

        for field in failed_fields:
            if field in updates:
                # Replace the entire field with the updated version
                result[field] = copy.deepcopy(updates[field])
                logger.debug(f"Surgical merge: replaced field '{field}'")
            elif field in result:
                # Field was in failed list but not in updates - keep original
                logger.warning(f"Surgical merge: field '{field}' not in retry response, keeping original")

        return result

    def _should_use_surgical_retry(self, quality: QualityScore) -> bool:
        """
        Determine if surgical retry is appropriate based on quality scores.

        Surgical retry is beneficial when:
        - Quality scores are reasonably high (>= 70%) - most fields are correct
        - Issues are localized, not structural

        Surgical retry is NOT appropriate when:
        - Quality scores are too low (< 70%) - need to regenerate most fields
        - Compliance is very low (< 50%) - structural JSON problems

        Args:
            quality: QualityScore with dimension scores

        Returns:
            True if surgical retry should be used
        """
        # Surgical retry threshold - if quality is above this, use surgical
        SURGICAL_THRESHOLD = 0.70  # 70%
        USDM_ADHERENCE_MIN_THRESHOLD = 0.50  # 50%

        # If no issues at all, no retry needed
        total_issues = (
            len(quality.accuracy_issues) +
            len(quality.completeness_issues) +
            len(quality.usdm_adherence_issues) +
            len(quality.provenance_issues) +
            len(quality.terminology_issues)
        )
        if total_issues == 0:
            return False

        # If USDM adherence is very low, indicates structural JSON problems
        # Full retry with feedback is better for structural issues
        if quality.usdm_adherence < USDM_ADHERENCE_MIN_THRESHOLD:
            logger.info(
                f"Surgical retry skipped: usdm_adherence too low ({quality.usdm_adherence:.1%}) "
                f"suggests structural issues"
            )
            return False

        # Calculate average quality using ONLY dimensions that have issues
        # This avoids inflated averages from dimensions not checked (e.g., Pass 1
        # doesn't check provenance/terminology, so they're fake 1.0 values)
        dimensions_with_issues = []
        if quality.accuracy_issues:
            dimensions_with_issues.append(("accuracy", quality.accuracy))
        if quality.completeness_issues:
            dimensions_with_issues.append(("completeness", quality.completeness))
        if quality.usdm_adherence_issues:
            dimensions_with_issues.append(("usdm_adherence", quality.usdm_adherence))
        if quality.provenance_issues:
            dimensions_with_issues.append(("provenance", quality.provenance))
        if quality.terminology_issues:
            dimensions_with_issues.append(("terminology", quality.terminology))

        # If no specific dimension has issues but total_issues > 0, use all checked dimensions
        # (accuracy, completeness, usdm_adherence are always checked)
        if not dimensions_with_issues:
            dimensions_with_issues = [
                ("accuracy", quality.accuracy),
                ("completeness", quality.completeness),
                ("usdm_adherence", quality.usdm_adherence),
            ]

        avg_quality = sum(score for _, score in dimensions_with_issues) / len(dimensions_with_issues)
        dimension_names = [name for name, _ in dimensions_with_issues]

        # If average quality is below threshold, full retry is better
        if avg_quality < SURGICAL_THRESHOLD:
            logger.info(
                f"Surgical retry skipped: average quality ({avg_quality:.1%}) "
                f"below threshold ({SURGICAL_THRESHOLD:.0%}) "
                f"[dimensions: {', '.join(dimension_names)}]"
            )
            return False

        logger.info(
            f"Surgical retry appropriate: avg={avg_quality:.1%} "
            f"[{', '.join(dimension_names)}], {total_issues} issues to fix"
        )
        return True

    def calculate_provenance_coverage(self, data: Dict[str, Any]) -> float:
        """
        Calculate provenance coverage percentage.

        Traverses the extracted data and counts fields with/without provenance.

        Args:
            data: Extracted data with provenance

        Returns:
            Coverage percentage (0.0 to 1.0)
        """
        total_fields = 0
        fields_with_provenance = 0

        def traverse(obj, path=""):
            nonlocal total_fields, fields_with_provenance

            if isinstance(obj, dict):
                # Check if this object has provenance
                has_provenance = "provenance" in obj and obj["provenance"]

                # Count non-provenance, non-meta fields
                for key, value in obj.items():
                    if key in ("provenance", "id", "instanceType", "schemaVersion"):
                        continue

                    if isinstance(value, (dict, list)):
                        traverse(value, f"{path}.{key}")
                    elif value is not None:
                        total_fields += 1
                        if has_provenance:
                            fields_with_provenance += 1

            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    traverse(item, f"{path}[{i}]")

        traverse(data)

        if total_fields == 0:
            return 1.0  # No fields to check

        return fields_with_provenance / total_fields

    async def extract_with_retry(
        self,
        module_id: str,
        gemini_file_uri: str,
        protocol_id: str,
        protocol_uuid: Any = None,
        max_retries: int = 3,
        target_provenance_coverage: float = 1.0,
    ) -> Tuple[Dict[str, Any], float]:
        """
        Extract with retries until provenance coverage target is met.

        Args:
            module_id: Module to extract
            gemini_file_uri: Gemini file URI
            protocol_id: Protocol identifier (filename stem)
            protocol_uuid: Protocol UUID for database linking (optional)
            max_retries: Maximum retry attempts
            target_provenance_coverage: Target coverage (default 100%)

        Returns:
            Tuple of (result, coverage)
        """
        last_result = None
        last_coverage = 0.0

        for attempt in range(max_retries):
            try:
                result = await self.extract_module(
                    module_id=module_id,
                    gemini_file_uri=gemini_file_uri,
                    protocol_id=protocol_id,
                )

                # Result is now flat JSON (no extracted_data wrapper)
                # Exclude _metadata from coverage calculation
                data_for_coverage = {k: v for k, v in result.items() if k != "_metadata"}
                coverage = self.calculate_provenance_coverage(data_for_coverage)

                logger.info(
                    f"Attempt {attempt + 1}: Provenance coverage = {coverage:.1%}"
                )

                if coverage >= target_provenance_coverage:
                    return result, coverage

                last_result = result
                last_coverage = coverage

            except Exception as e:
                logger.warning(f"Extraction attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise

        # Return best result if target not met
        logger.warning(
            f"Target provenance coverage not met. Best: {last_coverage:.1%}"
        )
        return last_result, last_coverage

    async def extract_with_quality_feedback(
        self,
        module_id: str,
        gemini_file_uri: str,
        protocol_id: str,
        max_retries: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], QualityScore]:
        """
        Extract with quality checks and targeted retry using feedback.

        This is the recommended extraction method that:
        1. Runs Pass 1 with accuracy/completeness checks
        2. On failure, retries Pass 1 with specific feedback
        3. Checks if Pass 1 already has sufficient provenance (optimization)
        4. If provenance passes threshold, skips Pass 2 entirely
        5. Otherwise runs Pass 2 with all quality checks
        6. On failure, retries Pass 2 with specific feedback
        7. Returns result with comprehensive quality score

        Args:
            module_id: Module to extract
            gemini_file_uri: Gemini file URI
            protocol_id: Protocol identifier
            max_retries: Maximum retry attempts per pass (default from settings)

        Returns:
            Tuple of (result, quality_score)
        """
        if max_retries is None:
            max_retries = settings.max_quality_retries

        module = get_module(module_id)
        if not module:
            raise ValueError(f"Unknown module: {module_id}")

        quality_checker = QualityChecker()
        thresholds = settings.quality_thresholds

        logger.info(f"Starting quality-based extraction for {module_id}")

        # === PASS 1: Values Extraction with quality feedback ===
        pass1_result = None
        pass1_quality = None
        pass1_start = time.time()
        pass1_surgical_retries = 0

        for attempt in range(max_retries):
            try:
                if attempt == 0:
                    # First attempt - use standard prompt
                    pass1_result = await self._execute_pass1(
                        module=module,
                        gemini_file_uri=gemini_file_uri,
                        protocol_id=protocol_id,
                    )
                else:
                    # If previous attempt threw an exception (result/quality is None),
                    # we must retry from scratch - can't do surgical or feedback-based retry
                    if pass1_result is None or pass1_quality is None:
                        logger.info(f"Pass 1 attempt {attempt + 1}: retrying from scratch (previous attempt failed)")
                        pass1_result = await self._execute_pass1(
                            module=module,
                            gemini_file_uri=gemini_file_uri,
                            protocol_id=protocol_id,
                        )
                    else:
                        # Retry - use surgical retry if appropriate (v3.4)
                        use_surgical = self._should_use_surgical_retry(pass1_quality)
                        if use_surgical:
                            try:
                                logger.info(f"Pass 1 attempt {attempt + 1}: using SURGICAL retry")
                                pass1_surgical_retries += 1
                                pass1_result = await self._execute_surgical_pass1(
                                    module=module,
                                    gemini_file_uri=gemini_file_uri,
                                    protocol_id=protocol_id,
                                    previous_result=pass1_result,
                                    quality=pass1_quality,
                                )
                            except (ValueError, Exception) as e:
                                # Surgical retry failed, fall back to full retry
                                logger.warning(f"Surgical Pass 1 failed ({e}), falling back to full retry")
                                pass1_surgical_retries -= 1  # Don't count failed surgical attempt
                                use_surgical = False

                        if not use_surgical:
                            # Full retry with feedback
                            logger.info(f"Pass 1 attempt {attempt + 1}: using FULL retry")
                            pass1_result = await self._execute_pass1_with_feedback(
                                module=module,
                                gemini_file_uri=gemini_file_uri,
                                protocol_id=protocol_id,
                                previous_result=pass1_result,
                                quality=pass1_quality,
                            )

                # Quality check Pass 1 (accuracy and completeness only)
                pass1_quality = quality_checker.evaluate_pass1(pass1_result, module_id)

                # Check if Pass 1 quality is acceptable
                if (pass1_quality.accuracy >= thresholds["accuracy"] and
                    pass1_quality.completeness >= thresholds["completeness"]):
                    logger.info(f"Pass 1 quality OK on attempt {attempt + 1}: {pass1_quality}")
                    break

                logger.warning(
                    f"Pass 1 quality failed on attempt {attempt + 1}: "
                    f"accuracy={pass1_quality.accuracy:.1%}, "
                    f"completeness={pass1_quality.completeness:.1%}"
                )

                # Add delay before retry
                if attempt < max_retries - 1:
                    await asyncio.sleep(settings.quality_retry_delay)

            except Exception as e:
                logger.error(f"Pass 1 attempt {attempt + 1} failed with error: {e}")
                if attempt == max_retries - 1:
                    raise

        pass1_duration = time.time() - pass1_start

        # === PROVENANCE CHECK: Can we skip Pass 2? ===
        # Run full quality evaluation on Pass 1 output including provenance
        pass1_full_quality = quality_checker.evaluate(pass1_result, module_id)
        pass2_skipped = False
        pass2_duration = 0.0

        if pass1_full_quality.provenance >= thresholds.get("provenance", 0.95):
            # Pass 1 has sufficient provenance - skip Pass 2 entirely
            logger.info(
                f"Pass 1 provenance ({pass1_full_quality.provenance:.1%}) meets threshold "
                f"({thresholds.get('provenance', 0.95):.1%}) - SKIPPING Pass 2"
            )
            pass2_skipped = True
            pass2_surgical_retries = 0  # No Pass 2 means no surgical retries

            # Post-process Pass 1 result (truncate snippets, fix codes)
            combined_result = quality_checker.post_process(pass1_result, module_id)

            # Re-evaluate quality after post-processing
            combined_quality = quality_checker.evaluate(combined_result, module_id)
        else:
            # === PASS 2: Provenance Extraction with quality feedback ===
            logger.info(
                f"Pass 1 provenance ({pass1_full_quality.provenance:.1%}) below threshold "
                f"({thresholds.get('provenance', 0.95):.1%}) - running Pass 2"
            )
            combined_result = None
            combined_quality = None
            pass2_start = time.time()
            pass2_surgical_retries = 0

            for attempt in range(max_retries):
                try:
                    if attempt == 0:
                        # First attempt - use standard prompt
                        combined_result = await self._execute_pass2(
                            module=module,
                            gemini_file_uri=gemini_file_uri,
                            pass1_output=pass1_result,
                        )
                    else:
                        # If previous attempt threw an exception (result/quality is None),
                        # we must retry from scratch - can't do surgical or feedback-based retry
                        if combined_result is None or combined_quality is None:
                            logger.info(f"Pass 2 attempt {attempt + 1}: retrying from scratch (previous attempt failed)")
                            combined_result = await self._execute_pass2(
                                module=module,
                                gemini_file_uri=gemini_file_uri,
                                pass1_output=pass1_result,
                            )
                        else:
                            # Retry - use surgical retry if appropriate (v3.4)
                            use_surgical = self._should_use_surgical_retry(combined_quality)
                            if use_surgical:
                                try:
                                    logger.info(f"Pass 2 attempt {attempt + 1}: using SURGICAL retry")
                                    pass2_surgical_retries += 1
                                    combined_result = await self._execute_surgical_pass2(
                                        module=module,
                                        gemini_file_uri=gemini_file_uri,
                                        pass1_output=pass1_result,
                                        previous_result=combined_result,
                                        quality=combined_quality,
                                    )
                                except (ValueError, Exception) as e:
                                    # Surgical retry failed, fall back to full retry
                                    logger.warning(f"Surgical Pass 2 failed ({e}), falling back to full retry")
                                    pass2_surgical_retries -= 1  # Don't count failed surgical attempt
                                    use_surgical = False

                            if not use_surgical:
                                # Full retry with feedback
                                logger.info(f"Pass 2 attempt {attempt + 1}: using FULL retry")
                                combined_result = await self._execute_pass2_with_feedback(
                                    module=module,
                                    gemini_file_uri=gemini_file_uri,
                                    pass1_output=pass1_result,
                                    previous_result=combined_result,
                                    quality=combined_quality,
                                )

                    # Post-process to fix auto-correctable issues (truncate snippets, fix codes)
                    combined_result = quality_checker.post_process(combined_result, module_id)

                    # Quality check combined result (all dimensions)
                    combined_quality = quality_checker.evaluate(combined_result, module_id)

                    # Check if all thresholds are met
                    if combined_quality.passes_thresholds(thresholds):
                        logger.info(f"Pass 2 quality OK on attempt {attempt + 1}: {combined_quality}")
                        break

                    failed = combined_quality.get_failed_dimensions(thresholds)
                    logger.warning(
                        f"Pass 2 quality failed on attempt {attempt + 1}: "
                        f"failed dimensions: {failed}"
                    )

                    # Log specific USDM adherence issues for debugging
                    if "usdm_adherence" in failed and combined_quality.usdm_adherence_issues:
                        logger.warning(f"USDM adherence issues ({len(combined_quality.usdm_adherence_issues)}):")
                        for issue in combined_quality.usdm_adherence_issues[:10]:
                            logger.warning(f"  - {issue.get('path', 'unknown')}: {issue.get('message', 'unknown')}")

                    # Add delay before retry
                    if attempt < max_retries - 1:
                        await asyncio.sleep(settings.quality_retry_delay)

                except Exception as e:
                    logger.error(f"Pass 2 attempt {attempt + 1} failed with error: {e}")
                    if attempt == max_retries - 1:
                        raise

            pass2_duration = time.time() - pass2_start

        # Build final result as flat JSON (no extracted_data wrapper)
        result = combined_result.copy()
        result["_metadata"] = {
            "module_id": module_id,
            "instance_type": module.instance_type,
            "pass1_duration_seconds": pass1_duration,
            "pass2_duration_seconds": pass2_duration,
            "pass2_skipped": pass2_skipped,
            "pass1_surgical_retries": pass1_surgical_retries,
            "pass2_surgical_retries": pass2_surgical_retries if not pass2_skipped else 0,
            "quality_score": combined_quality.to_dict() if combined_quality else None,
        }

        # Build log message with optimization details
        opt_details = []
        if pass2_skipped:
            opt_details.append("Pass 2 skipped")
        if pass1_surgical_retries > 0:
            opt_details.append(f"{pass1_surgical_retries} surgical P1 retries")
        if not pass2_skipped and pass2_surgical_retries > 0:
            opt_details.append(f"{pass2_surgical_retries} surgical P2 retries")

        opt_str = f" ({', '.join(opt_details)})" if opt_details else ""

        logger.info(
            f"Extraction complete for {module_id}: "
            f"overall={combined_quality.overall_score:.1%}, "
            f"duration={pass1_duration + pass2_duration:.1f}s{opt_str}"
        )

        return result, combined_quality

    async def _execute_pass1_with_feedback(
        self,
        module: ExtractionModuleConfig,
        gemini_file_uri: str,
        protocol_id: str,
        previous_result: Dict[str, Any],
        quality: QualityScore,
    ) -> Dict[str, Any]:
        """
        Execute Pass 1 with quality feedback for retry.

        Injects specific failure details into the prompt.
        """
        # Load base prompt
        prompt_path = module.get_pass1_prompt_path()
        if not prompt_path or not prompt_path.exists():
            raise FileNotFoundError(f"Pass 1 prompt not found: {prompt_path}")

        prompt_template = prompt_path.read_text(encoding='utf-8')
        prompt = prompt_template.replace("{protocol_id}", protocol_id)
        prompt = prompt.replace("{{ protocol_id }}", protocol_id)

        # Generate feedback section
        quality_checker = QualityChecker()
        feedback = quality_checker.generate_pass1_feedback(quality, previous_result)
        prompt = prompt + feedback

        logger.info(f"Executing Pass 1 with feedback for {module.module_id}")
        response = await self.gemini_service.generate_content(
            gemini_file_uri=gemini_file_uri,
            prompt=prompt,
        )

        result = self._parse_json_response(response)

        # Ensure mandatory fields are present
        if "id" not in result or not result["id"]:
            result["id"] = protocol_id
        if "instanceType" not in result:
            result["instanceType"] = module.instance_type

        return result

    async def _execute_pass2_with_feedback(
        self,
        module: ExtractionModuleConfig,
        gemini_file_uri: str,
        pass1_output: Dict[str, Any],
        previous_result: Dict[str, Any],
        quality: QualityScore,
    ) -> Dict[str, Any]:
        """
        Execute Pass 2 with quality feedback for retry.

        Injects specific provenance and USDM adherence failures into the prompt.
        """
        # Load base prompt
        prompt_path = module.get_pass2_prompt_path()
        if not prompt_path or not prompt_path.exists():
            raise FileNotFoundError(f"Pass 2 prompt not found: {prompt_path}")

        prompt_template = prompt_path.read_text(encoding='utf-8')

        # Inject Pass 1 output
        pass1_json = json.dumps(pass1_output, indent=2)
        prompt = prompt_template.replace("{{ pass1_output }}", pass1_json)
        prompt = prompt.replace("{{ extracted_data }}", pass1_json)
        prompt = prompt.replace("{{ extracted_values }}", pass1_json)
        prompt = prompt.replace("{pass1_output}", pass1_json)

        # Generate feedback section
        quality_checker = QualityChecker()
        feedback = quality_checker.generate_pass2_feedback(quality)
        prompt = prompt + feedback

        logger.info(f"Executing Pass 2 with feedback for {module.module_id}")
        response = await self.gemini_service.generate_content(
            gemini_file_uri=gemini_file_uri,
            prompt=prompt,
        )

        result = self._parse_json_response(response)

        # Ensure mandatory fields from Pass 1 are preserved
        if "id" not in result or not result["id"]:
            result["id"] = pass1_output.get("id", "")
        if "instanceType" not in result:
            result["instanceType"] = pass1_output.get("instanceType", module.instance_type)

        # Preserve other key fields from Pass 1 if missing
        for field in ["name", "officialTitle", "version"]:
            if field not in result and field in pass1_output:
                result[field] = pass1_output[field]

        return result

    # =========================================================================
    # SURGICAL RETRY EXECUTION METHODS (v3.4)
    # =========================================================================

    async def _execute_surgical_pass1(
        self,
        module: ExtractionModuleConfig,
        gemini_file_uri: str,
        protocol_id: str,
        previous_result: Dict[str, Any],
        quality: QualityScore,
    ) -> Dict[str, Any]:
        """
        Execute surgical Pass 1 retry - only re-extract failed fields.

        Preserves validated fields from previous_result and only asks LLM
        to regenerate the specific fields that failed quality checks.

        Args:
            module: Module configuration
            gemini_file_uri: Gemini file URI
            protocol_id: Protocol identifier
            previous_result: Previous extraction result to preserve
            quality: QualityScore with issue details

        Returns:
            Merged result with preserved valid fields and fixed failed fields
        """
        # Safety check - if previous_result is None, fall back to full retry
        if previous_result is None:
            logger.warning("Surgical Pass 1: previous_result is None, cannot perform surgical retry")
            raise ValueError("Cannot perform surgical retry without previous result")

        # Extract failed paths
        failed_paths = self._extract_failed_paths(quality)

        # Get top-level fields that need re-extraction
        all_paths = []
        for category_paths in failed_paths.values():
            all_paths.extend(category_paths)
        failed_fields = self._get_top_level_fields_from_paths(all_paths)
        failed_fields.update(failed_paths.get("completeness", []))

        if not failed_fields:
            logger.warning("Surgical Pass 1: no failed fields identified, returning previous result")
            return previous_result

        logger.info(f"Surgical Pass 1: re-extracting {len(failed_fields)} fields: {sorted(failed_fields)}")

        # Load base prompt
        prompt_path = module.get_pass1_prompt_path()
        if not prompt_path or not prompt_path.exists():
            raise FileNotFoundError(f"Pass 1 prompt not found: {prompt_path}")

        prompt_template = prompt_path.read_text(encoding='utf-8')
        prompt = prompt_template.replace("{protocol_id}", protocol_id)
        prompt = prompt.replace("{{ protocol_id }}", protocol_id)

        # Add surgical prompt
        surgical_prompt = self._build_surgical_prompt(failed_paths, previous_result, "pass1")
        prompt = prompt + surgical_prompt

        logger.info(f"Executing surgical Pass 1 for {module.module_id}")
        response = await self.gemini_service.generate_content(
            gemini_file_uri=gemini_file_uri,
            prompt=prompt,
        )

        # Parse the surgical response
        try:
            surgical_result = self._parse_json_response(response)
        except ValueError as e:
            logger.warning(f"Surgical Pass 1 failed to parse response: {e}")
            # Fall back to returning previous result
            return previous_result

        # Merge surgical result into preserved base
        merged_result = self._deep_merge(previous_result, surgical_result, failed_fields)

        # Ensure mandatory fields are present
        if "id" not in merged_result or not merged_result["id"]:
            merged_result["id"] = protocol_id
        if "instanceType" not in merged_result:
            merged_result["instanceType"] = module.instance_type

        logger.info(f"Surgical Pass 1 complete: merged {len(failed_fields)} fixed fields")
        return merged_result

    async def _execute_surgical_pass2(
        self,
        module: ExtractionModuleConfig,
        gemini_file_uri: str,
        pass1_output: Dict[str, Any],
        previous_result: Dict[str, Any],
        quality: QualityScore,
    ) -> Dict[str, Any]:
        """
        Execute surgical Pass 2 retry - only re-extract failed fields.

        Preserves validated fields from previous_result and only asks LLM
        to regenerate the specific fields that failed quality checks
        (typically missing provenance or USDM adherence issues).

        Args:
            module: Module configuration
            gemini_file_uri: Gemini file URI
            pass1_output: Output from Pass 1 (for context)
            previous_result: Previous extraction result to preserve
            quality: QualityScore with issue details

        Returns:
            Merged result with preserved valid fields and fixed failed fields
        """
        # Safety check - if previous_result is None, fall back to full retry
        if previous_result is None:
            logger.warning("Surgical Pass 2: previous_result is None, cannot perform surgical retry")
            raise ValueError("Cannot perform surgical retry without previous result")

        # Extract failed paths
        failed_paths = self._extract_failed_paths(quality)

        # Get top-level fields that need re-extraction
        all_paths = []
        for category_paths in failed_paths.values():
            all_paths.extend(category_paths)
        failed_fields = self._get_top_level_fields_from_paths(all_paths)
        failed_fields.update(failed_paths.get("completeness", []))

        if not failed_fields:
            logger.warning("Surgical Pass 2: no failed fields identified, returning previous result")
            return previous_result

        logger.info(f"Surgical Pass 2: re-extracting {len(failed_fields)} fields: {sorted(failed_fields)}")

        # Load base prompt
        prompt_path = module.get_pass2_prompt_path()
        if not prompt_path or not prompt_path.exists():
            raise FileNotFoundError(f"Pass 2 prompt not found: {prompt_path}")

        prompt_template = prompt_path.read_text(encoding='utf-8')

        # Inject Pass 1 output for context
        pass1_json = json.dumps(pass1_output, indent=2)
        prompt = prompt_template.replace("{{ pass1_output }}", pass1_json)
        prompt = prompt.replace("{{ extracted_data }}", pass1_json)
        prompt = prompt.replace("{{ extracted_values }}", pass1_json)
        prompt = prompt.replace("{pass1_output}", pass1_json)

        # Add surgical prompt
        surgical_prompt = self._build_surgical_prompt(failed_paths, previous_result, "pass2")
        prompt = prompt + surgical_prompt

        logger.info(f"Executing surgical Pass 2 for {module.module_id}")
        response = await self.gemini_service.generate_content(
            gemini_file_uri=gemini_file_uri,
            prompt=prompt,
        )

        # Parse the surgical response
        try:
            surgical_result = self._parse_json_response(response)
        except ValueError as e:
            logger.warning(f"Surgical Pass 2 failed to parse response: {e}")
            # Fall back to returning previous result
            return previous_result

        # Merge surgical result into preserved base
        merged_result = self._deep_merge(previous_result, surgical_result, failed_fields)

        # Ensure mandatory fields from Pass 1 are preserved
        if "id" not in merged_result or not merged_result["id"]:
            merged_result["id"] = pass1_output.get("id", "")
        if "instanceType" not in merged_result:
            merged_result["instanceType"] = pass1_output.get("instanceType", module.instance_type)

        # Preserve other key fields
        for field in ["name", "officialTitle", "version"]:
            if field not in merged_result and field in pass1_output:
                merged_result[field] = pass1_output[field]

        logger.info(f"Surgical Pass 2 complete: merged {len(failed_fields)} fixed fields")
        return merged_result

    async def extract_with_cache(
        self,
        module_id: str,
        gemini_file_uri: str,
        protocol_id: str,
        pdf_path: str,
        model_name: str = "gemini-2.5-flash",
        use_cache: bool = True,
        max_retries: Optional[int] = None,
        protocol_uuid: Any = None,
    ) -> Tuple[Dict[str, Any], QualityScore, bool]:
        """
        Extract with version-aware caching.

        Cache invalidates automatically when any of these change:
        - PDF content
        - Pass 1 prompt
        - Pass 2 prompt
        - JSON Schema
        - Model name

        Args:
            module_id: Module to extract
            gemini_file_uri: Gemini file URI
            protocol_id: Protocol identifier (filename stem)
            pdf_path: Path to PDF file (for cache key)
            model_name: Model name (for cache key)
            use_cache: Whether to use cache (default True)
            max_retries: Maximum retry attempts per pass
            protocol_uuid: Protocol UUID for database linking (optional)

        Returns:
            Tuple of (result, quality_score, from_cache)
        """
        module = get_module(module_id)
        if not module:
            raise ValueError(f"Unknown module: {module_id}")

        cache = get_cache()
        from_cache = False

        # Get file paths for cache key
        pass1_prompt_path = str(module.get_pass1_prompt_path())
        pass2_prompt_path = str(module.get_pass2_prompt_path())
        schema_path = str(module.get_schema_path())

        # Check cache
        if use_cache:
            cached = cache.get(
                pdf_path=pdf_path,
                module_name=module_id,
                pass1_prompt_path=pass1_prompt_path,
                pass2_prompt_path=pass2_prompt_path,
                schema_path=schema_path,
                model_name=model_name,
            )

            if cached:
                logger.info(f"Using cached result for {module_id}")
                result = cached["data"]

                # Reconstruct quality score from cached data
                quality_checker = QualityChecker()
                quality = quality_checker.evaluate(result, module_id)

                return result, quality, True

        # No cache hit - run extraction
        logger.info(f"Cache miss for {module_id} - running extraction")
        result, quality = await self.extract_with_quality_feedback(
            module_id=module_id,
            gemini_file_uri=gemini_file_uri,
            protocol_id=protocol_id,
            max_retries=max_retries,
        )

        # Store in cache
        if use_cache:
            cache.set(
                pdf_path=pdf_path,
                module_name=module_id,
                pass1_prompt_path=pass1_prompt_path,
                pass2_prompt_path=pass2_prompt_path,
                schema_path=schema_path,
                model_name=model_name,
                result=result,
                quality_score=quality.to_dict() if quality else None,
                protocol_id=protocol_uuid,  # Pass UUID directly, not string
            )

        return result, quality, from_cache
