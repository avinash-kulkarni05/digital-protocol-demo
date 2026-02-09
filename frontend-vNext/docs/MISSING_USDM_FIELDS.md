# Missing USDM Fields in Frontend UI

This document lists all USDM fields that are extracted by the backend but NOT currently displayed in the frontend UI, organized by section/module.

## Summary

| Section | Fields Displayed | Fields Missing | Coverage |
|---------|------------------|----------------|----------|
| Study Metadata | ~15 | ~45 | ~25% |
| Arms & Design | ~25 | ~60 | ~30% |
| Endpoints & SAP | ~20 | ~50 | ~30% |
| Adverse Events | ~15 | ~55 | ~20% |
| Safety Decision Points | ~8 | ~30 | ~20% |
| Concomitant Medications | ~15 | ~45 | ~25% |
| Biospecimen Handling | ~10 | ~60 | ~15% |
| Laboratory Specifications | ~12 | ~55 | ~18% |
| Data Management | ~8 | ~50 | ~15% |
| Site Operations | ~6 | ~80 | ~7% |
| Quality Management | ~5 | ~25 | ~17% |
| Withdrawal Procedures | ~5 | ~20 | ~20% |
| Imaging & Central Reading | ~5 | ~20 | ~20% |
| PK/PD Sampling | ~8 | ~25 | ~25% |
| Informed Consent | ~8 | ~25 | ~25% |
| PRO Specifications | ~6 | ~20 | ~25% |

**Overall: ~20-30% of extracted fields are displayed in fixed UI components**

---

## 1. STUDY METADATA (`study_metadata`)

### NOT DISPLAYED - Study Identifiers
- `studyIdentifiers[].provenance` - Source tracking for each identifier
- Full identifier schema details beyond id/scopeId

### NOT DISPLAYED - Protocol Versions
- `studyProtocolVersions[].amendmentNumber` - Amendment identifiers
- `studyProtocolVersions[].provenance` - Version source tracking

### NOT DISPLAYED - Target Disease (Deep Fields)
- `targetDisease.histology` - Histological classification
- `targetDisease.meddraCode` - MedDRA code
- `targetDisease.icdCode` - ICD-10 code

### NOT DISPLAYED - Prior Therapy Requirements
- `priorTherapyRequirements.required[]` - Array of required prior therapies
- `priorTherapyRequirements.minPriorLines` - Minimum prior treatment lines
- `priorTherapyRequirements.maxPriorLines` - Maximum prior treatment lines

### NOT DISPLAYED - Biomarker Requirements
- `biomarkerRequirements[]` - Full array:
  - `name` - Biomarker name
  - `requirement` - Required status
  - `testingRequired` - Boolean

### NOT DISPLAYED - Screening & Enrollment Statistics
- `estimatedScreenFailureRate` - Decimal (0.0-1.0)
- `screenFailureRateMethod` - Method description

### NOT DISPLAYED - Study Milestones (Date Objects)
- `studyStartDate` - Full milestone object (date, dateType, description)
- `firstSubjectScreened` - Milestone date object
- `firstSubjectRandomized` - Milestone date object
- `enrollmentCompletionDate` - Milestone date object
- `primaryCompletionDate` - Milestone date object
- `studyCompletionDate` - Milestone date object

### NOT DISPLAYED - Interim Analyses
- `interimAnalyses[]` - Full array:
  - `id` - Unique identifier (IA1, IA2...)
  - `name` - Descriptive name
  - `timing` - When analysis occurs
  - `plannedEventCount` - Integer
  - `purpose` - Futility/Efficacy/Safety/Other
  - `alphaSpent` - Decimal (0.0-1.0)
  - `stoppingBoundary` - O'Brien-Fleming, Pocock, etc.

### NOT DISPLAYED - Randomization Details (Deep Fields)
- `randomization.allocationMethod` - Method of allocation
- `randomization.blockSize` - Block size for randomization

### NOT DISPLAYED - Blinding Details
- `blinding.whoIsBlinded[]` - Array (Participant, Investigator, Outcomes Assessor, Caregiver)

### NOT DISPLAYED - Country Inference
- `countryInferenceMethod` - How countries were determined

### NOT DISPLAYED - Source Document Metadata
- `sourceDocument.documentId` - Unique identifier
- `sourceDocument.sha256Hash` - File hash
- `sourceDocument.byteSize` - Size in bytes
- `sourceDocument.uploadTimestamp` - ISO timestamp
- `sourceDocument.pageCount` - Total pages

---

## 2. ARMS & DESIGN (`arms_design`)

### NOT DISPLAYED - Study Epochs
- `studyEpochs[]` - Full array:
  - `id` - Epoch identifier (EPOCH01, SCREENING, TREATMENT)
  - `epochType` - Code object (Screening, Run-In, Treatment, Follow-up, Extension)
  - `sequenceInStudy` - Order (1, 2, 3...)
  - `durationDays` - Integer
  - `durationDescription` - Text description

### NOT DISPLAYED - Study Cells
- `studyCells[]` - Full array mapping arms to epochs:
  - `id` - Cell identifier
  - `armId` - Reference to arm
  - `epochId` - Reference to epoch
  - `interventionIds[]` - Array of intervention references

### NOT DISPLAYED - Extended Randomization Details
- `designMetadata.randomizationDetails`:
  - `randomization_type` - central, site-level, interactive, manual
  - `randomization_method` - IVRS, IWRS, IRT, envelope, computer_generated
  - `randomization_timing` - When randomization occurs
  - `irt_vendor` - Almac, Medidata RTSM, Oracle Siebel, etc.
  - `irt_system_name` - System name
  - `block_sizes` - Array of integers
  - `block_size_selection` - fixed, variable, random_permuted
  - `seed_documentation` - String

### NOT DISPLAYED - Enrollment Caps
- `enrollmentCaps[]` - Full array:
  - `cap_id` - Identifier
  - `cap_type` - stratum, arm, region, country, site, overall
  - `cap_criteria` - Criteria description
  - `max_subjects` - Integer limit
  - `action_when_reached` - stop_enrollment, redistribute, notify_sponsor

### NOT DISPLAYED - Adaptive Randomization
- `adaptiveRandomization`:
  - `is_adaptive` - Boolean
  - `adaptation_method` - response-adaptive, covariate-adaptive, outcome-adaptive, urn
  - `adaptation_triggers[]` - Array of triggers
  - `interim_analysis_points[]` - Array of analysis points
  - `adaptation_rules` - Rules description

### NOT DISPLAYED - Re-Randomization
- `reRandomization`:
  - `allowed` - Boolean
  - `triggers[]` - Array of triggers
  - `conditions` - Conditions text
  - `maximum_rerandomizations` - Integer limit

### NOT DISPLAYED - Drug Supply Model
- `supplyModel` - Central, Depot, Direct-to-Site, Hybrid, Other
- `drugSupply`:
  - `kitTypes[]` - Array of kit specifications
  - `dispensingSchedule` - Schedule text
  - `overagePercentage` - Decimal (0-100)

### NOT DISPLAYED - Intervention Deep Fields
- `interventions[].manufacturer` - Manufacturer name
- `interventions[].formulation` - e.g., "lyophilized powder"
- `interventions[].strength` - e.g., "100mg/vial"
- `interventions[].storageConditions` - Storage requirements
- `interventions[].isBlinded` - Boolean
- `interventions[].doseModifications.modificationTriggers[]`:
  - `id` - Trigger identifier
  - `condition` - e.g., "Grade 3 nausea"
  - `toxicityGrade` - Integer (1-5)
  - `action` - Hold, Reduce, Discontinue, Hold then reduce
  - `targetLevel` - Integer (-1, -2, etc.)
  - `holdCriteria` - Text
- `interventions[].doseModifications.permanentDiscontinuationTriggers[]`
- `interventions[].doseModifications.rechallengeCriteria`
- `interventions[].doseModifications.maximumReductions`

### NOT DISPLAYED - Stratification Factor Deep Fields
- `stratificationFactors[].is_irt_stratification` - Boolean
- `stratificationFactors[].is_analysis_stratification` - Boolean
- `stratificationFactors[].enrollment_cap_per_level` - Integer
- `stratificationFactors[].levels[]` (when object array):
  - `level_id`, `level_name`, `level_definition`, `data_source`

---

## 3. ENDPOINTS, ESTIMANDS & SAP (`endpoints`)

### NOT DISPLAYED - Objective Deep Fields
- `objectives[].endpoint_ids[]` - Array of linked endpoint references

### NOT DISPLAYED - Endpoint Deep Fields
- `endpoints[].purpose` - Endpoint purpose
- `endpoints[].assessment_method` - Method of assessment
- `endpoints[].assessor` - Who assesses
- `endpoints[].primary_timepoint_weeks` - Integer
- `endpoints[].assessment_timepoints_weeks[]` - Array of integers
- `endpoints[].analysis_population_id` - Population reference
- `endpoints[].primary_timepoint_text` - Text description

### NOT DISPLAYED - Estimand Treatment Details
- `estimands[].treatment.experimental_arm`:
  - `arm_type` - Code object
  - `description` - Text
- `estimands[].treatment.comparator_arm`:
  - `arm_type` - Code object
  - `description` - Text

### NOT DISPLAYED - Estimand Population Details
- `estimands[].population`:
  - `analysis_population_id` - Reference
  - `description` - Text

### NOT DISPLAYED - Estimand Variable Details
- `estimands[].variable`:
  - `endpoint_id` - Reference
  - `description` - Text

### NOT DISPLAYED - Intercurrent Events Deep Fields
- `estimands[].intercurrent_events[].strategy_rationale` - Rationale text

### NOT DISPLAYED - Analysis Population Deep Fields
- `analysis_populations[].inclusion_criteria[]` - Array of criteria
- `analysis_populations[].exclusion_criteria[]` - Array of criteria
- `analysis_populations[].is_primary_for_endpoints[]` - Array of endpoint refs
- `analysis_populations[].is_sensitivity_for_endpoints[]` - Array of endpoint refs

### NOT DISPLAYED - Statistical Methods Deep Fields
- `statistical_methods[].model_type` - Model type
- `statistical_methods[].alpha` - Decimal (0.0-1.0)
- `statistical_methods[].multiplicity`:
  - `method` - Method name
  - `description` - Description
- `statistical_methods[].software_package` - Software used
- `statistical_methods[].procedure` - Procedure text

### NOT DISPLAYED - Subgroup Analysis Deep Fields
- `subgroup_analyses[].interaction_test` - Boolean
- `subgroup_analyses[].forest_plot` - Boolean

### NOT DISPLAYED - Extraction Statistics
- `extraction_statistics`:
  - `objectives_count`, `endpoints_count`, `estimands_count`
  - `populations_count`, `sensitivity_analyses_count`
  - `statistical_methods_count`, `subgroup_analyses_count`
  - `has_multiplicity_adjustment`, `has_missing_data_strategy`

---

## 4. ADVERSE EVENTS (`safety/adverse_events`)

### NOT DISPLAYED - AE Definitions Deep Fields
- `ae_definitions.collection_start` - Start of collection
- `ae_definitions.collection_end` - End of collection
- `ae_definitions.collection_end_days` - Days after last dose
- `ae_definitions.pre_existing_condition_handling` - How handled

### NOT DISPLAYED - SAE Criteria Deep Fields
- `sae_criteria.criteria[].exclusions[]` - Array of exclusions

### NOT DISPLAYED - Grading System Deep Fields
- `grading_system.grade_definitions[]`:
  - `grade` - Integer (1-5)
  - `label` - Grade label
  - `definition` - Full definition

### NOT DISPLAYED - Causality Assessment Deep Fields
- `causality_assessment.assessment_method` - Method used
- `causality_assessment.assessor` - Who assesses
- `causality_assessment.categories[]`:
  - `category` - Code object
  - `definition` - Definition text

### NOT DISPLAYED - Coding Dictionary
- `coding_dictionary`:
  - `dictionary_name` - e.g., MedDRA
  - `dictionary_version` - Version
  - `coding_level` - Level of coding

### NOT DISPLAYED - Reporting Procedures Deep Fields
- `reporting_procedures.routine_ae_reporting`:
  - `timeline_hours`, `timeline_description`, `method`
- `reporting_procedures.sae_reporting`:
  - `initial_report_hours`, `followup_report_days`
  - `recipients[]`, `method`
- `reporting_procedures.susar_reporting`:
  - `fatal_timeline_days`, `non_fatal_timeline_days`
- `reporting_procedures.pregnancy_reporting`:
  - `timeline_hours`, `outcome_tracking`, `partner_pregnancy`
- `reporting_procedures.expedited_reporting_criteria[]`
- `reporting_procedures.unblinding_procedures`

### NOT DISPLAYED - AESI Deep Fields
- `aesi_list[].rationale` - Why it's an AESI
- `aesi_list[].special_monitoring` - Special monitoring requirements

### NOT DISPLAYED - DLT Criteria
- `dlt_criteria` (entire object):
  - `has_dlt_criteria` - Boolean
  - `dlt_observation_period`:
    - `duration_days`, `start_reference`
  - `dlt_definitions[]`:
    - `id`, `category`, `description`
    - `grade_threshold`, `duration_requirement`, `exceptions[]`
  - `mtd_determination`:
    - `method`, `dlt_rate_threshold`, `minimum_patients`

### NOT DISPLAYED - Safety Committees Deep Fields
- `safety_committees[].committee_type` - Code object
- `safety_committees[].review_frequency` - Frequency
- `safety_committees[].responsibilities[]` - Array of responsibilities
- `safety_committees[].charter_reference` - Reference to charter

---

## 5. SAFETY DECISION POINTS (`safety_decision_points`)

### NOT DISPLAYED - Discovered Categories
- `discovered_categories[]` (entire array):
  - `category_id`, `category_name`
  - `category_description`, `parameters_count`

### NOT DISPLAYED - Decision Points Deep Fields
- `decision_points[].measurement_type` - Type of measurement
- `decision_points[].decision_rules[].conditions` - Object with conditions
- `decision_points[].decision_rules[].actions[]` - Array of action objects
- `decision_points[].decision_rules[].recovery_criteria` - Recovery criteria object
- `decision_points[].monitoring_requirements` - Monitoring requirements object

### NOT DISPLAYED - Stopping Rules Summary
- `stopping_rules_summary` (entire object):
  - `total_permanent_stopping_conditions`
  - `stopping_conditions[]`:
    - `condition_id`, `condition_type`
    - `description`, `trigger_threshold`, `action`

### NOT DISPLAYED - Dose Modification Levels
- `dose_modification_levels` (entire object):
  - `has_defined_levels` - Boolean
  - `levels[]`:
    - `level_id`, `level_name`
    - `dose_percentage`, `absolute_dose`
  - `minimum_dose` - Minimum allowed dose
  - `re_escalation_allowed` - Boolean
  - `re_escalation_criteria` - Criteria text

### NOT DISPLAYED - Organ-Specific Adjustments
- `organ_specific_adjustments[]` (entire array):
  - `id`, `organ_system`, `organ_system_detail`
  - `adjustment_trigger`, `adjustment_action`
  - `monitoring_requirements`

---

## 6. CONCOMITANT MEDICATIONS (`medications`)

### NOT DISPLAYED - Prohibited Medications Deep Fields
- `prohibited_medications[].prohibition_period` - Code object
- `prohibited_medications[].prohibition_period_detail` - Detail text
- `prohibited_medications[].biomedicalConcept` - CDISC concept object

### NOT DISPLAYED - Restricted Medications Deep Fields
- `restricted_medications[].conditions`:
  - `max_dose`, `max_duration_days`
  - `approval_required_from`, `monitoring_requirements`
  - `timing_restriction`, `clinical_scenario`
- `restricted_medications[].rationale` - Rationale text
- `restricted_medications[].biomedicalConcept` - CDISC concept

### NOT DISPLAYED - Required Medications Deep Fields
- `required_medications[].requirement_type` - Code object
- `required_medications[].dosing`:
  - `dose`, `route`, `frequency`
- `required_medications[].timing`:
  - `relative_to`, `time_before_minutes`
  - `time_after_minutes`, `timing_description`
- `required_medications[].alternatives[]` - Array of alternatives
- `required_medications[].biomedicalConcept`

### NOT DISPLAYED - Rescue Medications Deep Fields
- `rescue_medications[].dosing_instructions`
- `rescue_medications[].documentation_required` - Boolean
- `rescue_medications[].impact_on_endpoints`
- `rescue_medications[].biomedicalConcept`

### NOT DISPLAYED - Washout Requirements Deep Fields
- `washout_requirements[].washout_duration_half_lives`
- `washout_requirements[].applies_to` - Code object
- `washout_requirements[].biomedicalConcept`

### NOT DISPLAYED - Drug Interactions Deep Fields
- `drug_interactions[].severity` - Code object (strong, moderate, weak)
- `drug_interactions[].affected_drugs[]` - Array
- `drug_interactions[].clinical_effect` - Clinical effect text
- `drug_interactions[].management` - Code object
- `drug_interactions[].management_detail` - Detail text
- `drug_interactions[].biomedicalConcept`

### NOT DISPLAYED - Allowed Medications Deep Fields
- `allowed_medications[].biomedicalConcept`

### NOT DISPLAYED - Vaccine Policy
- `vaccine_policy` (entire object):
  - `live_vaccines_prohibited` - Boolean
  - `live_vaccine_washout_days` - Integer
  - `inactivated_vaccines_allowed` - Boolean
  - `covid_vaccine_policy` - Policy text
  - `specific_restrictions[]` - Array

### NOT DISPLAYED - Herbal Supplements Policy
- `herbal_supplements_policy` (entire object):
  - `prohibited_supplements[]` - Array
  - `rationale` - Rationale text

---

## 7. BIOSPECIMEN HANDLING (`biospecimen`)

### NOT DISPLAYED - Central Laboratory Deep Fields
- `central_laboratory.location` - Location text
- `central_laboratory.accreditations[]` - Array (CAP, CLIA, ISO 15189, GLP)
- `central_laboratory.contact_info` - Contact information

### NOT DISPLAYED - Specimen Types Deep Fields
- `discovered_specimen_types[].specimen_subtype` - Subtype details
- `discovered_specimen_types[].purpose` - pk, pd, biomarker, safety, etc.
- `discovered_specimen_types[].purpose_description`
- `discovered_specimen_types[].biomedicalConcept`

### NOT DISPLAYED - Collection Containers
- `collection_containers[]` (entire array):
  - `container_id`, `container_name`
  - `tube_type` - SST, EDTA, lithium_heparin, etc.
  - `tube_color`, `anticoagulant`, `preservative`
  - `volume_capacity`, `fill_volume`
  - `specimen_ref`, `special_instructions`

### NOT DISPLAYED - Collection Schedule Deep Fields
- `collection_schedule[].schedule_id`, `specimen_ref`
- `collection_schedule[].timepoint_type` - screening, baseline, pre_dose, post_dose, etc.
- `collection_schedule[].relative_time`, `collection_window`
- `collection_schedule[].number_of_samples`, `volume_per_sample`
- `collection_schedule[].fasting_required`, `fasting_duration`
- `collection_schedule[].special_conditions`

### NOT DISPLAYED - Processing Requirements
- `processing_requirements[]` (entire array):
  - `processing_id`, `specimen_ref`
  - `processing_step`, `step_order`
  - `time_constraint`, `time_zero_reference`
  - `temperature_during_processing`
  - `centrifuge_speed`, `centrifuge_time`, `centrifuge_temperature`
  - `aliquot_count`, `aliquot_volume`, `aliquot_container`
  - `special_instructions`

### NOT DISPLAYED - Storage Requirements Deep Fields
- `storage_requirements[].storage_phase` - temporary, short_term, long_term, archive
- `storage_requirements[].equipment_type` - refrigerator, freezer types, LN2
- `storage_requirements[].monitoring_requirements`
- `storage_requirements[].excursion_limits`
- `storage_requirements[].backup_requirements`
- `storage_requirements[].stability_limit`

### NOT DISPLAYED - Shipping Requirements Deep Fields
- `shipping_requirements[].origin_description`
- `shipping_requirements[].destination`
- `shipping_requirements[].shipping_frequency`
- `shipping_requirements[].packaging_requirements`
- `shipping_requirements[].temperature_monitor`
- `shipping_requirements[].courier_requirements`
- `shipping_requirements[].un_classification`
- `shipping_requirements[].customs_requirements`
- `shipping_requirements[].manifest_requirements`
- `shipping_requirements[].contingency_procedures`

### NOT DISPLAYED - Kit Specifications
- `kit_specifications` (entire object):
  - `kit_provider`, `kit_components[]`
  - `labeling_requirements`, `barcode_format`
  - `label_content`, `kit_ordering`

### NOT DISPLAYED - Quality Requirements
- `quality_requirements` (entire object):
  - `acceptance_criteria`, `rejection_criteria`
  - `minimum_volume`, `chain_of_custody`
  - `documentation_requirements`, `quality_metrics`

### NOT DISPLAYED - Regulatory Requirements
- `regulatory_requirements` (entire object):
  - `informed_consent_requirements`
  - `genetic_consent`, `future_use_consent`
  - `withdrawal_procedures`, `export_requirements`
  - `privacy_requirements`, `retention_period`
  - `destruction_procedures`

### NOT DISPLAYED - Volume Summary Deep Fields
- `volume_summary.maximum_single_draw`
- `volume_summary.pediatric_adjustments`
- `volume_summary.volume_limit_compliance`

---

## 8. LABORATORY SPECIFICATIONS (`laboratory_specifications`)

### NOT DISPLAYED - Central Laboratory Deep Fields
- `central_laboratory.accreditations[]` - Array (CAP, CLIA, ISO 15189)
- `central_laboratory.data_transfer_method`

### NOT DISPLAYED - Discovered Panels Deep Fields
- `discovered_panels[].panel_code` - LOINC panel code
- `discovered_panels[].panel_category` - hematology, chemistry, coagulation, etc.
- `discovered_panels[].biomedicalConcept`

### NOT DISPLAYED - Laboratory Tests Deep Fields
- `laboratory_tests[].test_code` - LOINC code
- `laboratory_tests[].collection_container`
- `laboratory_tests[].collection_volume`
- `laboratory_tests[].fasting_required` - Boolean
- `laboratory_tests[].special_handling`
- `laboratory_tests[].reference_ranges[]`:
  - `low`, `high`, `unit`, `population`, `text`
- `laboratory_tests[].critical_values[]`:
  - `type`, `value`, `unit`, `action_required`
- `laboratory_tests[].clinical_significance`
- `laboratory_tests[].biomedicalConcept`

### NOT DISPLAYED - Testing Schedule Deep Fields
- `testing_schedule[].timepoints[]`:
  - `timepoint_name`, `timepoint_type`
  - `window`, `conditions`
- `testing_schedule[].frequency`

### NOT DISPLAYED - Sample Collection Requirements
- `sample_collection_requirements` (entire object):
  - `fasting_requirements`, `timing_requirements`
  - `processing_requirements`, `storage_requirements`
  - `shipping_requirements`

### NOT DISPLAYED - Lab-Based Dose Modifications
- `lab_based_dose_modifications[]` (entire array):
  - `modification_id`, `parameter_name`
  - `trigger_condition`, `operator`
  - `threshold_value`, `threshold_unit`
  - `reference_type` - ULN, LLN, baseline, absolute
  - `required_action`, `recovery_criteria`

### NOT DISPLAYED - Eligibility Lab Criteria
- `eligibility_lab_criteria[]` (entire array):
  - `criteria_id`, `criteria_type` - inclusion, exclusion
  - `parameter_name`, `condition`
  - `operator`, `threshold_value`, `threshold_unit`

### NOT DISPLAYED - Critical Value Reporting
- `critical_value_reporting` (entire object):
  - `notification_timeline`
  - `notification_recipients[]`
  - `documentation_requirements`
  - `critical_value_list[]`:
    - `parameter`, `critical_low`, `critical_high`
    - `unit`, `clinical_action`

### NOT DISPLAYED - Abnormal Result Grading
- `abnormal_result_grading` (entire object):
  - `grading_system`, `grading_version`
  - `clinically_significant_threshold`
  - `ae_reporting_threshold`

### NOT DISPLAYED - Pregnancy Testing
- `pregnancy_testing` (entire object):
  - `required`, `applicable_population`
  - `test_type`, `timing`
  - `sensitivity`, `action_if_positive`

### NOT DISPLAYED - Pharmacokinetic Samples
- `pharmacokinetic_samples` (entire object):
  - `pk_sampling_required`, `analytes[]`
  - `sample_type`, `timepoints_description`
  - `volume_per_sample`, `processing_requirements`

### NOT DISPLAYED - Biomarker Samples
- `biomarker_samples` (entire object):
  - `biomarker_sampling_required`
  - `biomarkers[]`:
    - `name`, `purpose`, `sample_type`, `timing`
  - `optional_consent_required`

### NOT DISPLAYED - Local Lab Requirements
- `local_lab_requirements` (entire object):
  - `local_lab_allowed`, `allowed_tests[]`
  - `certification_requirements`

---

## 9. DATA MANAGEMENT (`data_management`)

### NOT DISPLAYED - EDC Specifications Deep Fields
- `edc_specifications.integration_systems[]`:
  - `id`, `system_type`, `vendor_name`
  - `transfer_frequency`, `transfer_method`
- `edc_specifications.language_requirements[]`
- `edc_specifications.crf_modules[]`:
  - `id`, `module_name`, `forms[]`
  - `visit_schedule[]`, `is_repeating`

### NOT DISPLAYED - Data Standards Deep Fields
- `data_standards.sdtm_version`
- `data_standards.sdtm_ig_version`
- `data_standards.adam_version`
- `data_standards.controlled_terminology`:
  - `cdisc_ct_version`, `meddra_version`
  - `whodrug_version`, `snomed_version`
- `data_standards.define_xml_required`
- `data_standards.define_xml_version`
- `data_standards.adrg_required`
- `data_standards.sdrg_required`

### NOT DISPLAYED - Data Quality Deep Fields
- `data_quality.edit_checks`:
  - `standard_checks[]`, `protocol_specific_checks[]`
  - `auto_query_enabled`
- `data_quality.sdv_strategy`:
  - `approach`, `sdv_percentage`
  - `critical_data_points[]`, `sdv_timing`
- `data_quality.query_management`:
  - `resolution_target_days`, `escalation_threshold_days`
  - `auto_query_triggers[]`
- `data_quality.data_review`:
  - `medical_review_frequency`, `statistical_review_frequency`
  - `data_review_committee`

### NOT DISPLAYED - Database Management
- `database_management` (entire object):
  - `database_design`:
    - `external_data_sources[]`, `calculated_fields[]`
    - `derived_variables[]`
  - `interim_locks[]`:
    - `id`, `lock_name`, `trigger`, `scope`
  - `final_database_lock`:
    - `trigger_event`, `timeline_days_from_lplv`
    - `prerequisites[]`, `signoff_required[]`

### NOT DISPLAYED - Data Transfers Deep Fields
- `data_transfers.central_lab`:
  - `vendor_name`, `transfer_frequency`
  - `transfer_method`, `data_reconciliation`
- `data_transfers.imaging`:
  - `vendor_name`, `data_collected[]`, `transfer_method`
- `data_transfers.epro`:
  - `vendor_name`, `transfer_frequency`, `instruments_collected[]`
- `data_transfers.external_adjudication`:
  - `adjudication_types[]`, `export_frequency`
  - `blinding_maintained`
- `data_transfers.dsmb_exports`:
  - `export_frequency`, `unblinded_access`, `data_included[]`

### NOT DISPLAYED - Data Archival
- `data_archival` (entire object):
  - `retention_period_years`, `retention_basis`
  - `archival_format[]`, `archival_location`
  - `destruction_policy`

---

## 10. SITE OPERATIONS & LOGISTICS (`site_operations_logistics`)

### NOT DISPLAYED - Site Selection Deep Fields
- `site_selection.required_criteria[]` - Full criterion objects
- `site_selection.preferred_criteria[]`
- `site_selection.exclusionary_criteria[]`
- `site_selection.geographic_requirements`:
  - `countries[]`, `regions[]`
  - `site_count_target`, `language_requirements[]`

### NOT DISPLAYED - Regulatory & Ethics
- `regulatory_ethics` (entire object):
  - `regulatory_authorities[]`
  - `ethics_committees[]`
  - `informed_consent`:
    - `consent_type`, `languages_required[]`
    - `reconsent_triggers[]`, `assent_required`
    - `electronic_consent_allowed`
  - `data_privacy`:
    - `applicable_regulations`, `data_transfer_requirements`
    - `anonymization_requirements`

### NOT DISPLAYED - Site Personnel
- `site_personnel` (entire object):
  - `principal_investigator`:
    - `qualifications_required`, `responsibilities`
    - `delegation_restrictions`, `time_commitment`
  - `sub_investigators`:
    - `minimum_number`, `qualifications`, `delegated_duties`
  - `coordinators`:
    - `minimum_number`, `responsibilities`, `experience_required`
  - `other_personnel[]`

### NOT DISPLAYED - Training Requirements
- `training_requirements` (entire object):
  - `protocol_training`:
    - `required_for`, `format`, `duration`
    - `assessment_required`, `completion_deadline`
  - `gcp_training`:
    - `required`, `frequency`
    - `certification_required`, `accepted_providers`
  - `specialized_training[]`
  - `training_documentation`:
    - `documentation_requirements`, `retention_period`

### NOT DISPLAYED - Monitoring Plan Deep Fields
- `monitoring_plan.site_initiation_visit`:
  - `required`, `timing`, `format`, `activities`
- `monitoring_plan.routine_monitoring`:
  - `frequency`, `visit_type`, `sdv_percentage`
  - `sdv_scope`, `remote_monitoring_activities`
- `monitoring_plan.triggered_monitoring`:
  - `triggers`, `response_timeline`, `escalation_criteria`
- `monitoring_plan.close_out_visit`:
  - `timing`, `format`, `activities`

### NOT DISPLAYED - Site Activation Timeline
- `site_activation_timeline` (entire object):
  - `site_selection_phase`, `feasibility_assessment`
  - `contract_negotiation`, `regulatory_submission`
  - `ethics_approval`, `site_training`
  - `site_initiation_visit`, `first_patient_ready`
  - `critical_path_items[]`

### NOT DISPLAYED - Drug Supply Logistics Deep Fields
- `drug_supply_logistics.packaging_labeling`:
  - `blinding_requirements`, `label_languages`
  - `temperature_indicators`, `tamper_evident`, `kit_design`
- `drug_supply_logistics.storage_distribution`:
  - `storage_temperature`, `distribution_model`
  - `cold_chain_required`, `shelf_life_months`, `shipping_conditions`
- `drug_supply_logistics.inventory_management`:
  - `iwrs_rtsm_system`, `kit_design`
  - `resupply_triggers`, `resupply_threshold_days`, `expiry_management`
- `drug_supply_logistics.dispensing_schedule[]`:
  - `id`, `visit_name`, `cycle_day`
  - `kits_dispensed[]`, `quantity_dispensed`, `titration_rules`
- `drug_supply_logistics.drug_accountability`:
  - `accountability_frequency`, `accountability_method`
  - `documentation_requirements`, `discrepancy_handling`
- `drug_supply_logistics.drug_return_destruction`:
  - `return_required`, `return_timing`
  - `destruction_method`, `destruction_documentation`
  - `environmental_requirements`
- `drug_supply_logistics.dosing_error_handling`:
  - `overdose_procedures`, `underdose_procedures`
  - `missed_dose_procedures`, `dose_timing_windows`
- `drug_supply_logistics.comparator_medications[]`
- `drug_supply_logistics.emergency_unblinding`:
  - `unblinding_allowed`, `unblinding_triggers`
  - `unblinding_procedure`, `who_can_unblind`
  - `documentation_required`

### NOT DISPLAYED - Technology Systems
- `technology_systems` (entire object):
  - `edc_system`, `iwrs_rtsm`, `epro_devices`
  - `central_services[]`

### NOT DISPLAYED - Equipment & Facilities
- `equipment_facilities` (entire object):
  - `specialized_equipment[]`
  - `facility_requirements`:
    - `patient_space`, `storage_space`, `safety_equipment`

### NOT DISPLAYED - Vendor Coordination
- `vendor_coordination[]` (entire array):
  - `vendor_type`, `vendor_name`
  - `services_provided`, `site_interface_required`
  - `training_required`, `contact_info`

---

## 11. QUALITY MANAGEMENT (`quality_management`)

### NOT DISPLAYED - Monitoring Section Deep Fields
- `monitoring.strategy` - traditional, risk_based, centralized, hybrid
- `monitoring.rationale`
- `monitoring.regulatory_framework`
- `monitoring.adaptive_monitoring`
- `monitoring.centralized_monitoring_enabled`
- `monitoring.centralized_monitoring_tools`

### NOT DISPLAYED - SDV Strategy Deep Fields
- `sdv_strategy.overall_approach`
- `sdv_strategy.default_sdv_percentage`
- `sdv_strategy.critical_data_100_percent[]`
- `sdv_strategy.sdv_reduction_criteria`:
  - `enabled`, `minimum_subjects_enrolled`
  - `error_rate_threshold_percent`, `reduced_sdv_percentage`
- `sdv_strategy.sdv_escalation_criteria`:
  - `error_rate_threshold_percent`, `escalated_sdv_percentage`
- `sdv_strategy.remote_sdv_enabled`

### NOT DISPLAYED - RBQM Fields
- Risk-Based Quality Management fields (if any extracted)

---

## 12. WITHDRAWAL PROCEDURES (`withdrawal_procedures`)

### NOT DISPLAYED - Discontinuation Types Deep Fields
- `discontinuation_types[].definition`
- `discontinuation_types[].allows_continued_followup`

### NOT DISPLAYED - Consent Withdrawal Deep Fields
- `consent_withdrawal.right_to_withdraw`
- `consent_withdrawal.withdrawal_process`
- `consent_withdrawal.data_handling_options[]`:
  - `option code`, `description`, `conditions`

### NOT DISPLAYED - Additional Withdrawal Fields
- Lost to follow-up procedures
- Protocol deviation handling
- Early termination criteria
- Replacement subject criteria

---

## 13. IMAGING & CENTRAL READING (`imaging_central_reading`)

### NOT DISPLAYED - Response Criteria Deep Fields
- `response_criteria.criteria_version`
- `response_criteria.secondary_criteria[]`
- `response_criteria.modifications`

### NOT DISPLAYED - Assessment Deep Fields
- Full imaging assessment specifications
- BICR (Blinded Independent Central Review) requirements
- Reader qualifications and training
- Image quality requirements
- Adjudication procedures

---

## 14. PK/PD SAMPLING (`pkpd_sampling`)

### NOT DISPLAYED - PK Analytes Deep Fields
- Full PK analyte specifications
- Assay methods and validation
- Bioanalytical specifications

### NOT DISPLAYED - PD Biomarkers Deep Fields
- Full PD biomarker specifications
- Validation status
- Cut-off values

### NOT DISPLAYED - Population PK/PD
- Population PK model specifications
- Exposure-response analysis plans
- Covariate analysis

---

## 15. INFORMED CONSENT (`consent`)

### NOT DISPLAYED - Study Overview Deep Fields
- `study_overview.duration`
- `study_overview.procedures_summary`
- `study_overview.expected_number_of_subjects`

### NOT DISPLAYED - Study Procedures
- `study_procedures[]` (entire array):
  - `procedure_id`, `procedure_name`
  - `description`, `frequency`
  - `duration`, `is_optional`

### NOT DISPLAYED - Risks Deep Fields
- `risks[].frequency` - How common the risk is
- `risks[].management` - How risk is managed

### NOT DISPLAYED - Compensation
- `compensation` (entire object):
  - `compensation_type`, `amount_or_description`, `timing`

### NOT DISPLAYED - Confidentiality
- `confidentiality` (entire object):
  - `privacy_protections`, `data_retention`, `data_use_restrictions`

### NOT DISPLAYED - Voluntary Participation
- `voluntary_participation` (entire object):
  - `statement_of_rights`, `withdrawal_process`
  - `consequences_of_withdrawal`

### NOT DISPLAYED - Special Consents
- `special_consents` (entire object):
  - `genetic_testing`, `future_research`, `secondary_data_use`

---

## 16. PRO SPECIFICATIONS (`pro_specifications`)

### NOT DISPLAYED - Instrument Deep Fields
- `instruments[].validation_status`
- `instruments[].disease_or_condition`
- `instruments[].scoring_domains[]`:
  - Domain objects with scoring details
- `instruments[].number_of_items`
- `instruments[].recall_period`
- `instruments[].language_versions[]`
- `instruments[].biomedicalConcept`

### NOT DISPLAYED - Administration Specifications Deep Fields
- `administration.timepoints[]` - Assessment timepoint objects
- `administration.frequency`
- `administration.compliance_threshold`
- `administration.completion_requirements`

### NOT DISPLAYED - PRO Analysis Specifications
- Analysis methodology
- Responder definitions
- MID (Minimally Important Difference) values

---

## References

### Backend Schema Files
- `backend_vNext/schemas/*.json` - All JSON schemas for extraction modules

### Frontend View Components
- `frontend-vNext/client/src/components/review/*View.tsx` - All section view components

### Module Registry
- `backend_vNext/app/module_registry.py` - Extraction module definitions

---

*Document generated: December 2024*
*Based on USDM 4.0 extraction pipeline analysis*
