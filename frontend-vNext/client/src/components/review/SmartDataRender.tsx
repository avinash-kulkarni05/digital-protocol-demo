import { useState, useRef, useEffect } from "react";
import { FileText, Check, X, Pencil, AlertTriangle, ChevronDown } from "lucide-react";
import { useCoverageRegistry } from "@/lib/coverage-registry";
import { motion, AnimatePresence } from "framer-motion";

interface SmartDataRenderProps {
  data: any;
  onViewSource?: (page: number) => void;
  onDataChange?: (path: string[], newValue: any) => void;
  editable?: boolean;
  basePath?: string;
  excludeFields?: string[];
}

function formatKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

function getPageNumber(obj: any): number | null {
  if (!obj || typeof obj !== 'object') return null;
  
  if (obj.provenance) {
    const prov = obj.provenance;
    return prov.explicit?.page_number || prov.page_number || null;
  }
  
  return null;
}

function EditableText({ 
  value, 
  onSave,
  multiline = false
}: { 
  value: string; 
  onSave: (newValue: string) => void;
  multiline?: boolean;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value);
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSave = () => {
    onSave(editValue);
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditValue(value);
    setIsEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      handleCancel();
    }
  };

  if (isEditing) {
    return (
      <div className="flex items-start gap-2">
        {multiline ? (
          <textarea
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 px-2 py-1 text-sm border border-gray-400 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-700 min-h-[60px] resize-y"
            data-testid="inline-edit-textarea"
          />
        ) : (
          <input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 px-2 py-1 text-sm border border-gray-400 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-700"
            data-testid="inline-edit-input"
          />
        )}
        <button
          onClick={handleSave}
          className="p-1 text-gray-800 hover:bg-gray-100 rounded"
          data-testid="inline-edit-save"
        >
          <Check className="w-4 h-4" />
        </button>
        <button
          onClick={handleCancel}
          className="p-1 text-gray-600 hover:bg-gray-100 rounded"
          data-testid="inline-edit-cancel"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <span
      onDoubleClick={() => setIsEditing(true)}
      className="text-gray-700 cursor-text hover:bg-yellow-50 hover:outline hover:outline-1 hover:outline-yellow-300 rounded px-0.5 -mx-0.5 inline-block group relative"
      title="Double-click to edit"
      data-testid="editable-text"
    >
      {value || <span className="text-gray-400 italic">Not specified</span>}
      <Pencil className="w-3 h-3 text-gray-400 inline-block ml-1 opacity-0 group-hover:opacity-100 transition-opacity" />
    </span>
  );
}

function EditableNumber({ 
  value, 
  onSave 
}: { 
  value: number; 
  onSave: (newValue: number) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(String(value));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSave = () => {
    const num = parseFloat(editValue);
    if (!isNaN(num)) {
      onSave(num);
    }
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditValue(String(value));
    setIsEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSave();
    } else if (e.key === 'Escape') {
      handleCancel();
    }
  };

  if (isEditing) {
    return (
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="number"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          className="w-24 px-2 py-1 text-sm border border-gray-400 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-700"
          data-testid="inline-edit-number"
        />
        <button onClick={handleSave} className="p-1 text-gray-800 hover:bg-gray-100 rounded">
          <Check className="w-4 h-4" />
        </button>
        <button onClick={handleCancel} className="p-1 text-gray-600 hover:bg-gray-100 rounded">
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <span
      onDoubleClick={() => setIsEditing(true)}
      className="text-gray-700 font-medium cursor-text hover:bg-yellow-50 hover:outline hover:outline-1 hover:outline-yellow-300 rounded px-0.5 -mx-0.5 inline-block group"
      title="Double-click to edit"
    >
      {value}
      <Pencil className="w-3 h-3 text-gray-400 inline-block ml-1 opacity-0 group-hover:opacity-100 transition-opacity" />
    </span>
  );
}

function EditableBoolean({ 
  value, 
  onSave 
}: { 
  value: boolean; 
  onSave: (newValue: boolean) => void;
}) {
  return (
    <button
      onClick={() => onSave(!value)}
      className="text-gray-700 font-medium cursor-pointer hover:bg-yellow-50 hover:outline hover:outline-1 hover:outline-yellow-300 rounded px-1 inline-flex items-center gap-1 group"
      title="Click to toggle"
      data-testid="editable-boolean"
    >
      {String(value)}
      <Pencil className="w-3 h-3 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
    </button>
  );
}

function ProvenanceChip({
  pageNumber,
  onViewSource
}: {
  pageNumber: number | null;
  onViewSource?: (page: number) => void;
}) {
  if (!pageNumber || !onViewSource) return null;

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onViewSource(pageNumber);
      }}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded ml-2"
    >
      <FileText className="w-2.5 h-2.5" /> p. {pageNumber}
    </button>
  );
}

function ClickableWrapper({
  children,
  pageNumber,
  onViewSource,
  className = "",
  showInlineChip = false
}: {
  children: React.ReactNode;
  pageNumber: number | null;
  onViewSource?: (page: number) => void;
  className?: string;
  showInlineChip?: boolean;
}) {
  if (!pageNumber || !onViewSource) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div
      className={`${className} relative group`}
    >
      {children}
      {!showInlineChip && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onViewSource(pageNumber);
          }}
          className="absolute top-2 right-2 inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium text-gray-800 bg-gray-100 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <FileText className="w-2.5 h-2.5" /> p. {pageNumber}
        </button>
      )}
    </div>
  );
}

function RenderValue({ 
  value, 
  path = [],
  depth = 0, 
  onViewSource,
  onDataChange,
  editable = true
}: { 
  value: any;
  path?: string[];
  depth?: number;
  onViewSource?: (page: number) => void;
  onDataChange?: (path: string[], newValue: any) => void;
  editable?: boolean;
}): React.ReactNode {
  if (value === null || value === undefined) {
    if (editable && onDataChange) {
      return (
        <EditableText 
          value="" 
          onSave={(newVal) => onDataChange(path, newVal || null)} 
        />
      );
    }
    return <span className="text-gray-400 italic">Not specified</span>;
  }
  
  if (typeof value === 'string') {
    if (editable && onDataChange) {
      const isLong = value.length > 100;
      return (
        <EditableText 
          value={value} 
          onSave={(newVal) => onDataChange(path, newVal)} 
          multiline={isLong}
        />
      );
    }
    if (value.length === 0) return <span className="text-gray-400 italic">Not specified</span>;
    return <span className="text-gray-700">{value}</span>;
  }
  
  if (typeof value === 'number') {
    if (editable && onDataChange) {
      return (
        <EditableNumber 
          value={value} 
          onSave={(newVal) => onDataChange(path, newVal)} 
        />
      );
    }
    return <span className="text-gray-700 font-medium">{String(value)}</span>;
  }
  
  if (typeof value === 'boolean') {
    if (editable && onDataChange) {
      return (
        <EditableBoolean 
          value={value} 
          onSave={(newVal) => onDataChange(path, newVal)} 
        />
      );
    }
    return <span className="text-gray-700 font-medium">{String(value)}</span>;
  }
  
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-gray-400 italic">None</span>;
    }
    
    const allStrings = value.every(item => typeof item === 'string');
    if (allStrings) {
      return (
        <ul className="space-y-1.5">
          {value.map((item, idx) => (
            <li key={idx} className="flex items-start gap-2 text-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 mt-1.5 flex-shrink-0" />
              {editable && onDataChange ? (
                <EditableText 
                  value={item} 
                  onSave={(newVal) => {
                    const newArray = [...value];
                    newArray[idx] = newVal;
                    onDataChange(path, newArray);
                  }} 
                />
              ) : (
                <span className="text-gray-700">{item}</span>
              )}
            </li>
          ))}
        </ul>
      );
    }
    
    return (
      <div className="space-y-3">
        {value.map((item, idx) => {
          const pageNum = getPageNumber(item);
          return (
            <ClickableWrapper
              key={idx}
              pageNumber={pageNum}
              onViewSource={onViewSource}
              className="bg-gray-50/50 rounded-lg p-3 border border-gray-100"
            >
              <RenderValue 
                value={item} 
                path={[...path, String(idx)]}
                depth={depth + 1} 
                onViewSource={onViewSource}
                onDataChange={onDataChange}
                editable={editable}
              />
            </ClickableWrapper>
          );
        })}
      </div>
    );
  }
  
  if (typeof value === 'object') {
    const entries = Object.entries(value).filter(([key]) =>
      key !== 'provenance' && key !== 'section_number' && key !== 'text_snippet' &&
      !key.endsWith('_provenance') // Also filter out sibling provenance keys
    );

    // Get provenance for this object to show inline
    const objectPageNum = getPageNumber(value);

    // Helper to get sibling provenance for a key
    const getSiblingProvenance = (key: string): number | null => {
      const siblingKey = `${key}_provenance`;
      const siblingProv = value[siblingKey];
      if (siblingProv) {
        return siblingProv.explicit?.page_number || siblingProv.page_number || null;
      }
      return null;
    };

    if (entries.length === 0) {
      // Even if no other entries, show provenance if available
      if (objectPageNum && onViewSource) {
        return (
          <span className="text-gray-400 italic">
            No details available
            <ProvenanceChip pageNumber={objectPageNum} onViewSource={onViewSource} />
          </span>
        );
      }
      return <span className="text-gray-400 italic">No details available</span>;
    }

    return (
      <div className={`space-y-3 ${depth > 0 ? '' : ''}`}>
        {entries.map(([key, val]) => {
          const isComplex = typeof val === 'object' && val !== null;
          const isArray = Array.isArray(val);
          const nestedPageNum = isComplex && !isArray ? getPageNumber(val) : null;
          // Check for sibling provenance for primitive values
          const siblingPageNum = !isComplex ? getSiblingProvenance(key) : null;
          const effectivePageNum = nestedPageNum || siblingPageNum;

          if (isComplex && !isArray) {
            return (
              <ClickableWrapper
                key={key}
                pageNumber={nestedPageNum}
                onViewSource={onViewSource}
                className="bg-gray-50/50 rounded-lg p-3 border border-gray-100"
                showInlineChip={true}
              >
                <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1 flex items-center">
                  {formatKey(key)}
                  <ProvenanceChip pageNumber={nestedPageNum} onViewSource={onViewSource} />
                </div>
                <div>
                  <RenderValue
                    value={val}
                    path={[...path, key]}
                    depth={depth + 1}
                    onViewSource={onViewSource}
                    onDataChange={onDataChange}
                    editable={editable}
                  />
                </div>
              </ClickableWrapper>
            );
          }

          return (
            <div key={key}>
              <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1 flex items-center gap-2">
                {formatKey(key)}
                {effectivePageNum && <ProvenanceChip pageNumber={effectivePageNum} onViewSource={onViewSource} />}
              </div>
              <div className={isArray ? "mt-2" : ""}>
                <RenderValue
                  value={val}
                  path={[...path, key]}
                  depth={depth + 1}
                  onViewSource={onViewSource}
                  onDataChange={onDataChange}
                  editable={editable}
                />
              </div>
            </div>
          );
        })}
      </div>
    );
  }
  
  return <span className="text-gray-700">{String(value)}</span>;
}

export function SmartDataRender({ data, onViewSource, onDataChange, editable = true, basePath, excludeFields = [] }: SmartDataRenderProps) {
  const registry = useCoverageRegistry();

  useEffect(() => {
    if (registry && basePath) {
      registry.markRendered(basePath);
    }
  }, [registry, basePath]);

  if (!data) {
    return <span className="text-gray-400 italic">No data available</span>;
  }

  let parsedData = data;

  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data);
      if (typeof parsed === 'object' && parsed !== null) {
        parsedData = parsed;
      } else {
        return <p className="text-sm text-gray-700">{data}</p>;
      }
    } catch {
      return <p className="text-sm text-gray-700">{data}</p>;
    }
  }

  // Filter out excluded fields if any
  if (excludeFields.length > 0 && typeof parsedData === 'object' && parsedData !== null && !Array.isArray(parsedData)) {
    parsedData = Object.fromEntries(
      Object.entries(parsedData).filter(([key]) => !excludeFields.includes(key))
    );
  }

  const topLevelPageNum = getPageNumber(parsedData);
  
  return (
    <div className="space-y-4">
      {topLevelPageNum && onViewSource && (
        <div className="flex justify-end">
          <button 
            onClick={() => onViewSource(topLevelPageNum)} 
            className="inline-flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
          >
            <FileText className="w-3 h-3" /> p. {topLevelPageNum}
          </button>
        </div>
      )}
      <div className="text-sm">
        <RenderValue 
          value={parsedData} 
          path={[]}
          depth={0} 
          onViewSource={onViewSource}
          onDataChange={onDataChange}
          editable={editable}
        />
      </div>
    </div>
  );
}

export function UnmappedDataSection({ onViewSource }: { onViewSource?: (page: number) => void }) {
  const registry = useCoverageRegistry();
  const [isExpanded, setIsExpanded] = useState(false);
  
  if (!registry) return null;
  
  const unrenderedData = registry.getUnrenderedData();
  const unrenderedKeys = Object.keys(unrenderedData);
  
  if (unrenderedKeys.length === 0) return null;
  
  const stats = registry.getCoverageStats();
  
  return (
    <div className="mt-6 border-2 border-gray-400 bg-gray-50 rounded-xl overflow-hidden" data-testid="unmapped-data-section">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-100 transition-colors text-left"
        data-testid="unmapped-data-toggle"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gray-200 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-gray-700" />
          </div>
          <div>
            <span className="font-semibold text-gray-900">Additional Data ({unrenderedKeys.length} fields)</span>
            <p className="text-sm text-gray-700">
              Coverage: {stats.percentage}% ({stats.rendered} of {stats.total} paths)
            </p>
          </div>
        </div>
        <motion.div animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown className="w-5 h-5 text-gray-700" />
        </motion.div>
      </button>
      
      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="px-4 pb-4 border-t border-gray-300 pt-3 space-y-4">
              <p className="text-sm text-gray-800 mb-4">
                The following data exists in the source JSON but may not be explicitly displayed above:
              </p>
              {unrenderedKeys.map((key) => (
                <div key={key} className="bg-white rounded-lg p-4 border border-gray-300">
                  <div className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2">
                    {key.replace(/_/g, ' ')}
                  </div>
                  <SmartDataRender 
                    data={unrenderedData[key]} 
                    onViewSource={onViewSource}
                    basePath={key}
                  />
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function CoverageIndicator() {
  const registry = useCoverageRegistry();
  
  if (!registry) return null;
  
  const stats = registry.getCoverageStats();
  const unrenderedPaths = registry.getUnrenderedPaths();
  
  const bgColor = stats.percentage === 100 
    ? 'bg-gray-100 border-gray-400' 
    : stats.percentage >= 80 
      ? 'bg-gray-100 border-gray-400' 
      : 'bg-gray-100 border-gray-400';
  
  const textColor = stats.percentage === 100 
    ? 'text-gray-900' 
    : stats.percentage >= 80 
      ? 'text-gray-700' 
      : 'text-gray-600';
  
  return (
    <div className={`fixed bottom-4 right-4 ${bgColor} border rounded-lg p-3 shadow-lg z-50 max-w-xs`} data-testid="coverage-indicator">
      <div className={`text-sm font-semibold ${textColor}`}>
        Coverage: {stats.percentage}%
      </div>
      <div className="text-xs text-gray-600">
        {stats.rendered} / {stats.total} paths rendered
      </div>
      {unrenderedPaths.length > 0 && (
        <div className="mt-2 max-h-32 overflow-y-auto">
          <div className="text-xs text-gray-500 font-medium mb-1">Missing:</div>
          {unrenderedPaths.slice(0, 10).map((path) => (
            <div key={path} className="text-xs text-gray-600 truncate">{path}</div>
          ))}
          {unrenderedPaths.length > 10 && (
            <div className="text-xs text-gray-500">...and {unrenderedPaths.length - 10} more</div>
          )}
        </div>
      )}
    </div>
  );
}
