"""
Agent Documentation Registry - Enhanced for Downstream Automation

Comprehensive documentation for all 16+ extraction agents in the protocol digitalization pipeline.
Each agent's documentation includes:
- Purpose and scope
- Key insights extracted with JSON paths
- Downstream automation configurations (EDC edit checks, IRT rules, etc.)
- Cross-agent synergies for combined insights
- Validation rules for data consistency
- System-specific configuration templates

This documentation is embedded into the final USDM JSON output to enable:
1. Automated downstream system configuration (EDC, IRT, ePRO, Safety DB)
2. Cross-agent data validation and consistency checks
3. Human review prioritization based on data criticality
4. Quality assurance workflows with specific checkpoints
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class DownstreamSystem(Enum):
    """Target downstream systems that consume agent outputs."""
    EDC = "Electronic Data Capture"
    IRT = "Interactive Response Technology"
    IWRS = "Interactive Web Response System"
    CTMS = "Clinical Trial Management System"
    EPRO = "Electronic Patient-Reported Outcomes"
    ECOA = "Electronic Clinical Outcome Assessment"
    DRUG_SUPPLY = "Drug Supply Management"
    SAFETY_DB = "Safety Database (Pharmacovigilance)"
    TMF = "Trial Master File"
    CENTRAL_LAB = "Central Laboratory"
    IMAGING = "Central Imaging"
    BIOBANK = "Biospecimen Repository"
    RTSM = "Randomization & Trial Supply Management"
    REGULATORY = "Regulatory Submission Systems"


class AutomationCategory(Enum):
    """Categories of downstream automation enabled by agent outputs."""
    FORM_DESIGN = "EDC Form Design & Edit Checks"
    RANDOMIZATION = "Randomization Configuration"
    SUPPLY_CHAIN = "Drug Supply & Kit Management"
    SAFETY_RULES = "Safety Monitoring Rules"
    LAB_SETUP = "Laboratory Panel Configuration"
    VISIT_SCHEDULE = "Visit Schedule Programming"
    ELIGIBILITY = "Eligibility Verification"
    REGULATORY_DOCS = "Regulatory Document Generation"
    SITE_TRAINING = "Site Training Materials"
    DATA_STANDARDS = "CDISC Data Standards Mapping"


@dataclass
class AutomationRule:
    """A specific automation rule that can be generated from agent data."""
    rule_id: str
    rule_type: str  # "edit_check", "alert", "validation", "derivation", "workflow"
    target_system: DownstreamSystem
    description: str
    source_data_path: str
    rule_logic: str  # Pseudo-code or description of the rule
    example: Optional[str] = None


@dataclass
class CrossAgentSynergy:
    """Describes how combining data from multiple agents enables richer automation."""
    synergy_id: str
    name: str
    agents_involved: List[str]
    description: str
    combined_insight: str
    automation_enabled: str
    example_output: Optional[str] = None


@dataclass
class ValidationRule:
    """Cross-agent validation rule for data consistency."""
    rule_id: str
    name: str
    agents_involved: List[str]
    validation_type: str  # "consistency", "completeness", "cross_reference", "range"
    description: str
    check_logic: str
    severity: str  # "error", "warning", "info"


@dataclass
class SystemConfiguration:
    """System-specific configuration template derived from agent data."""
    system: DownstreamSystem
    config_type: str
    description: str
    data_sources: List[str]  # JSON paths
    output_format: str
    example_config: Optional[Dict[str, Any]] = None


@dataclass
class AgentInsight:
    """A specific insight or data point extracted by an agent."""
    name: str
    description: str
    data_path: str
    downstream_uses: List[str]
    automation_category: AutomationCategory
    priority: str
    # Enhanced fields
    automation_rules: List[AutomationRule] = field(default_factory=list)
    validation_checks: List[str] = field(default_factory=list)


@dataclass
class AgentDocumentation:
    """Complete documentation for a single extraction agent."""

    agent_id: str
    display_name: str
    instance_type: str
    wave: int
    priority: int

    # Core documentation
    purpose: str
    scope: str
    key_sections_analyzed: List[str]

    # What the agent extracts
    key_insights: List[AgentInsight]

    # How outputs are used
    downstream_systems: List[DownstreamSystem]
    automation_use_cases: List[str]

    # Integration with other agents
    depends_on: List[str]
    enriches: List[str]
    cross_references: List[str]

    # Quality and compliance
    cdisc_domains: List[str]
    regulatory_relevance: str

    # Metadata
    schema_file: str
    typical_extraction_time_seconds: int = 30

    # Enhanced fields for downstream automation
    automation_rules: List[AutomationRule] = field(default_factory=list)
    cross_agent_synergies: List[CrossAgentSynergy] = field(default_factory=list)
    validation_rules: List[ValidationRule] = field(default_factory=list)
    system_configurations: List[SystemConfiguration] = field(default_factory=list)


# =============================================================================
# WAVE 0: FOUNDATION AGENT
# =============================================================================

STUDY_METADATA_DOC = AgentDocumentation(
    agent_id="study_metadata",
    display_name="Study Metadata",
    instance_type="Study",
    wave=0,
    priority=0,

    purpose="""
    Extracts foundational study-level metadata that all other agents depend on.
    This agent runs first and provides the context (protocol ID, phase, therapeutic area,
    population characteristics) that enables accurate extraction by downstream agents.
    """,

    scope="""
    - Protocol identification (NCT, EudraCT, IND numbers)
    - Study phase, type, and design overview
    - Sponsor information
    - Target population characteristics (disease, age, sex, biomarkers)
    - Key milestones and timelines
    - Design metadata (randomization, blinding, enrollment targets)
    """,

    key_sections_analyzed=[
        "Title Page / Cover",
        "Synopsis",
        "Section 1: Introduction and Background",
        "Section 3: Study Objectives",
        "Section 4: Study Design",
        "Section 5: Study Population",
    ],

    key_insights=[
        AgentInsight(
            name="Protocol Identifiers",
            description="NCT number, EudraCT, IND numbers for regulatory cross-referencing",
            data_path="studyIdentifiers[]",
            downstream_uses=["CTMS study registration", "Regulatory submission linking", "ClinicalTrials.gov sync"],
            automation_category=AutomationCategory.REGULATORY_DOCS,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="CTMS_REG_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.CTMS,
                    description="Auto-populate CTMS study record from protocol identifiers",
                    source_data_path="studyIdentifiers[].identifier",
                    rule_logic="FOR EACH id IN studyIdentifiers: SET ctms.registry[id.type] = id.identifier",
                    example="NCT number → CTMS.NCT_ID field"
                ),
            ],
            validation_checks=["All identifiers must match ClinicalTrials.gov registry"]
        ),
        AgentInsight(
            name="Study Phase",
            description="Clinical trial phase with NCI Thesaurus code",
            data_path="studyPhase",
            downstream_uses=["Regulatory pathway determination", "Site qualification criteria", "Budget estimation"],
            automation_category=AutomationCategory.REGULATORY_DOCS,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="IRT_PHASE_001",
                    rule_type="validation",
                    target_system=DownstreamSystem.IRT,
                    description="Validate IRT complexity requirements based on phase",
                    source_data_path="studyPhase.decode",
                    rule_logic="IF phase IN ['Phase 1', 'Phase 1/2'] THEN require dose_escalation_module",
                    example="Phase 1 → Enable dose escalation cohort management"
                ),
            ]
        ),
        AgentInsight(
            name="Target Population",
            description="Disease, age range, sex, biomarker requirements, performance status",
            data_path="studyPopulation",
            downstream_uses=["Site feasibility scoring", "Patient recruitment targeting", "EDC eligibility forms"],
            automation_category=AutomationCategory.ELIGIBILITY,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_ELIG_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Generate age range edit check for eligibility form",
                    source_data_path="studyPopulation.ageRange",
                    rule_logic="IF subject_age < min_age OR subject_age > max_age THEN RAISE eligibility_failure",
                    example="Age 18-75 → Edit check: BRTHDT must result in age between 18 and 75 at screening"
                ),
            ]
        ),
        AgentInsight(
            name="Study Milestones",
            description="Screening period, enrollment duration, treatment duration, follow-up",
            data_path="studyMilestones",
            downstream_uses=["CTMS timeline configuration", "Site contract milestones", "Resource planning"],
            automation_category=AutomationCategory.VISIT_SCHEDULE,
            priority="high"
        ),
        AgentInsight(
            name="Design Metadata",
            description="Randomization ratio, blinding type, target enrollment, countries",
            data_path="studyDesignInfo",
            downstream_uses=["IRT configuration", "Drug supply planning", "Regulatory strategy"],
            automation_category=AutomationCategory.RANDOMIZATION,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="IRT_RAND_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.IRT,
                    description="Configure IRT randomization ratio",
                    source_data_path="studyDesignInfo.randomizationRatio",
                    rule_logic="SET irt.allocation_ratio = randomizationRatio; SET irt.block_size = CALCULATE(ratio)",
                    example="2:1 ratio → IRT blocks of 3 or 6"
                ),
            ]
        ),
    ],

    downstream_systems=[
        DownstreamSystem.EDC,
        DownstreamSystem.CTMS,
        DownstreamSystem.IRT,
        DownstreamSystem.REGULATORY,
    ],

    automation_use_cases=[
        "Pre-populate EDC study header and demographics forms",
        "Configure CTMS study record with identifiers and milestones",
        "Set IRT enrollment caps by country/region",
        "Generate ClinicalTrials.gov registration data",
        "Auto-configure site feasibility questionnaires",
    ],

    depends_on=[],
    enriches=["arms_design", "endpoints_estimands_sap", "eligibility_criteria"],
    cross_references=["quality_management", "data_management"],

    cdisc_domains=["DM", "DS"],
    regulatory_relevance="Foundation for ICH M11 sections 1-5, CTD Module 5",
    schema_file="study_metadata_schema.json",
    typical_extraction_time_seconds=45,

    automation_rules=[
        AutomationRule(
            rule_id="EDC_STUDY_001",
            rule_type="derivation",
            target_system=DownstreamSystem.EDC,
            description="Generate study-level EDC configuration",
            source_data_path="*",
            rule_logic="CREATE study_config FROM (protocolId, studyTitle, studyPhase, therapeuticArea)",
        ),
    ],

    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_META_ARMS_001",
            name="Study Context + Arms → IRT Complete Configuration",
            agents_involved=["study_metadata", "arms_design"],
            description="Combining study design info with arm definitions enables complete IRT setup",
            combined_insight="Randomization ratio + arm definitions + stratification = Complete IRT randomization module",
            automation_enabled="One-click IRT vendor specification generation",
            example_output='{"randomization": {"ratio": "2:1", "arms": ["Drug A", "Placebo"], "stratification": ["ECOG", "Prior Therapy"]}}'
        ),
        CrossAgentSynergy(
            synergy_id="SYN_META_ELIG_001",
            name="Population + Eligibility → Smart Screening",
            agents_involved=["study_metadata", "eligibility_criteria", "laboratory_specifications"],
            description="Population characteristics + criteria + lab values = intelligent screening tool",
            combined_insight="Age/sex + inclusion/exclusion + lab ranges = Complete eligibility calculator",
            automation_enabled="Site-facing eligibility screening app with real-time validation",
        ),
    ],

    validation_rules=[
        ValidationRule(
            rule_id="VAL_META_001",
            name="Phase-Design Consistency",
            agents_involved=["study_metadata", "arms_design"],
            validation_type="consistency",
            description="Verify study phase is consistent with arm complexity",
            check_logic="IF phase='Phase 1' THEN arms.count SHOULD BE <= 3",
            severity="warning"
        ),
    ],

    system_configurations=[
        SystemConfiguration(
            system=DownstreamSystem.EDC,
            config_type="study_header",
            description="EDC study-level configuration derived from metadata",
            data_sources=["protocolId", "studyTitle", "studyPhase", "sponsorName"],
            output_format="EDC vendor import format (Medidata Rave, Oracle InForm, Veeva Vault)",
            example_config={
                "study_id": "{protocolId}",
                "study_name": "{studyTitle}",
                "phase": "{studyPhase.decode}",
                "sponsor": "{sponsorName}",
                "therapeutic_area": "{therapeuticArea}"
            }
        ),
    ],
)


# =============================================================================
# WAVE 1: CORE MODULES (P0 - CRITICAL)
# =============================================================================

ARMS_DESIGN_DOC = AgentDocumentation(
    agent_id="arms_design",
    display_name="Treatment Arms & Study Design",
    instance_type="StudyDesign",
    wave=1,
    priority=0,

    purpose="""
    Extracts the complete treatment design including study arms, epochs, dosing regimens,
    randomization configuration, and drug supply requirements. This is the primary source
    for IRT/IWRS and drug supply management system configuration.
    """,

    scope="""
    - Study arms (experimental, comparator, placebo)
    - Treatment epochs (screening, treatment, follow-up)
    - Study cells (arm × epoch matrix)
    - Dosing regimens (dose, frequency, route, cycle length)
    - Dose modification rules and triggers
    - Randomization details (ratio, stratification, block size, algorithm)
    - Drug supply kit configurations
    """,

    key_sections_analyzed=[
        "Section 4: Study Design",
        "Section 5: Study Population",
        "Section 6: Study Drug/Treatment",
        "Section 7: Dose Modifications",
        "Section 9: Schedule of Assessments",
    ],

    key_insights=[
        AgentInsight(
            name="Study Arms",
            description="Complete arm definitions with interventions, types, and allocation ratios",
            data_path="studyArms[]",
            downstream_uses=["IRT arm configuration", "EDC treatment assignment forms", "Drug supply forecasting"],
            automation_category=AutomationCategory.RANDOMIZATION,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="IRT_ARM_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.IRT,
                    description="Generate IRT arm configuration from study arms",
                    source_data_path="studyArms[]",
                    rule_logic="""
                    FOR EACH arm IN studyArms:
                        CREATE irt_arm {
                            arm_code: arm.id,
                            arm_name: arm.name,
                            arm_type: arm.type.decode,
                            allocation: arm.allocationPercentage,
                            interventions: arm.interventions[].name
                        }
                    """,
                    example='{"arm_code": "A", "arm_name": "Drug + Chemo", "allocation": 66.7}'
                ),
                AutomationRule(
                    rule_id="EDC_ARM_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.EDC,
                    description="Generate treatment assignment dropdown options",
                    source_data_path="studyArms[].name",
                    rule_logic="CREATE codelist 'TREATMENT_ARM' WITH values FROM studyArms[].name",
                ),
            ]
        ),
        AgentInsight(
            name="Dosing Regimens",
            description="Dose, unit, frequency, route, cycle length, dose calculation basis",
            data_path="studyArms[].interventions[].dosingRegimen",
            downstream_uses=["Drug accountability forms", "IRT dispensing rules", "Pharmacy manual generation"],
            automation_category=AutomationCategory.SUPPLY_CHAIN,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="IRT_DISP_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.IRT,
                    description="Configure IRT dispensing rules from dosing regimen",
                    source_data_path="studyArms[].interventions[].dosingRegimen",
                    rule_logic="""
                    FOR EACH regimen:
                        SET dispense_quantity = regimen.dose * regimen.frequency * cycle_length
                        SET kit_type = DERIVE_KIT(regimen.route, regimen.formulation)
                        SET dispense_visits = MATCH(soa_schedule.visits, regimen.schedule)
                    """,
                    example="400mg BID x 28 days = 56 tablets per cycle, dispense at Day 1 of each cycle"
                ),
                AutomationRule(
                    rule_id="EDC_DOSE_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Validate dispensed dose against protocol regimen",
                    source_data_path="studyArms[].interventions[].dosingRegimen.dose",
                    rule_logic="IF dispensed_dose != protocol_dose AND NOT dose_modification THEN RAISE query",
                ),
            ]
        ),
        AgentInsight(
            name="Stratification Factors",
            description="Randomization stratification with levels and definitions",
            data_path="designMetadata.stratificationFactors[]",
            downstream_uses=["IRT stratification setup", "EDC stratification CRF", "Analysis programming"],
            automation_category=AutomationCategory.RANDOMIZATION,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="IRT_STRAT_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.IRT,
                    description="Configure IRT stratification from protocol factors",
                    source_data_path="designMetadata.stratificationFactors[]",
                    rule_logic="""
                    FOR EACH factor:
                        CREATE strat_factor {
                            name: factor.name,
                            levels: factor.levels[],
                            edc_field: DERIVE_FIELD(factor.name)
                        }
                    GENERATE strat_combinations = CARTESIAN_PRODUCT(all_factors.levels)
                    """,
                    example="ECOG (0-1, 2) × Prior Therapy (Yes, No) = 4 strata"
                ),
                AutomationRule(
                    rule_id="EDC_STRAT_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.EDC,
                    description="Generate stratification CRF fields",
                    source_data_path="designMetadata.stratificationFactors[]",
                    rule_logic="FOR EACH factor: CREATE dropdown_field WITH options = factor.levels",
                ),
            ]
        ),
        AgentInsight(
            name="Dose Modification Rules",
            description="Reduction levels, triggers, hold/resume criteria",
            data_path="studyArms[].interventions[].doseModifications",
            downstream_uses=["EDC dose modification forms", "Safety alert rules", "Medical monitor dashboards"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="high",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_DOSEMOD_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Validate dose modification follows protocol levels",
                    source_data_path="studyArms[].interventions[].doseModifications.levels[]",
                    rule_logic="""
                    IF new_dose NOT IN allowed_dose_levels THEN RAISE 'Invalid dose level'
                    IF dose_reduction_reason IS NULL THEN RAISE 'Reason required for dose modification'
                    """,
                ),
            ]
        ),
        AgentInsight(
            name="Drug Supply Configuration",
            description="Kit types, dispensing schedule, supply model",
            data_path="designMetadata.drugSupply",
            downstream_uses=["IRT kit management", "Depot configuration", "Supply chain forecasting"],
            automation_category=AutomationCategory.SUPPLY_CHAIN,
            priority="high",
            automation_rules=[
                AutomationRule(
                    rule_id="IRT_KIT_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.RTSM,
                    description="Generate kit configuration and depot requirements",
                    source_data_path="designMetadata.drugSupply",
                    rule_logic="""
                    FOR EACH kit_type:
                        SET initial_depot_stock = enrollment_target * cycles * safety_stock_factor
                        SET reorder_point = site_average_enrollment * lead_time_days
                    """,
                ),
            ]
        ),
    ],

    downstream_systems=[
        DownstreamSystem.IRT,
        DownstreamSystem.IWRS,
        DownstreamSystem.RTSM,
        DownstreamSystem.EDC,
        DownstreamSystem.DRUG_SUPPLY,
    ],

    automation_use_cases=[
        "Auto-generate IRT randomization and drug dispensing configuration",
        "Create EDC treatment assignment and dose modification CRFs",
        "Configure drug supply forecasting models",
        "Generate pharmacy manuals and dispensing instructions",
        "Set up stratification factor data entry forms",
        "Configure enrollment caps by stratum/region",
    ],

    depends_on=["study_metadata"],
    enriches=["safety_decision_points", "pkpd_sampling", "biospecimen_handling"],
    cross_references=["concomitant_medications", "adverse_events"],

    cdisc_domains=["TA", "TE", "TI", "TV", "EX", "EC"],
    regulatory_relevance="ICH M11 Section 6 (Treatment), CTD Module 2.7.1",
    schema_file="arms_design_schema.json",
    typical_extraction_time_seconds=60,

    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_ARMS_SAFETY_001",
            name="Dosing + Safety Rules → Complete Dose Management",
            agents_involved=["arms_design", "safety_decision_points", "laboratory_specifications"],
            description="Combining dosing regimens with safety thresholds and lab triggers enables intelligent dose management",
            combined_insight="Protocol doses + reduction levels + lab thresholds = Automated dose recommendation engine",
            automation_enabled="EDC can suggest appropriate dose level based on current labs and AEs",
            example_output='{"current_dose": "400mg", "recommended_action": "REDUCE to 300mg", "trigger": "ANC < 1000", "confidence": 0.95}'
        ),
        CrossAgentSynergy(
            synergy_id="SYN_ARMS_SOA_001",
            name="Arms + SOA → Visit-Based Dispensing",
            agents_involved=["arms_design", "soa_schedule"],
            description="Arm-specific dosing matched to visit schedule enables precise dispensing rules",
            combined_insight="Which drug, what dose, at which visits = Complete dispensing matrix",
            automation_enabled="IRT auto-dispense based on visit and arm assignment",
        ),
    ],

    validation_rules=[
        ValidationRule(
            rule_id="VAL_ARMS_001",
            name="Arm Allocation Total",
            agents_involved=["arms_design"],
            validation_type="consistency",
            description="Verify arm allocations sum to 100%",
            check_logic="SUM(studyArms[].allocationPercentage) == 100",
            severity="error"
        ),
        ValidationRule(
            rule_id="VAL_ARMS_002",
            name="Dose Levels Consistency",
            agents_involved=["arms_design", "safety_decision_points"],
            validation_type="cross_reference",
            description="Verify dose modification levels in arms match safety decision points",
            check_logic="arms.doseModifications.levels SUBSET_OF safety.dose_modification_levels.levels",
            severity="error"
        ),
    ],

    system_configurations=[
        SystemConfiguration(
            system=DownstreamSystem.IRT,
            config_type="randomization_module",
            description="Complete IRT randomization configuration",
            data_sources=[
                "studyArms[].id",
                "studyArms[].name",
                "studyArms[].allocationPercentage",
                "designMetadata.stratificationFactors[]",
                "designMetadata.randomizationRatio"
            ],
            output_format="IRT vendor import (Medidata RTSM, Oracle Siebel CTMS, Parexel ClinPhone)",
            example_config={
                "study_arms": [
                    {"code": "A", "name": "Drug A + Chemo", "ratio": 2},
                    {"code": "B", "name": "Placebo + Chemo", "ratio": 1}
                ],
                "stratification_factors": [
                    {"name": "ECOG Status", "levels": ["0-1", "2"]},
                    {"name": "Prior Therapy", "levels": ["Yes", "No"]}
                ],
                "block_size": [3, 6],
                "randomization_method": "permuted_block"
            }
        ),
    ],
)


ENDPOINTS_ESTIMANDS_SAP_DOC = AgentDocumentation(
    agent_id="endpoints_estimands_sap",
    display_name="Endpoints, Estimands & SAP",
    instance_type="EndpointsEstimandsSAP",
    wave=1,
    priority=0,

    purpose="""
    Extracts study objectives, endpoints, estimands (per ICH E9 R1), analysis populations,
    and statistical analysis specifications. This is the definitive source for programming
    analysis datasets and statistical outputs.
    """,

    scope="""
    - Primary, secondary, and exploratory objectives
    - Endpoint definitions with outcome types and assessment methods
    - ICH E9(R1) compliant estimands with intercurrent event strategies
    - Analysis populations (ITT, mITT, PP, Safety)
    - Sensitivity and subgroup analyses
    - Multiplicity adjustment strategy
    - Missing data handling
    """,

    key_sections_analyzed=[
        "Section 2: Study Objectives and Endpoints",
        "Section 3: Study Objectives",
        "Section 8: Statistical Considerations",
        "Section 9: Statistical Analysis Plan",
        "Appendix: Statistical Analysis Plan (if separate)",
    ],

    key_insights=[
        AgentInsight(
            name="Primary Endpoints",
            description="Primary efficacy endpoints with outcome type, timepoints, and assessment method",
            data_path="protocol_endpoints.endpoints[?(@.level.decode=='Primary')]",
            downstream_uses=["Primary analysis programming", "Sample size validation", "DSMB reporting"],
            automation_category=AutomationCategory.DATA_STANDARDS,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="ADAM_EP_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.REGULATORY,
                    description="Generate ADaM ADEFF specification from primary endpoint",
                    source_data_path="protocol_endpoints.endpoints[?(@.level.decode=='Primary')]",
                    rule_logic="""
                    FOR EACH primary_endpoint:
                        CREATE adam_spec {
                            dataset: 'ADEFF' or 'ADTTE',
                            paramcd: DERIVE_PARAMCD(endpoint.name),
                            param: endpoint.text,
                            dtype: endpoint.outcome_type.decode,
                            avisit: endpoint.primary_timepoint_text
                        }
                    """,
                ),
            ]
        ),
        AgentInsight(
            name="Estimands",
            description="ICH E9(R1) estimands with treatment comparison, population, variable, ICE strategies",
            data_path="protocol_endpoints.estimands[]",
            downstream_uses=["Analysis programming specifications", "SAP finalization", "Regulatory submission narrative"],
            automation_category=AutomationCategory.DATA_STANDARDS,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="SAP_EST_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.REGULATORY,
                    description="Generate SAP estimand section from extracted estimands",
                    source_data_path="protocol_endpoints.estimands[]",
                    rule_logic="""
                    FOR EACH estimand:
                        GENERATE estimand_table {
                            population: estimand.population.description,
                            treatment: estimand.treatment,
                            variable: estimand.variable.description,
                            intercurrent_events: estimand.intercurrent_events[],
                            summary_measure: estimand.summary_measure.decode
                        }
                    """,
                ),
            ]
        ),
        AgentInsight(
            name="Analysis Populations",
            description="ITT, mITT, PP, Safety population definitions with inclusion/exclusion criteria",
            data_path="protocol_endpoints.analysis_populations[]",
            downstream_uses=["ADSL derivation", "Population flag programming", "CSR population tables"],
            automation_category=AutomationCategory.DATA_STANDARDS,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="ADAM_POP_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.REGULATORY,
                    description="Generate ADSL population flags from definitions",
                    source_data_path="protocol_endpoints.analysis_populations[]",
                    rule_logic="""
                    FOR EACH population:
                        CREATE adsl_flag {
                            flag_name: population.label + 'FL',
                            definition: population.text,
                            inclusion_criteria: population.inclusion_criteria,
                            exclusion_criteria: population.exclusion_criteria
                        }
                    """,
                    example="ITTFL = 'Y' if randomized and received ≥1 dose"
                ),
            ]
        ),
        AgentInsight(
            name="Statistical Methods",
            description="Model specifications, covariates, multiplicity adjustment",
            data_path="sap_analyses.statistical_methods[]",
            downstream_uses=["Analysis program templates", "Validation programming", "TLF shells"],
            automation_category=AutomationCategory.DATA_STANDARDS,
            priority="high"
        ),
        AgentInsight(
            name="Subgroup Analyses",
            description="Pre-specified subgroup definitions and analysis methods",
            data_path="sap_analyses.subgroup_analyses[]",
            downstream_uses=["Forest plot programming", "Subgroup TLF generation", "Regulatory response preparation"],
            automation_category=AutomationCategory.DATA_STANDARDS,
            priority="medium"
        ),
    ],

    downstream_systems=[
        DownstreamSystem.EDC,
        DownstreamSystem.REGULATORY,
    ],

    automation_use_cases=[
        "Generate CDISC ADaM dataset specifications from estimands",
        "Auto-create TLF shells from endpoint definitions",
        "Pre-configure statistical analysis programs",
        "Generate SAP templates with population definitions",
        "Create endpoint assessment CRFs in EDC",
        "Configure DSMB reporting data cuts",
    ],

    depends_on=["study_metadata"],
    enriches=["pro_specifications", "imaging_central_reading"],
    cross_references=["adverse_events", "quality_management"],

    cdisc_domains=["ADSL", "ADEFF", "ADTTE"],
    regulatory_relevance="ICH E9(R1), ICH M11 Sections 2-3, CTD Module 2.7.3/2.7.6",
    schema_file="endpoints_estimands_sap_schema.json",
    typical_extraction_time_seconds=75,

    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_EP_SOA_001",
            name="Endpoints + SOA → Assessment Schedule Validation",
            agents_involved=["endpoints_estimands_sap", "soa_schedule"],
            description="Endpoint timepoints matched to SOA visits ensures all assessments are scheduled",
            combined_insight="Primary endpoint at Week 12 + SOA Week 12 visit with efficacy assessment = Validated schedule",
            automation_enabled="Auto-verify SOA includes all required endpoint assessments",
        ),
        CrossAgentSynergy(
            synergy_id="SYN_EP_AE_001",
            name="Endpoints + AEs + Withdrawal → Complete Estimand Definition",
            agents_involved=["endpoints_estimands_sap", "adverse_events", "withdrawal_procedures"],
            description="Combining endpoint definitions with AE handling and withdrawal reasons enables complete ICE specification",
            combined_insight="What happens to endpoint when subject discontinues due to AE = Complete intercurrent event strategy",
            automation_enabled="Generate regulatory-ready estimand framework documentation",
        ),
    ],

    validation_rules=[
        ValidationRule(
            rule_id="VAL_EP_001",
            name="Endpoint-Objective Linkage",
            agents_involved=["endpoints_estimands_sap"],
            validation_type="completeness",
            description="Every endpoint must link to at least one objective",
            check_logic="FOR EACH endpoint: EXISTS objective WHERE endpoint.id IN objective.endpoint_ids",
            severity="error"
        ),
    ],
)


ADVERSE_EVENTS_DOC = AgentDocumentation(
    agent_id="adverse_events",
    display_name="Adverse Events",
    instance_type="AdverseEvents",
    wave=1,
    priority=0,

    purpose="""
    Extracts comprehensive adverse event management specifications including AE/SAE definitions,
    grading systems, causality assessment, reporting timelines, and AESI lists. Critical for
    safety database configuration and pharmacovigilance workflows.
    """,

    scope="""
    - AE and TEAE definitions
    - SAE criteria per ICH E2A
    - CTCAE grading system version and definitions
    - Causality assessment methodology
    - MedDRA coding specifications
    - Reporting timelines (routine AE, SAE, SUSAR, pregnancy)
    - AESI list with special monitoring requirements
    - DLT criteria (oncology protocols)
    - Safety committees (DSMB, SMC)
    """,

    key_sections_analyzed=[
        "Section 7: Safety Reporting",
        "Section 8: Adverse Events",
        "Section 9: Safety Assessments",
        "Appendix: CTCAE Grading Tables",
        "Appendix: AESI Definitions",
    ],

    key_insights=[
        AgentInsight(
            name="AE Collection Period",
            description="When AE collection starts and ends relative to study drug",
            data_path="ae_definitions.collection_start, ae_definitions.collection_end",
            downstream_uses=["EDC AE form display logic", "Safety database query rules", "Site training"],
            automation_category=AutomationCategory.FORM_DESIGN,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_AE_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Validate AE dates within collection period",
                    source_data_path="ae_definitions",
                    rule_logic="""
                    IF ae.start_date < first_dose_date THEN SET ae.treatment_emergent = 'N'
                    IF ae.start_date > last_dose_date + followup_days THEN RAISE 'AE outside collection window'
                    """,
                    example="AE start date must be >= first dose date for TEAE flag"
                ),
            ]
        ),
        AgentInsight(
            name="SAE Criteria",
            description="ICH E2A serious criteria with protocol-specific exceptions",
            data_path="sae_criteria.criteria[]",
            downstream_uses=["Safety database serious flag logic", "EDC serious field validation", "Expedited reporting triggers"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="SAFETY_SAE_001",
                    rule_type="alert",
                    target_system=DownstreamSystem.SAFETY_DB,
                    description="Configure SAE detection and expedited reporting workflow",
                    source_data_path="sae_criteria.criteria[]",
                    rule_logic="""
                    IF any(sae_criteria) THEN:
                        SET serious_flag = 'Y'
                        SET report_due_hours = sae_criteria.initial_report_hours
                        TRIGGER expedited_workflow
                        NOTIFY medical_monitor, sponsor_safety
                    """,
                    example="Death → 24hr initial report, 7-day follow-up"
                ),
                AutomationRule(
                    rule_id="EDC_SAE_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Enforce SAE documentation requirements",
                    source_data_path="sae_criteria",
                    rule_logic="""
                    IF serious = 'Y' THEN REQUIRE (
                        seriousness_criteria IS NOT NULL,
                        onset_date IS NOT NULL,
                        outcome IS NOT NULL,
                        causality IS NOT NULL
                    )
                    """,
                ),
            ]
        ),
        AgentInsight(
            name="Reporting Timelines",
            description="Hours/days for initial SAE report, follow-up, SUSAR",
            data_path="reporting_procedures",
            downstream_uses=["Safety database workflow rules", "Site alert configuration", "PV team SLAs"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="SAFETY_TIMELINE_001",
                    rule_type="workflow",
                    target_system=DownstreamSystem.SAFETY_DB,
                    description="Configure safety reporting timeline workflows",
                    source_data_path="reporting_procedures",
                    rule_logic="""
                    CREATE workflow_rules:
                        - SAE initial: due_hours = reporting_procedures.sae_initial_hours
                        - SAE followup: due_days = reporting_procedures.sae_followup_days
                        - SUSAR: due_days = 15 (unexpected), 7 (fatal/life-threatening)
                    SET escalation_path = [site, medical_monitor, sponsor_safety, regulatory]
                    """,
                ),
            ]
        ),
        AgentInsight(
            name="AESI List",
            description="Adverse events of special interest with monitoring requirements",
            data_path="aesi_list[]",
            downstream_uses=["Safety database AESI flags", "EDC AESI prompts", "Medical monitor alerts"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="high",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_AESI_001",
                    rule_type="alert",
                    target_system=DownstreamSystem.EDC,
                    description="Prompt for AESI-specific data collection",
                    source_data_path="aesi_list[]",
                    rule_logic="""
                    FOR EACH aesi:
                        IF ae.meddra_pt IN aesi.matching_terms THEN:
                            DISPLAY aesi.additional_questions
                            SET aesi_flag = 'Y'
                            IF aesi.immediate_notification THEN NOTIFY medical_monitor
                    """,
                    example="Hepatotoxicity → Prompt for Hy's Law labs, trigger medical monitor alert"
                ),
            ]
        ),
        AgentInsight(
            name="DLT Criteria",
            description="Dose-limiting toxicity definitions, observation period, MTD rules",
            data_path="dlt_criteria",
            downstream_uses=["Dose escalation committee dashboards", "IRT dose assignment rules", "Safety stopping rules"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="high",
            automation_rules=[
                AutomationRule(
                    rule_id="IRT_DLT_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.IRT,
                    description="Configure DLT-based dose escalation rules",
                    source_data_path="dlt_criteria",
                    rule_logic="""
                    SET dlt_window_days = dlt_criteria.observation_period_days
                    SET escalation_rules = {
                        '0 DLTs in 3': 'ESCALATE',
                        '1 DLT in 3': 'EXPAND to 6',
                        '1 DLT in 6': 'ESCALATE',
                        '>=2 DLTs in 6': 'MTD exceeded, DE-ESCALATE'
                    }
                    """,
                    example="3+3 design with 28-day DLT window"
                ),
            ]
        ),
    ],

    downstream_systems=[
        DownstreamSystem.SAFETY_DB,
        DownstreamSystem.EDC,
        DownstreamSystem.CTMS,
    ],

    automation_use_cases=[
        "Configure safety database with protocol-specific SAE criteria",
        "Set up expedited reporting workflows and timelines",
        "Create EDC AE/SAE CRFs with proper grading dropdowns",
        "Configure AESI flag logic in safety database",
        "Generate site training materials on AE reporting",
        "Set up DLT tracking dashboards for dose escalation",
    ],

    depends_on=["study_metadata"],
    enriches=["quality_management", "withdrawal_procedures"],
    cross_references=["safety_decision_points", "concomitant_medications"],

    cdisc_domains=["AE", "MH", "FA"],
    regulatory_relevance="ICH E2A, ICH E6(R2), ICH M11 Section 8",
    schema_file="adverse_events_extraction_schema.json",
    typical_extraction_time_seconds=60,

    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_AE_SAFETY_001",
            name="AE Grading + Safety Thresholds → Automated Dose Decisions",
            agents_involved=["adverse_events", "safety_decision_points"],
            description="CTCAE grades combined with safety thresholds enable automated dose recommendations",
            combined_insight="Grade 3 neutropenia + safety rules = Hold dose, check ANC in 1 week",
            automation_enabled="EDC displays recommended action when AE grade is entered",
            example_output='{"ae": "Neutropenia Grade 3", "action": "Hold dose", "recheck": "7 days", "resume_criteria": "ANC >= 1500"}'
        ),
        CrossAgentSynergy(
            synergy_id="SYN_AE_CM_001",
            name="AE + Concomitant Meds → Drug Interaction Alerts",
            agents_involved=["adverse_events", "concomitant_medications"],
            description="AE patterns combined with prohibited medications enables interaction detection",
            combined_insight="QT prolongation AE + QT-prolonging concomitant med = Potential drug interaction",
            automation_enabled="Real-time drug interaction alert when entering concomitant medications",
        ),
    ],

    validation_rules=[
        ValidationRule(
            rule_id="VAL_AE_001",
            name="CTCAE Version Consistency",
            agents_involved=["adverse_events"],
            validation_type="consistency",
            description="Verify CTCAE version is specified and consistent throughout",
            check_logic="ctcae_version IS NOT NULL AND ctcae_version == data_standards.ctcae_version",
            severity="error"
        ),
        ValidationRule(
            rule_id="VAL_AE_002",
            name="AESI-SAE Overlap",
            agents_involved=["adverse_events"],
            validation_type="completeness",
            description="Check if AESIs have SAE reporting guidance",
            check_logic="FOR EACH aesi: EXISTS sae_guidance OR aesi.always_serious == true",
            severity="warning"
        ),
    ],

    system_configurations=[
        SystemConfiguration(
            system=DownstreamSystem.SAFETY_DB,
            config_type="protocol_profile",
            description="Safety database protocol-specific configuration",
            data_sources=[
                "sae_criteria.criteria[]",
                "reporting_procedures",
                "aesi_list[]",
                "dlt_criteria"
            ],
            output_format="Safety database import (Argus, ARISg, Oracle Empirica)",
            example_config={
                "sae_criteria": [
                    {"criterion": "Death", "code": "C48275", "timeline_hours": 24},
                    {"criterion": "Life-threatening", "code": "C84266", "timeline_hours": 24},
                    {"criterion": "Hospitalization", "code": "C84268", "timeline_hours": 72}
                ],
                "aesi_list": [
                    {"term": "Hepatotoxicity", "meddra_codes": ["10019670"], "enhanced_collection": True}
                ],
                "meddra_version": "26.0",
                "ctcae_version": "5.0"
            }
        ),
    ],
)


SAFETY_DECISION_POINTS_DOC = AgentDocumentation(
    agent_id="safety_decision_points",
    display_name="Safety Decision Points",
    instance_type="SafetyDecisionPoints",
    wave=1,
    priority=0,

    purpose="""
    Extracts actionable safety decision rules including dose modification triggers,
    study stopping rules, and organ-specific adjustments. These translate directly
    into EDC edit checks and medical monitor alert configurations.
    """,

    scope="""
    - Safety parameter categories discovered in protocol
    - Decision points with conditions and actions
    - Dose modification levels (reduction percentages, absolute doses)
    - Re-escalation criteria
    - Study stopping rules (individual and aggregate)
    - Organ-specific dose adjustments (hepatic, renal, cardiac)
    - Recovery/rechallenge criteria
    """,

    key_sections_analyzed=[
        "Section 6: Dose Modifications",
        "Section 7: Dose Reductions",
        "Section 8: Study Drug Discontinuation",
        "Section 9: Stopping Rules",
        "Appendix: Dose Modification Tables",
    ],

    key_insights=[
        AgentInsight(
            name="Dose Reduction Levels",
            description="Defined dose levels (-1, -2, etc.) with absolute or percentage reductions",
            data_path="dose_modification_levels.levels[]",
            downstream_uses=["IRT dose assignment options", "EDC dose level dropdown", "Drug accountability forms"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="IRT_DOSELEVEL_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.IRT,
                    description="Configure allowed dose levels in IRT",
                    source_data_path="dose_modification_levels.levels[]",
                    rule_logic="""
                    FOR EACH level IN dose_modification_levels.levels:
                        CREATE irt_dose_option {
                            level_id: level.level_name,
                            dose_value: level.absolute_dose OR (starting_dose * level.percentage/100),
                            kit_assignment: DERIVE_KIT(dose_value)
                        }
                    SET allowed_transitions = DEFINE_REDUCTION_PATH(levels)
                    """,
                    example="Level -1 = 300mg, Level -2 = 200mg, discontinue if further reduction needed"
                ),
            ]
        ),
        AgentInsight(
            name="Decision Rules",
            description="If-then rules mapping safety findings to required actions",
            data_path="decision_points[].decision_rules[]",
            downstream_uses=["EDC edit checks", "Medical monitor alerts", "Safety dashboard rules"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_DECISION_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Generate edit checks from decision rules",
                    source_data_path="decision_points[].decision_rules[]",
                    rule_logic="""
                    FOR EACH rule IN decision_rules:
                        CREATE edit_check {
                            trigger: PARSE_CONDITION(rule.condition),
                            action: rule.action,
                            message: 'Protocol requires: ' + rule.action + ' when ' + rule.condition,
                            severity: IF rule.action CONTAINS 'discontinue' THEN 'hard' ELSE 'soft'
                        }
                    """,
                    example="IF ALT > 5x ULN THEN 'Hold study drug, notify medical monitor'"
                ),
                AutomationRule(
                    rule_id="ALERT_DECISION_001",
                    rule_type="alert",
                    target_system=DownstreamSystem.EDC,
                    description="Configure real-time safety alerts from decision rules",
                    source_data_path="decision_points[].decision_rules[]",
                    rule_logic="""
                    FOR EACH rule WHERE rule.notify IS NOT NULL:
                        CREATE alert {
                            condition: rule.condition,
                            recipients: rule.notify,
                            urgency: DERIVE_URGENCY(rule.action),
                            include_data: [rule.parameter, subject_id, site_id]
                        }
                    """,
                ),
            ]
        ),
        AgentInsight(
            name="Stopping Rules",
            description="Individual and study-level stopping conditions",
            data_path="stopping_rules_summary.stopping_conditions[]",
            downstream_uses=["DSMB monitoring triggers", "Sponsor alert rules", "IRT enrollment stops"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="IRT_STOP_001",
                    rule_type="workflow",
                    target_system=DownstreamSystem.IRT,
                    description="Configure enrollment stops based on stopping rules",
                    source_data_path="stopping_rules_summary.stopping_conditions[]",
                    rule_logic="""
                    FOR EACH stop_rule WHERE stop_rule.scope == 'study':
                        CREATE enrollment_hold_trigger {
                            condition: stop_rule.condition,
                            action: 'PAUSE_ENROLLMENT',
                            notify: ['sponsor', 'dsmb', 'irb'],
                            resume_requires: 'sponsor_authorization'
                        }
                    """,
                ),
            ]
        ),
        AgentInsight(
            name="Organ-Specific Adjustments",
            description="Hepatic, renal, cardiac, hematologic dose adjustments",
            data_path="organ_specific_adjustments[]",
            downstream_uses=["Lab-triggered alerts", "Dose recommendation logic", "Site guidance documents"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="high",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_ORGAN_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.EDC,
                    description="Generate lab-triggered dose recommendations",
                    source_data_path="organ_specific_adjustments[]",
                    rule_logic="""
                    FOR EACH adjustment:
                        CREATE lab_alert {
                            lab_test: adjustment.lab_parameter,
                            thresholds: adjustment.thresholds,
                            actions: adjustment.actions,
                            display_message: FORMAT_RECOMMENDATION(adjustment)
                        }
                    """,
                    example="CrCl 30-50 mL/min → Reduce to 75% of dose"
                ),
            ]
        ),
    ],

    downstream_systems=[
        DownstreamSystem.EDC,
        DownstreamSystem.IRT,
        DownstreamSystem.SAFETY_DB,
    ],

    automation_use_cases=[
        "Generate EDC edit checks for dose modification triggers",
        "Configure IRT dose assignment validation rules",
        "Set up medical monitor safety alert thresholds",
        "Create dose modification decision trees for site training",
        "Configure DSMB stopping rule monitoring",
        "Generate lab-triggered safety alerts",
    ],

    depends_on=["study_metadata"],
    enriches=["quality_management"],
    cross_references=["adverse_events", "laboratory_specifications", "arms_design"],

    cdisc_domains=["DS", "EX", "LB"],
    regulatory_relevance="ICH E6(R2), ICH M11 Section 6-7",
    schema_file="safety_decision_points_schema.json",
    typical_extraction_time_seconds=50,

    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_SAFETY_LAB_001",
            name="Safety Thresholds + Lab Specs → Smart Lab Alerts",
            agents_involved=["safety_decision_points", "laboratory_specifications"],
            description="Combining safety thresholds with lab panel definitions enables intelligent lab alerting",
            combined_insight="Which labs to monitor + what thresholds trigger action = Complete lab safety system",
            automation_enabled="EDC auto-calculates if labs trigger dose modification upon data entry",
            example_output='{"lab": "ANC", "value": 800, "threshold": "<1000", "action": "Hold dose", "triggered": true}'
        ),
        CrossAgentSynergy(
            synergy_id="SYN_SAFETY_ARMS_001",
            name="Safety Rules + Arms → Arm-Specific Modifications",
            agents_involved=["safety_decision_points", "arms_design"],
            description="Safety rules applied to specific arm dosing enables precise modification tracking",
            combined_insight="Which dose level applies to which arm = Accurate dose tracking per subject",
            automation_enabled="IRT knows exact dose options for each arm based on safety rules",
        ),
    ],

    validation_rules=[
        ValidationRule(
            rule_id="VAL_SAFETY_001",
            name="Dose Level Consistency",
            agents_involved=["safety_decision_points", "arms_design"],
            validation_type="cross_reference",
            description="Verify dose modification levels align with arm dosing regimens",
            check_logic="FOR EACH level: level.absolute_dose IN arms.interventions.possible_doses",
            severity="error"
        ),
        ValidationRule(
            rule_id="VAL_SAFETY_002",
            name="Stopping Rule Completeness",
            agents_involved=["safety_decision_points"],
            validation_type="completeness",
            description="Verify all stopping rules have clear conditions and actions",
            check_logic="FOR EACH stop_rule: condition IS NOT NULL AND action IS NOT NULL",
            severity="error"
        ),
    ],

    system_configurations=[
        SystemConfiguration(
            system=DownstreamSystem.EDC,
            config_type="edit_check_library",
            description="Complete set of safety-related edit checks",
            data_sources=[
                "decision_points[].decision_rules[]",
                "dose_modification_levels.levels[]",
                "organ_specific_adjustments[]"
            ],
            output_format="EDC edit check specification (Medidata, Oracle, Veeva)",
            example_config={
                "edit_checks": [
                    {
                        "id": "EC_ALT_001",
                        "condition": "ALT > 5 * ULN",
                        "action": "FIRE",
                        "message": "ALT elevation requires dose hold per protocol section 6.2",
                        "severity": "HARD_STOP"
                    },
                    {
                        "id": "EC_ANC_001",
                        "condition": "ANC < 1000",
                        "action": "FIRE",
                        "message": "Neutropenia requires dose modification per Table 6-1",
                        "severity": "SOFT_STOP"
                    }
                ]
            }
        ),
    ],
)


# =============================================================================
# WAVE 1: CORE MODULES (P1 - HIGH PRIORITY)
# =============================================================================

CONCOMITANT_MEDICATIONS_DOC = AgentDocumentation(
    agent_id="concomitant_medications",
    display_name="Concomitant Medications",
    instance_type="ConcomitantMedicationRestrictions",
    wave=1,
    priority=1,

    purpose="""
    Extracts medication restrictions, drug interactions, washout requirements, and required
    premedications. Essential for site guidance, eligibility verification, and drug
    interaction checking in EDC.
    """,

    scope="""
    - Prohibited medications (with reasons and periods)
    - Restricted medications (with conditions for use)
    - Required premedications and prophylaxis
    - Rescue medications
    - Washout requirements
    - Drug-drug interactions (CYP450, QT, etc.)
    - Vaccine policy
    - Herbal/supplement restrictions
    """,

    key_sections_analyzed=[
        "Section 5: Prohibited/Restricted Medications",
        "Section 6: Concomitant Medications",
        "Section 7: Prior Medications",
        "Appendix: Drug Interaction Tables",
    ],

    key_insights=[
        AgentInsight(
            name="Prohibited Medications",
            description="Completely banned drug classes with prohibition reasons and periods",
            data_path="prohibited_medications[]",
            downstream_uses=["EDC CM edit checks", "Site reference cards", "Eligibility screening"],
            automation_category=AutomationCategory.ELIGIBILITY,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_PROHIB_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Alert when prohibited medication is entered",
                    source_data_path="prohibited_medications[]",
                    rule_logic="""
                    FOR EACH cm_entry:
                        IF cm_entry.drug_class IN prohibited_medications[].medication_class THEN:
                            IF cm_entry.dates OVERLAP study_period THEN
                                RAISE 'Prohibited medication during study period'
                            SET protocol_deviation = TRUE
                    """,
                    example="Strong CYP3A4 inhibitor during treatment → Protocol deviation query"
                ),
            ]
        ),
        AgentInsight(
            name="Washout Requirements",
            description="Required washout periods before study entry",
            data_path="washout_requirements[]",
            downstream_uses=["Eligibility calculator", "Screening visit scheduling", "EDC eligibility forms"],
            automation_category=AutomationCategory.ELIGIBILITY,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_WASHOUT_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Validate washout period for prior medications",
                    source_data_path="washout_requirements[]",
                    rule_logic="""
                    FOR EACH prior_med:
                        washout = LOOKUP(prior_med.drug_class, washout_requirements)
                        IF prior_med.end_date + washout.duration_days > first_dose_date THEN
                            RAISE 'Insufficient washout period for ' + prior_med.drug_class
                    """,
                    example="Prior chemotherapy end date + 28 days must be before first dose"
                ),
            ]
        ),
        AgentInsight(
            name="Drug Interactions",
            description="CYP450 inhibitors/inducers, QT prolonging agents with management",
            data_path="drug_interactions[]",
            downstream_uses=["EDC drug interaction alerts", "Medical monitor reviews", "Pharmacy guidance"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="high",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_DDI_001",
                    rule_type="alert",
                    target_system=DownstreamSystem.EDC,
                    description="Real-time drug interaction checking",
                    source_data_path="drug_interactions[]",
                    rule_logic="""
                    FOR EACH new_cm:
                        interactions = MATCH(new_cm, drug_interactions[].affected_drugs)
                        IF interactions.length > 0 THEN:
                            DISPLAY interaction_warning(interactions)
                            IF interaction.severity == 'strong' THEN NOTIFY medical_monitor
                    """,
                ),
            ]
        ),
        AgentInsight(
            name="Required Premedications",
            description="Mandatory premedications with dosing and timing",
            data_path="required_medications[]",
            downstream_uses=["Treatment day CRFs", "Site procedures", "Drug supply planning"],
            automation_category=AutomationCategory.FORM_DESIGN,
            priority="high",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_PREMED_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Verify required premedications were administered",
                    source_data_path="required_medications[]",
                    rule_logic="""
                    FOR EACH treatment_visit:
                        required_premeds = FILTER(required_medications, type='premedication')
                        FOR EACH premed IN required_premeds:
                            IF NOT premed_administered(premed) THEN
                                RAISE 'Required premedication not documented: ' + premed.name
                    """,
                    example="Diphenhydramine 50mg IV required 30 min before infusion"
                ),
            ]
        ),
    ],

    downstream_systems=[
        DownstreamSystem.EDC,
        DownstreamSystem.SAFETY_DB,
    ],

    automation_use_cases=[
        "Configure EDC concomitant medication edit checks",
        "Generate site reference cards for prohibited/restricted meds",
        "Create eligibility screening tools with washout calculators",
        "Set up drug interaction alerts in safety database",
        "Auto-populate premedication requirements in visit forms",
    ],

    depends_on=["study_metadata"],
    enriches=["eligibility_criteria"],
    cross_references=["adverse_events", "arms_design"],

    cdisc_domains=["CM"],
    regulatory_relevance="ICH M11 Section 6.6",
    schema_file="concomitant_medications_schema.json",
    typical_extraction_time_seconds=45,

    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_CM_ELIG_001",
            name="Washouts + Eligibility → Complete Screening Tool",
            agents_involved=["concomitant_medications", "eligibility_criteria"],
            description="Washout requirements combined with eligibility criteria enables smart screening",
            combined_insight="Prior therapy exclusions + washout periods = Earliest eligible date calculator",
            automation_enabled="Site tool that calculates when patient becomes eligible based on prior meds",
            example_output='{"prior_med": "Irinotecan", "last_dose": "2024-01-15", "washout": "28 days", "earliest_eligible": "2024-02-12"}'
        ),
    ],

    system_configurations=[
        SystemConfiguration(
            system=DownstreamSystem.EDC,
            config_type="drug_dictionary_config",
            description="Configure drug dictionary with protocol-specific flags",
            data_sources=[
                "prohibited_medications[]",
                "restricted_medications[]",
                "drug_interactions[]"
            ],
            output_format="WHODrug/MedDRA mapping with protocol flags",
            example_config={
                "drug_flags": [
                    {"atc_class": "L01", "flag": "PRIOR_CHEMO", "washout_days": 28},
                    {"drug_name": "Ketoconazole", "flag": "CYP3A4_INHIBITOR", "status": "PROHIBITED"}
                ]
            }
        ),
    ],
)


# Abbreviated definitions for remaining agents (keeping structure but condensing for brevity)

BIOSPECIMEN_HANDLING_DOC = AgentDocumentation(
    agent_id="biospecimen_handling",
    display_name="Biospecimen Handling",
    instance_type="BiospecimenHandling",
    wave=1,
    priority=1,
    purpose="Extracts specimen collection, processing, storage, and shipping requirements for central lab and biobank setup.",
    scope="Specimen types, tube types/volumes, processing instructions, storage conditions, shipping requirements, biobanking.",
    key_sections_analyzed=["Section 7: Laboratory Assessments", "Section 8: Specimen Collection", "Appendix: Laboratory Manual"],
    key_insights=[
        AgentInsight(
            name="Specimen Collection Requirements",
            description="Tubes, volumes, special handling for each sample type",
            data_path="specimens[]",
            downstream_uses=["Central lab kit configuration", "Site lab manual", "Supply ordering"],
            automation_category=AutomationCategory.LAB_SETUP,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="LAB_KIT_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.CENTRAL_LAB,
                    description="Generate lab kit contents from specimen requirements",
                    source_data_path="specimens[]",
                    rule_logic="FOR EACH specimen: ADD tube(specimen.tube_type, specimen.volume) TO visit_kit",
                ),
            ]
        ),
    ],
    downstream_systems=[DownstreamSystem.CENTRAL_LAB, DownstreamSystem.BIOBANK, DownstreamSystem.EDC],
    automation_use_cases=["Generate central lab sample collection kits", "Configure biobank sample tracking", "Create site laboratory manuals"],
    depends_on=["study_metadata"],
    enriches=["laboratory_specifications"],
    cross_references=["pkpd_sampling"],
    cdisc_domains=["LB", "IS", "MB"],
    regulatory_relevance="ICH M11 Section 7.3",
    schema_file="biospecimen_handling_schema.json",
    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_BIO_SOA_001",
            name="Specimens + SOA → Visit-Based Lab Kits",
            agents_involved=["biospecimen_handling", "soa_schedule"],
            description="Specimen requirements + visit schedule = visit-specific lab kit configurations",
            combined_insight="What samples at which visits = Complete lab kit manifest per visit",
            automation_enabled="Central lab auto-generates visit-specific kit labels",
        ),
    ],
)


LABORATORY_SPECIFICATIONS_DOC = AgentDocumentation(
    agent_id="laboratory_specifications",
    display_name="Laboratory Specifications",
    instance_type="LaboratorySpecifications",
    wave=1,
    priority=1,
    purpose="Extracts laboratory panel definitions, eligibility criteria, and lab-triggered dose modifications for central lab and EDC setup.",
    scope="Lab panels, individual tests, eligibility lab criteria, lab-triggered dose modifications, hepatotoxicity monitoring.",
    key_sections_analyzed=["Section 7: Laboratory Assessments", "Section 5: Eligibility Criteria", "Section 6: Dose Modifications"],
    key_insights=[
        AgentInsight(
            name="Laboratory Panels",
            description="Panel definitions with constituent tests",
            data_path="panels[]",
            downstream_uses=["Central lab requisition forms", "EDC lab CRF design", "Cost estimation"],
            automation_category=AutomationCategory.LAB_SETUP,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="LAB_PANEL_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.CENTRAL_LAB,
                    description="Generate central lab requisition from panel definitions",
                    source_data_path="panels[]",
                    rule_logic="FOR EACH panel: CREATE requisition_form WITH tests = panel.tests[]",
                ),
            ]
        ),
        AgentInsight(
            name="Eligibility Lab Criteria",
            description="Lab values required for study entry",
            data_path="eligibility_lab_criteria[]",
            downstream_uses=["EDC eligibility edit checks", "Site screening tools", "Subject ID verification"],
            automation_category=AutomationCategory.ELIGIBILITY,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_LABELIG_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Validate screening labs against eligibility criteria",
                    source_data_path="eligibility_lab_criteria[]",
                    rule_logic="""
                    FOR EACH criterion:
                        IF lab.value NOT IN criterion.range THEN
                            RAISE 'Lab value outside eligibility range'
                    """,
                    example="ANC >= 1500/µL required for eligibility"
                ),
            ]
        ),
    ],
    downstream_systems=[DownstreamSystem.CENTRAL_LAB, DownstreamSystem.EDC],
    automation_use_cases=["Configure central lab panel requisitions", "Set up EDC lab data entry", "Create eligibility screening lab checklists"],
    depends_on=["study_metadata"],
    enriches=["eligibility_criteria", "safety_decision_points"],
    cross_references=["biospecimen_handling"],
    cdisc_domains=["LB"],
    regulatory_relevance="ICH M11 Section 7.2",
    schema_file="laboratory_specifications_schema.json",
    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_LAB_SAFETY_001",
            name="Lab Panels + Safety Thresholds → Lab Alert System",
            agents_involved=["laboratory_specifications", "safety_decision_points"],
            description="Lab test definitions + safety thresholds = complete lab alerting system",
            combined_insight="Normal ranges + dose modification thresholds = Tiered lab alerts (normal, caution, action required)",
            automation_enabled="EDC displays color-coded lab values with action recommendations",
        ),
    ],
)


INFORMED_CONSENT_DOC = AgentDocumentation(
    agent_id="informed_consent",
    display_name="Informed Consent Elements",
    instance_type="InformedConsentElements",
    wave=1,
    priority=1,
    purpose="Extracts key informed consent content elements for ICF template generation and IRB submission.",
    scope="Key risks, potential benefits, treatment alternatives, compensation, genetic/biobanking consents, witness requirements.",
    key_sections_analyzed=["Section 10: Informed Consent", "Section 11: Subject Information", "Appendix: Informed Consent Form"],
    key_insights=[
        AgentInsight(name="Key Risks", description="Common, serious, and unknown risks to communicate", data_path="risks[]",
                    downstream_uses=["ICF template generation", "IRB submission", "Site training"],
                    automation_category=AutomationCategory.REGULATORY_DOCS, priority="critical"),
        AgentInsight(name="Optional Consents", description="Biobanking, genetic testing, future research options", data_path="optional_consents[]",
                    downstream_uses=["ICF optional sections", "EDC consent tracking", "Biobank enrollment"],
                    automation_category=AutomationCategory.FORM_DESIGN, priority="high"),
    ],
    downstream_systems=[DownstreamSystem.EDC, DownstreamSystem.TMF, DownstreamSystem.REGULATORY],
    automation_use_cases=["Generate ICF templates with protocol-specific risks", "Create consent tracking CRFs"],
    depends_on=["study_metadata"],
    enriches=[],
    cross_references=["adverse_events"],
    cdisc_domains=["DS"],
    regulatory_relevance="ICH E6(R2), 21 CFR 50",
    schema_file="informed_consent_schema.json",
)


PRO_SPECIFICATIONS_DOC = AgentDocumentation(
    agent_id="pro_specifications",
    display_name="PRO/eCOA Specifications",
    instance_type="PROSpecifications",
    wave=1,
    priority=1,
    purpose="Extracts patient-reported outcome specifications for ePRO/eCOA vendor configuration.",
    scope="PRO instruments, ePRO system config, ClinRO/ObsRO/PerfO instruments, daily diaries, compliance thresholds.",
    key_sections_analyzed=["Section 7: Efficacy Assessments", "Section 8: Patient-Reported Outcomes", "Schedule of Assessments"],
    key_insights=[
        AgentInsight(
            name="PRO Instruments",
            description="Questionnaires with administration mode, timing, scoring",
            data_path="pro_instruments[]",
            downstream_uses=["ePRO vendor setup", "Site training", "Compliance monitoring"],
            automation_category=AutomationCategory.FORM_DESIGN,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EPRO_CONFIG_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.EPRO,
                    description="Generate ePRO vendor configuration from PRO specifications",
                    source_data_path="pro_instruments[]",
                    rule_logic="""
                    FOR EACH instrument:
                        CREATE epro_config {
                            instrument_id: instrument.instrument_id,
                            schedule: MATCH(instrument.schedule, soa_schedule.visits),
                            recall_period: instrument.schedule.recall_period,
                            compliance_window: instrument.schedule.completion_window_hours
                        }
                    """,
                ),
            ]
        ),
    ],
    downstream_systems=[DownstreamSystem.EPRO, DownstreamSystem.ECOA, DownstreamSystem.EDC],
    automation_use_cases=["Configure ePRO/eCOA vendor systems", "Set up compliance monitoring and alerts"],
    depends_on=["study_metadata", "endpoints_estimands_sap"],
    enriches=[],
    cross_references=["endpoints_estimands_sap", "soa_schedule"],
    cdisc_domains=["QS", "RS"],
    regulatory_relevance="FDA PRO Guidance, ICH M11 Section 7.4",
    schema_file="pro_specifications_schema.json",
    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_PRO_SOA_001",
            name="PRO + SOA → Complete ePRO Schedule",
            agents_involved=["pro_specifications", "soa_schedule"],
            description="PRO instruments + visit timing = exact ePRO administration schedule",
            combined_insight="Which PRO at which visit with what window = Complete ePRO schedule",
            automation_enabled="ePRO system auto-schedules assessments based on subject visit dates",
        ),
    ],
)


DATA_MANAGEMENT_DOC = AgentDocumentation(
    agent_id="data_management",
    display_name="Data Management",
    instance_type="DataManagement",
    wave=1,
    priority=2,
    purpose="Extracts data management specifications for EDC setup and data management planning.",
    scope="EDC requirements, CDISC standards versions, data entry timelines, query management, database lock procedures.",
    key_sections_analyzed=["Section 10: Data Management", "Section 11: Quality Assurance", "Appendix: Data Management Plan"],
    key_insights=[
        AgentInsight(name="CDISC Standards", description="Required CDASH, SDTM, ADaM versions", data_path="cdisc_standards",
                    downstream_uses=["CRF standards library selection", "SDTM mapping", "ADaM specifications"],
                    automation_category=AutomationCategory.DATA_STANDARDS, priority="high"),
    ],
    downstream_systems=[DownstreamSystem.EDC, DownstreamSystem.CTMS],
    automation_use_cases=["Configure EDC data entry timelines", "Set up CDISC standards compliance checks"],
    depends_on=["study_metadata"],
    enriches=[],
    cross_references=["quality_management"],
    cdisc_domains=["All"],
    regulatory_relevance="ICH E6(R2), 21 CFR Part 11",
    schema_file="data_management_schema.json",
)


SITE_OPERATIONS_LOGISTICS_DOC = AgentDocumentation(
    agent_id="site_operations_logistics",
    display_name="Site Operations & Logistics",
    instance_type="SiteOperationsLogistics",
    wave=1,
    priority=2,
    purpose="Extracts site operational requirements for site initiation planning and CTMS configuration.",
    scope="Site equipment, training requirements, drug storage, IP accountability, vendor coordination.",
    key_sections_analyzed=["Section 9: Study Procedures", "Section 10: Drug Supply", "Appendix: Site Requirements"],
    key_insights=[
        AgentInsight(name="Equipment Requirements", description="Site equipment needs for assessments", data_path="equipment_requirements[]",
                    downstream_uses=["Site feasibility", "Site initiation checklist", "Budget planning"],
                    automation_category=AutomationCategory.SITE_TRAINING, priority="medium"),
    ],
    downstream_systems=[DownstreamSystem.CTMS, DownstreamSystem.TMF],
    automation_use_cases=["Generate site initiation checklists", "Configure LMS training assignments"],
    depends_on=["study_metadata"],
    enriches=[],
    cross_references=["arms_design", "biospecimen_handling"],
    cdisc_domains=["Not applicable"],
    regulatory_relevance="ICH E6(R2)",
    schema_file="site_operations_logistics_schema.json",
)


# =============================================================================
# WAVE 2: DEPENDENT MODULES
# =============================================================================

QUALITY_MANAGEMENT_DOC = AgentDocumentation(
    agent_id="quality_management",
    display_name="Quality Management",
    instance_type="QualityManagement",
    wave=2,
    priority=1,
    purpose="Extracts quality management specifications including RBQM, KRIs, and QTLs for CTMS monitoring configuration.",
    scope="Monitoring approach, RBQM, Key Risk Indicators, Quality Tolerance Limits, SDV extent, audit procedures.",
    key_sections_analyzed=["Section 10: Quality Management", "Section 11: Monitoring", "Appendix: Monitoring Plan"],
    key_insights=[
        AgentInsight(
            name="Key Risk Indicators",
            description="KRIs with thresholds and escalation procedures",
            data_path="kris[]",
            downstream_uses=["Central monitoring dashboards", "Site risk scores", "Escalation rules"],
            automation_category=AutomationCategory.SAFETY_RULES,
            priority="high",
            automation_rules=[
                AutomationRule(
                    rule_id="CTMS_KRI_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.CTMS,
                    description="Configure KRI monitoring thresholds",
                    source_data_path="kris[]",
                    rule_logic="""
                    FOR EACH kri:
                        CREATE dashboard_metric {
                            name: kri.name,
                            calculation: kri.formula,
                            thresholds: {yellow: kri.warning_threshold, red: kri.action_threshold},
                            escalation: kri.escalation_path
                        }
                    """,
                ),
            ]
        ),
    ],
    downstream_systems=[DownstreamSystem.CTMS, DownstreamSystem.EDC],
    automation_use_cases=["Configure CTMS monitoring schedules", "Set up KRI dashboards"],
    depends_on=["study_metadata", "adverse_events", "safety_decision_points"],
    enriches=[],
    cross_references=["data_management"],
    cdisc_domains=["Not applicable"],
    regulatory_relevance="ICH E6(R2) 5.0, ICH E8(R1)",
    schema_file="quality_management_schema.json",
    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_QM_ALL_001",
            name="All Agents → Complete RBQM Dashboard",
            agents_involved=["quality_management", "adverse_events", "safety_decision_points", "data_management"],
            description="KRI definitions + safety events + data quality = comprehensive central monitoring",
            combined_insight="Site-level risk scores based on all protocol-defined indicators",
            automation_enabled="Automated site risk scoring and monitoring prioritization",
        ),
    ],
)


WITHDRAWAL_PROCEDURES_DOC = AgentDocumentation(
    agent_id="withdrawal_procedures",
    display_name="Withdrawal Procedures",
    instance_type="WithdrawalProcedures",
    wave=2,
    priority=2,
    purpose="Extracts study discontinuation procedures for EDC disposition forms and protocol deviation tracking.",
    scope="Discontinuation types, consent withdrawal, early termination visits, survival follow-up, lost to follow-up.",
    key_sections_analyzed=["Section 5: Subject Withdrawal", "Section 6: Early Termination", "Section 9: Follow-up Procedures"],
    key_insights=[
        AgentInsight(name="Discontinuation Types", description="Treatment vs study discontinuation with criteria", data_path="discontinuation_types[]",
                    downstream_uses=["EDC disposition forms", "Analysis programming", "DSMB reporting"],
                    automation_category=AutomationCategory.FORM_DESIGN, priority="high"),
    ],
    downstream_systems=[DownstreamSystem.EDC, DownstreamSystem.CTMS],
    automation_use_cases=["Create EDC disposition forms", "Configure survival follow-up tracking"],
    depends_on=["study_metadata", "adverse_events"],
    enriches=[],
    cross_references=["adverse_events"],
    cdisc_domains=["DS"],
    regulatory_relevance="ICH E6(R2)",
    schema_file="withdrawal_procedures_schema.json",
)


IMAGING_CENTRAL_READING_DOC = AgentDocumentation(
    agent_id="imaging_central_reading",
    display_name="Imaging & Central Reading",
    instance_type="ImagingCentralReading",
    wave=2,
    priority=3,
    purpose="Extracts imaging specifications for oncology and imaging-endpoint studies.",
    scope="Response criteria (RECIST, RANO), imaging modalities, central vs local reading, adjudication procedures.",
    key_sections_analyzed=["Section 7: Tumor Assessments", "Section 8: Response Criteria", "Appendix: Imaging Charter"],
    key_insights=[
        AgentInsight(
            name="Response Criteria",
            description="RECIST/iRECIST/RANO version and modifications",
            data_path="response_criteria",
            downstream_uses=["Central imaging vendor setup", "Endpoint adjudication", "Analysis programming"],
            automation_category=AutomationCategory.DATA_STANDARDS,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="IMAGING_RESP_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.IMAGING,
                    description="Configure central imaging for response assessment",
                    source_data_path="response_criteria",
                    rule_logic="SET imaging_vendor.response_criteria = response_criteria.version; SET timepoints = response_criteria.assessment_schedule",
                ),
            ]
        ),
    ],
    downstream_systems=[DownstreamSystem.IMAGING, DownstreamSystem.EDC],
    automation_use_cases=["Configure central imaging vendor systems", "Set up response assessment workflows"],
    depends_on=["study_metadata"],
    enriches=[],
    cross_references=["endpoints_estimands_sap", "soa_schedule"],
    cdisc_domains=["TU", "TR", "RS"],
    regulatory_relevance="FDA Oncology Guidance, ICH M11 Section 7",
    schema_file="imaging_central_reading_schema.json",
    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_IMG_EP_001",
            name="Imaging + Endpoints → Response-Based Efficacy",
            agents_involved=["imaging_central_reading", "endpoints_estimands_sap"],
            description="Response criteria + primary endpoint = complete efficacy assessment workflow",
            combined_insight="RECIST definitions + ORR/PFS endpoints = Imaging-derived efficacy programming",
            automation_enabled="Central imaging outputs directly feed efficacy analysis datasets",
        ),
    ],
)


PKPD_SAMPLING_DOC = AgentDocumentation(
    agent_id="pkpd_sampling",
    display_name="PK/PD Sampling",
    instance_type="PKPDSampling",
    wave=2,
    priority=3,
    purpose="Extracts pharmacokinetic and pharmacodynamic sampling specifications for clinical pharmacology studies.",
    scope="PK sampling timepoints, PD biomarker sampling, bioanalytical methods, population PK specifications.",
    key_sections_analyzed=["Section 7: Pharmacokinetic Assessments", "Section 8: Pharmacodynamic Assessments", "Appendix: PK Sampling Schedule"],
    key_insights=[
        AgentInsight(name="PK Sampling Schedule", description="Intensive and sparse PK timepoints", data_path="pk_sampling.timepoints[]",
                    downstream_uses=["Site PK procedure guides", "Central lab setup", "Visit schedule"],
                    automation_category=AutomationCategory.LAB_SETUP, priority="high"),
    ],
    downstream_systems=[DownstreamSystem.CENTRAL_LAB, DownstreamSystem.EDC],
    automation_use_cases=["Configure bioanalytical lab sample requirements", "Create PK sampling procedure guides"],
    depends_on=["study_metadata"],
    enriches=[],
    cross_references=["biospecimen_handling", "arms_design", "soa_schedule"],
    cdisc_domains=["PC", "PP"],
    regulatory_relevance="FDA Clinical Pharmacology Guidance",
    schema_file="pkpd_sampling_schema.json",
)


# =============================================================================
# SPECIAL AGENTS (SOA & ELIGIBILITY)
# =============================================================================

SOA_SCHEDULE_DOC = AgentDocumentation(
    agent_id="soa_schedule",
    display_name="Schedule of Assessments",
    instance_type="ScheduleOfAssessments",
    wave=1,
    priority=0,

    purpose="""
    Extracts and interprets the Schedule of Assessments (SOA) table through a 12-stage
    pipeline. Produces the definitive visit schedule with activities, timing, and
    conditions for EDC form design and visit programming.
    """,

    scope="""
    - Visit definitions (screening, baseline, treatment, follow-up)
    - Activity-to-visit mapping
    - Visit windows and timing
    - Conditional activities
    - Cycle-based expansions
    - Footnote interpretation
    - CDISC domain categorization
    """,

    key_sections_analyzed=[
        "Schedule of Assessments table",
        "Section 9: Study Procedures",
        "Section 7: Assessments by Visit",
        "Footnotes to SOA table",
    ],

    key_insights=[
        AgentInsight(
            name="Visit Schedule",
            description="Complete visit definitions with timing and windows",
            data_path="visits[]",
            downstream_uses=["EDC visit design", "CTMS scheduling", "IRT visit tracking"],
            automation_category=AutomationCategory.VISIT_SCHEDULE,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_VISIT_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.EDC,
                    description="Generate EDC visit structure from SOA",
                    source_data_path="visits[]",
                    rule_logic="""
                    FOR EACH visit:
                        CREATE edc_visit {
                            visit_id: visit.id,
                            visit_name: visit.name,
                            target_day: visit.study_day,
                            window_before: visit.window_before,
                            window_after: visit.window_after,
                            epoch: visit.epoch
                        }
                    """,
                ),
            ]
        ),
        AgentInsight(
            name="Activity Matrix",
            description="Activities mapped to visits with conditions",
            data_path="activities[]",
            downstream_uses=["EDC form-to-visit mapping", "Site calendars", "Cost modeling"],
            automation_category=AutomationCategory.VISIT_SCHEDULE,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_FORMS_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.EDC,
                    description="Generate form-to-visit assignments from activity matrix",
                    source_data_path="activities[]",
                    rule_logic="""
                    FOR EACH activity:
                        form = MAP_TO_CRF(activity.name, activity.domain)
                        visits = activity.visit_assignments.filter(assigned=true)
                        CREATE form_assignment {form: form, visits: visits}
                    """,
                    example="Vital Signs → VS form assigned to all treatment visits"
                ),
            ]
        ),
        AgentInsight(
            name="Conditional Logic",
            description="Population/arm-specific activity requirements",
            data_path="conditional_activities[]",
            downstream_uses=["EDC conditional display logic", "Site procedures"],
            automation_category=AutomationCategory.FORM_DESIGN,
            priority="high",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_COND_001",
                    rule_type="derivation",
                    target_system=DownstreamSystem.EDC,
                    description="Generate conditional form display rules",
                    source_data_path="conditional_activities[]",
                    rule_logic="""
                    FOR EACH conditional:
                        CREATE display_condition {
                            form: conditional.activity,
                            condition: conditional.condition,
                            show_when: PARSE_CONDITION(conditional.condition)
                        }
                    """,
                    example="PK sampling only for Arm A subjects"
                ),
            ]
        ),
    ],

    downstream_systems=[
        DownstreamSystem.EDC,
        DownstreamSystem.CTMS,
        DownstreamSystem.IRT,
    ],

    automation_use_cases=[
        "Auto-generate EDC visit structure and form assignments",
        "Configure CTMS visit schedule and windows",
        "Create site-level visit calendars",
        "Generate study cost models based on assessments",
        "Configure IRT visit-based dispensing",
    ],

    depends_on=["study_metadata"],
    enriches=["pro_specifications", "laboratory_specifications", "pkpd_sampling"],
    cross_references=["arms_design", "biospecimen_handling"],

    cdisc_domains=["SV", "SE", "TV", "TA", "TE"],
    regulatory_relevance="ICH M11 Section 9",
    schema_file="soa_schedule_schema.json",
    typical_extraction_time_seconds=120,

    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_SOA_ALL_001",
            name="SOA + All Domain Agents → Complete Study Build",
            agents_involved=["soa_schedule", "arms_design", "laboratory_specifications", "pro_specifications", "biospecimen_handling"],
            description="SOA timing + all assessment details = complete study build specification",
            combined_insight="Visits + forms + labs + PROs + samples = One-click EDC build",
            automation_enabled="Generate complete EDC study specification from extracted protocol data",
        ),
    ],

    system_configurations=[
        SystemConfiguration(
            system=DownstreamSystem.EDC,
            config_type="study_build",
            description="Complete EDC study structure from SOA",
            data_sources=["visits[]", "activities[]", "conditional_activities[]"],
            output_format="EDC vendor study build format",
            example_config={
                "visits": [
                    {"id": "SCR", "name": "Screening", "day": -28, "window": [-7, 0], "epoch": "Screening"},
                    {"id": "BL", "name": "Baseline/Day 1", "day": 1, "window": [0, 0], "epoch": "Treatment"},
                    {"id": "C1D15", "name": "Cycle 1 Day 15", "day": 15, "window": [-3, 3], "epoch": "Treatment"}
                ],
                "form_assignments": [
                    {"form": "DM", "visits": ["SCR"]},
                    {"form": "VS", "visits": ["SCR", "BL", "C1D15"]},
                    {"form": "LB", "visits": ["SCR", "BL", "C1D15"]}
                ]
            }
        ),
    ],
)


ELIGIBILITY_CRITERIA_DOC = AgentDocumentation(
    agent_id="eligibility_criteria",
    display_name="Eligibility Criteria",
    instance_type="EligibilityCriteria",
    wave=1,
    priority=0,

    purpose="""
    Extracts and structures all inclusion and exclusion criteria with categorization,
    verification methods, and timing requirements. Essential for site screening tools
    and EDC eligibility verification.
    """,

    scope="""
    - Inclusion criteria (mandatory requirements)
    - Exclusion criteria (disqualifying conditions)
    - Criterion categories (demographic, disease, treatment history, lab, etc.)
    - Verification methods and timing
    - Waivers and exceptions
    - Re-screening criteria
    """,

    key_sections_analyzed=[
        "Section 5: Eligibility Criteria",
        "Section 5.1: Inclusion Criteria",
        "Section 5.2: Exclusion Criteria",
    ],

    key_insights=[
        AgentInsight(
            name="Inclusion Criteria",
            description="Mandatory requirements with categories and verification",
            data_path="inclusion_criteria[]",
            downstream_uses=["EDC eligibility CRF", "Site screening tools", "IRB review"],
            automation_category=AutomationCategory.ELIGIBILITY,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_INC_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Generate inclusion criteria edit checks",
                    source_data_path="inclusion_criteria[]",
                    rule_logic="""
                    FOR EACH criterion:
                        CREATE edit_check {
                            field: DERIVE_FIELD(criterion.category),
                            check: 'MUST BE TRUE',
                            message: 'Inclusion criterion ' + criterion.number + ' not met'
                        }
                    """,
                ),
            ]
        ),
        AgentInsight(
            name="Exclusion Criteria",
            description="Disqualifying conditions with timing and exceptions",
            data_path="exclusion_criteria[]",
            downstream_uses=["EDC eligibility CRF", "Site screening tools", "Medical monitor review"],
            automation_category=AutomationCategory.ELIGIBILITY,
            priority="critical",
            automation_rules=[
                AutomationRule(
                    rule_id="EDC_EXC_001",
                    rule_type="edit_check",
                    target_system=DownstreamSystem.EDC,
                    description="Generate exclusion criteria edit checks",
                    source_data_path="exclusion_criteria[]",
                    rule_logic="""
                    FOR EACH criterion:
                        CREATE edit_check {
                            field: DERIVE_FIELD(criterion.category),
                            check: 'MUST BE FALSE',
                            message: 'Exclusion criterion ' + criterion.number + ' applies - subject not eligible'
                        }
                    """,
                ),
            ]
        ),
    ],

    downstream_systems=[
        DownstreamSystem.EDC,
        DownstreamSystem.CTMS,
    ],

    automation_use_cases=[
        "Auto-generate EDC eligibility CRFs with edit checks",
        "Create site screening checklists",
        "Configure eligibility verification workflows",
        "Generate IRB-ready eligibility summaries",
    ],

    depends_on=["study_metadata"],
    enriches=[],
    cross_references=["laboratory_specifications", "concomitant_medications"],

    cdisc_domains=["IE"],
    regulatory_relevance="ICH M11 Section 5",
    schema_file="eligibility_criteria_schema.json",
    typical_extraction_time_seconds=60,

    cross_agent_synergies=[
        CrossAgentSynergy(
            synergy_id="SYN_ELIG_LAB_001",
            name="Eligibility + Labs → Automated Screening",
            agents_involved=["eligibility_criteria", "laboratory_specifications", "concomitant_medications"],
            description="Eligibility criteria + lab specifications + washout periods = complete screening automation",
            combined_insight="All screening requirements in one place = Site screening app",
            automation_enabled="Generate interactive eligibility checklist with real-time validation",
            example_output='{"criterion": "ANC >= 1500", "status": "PASS", "value": 2100, "source": "Screening Labs"}'
        ),
    ],

    system_configurations=[
        SystemConfiguration(
            system=DownstreamSystem.EDC,
            config_type="eligibility_module",
            description="Complete eligibility CRF with edit checks",
            data_sources=["inclusion_criteria[]", "exclusion_criteria[]"],
            output_format="EDC eligibility module specification",
            example_config={
                "inclusion_checks": [
                    {"criterion": "I1", "field": "AGE", "operator": ">=", "value": 18, "message": "Must be >= 18 years"},
                    {"criterion": "I2", "field": "ECOG", "operator": "<=", "value": 1, "message": "ECOG must be 0 or 1"}
                ],
                "exclusion_checks": [
                    {"criterion": "E1", "field": "BRAIN_METS", "operator": "=", "value": "N", "message": "Brain metastases excluded"},
                    {"criterion": "E2", "field": "PRIOR_IO", "operator": "=", "value": "N", "message": "Prior immunotherapy excluded"}
                ]
            }
        ),
    ],
)


# =============================================================================
# DOCUMENTATION REGISTRY
# =============================================================================

AGENT_DOCUMENTATION_REGISTRY: Dict[str, AgentDocumentation] = {
    # Wave 0
    "study_metadata": STUDY_METADATA_DOC,

    # Wave 1 - P0
    "arms_design": ARMS_DESIGN_DOC,
    "endpoints_estimands_sap": ENDPOINTS_ESTIMANDS_SAP_DOC,
    "adverse_events": ADVERSE_EVENTS_DOC,
    "safety_decision_points": SAFETY_DECISION_POINTS_DOC,

    # Wave 1 - P1
    "concomitant_medications": CONCOMITANT_MEDICATIONS_DOC,
    "biospecimen_handling": BIOSPECIMEN_HANDLING_DOC,
    "laboratory_specifications": LABORATORY_SPECIFICATIONS_DOC,
    "informed_consent": INFORMED_CONSENT_DOC,
    "pro_specifications": PRO_SPECIFICATIONS_DOC,

    # Wave 1 - P2
    "data_management": DATA_MANAGEMENT_DOC,
    "site_operations_logistics": SITE_OPERATIONS_LOGISTICS_DOC,

    # Wave 2
    "quality_management": QUALITY_MANAGEMENT_DOC,
    "withdrawal_procedures": WITHDRAWAL_PROCEDURES_DOC,
    "imaging_central_reading": IMAGING_CENTRAL_READING_DOC,
    "pkpd_sampling": PKPD_SAMPLING_DOC,

    # Special agents
    "soa_schedule": SOA_SCHEDULE_DOC,
    "eligibility_criteria": ELIGIBILITY_CRITERIA_DOC,
}


def get_agent_documentation(agent_id: str) -> Optional[AgentDocumentation]:
    """Get documentation for a specific agent."""
    return AGENT_DOCUMENTATION_REGISTRY.get(agent_id)


def get_all_agent_ids() -> List[str]:
    """Get all documented agent IDs."""
    return list(AGENT_DOCUMENTATION_REGISTRY.keys())


def get_agents_by_wave(wave: int) -> List[AgentDocumentation]:
    """Get all agents in a specific wave."""
    return [doc for doc in AGENT_DOCUMENTATION_REGISTRY.values() if doc.wave == wave]


def get_agents_by_downstream_system(system: DownstreamSystem) -> List[AgentDocumentation]:
    """Get all agents that feed into a specific downstream system."""
    return [
        doc for doc in AGENT_DOCUMENTATION_REGISTRY.values()
        if system in doc.downstream_systems
    ]


def generate_agent_documentation_json(agent_id: str) -> Optional[Dict]:
    """
    Generate JSON documentation for an agent to embed in USDM output.

    This is added to each agent's output under the `_agentDocumentation` key
    to provide context for downstream systems.
    """
    doc = get_agent_documentation(agent_id)
    if not doc:
        return None

    # Build automation rules list
    all_automation_rules = list(doc.automation_rules)
    for insight in doc.key_insights:
        all_automation_rules.extend(insight.automation_rules)

    return {
        "agentId": doc.agent_id,
        "displayName": doc.display_name,
        "instanceType": doc.instance_type,
        "wave": doc.wave,
        "priority": doc.priority,
        "purpose": doc.purpose.strip(),
        "scope": doc.scope.strip(),
        "keySectionsAnalyzed": doc.key_sections_analyzed,
        "keyInsights": [
            {
                "name": insight.name,
                "description": insight.description,
                "dataPath": insight.data_path,
                "downstreamUses": insight.downstream_uses,
                "automationCategory": insight.automation_category.value,
                "priority": insight.priority,
                "automationRules": [
                    {
                        "ruleId": rule.rule_id,
                        "ruleType": rule.rule_type,
                        "targetSystem": rule.target_system.value,
                        "description": rule.description,
                        "sourceDataPath": rule.source_data_path,
                        "ruleLogic": rule.rule_logic.strip() if rule.rule_logic else None,
                        "example": rule.example,
                    }
                    for rule in insight.automation_rules
                ],
                "validationChecks": insight.validation_checks,
            }
            for insight in doc.key_insights
        ],
        "downstreamSystems": [sys.value for sys in doc.downstream_systems],
        "automationUseCases": doc.automation_use_cases,
        "integration": {
            "dependsOn": doc.depends_on,
            "enriches": doc.enriches,
            "crossReferences": doc.cross_references,
        },
        "cdiscDomains": doc.cdisc_domains,
        "regulatoryRelevance": doc.regulatory_relevance,
        "schemaFile": doc.schema_file,

        # Enhanced fields for downstream automation
        "automationRules": [
            {
                "ruleId": rule.rule_id,
                "ruleType": rule.rule_type,
                "targetSystem": rule.target_system.value,
                "description": rule.description,
                "sourceDataPath": rule.source_data_path,
                "ruleLogic": rule.rule_logic.strip() if rule.rule_logic else None,
                "example": rule.example,
            }
            for rule in all_automation_rules
        ],
        "crossAgentSynergies": [
            {
                "synergyId": syn.synergy_id,
                "name": syn.name,
                "agentsInvolved": syn.agents_involved,
                "description": syn.description,
                "combinedInsight": syn.combined_insight,
                "automationEnabled": syn.automation_enabled,
                "exampleOutput": syn.example_output,
            }
            for syn in doc.cross_agent_synergies
        ],
        "validationRules": [
            {
                "ruleId": val.rule_id,
                "name": val.name,
                "agentsInvolved": val.agents_involved,
                "validationType": val.validation_type,
                "description": val.description,
                "checkLogic": val.check_logic,
                "severity": val.severity,
            }
            for val in doc.validation_rules
        ],
        "systemConfigurations": [
            {
                "system": cfg.system.value,
                "configType": cfg.config_type,
                "description": cfg.description,
                "dataSources": cfg.data_sources,
                "outputFormat": cfg.output_format,
                "exampleConfig": cfg.example_config,
            }
            for cfg in doc.system_configurations
        ],
    }


def generate_all_agent_documentation_json() -> Dict[str, Dict]:
    """Generate JSON documentation for all agents."""
    return {
        agent_id: generate_agent_documentation_json(agent_id)
        for agent_id in AGENT_DOCUMENTATION_REGISTRY
    }


def print_agent_documentation_summary():
    """Print a formatted summary of all agent documentation."""
    print("=" * 80)
    print("AGENT DOCUMENTATION REGISTRY - ENHANCED FOR DOWNSTREAM AUTOMATION")
    print("=" * 80)

    for wave in range(3):
        agents = get_agents_by_wave(wave)
        if not agents:
            continue

        print(f"\n{'='*40}")
        print(f"WAVE {wave}")
        print(f"{'='*40}")

        for doc in sorted(agents, key=lambda d: d.priority):
            priority_label = f"P{doc.priority}"
            systems = ", ".join(s.name for s in doc.downstream_systems[:3])

            # Count automation rules
            total_rules = len(doc.automation_rules)
            for insight in doc.key_insights:
                total_rules += len(insight.automation_rules)

            print(f"\n  [{priority_label}] {doc.display_name} ({doc.agent_id})")
            print(f"      Instance Type: {doc.instance_type}")
            print(f"      Downstream: {systems}")
            print(f"      Key Insights: {len(doc.key_insights)}")
            print(f"      Automation Rules: {total_rules}")
            print(f"      Cross-Agent Synergies: {len(doc.cross_agent_synergies)}")
            print(f"      CDISC Domains: {', '.join(doc.cdisc_domains)}")


if __name__ == "__main__":
    print_agent_documentation_summary()
