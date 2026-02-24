import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

type ConfidenceLevel = 'high' | 'medium' | 'low';

interface ConfidenceConfig {
  label: string;
  barColor: string;
  textColor: string;
  bgColor: string;
  borderColor: string;
}

const confidenceConfig: Record<ConfidenceLevel, ConfidenceConfig> = {
  high: {
    label: 'High Confidence',
    barColor: 'bg-green-500',
    textColor: 'text-green-700',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
  },
  medium: {
    label: 'Medium Confidence',
    barColor: 'bg-amber-500',
    textColor: 'text-amber-700',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
  },
  low: {
    label: 'Low Confidence',
    barColor: 'bg-red-500',
    textColor: 'text-red-700',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
  },
};

function getConfidenceLevel(confidence: number): ConfidenceLevel {
  if (confidence >= 0.9) return 'high';
  if (confidence >= 0.7) return 'medium';
  return 'low';
}

interface ConfidenceIndicatorProps {
  confidence: number; // 0.0 to 1.0
  reasoning?: string;
  showLabel?: boolean;
  showPercentage?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function ConfidenceIndicator({
  confidence,
  reasoning,
  showLabel = false,
  showPercentage = true,
  size = 'md',
  className,
}: ConfidenceIndicatorProps) {
  const level = getConfidenceLevel(confidence);
  const config = confidenceConfig[level];
  const percentage = Math.round(confidence * 100);

  const sizeClasses = {
    sm: { bar: 'h-1 w-12', text: 'text-[10px]', gap: 'gap-1' },
    md: { bar: 'h-1.5 w-16', text: 'text-xs', gap: 'gap-1.5' },
    lg: { bar: 'h-2 w-20', text: 'text-sm', gap: 'gap-2' },
  };

  const indicator = (
    <div className={cn("flex items-center", sizeClasses[size].gap, className)}>
      {/* Progress Bar */}
      <div className={cn("rounded-full bg-gray-200 overflow-hidden", sizeClasses[size].bar)}>
        <div
          className={cn("h-full rounded-full transition-all duration-500", config.barColor)}
          style={{ width: `${percentage}%` }}
        />
      </div>

      {/* Percentage/Label */}
      <span className={cn("font-medium", sizeClasses[size].text, config.textColor)}>
        {showPercentage && `${percentage}%`}
        {showLabel && !showPercentage && config.label}
        {showLabel && showPercentage && ` ${level}`}
      </span>
    </div>
  );

  if (reasoning) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="cursor-help">{indicator}</div>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">
            <p className="font-medium">{config.label}</p>
            <p className="text-xs text-muted-foreground mt-1">{reasoning}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return indicator;
}

// Badge-style confidence indicator
interface ConfidenceBadgeProps {
  confidence: number;
  reasoning?: string;
  className?: string;
}

export function ConfidenceBadge({ confidence, reasoning, className }: ConfidenceBadgeProps) {
  const level = getConfidenceLevel(confidence);
  const config = confidenceConfig[level];
  const percentage = Math.round(confidence * 100);

  const badge = (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border",
        config.bgColor,
        config.textColor,
        config.borderColor,
        className
      )}
    >
      <span
        className={cn("w-1.5 h-1.5 rounded-full", config.barColor)}
      />
      {percentage}%
    </span>
  );

  if (reasoning) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-help">{badge}</span>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">
            <p className="font-medium">{config.label}</p>
            <p className="text-xs text-muted-foreground mt-1">{reasoning}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return badge;
}

// Circular confidence gauge
interface ConfidenceGaugeProps {
  confidence: number;
  size?: number;
  strokeWidth?: number;
  className?: string;
}

export function ConfidenceGauge({
  confidence,
  size = 40,
  strokeWidth = 4,
  className,
}: ConfidenceGaugeProps) {
  const level = getConfidenceLevel(confidence);
  const config = confidenceConfig[level];
  const percentage = Math.round(confidence * 100);

  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (confidence * circumference);

  // Map bar color to stroke color
  const strokeColorMap: Record<ConfidenceLevel, string> = {
    high: '#22c55e', // green-500
    medium: '#f59e0b', // amber-500
    low: '#ef4444', // red-500
  };

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)}>
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#e5e5e5"
          strokeWidth={strokeWidth}
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={strokeColorMap[level]}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-500"
        />
      </svg>
      <span className={cn("absolute text-xs font-semibold", config.textColor)}>
        {percentage}
      </span>
    </div>
  );
}

// Mini inline confidence indicator
interface ConfidenceDotProps {
  confidence: number;
  showTooltip?: boolean;
  className?: string;
}

export function ConfidenceDot({ confidence, showTooltip = true, className }: ConfidenceDotProps) {
  const level = getConfidenceLevel(confidence);
  const config = confidenceConfig[level];
  const percentage = Math.round(confidence * 100);

  const dot = (
    <span
      className={cn("inline-block w-2 h-2 rounded-full", config.barColor, className)}
    />
  );

  if (showTooltip) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-help">{dot}</span>
          </TooltipTrigger>
          <TooltipContent>
            <p>{config.label}: {percentage}%</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return dot;
}
