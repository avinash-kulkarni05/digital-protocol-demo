import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

interface SkeletonProps {
  className?: string;
}

/**
 * TableGridSkeleton - Mimics the SOA table grid layout
 */
export function TableGridSkeleton({ className }: SkeletonProps) {
  return (
    <div className={cn("border rounded-xl bg-white p-4 space-y-3", className)}>
      {/* Table Header */}
      <div className="flex gap-2">
        {/* Activity column header */}
        <Skeleton className="h-10 w-48 rounded-lg" />
        {/* Visit column headers */}
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-20 rounded-lg" />
        ))}
      </div>

      {/* Table Rows */}
      {Array.from({ length: 8 }).map((_, row) => (
        <div key={row} className="flex gap-2">
          {/* Activity name */}
          <Skeleton className="h-8 w-48 rounded-md" />
          {/* Cell values */}
          {Array.from({ length: 6 }).map((_, col) => (
            <Skeleton key={col} className="h-8 w-20 rounded-md" />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * VisitTimelineSkeleton - Mimics the visits/activities timeline view
 */
export function VisitTimelineSkeleton({ className }: SkeletonProps) {
  return (
    <div className={cn("space-y-4", className)}>
      {/* Timeline Header */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-8 w-48 rounded-lg" />
        <Skeleton className="h-6 w-24 rounded-full" />
      </div>

      {/* Visit Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-gray-200 bg-white p-4 space-y-3"
          >
            {/* Visit Header */}
            <div className="flex items-center justify-between">
              <Skeleton className="h-6 w-24 rounded-md" />
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>

            {/* Timing Info */}
            <div className="flex gap-2">
              <Skeleton className="h-4 w-20 rounded-md" />
              <Skeleton className="h-4 w-16 rounded-md" />
            </div>

            {/* Activities */}
            <div className="space-y-2 pt-2 border-t border-gray-100">
              {Array.from({ length: 3 }).map((_, j) => (
                <div key={j} className="flex items-center gap-2">
                  <Skeleton className="h-4 w-4 rounded-full" />
                  <Skeleton className="h-4 w-full rounded-md" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * FootnotesSkeleton - Mimics the footnotes panel layout
 */
export function FootnotesSkeleton({ className }: SkeletonProps) {
  return (
    <div className={cn("space-y-3", className)}>
      {/* Footnotes Header */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-6 w-32 rounded-md" />
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>

      {/* Footnote Items */}
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="rounded-lg border border-gray-200 bg-white p-4 space-y-2"
        >
          {/* Marker and Category */}
          <div className="flex items-center gap-3">
            <Skeleton className="h-6 w-6 rounded-full" />
            <Skeleton className="h-5 w-24 rounded-full" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>

          {/* Footnote Text */}
          <Skeleton className="h-4 w-full rounded-md" />
          <Skeleton className="h-4 w-3/4 rounded-md" />
        </div>
      ))}
    </div>
  );
}

/**
 * MergeGroupSkeleton - Mimics the merge group cards layout
 */
export function MergeGroupSkeleton({ className }: SkeletonProps) {
  return (
    <div className={cn("space-y-4", className)}>
      {/* Header Stats */}
      <div className="flex items-center gap-4">
        <Skeleton className="h-8 w-32 rounded-lg" />
        <Skeleton className="h-6 w-20 rounded-full" />
        <Skeleton className="h-6 w-24 rounded-full" />
      </div>

      {/* Merge Groups */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-gray-200 bg-white p-4 space-y-4"
          >
            {/* Group Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Skeleton className="h-6 w-16 rounded-md" />
                <Skeleton className="h-5 w-24 rounded-full" />
              </div>
              <Skeleton className="h-5 w-12 rounded-full" />
            </div>

            {/* Reasoning */}
            <Skeleton className="h-4 w-full rounded-md" />

            {/* Table Items */}
            <div className="space-y-2">
              {Array.from({ length: 2 }).map((_, j) => (
                <div
                  key={j}
                  className="flex items-center gap-3 p-2 rounded-lg bg-gray-50"
                >
                  <Skeleton className="h-4 w-4 rounded" />
                  <Skeleton className="h-4 w-20 rounded-md" />
                  <Skeleton className="h-4 w-16 rounded-full" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * InterpretationSkeleton - Mimics the interpretation stages layout
 */
export function InterpretationSkeleton({ className }: SkeletonProps) {
  return (
    <div className={cn("space-y-6", className)}>
      {/* Header Card */}
      <div className="rounded-2xl border border-gray-200 bg-white p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <Skeleton className="h-7 w-48 rounded-lg" />
            <Skeleton className="h-4 w-32 rounded-md" />
          </div>
          <Skeleton className="h-8 w-24 rounded-full" />
        </div>
      </div>

      {/* Summary Stats */}
      <div className="rounded-xl bg-gray-50 border border-gray-200 p-4">
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex flex-col items-center gap-2">
              <Skeleton className="h-8 w-12 rounded-lg" />
              <Skeleton className="h-3 w-16 rounded-md" />
            </div>
          ))}
        </div>
      </div>

      {/* Stage Cards */}
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="rounded-lg border border-gray-200 bg-white p-3 flex items-center justify-between"
          >
            <div className="flex items-center gap-3">
              <Skeleton className="h-6 w-6 rounded-full" />
              <div className="space-y-1">
                <Skeleton className="h-4 w-32 rounded-md" />
                <Skeleton className="h-3 w-48 rounded-md" />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Skeleton className="h-3 w-10 rounded-md" />
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * WizardStepSkeleton - Mimics the wizard step content area
 */
export function WizardStepSkeleton({ className }: SkeletonProps) {
  return (
    <div className={cn("space-y-6", className)}>
      {/* Step Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-8 w-56 rounded-lg" />
          <Skeleton className="h-4 w-72 rounded-md" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-9 w-24 rounded-lg" />
          <Skeleton className="h-9 w-24 rounded-lg" />
        </div>
      </div>

      {/* Content Area */}
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="space-y-4">
          <Skeleton className="h-6 w-40 rounded-md" />
          <Skeleton className="h-48 w-full rounded-lg" />
          <div className="flex gap-4">
            <Skeleton className="h-4 w-24 rounded-md" />
            <Skeleton className="h-4 w-32 rounded-md" />
            <Skeleton className="h-4 w-20 rounded-md" />
          </div>
        </div>
      </div>
    </div>
  );
}
