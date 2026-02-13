import { motion } from "framer-motion";
import { FileText, ChevronRight, CheckCircle, XCircle } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

interface EligibilityListProps {
  title: string;
  items: string[];
  type: "inclusion" | "exclusion";
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
  onViewSource?: (page: number) => void;
}

export function EligibilityList({ 
  title, 
  items, 
  type, 
  provenance,
  onViewSource 
}: EligibilityListProps) {
  const [showProvenance, setShowProvenance] = useState(false);
  
  const isInclusion = type === "inclusion";
  const Icon = isInclusion ? CheckCircle : XCircle;
  const iconColor = isInclusion ? "text-gray-600" : "text-gray-500";
  const bulletColor = isInclusion ? "bg-gray-400" : "bg-gray-400";

  return (
    <motion.div 
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Icon className={cn("w-4 h-4", iconColor)} />
          <h4 className="text-sf-caption font-semibold text-muted-foreground uppercase tracking-wide">
            {title}
          </h4>
          <span className="text-sf-footnote text-muted-foreground">
            ({items.length} criteria)
          </span>
        </div>
        
        {provenance?.page_number && (
          <button
            type="button"
            onClick={() => setShowProvenance(!showProvenance)}
            className="provenance-chip"
          >
            <FileText className="w-3 h-3" />
            <span>Page {provenance.page_number}</span>
            <ChevronRight className={cn(
              "w-3 h-3 transition-transform",
              showProvenance && "rotate-90"
            )} />
          </button>
        )}
      </div>
      
      <ul className="space-y-3">
        {items.map((item, index) => (
          <li key={index} className="flex items-start gap-3 group">
            <span className={cn(
              "w-1.5 h-1.5 rounded-full mt-2 shrink-0",
              bulletColor
            )} />
            <span className="text-sf-body text-foreground leading-relaxed">
              {item}
            </span>
          </li>
        ))}
      </ul>
      
      {showProvenance && provenance?.text_snippet && (
        <motion.div 
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          className="mt-4 p-3 bg-gray-50/80 rounded-xl text-sf-caption text-gray-600 leading-relaxed border border-gray-100/80"
        >
          <span className="text-gray-400">"</span>
          {provenance.text_snippet}
          <span className="text-gray-400">"</span>
          {onViewSource && (
            <button
              type="button"
              className="mt-2 block text-sf-footnote text-gray-900 hover:text-gray-700 font-medium transition-colors flex items-center gap-1"
              onClick={() => onViewSource(provenance.page_number!)}
            >
              View in PDF
              <ChevronRight className="w-3 h-3" />
            </button>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}
