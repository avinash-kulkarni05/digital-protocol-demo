"""
Stage 10: Human Review Assembly

Aggregates review items from all pipeline stages (1-9, 12) into an API-ready
structure for React/Vue UI consumption.

Usage:
    from soa_analyzer.interpretation.stage10_human_review import (
        HumanReviewAssembler,
        assemble_review_package,
    )

    # Option 1: Class-based
    assembler = HumanReviewAssembler()
    result = assembler.assemble_review_package(stage_results, protocol_id, protocol_name)
    api_response = result.package.to_api()

    # Option 2: Convenience function
    package, result = assemble_review_package(
        stage_results, protocol_id, protocol_name, auto_approve_threshold=0.95
    )
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models.human_review import (
    BatchReviewRequest,
    HumanReviewPackage,
    ProvenanceDisplay,
    ReasoningDisplay,
    ReviewAction,
    ReviewDecisionRequest,
    ReviewItemType,
    ReviewOption,
    ReviewPriority,
    Stage10Config,
    Stage10Result,
    StageReviewSection,
    UnifiedReviewItem,
)
from ..models.expansion_proposal import HumanReviewItem, ReviewStatus

logger = logging.getLogger(__name__)


# =============================================================================
# MAIN HANDLER CLASS
# =============================================================================


class HumanReviewAssembler:
    """
    Stage 10: Aggregate review items from all stages into API-ready package.

    This handler collects review items from stage results, converts them to
    a unified format, and organizes them by stage for UI consumption.
    """

    def __init__(self, config: Optional[Stage10Config] = None):
        """Initialize the assembler."""
        self.config = config or Stage10Config()
        self._stage_info: Dict[int, Dict[str, Any]] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load stage configuration from JSON file."""
        config_path = Path(__file__).parent.parent / "config" / "review_config.json"
        try:
            if config_path.exists():
                with open(config_path, "r") as f:
                    data = json.load(f)
                    self._stage_info = {
                        int(k): v for k, v in data.get("stage_info", {}).items()
                    }
                    # Update thresholds from config if present
                    thresholds = data.get("confidence_thresholds", {})
                    if "auto_approve" in thresholds:
                        self.config.auto_approve_threshold = thresholds["auto_approve"]
                    if "high" in thresholds:
                        self.config.confidence_threshold_high = thresholds["high"]
                    if "medium" in thresholds:
                        self.config.confidence_threshold_medium = thresholds["medium"]
            else:
                logger.warning(f"Review config not found at {config_path}")
                self._init_default_stage_info()
        except Exception as e:
            logger.error(f"Error loading review config: {e}")
            self._init_default_stage_info()

    def _init_default_stage_info(self) -> None:
        """Initialize default stage information."""
        self._stage_info = {
            1: {"name": "Domain Categorization", "description": "CDISC domain assignments", "priority_default": "medium"},
            2: {"name": "Activity Expansion", "description": "Activity decomposition", "priority_default": "high"},
            3: {"name": "Hierarchy Building", "description": "Activity grouping", "priority_default": "medium"},
            4: {"name": "Alternative Resolution", "description": "Alternative choices", "priority_default": "critical"},
            5: {"name": "Specimen Enrichment", "description": "Specimen details", "priority_default": "high"},
            6: {"name": "Conditional Expansion", "description": "Condition applications", "priority_default": "high"},
            7: {"name": "Timing Distribution", "description": "Timing expansions", "priority_default": "high"},
            8: {"name": "Cycle Expansion", "description": "Cycle patterns", "priority_default": "critical"},
            9: {"name": "Protocol Mining", "description": "Cross-references", "priority_default": "medium"},
            12: {"name": "USDM Compliance", "description": "Code validation", "priority_default": "low"},
        }

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    def assemble_review_package(
        self,
        stage_results: Dict[int, Any],
        protocol_id: str,
        protocol_name: str,
    ) -> Stage10Result:
        """
        Assemble review items from all stage results.

        Args:
            stage_results: Dict of stage_number -> stage result object
            protocol_id: Protocol identifier
            protocol_name: Protocol display name

        Returns:
            Stage10Result with HumanReviewPackage
        """
        start_time = time.time()
        result = Stage10Result()
        result.package.protocol_id = protocol_id
        result.package.protocol_name = protocol_name

        try:
            # Collect items from each stage
            all_sections: List[StageReviewSection] = []

            for stage_num in sorted(stage_results.keys()):
                stage_result = stage_results[stage_num]
                if stage_result is None:
                    continue

                items = self._collect_items_from_stage(stage_num, stage_result)
                if items or self.config.include_empty_sections:
                    section = self._build_section(stage_num, items)
                    all_sections.append(section)

                    # Update metrics
                    result.items_by_stage[stage_num] = len(items)
                    for item in items:
                        result.items_by_type[item.item_type.value] = (
                            result.items_by_type.get(item.item_type.value, 0) + 1
                        )
                        result.items_by_priority[item.priority.value] = (
                            result.items_by_priority.get(item.priority.value, 0) + 1
                        )

            # Build the package
            result.package.sections = all_sections
            result.package.calculate_stats()
            result.items_collected = result.package.total_items

            # Include draft schedule from Stage 11 if available
            stage11_result = stage_results.get(11)
            if stage11_result:
                if hasattr(stage11_result, "draft_usdm") and stage11_result.draft_usdm:
                    result.package.draft_schedule = stage11_result.draft_usdm
                    result.package.draft_generation_summary = {
                        "autoApprovedCount": getattr(stage11_result, "auto_approved_count", 0),
                        "pendingReviewCount": getattr(stage11_result, "pending_review_count", 0),
                        "pendingCriticalCount": getattr(stage11_result, "pending_critical", 0),
                        "reviewItemLinks": getattr(stage11_result, "review_item_links", {}),
                    }
                    logger.info(f"Included draft schedule in review package")
                elif hasattr(stage11_result, "final_usdm") and stage11_result.final_usdm:
                    # Stage 11 ran in final mode (not draft)
                    result.package.draft_schedule = stage11_result.final_usdm
                    logger.info(f"Included final schedule in review package")

        except Exception as e:
            logger.error(f"Error assembling review package: {e}")
            result.errors.append(str(e))

        result.processing_time_seconds = time.time() - start_time
        return result

    # =========================================================================
    # STAGE-SPECIFIC COLLECTORS
    # =========================================================================

    def _collect_items_from_stage(
        self,
        stage_num: int,
        stage_result: Any,
    ) -> List[UnifiedReviewItem]:
        """Collect review items from a stage result."""
        collectors = {
            1: self._collect_stage1_items,
            2: self._collect_stage2_items,
            3: self._collect_stage3_items,
            4: self._collect_stage4_items,
            5: self._collect_stage5_items,
            6: self._collect_stage6_items,
            7: self._collect_stage7_items,
            8: self._collect_stage8_items,
            9: self._collect_stage9_items,
            12: self._collect_stage12_items,
        }

        collector = collectors.get(stage_num)
        if collector:
            try:
                return collector(stage_result)
            except Exception as e:
                logger.error(f"Error collecting items from stage {stage_num}: {e}")
                return []
        return []

    def _collect_stage1_items(self, result: Any) -> List[UnifiedReviewItem]:
        """Collect domain mapping review items from Stage 1."""
        items = []
        review_items = getattr(result, "review_items", [])

        for item in review_items:
            unified = self._convert_human_review_item(item, 1, ReviewItemType.DOMAIN_MAPPING)
            if unified:
                items.append(unified)

        return items

    def _collect_stage2_items(self, result: Any) -> List[UnifiedReviewItem]:
        """Collect activity expansion review items from Stage 2."""
        items = []
        review_items = getattr(result, "review_items", [])

        for item in review_items:
            item_type = ReviewItemType.ACTIVITY_EXPANSION
            if hasattr(item, "item_type") and "component" in str(item.item_type).lower():
                item_type = ReviewItemType.COMPONENT_ADDITION
            unified = self._convert_human_review_item(item, 2, item_type)
            if unified:
                items.append(unified)

        return items

    def _collect_stage3_items(self, result: Any) -> List[UnifiedReviewItem]:
        """Collect hierarchy building review items from Stage 3."""
        items = []
        review_items = getattr(result, "review_items", [])

        for item in review_items:
            unified = self._convert_human_review_item(item, 3, ReviewItemType.HIERARCHY_GROUPING)
            if unified:
                items.append(unified)

        return items

    def _collect_stage4_items(self, result: Any) -> List[UnifiedReviewItem]:
        """Collect alternative resolution review items from Stage 4."""
        items = []

        # Stage4Result has review_items list
        review_items = getattr(result, "review_items", [])
        for item in review_items:
            unified = self._convert_human_review_item(item, 4, ReviewItemType.ALTERNATIVE_CHOICE)
            if unified:
                # Stage 4 items are typically critical
                unified.priority = ReviewPriority.CRITICAL
                items.append(unified)

        # Also check resolutions for items needing review
        resolutions = getattr(result, "resolutions", [])
        for resolution in resolutions:
            if getattr(resolution, "requires_human_review", False):
                unified = self._create_unified_from_resolution(resolution, 4)
                if unified:
                    items.append(unified)

        return items

    def _collect_stage5_items(self, result: Any) -> List[UnifiedReviewItem]:
        """Collect specimen enrichment review items from Stage 5."""
        items = []
        review_items = getattr(result, "review_items", [])

        for item in review_items:
            item_type = ReviewItemType.SPECIMEN_TYPE
            if hasattr(item, "item_type"):
                if "tube" in str(item.item_type).lower():
                    item_type = ReviewItemType.TUBE_TYPE
                elif "collection" in str(item.item_type).lower():
                    item_type = ReviewItemType.COLLECTION_DETAIL
            unified = self._convert_human_review_item(item, 5, item_type)
            if unified:
                items.append(unified)

        return items

    def _collect_stage6_items(self, result: Any) -> List[UnifiedReviewItem]:
        """Collect conditional expansion review items from Stage 6."""
        items = []
        review_items = getattr(result, "review_items", [])

        for item in review_items:
            unified = self._convert_human_review_item(item, 6, ReviewItemType.CONDITION_APPLICATION)
            if unified:
                items.append(unified)

        return items

    def _collect_stage7_items(self, result: Any) -> List[UnifiedReviewItem]:
        """Collect timing distribution review items from Stage 7."""
        items = []
        review_items = getattr(result, "review_items", [])

        for item in review_items:
            item_type = ReviewItemType.TIMING_EXPANSION
            if hasattr(item, "item_type") and "bi_eoi" in str(item.item_type).lower():
                item_type = ReviewItemType.BI_EOI_SPLIT
            unified = self._convert_human_review_item(item, 7, item_type)
            if unified:
                items.append(unified)

        return items

    def _collect_stage8_items(self, result: Any) -> List[UnifiedReviewItem]:
        """Collect cycle expansion review items from Stage 8."""
        items = []
        review_items = getattr(result, "review_items", [])

        for item in review_items:
            item_type = ReviewItemType.CYCLE_COUNT
            if hasattr(item, "item_type") and "pattern" in str(item.item_type).lower():
                item_type = ReviewItemType.CYCLE_PATTERN
            unified = self._convert_human_review_item(item, 8, item_type)
            if unified:
                # Cycle decisions are typically critical
                unified.priority = ReviewPriority.CRITICAL
                items.append(unified)

        return items

    def _collect_stage9_items(self, result: Any) -> List[UnifiedReviewItem]:
        """Collect protocol mining review items from Stage 9."""
        items = []
        review_items = getattr(result, "review_items", [])

        for item in review_items:
            # Stage 9 review items may be dicts
            if isinstance(item, dict):
                unified = self._create_unified_from_dict(item, 9, ReviewItemType.PROTOCOL_ENRICHMENT)
            else:
                unified = self._convert_human_review_item(item, 9, ReviewItemType.PROTOCOL_ENRICHMENT)
            if unified:
                items.append(unified)

        return items

    def _collect_stage12_items(self, result: Any) -> List[UnifiedReviewItem]:
        """Collect USDM compliance review items from Stage 12."""
        items = []
        review_items = getattr(result, "review_items", [])

        for item in review_items:
            unified = self._convert_human_review_item(item, 12, ReviewItemType.CODE_VALIDATION)
            if unified:
                unified.priority = ReviewPriority.LOW
                items.append(unified)

        return items

    # =========================================================================
    # TRANSFORMATION HELPERS
    # =========================================================================

    def _convert_human_review_item(
        self,
        item: Any,
        stage: int,
        item_type: ReviewItemType,
    ) -> Optional[UnifiedReviewItem]:
        """Convert existing HumanReviewItem to UnifiedReviewItem."""
        if item is None:
            return None

        try:
            stage_info = self._stage_info.get(stage, {})
            priority_default = stage_info.get("priority_default", "medium")

            # Extract options
            options = []
            raw_options = getattr(item, "options", [])
            for idx, opt in enumerate(raw_options):
                if isinstance(opt, dict):
                    options.append(ReviewOption.from_dict(opt))
                else:
                    options.append(ReviewOption(
                        id=f"OPT-{idx}",
                        label=str(opt),
                        description="",
                    ))

            # Create unified item
            unified = UnifiedReviewItem(
                id=getattr(item, "id", None) or f"REV-{stage}-{id(item)}",
                stage=stage,
                stage_name=stage_info.get("name", f"Stage {stage}"),
                item_type=item_type,
                title=getattr(item, "title", "") or f"{item_type.value} review",
                description=getattr(item, "description", ""),
                priority=self._parse_priority(getattr(item, "priority", priority_default)),
                source_entity_id=getattr(item, "source_entity_id", "") or "",
                source_entity_type=getattr(item, "source_entity_type", "") or "entity",
                source_entity_name=getattr(item, "source_entity_name", "") or "",
                options=options,
                allows_custom_value=True,
                action=self._convert_status(getattr(item, "status", ReviewStatus.PENDING)),
                selected_option_id=getattr(item, "selected_option", None),
                custom_value=getattr(item, "custom_value", None),
                reviewer_notes=getattr(item, "reviewer_notes", None),
                confidence=getattr(item, "confidence", 0.0),
                provenance=self._extract_provenance(item),
                reasoning=self._extract_reasoning(item),
                _original_item=item,
            )

            return unified

        except Exception as e:
            logger.error(f"Error converting review item: {e}")
            return None

    def _create_unified_from_dict(
        self,
        data: Dict[str, Any],
        stage: int,
        item_type: ReviewItemType,
    ) -> Optional[UnifiedReviewItem]:
        """Create UnifiedReviewItem from a dictionary."""
        try:
            stage_info = self._stage_info.get(stage, {})

            # Extract options
            options = []
            for opt in data.get("options", []):
                if isinstance(opt, dict):
                    options.append(ReviewOption.from_dict(opt))

            unified = UnifiedReviewItem(
                id=data.get("id", f"REV-{stage}-{id(data)}"),
                stage=stage,
                stage_name=stage_info.get("name", f"Stage {stage}"),
                item_type=item_type,
                title=data.get("title", f"{item_type.value} review"),
                description=data.get("description", ""),
                priority=self._parse_priority(data.get("priority", stage_info.get("priority_default", "medium"))),
                source_entity_id=data.get("source_entity_id", data.get("activity_id", "")),
                source_entity_type=data.get("source_entity_type", "activity"),
                source_entity_name=data.get("source_entity_name", data.get("activity_name", "")),
                options=options,
                confidence=data.get("confidence", 0.0),
                provenance=ProvenanceDisplay.from_dict(data.get("provenance", {})),
                reasoning=ReasoningDisplay.from_dict(data.get("reasoning", {})),
            )

            return unified

        except Exception as e:
            logger.error(f"Error creating unified item from dict: {e}")
            return None

    def _create_unified_from_resolution(
        self,
        resolution: Any,
        stage: int,
    ) -> Optional[UnifiedReviewItem]:
        """Create UnifiedReviewItem from a resolution object."""
        try:
            stage_info = self._stage_info.get(stage, {})

            # Build options from alternatives
            options = []
            alternatives = getattr(resolution, "alternatives", [])
            for alt in alternatives:
                option = ReviewOption(
                    id=getattr(alt, "id", f"ALT-{id(alt)}"),
                    label=getattr(alt, "name", str(alt)),
                    description=getattr(alt, "description", ""),
                    is_recommended=getattr(alt, "is_recommended", False),
                    confidence=getattr(alt, "confidence", 0.0),
                )
                options.append(option)

            unified = UnifiedReviewItem(
                id=f"REV-RES-{id(resolution)}",
                stage=stage,
                stage_name=stage_info.get("name", f"Stage {stage}"),
                item_type=ReviewItemType.ALTERNATIVE_CHOICE,
                title=getattr(resolution, "description", "Alternative choice"),
                description=getattr(resolution, "rationale", ""),
                priority=ReviewPriority.CRITICAL,
                source_entity_id=getattr(resolution, "activity_id", ""),
                source_entity_type="activity",
                source_entity_name=getattr(resolution, "activity_name", ""),
                options=options,
                confidence=getattr(resolution, "confidence", 0.0),
                provenance=self._extract_provenance(resolution),
                reasoning=self._extract_reasoning(resolution),
            )

            return unified

        except Exception as e:
            logger.error(f"Error creating unified item from resolution: {e}")
            return None

    def _extract_provenance(self, item: Any) -> Optional[ProvenanceDisplay]:
        """Extract provenance from various item formats."""
        provenance_data = getattr(item, "provenance", None)
        if provenance_data is None:
            return None

        if isinstance(provenance_data, dict):
            return ProvenanceDisplay.from_dict(provenance_data)

        # Try to extract from ProvenanceRecord or similar
        try:
            return ProvenanceDisplay(
                page_numbers=getattr(provenance_data, "page_numbers", []),
                text_snippets=getattr(provenance_data, "text_snippets", []),
                source_table=getattr(provenance_data, "source_table", None),
                extraction_model=getattr(provenance_data, "model_name", None),
            )
        except Exception:
            return None

    def _extract_reasoning(self, item: Any) -> Optional[ReasoningDisplay]:
        """Extract reasoning/rationale from various item formats."""
        # Check for direct rationale field
        rationale = getattr(item, "rationale", None)
        if rationale:
            return ReasoningDisplay(
                rationale=rationale,
                model_used=getattr(item, "model_used", None),
            )

        # Check for reasoning dict
        reasoning_data = getattr(item, "reasoning", None)
        if reasoning_data:
            if isinstance(reasoning_data, dict):
                return ReasoningDisplay.from_dict(reasoning_data)

        # Check for match_rationale (from Stage 9)
        match_rationale = getattr(item, "match_rationale", None)
        if match_rationale:
            return ReasoningDisplay(
                rationale=str(match_rationale) if not isinstance(match_rationale, str) else match_rationale,
                model_used=getattr(item, "model_used", None),
            )

        return None

    def _parse_priority(self, priority: Any) -> ReviewPriority:
        """Parse priority from various formats."""
        if isinstance(priority, ReviewPriority):
            return priority
        if isinstance(priority, str):
            priority_lower = priority.lower()
            if priority_lower == "critical":
                return ReviewPriority.CRITICAL
            elif priority_lower == "high":
                return ReviewPriority.HIGH
            elif priority_lower == "low":
                return ReviewPriority.LOW
        return ReviewPriority.MEDIUM

    def _convert_status(self, status: Any) -> ReviewAction:
        """Convert ReviewStatus to ReviewAction."""
        if isinstance(status, ReviewAction):
            return status
        if isinstance(status, ReviewStatus):
            mapping = {
                ReviewStatus.PENDING: ReviewAction.PENDING,
                ReviewStatus.APPROVED: ReviewAction.APPROVED,
                ReviewStatus.REJECTED: ReviewAction.REJECTED,
                ReviewStatus.MODIFIED: ReviewAction.MODIFIED,
            }
            return mapping.get(status, ReviewAction.PENDING)
        return ReviewAction.PENDING

    # =========================================================================
    # SECTION BUILDING
    # =========================================================================

    def _build_section(
        self,
        stage: int,
        items: List[UnifiedReviewItem],
    ) -> StageReviewSection:
        """Build a stage section with aggregated statistics."""
        stage_info = self._stage_info.get(stage, {})

        # Sort items if configured
        if self.config.sort_items_by_priority:
            priority_order = {
                ReviewPriority.CRITICAL: 0,
                ReviewPriority.HIGH: 1,
                ReviewPriority.MEDIUM: 2,
                ReviewPriority.LOW: 3,
            }
            items.sort(key=lambda x: (priority_order.get(x.priority, 99), -x.confidence))
        elif self.config.sort_items_by_confidence:
            items.sort(key=lambda x: -x.confidence)

        section = StageReviewSection(
            stage=stage,
            stage_name=stage_info.get("name", f"Stage {stage}"),
            description=stage_info.get("description", ""),
            items=items,
        )
        section.calculate_stats()

        return section

    # =========================================================================
    # DECISION APPLICATION
    # =========================================================================

    def apply_decisions(
        self,
        package: HumanReviewPackage,
        decisions: List[ReviewDecisionRequest],
    ) -> HumanReviewPackage:
        """Apply review decisions to package."""
        for decision in decisions:
            item = package.get_item_by_id(decision.item_id)
            if item:
                item.apply_decision(
                    action=decision.action,
                    selected_option_id=decision.selected_option_id,
                    custom_value=decision.custom_value,
                    reviewer_notes=decision.reviewer_notes,
                    reviewed_by=decision.reviewed_by,
                )

        # Recalculate stats
        package.calculate_stats()
        return package

    def apply_batch_decisions(
        self,
        package: HumanReviewPackage,
        batch: BatchReviewRequest,
    ) -> HumanReviewPackage:
        """Apply batch review decisions."""
        return self.apply_decisions(package, batch.decisions)

    # =========================================================================
    # AUTO-APPROVAL
    # =========================================================================

    def auto_approve_high_confidence(
        self,
        package: HumanReviewPackage,
        threshold: Optional[float] = None,
    ) -> Tuple[HumanReviewPackage, int]:
        """
        Auto-approve items above confidence threshold.

        Returns:
            Tuple of (updated package, count of auto-approved items)
        """
        threshold = threshold or self.config.auto_approve_threshold
        auto_approved = 0

        for section in package.sections:
            for item in section.items:
                if item.action == ReviewAction.PENDING and item.confidence >= threshold:
                    # Find the highest confidence option or use recommended
                    selected_option = None
                    for opt in item.options:
                        if opt.is_recommended:
                            selected_option = opt.id
                            break
                        if selected_option is None or opt.confidence > item.options[0].confidence:
                            selected_option = opt.id

                    item.apply_decision(
                        action=ReviewAction.APPROVED,
                        selected_option_id=selected_option,
                        reviewer_notes=f"Auto-approved (confidence: {item.confidence:.2f})",
                        reviewed_by="system",
                    )
                    auto_approved += 1

        package.calculate_stats()
        return package, auto_approved

    # =========================================================================
    # EXPORT FOR STAGE 11
    # =========================================================================

    def export_for_stage11(
        self,
        package: HumanReviewPackage,
    ) -> Dict[str, Any]:
        """
        Export approved decisions for Stage 11 Schedule Generation.

        Returns:
            Dict with decisions organized by stage, ready for schedule generation.
        """
        export = {
            "protocol_id": package.protocol_id,
            "protocol_name": package.protocol_name,
            "export_timestamp": datetime.now().isoformat(),
            "decisions_by_stage": {},
            "summary": {
                "total_approved": 0,
                "total_rejected": 0,
                "total_modified": 0,
                "total_pending": 0,
            },
        }

        for section in package.sections:
            stage_decisions = []
            for item in section.items:
                if item.action != ReviewAction.PENDING:
                    decision = {
                        "item_id": item.id,
                        "item_type": item.item_type.value,
                        "action": item.action.value,
                        "source_entity_id": item.source_entity_id,
                        "source_entity_name": item.source_entity_name,
                        "selected_option_id": item.selected_option_id,
                        "custom_value": item.custom_value,
                        "reviewer_notes": item.reviewer_notes,
                        "reviewed_by": item.reviewed_by,
                        "reviewed_at": item.reviewed_at,
                    }
                    stage_decisions.append(decision)

                    # Update summary
                    if item.action == ReviewAction.APPROVED:
                        export["summary"]["total_approved"] += 1
                    elif item.action == ReviewAction.REJECTED:
                        export["summary"]["total_rejected"] += 1
                    elif item.action == ReviewAction.MODIFIED:
                        export["summary"]["total_modified"] += 1
                else:
                    export["summary"]["total_pending"] += 1

            if stage_decisions:
                export["decisions_by_stage"][section.stage] = {
                    "stage_name": section.stage_name,
                    "decisions": stage_decisions,
                }

        return export


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


def assemble_review_package(
    stage_results: Dict[int, Any],
    protocol_id: str,
    protocol_name: str,
    auto_approve_threshold: Optional[float] = None,
) -> Tuple[HumanReviewPackage, Stage10Result]:
    """
    Convenience function for human review assembly.

    Args:
        stage_results: Dict of stage_number -> stage result object
        protocol_id: Protocol identifier
        protocol_name: Protocol display name
        auto_approve_threshold: If set, auto-approve items above this confidence

    Returns:
        Tuple of (HumanReviewPackage, Stage10Result)
    """
    assembler = HumanReviewAssembler()
    result = assembler.assemble_review_package(stage_results, protocol_id, protocol_name)

    if auto_approve_threshold is not None:
        result.package, auto_count = assembler.auto_approve_high_confidence(
            result.package, auto_approve_threshold
        )
        result.auto_approved_count = auto_count

    return result.package, result
