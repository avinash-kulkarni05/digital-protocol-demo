import { FileText, AlertTriangle, Shield, Activity } from "lucide-react";

interface SafetyMonitoringProps {
  id?: string;
  name?: string;
  description?: string;
  frequency?: string;
  responsibleParty?: string;
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
}

interface AdverseEventCategoryProps {
  id?: string;
  name?: string;
  description?: string;
  reportingRequirements?: string;
  timeframe?: string;
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
}

interface SafetyCardProps {
  title: string;
  description?: string;
  monitoringItems?: SafetyMonitoringProps[];
  adverseEventCategories?: AdverseEventCategoryProps[];
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
  onViewSource?: (page: number) => void;
}

export function SafetyCard({
  title,
  description,
  monitoringItems,
  adverseEventCategories,
  provenance,
  onViewSource
}: SafetyCardProps) {
  return (
    <div className="glass-card overflow-hidden">
      <div className="p-5 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield className="w-5 h-5 text-gray-600" />
          <div>
            <h4 className="text-sf-headline font-semibold text-foreground">{title}</h4>
            {description && (
              <p className="text-sf-footnote text-muted-foreground mt-0.5">{description}</p>
            )}
          </div>
        </div>
        {provenance?.page_number && (
          <button
            onClick={() => onViewSource?.(provenance.page_number!)}
            className="provenance-chip"
            data-testid={`provenance-safety-${title}`}
          >
            <FileText className="w-3 h-3" />
            <span>p. {provenance.page_number}</span>
          </button>
        )}
      </div>

      {monitoringItems && monitoringItems.length > 0 && (
        <div className="p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-gray-600" />
            <span className="text-sf-caption text-muted-foreground uppercase tracking-wider font-medium">
              Monitoring Activities ({monitoringItems.length})
            </span>
          </div>
          <div className="space-y-2">
            {monitoringItems.map((item, idx) => (
              <div 
                key={item.id || idx}
                className="bg-gray-50/80 rounded-lg p-3 flex items-start justify-between gap-3"
              >
                <div className="space-y-1 flex-1">
                  <h5 className="text-sf-callout font-medium text-foreground">
                    {item.name || `Activity ${idx + 1}`}
                  </h5>
                  {item.description && (
                    <p className="text-sf-footnote text-muted-foreground">{item.description}</p>
                  )}
                  {(item.frequency || item.responsibleParty) && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {item.frequency && (
                        <span className="text-xs bg-white border border-gray-200 rounded-full px-2 py-0.5 text-muted-foreground">
                          {item.frequency}
                        </span>
                      )}
                      {item.responsibleParty && (
                        <span className="text-xs bg-white border border-gray-200 rounded-full px-2 py-0.5 text-muted-foreground">
                          {item.responsibleParty}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                {item.provenance?.page_number && (
                  <button
                    onClick={() => onViewSource?.(item.provenance!.page_number!)}
                    className="provenance-chip text-xs shrink-0"
                  >
                    <FileText className="w-3 h-3" />
                    <span>p. {item.provenance.page_number}</span>
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {adverseEventCategories && adverseEventCategories.length > 0 && (
        <div className="p-5 border-t border-gray-100 space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-gray-600" />
            <span className="text-sf-caption text-muted-foreground uppercase tracking-wider font-medium">
              Adverse Event Categories ({adverseEventCategories.length})
            </span>
          </div>
          <div className="space-y-2">
            {adverseEventCategories.map((category, idx) => (
              <div 
                key={category.id || idx}
                className="bg-gray-50/50 border border-gray-200 rounded-lg p-3 flex items-start justify-between gap-3"
              >
                <div className="space-y-1 flex-1">
                  <h5 className="text-sf-callout font-medium text-foreground">
                    {category.name || `Category ${idx + 1}`}
                  </h5>
                  {category.description && (
                    <p className="text-sf-footnote text-muted-foreground">{category.description}</p>
                  )}
                  {(category.reportingRequirements || category.timeframe) && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {category.reportingRequirements && (
                        <span className="text-xs bg-white border border-gray-200 rounded-full px-2 py-0.5 text-gray-700">
                          {category.reportingRequirements}
                        </span>
                      )}
                      {category.timeframe && (
                        <span className="text-xs bg-white border border-gray-200 rounded-full px-2 py-0.5 text-gray-700">
                          {category.timeframe}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                {category.provenance?.page_number && (
                  <button
                    onClick={() => onViewSource?.(category.provenance!.page_number!)}
                    className="provenance-chip text-xs shrink-0"
                  >
                    <FileText className="w-3 h-3" />
                    <span>p. {category.provenance.page_number}</span>
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
