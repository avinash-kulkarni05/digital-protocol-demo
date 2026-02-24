import { motion } from "framer-motion";
import { FileText, ExternalLink } from "lucide-react";

interface Identifier {
  id: string;
  scopeId: string;
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
}

interface IdentifierListProps {
  identifiers: Identifier[];
  onViewSource?: (page: number) => void;
}

const registryLabels: Record<string, string> = {
  "clinicaltrials.gov": "ClinicalTrials.gov",
  "eudract": "EudraCT",
  "fda_ind": "FDA IND",
  "who": "WHO ICTRP",
  "isrctn": "ISRCTN",
};

const registryUrls: Record<string, (id: string) => string> = {
  "clinicaltrials.gov": (id) => `https://clinicaltrials.gov/study/${id}`,
  "eudract": (id) => `https://www.clinicaltrialsregister.eu/ctr-search/search?query=${id}`,
};

export function IdentifierList({ identifiers, onViewSource }: IdentifierListProps) {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card overflow-hidden"
    >
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-100/80">
            <th className="px-5 py-3 text-left text-sf-footnote font-semibold text-muted-foreground uppercase tracking-wider">
              Registry
            </th>
            <th className="px-5 py-3 text-left text-sf-footnote font-semibold text-muted-foreground uppercase tracking-wider">
              Identifier
            </th>
            <th className="px-5 py-3 text-right text-sf-footnote font-semibold text-muted-foreground uppercase tracking-wider w-24">
              Source
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100/60">
          {identifiers.map((identifier, index) => {
            const label = registryLabels[identifier.scopeId] || identifier.scopeId;
            const urlFn = registryUrls[identifier.scopeId];
            const url = urlFn ? urlFn(identifier.id) : null;
            
            return (
              <tr key={index} className="group hover:bg-gray-50/50 transition-colors">
                <td className="px-5 py-3.5 text-sf-caption text-muted-foreground">
                  {label}
                </td>
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sf-body font-medium text-foreground font-mono">
                      {identifier.id}
                    </span>
                    {url && (
                      <a 
                        href={url} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="text-gray-600 hover:text-gray-900 transition-colors opacity-0 group-hover:opacity-100"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>
                </td>
                <td className="px-5 py-3.5 text-right">
                  {identifier.provenance?.page_number && (
                    <button
                      onClick={() => onViewSource?.(identifier.provenance!.page_number!)}
                      className="provenance-chip opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <FileText className="w-3 h-3" />
                      <span>p.{identifier.provenance.page_number}</span>
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </motion.div>
  );
}
