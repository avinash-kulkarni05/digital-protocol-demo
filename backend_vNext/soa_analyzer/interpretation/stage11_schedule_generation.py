"""
Stage 11: Schedule Generation

Applies human review decisions from Stage 10 to produce the final USDM-compliant schedule.
This stage transforms pending review items into concrete schedule modifications based on
approved/rejected/modified decisions.

Usage:
    from soa_analyzer.interpretation.stage11_schedule_generation import (
        ScheduleGenerator,
        Stage11Config,
        Stage11Result,
        generate_schedule,
    )

    # Option 1: Class-based
    generator = ScheduleGenerator()
    result = generator.generate_schedule(usdm_output, review_decisions)
    final_usdm = result.final_usdm

    # Option 2: Convenience function
    final_usdm, result = generate_schedule(usdm_output, review_decisions)
"""

import copy
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class Stage11Config:
    """Configuration for schedule generation."""

    # Draft mode settings (NEW)
    draft_mode: bool = True  # Generate draft with all options included for review
    auto_approve_non_critical: bool = True  # Auto-approve non-critical items in draft
    mark_review_status: bool = True  # Add _reviewStatus markers to entities

    # Behavior flags
    fail_on_pending_critical: bool = True  # Abort if critical items still pending (final mode only)
    include_rejected_provenance: bool = True  # Keep audit trail for rejected items
    generate_audit_trail: bool = True  # Generate detailed change log

    # Decision handling
    apply_auto_approved: bool = True  # Apply system auto-approved decisions
    strict_mode: bool = False  # If True, reject items without explicit approval

    # Output options
    remove_internal_fields: bool = True  # Remove _staging fields from output
    include_decision_metadata: bool = True  # Add _generatedBy metadata


# =============================================================================
# RESULT DATACLASS
# =============================================================================


@dataclass
class AuditEntry:
    """Single entry in the audit trail."""
    timestamp: str = ""
    stage: int = 0
    item_id: str = ""
    item_type: str = ""
    action: str = ""  # approved, rejected, modified
    entity_id: str = ""
    entity_name: str = ""
    change_description: str = ""
    reviewer: str = ""
    reviewer_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "stage": self.stage,
            "itemId": self.item_id,
            "itemType": self.item_type,
            "action": self.action,
            "entityId": self.entity_id,
            "entityName": self.entity_name,
            "changeDescription": self.change_description,
            "reviewer": self.reviewer,
            "reviewerNotes": self.reviewer_notes,
        }


@dataclass
class Stage11Result:
    """Result from schedule generation."""
    success: bool = False
    final_usdm: Optional[Dict[str, Any]] = None

    # Draft mode indicators
    is_draft: bool = False  # True if this is a draft (not final) schedule
    draft_usdm: Optional[Dict[str, Any]] = None  # Draft schedule with review markers

    # Metrics
    decisions_applied: int = 0
    decisions_skipped: int = 0
    pending_critical: int = 0
    pending_non_critical: int = 0

    # Draft-specific metrics
    auto_approved_count: int = 0  # Items auto-approved in draft mode
    pending_review_count: int = 0  # Items pending human review

    # Breakdown by action
    approved_count: int = 0
    rejected_count: int = 0
    modified_count: int = 0

    # Audit trail
    audit_trail: List[AuditEntry] = field(default_factory=list)

    # Review items with entity links (for draft mode)
    review_item_links: Dict[str, str] = field(default_factory=dict)  # item_id -> entity_id

    # Errors and warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Timing
    processing_time_seconds: float = 0.0

    def get_summary(self) -> str:
        """Get summary string."""
        if self.is_draft:
            return (
                f"Stage11 [DRAFT]: {'SUCCESS' if self.success else 'FAILED'} - "
                f"Auto-approved {self.auto_approved_count}, "
                f"pending review: {self.pending_review_count} "
                f"(critical={self.pending_critical})"
            )
        return (
            f"Stage11: {'SUCCESS' if self.success else 'FAILED'} - "
            f"Applied {self.decisions_applied} decisions "
            f"(approved={self.approved_count}, rejected={self.rejected_count}, modified={self.modified_count}), "
            f"skipped={self.decisions_skipped}, pending_critical={self.pending_critical}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "success": self.success,
            "isDraft": self.is_draft,
            "metrics": {
                "decisionsApplied": self.decisions_applied,
                "decisionsSkipped": self.decisions_skipped,
                "pendingCritical": self.pending_critical,
                "pendingNonCritical": self.pending_non_critical,
                "approvedCount": self.approved_count,
                "rejectedCount": self.rejected_count,
                "modifiedCount": self.modified_count,
                "autoApprovedCount": self.auto_approved_count,
                "pendingReviewCount": self.pending_review_count,
            },
            "auditTrail": [entry.to_dict() for entry in self.audit_trail],
            "reviewItemLinks": self.review_item_links,
            "errors": self.errors,
            "warnings": self.warnings,
            "processingTimeSeconds": self.processing_time_seconds,
        }
        return result


# =============================================================================
# MAIN HANDLER CLASS
# =============================================================================


class ScheduleGenerator:
    """
    Stage 11: Apply human review decisions and generate final schedule.

    This handler takes the USDM output from previous stages and applies
    the review decisions from Stage 10 to produce the final schedule.
    """

    # Stages that produce critical decisions
    CRITICAL_DECISION_STAGES = {4, 8}  # Alternative Resolution, Cycle Expansion

    # Mapping from item_type to application method
    DECISION_APPLICATORS = {
        "domain_mapping": "_apply_domain_decision",
        "activity_expansion": "_apply_expansion_decision",
        "component_addition": "_apply_expansion_decision",
        "hierarchy_grouping": "_apply_hierarchy_decision",
        "alternative_choice": "_apply_alternative_decision",
        "mutually_exclusive": "_apply_alternative_decision",
        "specimen_type": "_apply_specimen_decision",
        "tube_type": "_apply_specimen_decision",
        "collection_detail": "_apply_specimen_decision",
        "condition_application": "_apply_condition_decision",
        "population_filter": "_apply_condition_decision",
        "timing_expansion": "_apply_timing_decision",
        "bi_eoi_split": "_apply_timing_decision",
        "cycle_count": "_apply_cycle_decision",
        "cycle_pattern": "_apply_cycle_decision",
        "protocol_enrichment": "_apply_enrichment_decision",
        "endpoint_link": "_apply_enrichment_decision",
        "code_validation": "_apply_code_decision",
    }

    def __init__(self, config: Optional[Stage11Config] = None):
        """Initialize the schedule generator."""
        self.config = config or Stage11Config()
        self._entity_index: Dict[str, Dict[str, Any]] = {}

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    def generate_schedule(
        self,
        usdm_output: Dict[str, Any],
        review_decisions: Dict[str, Any],
    ) -> Stage11Result:
        """
        Apply review decisions from Stage 10 to generate final schedule.

        Args:
            usdm_output: USDM output from previous pipeline stages
            review_decisions: Output from Stage 10's export_for_stage11()

        Returns:
            Stage11Result with final USDM and audit trail
        """
        start_time = time.time()
        result = Stage11Result()

        try:
            # Make a deep copy to avoid mutating the input
            working_usdm = copy.deepcopy(usdm_output)

            # Build entity index for fast lookup
            self._build_entity_index(working_usdm)

            # Validate review_decisions format
            if not self._validate_decisions_format(review_decisions, result):
                return result

            # Check for pending critical items
            summary = review_decisions.get("summary", {})
            pending_count = summary.get("total_pending", 0)

            if pending_count > 0:
                # Count critical vs non-critical pending
                critical_pending = self._count_critical_pending(review_decisions)
                result.pending_critical = critical_pending
                result.pending_non_critical = pending_count - critical_pending

                if self.config.fail_on_pending_critical and critical_pending > 0:
                    result.errors.append(
                        f"Cannot generate schedule: {critical_pending} critical items still pending review"
                    )
                    result.processing_time_seconds = time.time() - start_time
                    return result

                if result.pending_non_critical > 0:
                    result.warnings.append(
                        f"{result.pending_non_critical} non-critical items pending review (proceeding anyway)"
                    )

            # Apply decisions by stage
            decisions_by_stage = review_decisions.get("decisions_by_stage", {})

            for stage_num, stage_data in sorted(decisions_by_stage.items(), key=lambda x: int(x[0])):
                stage_int = int(stage_num)
                stage_name = stage_data.get("stage_name", f"Stage {stage_int}")
                decisions = stage_data.get("decisions", [])

                logger.info(f"Applying {len(decisions)} decisions from {stage_name}")

                for decision in decisions:
                    applied = self._apply_decision(
                        working_usdm, decision, stage_int, result
                    )
                    if applied:
                        result.decisions_applied += 1
                    else:
                        result.decisions_skipped += 1

            # Clean up internal fields if configured
            if self.config.remove_internal_fields:
                self._remove_internal_fields(working_usdm)

            # Add generation metadata if configured
            if self.config.include_decision_metadata:
                working_usdm["_generationMetadata"] = {
                    "generatedAt": datetime.now().isoformat(),
                    "stage": 11,
                    "decisionsApplied": result.decisions_applied,
                    "protocolId": review_decisions.get("protocol_id", ""),
                }

            result.final_usdm = working_usdm
            result.success = True

        except Exception as e:
            logger.error(f"Error generating schedule: {e}", exc_info=True)
            result.errors.append(f"Schedule generation failed: {str(e)}")

        result.processing_time_seconds = time.time() - start_time
        logger.info(result.get_summary())

        return result

    # =========================================================================
    # DRAFT GENERATION (NEW)
    # =========================================================================

    def generate_draft_schedule(
        self,
        usdm_output: Dict[str, Any],
        stage_results: Dict[int, Any],
    ) -> Stage11Result:
        """
        Generate draft schedule with all options included for human review.

        In draft mode:
        - Non-critical items (stages 1,2,3,5,6,7,9,12) are auto-approved
        - Critical items (stages 4,8) include ALL options with review markers
        - All alternatives are shown (not just one)
        - All expanded cycles are shown
        - Entities are marked with _reviewStatus and _reviewItemId

        Args:
            usdm_output: USDM output from previous pipeline stages
            stage_results: Dictionary of results from stages 1-12

        Returns:
            Stage11Result with draft_usdm and review markers
        """
        start_time = time.time()
        result = Stage11Result()
        result.is_draft = True

        try:
            # Make a deep copy to avoid mutating the input
            working_usdm = copy.deepcopy(usdm_output)

            # Build entity index for fast lookup
            self._build_entity_index(working_usdm)

            # Collect review items from all stages
            review_items = self._collect_review_items_from_stages(stage_results)

            # Process each review item
            for item in review_items:
                stage = item.get("stage", 0)
                item_id = item.get("item_id", "")
                item_type = item.get("item_type", "")
                entity_id = item.get("entity_id", "")

                # Check if this is a critical item (stages 4, 8)
                is_critical = stage in self.CRITICAL_DECISION_STAGES

                if is_critical:
                    # Critical items: keep ALL options, mark for review
                    self._mark_entity_for_review(
                        working_usdm,
                        entity_id,
                        item_id,
                        item_type,
                        "pending_choice" if stage == 4 else "pending_confirmation",
                    )
                    result.pending_review_count += 1
                    result.pending_critical += 1
                    result.review_item_links[item_id] = entity_id
                else:
                    # Non-critical: auto-approve in draft mode
                    if self.config.auto_approve_non_critical:
                        self._mark_entity_for_review(
                            working_usdm,
                            entity_id,
                            item_id,
                            item_type,
                            "auto_approved",
                        )
                        result.auto_approved_count += 1
                    else:
                        self._mark_entity_for_review(
                            working_usdm,
                            entity_id,
                            item_id,
                            item_type,
                            "pending_review",
                        )
                        result.pending_review_count += 1
                        result.pending_non_critical += 1
                    result.review_item_links[item_id] = entity_id

            # Mark all alternatives for choice (Stage 4 items)
            self._mark_alternatives_for_review(working_usdm, stage_results, result)

            # Mark all expanded cycles for confirmation (Stage 8 items)
            self._mark_cycles_for_review(working_usdm, stage_results, result)

            # Add draft metadata
            working_usdm["_draftMetadata"] = {
                "generatedAt": datetime.now().isoformat(),
                "stage": 11,
                "isDraft": True,
                "autoApprovedCount": result.auto_approved_count,
                "pendingReviewCount": result.pending_review_count,
                "pendingCriticalCount": result.pending_critical,
            }

            result.draft_usdm = working_usdm
            result.final_usdm = working_usdm  # Also set final_usdm for compatibility
            result.success = True

        except Exception as e:
            logger.error(f"Error generating draft schedule: {e}", exc_info=True)
            result.errors.append(f"Draft schedule generation failed: {str(e)}")

        result.processing_time_seconds = time.time() - start_time
        logger.info(result.get_summary())

        return result

    def _collect_review_items_from_stages(
        self,
        stage_results: Dict[int, Any],
    ) -> List[Dict[str, Any]]:
        """Collect all review items from stage results."""
        review_items = []

        for stage_num, stage_result in stage_results.items():
            if stage_result is None:
                continue

            # Try to get review items from stage result
            items = []
            if hasattr(stage_result, "review_items"):
                items = stage_result.review_items or []
            elif hasattr(stage_result, "items_for_review"):
                items = stage_result.items_for_review or []
            elif isinstance(stage_result, dict):
                items = stage_result.get("review_items", []) or stage_result.get("items_for_review", [])

            for item in items:
                if isinstance(item, dict):
                    item["stage"] = stage_num
                    review_items.append(item)

        return review_items

    def _mark_entity_for_review(
        self,
        usdm: Dict[str, Any],
        entity_id: str,
        item_id: str,
        item_type: str,
        status: str,
    ) -> bool:
        """Mark an entity with review status."""
        if not entity_id:
            return False

        # Find entity in various collections
        for collection_name in ["activities", "encounters", "visits", "scheduledActivityInstances"]:
            collection = usdm.get(collection_name, [])
            for entity in collection:
                if entity.get("id") == entity_id:
                    entity["_reviewStatus"] = status
                    entity["_reviewItemId"] = item_id
                    entity["_reviewItemType"] = item_type
                    return True

        return False

    def _mark_alternatives_for_review(
        self,
        usdm: Dict[str, Any],
        stage_results: Dict[int, Any],
        result: Stage11Result,
    ) -> None:
        """Mark all alternative activities for human choice."""
        # Get Stage 4 result
        stage4_result = stage_results.get(4)
        if not stage4_result:
            return

        # Get alternative groups from Stage 4
        alternative_groups = {}
        if hasattr(stage4_result, "alternative_groups"):
            alternative_groups = stage4_result.alternative_groups or {}
        elif isinstance(stage4_result, dict):
            alternative_groups = stage4_result.get("alternative_groups", {})

        # Mark activities in each alternative group
        activities = usdm.get("activities", [])
        for group_id, group_data in alternative_groups.items():
            option_ids = group_data.get("option_ids", []) if isinstance(group_data, dict) else []

            for activity in activities:
                if activity.get("id") in option_ids:
                    activity["_alternativeGroup"] = group_id
                    activity["_alternativeOptions"] = option_ids
                    if activity.get("_reviewStatus") != "pending_choice":
                        activity["_reviewStatus"] = "pending_choice"

    def _mark_cycles_for_review(
        self,
        usdm: Dict[str, Any],
        stage_results: Dict[int, Any],
        result: Stage11Result,
    ) -> None:
        """Mark all expanded cycle encounters for human confirmation."""
        # Get Stage 8 result
        stage8_result = stage_results.get(8)
        if not stage8_result:
            return

        # Get expanded encounters from Stage 8
        expanded_encounters = []
        if hasattr(stage8_result, "expanded_encounters"):
            expanded_encounters = stage8_result.expanded_encounters or []
        elif isinstance(stage8_result, dict):
            expanded_encounters = stage8_result.get("expanded_encounters", [])
            # Also check encountersCreated
            created = stage8_result.get("encountersCreated", 0)
            if created > 0:
                # Mark encounters that have _expandedFrom field
                for encounter in usdm.get("encounters", usdm.get("visits", [])):
                    if encounter.get("_expandedFrom"):
                        if encounter.get("_reviewStatus") != "pending_confirmation":
                            encounter["_reviewStatus"] = "pending_confirmation"
                            encounter["_cycleExpanded"] = True

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_decisions_format(
        self,
        review_decisions: Dict[str, Any],
        result: Stage11Result,
    ) -> bool:
        """Validate the review_decisions structure."""
        if not review_decisions:
            result.errors.append("review_decisions is empty or None")
            return False

        if "decisions_by_stage" not in review_decisions:
            result.errors.append("review_decisions missing 'decisions_by_stage' key")
            return False

        return True

    def _count_critical_pending(self, review_decisions: Dict[str, Any]) -> int:
        """Count pending items from critical stages."""
        # In a full implementation, we'd track which items are pending
        # For now, we check if any critical stage has no decisions
        decisions_by_stage = review_decisions.get("decisions_by_stage", {})
        critical_pending = 0

        for stage in self.CRITICAL_DECISION_STAGES:
            stage_data = decisions_by_stage.get(str(stage), {})
            if not stage_data.get("decisions"):
                # Check if there were items needing review
                # This would require access to the original stage results
                pass

        return critical_pending

    # =========================================================================
    # ENTITY INDEX
    # =========================================================================

    def _build_entity_index(self, usdm: Dict[str, Any]) -> None:
        """Build index of entities by ID for fast lookup."""
        self._entity_index = {}

        # Index encounters/visits
        for key in ["encounters", "visits"]:
            for item in usdm.get(key, []):
                item_id = item.get("id", "")
                if item_id:
                    self._entity_index[item_id] = item

        # Index activities
        for activity in usdm.get("activities", []):
            activity_id = activity.get("id", "")
            if activity_id:
                self._entity_index[activity_id] = activity

        # Index scheduled instances
        for sai in usdm.get("scheduledActivityInstances", []):
            sai_id = sai.get("id", "")
            if sai_id:
                self._entity_index[sai_id] = sai

        # Index footnotes
        for footnote in usdm.get("footnotes", []):
            fn_id = footnote.get("id", "")
            if fn_id:
                self._entity_index[fn_id] = footnote

        # Index conditions
        for condition in usdm.get("conditions", []):
            cond_id = condition.get("id", "")
            if cond_id:
                self._entity_index[cond_id] = condition

        logger.debug(f"Built entity index with {len(self._entity_index)} entities")

    def _get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get entity by ID from index."""
        return self._entity_index.get(entity_id)

    # =========================================================================
    # DECISION APPLICATION
    # =========================================================================

    def _apply_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
        stage: int,
        result: Stage11Result,
    ) -> bool:
        """Apply a single decision to the USDM."""
        item_type = decision.get("item_type", "")
        action = decision.get("action", "")
        item_id = decision.get("item_id", "")
        entity_id = decision.get("source_entity_id", "")
        entity_name = decision.get("source_entity_name", "")

        # Track by action type
        if action == "approved":
            result.approved_count += 1
        elif action == "rejected":
            result.rejected_count += 1
        elif action == "modified":
            result.modified_count += 1

        # Get the appropriate applicator method
        applicator_name = self.DECISION_APPLICATORS.get(item_type)
        if not applicator_name:
            logger.warning(f"No applicator for item_type: {item_type}")
            return False

        applicator = getattr(self, applicator_name, None)
        if not applicator:
            logger.warning(f"Applicator method not found: {applicator_name}")
            return False

        try:
            success = applicator(usdm, decision)

            # Create audit entry if configured
            if self.config.generate_audit_trail:
                audit_entry = AuditEntry(
                    timestamp=datetime.now().isoformat(),
                    stage=stage,
                    item_id=item_id,
                    item_type=item_type,
                    action=action,
                    entity_id=entity_id,
                    entity_name=entity_name,
                    change_description=self._describe_change(decision),
                    reviewer=decision.get("reviewed_by", ""),
                    reviewer_notes=decision.get("reviewer_notes"),
                )
                result.audit_trail.append(audit_entry)

            return success

        except Exception as e:
            logger.error(f"Error applying decision {item_id}: {e}")
            result.errors.append(f"Failed to apply decision {item_id}: {str(e)}")
            return False

    def _describe_change(self, decision: Dict[str, Any]) -> str:
        """Generate human-readable description of the change."""
        action = decision.get("action", "")
        item_type = decision.get("item_type", "")
        entity_name = decision.get("source_entity_name", "")
        selected = decision.get("selected_option_id", "")
        custom = decision.get("custom_value", "")

        if action == "approved":
            if selected:
                return f"Approved {item_type} for '{entity_name}' with option: {selected}"
            return f"Approved {item_type} for '{entity_name}'"
        elif action == "rejected":
            return f"Rejected {item_type} for '{entity_name}'"
        elif action == "modified":
            if custom:
                return f"Modified {item_type} for '{entity_name}' to: {custom}"
            return f"Modified {item_type} for '{entity_name}'"

        return f"{action} {item_type} for '{entity_name}'"

    # =========================================================================
    # STAGE-SPECIFIC APPLICATORS
    # =========================================================================

    def _apply_domain_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> bool:
        """Apply domain mapping decision (Stage 1)."""
        entity_id = decision.get("source_entity_id", "")
        action = decision.get("action", "")

        entity = self._get_entity(entity_id)
        if not entity:
            return False

        if action == "approved":
            # Domain was correctly assigned, no change needed
            return True
        elif action == "rejected":
            # Remove the domain assignment
            entity.pop("domainCode", None)
            entity.pop("domain", None)
            return True
        elif action == "modified":
            # Apply custom domain
            custom_value = decision.get("custom_value", "")
            if custom_value:
                entity["domain"] = custom_value
            return True

        return False

    def _apply_expansion_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> bool:
        """Apply activity expansion decision (Stage 2)."""
        entity_id = decision.get("source_entity_id", "")
        action = decision.get("action", "")

        if action == "approved":
            # Expansion was kept, mark as confirmed
            entity = self._get_entity(entity_id)
            if entity:
                entity["_expansionConfirmed"] = True
            return True
        elif action == "rejected":
            # Remove the expanded activities
            activities = usdm.get("activities", [])
            usdm["activities"] = [
                a for a in activities
                if a.get("_expandedFrom") != entity_id
            ]

            # Also remove from scheduled instances
            sais = usdm.get("scheduledActivityInstances", [])
            usdm["scheduledActivityInstances"] = [
                s for s in sais
                if s.get("_expandedFrom") != entity_id
            ]
            return True

        return False

    def _apply_hierarchy_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> bool:
        """Apply hierarchy grouping decision (Stage 3)."""
        entity_id = decision.get("source_entity_id", "")
        action = decision.get("action", "")
        selected = decision.get("selected_option_id", "")

        entity = self._get_entity(entity_id)
        if not entity:
            return False

        if action == "approved":
            if selected:
                entity["parentActivityId"] = selected
            return True
        elif action == "rejected":
            entity.pop("parentActivityId", None)
            return True

        return False

    def _apply_alternative_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> bool:
        """Apply alternative resolution decision (Stage 4)."""
        entity_id = decision.get("source_entity_id", "")
        action = decision.get("action", "")
        selected = decision.get("selected_option_id", "")

        if action == "approved" and selected:
            # Keep the selected alternative, remove others
            activities = usdm.get("activities", [])

            # Find alternatives for this entity
            alternatives_to_remove = []
            for activity in activities:
                if activity.get("_alternativeGroup") == entity_id:
                    if activity.get("id") != selected:
                        alternatives_to_remove.append(activity.get("id"))

            # Remove non-selected alternatives
            if alternatives_to_remove:
                usdm["activities"] = [
                    a for a in activities
                    if a.get("id") not in alternatives_to_remove
                ]

                # Also remove from scheduled instances
                sais = usdm.get("scheduledActivityInstances", [])
                usdm["scheduledActivityInstances"] = [
                    s for s in sais
                    if s.get("activityId") not in alternatives_to_remove
                ]

            return True
        elif action == "rejected":
            # Remove all alternatives for this group
            activities = usdm.get("activities", [])
            to_remove = [
                a.get("id") for a in activities
                if a.get("_alternativeGroup") == entity_id
            ]

            usdm["activities"] = [
                a for a in activities
                if a.get("id") not in to_remove
            ]

            sais = usdm.get("scheduledActivityInstances", [])
            usdm["scheduledActivityInstances"] = [
                s for s in sais
                if s.get("activityId") not in to_remove
            ]

            return True

        return False

    def _apply_specimen_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> bool:
        """Apply specimen enrichment decision (Stage 5)."""
        entity_id = decision.get("source_entity_id", "")
        action = decision.get("action", "")
        selected = decision.get("selected_option_id", "")
        custom = decision.get("custom_value", "")

        entity = self._get_entity(entity_id)
        if not entity:
            return False

        if action == "approved":
            if selected:
                entity["specimenType"] = selected
            return True
        elif action == "rejected":
            entity.pop("specimenDetails", None)
            return True
        elif action == "modified" and custom:
            entity["specimenType"] = custom
            return True

        return False

    def _apply_condition_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> bool:
        """Apply conditional expansion decision (Stage 6)."""
        entity_id = decision.get("source_entity_id", "")
        action = decision.get("action", "")

        entity = self._get_entity(entity_id)
        if not entity:
            return False

        if action == "approved":
            # Condition was correctly applied
            return True
        elif action == "rejected":
            # Remove the condition linkage
            entity.pop("conditionId", None)
            entity.pop("conditionIds", None)
            return True

        return False

    def _apply_timing_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> bool:
        """Apply timing distribution decision (Stage 7)."""
        entity_id = decision.get("source_entity_id", "")
        action = decision.get("action", "")
        selected = decision.get("selected_option_id", "")

        entity = self._get_entity(entity_id)
        if not entity:
            return False

        if action == "approved":
            if selected:
                entity["timingModifier"] = selected
            return True
        elif action == "rejected":
            entity.pop("timingModifier", None)
            entity.pop("_timingExpanded", None)
            return True

        return False

    def _apply_cycle_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> bool:
        """Apply cycle expansion decision (Stage 8)."""
        entity_id = decision.get("source_entity_id", "")
        action = decision.get("action", "")
        selected = decision.get("selected_option_id", "")
        custom = decision.get("custom_value", "")

        if action == "approved":
            # Cycle expansion was correct, mark as confirmed
            encounters = usdm.get("encounters", usdm.get("visits", []))
            for enc in encounters:
                if enc.get("_expandedFrom") == entity_id:
                    enc["_cycleConfirmed"] = True
            return True
        elif action == "rejected":
            # Remove cycle-expanded encounters
            for key in ["encounters", "visits"]:
                items = usdm.get(key, [])
                usdm[key] = [
                    item for item in items
                    if item.get("_expandedFrom") != entity_id
                ]

            # Also remove SAIs linked to those encounters
            sais = usdm.get("scheduledActivityInstances", [])
            expanded_enc_ids = [
                e.get("id") for e in usdm.get("encounters", usdm.get("visits", []))
                if e.get("_expandedFrom") == entity_id
            ]
            usdm["scheduledActivityInstances"] = [
                s for s in sais
                if s.get("encounterId") not in expanded_enc_ids
            ]

            return True
        elif action == "modified" and custom:
            # Apply custom cycle count
            try:
                custom_cycles = json.loads(custom) if isinstance(custom, str) else custom
                # This would require re-expansion with the new cycle count
                # For now, just mark for manual review
                logger.warning(f"Modified cycle decision requires manual re-expansion: {entity_id}")
            except json.JSONDecodeError:
                pass
            return True

        return False

    def _apply_enrichment_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> bool:
        """Apply protocol enrichment decision (Stage 9)."""
        entity_id = decision.get("source_entity_id", "")
        action = decision.get("action", "")

        entity = self._get_entity(entity_id)
        if not entity:
            return False

        if action == "approved":
            # Enrichment was correct
            return True
        elif action == "rejected":
            # Remove the mining enrichment
            entity.pop("_miningEnrichment", None)
            return True

        return False

    def _apply_code_decision(
        self,
        usdm: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> bool:
        """Apply code validation decision (Stage 12)."""
        entity_id = decision.get("source_entity_id", "")
        action = decision.get("action", "")
        custom = decision.get("custom_value", "")

        entity = self._get_entity(entity_id)
        if not entity:
            return False

        if action == "approved":
            return True
        elif action == "modified" and custom:
            # Apply custom code fix
            try:
                code_fix = json.loads(custom) if isinstance(custom, str) else custom
                if isinstance(code_fix, dict):
                    for key, value in code_fix.items():
                        entity[key] = value
            except json.JSONDecodeError:
                pass
            return True

        return False

    # =========================================================================
    # CLEANUP
    # =========================================================================

    def _remove_internal_fields(self, usdm: Dict[str, Any]) -> None:
        """Remove internal staging fields from the output."""
        internal_prefixes = ("_expanded", "_alternative", "_staging", "_cycle", "_timing")

        def clean_dict(d: Dict[str, Any]) -> None:
            keys_to_remove = [
                k for k in d.keys()
                if k.startswith(internal_prefixes)
            ]
            for k in keys_to_remove:
                del d[k]

            # Recurse into nested dicts and lists
            for v in d.values():
                if isinstance(v, dict):
                    clean_dict(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            clean_dict(item)

        clean_dict(usdm)


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


def generate_schedule(
    usdm_output: Dict[str, Any],
    review_decisions: Dict[str, Any],
    config: Optional[Stage11Config] = None,
) -> Tuple[Optional[Dict[str, Any]], Stage11Result]:
    """
    Convenience function for schedule generation.

    Args:
        usdm_output: USDM output from previous pipeline stages
        review_decisions: Output from Stage 10's export_for_stage11()
        config: Optional Stage11Config

    Returns:
        Tuple of (final_usdm or None, Stage11Result)
    """
    generator = ScheduleGenerator(config)
    result = generator.generate_schedule(usdm_output, review_decisions)
    return result.final_usdm, result
