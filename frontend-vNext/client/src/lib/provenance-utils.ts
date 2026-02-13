/**
 * Provenance extraction utilities for handling various data patterns in USDM JSON.
 *
 * Two main provenance patterns exist in the extracted data:
 *
 * Pattern 1 (Nested): The provenance is inside the field object
 * { fieldName: { value: "X", provenance: { page_number: 1, text_snippet: "..." } } }
 *
 * Pattern 2 (Sibling): The provenance is a separate key alongside the field
 * { fieldName: "X", fieldName_provenance: { page_number: 1, text_snippet: "..." } }
 *
 * Pattern 3 (Direct object): The object itself contains provenance
 * { fieldName: { code: "C123", decode: "Value", provenance: { ... } } }
 */

/**
 * Extracts provenance from various data patterns.
 *
 * @param data - The parent object containing the field
 * @param fieldName - The name of the field to extract provenance for
 * @returns The provenance object or null if not found
 */
export function extractProvenance(data: any, fieldName: string): any {
  if (!data) return null;

  // Pattern 2: Sibling provenance (fieldName_provenance)
  const siblingKey = `${fieldName}_provenance`;
  if (data[siblingKey]) {
    return data[siblingKey];
  }

  // Pattern 1/3: Nested provenance within the field object
  const field = data[fieldName];
  if (field && typeof field === 'object') {
    return field.provenance || null;
  }

  return null;
}

/**
 * Extracts the actual value from wrapped provenance objects.
 * Handles { value: X } wrapper pattern.
 *
 * @param fieldData - The field data that may be wrapped
 * @returns The unwrapped value
 */
export function extractValue(fieldData: any): any {
  if (fieldData === null || fieldData === undefined) return null;
  if (typeof fieldData !== 'object') return fieldData;
  if ('value' in fieldData) return fieldData.value;
  if ('decode' in fieldData) return fieldData.decode;
  if ('code' in fieldData) return fieldData.code;
  return fieldData;
}

/**
 * Extracts display value from Code objects or simple values.
 * Prefers decode over code for display.
 *
 * @param fieldData - The field data (could be Code object or primitive)
 * @returns String representation for display
 */
export function extractDisplayValue(fieldData: any): string {
  if (fieldData === null || fieldData === undefined) return '';
  if (typeof fieldData !== 'object') return String(fieldData);
  if (fieldData.decode) return fieldData.decode;
  if (fieldData.value) return String(fieldData.value);
  if (fieldData.code) return fieldData.code;
  return '';
}

/**
 * Combined helper for rendering fields with provenance.
 * Returns both the value and its associated provenance.
 *
 * @param data - The parent object containing the field
 * @param fieldName - The name of the field
 * @returns Object with value and provenance
 */
export function getFieldWithProvenance(data: any, fieldName: string): {
  value: any;
  displayValue: string;
  provenance: any;
} {
  const fieldData = data?.[fieldName];
  return {
    value: extractValue(fieldData),
    displayValue: extractDisplayValue(fieldData),
    provenance: extractProvenance(data, fieldName)
  };
}

/**
 * Extracts provenance from an object that may have provenance at different levels.
 * Useful for objects where provenance could be at root or nested.
 *
 * @param obj - The object to extract provenance from
 * @returns The provenance object or null
 */
export function getObjectProvenance(obj: any): any {
  if (!obj || typeof obj !== 'object') return null;

  // Direct provenance on object
  if (obj.provenance) {
    return obj.provenance;
  }

  // Check for explicit provenance pattern
  if (obj.explicit?.page_number) {
    return obj;
  }

  return null;
}

/**
 * Checks if an object has valid provenance with a page number.
 *
 * @param provenance - The provenance object to check
 * @returns true if provenance has a valid page number
 */
export function hasValidProvenance(provenance: any): boolean {
  if (!provenance) return false;
  const pageNum = provenance.explicit?.page_number || provenance.page_number;
  return typeof pageNum === 'number' && pageNum > 0;
}
