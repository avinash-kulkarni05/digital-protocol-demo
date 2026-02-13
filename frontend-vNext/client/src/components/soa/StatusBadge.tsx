import { cn } from "@/lib/utils";
import {
  Clock,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  AlertCircle,
  HelpCircle
} from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export type StatusType =
  | 'pending'
  | 'in_progress'
  | 'awaiting_confirmation'
  | 'completed'
  | 'failed'
  | 'needs_review'
  | 'skipped'
  | 'success';

interface StatusConfig {
  label: string;
  className: string;
  icon: React.ComponentType<{ className?: string }>;
  animate?: boolean;
}

const statusConfig: Record<StatusType, StatusConfig> = {
  pending: {
    label: "Pending",
    className: "bg-gray-100 text-gray-600 border-gray-200",
    icon: Clock,
  },
  in_progress: {
    label: "In Progress",
    className: "bg-blue-50 text-blue-700 border-blue-200",
    icon: Loader2,
    animate: true,
  },
  awaiting_confirmation: {
    label: "Awaiting Review",
    className: "bg-amber-50 text-amber-700 border-amber-200",
    icon: AlertTriangle,
  },
  completed: {
    label: "Completed",
    className: "bg-green-50 text-green-700 border-green-200",
    icon: CheckCircle2,
  },
  success: {
    label: "Success",
    className: "bg-green-50 text-green-700 border-green-200",
    icon: CheckCircle2,
  },
  failed: {
    label: "Failed",
    className: "bg-red-50 text-red-700 border-red-200",
    icon: XCircle,
  },
  needs_review: {
    label: "Needs Review",
    className: "bg-yellow-50 text-yellow-700 border-yellow-200",
    icon: AlertCircle,
  },
  skipped: {
    label: "Skipped",
    className: "bg-gray-50 text-gray-500 border-gray-200",
    icon: HelpCircle,
  },
};

interface StatusBadgeProps {
  status: StatusType | string;
  label?: string;
  showIcon?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  tooltip?: string;
}

export function StatusBadge({
  status,
  label,
  showIcon = true,
  size = 'md',
  className,
  tooltip,
}: StatusBadgeProps) {
  // Get config, fallback to pending for unknown statuses
  const config = statusConfig[status as StatusType] || statusConfig.pending;
  const Icon = config.icon;
  const displayLabel = label || config.label;

  const sizeClasses = {
    sm: 'px-1.5 py-0.5 text-[10px] gap-1',
    md: 'px-2 py-0.5 text-xs gap-1.5',
    lg: 'px-2.5 py-1 text-sm gap-2',
  };

  const iconSizes = {
    sm: 'w-3 h-3',
    md: 'w-3.5 h-3.5',
    lg: 'w-4 h-4',
  };

  const badge = (
    <span
      className={cn(
        "inline-flex items-center font-medium rounded-full border transition-colors",
        sizeClasses[size],
        config.className,
        className
      )}
    >
      {showIcon && (
        <Icon
          className={cn(
            iconSizes[size],
            config.animate && "animate-spin"
          )}
        />
      )}
      {displayLabel}
    </span>
  );

  if (tooltip) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>{badge}</TooltipTrigger>
          <TooltipContent>
            <p>{tooltip}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return badge;
}

// Stage-specific status badge for interpretation stages
interface StageStatusBadgeProps {
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped';
  className?: string;
}

export function StageStatusBadge({ status, className }: StageStatusBadgeProps) {
  const stageStatusMap: Record<string, StatusType> = {
    pending: 'pending',
    running: 'in_progress',
    success: 'completed',
    failed: 'failed',
    skipped: 'skipped',
  };

  return (
    <StatusBadge
      status={stageStatusMap[status] || 'pending'}
      size="sm"
      className={className}
    />
  );
}

// Confidence-based status badge
interface ConfidenceStatusBadgeProps {
  confidence: number;
  className?: string;
}

export function ConfidenceStatusBadge({ confidence, className }: ConfidenceStatusBadgeProps) {
  const getConfidenceStatus = (c: number): { status: StatusType; label: string } => {
    if (c >= 0.9) return { status: 'completed', label: 'High' };
    if (c >= 0.7) return { status: 'needs_review', label: 'Medium' };
    return { status: 'failed', label: 'Low' };
  };

  const { status, label } = getConfidenceStatus(confidence);

  return (
    <StatusBadge
      status={status}
      label={`${label} (${Math.round(confidence * 100)}%)`}
      size="sm"
      showIcon={false}
      className={className}
    />
  );
}

// Extraction phase status badge
interface PhaseStatusBadgeProps {
  phase: string;
  className?: string;
}

export function PhaseStatusBadge({ phase, className }: PhaseStatusBadgeProps) {
  const phaseStatusMap: Record<string, { status: StatusType; label: string }> = {
    detecting_pages: { status: 'in_progress', label: 'Detecting Pages' },
    awaiting_page_confirmation: { status: 'awaiting_confirmation', label: 'Confirm Pages' },
    extracting: { status: 'in_progress', label: 'Extracting' },
    analyzing_merges: { status: 'in_progress', label: 'Analyzing' },
    awaiting_merge_confirmation: { status: 'awaiting_confirmation', label: 'Confirm Merges' },
    interpreting: { status: 'in_progress', label: 'Interpreting' },
    completed: { status: 'completed', label: 'Complete' },
    failed: { status: 'failed', label: 'Failed' },
  };

  const { status, label } = phaseStatusMap[phase] || { status: 'pending', label: phase };

  return (
    <StatusBadge
      status={status}
      label={label}
      className={className}
    />
  );
}
