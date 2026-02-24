import * as React from "react";
import { cn } from "@/lib/utils";
import { TrendingDown, Users, AlertTriangle, Zap } from "lucide-react";
import { InfoTooltip } from "./InfoTooltip";
import type { FunnelStage, QueryableBlock } from "@/lib/qebValidation";

interface FunnelDiagramProps {
  stages: FunnelStage[];
  killerQebs: QueryableBlock[];
  onStageClick?: (stageId: string) => void;
  selectedStageId?: string;
}

export function FunnelDiagram({
  stages,
  killerQebs,
  onStageClick,
  selectedStageId,
}: FunnelDiagramProps) {
  // Sort stages by order
  const sortedStages = [...stages].sort((a, b) => a.stageOrder - b.stageOrder);

  // Calculate cumulative elimination rate
  const getAccumulatedEliminationRate = (index: number): number => {
    let accumulated = 0;
    for (let i = 0; i <= index; i++) {
      accumulated += (sortedStages[i]?.combinedEliminationRate || 0);
    }
    return Math.min(accumulated, 100);
  };

  // Get remaining percentage after each stage
  const getRemainingPercent = (index: number): number => {
    return Math.max(100 - getAccumulatedEliminationRate(index), 0);
  };

  if (stages.length === 0) {
    return (
      <div className="p-4 text-center text-gray-500 text-sm">
        No funnel stages defined
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Funnel Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingDown className="w-4 h-4 text-gray-600" />
          <h4 className="text-sm font-semibold text-gray-800">Patient Funnel</h4>
          <InfoTooltip
            content="Visual representation of how each stage progressively filters the patient population. Wider bars indicate more patients remaining after that stage."
            size="sm"
          />
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Users className="w-3.5 h-3.5" />
          <span>{stages.length} Stages</span>
          {killerQebs.length > 0 && (
            <>
              <span className="text-gray-300">|</span>
              <Zap className="w-3.5 h-3.5 text-gray-500" />
              <span>{killerQebs.length} High Impact</span>
            </>
          )}
        </div>
      </div>

      {/* Funnel Visualization */}
      <div className="relative space-y-1">
        {/* Starting point - 100% */}
        <div className="flex items-center gap-2 mb-2">
          <div className="w-full h-2 bg-gray-700 rounded-full" />
          <span className="text-xs text-gray-600 font-medium whitespace-nowrap w-16 text-right">
            100%
          </span>
        </div>

        {/* Funnel Stages */}
        {sortedStages.map((stage, index) => {
          const remainingPercent = getRemainingPercent(index);
          const eliminationRate = stage.combinedEliminationRate || 0;
          const isSelected = selectedStageId === stage.stageId;
          const hasKillerCriteria = killerQebs.some(k =>
            stage.qebIds.includes(k.qebId)
          );

          // Color based on position in funnel - greyscale gradient
          const getBarColor = () => {
            if (remainingPercent > 70) return "bg-gray-700";
            if (remainingPercent > 40) return "bg-gray-500";
            return "bg-gray-400";
          };

          return (
            <button
              key={stage.stageId}
              onClick={() => onStageClick?.(stage.stageId)}
              className={cn(
                "w-full flex items-center gap-2 p-2 rounded-lg transition-all",
                "hover:bg-gray-50",
                isSelected && "bg-gray-50 ring-1 ring-gray-300"
              )}
            >
              {/* Stage Name */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-gray-700 truncate">
                    {stage.stageName}
                  </span>
                  {hasKillerCriteria && (
                    <Zap className="w-3 h-3 text-gray-500 flex-shrink-0" />
                  )}
                </div>
                <div className="text-[10px] text-gray-400 truncate">
                  {stage.qebIds.length} criteria
                </div>
              </div>

              {/* Funnel Bar */}
              <div className="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden relative">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-500",
                    getBarColor()
                  )}
                  style={{ width: `${remainingPercent}%` }}
                />
                {/* Elimination indicator */}
                {eliminationRate > 0 && (
                  <div
                    className="absolute top-0 right-0 h-full bg-gray-200/50 rounded-r-full flex items-center justify-center"
                    style={{ width: `${Math.min(eliminationRate, 100 - remainingPercent + eliminationRate)}%` }}
                  >
                    <span className="text-[8px] text-gray-600 font-medium">
                      -{Math.round(eliminationRate)}%
                    </span>
                  </div>
                )}
              </div>

              {/* Remaining Percentage */}
              <span className="text-xs text-gray-600 font-medium whitespace-nowrap w-16 text-right">
                {Math.round(remainingPercent)}%
              </span>
            </button>
          );
        })}

        {/* Final cohort indicator */}
        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-gray-100">
          <div className="flex-1">
            <span className="text-xs font-semibold text-gray-800">
              Estimated Final Cohort
            </span>
          </div>
          <div className="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-gray-600 to-gray-800 rounded-full transition-all duration-500"
              style={{ width: `${getRemainingPercent(sortedStages.length - 1)}%` }}
            />
          </div>
          <span className="text-xs text-gray-800 font-bold whitespace-nowrap w-16 text-right">
            {Math.round(getRemainingPercent(sortedStages.length - 1))}%
          </span>
        </div>
      </div>

      {/* Killer Criteria Highlight */}
      {killerQebs.length > 0 && (
        <div className="mt-4 p-3 bg-gray-50 border border-gray-300 rounded-lg">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-gray-600 flex-shrink-0 mt-0.5" />
            <div>
              <h5 className="text-xs font-semibold text-gray-800 mb-1">
                High Impact Criteria
              </h5>
              <p className="text-[10px] text-gray-600 mb-2">
                These criteria eliminate significant patient populations. Consider evaluating them early in the screening process.
              </p>
              <div className="space-y-1">
                {killerQebs.slice(0, 3).map(qeb => (
                  <div
                    key={qeb.qebId}
                    className="flex items-center justify-between text-[10px]"
                  >
                    <span className="text-gray-800 font-medium truncate flex-1 mr-2">
                      {qeb.clinicalName || qeb.protocolText.slice(0, 50)}...
                    </span>
                    {qeb.estimatedEliminationRate != null && (
                      <span className="text-gray-600 font-semibold">
                        -{Math.round(qeb.estimatedEliminationRate * 100)}%
                      </span>
                    )}
                  </div>
                ))}
                {killerQebs.length > 3 && (
                  <span className="text-[10px] text-gray-500">
                    +{killerQebs.length - 3} more high impact criteria
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Summary card for clinical context
interface ClinicalSummaryCardProps {
  totalCriteria: number;
  queryableCount: number;
  manualCount: number;
  killerCount: number;
  topEliminationFactors: string[];
}

export function ClinicalSummaryCard({
  totalCriteria,
  queryableCount,
  manualCount,
  killerCount,
  topEliminationFactors,
}: ClinicalSummaryCardProps) {
  const queryablePercent = totalCriteria > 0
    ? Math.round((queryableCount / totalCriteria) * 100)
    : 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
      <h4 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
        Clinical Summary
        <InfoTooltip
          content="Overview of the eligibility criteria analysis, showing queryability status and key elimination factors."
          size="sm"
        />
      </h4>

      {/* Stats Grid */}
      <div className="grid grid-cols-3 gap-3">
        <div className="text-center p-2 bg-gray-50 rounded-lg">
          <div className="text-lg font-bold text-gray-800">{queryablePercent}%</div>
          <div className="text-[10px] text-gray-600">Query-Ready</div>
        </div>
        <div className="text-center p-2 bg-gray-50 rounded-lg">
          <div className="text-lg font-bold text-gray-700">{manualCount}</div>
          <div className="text-[10px] text-gray-600">Manual Review</div>
        </div>
        <div className="text-center p-2 bg-gray-50 rounded-lg">
          <div className="text-lg font-bold text-gray-700">{killerCount}</div>
          <div className="text-[10px] text-gray-600">High Impact</div>
        </div>
      </div>

      {/* Top Elimination Factors */}
      {topEliminationFactors.length > 0 && (
        <div className="pt-2 border-t border-gray-100">
          <h5 className="text-[10px] font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">
            Top Elimination Factors
          </h5>
          <div className="space-y-1">
            {topEliminationFactors.slice(0, 3).map((factor, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2 text-[11px] text-gray-700"
              >
                <span className="w-4 h-4 rounded-full bg-gray-200 text-gray-700 flex items-center justify-center text-[9px] font-semibold">
                  {idx + 1}
                </span>
                <span className="truncate">{factor}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
