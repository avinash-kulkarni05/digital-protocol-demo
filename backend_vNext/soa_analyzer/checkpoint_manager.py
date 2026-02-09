"""
Checkpoint Manager - Validation Checkpoints at Pipeline Stage Transitions

This module implements validation checkpoints that run at key transitions
in the SOA extraction pipeline. Checkpoints can be:
- Blocking: Pipeline stops if validation fails
- Non-blocking: Pipeline continues but issues are flagged

Usage:
    manager = CheckpointManager()
    result = manager.validate("post_detection", detection_result)
    if not result.passed and result.blocking:
        raise RuntimeError(f"Checkpoint failed: {result}")
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class CheckResult:
    """Result of a single validation check."""
    check_name: str
    passed: bool
    message: str = ""
    actual_value: Any = None
    expected_value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkName": self.check_name,
            "passed": self.passed,
            "message": self.message,
            "actualValue": self.actual_value,
            "expectedValue": self.expected_value,
        }


@dataclass
class ValidationResult:
    """Result of checkpoint validation."""
    checkpoint: str
    passed: bool
    blocking: bool
    timestamp: datetime = field(default_factory=datetime.now)
    results: List[CheckResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint": self.checkpoint,
            "passed": self.passed,
            "blocking": self.blocking,
            "timestamp": self.timestamp.isoformat(),
            "results": [r.to_dict() for r in self.results],
            "warnings": self.warnings,
            "failedChecks": [r.check_name for r in self.results if not r.passed],
        }

    @property
    def failed_checks(self) -> List[CheckResult]:
        """Get list of failed checks."""
        return [r for r in self.results if not r.passed]

    def add_result(self, result: CheckResult) -> None:
        """Add a check result."""
        self.results.append(result)
        if not result.passed:
            self.passed = False

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)


# =============================================================================
# VALIDATION CHECK DEFINITIONS
# =============================================================================


def check_min_pages_detected(data: Any) -> Tuple[bool, str]:
    """Check that at least one SOA page was detected."""
    soa_tables = data.get("soaTables", [])
    count = len(soa_tables)
    passed = count >= 1
    message = f"Detected {count} SOA table(s)" if passed else "No SOA tables detected"
    return passed, message


def check_detection_confidence(data: Any) -> Tuple[bool, str]:
    """Check that detection confidence meets threshold."""
    confidence = data.get("confidence", 0.0)
    # Also check individual table confidences
    tables = data.get("soaTables", [])
    avg_conf = sum(t.get("confidence", 0) for t in tables) / max(len(tables), 1) if tables else 0

    threshold = 0.60
    passed = avg_conf >= threshold or confidence >= threshold
    message = f"Detection confidence: {avg_conf:.0%}" if passed else f"Low detection confidence: {avg_conf:.0%}"
    return passed, message


def check_min_cells_extracted(data: Any) -> Tuple[bool, str]:
    """Check that minimum cells were extracted from tables."""
    # Data could be a list of SOATable or extraction result
    if isinstance(data, list):
        # Count cells from HTML content length as proxy
        total_cells = sum(len(t.html_content) // 50 for t in data if hasattr(t, 'html_content'))
    else:
        total_cells = data.get("totalCells", 0)

    threshold = 10
    passed = total_cells >= threshold
    message = f"Extracted ~{total_cells} cells" if passed else f"Too few cells extracted: {total_cells}"
    return passed, message


def check_visit_columns_identified(data: Any) -> Tuple[bool, str]:
    """Check that visit columns were identified."""
    if isinstance(data, list):
        # Count from SOATable column_headers
        visit_cols = sum(len(getattr(t, 'column_headers', []) or []) for t in data)
    else:
        visit_cols = len(data.get("visitColumns", []))

    passed = visit_cols >= 1
    message = f"Found {visit_cols} visit column(s)" if passed else "No visit columns identified"
    return passed, message


def check_markers_linked_ratio(data: Any) -> Tuple[bool, str]:
    """Check that footnote markers were linked at acceptable ratio."""
    if hasattr(data, 'linking_quality'):
        ratio = data.linking_quality
    else:
        total = data.get("totalMarkers", 0)
        linked = data.get("markersLinked", 0)
        ratio = linked / max(total, 1)

    threshold = 0.50
    passed = ratio >= threshold
    message = f"Linking ratio: {ratio:.0%}" if passed else f"Low linking ratio: {ratio:.0%}"
    return passed, message


def check_footnote_extraction_quality(data: Any) -> Tuple[bool, str]:
    """Check footnote extraction quality."""
    if hasattr(data, 'extraction_quality'):
        quality = data.extraction_quality
    else:
        quality = data.get("extractionQuality", 0.0)

    threshold = 0.50
    passed = quality >= threshold
    message = f"Footnote quality: {quality:.0%}" if passed else f"Low footnote quality: {quality:.0%}"
    return passed, message


def check_visit_schedule_quality(data: Any) -> Tuple[bool, str]:
    """Check visit schedule generation quality."""
    if hasattr(data, 'generation_quality'):
        quality = data.generation_quality
    else:
        quality = data.get("generationQuality", 0.0)

    threshold = 0.50
    passed = quality >= threshold
    message = f"Schedule quality: {quality:.0%}" if passed else f"Low schedule quality: {quality:.0%}"
    return passed, message


def check_transformation_success(data: Any) -> Tuple[bool, str]:
    """Check that transformation produced valid USDM."""
    if isinstance(data, dict):
        has_timelines = "scheduleTimelines" in data
        has_encounters = any(
            "scheduledActivityInstances" in timeline
            for timeline in data.get("scheduleTimelines", [])
        )
        passed = has_timelines and has_encounters
    else:
        passed = data is not None

    message = "USDM structure valid" if passed else "Invalid USDM structure"
    return passed, message


def check_overall_quality_score(data: Any) -> Tuple[bool, str]:
    """Check overall quality score meets threshold."""
    if hasattr(data, 'overall_score'):
        score = data.overall_score
    else:
        score = data.get("overallScore", 0.0)

    threshold = 0.70
    passed = score >= threshold
    message = f"Quality score: {score:.0%}" if passed else f"Low quality score: {score:.0%}"
    return passed, message


# =============================================================================
# CHECKPOINT DEFINITIONS
# =============================================================================


# Checkpoint configurations
# Each checkpoint has:
# - blocking: Whether failure stops the pipeline
# - checks: List of (name, check_function) tuples
VALIDATION_CHECKPOINTS: Dict[str, Dict[str, Any]] = {
    "post_detection": {
        "blocking": True,
        "description": "Validates SOA table detection results",
        "checks": [
            ("min_pages_detected", check_min_pages_detected),
            ("detection_confidence", check_detection_confidence),
        ],
    },
    "post_footnote_extraction": {
        "blocking": False,  # Non-blocking - pipeline can continue
        "description": "Validates footnote extraction results",
        "checks": [
            ("footnote_extraction_quality", check_footnote_extraction_quality),
        ],
    },
    "post_visit_schedule": {
        "blocking": False,
        "description": "Validates visit schedule generation",
        "checks": [
            ("visit_schedule_quality", check_visit_schedule_quality),
        ],
    },
    "post_extraction": {
        "blocking": True,
        "description": "Validates HTML table extraction",
        "checks": [
            ("min_cells_extracted", check_min_cells_extracted),
            ("visit_columns_identified", check_visit_columns_identified),
        ],
    },
    "post_linking": {
        "blocking": False,
        "description": "Validates footnote cell linking",
        "checks": [
            ("markers_linked_ratio", check_markers_linked_ratio),
        ],
    },
    "post_transformation": {
        "blocking": True,
        "description": "Validates USDM transformation",
        "checks": [
            ("transformation_success", check_transformation_success),
        ],
    },
    "post_validation": {
        "blocking": False,
        "description": "Validates final quality scores",
        "checks": [
            ("overall_quality_score", check_overall_quality_score),
        ],
    },
}


# =============================================================================
# CHECKPOINT MANAGER
# =============================================================================


class CheckpointManager:
    """Manage validation checkpoints throughout the pipeline.

    Runs validation checks at key stage transitions and tracks results.
    Blocking checkpoints stop the pipeline on failure; non-blocking
    checkpoints flag issues but allow continuation.
    """

    def __init__(
        self,
        checkpoints: Optional[Dict[str, Dict[str, Any]]] = None,
        strict_mode: bool = False,
    ):
        """Initialize checkpoint manager.

        Args:
            checkpoints: Custom checkpoint definitions (defaults to VALIDATION_CHECKPOINTS)
            strict_mode: If True, treat all checkpoints as blocking
        """
        self.checkpoints = checkpoints or VALIDATION_CHECKPOINTS.copy()
        self.strict_mode = strict_mode
        self.history: List[ValidationResult] = []

    def validate(
        self,
        checkpoint_name: str,
        data: Any,
    ) -> ValidationResult:
        """Run validation checks for a checkpoint.

        Args:
            checkpoint_name: Name of the checkpoint to validate
            data: Data to validate (varies by checkpoint)

        Returns:
            ValidationResult with all check outcomes
        """
        if checkpoint_name not in self.checkpoints:
            logger.warning(f"Unknown checkpoint: {checkpoint_name}")
            return ValidationResult(
                checkpoint=checkpoint_name,
                passed=True,
                blocking=False,
            )

        config = self.checkpoints[checkpoint_name]
        blocking = self.strict_mode or config.get("blocking", False)

        result = ValidationResult(
            checkpoint=checkpoint_name,
            passed=True,
            blocking=blocking,
        )

        # Run each check
        for check_name, check_fn in config.get("checks", []):
            try:
                passed, message = check_fn(data)
                check_result = CheckResult(
                    check_name=check_name,
                    passed=passed,
                    message=message,
                )
                result.add_result(check_result)

                if passed:
                    logger.debug(f"Checkpoint {checkpoint_name}/{check_name}: PASS - {message}")
                else:
                    logger.warning(f"Checkpoint {checkpoint_name}/{check_name}: FAIL - {message}")

            except Exception as e:
                logger.error(f"Check {check_name} raised exception: {e}")
                result.add_result(CheckResult(
                    check_name=check_name,
                    passed=False,
                    message=f"Check failed with error: {str(e)}",
                ))

        # Record in history
        self.history.append(result)

        # Log summary
        status = "PASS" if result.passed else "FAIL"
        block_text = " [BLOCKING]" if result.blocking and not result.passed else ""
        logger.info(f"Checkpoint {checkpoint_name}: {status}{block_text}")

        return result

    def validate_all(
        self,
        stage_data: Dict[str, Any],
    ) -> Dict[str, ValidationResult]:
        """Validate multiple checkpoints at once.

        Args:
            stage_data: Dict mapping checkpoint names to their data

        Returns:
            Dict mapping checkpoint names to their results
        """
        results = {}
        for checkpoint_name, data in stage_data.items():
            if checkpoint_name in self.checkpoints:
                results[checkpoint_name] = self.validate(checkpoint_name, data)
        return results

    def get_history(self) -> List[ValidationResult]:
        """Get all validation results from this run."""
        return self.history

    def get_failed_checkpoints(
        self,
        blocking_only: bool = False,
    ) -> List[ValidationResult]:
        """Get list of failed checkpoints.

        Args:
            blocking_only: If True, only return blocking failures

        Returns:
            List of failed ValidationResults
        """
        failed = [r for r in self.history if not r.passed]
        if blocking_only:
            failed = [r for r in failed if r.blocking]
        return failed

    def has_blocking_failures(self) -> bool:
        """Check if any blocking checkpoints failed."""
        return any(not r.passed and r.blocking for r in self.history)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all checkpoint validations."""
        total = len(self.history)
        passed = sum(1 for r in self.history if r.passed)
        failed = total - passed
        blocking_failed = sum(1 for r in self.history if not r.passed and r.blocking)

        return {
            "totalCheckpoints": total,
            "passed": passed,
            "failed": failed,
            "blockingFailures": blocking_failed,
            "checkpoints": {r.checkpoint: r.passed for r in self.history},
        }

    def reset(self) -> None:
        """Reset checkpoint history."""
        self.history = []

    def add_custom_check(
        self,
        checkpoint_name: str,
        check_name: str,
        check_fn: Callable[[Any], Tuple[bool, str]],
    ) -> None:
        """Add a custom check to a checkpoint.

        Args:
            checkpoint_name: Name of checkpoint to add to
            check_name: Name for the new check
            check_fn: Check function (takes data, returns (passed, message))
        """
        if checkpoint_name not in self.checkpoints:
            self.checkpoints[checkpoint_name] = {
                "blocking": False,
                "checks": [],
            }

        self.checkpoints[checkpoint_name]["checks"].append((check_name, check_fn))


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def get_checkpoint_manager(strict_mode: bool = False) -> CheckpointManager:
    """Get a checkpoint manager instance.

    Args:
        strict_mode: If True, treat all checkpoints as blocking

    Returns:
        CheckpointManager instance
    """
    return CheckpointManager(strict_mode=strict_mode)
