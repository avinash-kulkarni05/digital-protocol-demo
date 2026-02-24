"""
JSON Schema validation for extracted data.

Validates extraction output against module-specific schemas
for USDM 4.0 compliance.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jsonschema
from jsonschema import Draft7Validator, ValidationError

from app.config import settings
from app.module_registry import get_module

logger = logging.getLogger(__name__)


class SchemaValidator:
    """
    Validates extracted data against JSON schemas.

    Provides detailed validation reports for compliance checking.
    """

    def __init__(self):
        """Initialize validator with schema cache."""
        self._schema_cache: Dict[str, Dict] = {}

    def load_schema(self, module_id: str) -> Dict[str, Any]:
        """
        Load JSON schema for a module.

        Args:
            module_id: Module identifier

        Returns:
            JSON schema dictionary
        """
        if module_id in self._schema_cache:
            return self._schema_cache[module_id]

        module = get_module(module_id)
        if not module:
            raise ValueError(f"Unknown module: {module_id}")

        schema_path = module.get_schema_path()
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema not found: {schema_path}")

        with open(schema_path) as f:
            schema = json.load(f)

        self._schema_cache[module_id] = schema
        return schema

    def validate(
        self,
        data: Dict[str, Any],
        module_id: str,
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Validate data against module schema.

        Args:
            data: Extracted data to validate
            module_id: Module identifier

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        schema = self.load_schema(module_id)

        # Create validator
        validator = Draft7Validator(schema)

        # Collect all errors
        errors = []
        for error in validator.iter_errors(data):
            errors.append(self._format_error(error))

        is_valid = len(errors) == 0
        return is_valid, errors

    def _format_error(self, error: ValidationError) -> Dict[str, Any]:
        """Format validation error for reporting."""
        return {
            "path": ".".join(str(p) for p in error.absolute_path),
            "message": error.message,
            "validator": error.validator,
            "value": str(error.instance)[:100] if error.instance else None,
            "schema_path": ".".join(str(p) for p in error.schema_path),
        }

    def validate_with_auto_fix(
        self,
        data: Dict[str, Any],
        module_id: str,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Validate and attempt to auto-fix common issues.

        Args:
            data: Extracted data to validate
            module_id: Module identifier

        Returns:
            Tuple of (fixed_data, remaining_errors, fixes_applied)
        """
        import copy
        fixed_data = copy.deepcopy(data)
        fixes_applied = []

        # Apply common fixes
        fixes_applied.extend(self._fix_null_values(fixed_data))
        fixes_applied.extend(self._fix_empty_arrays(fixed_data))
        fixes_applied.extend(self._fix_type_coercion(fixed_data))

        # Validate fixed data
        is_valid, errors = self.validate(fixed_data, module_id)

        return fixed_data, errors, fixes_applied

    def _fix_null_values(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Replace null values with appropriate defaults."""
        fixes = []

        def traverse(obj, path=""):
            if isinstance(obj, dict):
                for key, value in list(obj.items()):
                    field_path = f"{path}.{key}" if path else key
                    if value is None:
                        # Remove null values from objects
                        del obj[key]
                        fixes.append({
                            "path": field_path,
                            "fix": "removed_null",
                        })
                    elif isinstance(value, (dict, list)):
                        traverse(value, field_path)

            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    traverse(item, f"{path}[{i}]")

        traverse(data)
        return fixes

    def _fix_empty_arrays(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Remove empty arrays that should not be present."""
        fixes = []
        # No action - empty arrays are often valid
        return fixes

    def _fix_type_coercion(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Coerce types where safe to do so."""
        fixes = []

        def traverse(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    field_path = f"{path}.{key}" if path else key

                    # Coerce page_number to int
                    if key == "page_number" and isinstance(value, str):
                        try:
                            obj[key] = int(value)
                            fixes.append({
                                "path": field_path,
                                "fix": "coerced_to_int",
                                "original": value,
                            })
                        except ValueError:
                            pass

                    # Coerce numeric strings
                    if key.endswith("_percent") and isinstance(value, str):
                        try:
                            obj[key] = float(value.replace("%", ""))
                            fixes.append({
                                "path": field_path,
                                "fix": "coerced_to_float",
                                "original": value,
                            })
                        except ValueError:
                            pass

                    if isinstance(value, (dict, list)):
                        traverse(value, field_path)

            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    traverse(item, f"{path}[{i}]")

        traverse(data)
        return fixes

    def calculate_compliance_score(
        self,
        data: Dict[str, Any],
        module_id: str,
    ) -> Dict[str, Any]:
        """
        Calculate overall schema compliance score.

        Args:
            data: Extracted data
            module_id: Module identifier

        Returns:
            Compliance report with score
        """
        is_valid, errors = self.validate(data, module_id)

        # Count total expected fields from schema
        schema = self.load_schema(module_id)
        expected_fields = self._count_required_fields(schema)

        # Calculate score based on errors
        if expected_fields == 0:
            score = 1.0 if is_valid else 0.0
        else:
            error_penalty = min(len(errors) / expected_fields, 1.0)
            score = 1.0 - error_penalty

        return {
            "module_id": module_id,
            "is_valid": is_valid,
            "compliance_score": round(score, 3),
            "error_count": len(errors),
            "expected_fields": expected_fields,
            "errors": errors[:10],  # First 10 only
        }

    def _count_required_fields(self, schema: Dict[str, Any]) -> int:
        """Count required fields in schema."""
        count = 0

        def traverse(s):
            nonlocal count
            if isinstance(s, dict):
                required = s.get("required", [])
                count += len(required)

                properties = s.get("properties", {})
                for prop in properties.values():
                    traverse(prop)

                items = s.get("items")
                if items:
                    traverse(items)

        traverse(schema)
        return max(count, 1)  # At least 1 to avoid division by zero

    def generate_validation_report(
        self,
        data: Dict[str, Any],
        module_id: str,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive validation report.

        Args:
            data: Extracted data
            module_id: Module identifier

        Returns:
            Full validation report
        """
        # Basic validation
        is_valid, errors = self.validate(data, module_id)

        # Auto-fix attempt
        fixed_data, remaining_errors, fixes = self.validate_with_auto_fix(data, module_id)

        # Compliance scoring
        compliance = self.calculate_compliance_score(fixed_data, module_id)

        return {
            "module_id": module_id,
            "original_valid": is_valid,
            "original_errors": len(errors),
            "auto_fixes_applied": len(fixes),
            "fixes": fixes[:10],
            "post_fix_valid": len(remaining_errors) == 0,
            "remaining_errors": len(remaining_errors),
            "compliance_score": compliance["compliance_score"],
            "detailed_errors": errors[:20],
        }
