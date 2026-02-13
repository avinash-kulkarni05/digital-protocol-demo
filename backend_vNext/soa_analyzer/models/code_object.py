"""
USDM 4.0 Code Object Model

Implements the 6-field Code object structure required by USDM 4.0 specification.

Current Problem:
    SOA outputs use simple {code, decode} pairs which don't conform to USDM 4.0.

Required USDM 4.0 Structure:
    {
        "id": "CODE-001",
        "code": "C48262",
        "decode": "Screening",
        "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
        "codeSystemVersion": "24.12",
        "instanceType": "Code"
    }

Usage:
    from soa_analyzer.models.code_object import CodeObject, expand_to_usdm_code

    # Create from simple pair
    code = CodeObject.from_simple_pair("C48262", "Screening")

    # Or expand existing dict
    usdm_code = expand_to_usdm_code({"code": "C48262", "decode": "Screening"})
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid


# NCI EVS Code Systems
NCI_EVS_CODE_SYSTEM = "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"
NCI_EVS_VERSION = "24.12"

# CDISC CT Code Systems by domain
CDISC_CODE_SYSTEMS = {
    "SDTM": "http://www.cdisc.org/ns/sdtm",
    "CDASH": "http://www.cdisc.org/ns/cdash",
    "SEND": "http://www.cdisc.org/ns/send",
    "ADAM": "http://www.cdisc.org/ns/adam",
    "PROTOCOL": "http://www.cdisc.org/ns/protocol",
}


@dataclass
class CodeObject:
    """
    USDM 4.0 compliant Code object.

    All CDISC coded values must use this 6-field structure.
    """
    id: str
    code: str
    decode: str
    codeSystem: str = NCI_EVS_CODE_SYSTEM
    codeSystemVersion: str = NCI_EVS_VERSION
    instanceType: str = "Code"

    @classmethod
    def from_simple_pair(
        cls,
        code: str,
        decode: str,
        id_prefix: str = "CODE",
        code_system: Optional[str] = None,
        code_system_version: Optional[str] = None,
    ) -> "CodeObject":
        """
        Create CodeObject from simple code/decode pair.

        Args:
            code: CDISC NCI code (e.g., C48262)
            decode: Human-readable decode (e.g., Screening)
            id_prefix: Prefix for generated ID
            code_system: Override default NCI EVS code system
            code_system_version: Override default version

        Returns:
            USDM 4.0 compliant CodeObject
        """
        return cls(
            id=f"{id_prefix}-{uuid.uuid4().hex[:8].upper()}",
            code=code,
            decode=decode,
            codeSystem=code_system or NCI_EVS_CODE_SYSTEM,
            codeSystemVersion=code_system_version or NCI_EVS_VERSION,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any], id_prefix: str = "CODE") -> "CodeObject":
        """
        Create CodeObject from dictionary.

        Handles both simple pairs and full USDM format.

        Args:
            data: Dictionary with code/decode or full USDM structure
            id_prefix: Prefix for generated ID if missing

        Returns:
            USDM 4.0 compliant CodeObject
        """
        if not data:
            raise ValueError("Cannot create CodeObject from empty data")

        # Check if already USDM compliant
        if "instanceType" in data and data.get("instanceType") == "Code":
            return cls(
                id=data.get("id", f"{id_prefix}-{uuid.uuid4().hex[:8].upper()}"),
                code=data["code"],
                decode=data["decode"],
                codeSystem=data.get("codeSystem", NCI_EVS_CODE_SYSTEM),
                codeSystemVersion=data.get("codeSystemVersion", NCI_EVS_VERSION),
            )

        # Simple pair format
        code = data.get("code") or data.get("cdisc_code") or data.get("cdiscCode")
        decode = data.get("decode") or data.get("cdisc_decode") or data.get("cdiscDecode") or data.get("cdisc_name")

        if not code or not decode:
            raise ValueError(f"Cannot extract code/decode from data: {data}")

        return cls.from_simple_pair(code, decode, id_prefix)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to USDM 4.0 compliant dictionary."""
        return {
            "id": self.id,
            "code": self.code,
            "decode": self.decode,
            "codeSystem": self.codeSystem,
            "codeSystemVersion": self.codeSystemVersion,
            "instanceType": self.instanceType,
        }


def expand_to_usdm_code(
    data: Dict[str, Any],
    id_prefix: str = "CODE",
    allow_null: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Expand simple code/decode pair to USDM 4.0 Code object.

    Args:
        data: Dictionary with code/decode pair
        id_prefix: Prefix for generated ID
        allow_null: Return None instead of raising error for invalid input

    Returns:
        USDM 4.0 compliant Code dictionary, or None if invalid and allow_null=True

    Example:
        # Input
        {"code": "C48262", "decode": "Screening"}

        # Output
        {
            "id": "CODE-A1B2C3D4",
            "code": "C48262",
            "decode": "Screening",
            "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
            "codeSystemVersion": "24.12",
            "instanceType": "Code"
        }
    """
    if not data:
        return None if allow_null else {}

    # Already USDM compliant
    if data.get("instanceType") == "Code" and "codeSystem" in data:
        return data

    try:
        code_obj = CodeObject.from_dict(data, id_prefix)
        return code_obj.to_dict()
    except (ValueError, KeyError):
        if allow_null:
            return None
        return data


def is_usdm_compliant_code(data: Dict[str, Any]) -> bool:
    """
    Check if a code object is USDM 4.0 compliant.

    Required fields: id, code, decode, codeSystem, codeSystemVersion, instanceType
    """
    if not isinstance(data, dict):
        return False

    required_fields = {"id", "code", "decode", "codeSystem", "codeSystemVersion", "instanceType"}
    return all(field in data for field in required_fields) and data.get("instanceType") == "Code"


# Common CDISC codes for SOA entities
ENCOUNTER_TYPE_CODES = {
    "Screening": {"code": "C48262", "decode": "Screening"},
    "Run-In": {"code": "C98779", "decode": "Run-In"},
    "Treatment": {"code": "C25100", "decode": "Treatment"},
    "Follow-up": {"code": "C16033", "decode": "Follow-up"},
    "Early Termination": {"code": "C25629", "decode": "Early Termination"},
    "End of Treatment": {"code": "C25629", "decode": "End of Treatment"},
    "End of Study": {"code": "C25254", "decode": "End of Study"},
    "Unscheduled": {"code": "C102090", "decode": "Unscheduled Visit"},
}

TIMING_TYPE_CODES = {
    "Study Day": {"code": "C83095", "decode": "Study Day"},
    "Calendar Day": {"code": "C25155", "decode": "Day"},
    "Week": {"code": "C29844", "decode": "Week"},
    "Month": {"code": "C29846", "decode": "Month"},
    "Cycle": {"code": "C94535", "decode": "Cycle"},
}

TIMING_REFERENCE_CODES = {
    "Screening": {"code": "C48262", "decode": "Screening"},
    "Baseline": {"code": "C25213", "decode": "Baseline"},
    "Randomization": {"code": "C25196", "decode": "Randomization"},
    "First Dose": {"code": "C71148", "decode": "First Treatment"},
    "Last Dose": {"code": "C71149", "decode": "Last Treatment"},
}
