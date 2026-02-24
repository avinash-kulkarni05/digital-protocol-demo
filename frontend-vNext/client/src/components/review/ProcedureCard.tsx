import { FileText, CheckCircle2, Circle, AlertCircle } from "lucide-react";

interface ProcedureItemProps {
  id?: string;
  name?: string;
  description?: string;
  status?: string;
  required?: boolean;
  responsible?: string;
  timing?: string;
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
}

interface ProcedureCardProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  items?: ProcedureItemProps[];
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
  onViewSource?: (page: number) => void;
}

export function ProcedureCard({
  title,
  description,
  icon,
  items,
  provenance,
  onViewSource
}: ProcedureCardProps) {
  const getStatusIcon = (status?: string, required?: boolean) => {
    if (required) {
      return <AlertCircle className="w-4 h-4 text-gray-600" />;
    }
    switch (status?.toLowerCase()) {
      case 'completed':
      case 'required':
        return <CheckCircle2 className="w-4 h-4 text-gray-600" />;
      default:
        return <Circle className="w-4 h-4 text-gray-300" />;
    }
  };

  return (
    <div className="glass-card overflow-hidden">
      <div className="p-5 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {icon && <div className="text-gray-600">{icon}</div>}
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
            data-testid={`provenance-procedure-${title}`}
          >
            <FileText className="w-3 h-3" />
            <span>p. {provenance.page_number}</span>
          </button>
        )}
      </div>

      {items && items.length > 0 && (
        <div className="divide-y divide-gray-100">
          {items.map((item, idx) => (
            <div 
              key={item.id || idx}
              className="p-4 flex items-start gap-3 hover:bg-gray-50/50 transition-colors"
            >
              {getStatusIcon(item.status, item.required)}
              <div className="flex-1 space-y-1">
                <div className="flex items-start justify-between gap-3">
                  <h5 className="text-sf-callout font-medium text-foreground">
                    {item.name || `Item ${idx + 1}`}
                  </h5>
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
                {item.description && (
                  <p className="text-sf-footnote text-muted-foreground">{item.description}</p>
                )}
                {(item.responsible || item.timing) && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {item.responsible && (
                      <span className="text-xs bg-gray-100 rounded-full px-2 py-0.5 text-muted-foreground">
                        {item.responsible}
                      </span>
                    )}
                    {item.timing && (
                      <span className="text-xs bg-gray-100 rounded-full px-2 py-0.5 text-muted-foreground">
                        {item.timing}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface KeyValueCardProps {
  title: string;
  icon?: React.ReactNode;
  items: Array<{
    label: string;
    value: string | number | boolean | null | undefined;
    provenance?: {
      page_number?: number;
      text_snippet?: string;
    };
  }>;
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
  onViewSource?: (page: number) => void;
}

export function KeyValueCard({
  title,
  icon,
  items,
  provenance,
  onViewSource
}: KeyValueCardProps) {
  const formatValue = (value: string | number | boolean | null | undefined): string => {
    if (value === null || value === undefined) return "Not specified";
    if (typeof value === "boolean") return value ? "Yes" : "No";
    return String(value);
  };

  return (
    <div className="glass-card overflow-hidden">
      <div className="p-5 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {icon && <div className="text-gray-600">{icon}</div>}
          <h4 className="text-sf-headline font-semibold text-foreground">{title}</h4>
        </div>
        {provenance?.page_number && (
          <button
            onClick={() => onViewSource?.(provenance.page_number!)}
            className="provenance-chip"
            data-testid={`provenance-kv-${title}`}
          >
            <FileText className="w-3 h-3" />
            <span>p. {provenance.page_number}</span>
          </button>
        )}
      </div>

      <div className="divide-y divide-gray-100">
        {items.map((item, idx) => (
          <div 
            key={idx}
            className="px-5 py-3 flex items-center justify-between gap-4"
          >
            <span className="text-sf-callout text-muted-foreground">{item.label}</span>
            <div className="flex items-center gap-2">
              <span className="text-sf-callout font-medium text-foreground text-right">
                {formatValue(item.value)}
              </span>
              {item.provenance?.page_number && (
                <button
                  onClick={() => onViewSource?.(item.provenance!.page_number!)}
                  className="provenance-chip text-xs"
                >
                  <FileText className="w-3 h-3" />
                  <span>p. {item.provenance.page_number}</span>
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
