import { FileText } from "lucide-react";

interface PopulationOverviewProps {
  targetDisease?: {
    name?: string;
    stage?: string;
  };
  ageRange?: {
    minAge?: number;
    maxAge?: number;
    maxAgeNoLimit?: boolean;
    unit?: string;
  };
  sex?: {
    allowed?: Array<{
      code?: string;
      decode?: string;
      provenance?: {
        page_number?: number;
        text_snippet?: string;
      };
    }>;
  };
  performanceStatus?: {
    scale?: string;
    allowedValues?: number[];
    provenance?: {
      page_number?: number;
      text_snippet?: string;
    };
  };
  enrollmentTarget?: {
    planned?: number;
    description?: string;
  };
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
  onViewSource?: (page: number) => void;
}

export function PopulationOverview({
  targetDisease,
  ageRange,
  sex,
  performanceStatus,
  enrollmentTarget,
  provenance,
  onViewSource
}: PopulationOverviewProps) {
  const formatAgeRange = () => {
    if (!ageRange) return "Not specified";
    const min = ageRange.minAge ? `${ageRange.minAge}` : "0";
    const max = ageRange.maxAgeNoLimit ? "No upper limit" : (ageRange.maxAge ? `${ageRange.maxAge}` : "No limit");
    const unit = ageRange.unit || "years";
    return `${min}+ ${unit}${ageRange.maxAgeNoLimit ? "" : ` (max: ${max})`}`;
  };

  const formatSex = () => {
    if (!sex?.allowed || sex.allowed.length === 0) return "Not specified";
    return sex.allowed.map(s => s.decode).join(", ");
  };

  const formatPerformanceStatus = () => {
    if (!performanceStatus) return "Not specified";
    const scale = performanceStatus.scale || "Unknown";
    const values = performanceStatus.allowedValues?.join(", ") || "Not specified";
    return `${scale} ${values}`;
  };

  return (
    <div className="glass-card p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h4 className="text-sf-headline font-semibold text-foreground">Population Overview</h4>
        {provenance?.page_number && (
          <button
            onClick={() => onViewSource?.(provenance.page_number!)}
            className="provenance-chip"
            data-testid="provenance-population-overview"
          >
            <FileText className="w-3 h-3" />
            <span>p. {provenance.page_number}</span>
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {targetDisease && (
          <div className="space-y-1">
            <span className="text-sf-caption text-muted-foreground uppercase tracking-wider font-medium">Target Disease</span>
            <p className="text-sf-body text-foreground font-medium">{targetDisease.name || "Not specified"}</p>
            {targetDisease.stage && (
              <p className="text-sf-footnote text-muted-foreground">{targetDisease.stage}</p>
            )}
          </div>
        )}

        <div className="space-y-1">
          <span className="text-sf-caption text-muted-foreground uppercase tracking-wider font-medium">Age Range</span>
          <p className="text-sf-body text-foreground font-medium">{formatAgeRange()}</p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-sf-caption text-muted-foreground uppercase tracking-wider font-medium">Sex Eligibility</span>
            {sex?.allowed?.[0]?.provenance?.page_number && (
              <button
                onClick={() => onViewSource?.(sex.allowed![0].provenance!.page_number!)}
                className="provenance-chip text-xs"
                data-testid="provenance-sex"
              >
                <FileText className="w-3 h-3" />
                <span>p. {sex.allowed[0].provenance.page_number}</span>
              </button>
            )}
          </div>
          <p className="text-sf-body text-foreground font-medium">{formatSex()}</p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-sf-caption text-muted-foreground uppercase tracking-wider font-medium">Performance Status</span>
            {performanceStatus?.provenance?.page_number && (
              <button
                onClick={() => onViewSource?.(performanceStatus.provenance!.page_number!)}
                className="provenance-chip text-xs"
                data-testid="provenance-performance"
              >
                <FileText className="w-3 h-3" />
                <span>p. {performanceStatus.provenance.page_number}</span>
              </button>
            )}
          </div>
          <p className="text-sf-body text-foreground font-medium">{formatPerformanceStatus()}</p>
        </div>

        {enrollmentTarget && (
          <div className="space-y-1 md:col-span-2">
            <span className="text-sf-caption text-muted-foreground uppercase tracking-wider font-medium">Enrollment Target</span>
            <p className="text-sf-body text-foreground font-medium">
              {enrollmentTarget.planned ? `${enrollmentTarget.planned} subjects` : "Not specified"}
            </p>
            {enrollmentTarget.description && (
              <p className="text-sf-footnote text-muted-foreground">{enrollmentTarget.description}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
