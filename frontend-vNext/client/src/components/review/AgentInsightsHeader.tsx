import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Info, X, Lightbulb, CheckCircle2, Cog, ChevronRight, Database, Layers } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";

interface AutomationRule {
  ruleId: string;
  ruleType: string;
  targetSystem: string;
  description: string;
  sourceDataPath: string;
  ruleLogic: string;
  example?: string | null;
}

interface ValidationCheck {
  checkId: string;
  checkType: string;
  targetSystem: string;
  description: string;
  sourceDataPath: string;
  checkLogic: string;
}

interface KeyInsight {
  name: string;
  description: string;
  dataPath: string;
  downstreamUses: string[];
  automationCategory: string;
  priority: string;
  automationRules: AutomationRule[];
  validationChecks: ValidationCheck[];
}

interface AgentDoc {
  agentId: string;
  displayName: string;
  purpose: string;
  scope?: string;
  instanceType?: string;
  wave?: number;
  priority?: number;
  keySectionsAnalyzed?: string[];
  keyInsights?: KeyInsight[];
}

interface AgentInsightsHeaderProps {
  agentDoc: AgentDoc | undefined;
  qualityScore?: number;
}

export function AgentInsightsHeader({ agentDoc }: AgentInsightsHeaderProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  
  if (!agentDoc) return null;
  
  const formatMultilineText = (text: string) => {
    return text
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0);
  };

  const scopeLines = agentDoc.scope ? formatMultilineText(agentDoc.scope) : [];
  const purposeText = agentDoc.purpose?.replace(/\s+/g, ' ').trim();
  
  return (
    <>
      <div className="mb-6" data-testid={`agent-insights-${agentDoc.agentId}`}>
        <motion.div 
          className="relative overflow-hidden rounded-2xl bg-white border border-gray-200/80 shadow-sm"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <div className="absolute inset-0 bg-gradient-to-br from-gray-50/50 via-transparent to-gray-50/30" />
          
          <div className="relative p-5">
            <div className="flex items-start gap-4">
              <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-gray-700 to-gray-800 flex items-center justify-center shadow-md flex-shrink-0">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1.5">
                  <h3 className="font-semibold text-gray-900 text-base tracking-tight">{agentDoc.displayName}</h3>
                  <button
                    onClick={() => setIsModalOpen(true)}
                    className="w-5 h-5 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center transition-colors group"
                    data-testid={`agent-info-button-${agentDoc.agentId}`}
                  >
                    <Info className="w-3 h-3 text-gray-400 group-hover:text-gray-800 transition-colors" />
                  </button>
                </div>
                
                {purposeText && (
                  <p className="text-sm text-gray-600 leading-relaxed mb-3">
                    {purposeText}
                  </p>
                )}
                
                {scopeLines.length > 0 && (
                  <div className="mt-2">
                    <div className="flex flex-wrap gap-1.5">
                      {scopeLines.slice(0, 5).map((line, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center px-2 py-0.5 rounded-md bg-gray-100 text-xs text-gray-600"
                        >
                          {line.replace(/^-\s*/, '')}
                        </span>
                      ))}
                      {scopeLines.length > 5 && (
                        <span className="inline-flex items-center px-2 py-0.5 text-xs text-gray-400">
                          +{scopeLines.length - 5} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      <AgentDocumentationModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        agentDoc={agentDoc} 
      />
    </>
  );
}

interface AgentDocumentationModalProps {
  isOpen: boolean;
  onClose: () => void;
  agentDoc: AgentDoc;
}

function AgentDocumentationModal({ isOpen, onClose, agentDoc }: AgentDocumentationModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] p-0 overflow-hidden bg-white/95 backdrop-blur-xl border-0 shadow-2xl rounded-2xl">
        <div className="absolute inset-0 bg-gradient-to-br from-gray-50/30 via-transparent to-gray-50/20 rounded-2xl pointer-events-none" />
        
        <DialogHeader className="relative px-6 pt-6 pb-4 border-b border-gray-100/80">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-gray-700 to-gray-800 flex items-center justify-center shadow-lg">
              <Sparkles className="w-6 h-6 text-white" />
            </div>
            <div>
              <DialogTitle className="text-xl font-semibold text-gray-900 tracking-tight">
                {agentDoc.displayName}
              </DialogTitle>
              <DialogDescription className="text-sm text-gray-500 mt-0.5">
                Agent ID: {agentDoc.agentId}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        
        <ScrollArea className="relative max-h-[calc(85vh-100px)]">
          <div className="px-6 py-5 space-y-6">
            {agentDoc.purpose && (
              <section>
                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Lightbulb className="w-3.5 h-3.5" />
                  Purpose
                </h4>
                <p className="text-sm text-gray-700 leading-relaxed bg-gray-50/80 rounded-xl p-4">
                  {agentDoc.purpose.replace(/\s+/g, ' ').trim()}
                </p>
              </section>
            )}

            {agentDoc.scope && (
              <section>
                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Layers className="w-3.5 h-3.5" />
                  Scope
                </h4>
                <div className="bg-gray-50/80 rounded-xl p-4">
                  <ul className="space-y-1.5">
                    {agentDoc.scope.split('\n').map((line, idx) => {
                      const trimmed = line.trim();
                      if (!trimmed) return null;
                      return (
                        <li key={idx} className="flex items-start gap-2 text-sm text-gray-700">
                          <ChevronRight className="w-3.5 h-3.5 text-gray-700 mt-0.5 flex-shrink-0" />
                          <span>{trimmed.replace(/^-\s*/, '')}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </section>
            )}

            {agentDoc.keySectionsAnalyzed && agentDoc.keySectionsAnalyzed.length > 0 && (
              <section>
                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Database className="w-3.5 h-3.5" />
                  Key Sections Analyzed
                </h4>
                <div className="flex flex-wrap gap-2">
                  {agentDoc.keySectionsAnalyzed.map((section, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center px-3 py-1.5 rounded-lg bg-gray-100 text-sm text-gray-800 font-medium"
                    >
                      {section}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {agentDoc.keyInsights && agentDoc.keyInsights.length > 0 && (
              <section>
                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                  <Lightbulb className="w-3.5 h-3.5" />
                  Key Insights & Automation
                </h4>
                <div className="space-y-3">
                  {agentDoc.keyInsights.map((insight, idx) => (
                    <InsightCard key={idx} insight={insight} />
                  ))}
                </div>
              </section>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

function InsightCard({ insight }: { insight: KeyInsight }) {
  const [expanded, setExpanded] = useState(false);
  
  const priorityColors: Record<string, string> = {
    critical: "bg-gray-100 text-gray-900",
    high: "bg-gray-100 text-gray-800",
    medium: "bg-gray-100 text-gray-700",
    low: "bg-gray-100 text-gray-600",
  };
  
  const priorityColor = priorityColors[insight.priority] || "bg-gray-100 text-gray-600";
  
  return (
    <motion.div 
      className="bg-white rounded-xl border border-gray-200/80 shadow-sm overflow-hidden"
      initial={false}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50/50 transition-colors text-left"
        data-testid={`insight-expand-${insight.name}`}
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center">
            <Lightbulb className="w-4 h-4 text-gray-800" />
          </div>
          <div>
            <h5 className="text-sm font-medium text-gray-900">{insight.name}</h5>
            <p className="text-xs text-gray-500">{insight.automationCategory}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${priorityColor}`}>
            {insight.priority}
          </span>
          <ChevronRight className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-90' : ''}`} />
        </div>
      </button>
      
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="px-4 pb-4 space-y-4 border-t border-gray-100">
              <div className="pt-3">
                <p className="text-sm text-gray-600">{insight.description}</p>
                <p className="text-xs text-gray-400 mt-1 font-mono">{insight.dataPath}</p>
              </div>
              
              {insight.downstreamUses && insight.downstreamUses.length > 0 && (
                <div>
                  <h6 className="text-xs font-medium text-gray-500 mb-2">Downstream Uses</h6>
                  <div className="flex flex-wrap gap-1.5">
                    {insight.downstreamUses.map((use, idx) => (
                      <span key={idx} className="px-2 py-1 bg-gray-100 rounded-md text-xs text-gray-600">
                        {use}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              
              {insight.automationRules && insight.automationRules.length > 0 && (
                <div>
                  <h6 className="text-xs font-medium text-gray-500 mb-2 flex items-center gap-1.5">
                    <Cog className="w-3 h-3" />
                    Automation Rules ({insight.automationRules.length})
                  </h6>
                  <div className="space-y-2">
                    {insight.automationRules.map((rule, idx) => (
                      <div key={idx} className="bg-gray-50 rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-mono text-gray-800">{rule.ruleId}</span>
                          <span className="text-xs bg-gray-100 text-gray-900 px-1.5 py-0.5 rounded">{rule.targetSystem}</span>
                        </div>
                        <p className="text-xs text-gray-700">{rule.description}</p>
                        {rule.ruleLogic && (
                          <pre className="mt-2 text-xs text-gray-500 bg-gray-100 rounded p-2 overflow-x-auto whitespace-pre-wrap font-mono">
                            {rule.ruleLogic}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {insight.validationChecks && insight.validationChecks.length > 0 && (
                <div>
                  <h6 className="text-xs font-medium text-gray-500 mb-2 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3 h-3" />
                    Validation Checks ({insight.validationChecks.length})
                  </h6>
                  <div className="space-y-2">
                    {insight.validationChecks.map((check, idx) => (
                      <div key={idx} className="bg-gray-50 rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-mono text-gray-800">{check.checkId}</span>
                          <span className="text-xs bg-gray-100 text-gray-900 px-1.5 py-0.5 rounded">{check.targetSystem}</span>
                        </div>
                        <p className="text-xs text-gray-700">{check.description}</p>
                        {check.checkLogic && (
                          <pre className="mt-2 text-xs text-gray-500 bg-gray-100 rounded p-2 overflow-x-auto whitespace-pre-wrap font-mono">
                            {check.checkLogic}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
