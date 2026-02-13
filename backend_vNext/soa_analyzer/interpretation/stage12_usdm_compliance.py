"""
Stage 12: USDM Schema Compliance (CRITICAL)

Ensures ALL output conforms to USDM 4.0 specification.

Critical Issues Fixed:
1. instanceType fields missing from all entities
2. Code objects use simple {code, decode} instead of 6-field format
3. No referential integrity validation
4. Condition resources not properly linked
5. scheduleTimelines array missing

Design Principles:
1. instanceType Injection - Add required instanceType to all entities
2. Code Object Expansion - All {code, decode} → 6-field Code objects
3. ScheduleTimeline Generation - Create required scheduleTimelines array
4. Referential Integrity - All referenced IDs must exist
5. Condition Linkage - All Conditions properly linked via ConditionAssignments
6. Biomedical Concept Validation - Validate and fix BC objects from Stage 1
7. Validation Report - Comprehensive output of all issues found

Target: 100% USDM 4.0 compliance

Usage:
    from soa_analyzer.interpretation.stage12_usdm_compliance import USDMComplianceChecker

    checker = USDMComplianceChecker()
    result = checker.ensure_compliance(usdm_output)
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ..models.code_object import (
    CodeObject,
    expand_to_usdm_code,
    is_usdm_compliant_code,
    ENCOUNTER_TYPE_CODES,
    TIMING_TYPE_CODES,
    TIMING_REFERENCE_CODES,
)
from ..models.condition import (
    Condition,
    ConditionAssignment,
    extract_conditions_from_footnotes,
)

logger = logging.getLogger(__name__)


@dataclass
class ComplianceIssue:
    """A single compliance issue found during validation."""
    severity: str  # "error", "warning", "info"
    category: str  # "code_object", "referential_integrity", "condition_linkage", etc.
    entity_id: str
    entity_type: str
    field: str
    message: str
    auto_fixed: bool = False
    fix_applied: Optional[str] = None


@dataclass
class ComplianceResult:
    """Result of USDM compliance check and fix."""
    is_compliant: bool = False
    total_issues: int = 0
    errors: int = 0
    warnings: int = 0
    auto_fixed: int = 0
    issues: List[ComplianceIssue] = field(default_factory=list)

    # Counts
    code_objects_expanded: int = 0
    referential_integrity_passed: bool = False
    condition_linkage_complete: bool = False
    biomedical_concepts_validated: int = 0  # BC objects validated

    def add_issue(self, issue: ComplianceIssue) -> None:
        """Add an issue to the result."""
        self.issues.append(issue)
        self.total_issues += 1
        if issue.severity == "error":
            self.errors += 1
        elif issue.severity == "warning":
            self.warnings += 1
        if issue.auto_fixed:
            self.auto_fixed += 1

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of compliance results."""
        return {
            "is_compliant": self.is_compliant,
            "total_issues": self.total_issues,
            "errors": self.errors,
            "warnings": self.warnings,
            "auto_fixed": self.auto_fixed,
            "code_objects_expanded": self.code_objects_expanded,
            "referential_integrity_passed": self.referential_integrity_passed,
            "condition_linkage_complete": self.condition_linkage_complete,
            "biomedical_concepts_validated": self.biomedical_concepts_validated,
        }


class USDMComplianceChecker:
    """
    USDM 4.0 Compliance Checker and Fixer.

    Validates and auto-fixes USDM output to ensure full compliance.
    """

    # Fields that should contain Code objects
    CODE_OBJECT_FIELDS = {
        "encounters": ["type"],
        "timings": ["type", "relativeToFrom"],
        "activities": ["cdiscMapping"],
        "scheduledActivityInstances": [
            "specimenCollection.specimenType",
            "specimenCollection.collectionContainer",
            "specimenCollection.purpose",
        ],  # Nested specimen Code objects
    }

    # USDM 4.0 required instanceType values for each entity type
    INSTANCE_TYPES = {
        "activities": "Activity",
        "encounters": "Encounter",
        "scheduledActivityInstances": "ScheduledActivityInstance",
        "timings": "Timing",
        "conditions": "Condition",
        "conditionAssignments": "ConditionAssignment",
        "footnotes": "CommentAnnotation",
        "scheduleTimelines": "ScheduleTimeline",
    }

    def __init__(self):
        """Initialize compliance checker."""
        self._all_ids: Set[str] = set()

    def ensure_compliance(
        self,
        usdm_output: Dict[str, Any],
        auto_fix: bool = True,
    ) -> Tuple[Dict[str, Any], ComplianceResult]:
        """
        Ensure USDM output is fully compliant.

        Args:
            usdm_output: USDM output dictionary
            auto_fix: Whether to automatically fix issues

        Returns:
            Tuple of (fixed USDM output, compliance result)
        """
        result = ComplianceResult()

        # 1. Inject instanceType fields (CRITICAL - must be first)
        if auto_fix:
            usdm_output, instance_type_issues = self._inject_instance_types(usdm_output)
            for issue in instance_type_issues:
                result.add_issue(issue)

        # 2. Generate scheduleTimelines if missing (CRITICAL)
        if auto_fix:
            usdm_output, timeline_issues = self._ensure_schedule_timelines(usdm_output)
            for issue in timeline_issues:
                result.add_issue(issue)

        # 3. Collect all entity IDs
        self._collect_all_ids(usdm_output)

        # 4. Expand Code objects
        if auto_fix:
            usdm_output, code_issues = self._expand_code_objects(usdm_output)
            result.code_objects_expanded = len([i for i in code_issues if i.auto_fixed])
            for issue in code_issues:
                result.add_issue(issue)

        # 5. Validate referential integrity
        ref_issues = self._validate_referential_integrity(usdm_output)
        result.referential_integrity_passed = len([i for i in ref_issues if i.severity == "error"]) == 0
        for issue in ref_issues:
            result.add_issue(issue)

        # 6. Ensure condition linkage
        if auto_fix:
            usdm_output, cond_issues = self._ensure_condition_linkage(usdm_output)
            result.condition_linkage_complete = len([i for i in cond_issues if i.severity == "error"]) == 0
            for issue in cond_issues:
                result.add_issue(issue)

        # 7. Validate biomedical concepts (CDISC BC enrichment from Stage 1)
        usdm_output, bc_issues, bc_count = self._validate_biomedical_concepts(usdm_output, auto_fix)
        result.biomedical_concepts_validated = bc_count
        for issue in bc_issues:
            result.add_issue(issue)

        # 8. Final compliance check
        result.is_compliant = result.errors == 0

        logger.info(
            f"USDM compliance check complete: {result.total_issues} issues "
            f"({result.errors} errors, {result.warnings} warnings, {result.auto_fixed} auto-fixed)"
        )

        return usdm_output, result

    def _collect_all_ids(self, usdm_output: Dict[str, Any]) -> None:
        """Collect all entity IDs from USDM output."""
        self._all_ids.clear()

        # Collect from all entity types
        for entity_type in ["activities", "encounters", "timings", "conditions",
                           "scheduledActivityInstances", "conditionAssignments", "footnotes",
                           "scheduleTimelines"]:
            entities = usdm_output.get(entity_type, [])
            for entity in entities:
                if isinstance(entity, dict) and "id" in entity:
                    self._all_ids.add(entity["id"])

    def _inject_instance_types(
        self,
        usdm_output: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ComplianceIssue]]:
        """
        Inject instanceType field into all entities.

        USDM 4.0 requires instanceType on every entity.

        Returns:
            Tuple of (updated output, list of issues)
        """
        issues: List[ComplianceIssue] = []
        total_injected = 0

        for entity_type, instance_type_value in self.INSTANCE_TYPES.items():
            entities = usdm_output.get(entity_type, [])
            for entity in entities:
                if isinstance(entity, dict) and "instanceType" not in entity:
                    entity["instanceType"] = instance_type_value
                    total_injected += 1

        if total_injected > 0:
            issues.append(ComplianceIssue(
                severity="info",
                category="instance_type",
                entity_id="*",
                entity_type="*",
                field="instanceType",
                message=f"Injected instanceType into {total_injected} entities",
                auto_fixed=True,
                fix_applied=f"Added instanceType to {total_injected} entities",
            ))

        return usdm_output, issues

    def _ensure_schedule_timelines(
        self,
        usdm_output: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ComplianceIssue]]:
        """
        Ensure scheduleTimelines array exists and has required structure.

        USDM 4.0 requires at least one ScheduleTimeline with:
        - id, name, instanceType: "ScheduleTimeline"
        - mainTimeline: boolean
        - entryCondition: string
        - entryId: string (reference to first encounter)

        Returns:
            Tuple of (updated output, list of issues)
        """
        issues: List[ComplianceIssue] = []

        # Check if scheduleTimelines already exists and is valid
        existing_timelines = usdm_output.get("scheduleTimelines", [])
        if existing_timelines:
            # Validate existing timelines have required fields
            for timeline in existing_timelines:
                if isinstance(timeline, dict):
                    if "instanceType" not in timeline:
                        timeline["instanceType"] = "ScheduleTimeline"
            return usdm_output, issues

        # Generate scheduleTimelines from encounters and SAIs
        encounters = usdm_output.get("encounters", [])
        sais = usdm_output.get("scheduledActivityInstances", [])
        timings = usdm_output.get("timings", [])

        if not encounters:
            issues.append(ComplianceIssue(
                severity="warning",
                category="schedule_timeline",
                entity_id="",
                entity_type="ScheduleTimeline",
                field="",
                message="No encounters found - cannot generate scheduleTimelines",
                auto_fixed=False,
            ))
            return usdm_output, issues

        # Find the first encounter (entry point)
        first_encounter = encounters[0] if encounters else None
        entry_id = first_encounter.get("id", "") if first_encounter else ""

        # Get provenance from first encounter for schedule timeline
        first_encounter_provenance = first_encounter.get("provenance", {}) if first_encounter else {}

        # Create main schedule timeline
        timeline_id = f"TIMELINE-{uuid.uuid4().hex[:8].upper()}"
        schedule_timeline = {
            "id": timeline_id,
            "name": "Main Study Schedule",
            "instanceType": "ScheduleTimeline",
            "mainTimeline": True,
            "entryCondition": "Subject enrolled and eligible",
            "entryId": entry_id,
            "exits": [],
            "timings": timings,  # Reference existing timings
            "instances": [],  # SAIs are referenced separately in USDM
            "provenance": first_encounter_provenance.copy() if first_encounter_provenance else {
                "source": "generated",
                "description": "Schedule timeline auto-generated from SOA encounters"
            },
        }

        # Add reference to SAIs (instances array contains refs or embedded SAIs)
        # In USDM 4.0, instances can be embedded or referenced
        # We'll add SAI IDs as references
        for sai in sais:
            if isinstance(sai, dict) and "id" in sai:
                # Add timelineId to each SAI
                sai["timelineId"] = timeline_id

        usdm_output["scheduleTimelines"] = [schedule_timeline]

        issues.append(ComplianceIssue(
            severity="info",
            category="schedule_timeline",
            entity_id=timeline_id,
            entity_type="ScheduleTimeline",
            field="",
            message=f"Generated scheduleTimeline '{timeline_id}' with entry at '{entry_id}'",
            auto_fixed=True,
            fix_applied=f"Created main schedule timeline with {len(encounters)} encounters",
        ))

        return usdm_output, issues

    def _expand_code_objects(
        self,
        usdm_output: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ComplianceIssue]]:
        """
        Expand simple {code, decode} pairs to full USDM Code objects.

        Returns:
            Tuple of (updated output, list of issues)
        """
        issues: List[ComplianceIssue] = []

        # Expand encounter type codes
        for encounter in usdm_output.get("encounters", []):
            enc_id = encounter.get("id", "X")

            # First: If 'type' is missing but 'visitType' exists, create 'type' from 'visitType'
            if "type" not in encounter and "visitType" in encounter:
                visit_type = encounter.get("visitType", "")
                # Capitalize first letter to match ENCOUNTER_TYPE_CODES keys
                visit_type_normalized = visit_type.capitalize() if visit_type else ""

                # Map visitType to Code object
                code_data = ENCOUNTER_TYPE_CODES.get(visit_type_normalized)
                if not code_data:
                    # Try common mappings for lowercase visit types
                    visit_type_map = {
                        "screening": "Screening",
                        "treatment": "Treatment",
                        "follow-up": "Follow-up",
                        "follow_up": "Follow-up",
                        "followup": "Follow-up",
                        "end_of_treatment": "End of Treatment",
                        "end of treatment": "End of Treatment",
                        "eot": "End of Treatment",
                        "end_of_study": "End of Study",
                        "end of study": "End of Study",
                        "eos": "End of Study",
                        "early_termination": "Early Termination",
                        "early termination": "Early Termination",
                        "unscheduled": "Unscheduled",
                    }
                    mapped_type = visit_type_map.get(visit_type.lower(), "Treatment")
                    code_data = ENCOUNTER_TYPE_CODES.get(mapped_type, ENCOUNTER_TYPE_CODES.get("Treatment"))

                if code_data:
                    new_type = expand_to_usdm_code(code_data, f"CODE-ENC-{enc_id}-TYPE")
                    if new_type:
                        encounter["type"] = new_type
                        issues.append(ComplianceIssue(
                            severity="info",
                            category="code_object",
                            entity_id=enc_id,
                            entity_type="Encounter",
                            field="type",
                            message=f"Created type Code object from visitType '{visit_type}'",
                            auto_fixed=True,
                            fix_applied=f"visitType='{visit_type}' → Code object",
                        ))

            # Second: If 'type' exists but is not compliant, expand it
            elif "type" in encounter and not is_usdm_compliant_code(encounter.get("type", {})):
                old_type = encounter.get("type", {})
                if isinstance(old_type, dict) and old_type.get("code"):
                    new_type = expand_to_usdm_code(old_type, f"CODE-ENC-{enc_id}-TYPE")
                    if new_type:
                        encounter["type"] = new_type
                        issues.append(ComplianceIssue(
                            severity="info",
                            category="code_object",
                            entity_id=enc_id,
                            entity_type="Encounter",
                            field="type",
                            message="Expanded type to 6-field Code object",
                            auto_fixed=True,
                            fix_applied=f"code={old_type.get('code')} → full Code object",
                        ))
                elif isinstance(old_type, str):
                    # Try to map string type to code
                    code_data = ENCOUNTER_TYPE_CODES.get(old_type)
                    if code_data:
                        new_type = expand_to_usdm_code(code_data, f"CODE-ENC-{enc_id}-TYPE")
                        if new_type:
                            encounter["type"] = new_type
                            issues.append(ComplianceIssue(
                                severity="info",
                                category="code_object",
                                entity_id=enc_id,
                                entity_type="Encounter",
                                field="type",
                                message=f"Converted string type '{old_type}' to Code object",
                                auto_fixed=True,
                            ))

        # Expand timing codes
        for timing in usdm_output.get("timings", []):
            # Type field
            if "type" in timing and not is_usdm_compliant_code(timing.get("type", {})):
                old_type = timing.get("type", {})
                if isinstance(old_type, dict) and old_type.get("code"):
                    new_type = expand_to_usdm_code(old_type, f"CODE-TIM-{timing.get('id', 'X')}-TYPE")
                    if new_type:
                        timing["type"] = new_type
                        issues.append(ComplianceIssue(
                            severity="info",
                            category="code_object",
                            entity_id=timing.get("id", ""),
                            entity_type="Timing",
                            field="type",
                            message="Expanded type to 6-field Code object",
                            auto_fixed=True,
                        ))

            # relativeToFrom field
            if "relativeToFrom" in timing and not is_usdm_compliant_code(timing.get("relativeToFrom", {})):
                old_ref = timing.get("relativeToFrom", {})
                if isinstance(old_ref, dict) and old_ref.get("code"):
                    new_ref = expand_to_usdm_code(old_ref, f"CODE-TIM-{timing.get('id', 'X')}-REF")
                    if new_ref:
                        timing["relativeToFrom"] = new_ref
                        issues.append(ComplianceIssue(
                            severity="info",
                            category="code_object",
                            entity_id=timing.get("id", ""),
                            entity_type="Timing",
                            field="relativeToFrom",
                            message="Expanded relativeToFrom to 6-field Code object",
                            auto_fixed=True,
                        ))

        # Expand activity CDISC mappings
        for activity in usdm_output.get("activities", []):
            if "cdiscMapping" in activity and not is_usdm_compliant_code(activity.get("cdiscMapping", {})):
                old_mapping = activity.get("cdiscMapping", {})
                if isinstance(old_mapping, dict) and (old_mapping.get("code") or old_mapping.get("cdisc_code")):
                    new_mapping = expand_to_usdm_code(old_mapping, f"CODE-ACT-{activity.get('id', 'X')}-CDISC")
                    if new_mapping:
                        activity["cdiscMapping"] = new_mapping
                        issues.append(ComplianceIssue(
                            severity="info",
                            category="code_object",
                            entity_id=activity.get("id", ""),
                            entity_type="Activity",
                            field="cdiscMapping",
                            message="Expanded cdiscMapping to 6-field Code object",
                            auto_fixed=True,
                        ))

        # Expand specimen Code objects in SAIs
        for sai in usdm_output.get("scheduledActivityInstances", []):
            specimen_collection = sai.get("specimenCollection", {})
            if not specimen_collection:
                continue

            sai_id = sai.get("id", "")

            # specimenType Code object
            if "specimenType" in specimen_collection:
                old_type = specimen_collection.get("specimenType", {})
                if isinstance(old_type, dict) and not is_usdm_compliant_code(old_type):
                    if old_type.get("code") or old_type.get("decode"):
                        new_type = expand_to_usdm_code(old_type, f"CODE-SPEC-{uuid.uuid4().hex[:12].upper()}")
                        if new_type:
                            specimen_collection["specimenType"] = new_type
                            issues.append(ComplianceIssue(
                                severity="info",
                                category="code_object",
                                entity_id=sai_id,
                                entity_type="ScheduledActivityInstance",
                                field="specimenCollection.specimenType",
                                message="Expanded specimenType to 6-field Code object",
                                auto_fixed=True,
                            ))

            # collectionContainer Code object
            if "collectionContainer" in specimen_collection:
                old_container = specimen_collection.get("collectionContainer", {})
                if isinstance(old_container, dict) and not is_usdm_compliant_code(old_container):
                    if old_container.get("code") or old_container.get("decode"):
                        new_container = expand_to_usdm_code(old_container, f"CODE-TUBE-{uuid.uuid4().hex[:12].upper()}")
                        if new_container:
                            specimen_collection["collectionContainer"] = new_container
                            issues.append(ComplianceIssue(
                                severity="info",
                                category="code_object",
                                entity_id=sai_id,
                                entity_type="ScheduledActivityInstance",
                                field="specimenCollection.collectionContainer",
                                message="Expanded collectionContainer to 6-field Code object",
                                auto_fixed=True,
                            ))

            # purpose Code object
            if "purpose" in specimen_collection:
                old_purpose = specimen_collection.get("purpose", {})
                if isinstance(old_purpose, dict) and not is_usdm_compliant_code(old_purpose):
                    if old_purpose.get("code") or old_purpose.get("decode"):
                        new_purpose = expand_to_usdm_code(old_purpose, f"CODE-PURP-{uuid.uuid4().hex[:12].upper()}")
                        if new_purpose:
                            specimen_collection["purpose"] = new_purpose
                            issues.append(ComplianceIssue(
                                severity="info",
                                category="code_object",
                                entity_id=sai_id,
                                entity_type="ScheduledActivityInstance",
                                field="specimenCollection.purpose",
                                message="Expanded purpose to 6-field Code object",
                                auto_fixed=True,
                            ))

        return usdm_output, issues

    def _validate_referential_integrity(
        self,
        usdm_output: Dict[str, Any],
    ) -> List[ComplianceIssue]:
        """
        Validate all ID references point to existing entities.

        Returns:
            List of referential integrity issues
        """
        issues: List[ComplianceIssue] = []

        # Check SAI references
        for sai in usdm_output.get("scheduledActivityInstances", []):
            sai_id = sai.get("id", "")

            # activityId
            activity_id = sai.get("activityId")
            if activity_id and activity_id not in self._all_ids:
                issues.append(ComplianceIssue(
                    severity="error",
                    category="referential_integrity",
                    entity_id=sai_id,
                    entity_type="ScheduledActivityInstance",
                    field="activityId",
                    message=f"References non-existent activity: {activity_id}",
                ))

            # scheduledInstanceEncounterId / visitId / encounterId (check all variants)
            encounter_id = (
                sai.get("scheduledInstanceEncounterId") or
                sai.get("visitId") or
                sai.get("encounterId")
            )
            if encounter_id and encounter_id not in self._all_ids:
                issues.append(ComplianceIssue(
                    severity="error",
                    category="referential_integrity",
                    entity_id=sai_id,
                    entity_type="ScheduledActivityInstance",
                    field="scheduledInstanceEncounterId",
                    message=f"References non-existent encounter: {encounter_id}",
                ))

            # defaultConditionId
            condition_id = sai.get("defaultConditionId")
            if condition_id and condition_id not in self._all_ids:
                issues.append(ComplianceIssue(
                    severity="warning",
                    category="referential_integrity",
                    entity_id=sai_id,
                    entity_type="ScheduledActivityInstance",
                    field="defaultConditionId",
                    message=f"References non-existent condition: {condition_id}",
                ))

        # Check ConditionAssignment references
        for ca in usdm_output.get("conditionAssignments", []):
            ca_id = ca.get("id", "")

            condition_id = ca.get("conditionId")
            if condition_id and condition_id not in self._all_ids:
                issues.append(ComplianceIssue(
                    severity="error",
                    category="referential_integrity",
                    entity_id=ca_id,
                    entity_type="ConditionAssignment",
                    field="conditionId",
                    message=f"References non-existent condition: {condition_id}",
                ))

            target_id = ca.get("conditionTargetId")
            if target_id and target_id not in self._all_ids:
                issues.append(ComplianceIssue(
                    severity="error",
                    category="referential_integrity",
                    entity_id=ca_id,
                    entity_type="ConditionAssignment",
                    field="conditionTargetId",
                    message=f"References non-existent target: {target_id}",
                ))

        return issues

    def _ensure_condition_linkage(
        self,
        usdm_output: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ComplianceIssue]]:
        """
        Ensure conditions are properly extracted from footnotes and linked.

        Returns:
            Tuple of (updated output, list of issues)
        """
        issues: List[ComplianceIssue] = []

        # Get existing conditions
        existing_conditions = usdm_output.get("conditions", [])
        existing_assignments = usdm_output.get("conditionAssignments", [])

        # Extract conditions from footnotes
        footnotes = usdm_output.get("footnotes", [])
        new_conditions, marker_to_condition = extract_conditions_from_footnotes(footnotes)

        # Add new conditions not already present
        existing_condition_ids = {c.get("id") for c in existing_conditions}
        for condition in new_conditions:
            if condition.id not in existing_condition_ids:
                existing_conditions.append(condition.to_dict())
                self._all_ids.add(condition.id)
                issues.append(ComplianceIssue(
                    severity="info",
                    category="condition_linkage",
                    entity_id=condition.id,
                    entity_type="Condition",
                    field="",
                    message=f"Extracted condition from footnote '{condition.source_footnote_marker}': {condition.name}",
                    auto_fixed=True,
                ))

        # Link SAIs with footnote markers to conditions
        for sai in usdm_output.get("scheduledActivityInstances", []):
            footnote_markers = sai.get("footnoteMarkers", [])

            for marker in footnote_markers:
                condition_id = marker_to_condition.get(marker)
                if condition_id:
                    # Check if assignment already exists
                    existing = any(
                        ca.get("conditionId") == condition_id and ca.get("conditionTargetId") == sai.get("id")
                        for ca in existing_assignments
                    )

                    if not existing:
                        # Create ConditionAssignment
                        assignment = ConditionAssignment(
                            condition_id=condition_id,
                            target_id=sai.get("id", ""),
                        )
                        existing_assignments.append(assignment.to_dict())
                        self._all_ids.add(assignment.id)

                        # Update SAI defaultConditionId if not set
                        if not sai.get("defaultConditionId"):
                            sai["defaultConditionId"] = condition_id

                        issues.append(ComplianceIssue(
                            severity="info",
                            category="condition_linkage",
                            entity_id=assignment.id,
                            entity_type="ConditionAssignment",
                            field="",
                            message=f"Linked SAI {sai.get('id')} to condition {condition_id} via footnote '{marker}'",
                            auto_fixed=True,
                        ))

        # Update output
        usdm_output["conditions"] = existing_conditions
        usdm_output["conditionAssignments"] = existing_assignments

        return usdm_output, issues

    def _validate_biomedical_concepts(
        self,
        usdm_output: Dict[str, Any],
        auto_fix: bool = True,
    ) -> Tuple[Dict[str, Any], List[ComplianceIssue], int]:
        """
        Validate and fix biomedicalConcept objects on activities.

        CDISC Biomedical Concepts require:
        - conceptName (required): Standardized name
        - cdiscCode (required): NCI EVS code or "CUSTOM"
        - domain (required): CDISC domain (LB, VS, EG, PE, CM, etc.)
        - confidence (optional): 0.0-1.0
        - specimen (optional): Specimen type
        - method (optional): Method/route
        - rationale (optional): Explanation

        Returns:
            Tuple of (updated output, list of issues, count of validated BCs)
        """
        issues: List[ComplianceIssue] = []
        validated_count = 0

        # Valid CDISC domains
        valid_domains = {
            "LB", "VS", "EG", "PE", "CM", "EX", "DS", "MH", "AE", "QS",
            "DA", "PR", "MI", "PC", "PP", "BS", "IS", "DM", "SV", "SE",
            "IE", "TI", "TA", "TE", "TV", "OTHER"
        }

        for activity in usdm_output.get("activities", []):
            activity_id = activity.get("id", "")
            bc = activity.get("biomedicalConcept")

            if not bc:
                # No BC present - not an error, BC is optional
                continue

            if not isinstance(bc, dict):
                issues.append(ComplianceIssue(
                    severity="error",
                    category="biomedical_concept",
                    entity_id=activity_id,
                    entity_type="Activity",
                    field="biomedicalConcept",
                    message="biomedicalConcept must be an object",
                ))
                continue

            # Validate required fields
            has_errors = False

            # conceptName (required)
            if not bc.get("conceptName"):
                if auto_fix and activity.get("name"):
                    bc["conceptName"] = activity.get("name")[:150]  # Max 150 chars
                    issues.append(ComplianceIssue(
                        severity="info",
                        category="biomedical_concept",
                        entity_id=activity_id,
                        entity_type="Activity",
                        field="biomedicalConcept.conceptName",
                        message=f"Auto-filled conceptName from activity name",
                        auto_fixed=True,
                    ))
                else:
                    has_errors = True
                    issues.append(ComplianceIssue(
                        severity="error",
                        category="biomedical_concept",
                        entity_id=activity_id,
                        entity_type="Activity",
                        field="biomedicalConcept.conceptName",
                        message="Missing required field: conceptName",
                    ))

            # cdiscCode (required)
            if not bc.get("cdiscCode"):
                if auto_fix:
                    bc["cdiscCode"] = "CUSTOM"
                    bc["confidence"] = bc.get("confidence", 0.5)
                    issues.append(ComplianceIssue(
                        severity="info",
                        category="biomedical_concept",
                        entity_id=activity_id,
                        entity_type="Activity",
                        field="biomedicalConcept.cdiscCode",
                        message="Auto-set cdiscCode to 'CUSTOM'",
                        auto_fixed=True,
                    ))
                else:
                    has_errors = True
                    issues.append(ComplianceIssue(
                        severity="error",
                        category="biomedical_concept",
                        entity_id=activity_id,
                        entity_type="Activity",
                        field="biomedicalConcept.cdiscCode",
                        message="Missing required field: cdiscCode",
                    ))

            # domain (required)
            domain = bc.get("domain")
            if not domain:
                # Try to infer from cdashDomain
                if auto_fix and activity.get("cdashDomain"):
                    bc["domain"] = activity.get("cdashDomain")
                    issues.append(ComplianceIssue(
                        severity="info",
                        category="biomedical_concept",
                        entity_id=activity_id,
                        entity_type="Activity",
                        field="biomedicalConcept.domain",
                        message=f"Auto-filled domain from cdashDomain: {activity.get('cdashDomain')}",
                        auto_fixed=True,
                    ))
                else:
                    has_errors = True
                    issues.append(ComplianceIssue(
                        severity="error",
                        category="biomedical_concept",
                        entity_id=activity_id,
                        entity_type="Activity",
                        field="biomedicalConcept.domain",
                        message="Missing required field: domain",
                    ))
            elif domain not in valid_domains:
                issues.append(ComplianceIssue(
                    severity="warning",
                    category="biomedical_concept",
                    entity_id=activity_id,
                    entity_type="Activity",
                    field="biomedicalConcept.domain",
                    message=f"Invalid domain '{domain}' - should be one of {sorted(valid_domains)}",
                ))

            # Validate confidence range (optional field)
            confidence = bc.get("confidence")
            if confidence is not None:
                try:
                    conf_val = float(confidence)
                    if conf_val < 0.0 or conf_val > 1.0:
                        if auto_fix:
                            bc["confidence"] = max(0.0, min(1.0, conf_val))
                            issues.append(ComplianceIssue(
                                severity="info",
                                category="biomedical_concept",
                                entity_id=activity_id,
                                entity_type="Activity",
                                field="biomedicalConcept.confidence",
                                message=f"Clamped confidence to valid range [0.0, 1.0]",
                                auto_fixed=True,
                            ))
                        else:
                            issues.append(ComplianceIssue(
                                severity="warning",
                                category="biomedical_concept",
                                entity_id=activity_id,
                                entity_type="Activity",
                                field="biomedicalConcept.confidence",
                                message=f"Confidence {conf_val} out of range [0.0, 1.0]",
                            ))
                except (ValueError, TypeError):
                    issues.append(ComplianceIssue(
                        severity="warning",
                        category="biomedical_concept",
                        entity_id=activity_id,
                        entity_type="Activity",
                        field="biomedicalConcept.confidence",
                        message=f"Invalid confidence value: {confidence}",
                    ))

            # Truncate string fields to max lengths
            if auto_fix:
                if bc.get("conceptName") and len(str(bc["conceptName"])) > 150:
                    bc["conceptName"] = str(bc["conceptName"])[:150]
                if bc.get("cdiscCode") and len(str(bc["cdiscCode"])) > 20:
                    bc["cdiscCode"] = str(bc["cdiscCode"])[:20]
                if bc.get("rationale") and len(str(bc["rationale"])) > 200:
                    bc["rationale"] = str(bc["rationale"])[:200]

            if not has_errors:
                validated_count += 1

        return usdm_output, issues, validated_count


def ensure_usdm_compliance(
    usdm_output: Dict[str, Any],
    auto_fix: bool = True,
) -> Tuple[Dict[str, Any], ComplianceResult]:
    """
    Convenience function to ensure USDM compliance.

    Args:
        usdm_output: USDM output dictionary
        auto_fix: Whether to auto-fix issues

    Returns:
        Tuple of (compliant output, compliance result)
    """
    checker = USDMComplianceChecker()
    return checker.ensure_compliance(usdm_output, auto_fix)
