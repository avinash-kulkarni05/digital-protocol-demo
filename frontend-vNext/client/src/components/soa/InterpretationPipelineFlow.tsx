import { useMemo, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Circle,
  Clock,
  SkipForward,
} from 'lucide-react';

// Stage metadata with groupings
const stageGroups = [
  {
    name: 'Activity Processing',
    stages: [1, 2, 3],
    color: 'slate',
  },
  {
    name: 'Enrichment',
    stages: [4, 5, 6],
    color: 'slate',
  },
  {
    name: 'Timing & Cycles',
    stages: [7, 8],
    color: 'slate',
  },
  {
    name: 'Finalization',
    stages: [9, 10, 11, 12],
    color: 'slate',
  },
];

// Default stage names (can be overridden by props)
const defaultStageNames: Record<number, { name: string; description: string }> = {
  1: { name: 'Domain Categorization', description: 'Map activities to CDISC domains' },
  2: { name: 'Activity Expansion', description: 'Protocol-driven decomposition' },
  3: { name: 'Component Mapping', description: 'Map to CDASH/SDTM domains' },
  4: { name: 'Unit Extraction', description: 'Extract measurement units' },
  5: { name: 'Footnote Linking', description: 'Link footnotes to activities' },
  6: { name: 'SAI Generation', description: 'Generate Scheduled Activity Instances' },
  7: { name: 'Timing Distribution', description: 'Expand BI/EOI to atomic SAIs' },
  8: { name: 'Cycle Expansion', description: 'Handle cycle patterns' },
  9: { name: 'Validation', description: 'Validate USDM structure' },
  10: { name: 'Deduplication', description: 'Remove duplicate entries' },
  11: { name: 'Schedule Assembly', description: 'Assemble final schedule' },
  12: { name: 'USDM Compliance', description: 'Expand Code objects' },
};

export type StageStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped';

export interface StageData {
  number: number;
  name?: string;
  description?: string;
  status: StageStatus;
  duration?: number;
  result?: any;
}

interface InterpretationPipelineFlowProps {
  stages: StageData[];
  currentStage?: number;
  onStageClick?: (stageNumber: number) => void;
  className?: string;
  showHeader?: boolean;
}

export function InterpretationPipelineFlow({
  stages,
  currentStage,
  onStageClick,
  className,
  showHeader = true,
}: InterpretationPipelineFlowProps) {
  const stageRefs = useRef<Record<number, HTMLButtonElement | null>>({});

  // Build stage data map
  const stageMap = useMemo(() => {
    const map: Record<number, StageData> = {};
    stages.forEach(s => {
      map[s.number] = s;
    });
    // Fill in missing stages with defaults
    for (let i = 1; i <= 12; i++) {
      if (!map[i]) {
        map[i] = {
          number: i,
          name: defaultStageNames[i]?.name || `Stage ${i}`,
          description: defaultStageNames[i]?.description || '',
          status: 'pending',
        };
      } else {
        // Merge with defaults
        map[i] = {
          ...map[i],
          name: map[i].name || defaultStageNames[i]?.name || `Stage ${i}`,
          description: map[i].description || defaultStageNames[i]?.description || '',
        };
      }
    }
    return map;
  }, [stages]);

  // Calculate completion stats
  const stats = useMemo(() => {
    const completed = stages.filter(s => s.status === 'success').length;
    const failed = stages.filter(s => s.status === 'failed').length;
    const running = stages.filter(s => s.status === 'running').length;
    const totalDuration = stages.reduce((sum, s) => sum + (s.duration || 0), 0);
    return { completed, failed, running, totalDuration, total: 12 };
  }, [stages]);

  // Scroll to current stage
  useEffect(() => {
    if (currentStage && stageRefs.current[currentStage]) {
      stageRefs.current[currentStage]?.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
        inline: 'center',
      });
    }
  }, [currentStage]);

  const getStatusIcon = (status: StageStatus, isRunning: boolean) => {
    if (isRunning) {
      return <Loader2 className="w-3.5 h-3.5 animate-spin" />;
    }
    switch (status) {
      case 'success':
        return <CheckCircle2 className="w-3.5 h-3.5" />;
      case 'failed':
        return <XCircle className="w-3.5 h-3.5" />;
      case 'skipped':
        return <SkipForward className="w-3.5 h-3.5" />;
      case 'running':
        return <Loader2 className="w-3.5 h-3.5 animate-spin" />;
      default:
        return <Circle className="w-3.5 h-3.5" />;
    }
  };

  const getStatusClasses = (status: StageStatus, isCurrentStage: boolean) => {
    const base = 'transition-all duration-300';

    if (isCurrentStage) {
      return cn(base, 'bg-primary text-white stage-running scale-110 z-10');
    }

    switch (status) {
      case 'success':
        return cn(base, 'bg-primary text-white stage-complete');
      case 'failed':
        return cn(base, 'bg-red-500 text-white');
      case 'skipped':
        return cn(base, 'bg-gray-300 text-gray-600');
      case 'running':
        return cn(base, 'bg-primary text-white stage-running');
      default:
        return cn(base, 'bg-gray-100 text-gray-400 border border-gray-200');
    }
  };

  const getConnectorClass = (fromStage: number, toStage: number) => {
    const fromStatus = stageMap[fromStage]?.status;
    if (fromStatus === 'success' || fromStatus === 'failed' || fromStatus === 'skipped') {
      return 'bg-primary stage-connector-fill';
    }
    return 'bg-gray-200';
  };

  return (
    <div className={cn("space-y-4", className)}>
      {/* Header with stats */}
      {showHeader && (
        <Card className="bg-white border-gray-200">
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="text-sm">
                  <span className="text-gray-500">Progress:</span>
                  <span className="ml-2 font-semibold text-gray-900">
                    {stats.completed} of {stats.total} stages
                  </span>
                </div>
                {stats.running > 0 && (
                  <div className="flex items-center gap-1.5 text-sm text-blue-600">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Processing Stage {currentStage}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-4 text-xs text-gray-500">
                {stats.failed > 0 && (
                  <span className="text-red-600">{stats.failed} failed</span>
                )}
                {stats.totalDuration > 0 && (
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {stats.totalDuration.toFixed(1)}s total
                  </span>
                )}
              </div>
            </div>
            <Progress
              value={(stats.completed / stats.total) * 100}
              className="h-1.5 mt-3"
            />
          </CardContent>
        </Card>
      )}

      {/* Pipeline Visualization */}
      <Card className="bg-white border-gray-200 overflow-hidden">
        <CardContent className="py-6 px-4">
          {/* Stage Groups */}
          <div className="flex flex-col gap-6">
            {stageGroups.map((group, groupIndex) => {
              const isLastGroup = groupIndex === stageGroups.length - 1;

              return (
              <div key={group.name} className="space-y-2">
                {/* Group Label */}
                <div className="text-xs font-medium text-gray-500 uppercase tracking-wide px-1">
                  {group.name}
                </div>

                {/* Stage Nodes */}
                <div className="flex items-center">
                  {group.stages.map((stageNum, stageIndex) => {
                    const stage = stageMap[stageNum];
                    const isCurrentStage = stageNum === currentStage;
                    const isLastInGroup = stageIndex === group.stages.length - 1;
                    const nextStage = group.stages[stageIndex + 1];

                    return (
                      <div key={stageNum} className="flex items-center">
                        {/* Stage Node */}
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                ref={el => { stageRefs.current[stageNum] = el; }}
                                onClick={() => onStageClick?.(stageNum)}
                                className={cn(
                                  "relative flex items-center justify-center w-9 h-9 rounded-full font-medium text-xs",
                                  "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
                                  getStatusClasses(stage.status, isCurrentStage),
                                  onStageClick && "cursor-pointer hover:scale-105"
                                )}
                              >
                                {stage.status === 'pending' ? (
                                  <span>{stageNum}</span>
                                ) : (
                                  getStatusIcon(stage.status, isCurrentStage)
                                )}
                              </button>
                            </TooltipTrigger>
                            <TooltipContent side="bottom" className="max-w-xs">
                              <div className="space-y-1">
                                <p className="font-medium">
                                  Stage {stageNum}: {stage.name}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                  {stage.description}
                                </p>
                                <div className="flex items-center gap-2 pt-1 text-xs">
                                  <span className={cn(
                                    "px-1.5 py-0.5 rounded capitalize",
                                    stage.status === 'success' && "bg-green-100 text-green-700",
                                    stage.status === 'failed' && "bg-red-100 text-red-700",
                                    stage.status === 'running' && "bg-blue-100 text-blue-700",
                                    stage.status === 'skipped' && "bg-gray-100 text-gray-600",
                                    stage.status === 'pending' && "bg-gray-100 text-gray-500"
                                  )}>
                                    {stage.status}
                                  </span>
                                  {stage.duration !== undefined && (
                                    <span className="text-gray-400">
                                      {stage.duration.toFixed(2)}s
                                    </span>
                                  )}
                                </div>
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>

                        {/* Connector Line (within group) */}
                        {!isLastInGroup && nextStage && (
                          <div className="relative w-6 h-0.5 mx-1">
                            <div className="absolute inset-0 bg-gray-200 rounded-full" />
                            <div
                              className={cn(
                                "absolute inset-y-0 left-0 rounded-full",
                                getConnectorClass(stageNum, nextStage)
                              )}
                              style={{
                                width: stageMap[stageNum]?.status !== 'pending' ? '100%' : '0%',
                              }}
                            />
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {/* Connector to next group */}
                  {!isLastGroup && (
                    <div className="relative w-10 h-0.5 mx-2">
                      <div className="absolute inset-0 bg-gray-200 rounded-full" />
                      <div
                        className={cn(
                          "absolute inset-y-0 left-0 rounded-full transition-all duration-300",
                          stageMap[group.stages[group.stages.length - 1]]?.status === 'success'
                            ? 'bg-primary'
                            : 'bg-gray-200'
                        )}
                        style={{
                          width: stageMap[group.stages[group.stages.length - 1]]?.status !== 'pending' ? '100%' : '0%',
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Legend */}
      <div className="flex items-center justify-center gap-6 text-xs text-gray-500">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-full bg-gray-100 border border-gray-200" />
          <span>Pending</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-full bg-primary" />
          <span>Running</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-full bg-primary flex items-center justify-center">
            <CheckCircle2 className="w-2 h-2 text-white" />
          </div>
          <span>Complete</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <span>Failed</span>
        </div>
      </div>
    </div>
  );
}

// Compact version for inline display
interface CompactPipelineProps {
  stages: StageData[];
  currentStage?: number;
  className?: string;
}

export function CompactPipeline({ stages, currentStage, className }: CompactPipelineProps) {
  const stageMap = useMemo(() => {
    const map: Record<number, StageData> = {};
    stages.forEach(s => map[s.number] = s);
    return map;
  }, [stages]);

  return (
    <div className={cn("flex items-center gap-0.5", className)}>
      {Array.from({ length: 12 }, (_, i) => i + 1).map(stageNum => {
        const stage = stageMap[stageNum];
        const isCurrentStage = stageNum === currentStage;

        return (
          <div
            key={stageNum}
            className={cn(
              "w-2 h-2 rounded-full transition-all duration-300",
              !stage || stage.status === 'pending' && "bg-gray-200",
              stage?.status === 'success' && "bg-primary",
              stage?.status === 'failed' && "bg-red-500",
              stage?.status === 'running' && "bg-primary animate-pulse",
              stage?.status === 'skipped' && "bg-gray-300",
              isCurrentStage && "scale-125 ring-2 ring-primary/30"
            )}
          />
        );
      })}
    </div>
  );
}
