import { useState, useRef, useEffect } from "react";
import { Check, X, Pencil } from "lucide-react";

interface EditableTextProps {
  value: string;
  onSave?: (newValue: string) => void;
  multiline?: boolean;
  className?: string;
  placeholder?: string;
}

export function EditableText({
  value,
  onSave,
  multiline = false,
  className = "",
  placeholder = ""
}: EditableTextProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value || "");
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  useEffect(() => {
    setEditValue(value || "");
  }, [value]);

  const handleSave = () => {
    console.log("[EditableText] handleSave called, onSave:", !!onSave, "editValue:", editValue);
    if (onSave) {
      onSave(editValue);
    } else {
      console.log("[EditableText] onSave is undefined - field is not connected to update handler");
    }
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditValue(value || "");
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
      <div className="flex items-start gap-2" onClick={(e) => e.stopPropagation()}>
        {multiline ? (
          <textarea
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 min-h-[60px] resize-y bg-white"
            data-testid="inline-edit-textarea"
          />
        ) : (
          <input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 bg-white"
            data-testid="inline-edit-input"
          />
        )}
        <button
          onClick={(e) => { e.stopPropagation(); handleSave(); }}
          className="p-1.5 text-gray-800 hover:bg-gray-50 rounded-md border border-gray-200"
          data-testid="inline-edit-save"
        >
          <Check className="w-4 h-4" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); handleCancel(); }}
          className="p-1.5 text-gray-600 hover:bg-gray-50 rounded-md border border-gray-200"
          data-testid="inline-edit-cancel"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  const displayValue = value || placeholder;
  const isEmpty = !value;

  return (
    <span
      onDoubleClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
      className={`cursor-text hover:bg-yellow-50 hover:outline hover:outline-1 hover:outline-yellow-300 rounded px-1 -mx-1 inline-flex items-center gap-1 group ${className} ${isEmpty ? 'text-gray-400 italic' : ''}`}
      title="Double-click to edit"
      data-testid="editable-text"
    >
      {displayValue}
      <Pencil className="w-3 h-3 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
    </span>
  );
}

interface EditableNumberProps {
  value: number | string;
  onSave?: (newValue: number) => void;
  className?: string;
}

export function EditableNumber({ 
  value, 
  onSave,
  className = ""
}: EditableNumberProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(String(value));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  useEffect(() => {
    setEditValue(String(value));
  }, [value]);

  const handleSave = () => {
    const num = parseFloat(editValue);
    if (!isNaN(num) && onSave) {
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
      <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          type="number"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          className="w-24 px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 bg-white"
          data-testid="inline-edit-number"
        />
        <button 
          onClick={(e) => { e.stopPropagation(); handleSave(); }} 
          className="p-1.5 text-gray-800 hover:bg-gray-50 rounded-md border border-gray-200"
        >
          <Check className="w-4 h-4" />
        </button>
        <button 
          onClick={(e) => { e.stopPropagation(); handleCancel(); }} 
          className="p-1.5 text-gray-600 hover:bg-gray-50 rounded-md border border-gray-200"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <span
      onDoubleClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
      className={`cursor-text hover:bg-yellow-50 hover:outline hover:outline-1 hover:outline-yellow-300 rounded px-1 -mx-1 inline-flex items-center gap-1 group ${className}`}
      title="Double-click to edit"
      data-testid="editable-number"
    >
      {value}
      <Pencil className="w-3 h-3 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
    </span>
  );
}
