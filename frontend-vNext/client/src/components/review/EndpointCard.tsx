import { FileText, Target, TrendingUp, BarChart3 } from "lucide-react";

interface EndpointProps {
  id?: string;
  name?: string;
  text?: string;
  description?: string;
  level?: {
    code?: string;
    decode?: string;
  };
  measure?: string;
  timeFrame?: string;
  analysisPopulation?: string;
  provenance?: {
    page_number?: number;
    section_number?: string;
    text_snippet?: string;
  };
}

interface ObjectiveProps {
  id?: string;
  name?: string;
  text?: string;
  level?: {
    code?: string;
    decode?: string;
  };
  endpoint_ids?: string[];
  provenance?: {
    page_number?: number;
    section_number?: string;
    text_snippet?: string;
  };
}

interface EndpointCardProps {
  objective?: ObjectiveProps;
  endpoints?: EndpointProps[];
  onViewSource?: (page: number) => void;
}

export function EndpointCard({
  objective,
  endpoints,
  onViewSource
}: EndpointCardProps) {
  const getLevelIcon = (level?: string) => {
    switch (level?.toLowerCase()) {
      case 'primary':
        return <Target className="w-4 h-4 text-gray-900" />;
      case 'secondary':
        return <TrendingUp className="w-4 h-4 text-gray-900" />;
      case 'exploratory':
        return <BarChart3 className="w-4 h-4 text-gray-900" />;
      default:
        return <Target className="w-4 h-4 text-gray-500" />;
    }
  };

  const getLevelBadgeColor = (level?: string) => {
    switch (level?.toLowerCase()) {
      case 'primary':
        return 'bg-gray-100 text-gray-700 border-gray-200';
      case 'secondary':
        return 'bg-gray-100 text-gray-700 border-gray-200';
      case 'exploratory':
        return 'bg-gray-100 text-gray-700 border-gray-200';
      default:
        return 'bg-gray-100 text-gray-600 border-gray-200';
    }
  };

  return (
    <div className="glass-card overflow-hidden">
      {objective && (
        <div className="p-5 border-b border-gray-100">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              {getLevelIcon(objective.level?.decode)}
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <h4 className="text-sf-headline font-semibold text-foreground">
                    {objective.name || "Objective"}
                  </h4>
                  {objective.level?.decode && (
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${getLevelBadgeColor(objective.level.decode)}`}>
                      {objective.level.decode}
                    </span>
                  )}
                </div>
                <p className="text-sf-body text-foreground">{objective.text}</p>
              </div>
            </div>
            {objective.provenance?.page_number && (
              <button
                onClick={() => onViewSource?.(objective.provenance!.page_number!)}
                className="provenance-chip shrink-0"
                data-testid={`provenance-objective-${objective.id}`}
              >
                <FileText className="w-3 h-3" />
                <span>p. {objective.provenance.page_number}</span>
              </button>
            )}
          </div>
        </div>
      )}

      {endpoints && endpoints.length > 0 && (
        <div className="p-5 space-y-3">
          <span className="text-sf-caption text-muted-foreground uppercase tracking-wider font-medium">
            Related Endpoints ({endpoints.length})
          </span>
          <div className="space-y-3">
            {endpoints.map((endpoint, idx) => (
              <div 
                key={endpoint.id || idx}
                className="bg-gray-50/80 rounded-lg p-4 space-y-2"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1 flex-1">
                    <h5 className="text-sf-callout font-medium text-foreground">
                      {endpoint.name || endpoint.text || `Endpoint ${idx + 1}`}
                    </h5>
                    {endpoint.description && endpoint.description !== endpoint.name && (
                      <p className="text-sf-footnote text-muted-foreground">{endpoint.description}</p>
                    )}
                  </div>
                  {endpoint.provenance?.page_number && (
                    <button
                      onClick={() => onViewSource?.(endpoint.provenance!.page_number!)}
                      className="provenance-chip text-xs shrink-0"
                      data-testid={`provenance-endpoint-${endpoint.id}`}
                    >
                      <FileText className="w-3 h-3" />
                      <span>p. {endpoint.provenance.page_number}</span>
                    </button>
                  )}
                </div>

                {(endpoint.measure || endpoint.timeFrame || endpoint.analysisPopulation) && (
                  <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-200/50">
                    {endpoint.measure && (
                      <span className="text-xs bg-white border border-gray-200 rounded-full px-2 py-0.5 text-muted-foreground">
                        {endpoint.measure}
                      </span>
                    )}
                    {endpoint.timeFrame && (
                      <span className="text-xs bg-white border border-gray-200 rounded-full px-2 py-0.5 text-muted-foreground">
                        {endpoint.timeFrame}
                      </span>
                    )}
                    {endpoint.analysisPopulation && (
                      <span className="text-xs bg-white border border-gray-200 rounded-full px-2 py-0.5 text-muted-foreground">
                        {endpoint.analysisPopulation}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface EndpointListProps {
  objectives?: ObjectiveProps[];
  endpoints?: EndpointProps[];
  onViewSource?: (page: number) => void;
}

export function EndpointList({
  objectives,
  endpoints,
  onViewSource
}: EndpointListProps) {
  if (!objectives || objectives.length === 0) {
    return null;
  }

  const getEndpointsForObjective = (endpointIds?: string[]) => {
    if (!endpointIds || !endpoints) return [];
    return endpoints.filter(ep => endpointIds.includes(ep.id || ''));
  };

  const groupedByLevel = {
    primary: objectives.filter(o => o.level?.decode?.toLowerCase() === 'primary'),
    secondary: objectives.filter(o => o.level?.decode?.toLowerCase() === 'secondary'),
    exploratory: objectives.filter(o => o.level?.decode?.toLowerCase() === 'exploratory'),
    other: objectives.filter(o => 
      !['primary', 'secondary', 'exploratory'].includes(o.level?.decode?.toLowerCase() || '')
    )
  };

  return (
    <div className="space-y-6">
      {groupedByLevel.primary.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sf-headline font-semibold text-foreground">Primary Objectives</h3>
          {groupedByLevel.primary.map((obj, idx) => (
            <EndpointCard
              key={obj.id || idx}
              objective={obj}
              endpoints={getEndpointsForObjective(obj.endpoint_ids)}
              onViewSource={onViewSource}
            />
          ))}
        </div>
      )}

      {groupedByLevel.secondary.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sf-headline font-semibold text-foreground">Secondary Objectives</h3>
          {groupedByLevel.secondary.map((obj, idx) => (
            <EndpointCard
              key={obj.id || idx}
              objective={obj}
              endpoints={getEndpointsForObjective(obj.endpoint_ids)}
              onViewSource={onViewSource}
            />
          ))}
        </div>
      )}

      {groupedByLevel.exploratory.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sf-headline font-semibold text-foreground">Exploratory Objectives</h3>
          {groupedByLevel.exploratory.map((obj, idx) => (
            <EndpointCard
              key={obj.id || idx}
              objective={obj}
              endpoints={getEndpointsForObjective(obj.endpoint_ids)}
              onViewSource={onViewSource}
            />
          ))}
        </div>
      )}

      {groupedByLevel.other.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sf-headline font-semibold text-foreground">Other Objectives</h3>
          {groupedByLevel.other.map((obj, idx) => (
            <EndpointCard
              key={obj.id || idx}
              objective={obj}
              endpoints={getEndpointsForObjective(obj.endpoint_ids)}
              onViewSource={onViewSource}
            />
          ))}
        </div>
      )}
    </div>
  );
}
