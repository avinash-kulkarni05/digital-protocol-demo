"""
Module registry for the 17 extraction modules.

Defines configuration for each module including:
- Schema files
- Prompt files (Pass 1 and Pass 2)
- Instance types for USDM compliance
- Execution order and wave-based parallelism
- Dependencies between modules

Agent enabled/disabled status is controlled by config.yaml in the project root.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path
import logging

import yaml

from app.config import settings

logger = logging.getLogger(__name__)

# Path to config.yaml
CONFIG_YAML_PATH = Path(__file__).parent.parent / "config.yaml"


def load_agent_config() -> Dict:
    """
    Load agent configuration from config.yaml.

    Returns:
        Dictionary with agent configurations including enabled status.
    """
    if not CONFIG_YAML_PATH.exists():
        logger.warning(f"config.yaml not found at {CONFIG_YAML_PATH}, using defaults")
        return {}

    try:
        with open(CONFIG_YAML_PATH, 'r') as f:
            config = yaml.safe_load(f)
        return config.get('agents', {})
    except Exception as e:
        logger.error(f"Error loading config.yaml: {e}")
        return {}


# Load agent config once at module load
_AGENT_CONFIG = load_agent_config()


def is_agent_enabled(agent_id: str, default: bool = True) -> bool:
    """
    Check if an agent is enabled in config.yaml.

    Args:
        agent_id: The agent/module ID (e.g., 'study_metadata', 'adverse_events')
        default: Default value if agent not found in config

    Returns:
        True if agent is enabled, False otherwise.
    """
    agent_config = _AGENT_CONFIG.get(agent_id, {})
    if isinstance(agent_config, dict):
        return agent_config.get('enabled', default)
    return default


def reload_agent_config():
    """
    Reload agent configuration from config.yaml.

    Call this if you need to pick up changes to config.yaml at runtime.
    """
    global _AGENT_CONFIG
    _AGENT_CONFIG = load_agent_config()
    logger.info("Agent configuration reloaded from config.yaml")


@dataclass
class ExtractionModuleConfig:
    """Configuration for a single extraction module."""

    module_id: str
    instance_type: str
    display_name: str
    schema_file: str
    pass1_prompt: Optional[str] = None
    pass2_prompt: Optional[str] = None
    # For combined modules with multiple source prompts
    pass1_prompts: Optional[List[str]] = None
    pass2_prompts: Optional[List[str]] = None
    # Execution order (lower = earlier, used for ordering within wave)
    order: int = 0
    # Whether this module is enabled
    enabled: bool = True
    # Wave for parallel execution (0 = runs first, 1 = after wave 0, etc.)
    wave: int = 0
    # Module IDs this module depends on (must complete before this runs)
    dependencies: List[str] = field(default_factory=list)
    # Priority within wave (P0=highest=0, P3=lowest=3)
    priority: int = 0

    def get_schema_path(self) -> Path:
        """Get full path to schema file."""
        return settings.schemas_dir / self.schema_file

    def get_pass1_prompt_path(self) -> Optional[Path]:
        """Get full path to Pass 1 prompt file."""
        if self.pass1_prompt:
            return settings.prompts_dir / self.pass1_prompt
        return None

    def get_pass2_prompt_path(self) -> Optional[Path]:
        """Get full path to Pass 2 prompt file."""
        if self.pass2_prompt:
            return settings.prompts_dir / self.pass2_prompt
        return None

    def get_pass1_prompt_paths(self) -> List[Path]:
        """Get all Pass 1 prompt file paths (for combined modules)."""
        if self.pass1_prompts:
            return [settings.prompts_dir / p for p in self.pass1_prompts]
        elif self.pass1_prompt:
            return [settings.prompts_dir / self.pass1_prompt]
        return []

    def get_pass2_prompt_paths(self) -> List[Path]:
        """Get all Pass 2 prompt file paths (for combined modules)."""
        if self.pass2_prompts:
            return [settings.prompts_dir / p for p in self.pass2_prompts]
        elif self.pass2_prompt:
            return [settings.prompts_dir / self.pass2_prompt]
        return []


# 17 Extraction Modules (includes combined site_operations_logistics)
# Organized into 3 waves for parallel execution
# NOTE: enabled status is now read from config.yaml via is_agent_enabled()
EXTRACTION_MODULES = {
    # WAVE 0: Foundation (must run first - all other modules depend on this)
    "study_metadata": ExtractionModuleConfig(
        module_id="study_metadata",
        instance_type="Study",
        display_name="Study Metadata",
        schema_file="study_metadata_schema.json",
        pass1_prompt="study_metadata_pass1_values.txt",
        pass2_prompt="study_metadata_pass2_provenance.txt",
        order=1,
        wave=0,
        dependencies=[],
        priority=0,  # P0 - Critical
        enabled=is_agent_enabled("study_metadata", default=True),
    ),

    # WAVE 1: Core modules (can run in parallel after Wave 0)
    "arms_design": ExtractionModuleConfig(
        module_id="arms_design",
        instance_type="ArmsDesign",
        display_name="Treatment Arms Design",
        schema_file="arms_design_schema.json",
        pass1_prompt="arms_design_pass1_values.txt",
        pass2_prompt="arms_design_pass2_provenance.txt",
        order=2,
        wave=1,
        dependencies=["study_metadata"],
        priority=0,  # P0 - Critical
        enabled=is_agent_enabled("arms_design", default=True),
    ),

    "endpoints_estimands_sap": ExtractionModuleConfig(
        module_id="endpoints_estimands_sap",
        instance_type="EndpointsEstimandsSAP",
        display_name="Endpoints, Estimands & SAP",
        schema_file="endpoints_estimands_sap_schema.json",
        pass1_prompt="endpoints_estimands_sap_pass1_values.txt",
        pass2_prompt="endpoints_estimands_sap_pass2_provenance.txt",
        order=3,
        wave=1,
        dependencies=["study_metadata"],
        priority=0,  # P0 - Critical
        enabled=is_agent_enabled("endpoints_estimands_sap", default=True),
    ),

    # NOTE: safety_management was a legacy combined module, now replaced by:
    # - adverse_events (AE/SAE definitions, grading, reporting)
    # - safety_decision_points (dose modifications, stopping rules)
    "adverse_events": ExtractionModuleConfig(
        module_id="adverse_events",
        instance_type="AdverseEvents",
        display_name="Adverse Events",
        schema_file="adverse_events_extraction_schema.json",
        pass1_prompt="adverse_events_extraction_pass1_values.txt",
        pass2_prompt="adverse_events_extraction_pass2_provenance.txt",
        order=4,
        wave=1,
        dependencies=["study_metadata"],
        priority=0,  # P0 - Critical
        enabled=is_agent_enabled("adverse_events", default=True),
    ),

    "safety_decision_points": ExtractionModuleConfig(
        module_id="safety_decision_points",
        instance_type="SafetyDecisionPoints",
        display_name="Safety Decision Points",
        schema_file="safety_decision_points_schema.json",
        pass1_prompt="safety_decision_points_pass1_values.txt",
        pass2_prompt="safety_decision_points_pass2_provenance.txt",
        order=5,
        wave=1,
        dependencies=["study_metadata"],
        priority=0,  # P0 - Critical
        enabled=is_agent_enabled("safety_decision_points", default=True),
    ),

    "concomitant_medications": ExtractionModuleConfig(
        module_id="concomitant_medications",
        instance_type="ConcomitantMedications",
        display_name="Concomitant Medications",
        schema_file="concomitant_medications_schema.json",
        pass1_prompt="concomitant_medications_pass1_values.txt",
        pass2_prompt="concomitant_medications_pass2_provenance.txt",
        order=5,
        wave=1,
        dependencies=["study_metadata"],
        priority=1,  # P1 - High
        enabled=is_agent_enabled("concomitant_medications", default=True),
    ),

    "biospecimen_handling": ExtractionModuleConfig(
        module_id="biospecimen_handling",
        instance_type="BiospecimenHandling",
        display_name="Biospecimen Handling",
        schema_file="biospecimen_handling_schema.json",
        pass1_prompt="biospecimen_handling_pass1_values.txt",
        pass2_prompt="biospecimen_handling_pass2_provenance.txt",
        order=6,
        wave=1,
        dependencies=["study_metadata"],
        priority=1,  # P1 - High
        enabled=is_agent_enabled("biospecimen_handling", default=True),
    ),

    "laboratory_specifications": ExtractionModuleConfig(
        module_id="laboratory_specifications",
        instance_type="LaboratorySpecifications",
        display_name="Laboratory Specifications",
        schema_file="laboratory_specifications_schema.json",
        pass1_prompt="laboratory_specifications_pass1_values.txt",
        pass2_prompt="laboratory_specifications_pass2_provenance.txt",
        order=7,
        wave=1,
        dependencies=["study_metadata"],
        priority=1,  # P1 - High
        enabled=is_agent_enabled("laboratory_specifications", default=True),
    ),

    "data_management": ExtractionModuleConfig(
        module_id="data_management",
        instance_type="DataManagement",
        display_name="Data Management",
        schema_file="data_management_schema.json",
        pass1_prompt="data_management_pass1_values.txt",
        pass2_prompt="data_management_pass2_provenance.txt",
        order=8,
        wave=1,
        dependencies=["study_metadata"],
        priority=2,  # P2 - Medium
        enabled=is_agent_enabled("data_management", default=True),
    ),

    "site_operations_logistics": ExtractionModuleConfig(
        module_id="site_operations_logistics",
        instance_type="SiteOperationsLogistics",
        display_name="Site Operations & Logistics",
        schema_file="site_operations_logistics_schema.json",
        pass1_prompt="site_operations_logistics_pass1_values.txt",
        pass2_prompt="site_operations_logistics_pass2_provenance.txt",
        order=9,
        wave=1,
        dependencies=["study_metadata"],
        priority=2,  # P2 - Medium (Operational)
        enabled=is_agent_enabled("site_operations_logistics", default=True),
    ),

    # WAVE 2: Dependent modules (need Wave 1 outputs)
    "quality_management": ExtractionModuleConfig(
        module_id="quality_management",
        instance_type="QualityManagement",
        display_name="Quality Management (Monitoring + RBQM)",
        schema_file="quality_management_schema.json",
        pass1_prompt="quality_management_pass1_values.txt",
        pass2_prompt="quality_management_pass2_provenance.txt",
        order=9,
        wave=2,
        dependencies=["study_metadata", "adverse_events", "safety_decision_points"],
        priority=1,  # P1 - High
        enabled=is_agent_enabled("quality_management", default=True),
    ),

    "withdrawal_procedures": ExtractionModuleConfig(
        module_id="withdrawal_procedures",
        instance_type="WithdrawalProcedures",
        display_name="Withdrawal Procedures",
        schema_file="withdrawal_procedures_schema.json",
        pass1_prompt="withdrawal_procedures_pass1_values.txt",
        pass2_prompt="withdrawal_procedures_pass2_provenance.txt",
        order=10,
        wave=2,
        dependencies=["study_metadata", "adverse_events"],
        priority=2,  # P2 - Medium
        enabled=is_agent_enabled("withdrawal_procedures", default=True),
    ),

    # Oncology-specific modules (Wave 2, P3)
    "imaging_central_reading": ExtractionModuleConfig(
        module_id="imaging_central_reading",
        instance_type="ImagingCentralReading",
        display_name="Imaging & Central Reading",
        schema_file="imaging_central_reading_schema.json",
        pass1_prompt="imaging_central_reading_pass1_values.txt",
        pass2_prompt="imaging_central_reading_pass2_provenance.txt",
        order=11,
        wave=2,
        dependencies=["study_metadata"],
        priority=3,  # P3 - Oncology-specific
        enabled=is_agent_enabled("imaging_central_reading", default=True),
    ),

    "pkpd_sampling": ExtractionModuleConfig(
        module_id="pkpd_sampling",
        instance_type="PKPDSampling",
        display_name="PK/PD Sampling",
        schema_file="pkpd_sampling_schema.json",
        pass1_prompt="pkpd_sampling_pass1_values.txt",
        pass2_prompt="pkpd_sampling_pass2_provenance.txt",
        order=12,
        wave=2,
        dependencies=["study_metadata"],
        priority=3,  # P3 - Specialized
        enabled=is_agent_enabled("pkpd_sampling", default=True),
    ),

    # ICF Content Elements (Wave 1, P1)
    "informed_consent": ExtractionModuleConfig(
        module_id="informed_consent",
        instance_type="InformedConsentElements",
        display_name="Informed Consent Elements",
        schema_file="informed_consent_schema.json",
        pass1_prompt="informed_consent_pass1_values.txt",
        pass2_prompt="informed_consent_pass2_provenance.txt",
        order=13,
        wave=1,
        dependencies=["study_metadata"],
        priority=1,  # P1 - High (ICF template generation)
        enabled=is_agent_enabled("informed_consent", default=True),
    ),

    # PRO/COA Specifications (Wave 1, P1)
    "pro_specifications": ExtractionModuleConfig(
        module_id="pro_specifications",
        instance_type="PROSpecifications",
        display_name="PRO Specifications",
        schema_file="pro_specifications_schema.json",
        pass1_prompt="pro_specifications_pass1_values.txt",
        pass2_prompt="pro_specifications_pass2_provenance.txt",
        order=14,
        wave=1,
        dependencies=["study_metadata", "endpoints_estimands_sap"],
        priority=1,  # P1 - High (ePRO/eCOA configuration)
        enabled=is_agent_enabled("pro_specifications", default=True),
    ),
}


def get_module(module_id: str) -> Optional[ExtractionModuleConfig]:
    """Get module configuration by ID."""
    return EXTRACTION_MODULES.get(module_id)


def get_enabled_modules() -> List[ExtractionModuleConfig]:
    """Get list of enabled modules in execution order."""
    enabled = [m for m in EXTRACTION_MODULES.values() if m.enabled]
    return sorted(enabled, key=lambda m: m.order)


def get_module_ids() -> List[str]:
    """Get list of all module IDs in execution order."""
    return [m.module_id for m in get_enabled_modules()]


def get_total_modules() -> int:
    """Get total number of enabled modules."""
    return len(get_enabled_modules())


def get_modules_by_wave() -> Dict[int, List[ExtractionModuleConfig]]:
    """
    Get enabled modules organized by wave number.

    Returns:
        Dictionary mapping wave number to list of modules,
        sorted by priority and order within each wave.
    """
    waves: Dict[int, List[ExtractionModuleConfig]] = defaultdict(list)
    for module in get_enabled_modules():
        waves[module.wave].append(module)

    # Sort within each wave by priority first, then by order
    for wave_num in waves:
        waves[wave_num].sort(key=lambda m: (m.priority, m.order))

    return dict(sorted(waves.items()))


def get_wave_count() -> int:
    """Get total number of waves."""
    waves = get_modules_by_wave()
    return len(waves) if waves else 0


def get_modules_in_wave(wave: int) -> List[ExtractionModuleConfig]:
    """
    Get all enabled modules in a specific wave.

    Args:
        wave: Wave number (0, 1, 2, etc.)

    Returns:
        List of modules in the wave, sorted by priority and order.
    """
    waves = get_modules_by_wave()
    return waves.get(wave, [])


def get_agent_status_summary() -> str:
    """
    Get a formatted summary of agent enabled/disabled status.

    Returns:
        Formatted string showing all agents grouped by wave with status.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("AGENT CONFIGURATION (from config.yaml)")
    lines.append("=" * 60)

    # Group by wave
    waves_all: Dict[int, List[ExtractionModuleConfig]] = defaultdict(list)
    for module in EXTRACTION_MODULES.values():
        waves_all[module.wave].append(module)

    # Sort within each wave
    for wave_num in sorted(waves_all.keys()):
        modules = sorted(waves_all[wave_num], key=lambda m: (m.priority, m.order))
        lines.append(f"\nWave {wave_num}:")
        lines.append("-" * 40)

        for m in modules:
            status = "✓ ENABLED" if m.enabled else "✗ DISABLED"
            priority_label = f"P{m.priority}"
            lines.append(f"  [{status:12}] {m.module_id:30} ({priority_label})")

    # Summary
    enabled_count = len(get_enabled_modules())
    total_count = len(EXTRACTION_MODULES)
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"TOTAL: {enabled_count}/{total_count} agents enabled")
    lines.append("=" * 60)

    return "\n".join(lines)


def print_agent_status():
    """Print agent status summary to console."""
    print(get_agent_status_summary())


def get_config_yaml_path() -> Path:
    """Get path to config.yaml file."""
    return CONFIG_YAML_PATH
