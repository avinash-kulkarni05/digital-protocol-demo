import { useState } from "react";
import { Check, Flag, ChevronRight, FileText, Code } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type ReviewStatus = "pending" | "approved" | "rejected" | "flagged";

interface DataCardProps {
  label: string;
  value: string | number | React.ReactNode;
  confidence?: "high" | "medium" | "low";
  provenance?: {
    page: number;
    text: string;
  };
  controlTerminology?: {
    code: string;
    decode: string;
    system: string;
    version: string;
  };
  onViewSource?: (page: number) => void;
  reviewId?: number;
  initialStatus?: ReviewStatus;
  onStatusChange?: (reviewId: number, status: ReviewStatus) => void;
}

export function DataCard({ 
  label, 
  value, 
  provenance, 
  controlTerminology, 
  onViewSource,
  reviewId,
  initialStatus = "pending",
  onStatusChange
}: DataCardProps) {
  const [status, setStatus] = useState<ReviewStatus>(initialStatus);
  const [isExpanded, setIsExpanded] = useState(false);

  const handleStatusChange = (newStatus: ReviewStatus) => {
    const updatedStatus = status === newStatus ? "pending" : newStatus;
    setStatus(updatedStatus);
    if (reviewId && onStatusChange) {
      onStatusChange(reviewId, updatedStatus);
    }
  };

  return (
    <motion.div 
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
      className={cn(
        "group relative glass-card overflow-hidden",
        status === "approved" && "ring-1 ring-green-300/50",
        status === "flagged" && "ring-1 ring-amber-300/50"
      )}
    >
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-sf-caption text-muted-foreground font-medium">
                {label}
              </span>
              
              {controlTerminology && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded-md bg-slate-100/80 text-slate-500 hover:bg-slate-200/80 cursor-help transition-colors">
                        <Code className="w-2.5 h-2.5" />
                        {controlTerminology.code}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs bg-gray-900 text-white border-0 shadow-xl">
                      <div className="space-y-1.5 p-1">
                        <p className="font-semibold text-xs text-gray-100">Controlled Terminology</p>
                        <div className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-[11px]">
                          <span className="text-gray-400">Code</span>
                          <span className="font-mono text-gray-200">{controlTerminology.code}</span>
                          <span className="text-gray-400">Decode</span>
                          <span className="text-gray-200">{controlTerminology.decode}</span>
                          <span className="text-gray-400">System</span>
                          <span className="text-gray-200 break-all">{controlTerminology.system}</span>
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </div>

            <div className="text-sf-headline text-foreground">
              {value}
            </div>
          </div>
          
          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
            <Button 
              variant="ghost" 
              size="icon" 
              className={cn(
                "h-7 w-7 rounded-full transition-all duration-200",
                status === "approved" 
                  ? "bg-gray-100 text-gray-900 opacity-100" 
                  : "hover:bg-gray-50 hover:text-gray-900 hover:scale-110"
              )}
              onClick={() => handleStatusChange("approved")}
              data-testid={`button-approve-${label.toLowerCase().replace(/\s+/g, '-')}`}
            >
              <Check className="w-3.5 h-3.5" />
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              className={cn(
                "h-7 w-7 rounded-full transition-all duration-200",
                status === "flagged" 
                  ? "bg-gray-100 text-gray-900 opacity-100" 
                  : "hover:bg-gray-50 hover:text-gray-900 hover:scale-110"
              )}
              onClick={() => handleStatusChange("flagged")}
              data-testid={`button-flag-${label.toLowerCase().replace(/\s+/g, '-')}`}
            >
              <Flag className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>

        {provenance && (
          <div className="mt-4">
            <button
              type="button"
              onClick={() => setIsExpanded(!isExpanded)}
              className="provenance-chip"
            >
              <FileText className="w-3 h-3" />
              <span>Page {provenance.page}</span>
              <ChevronRight className={cn(
                "w-3 h-3 transition-transform duration-200",
                isExpanded && "rotate-90"
              )} />
            </button>

            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
                  className="overflow-hidden"
                >
                  <div className="mt-3 p-3 bg-gray-50/80 rounded-xl text-sf-caption text-gray-600 leading-relaxed border border-gray-100/80">
                    <span className="text-gray-400">"</span>
                    {provenance.text}
                    <span className="text-gray-400">"</span>
                  </div>
                  {onViewSource && (
                    <button
                      type="button"
                      className="mt-2 text-sf-footnote text-gray-900 hover:text-gray-700 font-medium transition-colors flex items-center gap-1"
                      onClick={() => onViewSource(provenance.page)}
                    >
                      View in PDF
                      <ChevronRight className="w-3 h-3" />
                    </button>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
      
      {status !== "pending" && (
        <motion.div 
          initial={{ scaleY: 0 }}
          animate={{ scaleY: 1 }}
          className={cn(
            "absolute left-0 top-0 bottom-0 w-0.5 origin-top",
            status === "approved" ? "bg-gray-400" : "bg-gray-400"
          )} 
        />
      )}
    </motion.div>
  );
}
