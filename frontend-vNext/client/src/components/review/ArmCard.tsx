import { FileText, Pill, Clock, Beaker } from "lucide-react";

interface DosingRegimen {
  dose?: number;
  doseUnit?: string;
  frequency?: string;
  route?: {
    code?: string;
    decode?: string;
  };
  cycleLengthDays?: number;
  infusionDurationMinutes?: number;
  doseCalculationBasis?: string;
}

interface Intervention {
  id?: string;
  name?: string;
  type?: string;
  role?: {
    decode?: string;
  };
  drugClass?: string;
  dosingRegimen?: DosingRegimen;
  isBlinded?: boolean;
  isPlacebo?: boolean;
  isComparator?: boolean;
  biomedicalConcept?: {
    conceptName?: string;
  };
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
}

interface ArmCardProps {
  armName: string;
  armType?: string;
  description?: string;
  interventions?: Intervention[];
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
  onViewSource?: (page: number) => void;
}

export function ArmCard({
  armName,
  armType,
  description,
  interventions,
  provenance,
  onViewSource
}: ArmCardProps) {
  const getRoleBadgeColor = (role?: string) => {
    switch (role?.toLowerCase()) {
      case 'investigational':
        return 'bg-gray-100 text-gray-700';
      case 'comparator':
        return 'bg-gray-100 text-gray-700';
      case 'placebo':
        return 'bg-gray-100 text-gray-600';
      default:
        return 'bg-gray-100 text-gray-600';
    }
  };

  return (
    <div className="glass-card overflow-hidden">
      <div className="p-5 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h4 className="text-sf-headline font-semibold text-foreground">{armName}</h4>
          {armType && (
            <span className="text-sf-caption text-muted-foreground">{armType}</span>
          )}
        </div>
        {provenance?.page_number && (
          <button
            onClick={() => onViewSource?.(provenance.page_number!)}
            className="provenance-chip"
            data-testid={`provenance-arm-${armName}`}
          >
            <FileText className="w-3 h-3" />
            <span>p. {provenance.page_number}</span>
          </button>
        )}
      </div>

      {description && (
        <div className="px-5 py-3 bg-gray-50/50 border-b border-gray-100">
          <p className="text-sf-footnote text-muted-foreground">{description}</p>
        </div>
      )}

      {interventions && interventions.length > 0 && (
        <div className="p-5 space-y-4">
          {interventions.map((intervention, idx) => (
            <div 
              key={intervention.id || idx} 
              className="bg-white border border-gray-100 rounded-lg p-4 space-y-3"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Pill className="w-4 h-4 text-gray-600" />
                  <span className="text-sf-body font-semibold text-foreground">
                    {intervention.name || "Unnamed Intervention"}
                  </span>
                </div>
                {intervention.role?.decode && (
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${getRoleBadgeColor(intervention.role.decode)}`}>
                    {intervention.role.decode}
                  </span>
                )}
              </div>

              {intervention.drugClass && (
                <p className="text-sf-footnote text-muted-foreground flex items-center gap-1">
                  <Beaker className="w-3 h-3" />
                  {intervention.drugClass}
                </p>
              )}

              {intervention.dosingRegimen && (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3 pt-2 border-t border-gray-100">
                  {intervention.dosingRegimen.dose !== undefined && (
                    <div>
                      <span className="text-sf-caption text-muted-foreground uppercase tracking-wider block">Dose</span>
                      <span className="text-sf-callout font-medium text-foreground">
                        {intervention.dosingRegimen.dose} {intervention.dosingRegimen.doseUnit || ""}
                      </span>
                    </div>
                  )}
                  {intervention.dosingRegimen.frequency && (
                    <div>
                      <span className="text-sf-caption text-muted-foreground uppercase tracking-wider block">Frequency</span>
                      <span className="text-sf-callout font-medium text-foreground">
                        {intervention.dosingRegimen.frequency}
                      </span>
                    </div>
                  )}
                  {intervention.dosingRegimen.route?.decode && (
                    <div>
                      <span className="text-sf-caption text-muted-foreground uppercase tracking-wider block">Route</span>
                      <span className="text-sf-callout font-medium text-foreground">
                        {intervention.dosingRegimen.route.decode}
                      </span>
                    </div>
                  )}
                  {intervention.dosingRegimen.cycleLengthDays && (
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-muted-foreground" />
                      <span className="text-sf-footnote text-muted-foreground">
                        {intervention.dosingRegimen.cycleLengthDays}-day cycle
                      </span>
                    </div>
                  )}
                  {intervention.dosingRegimen.infusionDurationMinutes && (
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-muted-foreground" />
                      <span className="text-sf-footnote text-muted-foreground">
                        {intervention.dosingRegimen.infusionDurationMinutes} min infusion
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
