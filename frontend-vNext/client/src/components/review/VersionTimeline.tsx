import { motion } from "framer-motion";
import { FileText, Calendar, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface ProtocolVersion {
  versionNumber: string;
  versionDate: string;
  provenance?: {
    page_number?: number;
    text_snippet?: string;
  };
}

interface VersionTimelineProps {
  versions: ProtocolVersion[];
  currentVersion?: string;
  onViewSource?: (page: number) => void;
}

export function VersionTimeline({ versions, currentVersion, onViewSource }: VersionTimelineProps) {
  const sortedVersions = [...versions].sort((a, b) => {
    const dateA = new Date(a.versionDate);
    const dateB = new Date(b.versionDate);
    return dateB.getTime() - dateA.getTime();
  });

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric' 
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <motion.div 
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="relative">
        <div className="absolute left-3 top-2 bottom-2 w-0.5 bg-gradient-to-b from-gray-200 via-gray-200 to-gray-100" />
        
        <div className="space-y-0">
          {sortedVersions.map((version, index) => {
            const isCurrent = version.versionNumber === currentVersion || index === 0;
            
            return (
              <div key={version.versionNumber} className="relative pl-9 py-3 group">
                <div className={cn(
                  "absolute left-0 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full flex items-center justify-center z-10",
                  isCurrent 
                    ? "bg-gray-400 text-white shadow-md shadow-gray-200" 
                    : "bg-white border-2 border-gray-200 text-gray-400"
                )}>
                  {isCurrent ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-gray-300" />
                  )}
                </div>
                
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className={cn(
                      "text-sf-body font-semibold",
                      isCurrent ? "text-foreground" : "text-muted-foreground"
                    )}>
                      Version {version.versionNumber}
                      {isCurrent && (
                        <span className="ml-2 text-sf-footnote font-medium text-gray-900 bg-gray-50 px-2 py-0.5 rounded-full">
                          Current
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-0.5 text-sf-caption text-muted-foreground">
                      <Calendar className="w-3 h-3" />
                      {formatDate(version.versionDate)}
                    </div>
                  </div>
                  
                  {version.provenance?.page_number && (
                    <button
                      onClick={() => onViewSource?.(version.provenance!.page_number!)}
                      className="provenance-chip opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <FileText className="w-3 h-3" />
                      <span>p.{version.provenance.page_number}</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </motion.div>
  );
}
