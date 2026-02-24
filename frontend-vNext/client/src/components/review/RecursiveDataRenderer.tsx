import { DataCard } from "./DataCard";

type ReviewStatus = "pending" | "approved" | "rejected" | "flagged";

interface ProvenanceInfo {
  page_number?: number;
  section_number?: string;
  text_snippet?: string;
}

interface ControlTerminology {
  code: string;
  decode: string;
  system: string;
  version: string;
}

interface RecursiveDataRendererProps {
  data: any;
  path?: string;
  onViewSource?: (page: number) => void;
  onStatusChange?: (reviewId: number, status: ReviewStatus) => void;
  depth?: number;
  excludeKeys?: string[];
  parentProvenance?: ProvenanceInfo;
}

const EXCLUDED_KEYS = ['instanceType', '$schema', 'schemaVersion', 'provenance', 'id', 'codeSystem', 'codeSystemVersion'];

function extractProvenance(obj: any): ProvenanceInfo | undefined {
  if (!obj) return undefined;
  if (obj.provenance) {
    return {
      page_number: obj.provenance.page_number,
      section_number: obj.provenance.section_number,
      text_snippet: obj.provenance.text_snippet
    };
  }
  return undefined;
}

function extractControlTerminology(obj: any): ControlTerminology | undefined {
  if (!obj) return undefined;
  if (obj.code && obj.decode) {
    return {
      code: obj.code,
      decode: obj.decode,
      system: obj.codeSystem || 'N/A',
      version: obj.codeSystemVersion || 'N/A'
    };
  }
  return undefined;
}

function formatLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, str => str.toUpperCase())
    .trim();
}

function isCodedValue(value: any): boolean {
  return typeof value === 'object' && value !== null && 'code' in value && 'decode' in value;
}

function isObjectWithValues(value: any): boolean {
  return typeof value === 'object' && value !== null && 'values' in value && Array.isArray(value.values);
}

function isSimpleNestedObject(value: any): boolean {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const keys = Object.keys(value).filter(k => !EXCLUDED_KEYS.includes(k));
  if (keys.length === 0) return false;
  if (keys.length > 4) return false;
  return keys.every(k => {
    const v = value[k];
    return v === null || v === undefined || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean';
  });
}

function formatSimpleNestedObject(value: any): string {
  if (!value || typeof value !== 'object') return 'Not specified';
  const keys = Object.keys(value).filter(k => !EXCLUDED_KEYS.includes(k));
  const parts: string[] = [];
  for (const k of keys) {
    const v = value[k];
    if (v === null || v === undefined) continue;
    if (typeof v === 'boolean') {
      if (v) parts.push(formatLabel(k));
    } else {
      parts.push(`${v}`);
    }
  }
  return parts.length > 0 ? parts.join(' ') : 'Not specified';
}

function formatValue(value: any): string {
  if (value === null || value === undefined) return 'Not specified';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return value.toString();
  if (typeof value === 'string') return value || 'Not specified';
  
  if (Array.isArray(value)) {
    if (value.length === 0) return 'None';
    if (value.every(v => typeof v === 'string' || typeof v === 'number')) {
      return value.join(', ');
    }
    if (value.every(v => isCodedValue(v))) {
      return value.map(v => v.decode).join(', ');
    }
    return `${value.length} items`;
  }
  
  if (typeof value === 'object') {
    if (isCodedValue(value)) return value.decode;
    if (value.value !== undefined) return String(value.value);
    if (value.name) return value.name;
    if (value.text) return value.text;
    if (value.description) return value.description;
    if (value.versionNumber) return `v${value.versionNumber}${value.versionDate ? ` (${value.versionDate})` : ''}`;
    if (isSimpleNestedObject(value)) return formatSimpleNestedObject(value);
    
    const keys = Object.keys(value).filter(k => !EXCLUDED_KEYS.includes(k));
    if (keys.length <= 3) {
      const parts = keys.map(k => {
        const v = value[k];
        if (v === null || v === undefined) return null;
        if (typeof v === 'boolean') return v ? formatLabel(k) : null;
        if (typeof v === 'string' || typeof v === 'number') return `${formatLabel(k)}: ${v}`;
        return null;
      }).filter(Boolean);
      if (parts.length > 0) return parts.join(', ');
    }
    return 'See details';
  }
  return String(value);
}

function isSimpleValue(value: any): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return true;
  if (Array.isArray(value) && value.every(v => typeof v === 'string' || typeof v === 'number')) return true;
  if (isCodedValue(value)) return true;
  if (isSimpleNestedObject(value)) return true;
  return false;
}

function isArrayOfObjects(value: any): boolean {
  if (!Array.isArray(value) || value.length === 0) return false;
  if (value.every(v => typeof v === 'string' || typeof v === 'number')) return false;
  if (value.every(v => isCodedValue(v))) return false;
  return typeof value[0] === 'object';
}

function isComplexObject(value: any): boolean {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  if (isCodedValue(value)) return false;
  if (isSimpleNestedObject(value)) return false;
  return true;
}

function ValuesListCard({ 
  label, 
  values, 
  provenance, 
  onViewSource 
}: { 
  label: string; 
  values: string[]; 
  provenance?: { page: number; text: string };
  onViewSource?: (page: number) => void;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
      <div className="flex items-start justify-between mb-3">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
        {provenance && (
          <button
            onClick={() => onViewSource?.(provenance.page)}
            className="text-xs text-gray-900 hover:text-gray-700 flex items-center gap-1"
          >
            Page {provenance.page}
          </button>
        )}
      </div>
      <ul className="space-y-2">
        {values.map((item, idx) => (
          <li key={idx} className="flex items-start gap-2 text-sm text-foreground">
            <span className="text-gray-600 mt-1">•</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RecursiveDataRenderer({
  data,
  path = '',
  onViewSource,
  onStatusChange,
  depth = 0,
  excludeKeys = EXCLUDED_KEYS,
  parentProvenance
}: RecursiveDataRendererProps) {
  if (!data || typeof data !== 'object') {
    return null;
  }

  const entries = Object.entries(data).filter(([key]) => !excludeKeys.includes(key));

  if (entries.length === 0) {
    return null;
  }

  const simpleFields: [string, any][] = [];
  const complexFields: [string, any][] = [];
  const arrayFields: [string, any[]][] = [];
  const valuesListFields: [string, { values: string[]; provenance?: ProvenanceInfo }][] = [];

  for (const [key, value] of entries) {
    if (isObjectWithValues(value)) {
      const obj = value as { values: any[]; provenance?: any };
      if (obj.values.every((v: any) => typeof v === 'string')) {
        valuesListFields.push([key, { values: obj.values, provenance: extractProvenance(value) }]);
      } else {
        complexFields.push([key, value]);
      }
    } else if (isSimpleValue(value)) {
      simpleFields.push([key, value]);
    } else if (isArrayOfObjects(value)) {
      arrayFields.push([key, value as any[]]);
    } else if (isComplexObject(value)) {
      complexFields.push([key, value]);
    }
  }

  const ownProvenance = extractProvenance(data);
  const provenance = ownProvenance || parentProvenance;

  return (
    <div className="space-y-4">
      {simpleFields.length > 0 && (
        <div className={`grid grid-cols-1 ${simpleFields.length > 1 ? 'md:grid-cols-2' : ''} gap-4`}>
          {simpleFields.map(([key, value]) => {
            const fieldProv = typeof value === 'object' && value !== null ? extractProvenance(value) : undefined;
            const itemProvenance = fieldProv || provenance;
            const ct = extractControlTerminology(value);
            return (
              <DataCard
                key={`${path}-${key}`}
                label={formatLabel(key)}
                value={formatValue(value)}
                provenance={itemProvenance?.page_number && itemProvenance?.text_snippet ? { page: itemProvenance.page_number, text: itemProvenance.text_snippet } : undefined}
                controlTerminology={ct}
                onViewSource={onViewSource}
              />
            );
          })}
        </div>
      )}

      {valuesListFields.map(([key, { values, provenance: listProv }]) => (
        <ValuesListCard
          key={`${path}-${key}`}
          label={formatLabel(key)}
          values={values}
          provenance={listProv?.page_number ? { page: listProv.page_number, text: listProv.text_snippet || '' } : undefined}
          onViewSource={onViewSource}
        />
      ))}

      {arrayFields.map(([key, items]) => (
        <div key={`${path}-${key}`} className="space-y-4 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">{formatLabel(key)}</h3>
            <span className="text-xs text-muted-foreground">({items.length} items)</span>
            <div className="h-px bg-gray-200 flex-1" />
          </div>
          <div className="grid grid-cols-1 gap-4">
            {items.map((item, index) => {
              const itemProvenance = extractProvenance(item);
              const ct = extractControlTerminology(item) || extractControlTerminology(item.type) || extractControlTerminology(item.level);
              
              // Special handling for identifier-like objects (have id and scopeId)
              if (item.id && item.scopeId) {
                const labelText = formatLabel(item.scopeId);
                return (
                  <DataCard
                    key={`${path}-${key}-${index}`}
                    label={labelText}
                    value={item.id}
                    provenance={itemProvenance?.page_number && itemProvenance?.text_snippet ? { page: itemProvenance.page_number, text: itemProvenance.text_snippet } : undefined}
                    controlTerminology={ct}
                    onViewSource={onViewSource}
                  />
                );
              }
              
              // Special handling for version objects
              if (item.versionNumber !== undefined) {
                return (
                  <DataCard
                    key={`${path}-${key}-${index}`}
                    label={`Version ${item.versionNumber}`}
                    value={item.versionDate || 'Date not specified'}
                    provenance={itemProvenance?.page_number && itemProvenance?.text_snippet ? { page: itemProvenance.page_number, text: itemProvenance.text_snippet } : undefined}
                    onViewSource={onViewSource}
                  />
                );
              }
              
              const itemLabel = item.name || item.label || item.text || item.id || `Item ${index + 1}`;
              
              // Get all displayable keys (exclude metadata keys but keep id for display)
              const displayKeys = Object.keys(item).filter(k => 
                !['instanceType', '$schema', 'schemaVersion', 'provenance', 'codeSystem', 'codeSystemVersion', 'name', 'label'].includes(k)
              );
              
              if (displayKeys.length > 4 || displayKeys.some(k => typeof item[k] === 'object' && item[k] !== null && !isCodedValue(item[k]) && !isSimpleNestedObject(item[k]))) {
                return (
                  <div key={`${path}-${key}-${index}`} className="border border-gray-200 rounded-lg p-4 bg-white">
                    <h4 className="font-semibold text-foreground mb-3">{formatValue(itemLabel)}</h4>
                    <RecursiveDataRenderer
                      data={item}
                      path={`${path}-${key}-${index}`}
                      onViewSource={onViewSource}
                      onStatusChange={onStatusChange}
                      depth={depth + 1}
                      excludeKeys={[...excludeKeys, 'name', 'label']}
                      parentProvenance={provenance}
                    />
                  </div>
                );
              }
              
              const displayValue = displayKeys
                .filter(k => k !== 'id' || !item.name)
                .map(k => {
                  const v = item[k];
                  return formatValue(v);
                })
                .filter(v => v && v !== 'Not specified' && v !== 'See details')
                .join(' | ') || formatValue(item);
              
              return (
                <DataCard
                  key={`${path}-${key}-${index}`}
                  label={formatValue(itemLabel)}
                  value={displayValue}
                  provenance={itemProvenance?.page_number && itemProvenance?.text_snippet ? { page: itemProvenance.page_number, text: itemProvenance.text_snippet } : undefined}
                  controlTerminology={ct}
                  onViewSource={onViewSource}
                />
              );
            })}
          </div>
        </div>
      ))}

      {complexFields.map(([key, value]) => (
        <div key={`${path}-${key}`} className="space-y-4 pt-4">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">{formatLabel(key)}</h3>
            <div className="h-px bg-gray-200 flex-1" />
          </div>
          <div className="pl-0">
            <RecursiveDataRenderer
              data={value}
              path={`${path}-${key}`}
              onViewSource={onViewSource}
              onStatusChange={onStatusChange}
              depth={depth + 1}
              parentProvenance={provenance}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SectionRenderer({
  title,
  description,
  data,
  onViewSource,
}: {
  title: string;
  description: string;
  data: any;
  onViewSource?: (page: number) => void;
}) {
  return (
    <div className="space-y-6">
      <RecursiveDataRenderer
        data={data}
        onViewSource={onViewSource}
      />
    </div>
  );
}
