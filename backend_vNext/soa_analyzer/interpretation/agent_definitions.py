"""
Agent Definitions for SOA Interpretation Stages

This module contains comprehensive documentation for each interpretation stage,
describing how outputs are extracted and how they can be leveraged for
downstream process automation (EDC Build, IRT Build, CTMS, etc.).

Each _agentDefinition provides:
- Purpose and extraction methodology
- Key outputs and their structure
- Downstream system integrations
- Automation opportunities
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DownstreamIntegration:
    """Definition of how a stage output integrates with a downstream system."""
    system: str
    use_case: str
    automation_type: str  # "direct_mapping", "rule_generation", "configuration", "validation"
    fields_used: List[str]
    automation_example: str


@dataclass
class StageAgentDefinition:
    """Comprehensive definition for an interpretation stage agent."""
    stage_number: int
    stage_name: str
    display_name: str
    purpose: str
    extraction_methodology: str
    key_outputs: List[Dict[str, str]]
    downstream_integrations: List[DownstreamIntegration]
    automation_insights: List[Dict[str, str]]
    data_quality_indicators: List[str]
    human_review_triggers: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "stageNumber": self.stage_number,
            "stageName": self.stage_name,
            "displayName": self.display_name,
            "purpose": self.purpose,
            "extractionMethodology": self.extraction_methodology,
            "keyOutputs": self.key_outputs,
            "downstreamIntegrations": [
                {
                    "system": di.system,
                    "useCase": di.use_case,
                    "automationType": di.automation_type,
                    "fieldsUsed": di.fields_used,
                    "automationExample": di.automation_example,
                }
                for di in self.downstream_integrations
            ],
            "automationInsights": self.automation_insights,
            "dataQualityIndicators": self.data_quality_indicators,
            "humanReviewTriggers": self.human_review_triggers,
        }


# =============================================================================
# STAGE DEFINITIONS
# =============================================================================

STAGE_AGENT_DEFINITIONS: Dict[int, StageAgentDefinition] = {
    1: StageAgentDefinition(
        stage_number=1,
        stage_name="Domain Categorization",
        display_name="CDISC Domain Mapper",
        purpose="Maps each SOA activity to its appropriate CDISC CDASH domain (LB, VS, EG, PE, etc.) with NCI Thesaurus codes, enabling standardized data collection form generation.",
        extraction_methodology="LLM-based semantic analysis of activity names against CDISC domain definitions. Uses few-shot prompting with domain examples and NCI EVS code lookup for standardization. Confidence scoring based on semantic similarity and domain rule matching.",
        key_outputs=[
            {"field": "cdashDomain", "description": "CDISC CDASH domain code (LB, VS, EG, PE, AE, CM, etc.)"},
            {"field": "cdiscCode", "description": "NCI Thesaurus concept code (e.g., C78713 for Complete Blood Count)"},
            {"field": "cdiscDecode", "description": "Human-readable decode for the CDISC code"},
            {"field": "category", "description": "High-level categorization (LABORATORY, VITAL_SIGNS, ECG, etc.)"},
            {"field": "confidence", "description": "Model confidence score (0.0-1.0) for the mapping"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="EDC Build",
                use_case="Automatic form selection and CRF generation",
                automation_type="direct_mapping",
                fields_used=["cdashDomain", "cdiscCode", "category"],
                automation_example="Domain=LB triggers Lab Form template selection; cdiscCode=C78713 pre-populates CBC test panel fields",
            ),
            DownstreamIntegration(
                system="CDASH Library",
                use_case="Standard field set selection from CDISC library",
                automation_type="configuration",
                fields_used=["cdashDomain", "cdiscCode"],
                automation_example="cdashDomain=VS selects CDASH VS domain fields (VSTEST, VSORRES, VSORRESU, etc.)",
            ),
            DownstreamIntegration(
                system="Data Standards",
                use_case="SDTM mapping specification generation",
                automation_type="rule_generation",
                fields_used=["cdashDomain", "cdiscCode", "category"],
                automation_example="Generates CDASH-to-SDTM mapping rules based on domain assignment",
            ),
        ],
        automation_insights=[
            {"insight": "Domain-Form Mapping", "description": "Each CDASH domain maps to a specific CRF form template in EDC"},
            {"insight": "Test Panel Selection", "description": "cdiscCode determines which lab panels or assessment batteries to include"},
            {"insight": "Edit Check Seeding", "description": "Domain-specific edit checks can be pre-configured based on mapping"},
        ],
        data_quality_indicators=["confidence >= 0.90", "cdiscCode is valid NCI code", "domain is in allowed list"],
        human_review_triggers=["confidence < 0.70", "multiple domains could apply", "activity name is ambiguous"],
    ),

    2: StageAgentDefinition(
        stage_number=2,
        stage_name="Activity Expansion",
        display_name="Activity Component Decomposer",
        purpose="Decomposes composite SOA activities into their constituent components (e.g., 'Physical Exam including weight' -> separate PE and VS assessments), enabling granular scheduling and form assignment.",
        extraction_methodology="PDF-aware LLM analysis using Gemini File API to search protocol text for component details. Pattern recognition for common composite activities (PE+VS, Labs+UA, etc.). Parent-child relationship inference with confidence scoring.",
        key_outputs=[
            {"field": "expandedActivities", "description": "List of component activities derived from parent"},
            {"field": "parentActivityId", "description": "Reference to the original composite activity"},
            {"field": "componentType", "description": "Type of component (primary, secondary, conditional)"},
            {"field": "expansionRationale", "description": "LLM reasoning for the decomposition"},
            {"field": "protocolEvidence", "description": "Supporting text from protocol PDF"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="EDC Build",
                use_case="Granular form generation for each component",
                automation_type="direct_mapping",
                fields_used=["expandedActivities", "componentType"],
                automation_example="Parent 'PE including weight' generates both PE Form and separate Weight field in VS Form",
            ),
            DownstreamIntegration(
                system="IRT Build",
                use_case="Visit procedure list generation",
                automation_type="configuration",
                fields_used=["expandedActivities", "parentActivityId"],
                automation_example="IRT visit checklist includes all expanded components for site guidance",
            ),
            DownstreamIntegration(
                system="Site Operations",
                use_case="Procedure workflow sequencing",
                automation_type="rule_generation",
                fields_used=["expandedActivities", "componentType"],
                automation_example="Primary components scheduled first, secondary components follow",
            ),
        ],
        automation_insights=[
            {"insight": "Form Multiplexing", "description": "One SOA row may require multiple EDC forms when expanded"},
            {"insight": "Dependency Tracking", "description": "Component relationships enable workflow sequencing in site systems"},
            {"insight": "Resource Planning", "description": "Expanded components inform site resource and timing requirements"},
        ],
        data_quality_indicators=["all components have valid domain", "parent-child links are consistent", "no orphan components"],
        human_review_triggers=["expansion creates > 5 components", "ambiguous component boundaries", "protocol text unclear"],
    ),

    3: StageAgentDefinition(
        stage_number=3,
        stage_name="Hierarchy Building",
        display_name="Activity Hierarchy Organizer",
        purpose="Builds parent-child hierarchies for activities that naturally group together (e.g., 'Safety Labs' containing CBC, CMP, UA), enabling logical form organization and visit structure.",
        extraction_methodology="Semantic clustering of activities by domain and purpose. LLM-based grouping inference using activity names and protocol context. Hierarchy depth limited to 3 levels for practical CRF organization.",
        key_outputs=[
            {"field": "hierarchyGroups", "description": "Organized groups of related activities"},
            {"field": "parentActivityId", "description": "Parent activity for grouped items"},
            {"field": "childActivityIds", "description": "List of child activities in the group"},
            {"field": "groupingRationale", "description": "Reason for the hierarchical grouping"},
            {"field": "displayOrder", "description": "Suggested ordering within the hierarchy"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="EDC Build",
                use_case="Form section organization and navigation",
                automation_type="configuration",
                fields_used=["hierarchyGroups", "displayOrder"],
                automation_example="'Safety Labs' parent creates collapsible form section containing CBC, CMP, UA sub-forms",
            ),
            DownstreamIntegration(
                system="CTMS",
                use_case="Visit procedure grouping for site training",
                automation_type="direct_mapping",
                fields_used=["hierarchyGroups", "parentActivityId"],
                automation_example="Site manual organizes procedures by hierarchy for clear workflow guidance",
            ),
            DownstreamIntegration(
                system="Reporting",
                use_case="Hierarchical data aggregation for listings",
                automation_type="rule_generation",
                fields_used=["hierarchyGroups", "childActivityIds"],
                automation_example="Safety reports aggregate child lab results under parent safety category",
            ),
        ],
        automation_insights=[
            {"insight": "Section Generation", "description": "Hierarchy groups map directly to EDC form sections"},
            {"insight": "Completion Tracking", "description": "Parent completion requires all children complete - drives edit checks"},
            {"insight": "Training Materials", "description": "Hierarchy provides structure for site training documents"},
        ],
        data_quality_indicators=["no circular references", "depth <= 3 levels", "all children have valid parent"],
        human_review_triggers=["unusual grouping pattern", "single-child parent", "cross-domain hierarchy"],
    ),

    4: StageAgentDefinition(
        stage_number=4,
        stage_name="Alternative Resolution",
        display_name="Choice Point Resolver",
        purpose="Identifies and structures mutually exclusive alternatives in the SOA (e.g., 'CT or MRI', 'Treatment A or B'), enabling conditional logic in downstream systems.",
        extraction_methodology="Pattern matching for 'or', 'either/or', slash-separated alternatives. LLM disambiguation of true alternatives vs. combined requirements. Confidence scoring based on pattern clarity and protocol context.",
        key_outputs=[
            {"field": "alternativeGroups", "description": "Groups of mutually exclusive options"},
            {"field": "optionIds", "description": "IDs of activities that are alternatives to each other"},
            {"field": "selectionCriteria", "description": "Rules for choosing between alternatives"},
            {"field": "isExclusive", "description": "Whether options are truly mutually exclusive"},
            {"field": "defaultOption", "description": "Recommended default if specified in protocol"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="EDC Build",
                use_case="Conditional form logic and branching",
                automation_type="rule_generation",
                fields_used=["alternativeGroups", "selectionCriteria", "isExclusive"],
                automation_example="Radio button selection for 'CT or MRI' - selecting one hides the other form",
            ),
            DownstreamIntegration(
                system="IRT Build",
                use_case="Randomization arm-specific procedures",
                automation_type="configuration",
                fields_used=["alternativeGroups", "optionIds"],
                automation_example="IRT displays only treatment-specific procedures based on randomization arm",
            ),
            DownstreamIntegration(
                system="Edit Checks",
                use_case="Mutual exclusion validation",
                automation_type="rule_generation",
                fields_used=["alternativeGroups", "isExclusive"],
                automation_example="Edit check: ERROR if both CT and MRI data entered for same visit",
            ),
        ],
        automation_insights=[
            {"insight": "Branching Logic", "description": "Alternatives drive EDC conditional display rules"},
            {"insight": "Randomization Integration", "description": "Treatment alternatives link to IRT arm assignment"},
            {"insight": "Data Consistency", "description": "Mutual exclusion rules prevent contradictory data entry"},
        ],
        data_quality_indicators=["all alternatives have same timing", "selection criteria is clear", "no nested alternatives"],
        human_review_triggers=["unclear if truly exclusive", "> 3 alternatives", "complex selection criteria"],
    ),

    5: StageAgentDefinition(
        stage_number=5,
        stage_name="Specimen Enrichment",
        display_name="Biospecimen Detail Extractor",
        purpose="Extracts detailed specimen collection requirements (tube types, volumes, processing instructions) from protocol text and lab manuals, enabling precise site logistics.",
        extraction_methodology="PDF search for specimen/collection tables using Gemini File API. Pattern matching for tube colors, volumes (mL), temperature requirements. Cross-reference with laboratory specifications extraction module.",
        key_outputs=[
            {"field": "specimenType", "description": "Type of specimen (blood, urine, tissue, etc.)"},
            {"field": "tubeType", "description": "Collection tube specification (EDTA, SST, etc.)"},
            {"field": "volume", "description": "Required collection volume with units"},
            {"field": "processingInstructions", "description": "Handling and processing requirements"},
            {"field": "storageConditions", "description": "Temperature and storage specifications"},
            {"field": "shippingRequirements", "description": "Transport and shipping conditions"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="IRT Build",
                use_case="Kit configuration and supply planning",
                automation_type="configuration",
                fields_used=["tubeType", "volume", "storageConditions"],
                automation_example="IRT kit builder auto-selects tubes: 2x EDTA (4mL), 1x SST (6mL) per visit",
            ),
            DownstreamIntegration(
                system="EDC Build",
                use_case="Collection checklist and deviation tracking",
                automation_type="direct_mapping",
                fields_used=["specimenType", "tubeType", "volume"],
                automation_example="Lab form includes collection checklist with tube types and expected volumes",
            ),
            DownstreamIntegration(
                system="Central Lab",
                use_case="Requisition form pre-population",
                automation_type="direct_mapping",
                fields_used=["specimenType", "processingInstructions", "shippingRequirements"],
                automation_example="Lab requisition auto-filled with specimen handling instructions",
            ),
            DownstreamIntegration(
                system="Supply Chain",
                use_case="Kit inventory forecasting",
                automation_type="rule_generation",
                fields_used=["tubeType", "volume"],
                automation_example="Supply system calculates tube requirements: visits x sites x buffer = order quantity",
            ),
        ],
        automation_insights=[
            {"insight": "Kit Composition", "description": "Specimen details drive exact kit contents for each visit type"},
            {"insight": "Site Training", "description": "Processing instructions feed into site training materials"},
            {"insight": "Deviation Detection", "description": "Volume requirements enable automated deviation flagging"},
        ],
        data_quality_indicators=["volume is numeric with units", "tube type is from standard list", "processing instructions present"],
        human_review_triggers=["unusual tube type", "volume seems incorrect", "conflicting instructions"],
    ),

    6: StageAgentDefinition(
        stage_number=6,
        stage_name="Conditional Expansion",
        display_name="Population Condition Applier",
        purpose="Applies population-specific and clinical conditions from SOA footnotes to activities (e.g., 'females only', 'if clinically indicated'), enabling conditional scheduling.",
        extraction_methodology="Footnote marker detection and text extraction. LLM classification of condition types (population, clinical, timing). Rule structure generation with applicable activity linkage. Provenance tracking to source footnote.",
        key_outputs=[
            {"field": "conditions", "description": "Structured condition objects with rules"},
            {"field": "conditionType", "description": "Type: POPULATION, CLINICAL, TIMING, SAFETY"},
            {"field": "ruleExpression", "description": "Structured rule in evaluatable format"},
            {"field": "applicableActivities", "description": "Activities this condition applies to"},
            {"field": "footnoteSource", "description": "Source footnote marker and text"},
            {"field": "edcImpact", "description": "How this affects EDC form logic"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="EDC Build",
                use_case="Dynamic form visibility and edit checks",
                automation_type="rule_generation",
                fields_used=["conditions", "ruleExpression", "applicableActivities"],
                automation_example="Pregnancy test form shows only when SEX='F' AND AGE>=childbearing age",
            ),
            DownstreamIntegration(
                system="IRT Build",
                use_case="Conditional visit scheduling",
                automation_type="configuration",
                fields_used=["conditions", "conditionType", "applicableActivities"],
                automation_example="IRT schedules MRI only for subjects with brain metastases at baseline",
            ),
            DownstreamIntegration(
                system="Eligibility",
                use_case="Screening criteria validation",
                automation_type="rule_generation",
                fields_used=["conditions", "ruleExpression"],
                automation_example="Population conditions feed eligibility check automation",
            ),
            DownstreamIntegration(
                system="Safety Monitoring",
                use_case="Conditional safety assessment triggers",
                automation_type="rule_generation",
                fields_used=["conditions", "conditionType"],
                automation_example="Additional ECG triggered when QTc > threshold per footnote rule",
            ),
        ],
        automation_insights=[
            {"insight": "Edit Check Generation", "description": "Conditions translate directly to EDC conditional logic"},
            {"insight": "Visit Customization", "description": "Population conditions enable subject-specific visit schedules"},
            {"insight": "Protocol Deviation Prevention", "description": "Automated condition checking prevents missed assessments"},
        ],
        data_quality_indicators=["condition has valid rule expression", "footnote source is traceable", "applicable activities exist"],
        human_review_triggers=["complex nested conditions", "ambiguous condition text", "condition conflicts with other rules"],
    ),

    7: StageAgentDefinition(
        stage_number=7,
        stage_name="Timing Distribution",
        display_name="Timing Window Expander",
        purpose="Expands timing annotations (BI/EOI, pre-dose/post-dose, time windows) into discrete scheduled instances, enabling precise visit window calculations.",
        extraction_methodology="Pattern recognition for timing markers (BI, EOI, predose, +30min, etc.). Time window parsing and standardization. LLM interpretation of complex timing descriptions. Window calculation based on protocol-defined tolerances.",
        key_outputs=[
            {"field": "timingInstances", "description": "Expanded discrete timing points"},
            {"field": "timingModifier", "description": "Type: BI, EOI, PREDOSE, POSTDOSE, WINDOW"},
            {"field": "offsetMinutes", "description": "Time offset from reference point"},
            {"field": "windowStart", "description": "Earliest acceptable time"},
            {"field": "windowEnd", "description": "Latest acceptable time"},
            {"field": "referenceEvent", "description": "Event this timing is relative to (dosing, visit start)"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="EDC Build",
                use_case="Visit window calculation and out-of-window flags",
                automation_type="rule_generation",
                fields_used=["windowStart", "windowEnd", "referenceEvent"],
                automation_example="Edit check: WARN if assessment time outside ±30 min window from dosing",
            ),
            DownstreamIntegration(
                system="IRT Build",
                use_case="Appointment scheduling with time constraints",
                automation_type="configuration",
                fields_used=["timingInstances", "offsetMinutes", "referenceEvent"],
                automation_example="IRT schedules PK draw at dose +2hr ±15min with automated reminder",
            ),
            DownstreamIntegration(
                system="PK Analysis",
                use_case="Nominal time assignment for concentration data",
                automation_type="direct_mapping",
                fields_used=["offsetMinutes", "referenceEvent"],
                automation_example="PK system receives nominal timepoints for concentration-time profiles",
            ),
            DownstreamIntegration(
                system="Site Operations",
                use_case="Visit timeline generation",
                automation_type="direct_mapping",
                fields_used=["timingInstances", "timingModifier"],
                automation_example="Site receives visit day timeline: Pre-dose labs → Dosing → 2hr PK → 4hr PK",
            ),
        ],
        automation_insights=[
            {"insight": "Window Edit Checks", "description": "Timing windows auto-generate out-of-window deviation checks"},
            {"insight": "PK Scheduling", "description": "Offset times enable automated PK sampling schedule generation"},
            {"insight": "Site Logistics", "description": "Timing sequence informs site procedure ordering and duration"},
        ],
        data_quality_indicators=["windows are non-negative", "reference event is defined", "no overlapping windows"],
        human_review_triggers=["complex timing pattern", "unclear reference event", "window tolerance missing"],
    ),

    8: StageAgentDefinition(
        stage_number=8,
        stage_name="Cycle Expansion",
        display_name="Treatment Cycle Generator",
        purpose="Expands repeating cycle patterns (e.g., 'Cycles 1-6, Day 1 of each 21-day cycle') into individual visit instances, enabling complete schedule generation.",
        extraction_methodology="Cycle pattern detection from visit/epoch headers. LLM interpretation of cycle descriptions (duration, repetition count). Visit instance generation with proper sequencing. Handling of variable cycle counts (until PD, max N cycles).",
        key_outputs=[
            {"field": "expandedEncounters", "description": "Individual visit instances for each cycle"},
            {"field": "cycleNumber", "description": "Cycle number (1, 2, 3, ...)"},
            {"field": "dayInCycle", "description": "Day within the cycle"},
            {"field": "cycleDuration", "description": "Length of each cycle in days"},
            {"field": "maxCycles", "description": "Maximum number of cycles or 'until progression'"},
            {"field": "cyclePattern", "description": "Description of the repeating pattern"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="EDC Build",
                use_case="Visit form instance generation",
                automation_type="configuration",
                fields_used=["expandedEncounters", "cycleNumber", "dayInCycle"],
                automation_example="EDC generates C1D1, C1D8, C1D15, C2D1, C2D8... form instances automatically",
            ),
            DownstreamIntegration(
                system="IRT Build",
                use_case="Treatment supply forecasting per cycle",
                automation_type="rule_generation",
                fields_used=["maxCycles", "cycleDuration"],
                automation_example="IRT calculates drug supply: 6 cycles x 21 days = 126 days supply per subject",
            ),
            DownstreamIntegration(
                system="CTMS",
                use_case="Expected visit count for enrollment planning",
                automation_type="direct_mapping",
                fields_used=["expandedEncounters", "maxCycles"],
                automation_example="CTMS forecasts: 100 subjects x 6 cycles x 3 visits/cycle = 1800 expected visits",
            ),
            DownstreamIntegration(
                system="Patient Portal",
                use_case="Subject-facing visit schedule display",
                automation_type="direct_mapping",
                fields_used=["expandedEncounters", "cycleNumber", "dayInCycle"],
                automation_example="Patient app shows: 'Your next visit: Cycle 3, Day 1 (approximately March 15)'",
            ),
        ],
        automation_insights=[
            {"insight": "Visit Generation", "description": "Cycle expansion creates complete EDC visit structure automatically"},
            {"insight": "Supply Planning", "description": "Cycle count drives drug and kit supply calculations"},
            {"insight": "Study Duration", "description": "Max cycles determine expected study duration for planning"},
        ],
        data_quality_indicators=["cycle duration > 0", "max cycles is defined or 'until PD'", "day numbers are valid"],
        human_review_triggers=["uncertain cycle count", "variable cycle duration", "complex termination criteria"],
    ),

    9: StageAgentDefinition(
        stage_number=9,
        stage_name="Protocol Mining",
        display_name="Cross-Reference Enricher",
        purpose="Cross-references SOA activities with other extracted protocol sections (lab specs, biospecimen handling, safety monitoring) to enrich activity details beyond the SOA table.",
        extraction_methodology="Module matching using extraction outputs from other agents (laboratory, biospecimen, safety, etc.). PDF validation for low-confidence matches using Gemini File API. Confidence scoring based on semantic similarity and field coverage.",
        key_outputs=[
            {"field": "enrichments", "description": "Additional details from protocol mining"},
            {"field": "sourcesUsed", "description": "Which extraction modules provided data"},
            {"field": "labManualEnrichment", "description": "Lab-specific details from lab specs module"},
            {"field": "biospecimenEnrichment", "description": "Specimen details from biospecimen module"},
            {"field": "safetyEnrichment", "description": "Safety monitoring details"},
            {"field": "overallConfidence", "description": "Combined confidence from all sources"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="EDC Build",
                use_case="Pre-populated form field values",
                automation_type="direct_mapping",
                fields_used=["labManualEnrichment", "biospecimenEnrichment"],
                automation_example="Lab form pre-fills expected ranges, units, and collection requirements from mining",
            ),
            DownstreamIntegration(
                system="Central Lab",
                use_case="Test panel configuration",
                automation_type="configuration",
                fields_used=["labManualEnrichment", "sourcesUsed"],
                automation_example="Central lab system receives exact test codes and expected values from protocol",
            ),
            DownstreamIntegration(
                system="Safety Database",
                use_case="AE expectedness determination",
                automation_type="rule_generation",
                fields_used=["safetyEnrichment"],
                automation_example="Safety system pre-configured with expected AEs and monitoring thresholds",
            ),
            DownstreamIntegration(
                system="Site Training",
                use_case="Comprehensive procedure documentation",
                automation_type="direct_mapping",
                fields_used=["enrichments", "sourcesUsed"],
                automation_example="Site manual combines SOA with enriched details for complete procedure guides",
            ),
        ],
        automation_insights=[
            {"insight": "Data Completeness", "description": "Mining fills gaps that SOA table alone cannot provide"},
            {"insight": "Cross-Validation", "description": "Multiple sources increase confidence in extracted values"},
            {"insight": "Protocol Consistency", "description": "Mining detects discrepancies between SOA and detailed sections"},
        ],
        data_quality_indicators=["at least one source used", "confidence >= 0.70", "no conflicting enrichments"],
        human_review_triggers=["confidence < 0.70", "conflicting data between sources", "sparse enrichment data"],
    ),

    10: StageAgentDefinition(
        stage_number=10,
        stage_name="Human Review Assembly",
        display_name="Review Package Builder",
        purpose="Aggregates all items requiring human review from stages 1-9 and 12 into a structured API-ready package for UI-based review and decision making.",
        extraction_methodology="Collection of review items from each stage result. Priority classification (Critical, High, Medium, Low). Auto-approval of high-confidence items (>= 0.95). Grouping by stage and type for efficient review workflow.",
        key_outputs=[
            {"field": "reviewPackage", "description": "Complete review package for UI"},
            {"field": "sections", "description": "Review items organized by stage"},
            {"field": "totalItems", "description": "Count of items requiring review"},
            {"field": "autoApprovedCount", "description": "Items auto-approved by confidence threshold"},
            {"field": "pendingCriticalCount", "description": "Critical items awaiting review"},
            {"field": "draftSchedule", "description": "Draft USDM schedule for preview"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="Review UI",
                use_case="Human review workflow interface",
                automation_type="direct_mapping",
                fields_used=["reviewPackage", "sections"],
                automation_example="React UI displays review items with approve/reject/modify actions",
            ),
            DownstreamIntegration(
                system="Audit Trail",
                use_case="Decision tracking and compliance",
                automation_type="direct_mapping",
                fields_used=["reviewPackage", "autoApprovedCount"],
                automation_example="Audit log records each decision with timestamp and reviewer ID",
            ),
            DownstreamIntegration(
                system="Quality Metrics",
                use_case="Extraction quality monitoring",
                automation_type="rule_generation",
                fields_used=["totalItems", "autoApprovedCount", "pendingCriticalCount"],
                automation_example="Dashboard shows auto-approval rate and critical item trends",
            ),
        ],
        automation_insights=[
            {"insight": "Workload Optimization", "description": "Auto-approval reduces manual review burden for high-confidence items"},
            {"insight": "Risk Prioritization", "description": "Critical items surfaced first for expert attention"},
            {"insight": "Quality Feedback", "description": "Review patterns inform extraction model improvements"},
        ],
        data_quality_indicators=["all stages represented", "priorities are assigned", "draft schedule included"],
        human_review_triggers=["N/A - this stage creates the review package itself"],
    ),

    11: StageAgentDefinition(
        stage_number=11,
        stage_name="Schedule Generation",
        display_name="Final Schedule Generator",
        purpose="Applies human review decisions from Stage 10 to produce the final USDM-compliant visit schedule, resolving all pending choices and confirmations.",
        extraction_methodology="Decision application from Stage 10 review package. Alternative resolution (keep selected, remove rejected). Cycle confirmation (expand or collapse). Audit trail generation for all applied decisions.",
        key_outputs=[
            {"field": "finalUsdm", "description": "Complete USDM-compliant schedule"},
            {"field": "decisionsApplied", "description": "Count of decisions applied"},
            {"field": "auditTrail", "description": "Record of all changes made"},
            {"field": "approvedCount", "description": "Items approved"},
            {"field": "rejectedCount", "description": "Items rejected"},
            {"field": "modifiedCount", "description": "Items modified with custom values"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="EDC Build",
                use_case="Final CRF structure generation",
                automation_type="configuration",
                fields_used=["finalUsdm"],
                automation_example="EDC system receives final schedule for complete CRF build",
            ),
            DownstreamIntegration(
                system="IRT Build",
                use_case="Confirmed visit structure for randomization",
                automation_type="configuration",
                fields_used=["finalUsdm", "auditTrail"],
                automation_example="IRT receives approved schedule with full decision provenance",
            ),
            DownstreamIntegration(
                system="CTMS",
                use_case="Study setup with confirmed parameters",
                automation_type="direct_mapping",
                fields_used=["finalUsdm"],
                automation_example="CTMS imports final visit schedule for site management",
            ),
            DownstreamIntegration(
                system="Regulatory",
                use_case="Schedule documentation for submissions",
                automation_type="direct_mapping",
                fields_used=["finalUsdm", "auditTrail"],
                automation_example="FDA submission includes USDM schedule with decision audit trail",
            ),
        ],
        automation_insights=[
            {"insight": "Decision Finality", "description": "Applied decisions become immutable for downstream system consumption"},
            {"insight": "Audit Compliance", "description": "Full audit trail supports regulatory inspection requirements"},
            {"insight": "Version Control", "description": "Each generation creates a versioned, traceable schedule"},
        ],
        data_quality_indicators=["no pending critical items", "all decisions applied", "audit trail complete"],
        human_review_triggers=["pending critical items remain", "decision conflicts detected"],
    ),

    12: StageAgentDefinition(
        stage_number=12,
        stage_name="USDM Compliance",
        display_name="USDM Code Validator",
        purpose="Ensures all Code objects have complete 6-field USDM structure (code, decode, codeSystem, codeSystemVersion, instanceType) with valid NCI Thesaurus codes.",
        extraction_methodology="Schema validation against USDM 4.0 specification. NCI EVS API lookup for code validation. Auto-correction of common issues (missing codeSystemVersion, instanceType). Referential integrity checking.",
        key_outputs=[
            {"field": "compliantUsdm", "description": "USDM output with all codes validated"},
            {"field": "issuesFound", "description": "List of compliance issues detected"},
            {"field": "issuesFixed", "description": "Issues auto-corrected"},
            {"field": "issuesRemaining", "description": "Issues requiring manual attention"},
            {"field": "validationReport", "description": "Detailed validation results"},
        ],
        downstream_integrations=[
            DownstreamIntegration(
                system="CDISC Compliance",
                use_case="Standards validation for submissions",
                automation_type="validation",
                fields_used=["compliantUsdm", "validationReport"],
                automation_example="CDISC validation confirms all codes are valid NCI Thesaurus references",
            ),
            DownstreamIntegration(
                system="Data Standards",
                use_case="Controlled terminology enforcement",
                automation_type="validation",
                fields_used=["compliantUsdm", "issuesFound"],
                automation_example="Data standards team receives validation report for terminology governance",
            ),
            DownstreamIntegration(
                system="EDC Build",
                use_case="Code list population from validated codes",
                automation_type="configuration",
                fields_used=["compliantUsdm"],
                automation_example="EDC code lists populated with validated CDISC codes and decodes",
            ),
            DownstreamIntegration(
                system="SDTM Mapping",
                use_case="Terminology mapping specifications",
                automation_type="direct_mapping",
                fields_used=["compliantUsdm"],
                automation_example="SDTM mapping specs reference validated code objects for terminology alignment",
            ),
        ],
        automation_insights=[
            {"insight": "Regulatory Compliance", "description": "USDM compliance is prerequisite for FDA/EMA digital submissions"},
            {"insight": "Interoperability", "description": "Standard codes enable system-to-system data exchange"},
            {"insight": "Quality Assurance", "description": "Code validation catches terminology errors before downstream propagation"},
        ],
        data_quality_indicators=["all codes have 6 fields", "codes are valid NCI", "no referential integrity errors"],
        human_review_triggers=["unknown code system", "deprecated NCI code", "missing mandatory code"],
    ),
}


def get_agent_definition(stage: int) -> Optional[Dict[str, Any]]:
    """Get the agent definition for a specific stage."""
    definition = STAGE_AGENT_DEFINITIONS.get(stage)
    if definition:
        return definition.to_dict()
    return None


def get_all_agent_definitions() -> Dict[int, Dict[str, Any]]:
    """Get all agent definitions as a dictionary."""
    return {
        stage: definition.to_dict()
        for stage, definition in STAGE_AGENT_DEFINITIONS.items()
    }
