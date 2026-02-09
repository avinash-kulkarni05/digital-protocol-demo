import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyMedia,
  EmptyContent,
} from "@/components/ui/empty";
import {
  Table2,
  FileText,
  Calendar,
  Sparkles,
  AlertCircle,
  RefreshCw,
  Upload,
  Layers,
  ClipboardList,
} from "lucide-react";

interface EmptyStateProps {
  className?: string;
  onAction?: () => void;
  actionLabel?: string;
}

/**
 * NoTablesExtracted - Shown when extraction finds no SOA tables
 */
export function NoTablesExtracted({
  className,
  onAction,
  actionLabel = "Retry Extraction",
}: EmptyStateProps) {
  return (
    <Empty className={cn("py-16 border border-dashed border-gray-200 rounded-2xl", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-gray-100">
          <Table2 className="w-6 h-6 text-gray-500" />
        </EmptyMedia>
        <EmptyTitle>No SOA Tables Found</EmptyTitle>
        <EmptyDescription>
          The extraction process did not find any Schedule of Activities tables in this protocol.
          Please verify the document contains SOA tables and try again.
        </EmptyDescription>
      </EmptyHeader>
      {onAction && (
        <EmptyContent>
          <Button variant="outline" onClick={onAction} className="gap-2">
            <RefreshCw className="w-4 h-4" />
            {actionLabel}
          </Button>
        </EmptyContent>
      )}
    </Empty>
  );
}

/**
 * NoActivitiesFound - Shown when a table has no activities
 */
export function NoActivitiesFound({
  className,
  onAction,
  actionLabel = "View Table Grid",
}: EmptyStateProps) {
  return (
    <Empty className={cn("py-12 border border-dashed border-gray-200 rounded-xl", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-gray-100">
          <ClipboardList className="w-6 h-6 text-gray-500" />
        </EmptyMedia>
        <EmptyTitle>No Activities Detected</EmptyTitle>
        <EmptyDescription>
          No activities were extracted from this table. Check the table grid
          to verify the structure was correctly identified.
        </EmptyDescription>
      </EmptyHeader>
      {onAction && (
        <EmptyContent>
          <Button variant="outline" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        </EmptyContent>
      )}
    </Empty>
  );
}

/**
 * NoFootnotesFound - Shown when a table has no footnotes
 */
export function NoFootnotesFound({ className }: EmptyStateProps) {
  return (
    <Empty className={cn("py-10 border border-dashed border-gray-200 rounded-xl", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-gray-100">
          <FileText className="w-6 h-6 text-gray-500" />
        </EmptyMedia>
        <EmptyTitle>No Footnotes</EmptyTitle>
        <EmptyDescription>
          No footnotes were found in this table. Footnotes provide additional
          context for visit scheduling and activity requirements.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

/**
 * NoVisitsFound - Shown when a table has no visits
 */
export function NoVisitsFound({ className }: EmptyStateProps) {
  return (
    <Empty className={cn("py-10 border border-dashed border-gray-200 rounded-xl", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-gray-100">
          <Calendar className="w-6 h-6 text-gray-500" />
        </EmptyMedia>
        <EmptyTitle>No Visits Detected</EmptyTitle>
        <EmptyDescription>
          No visit columns were identified in this table. The table structure
          may need manual review.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

/**
 * InterpretationPending - Shown before interpretation has started
 */
export function InterpretationPending({
  className,
  onAction,
  actionLabel = "Start Interpretation",
}: EmptyStateProps) {
  return (
    <Empty className={cn("py-16 border border-dashed border-gray-200 rounded-2xl", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-gray-100">
          <Sparkles className="w-6 h-6 text-gray-500" />
        </EmptyMedia>
        <EmptyTitle>Interpretation Not Started</EmptyTitle>
        <EmptyDescription>
          The 12-stage interpretation pipeline has not been run yet. Complete
          the review steps and confirm the merge plan to start interpretation.
        </EmptyDescription>
      </EmptyHeader>
      {onAction && (
        <EmptyContent>
          <Button onClick={onAction} className="gap-2">
            <Sparkles className="w-4 h-4" />
            {actionLabel}
          </Button>
        </EmptyContent>
      )}
    </Empty>
  );
}

/**
 * NoMergeGroups - Shown when no merge groups are available
 */
export function NoMergeGroups({
  className,
  onAction,
  actionLabel = "Analyze Merges",
}: EmptyStateProps) {
  return (
    <Empty className={cn("py-12 border border-dashed border-gray-200 rounded-xl", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-gray-100">
          <Layers className="w-6 h-6 text-gray-500" />
        </EmptyMedia>
        <EmptyTitle>No Merge Plan Available</EmptyTitle>
        <EmptyDescription>
          A merge plan needs to be generated to determine how tables should be
          combined before interpretation.
        </EmptyDescription>
      </EmptyHeader>
      {onAction && (
        <EmptyContent>
          <Button variant="outline" onClick={onAction} className="gap-2">
            <Layers className="w-4 h-4" />
            {actionLabel}
          </Button>
        </EmptyContent>
      )}
    </Empty>
  );
}

/**
 * ExtractionError - Shown when extraction fails
 */
export function ExtractionError({
  className,
  onAction,
  actionLabel = "Retry",
  errorMessage,
}: EmptyStateProps & { errorMessage?: string }) {
  return (
    <Empty className={cn("py-16 border border-dashed border-red-200 rounded-2xl bg-red-50/30", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-red-100">
          <AlertCircle className="w-6 h-6 text-red-600" />
        </EmptyMedia>
        <EmptyTitle className="text-red-800">Extraction Failed</EmptyTitle>
        <EmptyDescription className="text-red-600">
          {errorMessage || "An error occurred during extraction. Please try again or contact support if the issue persists."}
        </EmptyDescription>
      </EmptyHeader>
      {onAction && (
        <EmptyContent>
          <Button variant="outline" onClick={onAction} className="gap-2 border-red-300 text-red-700 hover:bg-red-50">
            <RefreshCw className="w-4 h-4" />
            {actionLabel}
          </Button>
        </EmptyContent>
      )}
    </Empty>
  );
}

/**
 * NoProtocolSelected - Shown when no protocol is selected for SOA analysis
 */
export function NoProtocolSelected({
  className,
  onAction,
  actionLabel = "Upload Protocol",
}: EmptyStateProps) {
  return (
    <Empty className={cn("py-20 border border-dashed border-gray-200 rounded-2xl", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-gray-100">
          <Upload className="w-6 h-6 text-gray-500" />
        </EmptyMedia>
        <EmptyTitle>No Protocol Selected</EmptyTitle>
        <EmptyDescription>
          Select a protocol from your uploads or upload a new protocol PDF
          to begin SOA analysis.
        </EmptyDescription>
      </EmptyHeader>
      {onAction && (
        <EmptyContent>
          <Button onClick={onAction} className="gap-2">
            <Upload className="w-4 h-4" />
            {actionLabel}
          </Button>
        </EmptyContent>
      )}
    </Empty>
  );
}

/**
 * AwaitingPageConfirmation - Shown when waiting for user to confirm detected pages
 */
export function AwaitingPageConfirmation({
  className,
  detectedPages,
  onConfirm,
  onEdit,
}: EmptyStateProps & {
  detectedPages?: number;
  onConfirm?: () => void;
  onEdit?: () => void;
}) {
  return (
    <Empty className={cn("py-12 border border-amber-200 rounded-2xl bg-amber-50/30", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-amber-100">
          <FileText className="w-6 h-6 text-amber-600" />
        </EmptyMedia>
        <EmptyTitle className="text-amber-800">Confirm Detected Pages</EmptyTitle>
        <EmptyDescription className="text-amber-700">
          {detectedPages
            ? `${detectedPages} SOA page${detectedPages > 1 ? 's' : ''} detected. Please review and confirm the page selection.`
            : "Please review and confirm the detected SOA pages before continuing."}
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <div className="flex gap-2">
          {onEdit && (
            <Button variant="outline" onClick={onEdit} size="sm">
              Edit Selection
            </Button>
          )}
          {onConfirm && (
            <Button onClick={onConfirm} size="sm">
              Confirm Pages
            </Button>
          )}
        </div>
      </EmptyContent>
    </Empty>
  );
}
