import * as React from "react";
import { useState } from "react";
import {
  Users,
  Activity,
  Pill,
  Heart,
  FileCheck,
  Beaker,
  Shield,
  Clock,
  TestTube,
  ChevronDown,
  ChevronUp,
  Zap,
  FileText,
  CheckCircle2,
  AlertCircle,
  Circle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { InfoTooltip, ELIGIBILITY_TOOLTIPS } from "./InfoTooltip";
import type { QueryableBlock, AtomicCriterion } from "@/lib/qebValidation";

// Category configuration with icons and colors
export const CLINICAL_CATEGORIES: Record<string, { icon: React.ElementType; color: string; bgColor: string; borderColor: string }> = {
  "Demographics": { icon: Users, color: "text-gray-600", bgColor: "bg-gray-50", borderColor: "border-gray-300" },
  "Disease Characteristics": { icon: Activity, color: "text-gray-600", bgColor: "bg-gray-50", borderColor: "border-gray-300" },
  "Disease Status": { icon: Activity, color: "text-gray-600", bgColor: "bg-gray-50", borderColor: "border-gray-300" },
  "Prior Therapy": { icon: Pill, color: "text-gray-600", bgColor: "bg-gray-50", borderColor: "border-gray-300" },
  "Prior/Concurrent Therapy": { icon: Pill, color: "text-gray-600", bgColor: "bg-gray-50", borderColor: "border-gray-300" },
  "Organ Function": { icon: Heart, color: "text-gray-600", bgColor: "bg-gray-50", borderColor: "border-gray-300" },
  "Laboratory": { icon: TestTube, color: "text-gray-600", bgColor: "bg-gray-50", borderColor: "border-gray-300" },
  "Informed Consent": { icon: FileCheck, color: "text-gray-600", bgColor: "bg-gray-100", borderColor: "border-gray-300" },
  "Reproductive Status": { icon: Shield, color: "text-gray-600", bgColor: "bg-gray-50", borderColor: "border-gray-300" },
  "Washout Period": { icon: Clock, color: "text-gray-600", bgColor: "bg-gray-50", borderColor: "border-gray-300" },
  "Other": { icon: Beaker, color: "text-gray-600", bgColor: "bg-gray-100", borderColor: "border-gray-300" },
};

const getCategory = (category: string) => {
  // Find matching category (case-insensitive partial match)
  const normalizedCategory = category.toLowerCase();
  for (const [key, value] of Object.entries(CLINICAL_CATEGORIES)) {
    if (normalizedCategory.includes(key.toLowerCase()) || key.toLowerCase().includes(normalizedCategory)) {
      return value;
    }
  }
  return CLINICAL_CATEGORIES["Other"];
};

interface CriterionCardProps {
  qeb: QueryableBlock;
  index: number;
  type: "inclusion" | "exclusion";
  onViewProvenance?: (pageNumber: number) => void;
  atomicLookup?: Map<string, AtomicCriterion>;
  isSelected?: boolean;
  onSelect?: (qebId: string) => void;
  showCheckbox?: boolean;
}

export function CriterionCard({
  qeb,
  index,
  type,
  onViewProvenance,
  atomicLookup,
  isSelected,
  onSelect,
  showCheckbox = false,
}: CriterionCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Determine queryable status based on atomics or QEB status
  const getQueryableStatus = (): "fully_queryable" | "partially_queryable" | "requires_manual" => {
    if (!atomicLookup || qeb.atomicIds.length === 0) {
      return qeb.queryableStatus;
    }

    let queryableCount = 0;
    let totalCount = 0;

    qeb.atomicIds.forEach(atomicId => {
      const atomic = atomicLookup.get(atomicId);
      if (atomic) {
        totalCount++;
        if (atomic.queryabilityClassification.category === "QUERYABLE") {
          queryableCount++;
        }
      }
    });

    if (queryableCount === totalCount && totalCount > 0) return "fully_queryable";
    if (queryableCount > 0) return "partially_queryable";
    return "requires_manual";
  };

  const status = getQueryableStatus();
  const statusConfig = {
    "fully_queryable": { color: "bg-gray-700", label: "Fully Queryable", icon: CheckCircle2 },
    "partially_queryable": { color: "bg-gray-400", label: "Needs Mapping", icon: AlertCircle },
    "requires_manual": { color: "bg-gray-300", label: "Manual Review", icon: Circle },
  };

  const currentStatus = statusConfig[status];
  const categoryConfig = getCategory(qeb.clinicalCategory);
  const CategoryIcon = categoryConfig.icon;

  // Truncate text if too long
  const MAX_LENGTH = 250;
  const isLongText = qeb.protocolText.length > MAX_LENGTH;
  const displayText = isLongText && !isExpanded
    ? qeb.protocolText.substring(0, MAX_LENGTH) + "..."
    : qeb.protocolText;

  // Parse text into lines for display
  const parseText = (text: string) => {
    return text.split(/\n|(?:(?<=[.;])\s*(?=[a-z]\)|[ivx]+\)|•|−|–))/gi)
      .map(line => line.trim())
      .filter(line => line.length > 0);
  };

  const typeColors = {
    inclusion: {
      band: "bg-gradient-to-b from-gray-400 to-gray-600",
      badge: "bg-gray-50 border-gray-300 text-gray-700",
      indexBg: "bg-gray-100 border-gray-300 text-gray-600",
    },
    exclusion: {
      band: "bg-gradient-to-b from-gray-300 to-gray-400",
      badge: "bg-gray-50 border-gray-300 text-gray-600",
      indexBg: "bg-gray-50 border-gray-300 text-gray-500",
    },
  };

  const colors = typeColors[type];

  return (
    <div
      className={cn(
        "group relative rounded-lg border bg-white shadow-sm hover:shadow-md transition-all duration-200 overflow-hidden",
        isSelected && "ring-2 ring-gray-500 ring-offset-1"
      )}
    >
      {/* Left Color Band */}
      <div className={cn("absolute left-0 top-0 bottom-0 w-1", colors.band)} />

      <div className="pl-4 pr-3 py-3">
        {/* Header Row */}
        <div className="flex items-start gap-3">
          {/* Checkbox */}
          {showCheckbox && (
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => onSelect?.(qeb.qebId)}
              className="mt-1 h-4 w-4 rounded border-gray-300 text-gray-600 focus:ring-gray-500"
            />
          )}

          {/* Index Badge */}
          <div className={cn(
            "flex-shrink-0 w-6 h-6 rounded-full border flex items-center justify-center text-[10px] font-semibold",
            colors.indexBg
          )}>
            {index}
          </div>

          {/* Main Content */}
          <div className="flex-1 min-w-0">
            {/* Top Row with ID and Status */}
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                {qeb.originalCriterionId}
              </span>
              <div className="flex items-center gap-1">
                <div className={cn("w-2 h-2 rounded-full", currentStatus.color)} />
                <span className="text-[9px] text-gray-500">{currentStatus.label}</span>
              </div>
              {qeb.provenance?.pageNumber && onViewProvenance && (
                <button
                  onClick={() => onViewProvenance(qeb.provenance.pageNumber)}
                  className="ml-auto flex items-center gap-1 text-[9px] text-gray-500 hover:text-gray-700 transition-colors"
                >
                  <FileText className="w-3 h-3" />
                  Page {qeb.provenance.pageNumber}
                </button>
              )}
            </div>

            {/* Criterion Text */}
            <div className="text-[13px] text-gray-700 leading-relaxed">
              {parseText(displayText).map((line, lineIdx) => {
                const isBullet = /^[a-z]\)|^[ivx]+\)|^•|^−|^–|^\d+\./i.test(line);
                return (
                  <div key={lineIdx} className={isBullet ? "pl-4 mt-1" : lineIdx > 0 ? "mt-1" : ""}>
                    {isBullet && <span className="text-gray-400 mr-1">•</span>}
                    <span>{isBullet ? line.replace(/^[a-z]\)|^[ivx]+\)|^•|^−|^–|^\d+\.\s*/i, '') : line}</span>
                  </div>
                );
              })}
            </div>

            {/* Show More/Less Toggle */}
            {isLongText && (
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="mt-1 flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-700 transition-colors"
              >
                {isExpanded ? (
                  <>
                    Show less <ChevronUp className="w-3 h-3" />
                  </>
                ) : (
                  <>
                    Show more <ChevronDown className="w-3 h-3" />
                  </>
                )}
              </button>
            )}

            {/* Badges Row */}
            <div className="flex flex-wrap items-center gap-1.5 mt-2">
              {/* Category Badge with Icon */}
              <span className={cn(
                "inline-flex items-center gap-1 text-[9px] px-2 py-0.5 rounded-full border font-medium",
                categoryConfig.bgColor,
                categoryConfig.borderColor,
                categoryConfig.color
              )}>
                <CategoryIcon className="w-2.5 h-2.5" />
                {qeb.clinicalCategory}
              </span>

              {/* Killer Criterion Badge */}
              {qeb.isKillerCriterion && (
                <span className="inline-flex items-center gap-0.5 text-[9px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 border border-gray-300 font-medium">
                  <Zap className="w-2.5 h-2.5" />
                  High Impact
                  {qeb.estimatedEliminationRate != null && (
                    <span className="ml-0.5 text-gray-600">
                      ({Math.round(qeb.estimatedEliminationRate * 100)}%)
                    </span>
                  )}
                </span>
              )}

              {/* Sub-criteria Count */}
              {qeb.atomicCount > 1 && (
                <span className="inline-flex items-center gap-1 text-[9px] px-2 py-0.5 rounded-full bg-gray-50 text-gray-600 border border-gray-300 font-medium">
                  {qeb.atomicCount} sub-criteria
                  <InfoTooltip content={ELIGIBILITY_TOOLTIPS.subCriteria} size="sm" />
                </span>
              )}

              {/* Complex Logic Indicator */}
              {qeb.internalLogic === "COMPLEX" && (
                <span className="text-[9px] px-2 py-0.5 rounded-full bg-gray-50 text-gray-600 border border-gray-300 font-medium">
                  Complex Logic
                </span>
              )}
            </div>

            {/* OMOP Concepts Row */}
            {qeb.omopConcepts && qeb.omopConcepts.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {qeb.omopConcepts.slice(0, 4).map((concept, cIdx) => (
                  <span
                    key={cIdx}
                    className="inline-flex items-center text-[9px] px-2 py-0.5 rounded-md bg-gray-50 text-gray-600 border border-gray-200"
                    title={`${concept.domain} | ${concept.vocabularyId || 'N/A'} | ID: ${concept.conceptId}`}
                  >
                    {concept.conceptName.length > 25
                      ? concept.conceptName.substring(0, 25) + '...'
                      : concept.conceptName}
                  </span>
                ))}
                {qeb.omopConcepts.length > 4 && (
                  <span className="text-[9px] px-2 py-0.5 rounded-md bg-gray-100 text-gray-500 font-medium">
                    +{qeb.omopConcepts.length - 4} more
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Sticky section header component
interface SectionHeaderProps {
  type: "inclusion" | "exclusion";
  count: number;
  reviewedCount?: number;
  totalCount?: number;
}

export function SectionHeader({ type, count, reviewedCount = 0, totalCount }: SectionHeaderProps) {
  const config = {
    inclusion: {
      bgColor: "bg-gray-700",
      icon: CheckCircle2,
      label: "Inclusion Criteria",
    },
    exclusion: {
      bgColor: "bg-gray-500",
      icon: AlertCircle,
      label: "Exclusion Criteria",
    },
  };

  const { bgColor, icon: Icon, label } = config[type];
  const showProgress = totalCount !== undefined && totalCount > 0;
  const progressPercent = showProgress ? Math.round((reviewedCount / totalCount) * 100) : 0;

  return (
    <div className={cn(
      "sticky top-0 z-10 flex items-center justify-between px-4 py-2.5 rounded-t-lg shadow-sm",
      bgColor
    )}>
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 text-white" />
        <h4 className="text-sm font-semibold text-white">{label}</h4>
        <span className="text-xs text-white/80 font-medium bg-white/20 px-2 py-0.5 rounded-full">
          {count} criteria
        </span>
      </div>
      {showProgress && (
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-20 bg-white/30 rounded-full overflow-hidden">
            <div
              className="h-full bg-white rounded-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-[10px] text-white/90 font-medium">
            {reviewedCount}/{totalCount} reviewed
          </span>
        </div>
      )}
    </div>
  );
}
