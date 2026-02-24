import { cn } from "@/lib/utils";
import {
  FileSearch,
  Table2,
  Layers,
  Sparkles,
  CheckCircle2,
  Loader2,
  XCircle
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent } from "@/components/ui/card";

// Phase definitions for the SOA extraction pipeline
const phases = [
  {
    id: 'detecting_pages',
    label: 'Page Detection',
    shortLabel: 'Detect',
    icon: FileSearch,
    description: 'Identifying SOA table pages in the PDF'
  },
  {
    id: 'extracting',
    label: 'Table Extraction',
    shortLabel: 'Extract',
    icon: Table2,
    description: 'Extracting table structure and content'
  },
  {
    id: 'analyzing_merges',
    label: 'Merge Analysis',
    shortLabel: 'Analyze',
    icon: Layers,
    description: 'Analyzing table relationships and merge patterns'
  },
  {
    id: 'interpreting',
    label: 'Interpretation',
    shortLabel: 'Interpret',
    icon: Sparkles,
    description: 'Running 12-stage interpretation pipeline'
  },
];

type PhaseStatus = 'pending' | 'running' | 'completed' | 'failed';

interface SOAProgressDisplayProps {
  currentPhase: string;
  phaseProgress?: { phase: string; progress: number } | null;
  interpretationStage?: number;
  className?: string;
}

export function SOAProgressDisplay({
  currentPhase,
  phaseProgress,
  interpretationStage,
  className
}: SOAProgressDisplayProps) {
  // Determine phase statuses based on current phase
  const getPhaseStatus = (phaseId: string): PhaseStatus => {
    const currentIndex = phases.findIndex(p => p.id === currentPhase);
    const phaseIndex = phases.findIndex(p => p.id === phaseId);

    if (currentPhase === 'completed') return 'completed';
    if (currentPhase === 'failed') {
      if (phaseIndex < currentIndex) return 'completed';
      if (phaseIndex === currentIndex) return 'failed';
      return 'pending';
    }

    if (phaseIndex < currentIndex) return 'completed';
    if (phaseIndex === currentIndex) return 'running';
    return 'pending';
  };

  // Calculate overall progress percentage
  const getOverallProgress = (): number => {
    const currentIndex = phases.findIndex(p => p.id === currentPhase);
    if (currentPhase === 'completed') return 100;
    if (currentIndex === -1) return 0;

    const baseProgress = (currentIndex / phases.length) * 100;
    const phaseContribution = phaseProgress?.progress
      ? (phaseProgress.progress * (1 / phases.length) * 100)
      : 0;

    return Math.min(baseProgress + phaseContribution, 100);
  };

  // Get current phase info
  const currentPhaseInfo = phases.find(p => p.id === currentPhase);

  return (
    <div className={cn("w-full max-w-2xl mx-auto", className)}>
      {/* Phase Timeline */}
      <div className="relative flex items-center justify-between mb-6">
        {/* Progress Track */}
        <div className="absolute top-4 left-0 right-0 h-0.5 bg-gray-200">
          <div
            className="h-full bg-primary transition-all duration-500 ease-out"
            style={{ width: `${getOverallProgress()}%` }}
          />
        </div>

        {/* Phase Nodes */}
        {phases.map((phase, index) => {
          const status = getPhaseStatus(phase.id);
          const Icon = phase.icon;

          return (
            <div key={phase.id} className="relative flex flex-col items-center z-10">
              {/* Node */}
              <div
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center transition-all duration-300",
                  status === 'completed' && "bg-primary text-white",
                  status === 'running' && "bg-white border-2 border-primary text-primary stage-running",
                  status === 'pending' && "bg-gray-100 text-gray-400 border border-gray-200",
                  status === 'failed' && "bg-red-100 text-red-600 border border-red-300"
                )}
              >
                {status === 'completed' ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : status === 'failed' ? (
                  <XCircle className="w-4 h-4" />
                ) : status === 'running' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Icon className="w-4 h-4" />
                )}
              </div>

              {/* Label */}
              <span className={cn(
                "mt-2 text-xs font-medium transition-colors",
                status === 'running' && "text-primary",
                status === 'completed' && "text-gray-700",
                status === 'pending' && "text-gray-400",
                status === 'failed' && "text-red-600"
              )}>
                {phase.shortLabel}
              </span>
            </div>
          );
        })}
      </div>

      {/* Current Phase Card */}
      {currentPhaseInfo && currentPhase !== 'completed' && (
        <Card className="glass-card">
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4">
              {/* Phase Icon */}
              <div className={cn(
                "w-12 h-12 rounded-full flex items-center justify-center",
                currentPhase === 'failed' ? "bg-red-100" : "bg-primary/10"
              )}>
                {currentPhase === 'failed' ? (
                  <XCircle className="w-6 h-6 text-red-600" />
                ) : (
                  <currentPhaseInfo.icon className="w-6 h-6 text-primary" />
                )}
              </div>

              {/* Phase Info */}
              <div className="text-center">
                <h3 className="text-lg font-semibold text-gray-900">
                  {currentPhaseInfo.label}
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  {currentPhaseInfo.description}
                </p>
              </div>

              {/* Progress Bar */}
              {phaseProgress && currentPhase !== 'failed' && (
                <div className="w-full">
                  <Progress
                    value={phaseProgress.progress * 100}
                    className="h-2"
                  />
                  <p className="text-xs text-gray-400 text-center mt-2">
                    {Math.round(phaseProgress.progress * 100)}% complete
                  </p>
                </div>
              )}

              {/* Interpretation Stage Indicator */}
              {currentPhase === 'interpreting' && interpretationStage && (
                <div className="w-full">
                  <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                    <span>Stage {interpretationStage} of 12</span>
                    <span>{Math.round((interpretationStage / 12) * 100)}%</span>
                  </div>
                  <Progress
                    value={(interpretationStage / 12) * 100}
                    className="h-1.5"
                  />
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Completed State */}
      {currentPhase === 'completed' && (
        <Card className="glass-card border-green-200 bg-green-50/50">
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6 text-green-600" />
              </div>
              <div className="text-center">
                <h3 className="text-lg font-semibold text-green-800">
                  Extraction Complete
                </h3>
                <p className="text-sm text-green-600 mt-1">
                  All stages completed successfully
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// Mini version for compact display
interface SOAProgressMiniProps {
  currentPhase: string;
  className?: string;
}

export function SOAProgressMini({ currentPhase, className }: SOAProgressMiniProps) {
  const currentIndex = phases.findIndex(p => p.id === currentPhase);
  const currentPhaseInfo = phases.find(p => p.id === currentPhase);

  if (currentPhase === 'completed') {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        <CheckCircle2 className="w-4 h-4 text-green-600" />
        <span className="text-sm font-medium text-green-600">Complete</span>
      </div>
    );
  }

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Loader2 className="w-4 h-4 text-primary animate-spin" />
      <span className="text-sm text-gray-600">
        {currentPhaseInfo?.label || 'Processing'} ({currentIndex + 1}/{phases.length})
      </span>
    </div>
  );
}
