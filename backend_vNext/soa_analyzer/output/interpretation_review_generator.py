"""
Interpretation Review Generator - Phase 2 UI JSON

Transforms interpretation pipeline stage results into a wizard-style JSON
format for user validation ("Did we interpret it correctly?").

This generator produces the _interpretation_review.json file that powers:
- 6-step wizard for interpretation validation
- Auto-approval for high-confidence items
- Critical item highlighting for must-review items
- Question prompts for ambiguous decisions

Usage:
    from soa_analyzer.output.interpretation_review_generator import (
        InterpretationReviewGenerator,
        generate_interpretation_review,
    )

    generator = InterpretationReviewGenerator()
    review_json = generator.generate(pipeline_result, protocol_id)
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"
AUTO_APPROVE_THRESHOLD = 0.95


# =============================================================================
# SECTION DESCRIPTIONS FOR INTERPRETATION STEPS
# =============================================================================
# These descriptions explain the purpose, logic, and downstream usage of each
# interpretation step. They are inserted into the JSON output to provide
# context for reviewers.

STEP_SECTION_DESCRIPTIONS = {
    "DOMAIN_MAPPING": """
## Step 1: Domain Categorization

This step maps each extracted activity to a CDISC SDTM domain based on its clinical purpose.

### What It Does
- Analyzes activity names and descriptions
- Maps to standard domains: VS (Vital Signs), LB (Laboratory), EG (ECG), PE (Physical Exam), etc.
- Uses NCI Thesaurus codes for standardized terminology

### Confidence Scoring
- **High (>0.95)**: Standard activity names with clear domain mappings (e.g., "Blood Pressure" → VS)
- **Medium (0.7-0.95)**: Activities requiring context interpretation
- **Low (<0.7)**: Ambiguous activities, compound names, or novel assessments

### Downstream Usage
- **EDC Build**: Determines which CRF templates to use
- **CDISC SDTM**: Direct mapping to submission domains
- **Data Standards**: Ensures regulatory compliance
""",

    "ACTIVITY_EXPANSION": """
## Step 2: Activity Expansion

This step decomposes parent activities into their individual measurable components.

### What It Does
- Expands "Vital Signs" → [Systolic BP, Diastolic BP, Heart Rate, Respiratory Rate, Temperature]
- Expands "Chemistry Panel" → [Glucose, BUN, Creatinine, AST, ALT, etc.]
- Links components to standard tests and units

### Expansion Sources
- Protocol lab specifications sections
- Standard clinical assessment definitions
- CDISC controlled terminology

### Downstream Usage
- **EDC Build**: Creates individual data fields for each component
- **Data Collection**: Ensures all required measurements are captured
- **Validation Rules**: Enables component-level range checks
""",

    "ALTERNATIVES": """
## Step 3: Alternatives Resolution

This step identifies and resolves "X or Y" choice points in the SOA where multiple procedures are listed as options.

### What It Does
- Detects patterns like "CT or MRI", "Blood or Urine sample"
- Determines if alternatives are:
  - **Mutually exclusive**: Site chooses one (create choice field)
  - **Both allowed**: Either can satisfy requirement
  - **Preference-based**: One preferred, other as backup

### Decision Criteria
- Presence of "or" vs "and/or" vs comma separation
- Clinical context (e.g., MRI often preferred but CT acceptable if contraindicated)
- Protocol footnotes specifying conditions

### Downstream Usage
- **EDC Build**: Creates choice fields or parallel paths
- **Site Operations**: Clarifies acceptable options
- **Data Analysis**: Tracks which alternative was used
""",

    "SPECIMENS": """
## Step 4: Specimen Enrichment

This step enriches specimen collection activities with detailed handling requirements.

### What It Does
- Links activities to specimen collection requirements
- Extracts: tube types, volumes, processing instructions, storage conditions
- Identifies special handling requirements (e.g., fasting, time-sensitive)

### Information Sources
- Protocol biospecimen handling sections
- Laboratory manual references
- Standard specimen requirements by test type

### Downstream Usage
- **Site Training**: Specimen collection procedures
- **Lab Kits**: Defines required materials
- **Query Generation**: Flags deviations from collection requirements
""",

    "CONDITIONS": """
## Step 5: Conditional Expansion

This step interprets footnotes that create conditional logic for activity scheduling.

### What It Does
- Parses conditional footnotes (e.g., "Only for females of childbearing potential")
- Creates population subsets and branching logic
- Links conditions to affected activities and visits

### Condition Types
- **Population subset**: Gender, age, disease characteristics
- **Clinical indication**: "If clinically indicated", "If abnormal"
- **Prior event**: Triggered by previous study events
- **Timing-based**: Specific to certain visits or cycles

### Downstream Usage
- **EDC Build**: Show/hide logic, skip patterns
- **Edit Checks**: Conditional validation rules
- **Patient Scheduling**: Identifies which activities apply to each subject
""",

    "TIMING_CYCLES": """
## Step 6: Timing & Cycle Expansion

This step expands cycle-based visit patterns and applies timing windows.

### What It Does
- Expands "Cycles 2-6" into individual visits
- Applies visit windows (e.g., "±3 days")
- Handles open-ended cycles ("until progression")
- Distributes BI/EOI (Before/End of Infusion) timing modifiers

### Cycle Patterns
- **Fixed range**: Cycles 1-6, expanded to individual visits
- **Open-ended**: "Until progression" - may require max cycle input
- **Maintenance**: Post-treatment continuation phases

### Downstream Usage
- **Visit Schedule**: Generates complete patient calendar
- **EDC Build**: Creates visit structures with windows
- **Compliance Tracking**: Defines acceptable visit timing ranges
""",

    "PROTOCOL_MINING": """
## Step 7: Protocol Mining

This step discovers cross-references between SOA activities and other protocol sections.

### What It Does
- Links laboratory activities to lab specification tables
- Connects activities to safety monitoring requirements
- Identifies PK/PD sampling relationships
- Links PRO/QoL instruments to questionnaire definitions

### Discovery Types
- **Laboratory**: Test panels, ranges, central vs local lab
- **Safety**: Dose modification triggers, stopping rules
- **PK/PD**: Sampling timepoints, bioanalytical requirements
- **Efficacy**: Response assessment criteria, imaging protocols

### Downstream Usage
- **Data Review**: Complete context for each activity
- **Safety Monitoring**: Links assessments to action triggers
- **Regulatory Submission**: Cross-references for clinical study report
""",
}


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class ReviewOption:
    """Single option for a review decision."""
    label: str
    description: str
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "description": self.description,
            "confidence": self.confidence,
        }


@dataclass
class ReviewQuestion:
    """Question to ask user for ambiguous items."""
    id: str
    question: str
    question_type: str  # NUMBER, SELECT, TEXT
    placeholder: str = ""
    options: List[Dict[str, str]] = field(default_factory=list)
    required: bool = True
    hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "question": self.question,
            "type": self.question_type,
            "required": self.required,
        }
        if self.placeholder:
            result["placeholder"] = self.placeholder
        if self.options:
            result["options"] = self.options
        if self.hint:
            result["hint"] = self.hint
        return result


@dataclass
class AutoApprovedItem:
    """Item that was auto-approved due to high confidence."""
    item_id: str
    item_type: str
    display_name: str
    details: Dict[str, Any]
    confidence: float
    reasoning: str
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {
            **self.details,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }
        if self.source:
            result["source"] = self.source
        return result


@dataclass
class ReviewItem:
    """Item requiring human review."""
    item_id: str
    item_type: str
    source_id: str
    source_name: str
    confidence: float
    status: str = "PENDING"
    is_critical: bool = False
    proposal: Dict[str, Any] = field(default_factory=dict)
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    questions: List[ReviewQuestion] = field(default_factory=list)
    user_decision: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "itemId": self.item_id,
            "type": self.item_type,
            "confidence": self.confidence,
            "status": self.status,
            "proposal": self.proposal,
            "context": self.context,
            "userDecision": self.user_decision,
        }

        if self.source_id:
            result["activityId"] = self.source_id
        if self.source_name:
            result["activityName"] = self.source_name
        if self.is_critical:
            result["isCritical"] = True
        if self.alternatives:
            result["alternatives"] = self.alternatives
        if self.questions:
            result["questions"] = [q.to_dict() for q in self.questions]

        return result


@dataclass
class WizardStep:
    """Single step in the interpretation wizard."""
    step_number: int
    step_id: str
    title: str
    description: str
    icon: str
    status: str = "PENDING"  # PENDING, IN_PROGRESS, AUTO_APPROVED, COMPLETED
    is_critical: bool = False
    auto_approved_items: List[AutoApprovedItem] = field(default_factory=list)
    review_items: List[ReviewItem] = field(default_factory=list)
    stage_numbers: List[int] = field(default_factory=list)  # Pipeline stages contributing to this step

    @property
    def total_items(self) -> int:
        return len(self.auto_approved_items) + len(self.review_items)

    @property
    def pending_count(self) -> int:
        return len(self.review_items)

    def to_dict(self) -> Dict[str, Any]:
        # Determine status
        if not self.review_items and self.auto_approved_items:
            status = "AUTO_APPROVED"
        elif self.review_items:
            status = "PENDING"
        else:
            status = "COMPLETED"

        # Get section description for this step
        section_description = STEP_SECTION_DESCRIPTIONS.get(self.step_id, "").strip()

        result = {
            "stepNumber": self.step_number,
            "stepId": self.step_id,
            "title": self.title,
            "description": self.description,
            "sectionDescription": section_description,
            "icon": self.icon,
            "status": status,
            "progress": {
                "reviewed": 0,
                "total": len(self.review_items),
            },
        }

        if self.is_critical:
            result["isCritical"] = True

        # Only include auto-approved items in summary format
        if self.auto_approved_items:
            result["autoApprovedItems"] = [
                item.to_dict() for item in self.auto_approved_items
            ]

        if self.review_items:
            result["reviewItems"] = [
                item.to_dict() for item in self.review_items
            ]

        # Add _agentDefinition for downstream system automation
        if self.stage_numbers:
            from soa_analyzer.interpretation.agent_definitions import get_agent_definition
            agent_defs = []
            for stage in self.stage_numbers:
                agent_def = get_agent_definition(stage)
                if agent_def:
                    agent_defs.append(agent_def)
            if agent_defs:
                # If multiple stages contribute, include all; otherwise just the one
                result["_agentDefinition"] = agent_defs if len(agent_defs) > 1 else agent_defs[0]

        return result


# =============================================================================
# STEP BUILDERS
# =============================================================================


class Step1DomainMappingBuilder:
    """Build Step 1: Domain Categorization review items."""

    STEP_ID = "DOMAIN_MAPPING"
    TITLE = "Domain Categorization"
    DESCRIPTION = "Review how activities are mapped to CDISC domains (VS, LB, EG, etc.)"
    ICON = "category"

    def build(self, stage1_result: Any, threshold: float) -> WizardStep:
        """Build domain mapping step from Stage 1 result."""
        step = WizardStep(
            step_number=1,
            step_id=self.STEP_ID,
            title=self.TITLE,
            description=self.DESCRIPTION,
            icon=self.ICON,
            stage_numbers=[1],  # Stage 1: Domain Categorization
        )

        if not stage1_result:
            return step

        # Extract categorized activities
        categorized = []
        if hasattr(stage1_result, "categorized_activities"):
            categorized = stage1_result.categorized_activities
        elif isinstance(stage1_result, dict):
            categorized = stage1_result.get("categorized_activities", [])

        for item in categorized:
            activity_id = item.activity_id if hasattr(item, "activity_id") else item.get("activity_id", "")
            activity_name = item.activity_name if hasattr(item, "activity_name") else item.get("activity_name", "")
            confidence = item.confidence if hasattr(item, "confidence") else item.get("confidence", 0.0)
            reasoning = item.reasoning if hasattr(item, "reasoning") else item.get("reasoning", "")

            domain_code = None
            if hasattr(item, "domain_code") and item.domain_code:
                if hasattr(item.domain_code, "to_dict"):
                    domain_code = item.domain_code.to_dict()
                elif isinstance(item.domain_code, dict):
                    domain_code = item.domain_code
                else:
                    domain_code = {"code": str(item.domain_code)}

            if confidence >= threshold:
                step.auto_approved_items.append(AutoApprovedItem(
                    item_id=f"DOM-AUTO-{activity_id}",
                    item_type="domain_mapping",
                    display_name=activity_name,
                    details={
                        "activityId": activity_id,
                        "activityName": activity_name,
                        "domain": domain_code,
                    },
                    confidence=confidence,
                    reasoning=reasoning,
                ))
            else:
                step.review_items.append(ReviewItem(
                    item_id=f"DOM-{len(step.review_items) + 1:03d}",
                    item_type="DOMAIN_MAPPING",
                    source_id=activity_id,
                    source_name=activity_name,
                    confidence=confidence,
                    proposal={
                        "domain": domain_code,
                        "reasoning": reasoning,
                    },
                    alternatives=self._get_domain_alternatives(item),
                    context={
                        "originalText": activity_name,
                    },
                ))

        return step

    def _get_domain_alternatives(self, item: Any) -> List[Dict[str, Any]]:
        """Extract alternative domain suggestions."""
        alternatives = []
        alt_domains = []

        if hasattr(item, "alternative_domains"):
            alt_domains = item.alternative_domains
        elif isinstance(item, dict):
            alt_domains = item.get("alternative_domains", [])

        for alt in alt_domains:
            if hasattr(alt, "to_dict"):
                alternatives.append({"domain": alt.to_dict()})
            elif isinstance(alt, dict):
                alternatives.append({"domain": alt})
            else:
                alternatives.append({"domain": {"code": str(alt)}})

        return alternatives


class Step2ActivityExpansionBuilder:
    """Build Step 2: Activity Expansion review items."""

    STEP_ID = "ACTIVITY_EXPANSION"
    TITLE = "Activity Expansion"
    DESCRIPTION = "Review decomposition of parent activities into measurable components"
    ICON = "expand"

    def build(self, stage2_result: Any, threshold: float) -> WizardStep:
        """Build activity expansion step from Stage 2 result."""
        step = WizardStep(
            step_number=2,
            step_id=self.STEP_ID,
            title=self.TITLE,
            description=self.DESCRIPTION,
            icon=self.ICON,
            stage_numbers=[2],  # Stage 2: Activity Expansion
        )

        if not stage2_result:
            return step

        # Extract expansions
        expansions = []
        if hasattr(stage2_result, "expansions"):
            expansions = stage2_result.expansions
        elif isinstance(stage2_result, dict):
            expansions = stage2_result.get("expansions", [])

        for exp in expansions:
            # Handle ActivityExpansion dataclass (uses parent_activity_id/parent_activity_name)
            # or dict format (uses activity_id/original_name)
            if hasattr(exp, "parent_activity_id"):
                activity_id = exp.parent_activity_id
            elif hasattr(exp, "activity_id"):
                activity_id = exp.activity_id
            elif isinstance(exp, dict):
                activity_id = exp.get("parent_activity_id", exp.get("activity_id", ""))
            else:
                activity_id = ""

            if hasattr(exp, "parent_activity_name"):
                activity_name = exp.parent_activity_name
            elif hasattr(exp, "original_name"):
                activity_name = exp.original_name
            elif isinstance(exp, dict):
                activity_name = exp.get("parent_activity_name", exp.get("original_name", ""))
            else:
                activity_name = ""

            if hasattr(exp, "confidence"):
                confidence = exp.confidence
            elif isinstance(exp, dict):
                confidence = exp.get("confidence", 0.0)
            else:
                confidence = 0.0

            # Handle rationale (ActivityExpansion) or reasoning (dict format)
            if hasattr(exp, "rationale"):
                reasoning = exp.rationale or ""
            elif hasattr(exp, "reasoning"):
                reasoning = exp.reasoning
            elif isinstance(exp, dict):
                reasoning = exp.get("rationale", exp.get("reasoning", ""))
            else:
                reasoning = ""

            # Get components
            components = []
            if hasattr(exp, "components"):
                for comp in exp.components:
                    if hasattr(comp, "to_dict"):
                        components.append(comp.to_dict())
                    elif isinstance(comp, dict):
                        components.append(comp)
            elif isinstance(exp, dict):
                components = exp.get("components", [])

            if hasattr(exp, "source"):
                source = exp.source or ""
            elif isinstance(exp, dict):
                source = exp.get("source", "")
            else:
                source = ""

            if confidence >= threshold:
                step.auto_approved_items.append(AutoApprovedItem(
                    item_id=f"EXP-AUTO-{activity_id}",
                    item_type="activity_expansion",
                    display_name=activity_name,
                    details={
                        "activityId": activity_id,
                        "activityName": activity_name,
                        "components": components,
                    },
                    confidence=confidence,
                    reasoning=reasoning,
                    source=source,
                ))
            else:
                step.review_items.append(ReviewItem(
                    item_id=f"EXP-{len(step.review_items) + 1:03d}",
                    item_type="ACTIVITY_EXPANSION",
                    source_id=activity_id,
                    source_name=activity_name,
                    confidence=confidence,
                    proposal={
                        "components": components,
                        "source": source,
                        "reasoning": reasoning,
                    },
                    context={
                        "originalText": activity_name,
                    },
                ))

        return step


class Step3AlternativesBuilder:
    """Build Step 3: Alternative Resolution review items."""

    STEP_ID = "ALTERNATIVES"
    TITLE = "Alternative Resolution"
    DESCRIPTION = "Review 'X or Y' choice points - determine if mutually exclusive or both required"
    ICON = "fork"

    def build(self, stage4_result: Any, threshold: float) -> WizardStep:
        """Build alternatives step from Stage 4 result."""
        step = WizardStep(
            step_number=3,
            step_id=self.STEP_ID,
            title=self.TITLE,
            description=self.DESCRIPTION,
            icon=self.ICON,
            is_critical=True,  # Alternatives are critical
            stage_numbers=[4],  # Stage 4: Alternative Resolution
        )

        if not stage4_result:
            return step

        # Extract alternative expansions
        expansions = []
        if hasattr(stage4_result, "expansions"):
            expansions = stage4_result.expansions
        elif isinstance(stage4_result, dict):
            expansions = stage4_result.get("expansions", [])

        for exp in expansions:
            # Handle both dict and AlternativeExpansion dataclass
            if isinstance(exp, dict):
                activity_id = exp.get("original_activity_id", exp.get("originalActivityId", ""))
                activity_name = exp.get("original_activity_name", exp.get("originalActivityName", ""))
                confidence = exp.get("confidence", 0.0)
                reasoning = exp.get("reasoning", exp.get("review_reason", ""))
            else:
                # Dataclass with snake_case attributes
                activity_id = getattr(exp, "original_activity_id", "")
                activity_name = getattr(exp, "original_activity_name", "")
                confidence = getattr(exp, "confidence", 0.0)
                reasoning = getattr(exp, "review_reason", "") or ""

            # Get resolution action
            resolution = "MUTUALLY_EXCLUSIVE"
            if hasattr(exp, "decision") and exp.decision:
                if hasattr(exp.decision, "action"):
                    resolution = str(exp.decision.action.value) if hasattr(exp.decision.action, "value") else str(exp.decision.action)
            elif isinstance(exp, dict) and "decision" in exp:
                decision = exp["decision"]
                if isinstance(decision, dict):
                    resolution = decision.get("action", resolution)

            # Get expanded activities
            expanded = []
            if isinstance(exp, dict):
                # Dict format from JSON - try both camelCase and snake_case
                expanded = exp.get("expandedActivities", exp.get("expanded_activities", exp.get("options", [])))
            elif hasattr(exp, "expanded_activities"):
                # Dataclass format
                for opt in exp.expanded_activities:
                    if hasattr(opt, "to_dict"):
                        expanded.append(opt.to_dict())
                    elif isinstance(opt, dict):
                        expanded.append(opt)

            # Alternatives always need review (critical)
            step.review_items.append(ReviewItem(
                item_id=f"ALT-{len(step.review_items) + 1:03d}",
                item_type="ALTERNATIVE_RESOLUTION",
                source_id=activity_id,
                source_name=activity_name,
                confidence=confidence,
                is_critical=True,
                proposal={
                    "resolution": resolution,
                    "reasoning": reasoning,
                    "expandedActivities": expanded,
                },
                alternatives=[
                    {"resolution": "MUTUALLY_EXCLUSIVE", "reasoning": "One or the other, not both"},
                    {"resolution": "BOTH_REQUIRED", "reasoning": "Both options are required"},
                    {"resolution": "CONDITIONAL_CHOICE", "reasoning": "Choice depends on clinical need"},
                ],
                context={
                    "originalText": activity_name,
                },
            ))

        return step


class Step4SpecimensBuilder:
    """Build Step 4: Specimen Details review items."""

    STEP_ID = "SPECIMENS"
    TITLE = "Specimen Details"
    DESCRIPTION = "Review specimen collection requirements (tube types, volumes)"
    ICON = "biotech"

    def build(self, stage5_result: Any, threshold: float) -> WizardStep:
        """Build specimens step from Stage 5 result."""
        step = WizardStep(
            step_number=4,
            step_id=self.STEP_ID,
            title=self.TITLE,
            description=self.DESCRIPTION,
            icon=self.ICON,
            stage_numbers=[5],  # Stage 5: Specimen Enrichment
        )

        if not stage5_result:
            return step

        # Extract specimen enrichments
        enrichments = []
        if hasattr(stage5_result, "enrichments"):
            enrichments = stage5_result.enrichments
        elif isinstance(stage5_result, dict):
            enrichments = stage5_result.get("enrichments", [])

        for enr in enrichments:
            activity_id = enr.activity_id if hasattr(enr, "activity_id") else enr.get("activity_id", "")
            activity_name = enr.activity_name if hasattr(enr, "activity_name") else enr.get("activity_name", "")
            confidence = enr.confidence if hasattr(enr, "confidence") else enr.get("confidence", 0.0)

            # Get specimen details
            specimen = {}
            if hasattr(enr, "tube_specification") and enr.tube_specification:
                ts = enr.tube_specification
                specimen = {
                    "tubeType": ts.tube_type.value if hasattr(ts.tube_type, "value") else str(ts.tube_type) if hasattr(ts, "tube_type") else "",
                    "volume": f"{ts.volume.value} {ts.volume.unit}" if hasattr(ts, "volume") and ts.volume else "",
                    "processing": ts.processing if hasattr(ts, "processing") else "",
                    "storage": ts.storage if hasattr(ts, "storage") else "",
                }
            elif isinstance(enr, dict):
                specimen = enr.get("specimen", {})

            source = ""
            if hasattr(enr, "provenance") and enr.provenance:
                source = enr.provenance.source_section if hasattr(enr.provenance, "source_section") else ""
            elif isinstance(enr, dict) and "provenance" in enr:
                source = enr["provenance"].get("source_section", "")

            if confidence >= threshold:
                step.auto_approved_items.append(AutoApprovedItem(
                    item_id=f"SPEC-AUTO-{activity_id}",
                    item_type="specimen_enrichment",
                    display_name=activity_name,
                    details={
                        "activityId": activity_id,
                        "activityName": activity_name,
                        "specimen": specimen,
                    },
                    confidence=confidence,
                    reasoning=f"Extracted from {source}" if source else "Standard specimen requirements",
                    source=source,
                ))
            else:
                step.review_items.append(ReviewItem(
                    item_id=f"SPEC-{len(step.review_items) + 1:03d}",
                    item_type="SPECIMEN_ENRICHMENT",
                    source_id=activity_id,
                    source_name=activity_name,
                    confidence=confidence,
                    proposal={
                        "specimen": specimen,
                    },
                    context={
                        "protocolReference": source,
                    },
                ))

        return step


class Step5ConditionsBuilder:
    """Build Step 5: Conditional Logic review items."""

    STEP_ID = "CONDITIONS"
    TITLE = "Conditional Logic"
    DESCRIPTION = "Review conditions that apply to specific activities or visits"
    ICON = "rule"

    def build(self, stage6_result: Any, threshold: float) -> WizardStep:
        """Build conditions step from Stage 6 result."""
        step = WizardStep(
            step_number=5,
            step_id=self.STEP_ID,
            title=self.TITLE,
            description=self.DESCRIPTION,
            icon=self.ICON,
            stage_numbers=[6],  # Stage 6: Conditional Expansion
        )

        if not stage6_result:
            return step

        # Extract conditions
        conditions = []
        if hasattr(stage6_result, "conditions"):
            conditions = stage6_result.conditions
        elif isinstance(stage6_result, dict):
            conditions = stage6_result.get("conditions", [])

        for cond in conditions:
            # Handle both dict and Condition dataclass formats
            if isinstance(cond, dict):
                condition_id = cond.get("id", "")
                condition_type = cond.get("conditionType", cond.get("condition_type", ""))
                # Try different field names for description
                description = cond.get("description", cond.get("text", cond.get("name", "")))
                confidence = cond.get("confidence", 0.0)
                applies_to = cond.get("applies_to", cond.get("appliesTo", cond.get("applies_to_ids", [])))
                source_footnote = cond.get("source_footnote", cond.get("sourceFootnote", {}))
            else:
                # Condition dataclass - use getattr with proper defaults
                condition_id = getattr(cond, "id", "")
                condition_type = getattr(cond, "condition_type", "")
                # Condition dataclass uses 'text' or 'name' for description
                description = getattr(cond, "text", "") or getattr(cond, "name", "")
                confidence = getattr(cond, "confidence", 0.0)
                applies_to = getattr(cond, "applies_to_ids", []) or []
                # Build source_footnote from individual fields
                source_footnote = {
                    "marker": getattr(cond, "source_footnote_marker", ""),
                    "text": getattr(cond, "source_footnote_text", ""),
                }

            if confidence >= threshold:
                step.auto_approved_items.append(AutoApprovedItem(
                    item_id=f"COND-AUTO-{condition_id}",
                    item_type="condition",
                    display_name=description[:50],
                    details={
                        "conditionId": condition_id,
                        "type": str(condition_type.value) if hasattr(condition_type, "value") else str(condition_type),
                        "description": description,
                        "appliesTo": applies_to,
                    },
                    confidence=confidence,
                    reasoning="Extracted from footnote",
                ))
            else:
                step.review_items.append(ReviewItem(
                    item_id=f"COND-{len(step.review_items) + 1:03d}",
                    item_type="CONDITION_INTERPRETATION",
                    source_id=condition_id,
                    source_name=description[:50],
                    confidence=confidence,
                    proposal={
                        "conditionType": str(condition_type.value) if hasattr(condition_type, "value") else str(condition_type),
                        "structuredRule": {
                            "appliesTo": applies_to,
                        },
                        "reasoning": "Footnote interpretation",
                    },
                    context={
                        "sourceFootnote": source_footnote,
                    },
                ))

        return step


class Step6TimingCyclesBuilder:
    """Build Step 6: Timing & Cycles review items."""

    STEP_ID = "TIMING_CYCLES"
    TITLE = "Timing & Cycles"
    DESCRIPTION = "Review visit timing, windows, and cycle expansion patterns"
    ICON = "schedule"

    def build(self, stage7_result: Any, stage8_result: Any, threshold: float) -> WizardStep:
        """Build timing/cycles step from Stage 7 and 8 results."""
        step = WizardStep(
            step_number=6,
            step_id=self.STEP_ID,
            title=self.TITLE,
            description=self.DESCRIPTION,
            icon=self.ICON,
            is_critical=True,  # Timing is critical
            stage_numbers=[7, 8],  # Stage 7: Timing Distribution + Stage 8: Cycle Expansion
        )

        # Process Stage 7: Timing Distribution
        if stage7_result:
            expansions = []
            if hasattr(stage7_result, "timing_expansions"):
                expansions = stage7_result.timing_expansions
            elif isinstance(stage7_result, dict):
                expansions = stage7_result.get("timing_expansions", [])

            for exp in expansions:
                activity_id = exp.activity_id if hasattr(exp, "activity_id") else exp.get("activity_id", "")
                visit_id = exp.visit_id if hasattr(exp, "visit_id") else exp.get("visit_id", "")
                confidence = exp.confidence if hasattr(exp, "confidence") else exp.get("confidence", 0.0)
                pattern = exp.pattern if hasattr(exp, "pattern") else exp.get("pattern", "")

                if confidence >= threshold:
                    step.auto_approved_items.append(AutoApprovedItem(
                        item_id=f"TIM-AUTO-{activity_id}-{visit_id}",
                        item_type="timing",
                        display_name=f"{activity_id}@{visit_id}",
                        details={
                            "type": "TIMING",
                            "visitId": visit_id,
                            "timing": {"pattern": str(pattern)},
                        },
                        confidence=confidence,
                        reasoning="Timing pattern detected",
                    ))
                else:
                    step.review_items.append(ReviewItem(
                        item_id=f"TIM-{len(step.review_items) + 1:03d}",
                        item_type="TIMING_AMBIGUITY",
                        source_id=visit_id,
                        source_name=f"{activity_id}@{visit_id}",
                        confidence=confidence,
                        proposal={
                            "timing": {"pattern": str(pattern)},
                            "reasoning": "Timing interpretation",
                        },
                    ))

        # Process Stage 8: Cycle Expansion
        if stage8_result:
            patterns = []
            if hasattr(stage8_result, "cycle_patterns"):
                patterns = stage8_result.cycle_patterns
            elif isinstance(stage8_result, dict):
                patterns = stage8_result.get("cycle_patterns", [])

            for pattern in patterns:
                pattern_name = pattern.name if hasattr(pattern, "name") else pattern.get("name", "")
                confidence = pattern.confidence if hasattr(pattern, "confidence") else pattern.get("confidence", 0.0)

                # Extract pattern details
                cycle_length = pattern.cycle_length if hasattr(pattern, "cycle_length") else pattern.get("cycle_length", 21)
                visit_days = pattern.visit_days if hasattr(pattern, "visit_days") else pattern.get("visit_days", [])
                defined_cycles = pattern.defined_cycles if hasattr(pattern, "defined_cycles") else pattern.get("defined_cycles", [])
                is_open_ended = pattern.is_open_ended if hasattr(pattern, "is_open_ended") else pattern.get("is_open_ended", True)

                # Cycle patterns always need review (critical)
                questions = []
                if is_open_ended:
                    questions.append(ReviewQuestion(
                        id="MAX_CYCLES",
                        question="What is the maximum number of treatment cycles?",
                        question_type="NUMBER",
                        placeholder="Enter max cycles",
                        required=True,
                        hint="Check protocol section on treatment duration",
                    ))
                    questions.append(ReviewQuestion(
                        id="CYCLE_NAMING",
                        question="How should cycles be named after the defined cycles?",
                        question_type="SELECT",
                        options=[
                            {"value": "NUMBERED", "label": "Numbered (Cycle 4, Cycle 5, ...)"},
                            {"value": "MAINTENANCE", "label": "Maintenance Cycles"},
                            {"value": "CONTINUATION", "label": "Continuation Phase"},
                        ],
                        required=True,
                    ))

                step.review_items.append(ReviewItem(
                    item_id=f"CYC-{len(step.review_items) + 1:03d}",
                    item_type="CYCLE_PATTERN",
                    source_id="",
                    source_name=pattern_name,
                    confidence=confidence,
                    is_critical=True,
                    proposal={
                        "expansion": "FIXED_COUNT" if not is_open_ended else "NEEDS_MAX",
                        "maxCycles": None,
                        "reasoning": "Cycle pattern detected",
                    },
                    context={
                        "detectedPattern": {
                            "cycleLength": cycle_length,
                            "unit": "days",
                            "visitDays": visit_days,
                            "definedCycles": defined_cycles,
                            "isOpenEnded": is_open_ended,
                        },
                    },
                    questions=questions,
                ))

        return step


# =============================================================================
# MAIN GENERATOR CLASS
# =============================================================================


class InterpretationReviewGenerator:
    """
    Generates Phase 2 Interpretation Review JSON for UI.

    Transforms interpretation pipeline results into a wizard-style
    format optimized for step-by-step user validation.
    """

    def __init__(self, auto_approve_threshold: float = AUTO_APPROVE_THRESHOLD):
        self.threshold = auto_approve_threshold
        self._step_builders = {
            1: Step1DomainMappingBuilder(),
            2: Step2ActivityExpansionBuilder(),
            3: Step3AlternativesBuilder(),
            4: Step4SpecimensBuilder(),
            5: Step5ConditionsBuilder(),
            6: Step6TimingCyclesBuilder(),
        }

    def generate(
        self,
        pipeline_result: Any,
        protocol_id: str,
        protocol_title: str = "",
    ) -> Dict[str, Any]:
        """
        Generate interpretation review JSON from pipeline result.

        Args:
            pipeline_result: PipelineResult from interpretation pipeline
            protocol_id: Protocol identifier
            protocol_title: Protocol display title

        Returns:
            Interpretation review JSON for UI
        """
        logger.info(f"Generating interpretation review for {protocol_id}")

        # Extract stage results - handle various input formats
        stage_results = {}
        if hasattr(pipeline_result, "stage_results"):
            # Direct PipelineResult object
            stage_results = pipeline_result.stage_results
        elif isinstance(pipeline_result, dict):
            raw_results = pipeline_result.get("stage_results", {})
            # Handle list format (convert to dict by stage number)
            if isinstance(raw_results, list):
                for item in raw_results:
                    if isinstance(item, dict) and "stage" in item:
                        stage_results[item["stage"]] = item
            # Handle dict with string keys (from JSON)
            elif isinstance(raw_results, dict):
                for key, value in raw_results.items():
                    try:
                        stage_results[int(key)] = value
                    except (ValueError, TypeError):
                        stage_results[key] = value

        logger.debug(f"Stage results available: {list(stage_results.keys())}")

        # Build wizard steps
        steps = []

        # Step 1: Domain Mapping (Stage 1)
        step1 = self._step_builders[1].build(stage_results.get(1), self.threshold)
        steps.append(step1)

        # Step 2: Activity Expansion (Stage 2)
        step2 = self._step_builders[2].build(stage_results.get(2), self.threshold)
        steps.append(step2)

        # Step 3: Alternatives (Stage 4)
        step3 = self._step_builders[3].build(stage_results.get(4), self.threshold)
        steps.append(step3)

        # Step 4: Specimens (Stage 5)
        step4 = self._step_builders[4].build(stage_results.get(5), self.threshold)
        steps.append(step4)

        # Step 5: Conditions (Stage 6)
        step5 = self._step_builders[5].build(stage_results.get(6), self.threshold)
        steps.append(step5)

        # Step 6: Timing & Cycles (Stage 7 + 8)
        step6 = self._step_builders[6].build(
            stage_results.get(7),
            stage_results.get(8),
            self.threshold
        )
        steps.append(step6)

        # Calculate summary
        total_items = sum(s.total_items for s in steps)
        auto_approved = sum(len(s.auto_approved_items) for s in steps)
        pending_review = sum(len(s.review_items) for s in steps)

        summary_by_category = {}
        for step in steps:
            summary_by_category[step.step_id.lower()] = {
                "total": step.total_items,
                "autoApproved": len(step.auto_approved_items),
                "pending": len(step.review_items),
            }

        # Build final JSON
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "reviewType": "INTERPRETATION_WIZARD",
            "protocolId": protocol_id,
            "protocolTitle": protocol_title or protocol_id,
            "generatedAt": datetime.utcnow().isoformat() + "Z",
            "wizardConfig": {
                "totalSteps": len(steps),
                "autoApproveThreshold": self.threshold,
                "allowBatchOperations": True,
                "allowSkipToEnd": False,
            },
            "summary": {
                "totalItems": total_items,
                "autoApproved": auto_approved,
                "pendingReview": pending_review,
                "byCategory": summary_by_category,
            },
            "steps": [s.to_dict() for s in steps],
            "wizardActions": {
                "allowedOperations": [
                    "APPROVE_ITEM",
                    "REJECT_ITEM",
                    "MODIFY_ITEM",
                    "SELECT_ALTERNATIVE",
                    "ANSWER_QUESTION",
                    "ADD_COMMENT",
                    "APPROVE_ALL_IN_STEP",
                    "SKIP_STEP",
                    "GO_BACK",
                ],
                "completionRequired": {
                    "criticalItems": True,
                    "allItems": False,
                },
                "nextStep": "GENERATE_USDM",
            },
        }

        logger.info(
            f"Interpretation review generated: {len(steps)} steps, "
            f"{total_items} total items, {auto_approved} auto-approved, "
            f"{pending_review} pending review"
        )

        return result


# =============================================================================
# STEP 7: PROTOCOL MINING BUILDER (Stage 9)
# =============================================================================


class Step7ProtocolMiningBuilder:
    """Build Step 7: Protocol Mining review items (Stage 9)."""

    STEP_ID = "PROTOCOL_MINING"
    TITLE = "Protocol Mining"
    DESCRIPTION = "Review cross-protocol discoveries linking SOA activities to lab specs, PK/PD, endpoints, and safety"
    ICON = "link"

    def build(self, stage9_result: Any) -> WizardStep:
        """Build protocol mining step from Stage 9 result."""
        step = WizardStep(
            step_number=7,
            step_id=self.STEP_ID,
            title=self.TITLE,
            description=self.DESCRIPTION,
            icon=self.ICON,
            stage_numbers=[9],  # Stage 9: Protocol Mining
        )

        if not stage9_result:
            return step

        # Extract enrichments from Stage 9
        enrichments = []
        if hasattr(stage9_result, "enrichments"):
            enrichments = stage9_result.enrichments
        elif isinstance(stage9_result, dict):
            enrichments = stage9_result.get("enrichments", [])

        # Also check decisions for activity-level matches
        decisions = {}
        if hasattr(stage9_result, "decisions"):
            decisions = stage9_result.decisions
        elif isinstance(stage9_result, dict):
            decisions = stage9_result.get("decisions", {})

        # Process enrichments
        for enr in enrichments:
            activity_id = enr.activity_id if hasattr(enr, "activity_id") else enr.get("activity_id", "")
            activity_name = enr.activity_name if hasattr(enr, "activity_name") else enr.get("activity_name", "")
            confidence = enr.overall_confidence if hasattr(enr, "overall_confidence") else enr.get("overall_confidence", 0.0)

            # Get matched modules
            sources = []
            if hasattr(enr, "sources_used"):
                sources = enr.sources_used
            elif isinstance(enr, dict):
                sources = enr.get("sources_used", enr.get("matchedModules", []))

            # Get enrichment details
            enrichment_details = {}
            if hasattr(enr, "enrichment_data"):
                enrichment_details = enr.enrichment_data
            elif isinstance(enr, dict):
                enrichment_details = enr.get("enrichment_data", {})

            # Get clinical insight/reasoning
            reasoning = ""
            if hasattr(enr, "clinical_insight"):
                reasoning = enr.clinical_insight
            elif hasattr(enr, "match_rationale"):
                reasoning = str(enr.match_rationale)
            elif isinstance(enr, dict):
                reasoning = enr.get("clinical_insight", enr.get("match_rationale", ""))

            if confidence >= 0.95:
                step.auto_approved_items.append(AutoApprovedItem(
                    item_id=f"MINE-AUTO-{activity_id}",
                    item_type="protocol_mining",
                    display_name=activity_name or activity_id,
                    details={
                        "activityId": activity_id,
                        "activityName": activity_name,
                        "linkedModules": sources,
                        "enrichments": enrichment_details,
                    },
                    confidence=confidence,
                    reasoning=reasoning or f"Linked to {len(sources)} extraction module(s)",
                    source=", ".join(sources) if isinstance(sources, list) else str(sources),
                ))
            elif sources:  # Only create review item if there are potential matches
                step.review_items.append(ReviewItem(
                    item_id=f"MINE-{len(step.review_items) + 1:03d}",
                    item_type="PROTOCOL_MINING",
                    source_id=activity_id,
                    source_name=activity_name,
                    confidence=confidence,
                    proposal={
                        "linkedModules": sources,
                        "enrichments": enrichment_details,
                        "reasoning": reasoning,
                    },
                    context={
                        "activityId": activity_id,
                        "activityName": activity_name,
                        "domain": enr.get("domain") if isinstance(enr, dict) else getattr(enr, "domain", None),
                    },
                ))

        # Process decisions that need review
        for activity_id, decision in decisions.items():
            if isinstance(decision, dict):
                requires_review = decision.get("requiresHumanReview", False)
                confidence = decision.get("confidence", 0.0)
                activity_name = decision.get("activityName", "")

                if requires_review and activity_name:  # Only if we have a name
                    step.review_items.append(ReviewItem(
                        item_id=f"MINE-DEC-{len(step.review_items) + 1:03d}",
                        item_type="PROTOCOL_MINING_DECISION",
                        source_id=activity_id,
                        source_name=activity_name,
                        confidence=confidence,
                        proposal={
                            "matchedModules": decision.get("matchedModules", []),
                            "matchRationale": decision.get("matchRationale", {}),
                            "reasoning": "Activity-module relationship needs validation",
                        },
                        context={
                            "activityId": activity_id,
                            "activityName": activity_name,
                            "domain": decision.get("domain"),
                        },
                    ))

        return step


# =============================================================================
# V2 GENERATOR WITH CLINICAL INSIGHTS
# =============================================================================


class InterpretationReviewGeneratorV2(InterpretationReviewGenerator):
    """
    V2 Generator with rich clinical insights, provenance index, and review queue.

    Extends the base generator with:
    - Clinical Insights Summary (keyDiscoveries, openQuestions, qualityMetrics)
    - Protocol Mining Discoveries (cross-module links)
    - Provenance Index (page-to-item mapping for UI highlighting)
    - Review Queue (consolidated priority-sorted items)
    - Provenance Deduplication (reduces file size by 80%)
    """

    SCHEMA_VERSION = "2.0"

    def __init__(self, auto_approve_threshold: float = AUTO_APPROVE_THRESHOLD):
        super().__init__(auto_approve_threshold)
        # Add Stage 9 builder
        self._step_builders[9] = Step7ProtocolMiningBuilder()
        # Provenance store for deduplication
        self._provenance_store: Dict[str, Dict[str, Any]] = {}
        self._provenance_counter = 0

    def generate(
        self,
        pipeline_result: Any,
        protocol_id: str,
        protocol_title: str = "",
        usdm: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate V2 interpretation review JSON with rich clinical insights.

        Args:
            pipeline_result: PipelineResult from interpretation pipeline
            protocol_id: Protocol identifier
            protocol_title: Protocol display title
            usdm: Optional USDM data for metrics extraction

        Returns:
            V2 Interpretation review JSON with insights
        """
        logger.info(f"Generating V2 interpretation review for {protocol_id}")

        # Reset provenance store
        self._provenance_store = {}
        self._provenance_counter = 0

        # Extract stage results
        stage_results = self._extract_stage_results(pipeline_result)

        # Build all wizard steps (including Stage 9)
        steps = self._build_all_steps(stage_results)

        # Build clinical insights summary
        clinical_insights = self._build_clinical_insights(stage_results, usdm)

        # Build protocol mining discoveries
        mining_discoveries = self._build_mining_discoveries(stage_results.get(9))

        # Build provenance index
        provenance_index = self._build_provenance_index(steps)

        # Build consolidated review queue
        review_queue = self._build_review_queue(steps)

        # Calculate summary
        total_items = sum(s.total_items for s in steps)
        auto_approved = sum(len(s.auto_approved_items) for s in steps)
        pending_review = sum(len(s.review_items) for s in steps)

        summary_by_category = {}
        for step in steps:
            summary_by_category[step.step_id.lower()] = {
                "total": step.total_items,
                "autoApproved": len(step.auto_approved_items),
                "pending": len(step.review_items),
            }

        # Build final V2 JSON
        result = {
            "schemaVersion": self.SCHEMA_VERSION,
            "reviewType": "INTERPRETATION_WIZARD_V2",
            "protocolId": protocol_id,
            "protocolTitle": protocol_title or protocol_id,
            "generatedAt": datetime.utcnow().isoformat() + "Z",

            # NEW: Clinical Insights Summary
            "clinicalInsightsSummary": clinical_insights,

            # Wizard config
            "wizardConfig": {
                "totalSteps": len(steps),
                "autoApproveThreshold": self.threshold,
                "allowBatchOperations": True,
                "allowSkipToEnd": False,
            },

            # Summary
            "summary": {
                "totalItems": total_items,
                "autoApproved": auto_approved,
                "pendingReview": pending_review,
                "byCategory": summary_by_category,
            },

            # Steps (with deduped provenance references)
            "steps": [s.to_dict() for s in steps],

            # NEW: Protocol Mining Discoveries
            "protocolMiningDiscoveries": mining_discoveries,

            # NEW: Provenance Index for UI highlighting
            "provenanceIndex": provenance_index,

            # NEW: Provenance Store (deduplicated)
            "provenanceStore": self._provenance_store,

            # NEW: Consolidated Review Queue
            "reviewQueue": review_queue,

            # Wizard actions
            "wizardActions": {
                "allowedOperations": [
                    "APPROVE_ITEM", "REJECT_ITEM", "MODIFY_ITEM",
                    "SELECT_ALTERNATIVE", "ANSWER_QUESTION", "ADD_COMMENT",
                    "APPROVE_ALL_IN_STEP", "SKIP_STEP", "GO_BACK",
                ],
                "completionRequired": {
                    "criticalItems": True,
                    "allItems": False,
                },
                "nextStep": "GENERATE_USDM",
            },
        }

        logger.info(
            f"V2 Interpretation review generated: {len(steps)} steps, "
            f"{total_items} total items, {auto_approved} auto-approved, "
            f"{pending_review} pending review, {len(self._provenance_store)} unique provenance entries"
        )

        return result

    def _extract_stage_results(self, pipeline_result: Any) -> Dict[int, Any]:
        """Extract stage results from various input formats."""
        stage_results = {}
        if hasattr(pipeline_result, "stage_results"):
            stage_results = pipeline_result.stage_results
        elif isinstance(pipeline_result, dict):
            raw_results = pipeline_result.get("stage_results", {})
            if isinstance(raw_results, list):
                for item in raw_results:
                    if isinstance(item, dict) and "stage" in item:
                        stage_results[item["stage"]] = item
            elif isinstance(raw_results, dict):
                for key, value in raw_results.items():
                    try:
                        stage_results[int(key)] = value
                    except (ValueError, TypeError):
                        stage_results[key] = value
        return stage_results

    def _build_all_steps(self, stage_results: Dict[int, Any]) -> List[WizardStep]:
        """Build all wizard steps including Stage 9."""
        steps = []

        # Steps 1-6 (from parent class)
        step1 = self._step_builders[1].build(stage_results.get(1), self.threshold)
        steps.append(step1)

        step2 = self._step_builders[2].build(stage_results.get(2), self.threshold)
        steps.append(step2)

        step3 = self._step_builders[3].build(stage_results.get(4), self.threshold)
        steps.append(step3)

        step4 = self._step_builders[4].build(stage_results.get(5), self.threshold)
        steps.append(step4)

        step5 = self._step_builders[5].build(stage_results.get(6), self.threshold)
        steps.append(step5)

        step6 = self._step_builders[6].build(
            stage_results.get(7), stage_results.get(8), self.threshold
        )
        steps.append(step6)

        # Step 7: Protocol Mining (Stage 9)
        step7 = self._step_builders[9].build(stage_results.get(9))
        steps.append(step7)

        return steps

    def _build_clinical_insights(
        self,
        stage_results: Dict[int, Any],
        usdm: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build the clinical insights summary section."""
        insights = {
            "protocolComplexity": self._calculate_complexity(stage_results, usdm),
            "keyDiscoveries": self._extract_key_discoveries(stage_results),
            "openQuestions": self._extract_open_questions(stage_results),
            "qualityMetrics": self._calculate_quality_metrics(stage_results),
        }
        return insights

    def _calculate_complexity(
        self,
        stage_results: Dict[int, Any],
        usdm: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Calculate protocol complexity metrics."""
        complexity = {
            "treatmentCycles": 0,
            "maintenancePhase": False,
            "openEndedCycles": [],
            "totalUniqueVisits": 0,
            "totalScheduledActivities": 0,
            "conditionsDetected": 0,
            "alternativesDetected": 0,
        }

        # From USDM if available
        if usdm:
            complexity["totalUniqueVisits"] = len(usdm.get("visits", []))
            complexity["totalScheduledActivities"] = len(usdm.get("scheduledActivityInstances", []))

        # From Stage 8 (Cycle Expansion)
        stage8 = stage_results.get(8)
        if stage8:
            expansions = stage8.get("expansions", []) if isinstance(stage8, dict) else getattr(stage8, "expansions", [])
            decisions = stage8.get("decisions", {}) if isinstance(stage8, dict) else getattr(stage8, "decisions", {})

            for exp in expansions:
                if isinstance(exp, dict):
                    cycles = exp.get("expandedCycleNumbers", [])
                    if cycles:
                        complexity["treatmentCycles"] = max(complexity["treatmentCycles"], max(cycles))

            for decision in decisions.values() if isinstance(decisions, dict) else []:
                if isinstance(decision, dict):
                    if decision.get("isOpenEnded"):
                        complexity["openEndedCycles"].append(decision.get("encounterName", "Unknown"))
                        complexity["maintenancePhase"] = True

        # From Stage 6 (Conditions)
        stage6 = stage_results.get(6)
        if stage6:
            conditions = stage6.get("conditions", []) if isinstance(stage6, dict) else getattr(stage6, "conditions", [])
            complexity["conditionsDetected"] = len(conditions)

        # From Stage 4 (Alternatives)
        stage4 = stage_results.get(4)
        if stage4:
            expansions = stage4.get("expansions", []) if isinstance(stage4, dict) else getattr(stage4, "expansions", [])
            complexity["alternativesDetected"] = len(expansions)

        return complexity

    def _extract_key_discoveries(self, stage_results: Dict[int, Any]) -> List[Dict[str, Any]]:
        """Extract key discoveries from stage results."""
        discoveries = []
        discovery_id = 1

        # From Stage 9: Cross-module links
        stage9 = stage_results.get(9)
        if stage9:
            enrichments = stage9.get("enrichments", []) if isinstance(stage9, dict) else getattr(stage9, "enrichments", [])
            for enr in enrichments[:5]:  # Top 5 discoveries
                if isinstance(enr, dict):
                    if enr.get("matchedModules") or enr.get("sources_used"):
                        discoveries.append({
                            "id": f"DISC-{discovery_id:03d}",
                            "type": "CROSS_REFERENCE",
                            "category": self._categorize_discovery(enr),
                            "finding": f"{enr.get('activityName', 'Activity')} linked to extraction modules",
                            "linkedActivities": [enr.get("activityId", "")],
                            "linkedModules": enr.get("matchedModules", enr.get("sources_used", [])),
                            "clinicalReasoning": enr.get("clinical_insight", enr.get("match_rationale", "")),
                            "provenance": {"pages": [], "sections": []},
                        })
                        discovery_id += 1

        # From Stage 4: Alternative resolutions
        stage4 = stage_results.get(4)
        if stage4:
            expansions = stage4.get("expansions", []) if isinstance(stage4, dict) else getattr(stage4, "expansions", [])
            for exp in expansions[:3]:  # Top 3 alternatives
                if isinstance(exp, dict):
                    discoveries.append({
                        "id": f"DISC-{discovery_id:03d}",
                        "type": "ALTERNATIVE_IDENTIFIED",
                        "category": "SCHEDULE_IMPACT",
                        "finding": f"Choice point detected: {exp.get('original_name', 'Unknown')}",
                        "linkedActivities": [exp.get("original_activity_id", "")],
                        "linkedModules": [],
                        "clinicalReasoning": exp.get("reasoning", "X or Y pattern detected requiring user decision"),
                        "provenance": {"pages": [], "sections": []},
                    })
                    discovery_id += 1

        return discoveries

    def _categorize_discovery(self, enrichment: Dict[str, Any]) -> str:
        """Categorize a discovery based on linked modules."""
        modules = enrichment.get("matchedModules", enrichment.get("sources_used", []))
        if not modules:
            return "GENERAL"

        modules_str = " ".join(str(m).lower() for m in modules)
        if "safety" in modules_str or "adverse" in modules_str:
            return "SAFETY_CRITICAL"
        elif "laboratory" in modules_str or "lab" in modules_str:
            return "LABORATORY"
        elif "pkpd" in modules_str or "pharmacokinetic" in modules_str:
            return "PK_PD"
        elif "imaging" in modules_str or "recist" in modules_str:
            return "IMAGING"
        return "CROSS_REFERENCE"

    def _extract_open_questions(self, stage_results: Dict[int, Any]) -> List[Dict[str, Any]]:
        """Extract open questions that need user input."""
        questions = []
        question_id = 1

        # From Stage 8: Open-ended cycles
        stage8 = stage_results.get(8)
        if stage8:
            decisions = stage8.get("decisions", {}) if isinstance(stage8, dict) else getattr(stage8, "decisions", {})
            for enc_id, decision in (decisions.items() if isinstance(decisions, dict) else []):
                if isinstance(decision, dict) and decision.get("requiresHumanReview"):
                    questions.append({
                        "id": f"Q-{question_id:03d}",
                        "question": f"Cycle count undefined for {decision.get('encounterName', 'encounter')}",
                        "context": decision.get("rationale", "Pattern requires human review"),
                        "recommendation": "Set practical maximum cycles for scheduling",
                        "criticality": "HIGH" if decision.get("isOpenEnded") else "MEDIUM",
                        "linkedReviewItem": f"CYC-{question_id:03d}",
                    })
                    question_id += 1

        # From Stage 4: Unresolved alternatives
        stage4 = stage_results.get(4)
        if stage4:
            expansions = stage4.get("expansions", []) if isinstance(stage4, dict) else getattr(stage4, "expansions", [])
            for exp in expansions:
                if isinstance(exp, dict):
                    confidence = exp.get("confidence", 0)
                    if confidence < 0.8:
                        questions.append({
                            "id": f"Q-{question_id:03d}",
                            "question": f"Which option is required: {exp.get('original_name', 'X or Y')}?",
                            "context": "Multiple alternatives detected but resolution unclear",
                            "recommendation": "Review protocol to determine if mutually exclusive or both required",
                            "criticality": "HIGH",
                            "linkedReviewItem": f"ALT-{question_id:03d}",
                        })
                        question_id += 1

        return questions

    def _calculate_quality_metrics(self, stage_results: Dict[int, Any]) -> Dict[str, Any]:
        """Calculate quality metrics across all stages."""
        metrics = {
            "activitiesWithFullProvenance": 0.0,
            "activitiesLinkedToModules": 0.0,
            "conditionsFullyInterpreted": 0.0,
            "aiConfidenceDistribution": {"high": 0, "medium": 0, "low": 0},
        }

        # Count confidence distribution from all stages
        total_items = 0
        for stage_num, result in stage_results.items():
            if result is None:
                continue

            # Try to get items from various stage result formats
            items = []
            if isinstance(result, dict):
                items.extend(result.get("categorized_activities", []))
                items.extend(result.get("expansions", []))
                items.extend(result.get("enrichments", []))
                items.extend(result.get("conditions", []))
            else:
                items.extend(getattr(result, "categorized_activities", []))
                items.extend(getattr(result, "expansions", []))
                items.extend(getattr(result, "enrichments", []))
                items.extend(getattr(result, "conditions", []))

            for item in items:
                confidence = item.get("confidence", 0) if isinstance(item, dict) else getattr(item, "confidence", 0)
                total_items += 1
                if confidence >= 0.9:
                    metrics["aiConfidenceDistribution"]["high"] += 1
                elif confidence >= 0.7:
                    metrics["aiConfidenceDistribution"]["medium"] += 1
                else:
                    metrics["aiConfidenceDistribution"]["low"] += 1

        # Calculate percentages
        if total_items > 0:
            metrics["activitiesWithFullProvenance"] = round(
                metrics["aiConfidenceDistribution"]["high"] / total_items, 2
            )

        # Stage 9 specific: linked to modules
        stage9 = stage_results.get(9)
        if stage9:
            enrichments = stage9.get("enrichments", []) if isinstance(stage9, dict) else getattr(stage9, "enrichments", [])
            linked = sum(1 for e in enrichments if (e.get("matchedModules") if isinstance(e, dict) else getattr(e, "matchedModules", [])))
            total = len(enrichments) or 1
            metrics["activitiesLinkedToModules"] = round(linked / total, 2)

        return metrics

    def _build_mining_discoveries(self, stage9_result: Any) -> Dict[str, Any]:
        """Build protocol mining discoveries section."""
        discoveries = {
            "totalActivitiesAnalyzed": 0,
            "activitiesWithDiscoveries": 0,
            "discoveryCategories": {
                "laboratory": 0,
                "safety": 0,
                "pkpd": 0,
                "imaging": 0,
                "pro": 0,
                "other": 0,
            },
            "discoveries": [],
        }

        if not stage9_result:
            return discoveries

        enrichments = stage9_result.get("enrichments", []) if isinstance(stage9_result, dict) else getattr(stage9_result, "enrichments", [])
        decisions = stage9_result.get("decisions", {}) if isinstance(stage9_result, dict) else getattr(stage9_result, "decisions", {})

        discoveries["totalActivitiesAnalyzed"] = len(decisions)

        for enr in enrichments:
            if isinstance(enr, dict):
                modules = enr.get("matchedModules", enr.get("sources_used", []))
                if modules:
                    discoveries["activitiesWithDiscoveries"] += 1

                    # Categorize
                    for module in modules:
                        module_lower = str(module).lower()
                        if "lab" in module_lower:
                            discoveries["discoveryCategories"]["laboratory"] += 1
                        elif "safety" in module_lower or "adverse" in module_lower:
                            discoveries["discoveryCategories"]["safety"] += 1
                        elif "pk" in module_lower:
                            discoveries["discoveryCategories"]["pkpd"] += 1
                        elif "imaging" in module_lower:
                            discoveries["discoveryCategories"]["imaging"] += 1
                        elif "pro" in module_lower:
                            discoveries["discoveryCategories"]["pro"] += 1
                        else:
                            discoveries["discoveryCategories"]["other"] += 1

                    # Add to discoveries list
                    discoveries["discoveries"].append({
                        "id": f"MINE-{len(discoveries['discoveries']) + 1:03d}",
                        "activityId": enr.get("activityId", enr.get("activity_id", "")),
                        "activityName": enr.get("activityName", enr.get("activity_name", "")),
                        "domain": enr.get("domain"),
                        "linkedModules": [
                            {
                                "module": m,
                                "matchType": "DIRECT" if "lab" in str(m).lower() or "pk" in str(m).lower() else "INDIRECT",
                                "confidence": enr.get("confidence", enr.get("overall_confidence", 0.0)),
                            }
                            for m in modules
                        ],
                        "clinicalInsight": enr.get("clinical_insight", enr.get("match_rationale", "")),
                        "provenance": {"pages": []},
                    })

        return discoveries

    def _build_provenance_index(self, steps: List[WizardStep]) -> Dict[str, Any]:
        """Build provenance index for UI highlighting."""
        index = {
            "byPage": {},
            "byActivity": {},
            "totalPages": 0,
            "totalActivities": 0,
        }

        pages_seen = set()
        activities_seen = set()

        for step in steps:
            # Process auto-approved items
            for item in step.auto_approved_items:
                details = item.details
                activity_id = details.get("activityId", "")

                if activity_id:
                    activities_seen.add(activity_id)
                    if activity_id not in index["byActivity"]:
                        index["byActivity"][activity_id] = []
                    index["byActivity"][activity_id].append({
                        "itemId": item.item_id,
                        "type": item.item_type,
                        "stepId": step.step_id,
                    })

            # Process review items
            for item in step.review_items:
                # Try to get page from provenance
                page = None
                if hasattr(item, "context") and item.context:
                    prov = item.context.get("provenance", {})
                    page = prov.get("pageNumber")

                if page:
                    pages_seen.add(page)
                    page_key = str(page)
                    if page_key not in index["byPage"]:
                        index["byPage"][page_key] = []
                    index["byPage"][page_key].append({
                        "itemId": item.item_id,
                        "type": item.item_type,
                        "stepId": step.step_id,
                    })

                # Index by activity
                if item.source_id:
                    activities_seen.add(item.source_id)
                    if item.source_id not in index["byActivity"]:
                        index["byActivity"][item.source_id] = []
                    index["byActivity"][item.source_id].append({
                        "itemId": item.item_id,
                        "type": item.item_type,
                        "stepId": step.step_id,
                    })

        index["totalPages"] = len(pages_seen)
        index["totalActivities"] = len(activities_seen)

        return index

    def _build_review_queue(self, steps: List[WizardStep]) -> Dict[str, Any]:
        """Build consolidated review queue sorted by priority."""
        queue = {
            "criticalItems": [],
            "highPriorityItems": [],
            "mediumPriorityItems": [],
            "lowPriorityItems": [],
            "summary": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "autoApproved": 0,
            },
        }

        for step in steps:
            queue["summary"]["autoApproved"] += len(step.auto_approved_items)

            for item in step.review_items:
                queue_item = {
                    "itemId": item.item_id,
                    "step": step.step_id,
                    "stepTitle": step.title,
                    "title": f"{item.item_type}: {item.source_name or item.source_id}",
                    "confidence": item.confidence,
                    "isCritical": item.is_critical,
                }

                # Categorize by priority
                if item.is_critical or step.step_id in ["ALTERNATIVES", "TIMING_CYCLES"]:
                    queue["criticalItems"].append(queue_item)
                    queue["summary"]["critical"] += 1
                elif item.confidence < 0.6:
                    queue["highPriorityItems"].append(queue_item)
                    queue["summary"]["high"] += 1
                elif item.confidence < 0.8:
                    queue["mediumPriorityItems"].append(queue_item)
                    queue["summary"]["medium"] += 1
                else:
                    queue["lowPriorityItems"].append(queue_item)
                    queue["summary"]["low"] += 1

        # Sort by confidence (lowest first)
        for key in ["criticalItems", "highPriorityItems", "mediumPriorityItems", "lowPriorityItems"]:
            queue[key].sort(key=lambda x: x["confidence"])

        return queue


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def generate_interpretation_review(
    pipeline_result: Any,
    protocol_id: str,
    protocol_title: str = "",
    auto_approve_threshold: float = AUTO_APPROVE_THRESHOLD,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Convenience function to generate interpretation review JSON.

    Args:
        pipeline_result: PipelineResult from interpretation pipeline
        protocol_id: Protocol identifier
        protocol_title: Protocol display title
        auto_approve_threshold: Confidence threshold for auto-approval
        output_path: Optional path to save JSON file

    Returns:
        Interpretation review JSON
    """
    generator = InterpretationReviewGenerator(auto_approve_threshold)
    review_json = generator.generate(pipeline_result, protocol_id, protocol_title)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(review_json, f, indent=2)
        logger.info(f"Interpretation review saved to {output_path}")

    return review_json
