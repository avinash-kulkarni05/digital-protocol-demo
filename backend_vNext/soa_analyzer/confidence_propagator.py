"""
Confidence Propagator - Score Propagation Through Pipeline Stages

This module handles the calculation and propagation of confidence scores
as values flow through the SOA extraction pipeline. It provides:
- Stage-weighted confidence calculations
- Entity-level confidence aggregation
- Confidence decay through transformation chains
- Quality threshold evaluation

Usage:
    propagator = ConfidencePropagator()
    final_conf = propagator.calculate_final(stage_confidences)
    entity_conf = propagator.aggregate_entity("visit", cell_confidences)
"""

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfidencePropagator:
    """Propagate confidence scores through pipeline stages.

    Uses weighted geometric mean for stage combination and entity-specific
    aggregation strategies for different entity types.
    """

    # Stage weights for final confidence calculation
    # Weights reflect the importance of each stage to overall accuracy
    STAGE_WEIGHTS = {
        "detection": 0.10,        # SOA page/table detection
        "ocr": 0.20,              # OCR/extraction quality
        "parsing": 0.15,          # Name/timing parsing
        "footnote": 0.10,         # Footnote extraction
        "cell_linking": 0.15,     # Footnote-to-cell linking
        "transformation": 0.15,   # USDM transformation
        "enrichment": 0.05,       # CDISC enrichment
        "validation": 0.10,       # Validation checks
    }

    # Minimum confidence floor (prevents zero propagation)
    MIN_CONFIDENCE = 0.01

    # Decay factor per transformation step
    DECAY_PER_STEP = 0.98

    def __init__(
        self,
        stage_weights: Optional[Dict[str, float]] = None,
        min_confidence: float = 0.01,
    ):
        """Initialize confidence propagator.

        Args:
            stage_weights: Custom stage weights (defaults to STAGE_WEIGHTS)
            min_confidence: Minimum confidence floor
        """
        self.stage_weights = stage_weights or self.STAGE_WEIGHTS.copy()
        self.min_confidence = min_confidence

        # Normalize weights to sum to 1.0
        total = sum(self.stage_weights.values())
        if total > 0:
            self.stage_weights = {
                k: v / total for k, v in self.stage_weights.items()
            }

    # =========================================================================
    # STAGE-LEVEL PROPAGATION
    # =========================================================================

    def calculate_final(self, stage_confidences: Dict[str, float]) -> float:
        """Calculate final confidence from stage confidences.

        Uses weighted geometric mean for robust combination that penalizes
        low confidence in any stage.

        Args:
            stage_confidences: Dict mapping stage names to confidence scores

        Returns:
            Final aggregated confidence score (0-1)
        """
        if not stage_confidences:
            return 1.0

        # Calculate weighted log sum (geometric mean approach)
        log_sum = 0.0
        total_weight = 0.0

        for stage, confidence in stage_confidences.items():
            weight = self.stage_weights.get(stage, 0.1)
            # Clamp confidence to prevent log(0)
            clamped_conf = max(confidence, self.min_confidence)
            log_sum += weight * math.log(clamped_conf)
            total_weight += weight

        if total_weight == 0:
            return 1.0

        # Geometric mean
        final = math.exp(log_sum / total_weight) if total_weight > 0 else 1.0

        return self._clamp(final)

    def propagate_through_stages(
        self,
        initial_confidence: float,
        stages: List[str],
        stage_factors: Optional[Dict[str, float]] = None,
    ) -> float:
        """Propagate confidence through a sequence of stages.

        Applies multiplicative decay with optional per-stage factors.

        Args:
            initial_confidence: Starting confidence
            stages: Ordered list of stage names
            stage_factors: Optional confidence factors per stage

        Returns:
            Final propagated confidence
        """
        confidence = initial_confidence
        stage_factors = stage_factors or {}

        for stage in stages:
            factor = stage_factors.get(stage, self.DECAY_PER_STEP)
            confidence *= factor

        return self._clamp(confidence)

    # =========================================================================
    # ENTITY-LEVEL AGGREGATION
    # =========================================================================

    def aggregate_entity(
        self,
        entity_type: str,
        cell_confidences: List[float],
        strategy: Optional[str] = None,
    ) -> float:
        """Aggregate cell confidences for an entity.

        Uses entity-type-specific strategies:
        - visit/encounter: Conservative (minimum) - any low confidence affects quality
        - activity: Average - balance across cells
        - footnote: Weighted average by position count

        Args:
            entity_type: Type of entity (visit, activity, footnote, etc.)
            cell_confidences: List of confidence scores to aggregate
            strategy: Override strategy (min, avg, max, median)

        Returns:
            Aggregated confidence score
        """
        if not cell_confidences:
            return 1.0

        # Determine strategy based on entity type
        if strategy:
            agg_strategy = strategy
        elif entity_type in ("visit", "encounter"):
            agg_strategy = "min"  # Conservative for critical entities
        elif entity_type == "activity":
            agg_strategy = "avg"
        elif entity_type == "footnote":
            agg_strategy = "weighted_avg"
        else:
            agg_strategy = "avg"

        # Apply aggregation
        if agg_strategy == "min":
            return min(cell_confidences)
        elif agg_strategy == "max":
            return max(cell_confidences)
        elif agg_strategy == "median":
            sorted_conf = sorted(cell_confidences)
            n = len(sorted_conf)
            if n % 2 == 0:
                return (sorted_conf[n // 2 - 1] + sorted_conf[n // 2]) / 2
            return sorted_conf[n // 2]
        elif agg_strategy == "weighted_avg":
            # Weight by position (earlier cells more important)
            weights = [1.0 / (i + 1) for i in range(len(cell_confidences))]
            total_weight = sum(weights)
            return sum(c * w for c, w in zip(cell_confidences, weights)) / total_weight
        else:  # avg
            return sum(cell_confidences) / len(cell_confidences)

    # =========================================================================
    # TRANSFORMATION CHAIN PROPAGATION
    # =========================================================================

    def propagate_chain(
        self,
        transformation_confidences: List[float],
        initial_confidence: float = 1.0,
    ) -> float:
        """Calculate final confidence from transformation chain.

        Uses multiplicative propagation with decay for each step.

        Args:
            transformation_confidences: List of confidence scores for each step
            initial_confidence: Starting confidence (e.g., OCR confidence)

        Returns:
            Final propagated confidence
        """
        confidence = initial_confidence

        for step_confidence in transformation_confidences:
            # Multiplicative with decay
            confidence *= step_confidence * self.DECAY_PER_STEP

        return self._clamp(confidence)

    def calculate_chain_confidence(
        self,
        steps: List[Dict[str, Any]],
    ) -> float:
        """Calculate confidence from a list of transformation steps.

        Args:
            steps: List of step dicts with 'confidence_out' keys

        Returns:
            Final chain confidence
        """
        if not steps:
            return 1.0

        confidences = [s.get("confidence_out", 1.0) for s in steps]
        return self.propagate_chain(confidences)

    # =========================================================================
    # QUALITY THRESHOLD EVALUATION
    # =========================================================================

    def evaluate_quality(
        self,
        confidence: float,
        thresholds: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Evaluate confidence against quality thresholds.

        Args:
            confidence: Confidence score to evaluate
            thresholds: Custom thresholds (defaults below)

        Returns:
            Evaluation result with pass/fail and recommendations
        """
        thresholds = thresholds or {
            "excellent": 0.95,
            "good": 0.80,
            "acceptable": 0.60,
            "needs_review": 0.40,
        }

        if confidence >= thresholds.get("excellent", 0.95):
            rating = "excellent"
            passes = True
            needs_review = False
        elif confidence >= thresholds.get("good", 0.80):
            rating = "good"
            passes = True
            needs_review = False
        elif confidence >= thresholds.get("acceptable", 0.60):
            rating = "acceptable"
            passes = True
            needs_review = True
        elif confidence >= thresholds.get("needs_review", 0.40):
            rating = "low"
            passes = False
            needs_review = True
        else:
            rating = "very_low"
            passes = False
            needs_review = True

        return {
            "confidence": confidence,
            "rating": rating,
            "passes_threshold": passes,
            "needs_review": needs_review,
            "recommendation": self._get_recommendation(rating),
        }

    def _get_recommendation(self, rating: str) -> str:
        """Get recommendation based on quality rating."""
        recommendations = {
            "excellent": "High confidence extraction, minimal review needed",
            "good": "Good quality, spot-check recommended",
            "acceptable": "Review flagged items before production use",
            "low": "Manual review required for critical fields",
            "very_low": "Re-extraction or manual entry recommended",
        }
        return recommendations.get(rating, "Review recommended")

    # =========================================================================
    # LINKING-SPECIFIC CONFIDENCE
    # =========================================================================

    def calculate_linking_confidence(
        self,
        strategy: str,
        markers_linked: int,
        total_markers: int,
        ambiguous_count: int,
        avg_link_confidence: float,
    ) -> float:
        """Calculate overall confidence for footnote linking.

        Args:
            strategy: Linking strategy used (llm_cell_level, llm_semantic, heuristic)
            markers_linked: Number of markers successfully linked
            total_markers: Total number of markers
            ambiguous_count: Number of ambiguously linked markers
            avg_link_confidence: Average confidence of individual links

        Returns:
            Overall linking confidence score
        """
        # Base confidence by strategy
        strategy_base = {
            "llm_cell_level": 0.95,
            "llm_semantic": 0.80,
            "existing_heuristic": 0.60,
            "none": 0.30,
        }
        base = strategy_base.get(strategy.lower(), 0.70)

        # Coverage factor
        coverage = markers_linked / max(total_markers, 1)

        # Ambiguity penalty
        ambiguity_rate = ambiguous_count / max(markers_linked, 1)
        ambiguity_factor = 1.0 - (ambiguity_rate * 0.3)

        # Combine factors
        confidence = base * coverage * ambiguity_factor * avg_link_confidence

        return self._clamp(confidence)

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _clamp(self, value: float) -> float:
        """Clamp confidence to valid range [min, 1.0]."""
        return max(self.min_confidence, min(1.0, value))


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def get_confidence_propagator(
    stage_weights: Optional[Dict[str, float]] = None,
) -> ConfidencePropagator:
    """Get a confidence propagator instance.

    Args:
        stage_weights: Optional custom stage weights

    Returns:
        ConfidencePropagator instance
    """
    return ConfidencePropagator(stage_weights=stage_weights)
