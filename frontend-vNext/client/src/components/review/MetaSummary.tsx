import { motion } from "framer-motion";
import { FileText, ChevronRight } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

interface MetaField {
  label: string;
  value: string | number | null | undefined;
  provenance?: {
    page: number;
    text: string;
  };
}

interface MetaSummaryProps {
  fields: MetaField[];
  onViewSource?: (page: number) => void;
}

export function MetaSummary({ fields, onViewSource }: MetaSummaryProps) {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card overflow-hidden"
    >
      <div className="divide-y divide-gray-100/80">
        {fields.map((field, index) => (
          <MetaRow 
            key={field.label} 
            field={field} 
            onViewSource={onViewSource}
            isFirst={index === 0}
            isLast={index === fields.length - 1}
          />
        ))}
      </div>
    </motion.div>
  );
}

function MetaRow({ 
  field, 
  onViewSource,
  isFirst,
  isLast 
}: { 
  field: MetaField; 
  onViewSource?: (page: number) => void;
  isFirst: boolean;
  isLast: boolean;
}) {
  const [showProvenance, setShowProvenance] = useState(false);

  return (
    <div className={cn(
      "group px-5 py-4 hover:bg-gray-50/50 transition-colors",
      isFirst && "rounded-t-2xl",
      isLast && "rounded-b-2xl"
    )}>
      <div className="flex items-start justify-between gap-6">
        <div className="flex-1 min-w-0">
          <div className="text-sf-caption text-muted-foreground mb-1">
            {field.label}
          </div>
          <div className="text-sf-body text-foreground">
            {field.value || <span className="text-muted-foreground italic">Not specified</span>}
          </div>
        </div>
        
        {field.provenance && (
          <button
            onClick={() => setShowProvenance(!showProvenance)}
            className="provenance-chip shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <FileText className="w-3 h-3" />
            <span>Page {field.provenance.page}</span>
          </button>
        )}
      </div>
      
      {showProvenance && field.provenance && (
        <motion.div 
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          className="mt-3 p-3 bg-gray-50/80 rounded-xl text-sf-caption text-gray-600 leading-relaxed border border-gray-100/80"
        >
          <span className="text-gray-400">"</span>
          {field.provenance.text}
          <span className="text-gray-400">"</span>
          {onViewSource && (
            <button
              type="button"
              className="mt-2 block text-sf-footnote text-gray-900 hover:text-gray-700 font-medium transition-colors flex items-center gap-1"
              onClick={() => onViewSource(field.provenance!.page)}
            >
              View in PDF
              <ChevronRight className="w-3 h-3" />
            </button>
          )}
        </motion.div>
      )}
    </div>
  );
}
