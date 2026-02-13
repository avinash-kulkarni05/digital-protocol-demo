import * as React from "react";
import { Info, HelpCircle } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface InfoTooltipProps {
  content: string | React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  className?: string;
  iconClassName?: string;
  variant?: "info" | "help";
  size?: "sm" | "md" | "lg";
  children?: React.ReactNode;
}

export function InfoTooltip({
  content,
  side = "top",
  className,
  iconClassName,
  variant = "info",
  size = "sm",
  children,
}: InfoTooltipProps) {
  const sizeClasses = {
    sm: "w-3.5 h-3.5",
    md: "w-4 h-4",
    lg: "w-5 h-5",
  };

  const Icon = variant === "help" ? HelpCircle : Info;

  return (
    <TooltipProvider>
      <Tooltip delayDuration={200}>
        <TooltipTrigger asChild>
          {children || (
            <button
              type="button"
              className={cn(
                "inline-flex items-center justify-center rounded-full text-gray-400 hover:text-gray-600 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-400 focus:ring-offset-1",
                className
              )}
            >
              <Icon className={cn(sizeClasses[size], iconClassName)} />
            </button>
          )}
        </TooltipTrigger>
        <TooltipContent
          side={side}
          className="max-w-xs bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-lg"
        >
          {content}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// Pre-defined tooltips for common eligibility terms
export const ELIGIBILITY_TOOLTIPS = {
  atomics: "Individual testable conditions extracted from compound criteria. Each atomic can be independently validated against patient data.",
  subCriteria: "Individual testable conditions extracted from compound criteria. Each sub-criterion can be independently validated against patient data.",
  clinicalGroup: "Category grouping related criteria for funnel analysis. Groups help organize criteria by clinical domain (e.g., Demographics, Disease Status).",
  queryableStatus: "Whether criteria can be auto-evaluated via database queries. Fully queryable criteria have complete OMOP concept mappings.",
  killerCriterion: "Criteria that eliminate significant patient populations. These high-impact criteria should be evaluated early in the screening process.",
  funnelStage: "A step in the patient screening sequence. Criteria are organized into stages based on when they should be evaluated.",
  omopConcept: "Standardized clinical concept from the OHDSI OMOP Common Data Model. Used for querying electronic health records.",
  decomposition: "The process of breaking complex criteria into individual testable conditions (atomics/sub-criteria).",
  normalization: "Standardizing criteria text and mapping to controlled vocabularies like OMOP for database queries.",
  eliminationRate: "Estimated percentage of patients excluded by this criterion. Higher rates indicate more restrictive criteria.",
};
