import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { useCoverageRegistry } from "@/lib/coverage-registry";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, ChevronDown, ChevronRight, Target, Flag, TrendingUp, BarChart3,
  CheckCircle, Circle, AlertCircle, Layers, Calculator, Users, Shield,
  Database, GitBranch, Activity, Clock, User, Hash, Link2, Beaker,
  ClipboardList, Scale, Box, Stethoscope, Info, ListChecks, Percent
} from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";
import { EditableText } from "./EditableValue";

interface EndpointsViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "objectives" | "primary" | "secondary" | "exploratory" | "estimands" | "populations" | "sap";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function FieldRow({ label, value, provenance, onViewSource }: { label: string; value: any; provenance?: any; onViewSource?: (page: number) => void }) {
  if (!value) return null;
  
  const displayValue = typeof value === 'object' && value.decode ? value.decode : 
                       typeof value === 'object' && value.code ? `${value.decode || value.code}` :
                       Array.isArray(value) ? value.join(', ') :
                       String(value);
  
  return (
    <div className="flex items-start justify-between py-2 border-b border-gray-100 last:border-0">
      <div className="flex-1">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
        <p className="text-sm text-foreground mt-0.5">{displayValue}</p>
      </div>
      {provenance && <ProvenanceChip provenance={provenance} onViewSource={onViewSource} />}
    </div>
  );
}

function CollapsibleSection({ title, icon: Icon, children, defaultOpen = false, count }: { title: string; icon: React.ElementType; children: React.ReactNode; defaultOpen?: boolean; count?: number }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
        data-testid={`section-toggle-${title.toLowerCase().replace(/\s+/g, '-')}`}
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
            <Icon className="w-4 h-4 text-gray-700" />
          </div>
          <span className="font-medium text-foreground">{title}</span>
          {count !== undefined && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{count}</span>
          )}
        </div>
        {isOpen ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="p-4 pt-0 border-t border-gray-100">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SummaryHeader({ objectives, endpoints, sapAnalyses }: { objectives: any[]; endpoints: any[]; sapAnalyses?: any }) {
  const primaryEndpoints = endpoints?.filter(e => 
    e.level?.decode?.toLowerCase().includes("primary") ||
    e.endpoint_level?.decode?.toLowerCase().includes("primary") ||
    e.endpoint_type?.toLowerCase().includes("primary")
  ).length || 0;
  
  const secondaryEndpoints = endpoints?.filter(e => 
    e.level?.decode?.toLowerCase().includes("secondary") ||
    e.endpoint_level?.decode?.toLowerCase().includes("secondary") ||
    e.endpoint_type?.toLowerCase().includes("secondary")
  ).length || 0;
  
  const exploratoryEndpoints = endpoints?.filter(e => 
    e.level?.decode?.toLowerCase().includes("exploratory") ||
    e.endpoint_level?.decode?.toLowerCase().includes("exploratory") ||
    e.endpoint_type?.toLowerCase().includes("exploratory")
  ).length || 0;
  
  const hasSapData = sapAnalyses && (
    sapAnalyses.statistical_methods?.length > 0 ||
    sapAnalyses.subgroup_analyses?.length > 0 ||
    sapAnalyses.sensitivity_analyses?.length > 0 ||
    sapAnalyses.missing_data_handling ||
    sapAnalyses.multiplicity_adjustment
  );
  
  return (
    <div className="bg-gradient-to-br from-slate-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="endpoints-summary-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <Target className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Endpoints & Objectives</h3>
          <p className="text-sm text-muted-foreground">Study objectives, endpoints, and statistical analysis plan</p>
        </div>
      </div>
      
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-objectives">
          <div className="flex items-center gap-2 mb-1">
            <Flag className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Objectives</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{objectives?.length || 0}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-primary">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Primary</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{primaryEndpoints}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-secondary">
          <div className="flex items-center gap-2 mb-1">
            <Circle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Secondary</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{secondaryEndpoints}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-exploratory">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Exploratory</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{exploratoryEndpoints}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-sap">
          <div className="flex items-center gap-2 mb-1">
            <Calculator className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">SAP</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{hasSapData ? "Yes" : "No"}</p>
        </div>
      </div>
    </div>
  );
}

function ObjectiveCard({ objective, idx, onViewSource, onFieldUpdate }: { objective: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [expanded, setExpanded] = useState(false);
  const level = objective.objective_level?.decode || objective.level?.decode || objective.level || "Objective";
  const isPrimary = level.toLowerCase().includes("primary");
  const isSecondary = level.toLowerCase().includes("secondary");
  const basePath = `domainSections.endpointsEstimandsSAP.data.protocol_endpoints.objectives.${idx}`;

  const colorConfig = isPrimary
    ? { bg: "from-gray-800 to-gray-900", light: "bg-gray-50", text: "text-gray-700", border: "border-gray-200" }
    : isSecondary
    ? { bg: "from-gray-800 to-gray-900", light: "bg-gray-50", text: "text-gray-700", border: "border-gray-200" }
    : { bg: "from-gray-800 to-gray-900", light: "bg-gray-50", text: "text-gray-700", border: "border-gray-200" };

  const hasEndpoints = objective.endpoint_ids?.length > 0;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm" data-testid={`objective-card-${objective.id}`}>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1">
            <div className={cn("w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center flex-shrink-0", colorConfig.bg)}>
              <Flag className="w-5 h-5 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className={cn("text-xs font-bold px-2 py-0.5 rounded-full", colorConfig.light, colorConfig.text)}>
                  {level}
                </span>
                {hasEndpoints && (
                  <span className="text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full">
                    {objective.endpoint_ids.length} endpoint(s)
                  </span>
                )}
              </div>
              <div className="text-sm text-foreground leading-relaxed">
                <EditableText
                  value={objective.text || objective.objective_text || objective.description || ""}
                  multiline
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.text`, v) : undefined}
                />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ProvenanceChip provenance={objective.provenance} onViewSource={onViewSource} />
            {hasEndpoints && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="p-1 hover:bg-gray-200 rounded transition-colors"
              >
                {expanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Linked Endpoints */}
      <AnimatePresence>
        {expanded && hasEndpoints && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-2 border-t border-gray-100">
              <div className="flex items-center gap-2 mb-2">
                <Link2 className="w-4 h-4 text-gray-400" />
                <span className="text-xs font-medium text-muted-foreground uppercase">Linked Endpoints</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {objective.endpoint_ids.map((epId: string, idx: number) => (
                  <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full font-mono">
                    {epId}
                  </span>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function EndpointCard({ endpoint, idx, onViewSource, onFieldUpdate }: { endpoint: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [expanded, setExpanded] = useState(false);
  const level = endpoint.level?.decode || endpoint.endpoint_level?.decode || endpoint.endpoint_type || "Endpoint";
  const isPrimary = level.toLowerCase().includes("primary");
  const isSecondary = level.toLowerCase().includes("secondary");
  const basePath = `domainSections.endpointsEstimandsSAP.data.protocol_endpoints.endpoints.${idx}`;

  const colorConfig = isPrimary
    ? { bg: "bg-gray-100", icon: "text-gray-900", badge: "bg-gray-50 text-gray-700 border-gray-200" }
    : isSecondary
    ? { bg: "bg-gray-100", icon: "text-gray-900", badge: "bg-gray-50 text-gray-700 border-gray-200" }
    : { bg: "bg-gray-100", icon: "text-gray-900", badge: "bg-gray-50 text-gray-700 border-gray-200" };

  const hasDetails = endpoint.purpose || endpoint.assessor || endpoint.outcome_type ||
                     endpoint.assessment_method || endpoint.assessment_timepoints_weeks?.length > 0 ||
                     endpoint.analysis_population_id || endpoint.primary_timepoint_weeks ||
                     endpoint.primary_timepoint_text;

  return (
    <div className="bg-gray-50 rounded-xl border border-gray-200 overflow-hidden" data-testid={`endpoint-card-${endpoint.id}`}>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1">
            <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0", colorConfig.bg)}>
              <Target className={cn("w-4 h-4", colorConfig.icon)} />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full border", colorConfig.badge)}>
                  {level}
                </span>
                {endpoint.label && (
                  <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                    {endpoint.label}
                  </span>
                )}
                {endpoint.outcome_type?.decode && (
                  <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                    {endpoint.outcome_type.decode}
                  </span>
                )}
              </div>
              <div className="text-sm text-foreground font-medium">
                <EditableText
                  value={endpoint.text || endpoint.endpoint_text || endpoint.description || endpoint.name || ""}
                  multiline
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.text`, v) : undefined}
                />
              </div>

              {endpoint.purpose && (
                <div className="text-xs text-muted-foreground mt-2">
                  <span className="font-medium">Purpose: </span>
                  <EditableText
                    value={endpoint.purpose}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.purpose`, v) : undefined}
                  />
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ProvenanceChip provenance={endpoint.provenance} onViewSource={onViewSource} />
            {hasDetails && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="p-1 hover:bg-gray-200 rounded transition-colors"
                data-testid={`expand-endpoint-${endpoint.id}`}
              >
                {expanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
              </button>
            )}
          </div>
        </div>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-2 border-t border-gray-200 bg-white space-y-4">
              {/* Assessment Details */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {endpoint.assessment_method && (
                  <div className="flex items-start gap-2">
                    <Stethoscope className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase">Assessment Method</span>
                      <p className="text-sm text-foreground">{endpoint.assessment_method}</p>
                    </div>
                  </div>
                )}
                {endpoint.assessor && (
                  <div className="flex items-start gap-2">
                    <User className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase">Assessor</span>
                      <p className="text-sm text-foreground">{endpoint.assessor}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Timepoints */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(endpoint.primary_timepoint_weeks || endpoint.primary_timepoint_text) && (
                  <div className="flex items-start gap-2">
                    <Clock className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase">Primary Timepoint</span>
                      <p className="text-sm text-foreground">
                        {endpoint.primary_timepoint_weeks && `Week ${endpoint.primary_timepoint_weeks}`}
                        {endpoint.primary_timepoint_weeks && endpoint.primary_timepoint_text && ' - '}
                        {endpoint.primary_timepoint_text}
                      </p>
                    </div>
                  </div>
                )}
                {endpoint.analysis_population_id && (
                  <div className="flex items-start gap-2">
                    <Users className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase">Analysis Population</span>
                      <p className="text-sm text-foreground font-mono">{endpoint.analysis_population_id}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Assessment Timepoints Array */}
              {endpoint.assessment_timepoints_weeks?.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Clock className="w-4 h-4 text-gray-400" />
                    <span className="text-xs font-medium text-muted-foreground uppercase">Assessment Timepoints (Weeks)</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {endpoint.assessment_timepoints_weeks.map((week: number, idx: number) => (
                      <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full">
                        Week {week}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Fallback for remaining fields */}
              <SmartDataRender
                data={endpoint}
                onViewSource={onViewSource}
                editable={false}
                excludeFields={['id', 'name', 'text', 'endpoint_text', 'description', 'purpose', 'level',
                  'endpoint_level', 'endpoint_type', 'label', 'outcome_type', 'provenance',
                  'assessment_method', 'assessor', 'primary_timepoint_weeks', 'primary_timepoint_text',
                  'analysis_population_id', 'assessment_timepoints_weeks']}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function StatisticalMethodCard({ method, idx, onViewSource, onFieldUpdate }: { method: any; idx?: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [expanded, setExpanded] = useState(false);
  const basePath = idx !== undefined ? `domainSections.endpointsEstimandsSAP.data.sap_analyses.statistical_methods.${idx}` : "";

  const hasDeepFields = method.alpha || method.multiplicity || method.software_package ||
                        method.procedure || method.endpoint_ids?.length > 0;

  return (
    <div className="bg-gray-50 rounded-lg p-4 border border-gray-200" data-testid={`stat-method-${method.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <EditableText
              value={method.name || ""}
              onSave={onFieldUpdate && basePath ? (v) => onFieldUpdate(`${basePath}.name`, v) : undefined}
              className="font-medium text-foreground"
            />
            {method.model_type && (
              <EditableText
                value={method.model_type}
                onSave={onFieldUpdate && basePath ? (v) => onFieldUpdate(`${basePath}.model_type`, v) : undefined}
                className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full"
              />
            )}
            {method.alpha && (
              <span className="text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full">
                α = {method.alpha}
              </span>
            )}
          </div>
          <EditableText
            value={method.description || ""}
            multiline
            onSave={onFieldUpdate && basePath ? (v) => onFieldUpdate(`${basePath}.description`, v) : undefined}
            className="text-sm text-muted-foreground"
          />

          {/* Quick preview of key fields */}
          {(method.software_package || method.endpoint_ids?.length > 0) && (
            <div className="flex flex-wrap gap-2 mt-2">
              {method.software_package && (
                <span className="text-xs text-gray-600 flex items-center gap-1">
                  <Box className="w-3 h-3" /> {method.software_package}
                </span>
              )}
              {method.endpoint_ids?.length > 0 && (
                <span className="text-xs text-gray-600 flex items-center gap-1">
                  <Link2 className="w-3 h-3" /> {method.endpoint_ids.length} endpoint(s)
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={method.provenance} onViewSource={onViewSource} />
          <button onClick={() => setExpanded(!expanded)} className="p-1 hover:bg-gray-200 rounded transition-colors">
            {expanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
          </button>
        </div>
      </div>
      <AnimatePresence>
        {expanded && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <div className="mt-3 pt-3 border-t border-gray-200 space-y-3">
              {/* Detailed fields */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {method.alpha && (
                  <div className="flex items-start gap-2">
                    <Percent className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase">Alpha Level</span>
                      <p className="text-sm text-foreground">{method.alpha}</p>
                    </div>
                  </div>
                )}
                {method.software_package && (
                  <div className="flex items-start gap-2">
                    <Box className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase">Software Package</span>
                      <p className="text-sm text-foreground">{method.software_package}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Multiplicity */}
              {method.multiplicity && (
                <div className="bg-white rounded-lg p-3 border border-gray-100">
                  <div className="flex items-center gap-2 mb-2">
                    <GitBranch className="w-4 h-4 text-gray-400" />
                    <span className="text-xs font-medium text-muted-foreground uppercase">Multiplicity Adjustment</span>
                  </div>
                  {method.multiplicity.method && (
                    <p className="text-sm text-foreground mb-1"><span className="font-medium">Method:</span> {method.multiplicity.method}</p>
                  )}
                  {method.multiplicity.description && (
                    <p className="text-sm text-muted-foreground">{method.multiplicity.description}</p>
                  )}
                </div>
              )}

              {/* Procedure */}
              {method.procedure && (
                <div className="bg-white rounded-lg p-3 border border-gray-100">
                  <div className="flex items-center gap-2 mb-2">
                    <ClipboardList className="w-4 h-4 text-gray-400" />
                    <span className="text-xs font-medium text-muted-foreground uppercase">Procedure</span>
                  </div>
                  <p className="text-sm text-muted-foreground">{method.procedure}</p>
                </div>
              )}

              {/* Linked Endpoints */}
              {method.endpoint_ids?.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Link2 className="w-4 h-4 text-gray-400" />
                    <span className="text-xs font-medium text-muted-foreground uppercase">Linked Endpoints</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {method.endpoint_ids.map((epId: string, idx: number) => (
                      <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full font-mono">
                        {epId}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <SmartDataRender
                data={method}
                onViewSource={onViewSource}
                editable={false}
                excludeFields={['id', 'name', 'description', 'model_type', 'provenance', 'alpha',
                  'multiplicity', 'software_package', 'procedure', 'endpoint_ids']}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SubgroupAnalysisCard({ analysis, onViewSource }: { analysis: any; onViewSource?: (page: number) => void }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="bg-gray-50 rounded-lg p-4 border border-gray-200" data-testid={`subgroup-${analysis.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <h5 className="font-medium text-foreground">{analysis.name}</h5>
            {analysis.interaction_test !== undefined && (
              <span className={cn(
                "text-xs px-2 py-0.5 rounded-full",
                analysis.interaction_test ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-600"
              )}>
                {analysis.interaction_test ? "Interaction Test" : "No Interaction Test"}
              </span>
            )}
            {analysis.forest_plot !== undefined && (
              <span className={cn(
                "text-xs px-2 py-0.5 rounded-full",
                analysis.forest_plot ? "bg-gray-50 text-gray-700" : "bg-gray-100 text-gray-600"
              )}>
                {analysis.forest_plot ? "Forest Plot" : "No Forest Plot"}
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground">{analysis.description}</p>

          {/* Subgroup factors preview */}
          {analysis.subgroup_factors?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {analysis.subgroup_factors.slice(0, 3).map((factor: string, idx: number) => (
                <span key={idx} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                  {factor}
                </span>
              ))}
              {analysis.subgroup_factors.length > 3 && (
                <span className="text-xs text-gray-500">+{analysis.subgroup_factors.length - 3} more</span>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={analysis.provenance} onViewSource={onViewSource} />
          <button onClick={() => setExpanded(!expanded)} className="p-1 hover:bg-gray-200 rounded transition-colors">
            {expanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
          </button>
        </div>
      </div>
      <AnimatePresence>
        {expanded && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <div className="mt-3 pt-3 border-t border-gray-200 space-y-3">
              {/* Subgroup factors full list */}
              {analysis.subgroup_factors?.length > 0 && (
                <div>
                  <span className="text-xs font-medium text-muted-foreground uppercase">Subgroup Factors</span>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {analysis.subgroup_factors.map((factor: string, idx: number) => (
                      <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full">
                        {factor}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Endpoint links */}
              {analysis.endpoint_ids?.length > 0 && (
                <div>
                  <span className="text-xs font-medium text-muted-foreground uppercase">Linked Endpoints</span>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {analysis.endpoint_ids.map((epId: string, idx: number) => (
                      <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full font-mono">
                        {epId}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <SmartDataRender
                data={analysis}
                onViewSource={onViewSource}
                editable={false}
                excludeFields={['id', 'name', 'description', 'provenance', 'interaction_test',
                  'forest_plot', 'subgroup_factors', 'endpoint_ids']}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SensitivityAnalysisCard({ analysis, onViewSource }: { analysis: any; onViewSource?: (page: number) => void }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="bg-gray-50 rounded-lg p-4 border border-gray-200" data-testid={`sensitivity-${analysis.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h5 className="font-medium text-foreground">{analysis.name}</h5>
            {analysis.analysis_type?.decode && (
              <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">{analysis.analysis_type.decode}</span>
            )}
          </div>
          <p className="text-sm text-muted-foreground">{analysis.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={analysis.provenance} onViewSource={onViewSource} />
          <button onClick={() => setExpanded(!expanded)} className="p-1 hover:bg-gray-200 rounded transition-colors">
            {expanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
          </button>
        </div>
      </div>
      <AnimatePresence>
        {expanded && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <div className="mt-3 pt-3 border-t border-gray-200">
              <SmartDataRender data={analysis} onViewSource={onViewSource} editable={false} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function EstimandCard({ estimand, idx, onViewSource, onFieldUpdate }: { estimand: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [expanded, setExpanded] = useState(false);
  const basePath = `domainSections.endpointsEstimandsSAP.data.protocol_endpoints.estimands.${idx}`;

  const hasDeepFields = estimand.treatment || estimand.population || estimand.variable ||
                        estimand.intercurrent_events?.length > 0;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm" data-testid={`estimand-card-${estimand.id}`}>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center flex-shrink-0">
              <Activity className="w-5 h-5 text-white" />
            </div>
            <div className="flex-1">
              <h5 className="font-medium text-foreground mb-1">
                <EditableText
                  value={estimand.name || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.name`, v) : undefined}
                />
              </h5>
              <div className="text-sm text-muted-foreground">
                <EditableText
                  value={estimand.text || ""}
                  multiline
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.text`, v) : undefined}
                />
              </div>

              <div className="flex flex-wrap gap-2 mt-2">
                {estimand.summary_measure?.decode && (
                  <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">
                    {estimand.summary_measure.decode}
                  </span>
                )}
                {estimand.intercurrent_events?.length > 0 && (
                  <span className="text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full">
                    {estimand.intercurrent_events.length} ICE(s)
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ProvenanceChip provenance={estimand.provenance} onViewSource={onViewSource} />
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1 hover:bg-gray-200 rounded transition-colors"
              data-testid={`expand-estimand-${estimand.id}`}
            >
              {expanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
            </button>
          </div>
        </div>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-2 border-t border-gray-200 bg-gray-50 space-y-4">
              {/* Treatment Arms */}
              {estimand.treatment && (
                <div className="bg-white rounded-lg p-3 border border-gray-100">
                  <div className="flex items-center gap-2 mb-3">
                    <Beaker className="w-4 h-4 text-gray-400" />
                    <span className="text-xs font-medium text-muted-foreground uppercase">Treatment</span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {estimand.treatment.experimental_arm && (
                      <div className="bg-gray-50 rounded-lg p-2">
                        <span className="text-xs font-medium text-green-700 uppercase">Experimental Arm</span>
                        {estimand.treatment.experimental_arm.arm_type?.decode && (
                          <p className="text-sm text-foreground">{estimand.treatment.experimental_arm.arm_type.decode}</p>
                        )}
                        {estimand.treatment.experimental_arm.description && (
                          <p className="text-xs text-muted-foreground mt-1">{estimand.treatment.experimental_arm.description}</p>
                        )}
                      </div>
                    )}
                    {estimand.treatment.comparator_arm && (
                      <div className="bg-gray-50 rounded-lg p-2">
                        <span className="text-xs font-medium text-gray-700 uppercase">Comparator Arm</span>
                        {estimand.treatment.comparator_arm.arm_type?.decode && (
                          <p className="text-sm text-foreground">{estimand.treatment.comparator_arm.arm_type.decode}</p>
                        )}
                        {estimand.treatment.comparator_arm.description && (
                          <p className="text-xs text-muted-foreground mt-1">{estimand.treatment.comparator_arm.description}</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Population */}
              {estimand.population && (
                <div className="bg-white rounded-lg p-3 border border-gray-100">
                  <div className="flex items-center gap-2 mb-2">
                    <Users className="w-4 h-4 text-gray-400" />
                    <span className="text-xs font-medium text-muted-foreground uppercase">Population</span>
                  </div>
                  {estimand.population.analysis_population_id && (
                    <p className="text-sm text-foreground font-mono">{estimand.population.analysis_population_id}</p>
                  )}
                  {estimand.population.description && (
                    <p className="text-sm text-muted-foreground mt-1">{estimand.population.description}</p>
                  )}
                </div>
              )}

              {/* Variable */}
              {estimand.variable && (
                <div className="bg-white rounded-lg p-3 border border-gray-100">
                  <div className="flex items-center gap-2 mb-2">
                    <Target className="w-4 h-4 text-gray-400" />
                    <span className="text-xs font-medium text-muted-foreground uppercase">Variable</span>
                  </div>
                  {estimand.variable.endpoint_id && (
                    <p className="text-sm text-foreground font-mono">{estimand.variable.endpoint_id}</p>
                  )}
                  {estimand.variable.description && (
                    <p className="text-sm text-muted-foreground mt-1">{estimand.variable.description}</p>
                  )}
                </div>
              )}

              {/* Intercurrent Events */}
              {estimand.intercurrent_events?.length > 0 && (
                <div className="bg-white rounded-lg p-3 border border-gray-100">
                  <div className="flex items-center gap-2 mb-3">
                    <AlertCircle className="w-4 h-4 text-gray-500" />
                    <span className="text-xs font-medium text-muted-foreground uppercase">Intercurrent Events</span>
                    <span className="text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full">
                      {estimand.intercurrent_events.length}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {estimand.intercurrent_events.map((ice: any, idx: number) => (
                      <div key={idx} className="bg-gray-50 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium text-foreground">{ice.name || ice.event_name}</span>
                          {ice.strategy?.decode && (
                            <span className="text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded-full">
                              {ice.strategy.decode}
                            </span>
                          )}
                        </div>
                        {ice.description && (
                          <p className="text-xs text-muted-foreground mb-1">{ice.description}</p>
                        )}
                        {ice.strategy_rationale && (
                          <div className="mt-2 pt-2 border-t border-gray-200">
                            <span className="text-xs font-medium text-muted-foreground">Rationale:</span>
                            <p className="text-xs text-muted-foreground mt-0.5">{ice.strategy_rationale}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <SmartDataRender
                data={estimand}
                onViewSource={onViewSource}
                editable={false}
                excludeFields={['id', 'name', 'text', 'provenance', 'summary_measure', 'treatment',
                  'population', 'variable', 'intercurrent_events']}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AnalysisPopulationCard({ population, idx, onViewSource, onFieldUpdate }: { population: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [expanded, setExpanded] = useState(false);
  const basePath = `domainSections.endpointsEstimandsSAP.data.protocol_endpoints.analysis_populations.${idx}`;

  const hasDeepFields = population.inclusion_criteria?.length > 0 || population.exclusion_criteria?.length > 0 ||
                        population.is_primary_for_endpoints?.length > 0 || population.is_sensitivity_for_endpoints?.length > 0;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm" data-testid={`population-card-${population.id}`}>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-600 to-gray-700 flex items-center justify-center flex-shrink-0">
              <Users className="w-5 h-5 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <h5 className="font-medium text-foreground">
                  <EditableText
                    value={population.name || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.name`, v) : undefined}
                  />
                </h5>
                {population.label && (
                  <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full font-medium">{population.label}</span>
                )}
                {population.population_type?.decode && (
                  <span className="text-xs bg-gray-50 text-gray-600 px-2 py-0.5 rounded-full">{population.population_type.decode}</span>
                )}
                {population.is_primary_for_endpoints?.length > 0 && (
                  <span className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full">
                    Primary for {population.is_primary_for_endpoints.length} endpoint(s)
                  </span>
                )}
              </div>
              <div className="text-sm text-muted-foreground">
                <EditableText
                  value={population.text || ""}
                  multiline
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.text`, v) : undefined}
                />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ProvenanceChip provenance={population.provenance} onViewSource={onViewSource} />
            <button onClick={() => setExpanded(!expanded)} className="p-1 hover:bg-gray-200 rounded transition-colors">
              {expanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
            </button>
          </div>
        </div>
      </div>
      <AnimatePresence>
        {expanded && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <div className="px-4 pb-4 pt-2 border-t border-gray-200 space-y-4">
              {/* Inclusion Criteria */}
              {population.inclusion_criteria?.length > 0 && (
                <div className="bg-green-50 rounded-lg p-3 border border-green-100">
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle className="w-4 h-4 text-green-600" />
                    <span className="text-xs font-medium text-green-700 uppercase">Inclusion Criteria</span>
                    <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                      {population.inclusion_criteria.length}
                    </span>
                  </div>
                  <ul className="space-y-1">
                    {population.inclusion_criteria.map((criterion: string, idx: number) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-gray-700">
                        <span className="w-1.5 h-1.5 rounded-full bg-green-500 mt-2 flex-shrink-0" />
                        <span>{criterion}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Exclusion Criteria */}
              {population.exclusion_criteria?.length > 0 && (
                <div className="bg-red-50 rounded-lg p-3 border border-red-100">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertCircle className="w-4 h-4 text-red-600" />
                    <span className="text-xs font-medium text-red-700 uppercase">Exclusion Criteria</span>
                    <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">
                      {population.exclusion_criteria.length}
                    </span>
                  </div>
                  <ul className="space-y-1">
                    {population.exclusion_criteria.map((criterion: string, idx: number) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-gray-700">
                        <span className="w-1.5 h-1.5 rounded-full bg-red-500 mt-2 flex-shrink-0" />
                        <span>{criterion}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Endpoint Links */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {/* Primary For Endpoints */}
                {population.is_primary_for_endpoints?.length > 0 && (
                  <div className="bg-white rounded-lg p-3 border border-gray-100">
                    <div className="flex items-center gap-2 mb-2">
                      <Target className="w-4 h-4 text-green-600" />
                      <span className="text-xs font-medium text-muted-foreground uppercase">Primary For Endpoints</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {population.is_primary_for_endpoints.map((epId: string, idx: number) => (
                        <span key={idx} className="text-xs bg-green-50 text-green-700 px-2 py-1 rounded-full font-mono">
                          {epId}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Sensitivity For Endpoints */}
                {population.is_sensitivity_for_endpoints?.length > 0 && (
                  <div className="bg-white rounded-lg p-3 border border-gray-100">
                    <div className="flex items-center gap-2 mb-2">
                      <Shield className="w-4 h-4 text-gray-900" />
                      <span className="text-xs font-medium text-muted-foreground uppercase">Sensitivity For Endpoints</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {population.is_sensitivity_for_endpoints.map((epId: string, idx: number) => (
                        <span key={idx} className="text-xs bg-gray-50 text-gray-700 px-2 py-1 rounded-full font-mono">
                          {epId}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <SmartDataRender
                data={population}
                onViewSource={onViewSource}
                editable={false}
                excludeFields={['id', 'name', 'text', 'label', 'population_type', 'provenance',
                  'inclusion_criteria', 'exclusion_criteria', 'is_primary_for_endpoints', 'is_sensitivity_for_endpoints']}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function EstimandsTab({ estimands, onViewSource, onFieldUpdate }: { estimands: any[]; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!estimands || estimands.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Activity className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No estimands defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {estimands.map((estimand: any, idx: number) => (
        <EstimandCard key={estimand.id || idx} estimand={estimand} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function AnalysisPopulationsTab({ populations, onViewSource, onFieldUpdate }: { populations: any[]; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!populations || populations.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No analysis populations defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {populations.map((population: any, idx: number) => (
        <AnalysisPopulationCard key={population.id || idx} population={population} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function SAPTab({ sapAnalyses, onViewSource, onFieldUpdate }: { sapAnalyses: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const basePath = "domainSections.endpointsEstimandsSAP.data.sap_analyses";

  if (!sapAnalyses) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Calculator className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No statistical analysis plan data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {sapAnalyses.statistical_methods?.length > 0 && (
        <CollapsibleSection
          title="Statistical Methods"
          icon={Calculator}
          count={sapAnalyses.statistical_methods.length}
          defaultOpen={true}
        >
          <div className="space-y-3">
            {sapAnalyses.statistical_methods.map((method: any, idx: number) => (
              <StatisticalMethodCard key={method.id || idx} method={method} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
            ))}
          </div>
        </CollapsibleSection>
      )}
      
      {sapAnalyses.subgroup_analyses?.length > 0 && (
        <CollapsibleSection 
          title="Subgroup Analyses" 
          icon={Users} 
          count={sapAnalyses.subgroup_analyses.length}
        >
          <div className="space-y-3">
            {sapAnalyses.subgroup_analyses.map((analysis: any, idx: number) => (
              <SubgroupAnalysisCard key={analysis.id || idx} analysis={analysis} onViewSource={onViewSource} />
            ))}
          </div>
        </CollapsibleSection>
      )}
      
      {sapAnalyses.sensitivity_analyses?.length > 0 && (
        <CollapsibleSection 
          title="Sensitivity Analyses" 
          icon={Shield} 
          count={sapAnalyses.sensitivity_analyses.length}
        >
          <div className="space-y-3">
            {sapAnalyses.sensitivity_analyses.map((analysis: any, idx: number) => (
              <SensitivityAnalysisCard key={analysis.id || idx} analysis={analysis} onViewSource={onViewSource} />
            ))}
          </div>
        </CollapsibleSection>
      )}
      
      {sapAnalyses.missing_data_handling && (
        <CollapsibleSection title="Missing Data Handling" icon={Database}>
          <div className="space-y-3">
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  {sapAnalyses.missing_data_handling.primary_method && (
                    <div className="mb-3">
                      <span className="text-xs font-medium text-muted-foreground uppercase">Primary Method</span>
                      <EditableText
                        value={sapAnalyses.missing_data_handling.primary_method}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.missing_data_handling.primary_method`, v) : undefined}
                        className="text-sm text-foreground"
                      />
                    </div>
                  )}

                  {sapAnalyses.missing_data_handling.method_description && (
                    <div className="mb-3">
                      <span className="text-xs font-medium text-muted-foreground uppercase">Description</span>
                      <EditableText
                        value={sapAnalyses.missing_data_handling.method_description}
                        multiline
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.missing_data_handling.method_description`, v) : undefined}
                        className="text-sm text-muted-foreground"
                      />
                    </div>
                  )}

                  {sapAnalyses.missing_data_handling.assumptions?.length > 0 && (
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase">Assumptions</span>
                      <ul className="text-sm text-muted-foreground list-disc list-inside mt-1">
                        {sapAnalyses.missing_data_handling.assumptions.map((assumption: string, idx: number) => (
                          <li key={idx}>
                            <EditableText
                              value={assumption}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.missing_data_handling.assumptions.${idx}`, v) : undefined}
                            />
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                <ProvenanceChip provenance={sapAnalyses.missing_data_handling.provenance} onViewSource={onViewSource} />
              </div>
            </div>
          </div>
        </CollapsibleSection>
      )}
      
      {sapAnalyses.multiplicity_adjustment && (
        <CollapsibleSection title="Multiplicity Adjustment" icon={GitBranch}>
          <div className="space-y-3">
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  {sapAnalyses.multiplicity_adjustment.method && (
                    <div className="mb-3">
                      <span className="text-xs font-medium text-muted-foreground uppercase">Method</span>
                      <EditableText
                        value={sapAnalyses.multiplicity_adjustment.method}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.multiplicity_adjustment.method`, v) : undefined}
                        className="text-sm text-foreground"
                      />
                    </div>
                  )}

                  {sapAnalyses.multiplicity_adjustment.description && (
                    <div className="mb-3">
                      <span className="text-xs font-medium text-muted-foreground uppercase">Description</span>
                      <EditableText
                        value={sapAnalyses.multiplicity_adjustment.description}
                        multiline
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.multiplicity_adjustment.description`, v) : undefined}
                        className="text-sm text-muted-foreground"
                      />
                    </div>
                  )}

                  {sapAnalyses.multiplicity_adjustment.alpha_allocation && (
                    <div className="mb-3">
                      <span className="text-xs font-medium text-muted-foreground uppercase">Alpha Allocation</span>
                      <EditableText
                        value={sapAnalyses.multiplicity_adjustment.alpha_allocation}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.multiplicity_adjustment.alpha_allocation`, v) : undefined}
                        className="text-sm text-foreground"
                      />
                    </div>
                  )}

                  {sapAnalyses.multiplicity_adjustment.gatekeeping_strategy && (
                    <div>
                      <span className="text-xs font-medium text-muted-foreground uppercase">Gatekeeping Strategy</span>
                      <EditableText
                        value={sapAnalyses.multiplicity_adjustment.gatekeeping_strategy}
                        multiline
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.multiplicity_adjustment.gatekeeping_strategy`, v) : undefined}
                        className="text-sm text-muted-foreground"
                      />
                    </div>
                  )}
                </div>
                <ProvenanceChip provenance={sapAnalyses.multiplicity_adjustment.provenance} onViewSource={onViewSource} />
              </div>
            </div>
          </div>
        </CollapsibleSection>
      )}
    </div>
  );
}

function OverviewTab({ objectives, endpoints, sapAnalyses, extractionStatistics, estimands, populations, onViewSource, onFieldUpdate }: {
  objectives: any[];
  endpoints: any[];
  sapAnalyses?: any;
  extractionStatistics?: any;
  estimands?: any[];
  populations?: any[];
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
}) {
  const primaryEndpoints = endpoints?.filter(e =>
    e.level?.decode?.toLowerCase().includes("primary") ||
    e.endpoint_level?.decode?.toLowerCase().includes("primary") ||
    e.endpoint_type?.toLowerCase().includes("primary")
  ) || [];

  const secondaryEndpoints = endpoints?.filter(e =>
    e.level?.decode?.toLowerCase().includes("secondary") ||
    e.endpoint_level?.decode?.toLowerCase().includes("secondary") ||
    e.endpoint_type?.toLowerCase().includes("secondary")
  ) || [];

  const exploratoryEndpoints = endpoints?.filter(e =>
    e.level?.decode?.toLowerCase().includes("exploratory") ||
    e.endpoint_level?.decode?.toLowerCase().includes("exploratory") ||
    e.endpoint_type?.toLowerCase().includes("exploratory")
  ) || [];

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Target className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-2">Endpoints & Objectives Overview</h4>
            <p className="text-sm text-gray-700 leading-relaxed">
              This section defines the study objectives and endpoints that will be measured to evaluate the efficacy and safety of the intervention, along with the statistical analysis plan.
            </p>
          </div>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-gray-600" />
            Summary Metrics
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Flag className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{objectives?.length || 0}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Objectives</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <CheckCircle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{primaryEndpoints.length}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Primary</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Circle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{secondaryEndpoints.length}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Secondary</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <TrendingUp className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{exploratoryEndpoints.length}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Exploratory</p>
            </div>
          </div>
        </div>
      </div>

      {/* Extraction Statistics */}
      {extractionStatistics && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h4 className="font-semibold text-foreground flex items-center gap-2">
              <Hash className="w-5 h-5 text-gray-600" />
              Extraction Statistics
            </h4>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
              {extractionStatistics.objectives_count !== undefined && (
                <div className="bg-gray-50 rounded-lg p-3 text-center">
                  <p className="text-xl font-bold text-gray-900">{extractionStatistics.objectives_count}</p>
                  <p className="text-xs text-gray-600">Objectives</p>
                </div>
              )}
              {extractionStatistics.endpoints_count !== undefined && (
                <div className="bg-gray-50 rounded-lg p-3 text-center">
                  <p className="text-xl font-bold text-gray-900">{extractionStatistics.endpoints_count}</p>
                  <p className="text-xs text-gray-600">Endpoints</p>
                </div>
              )}
              {extractionStatistics.estimands_count !== undefined && (
                <div className="bg-gray-50 rounded-lg p-3 text-center">
                  <p className="text-xl font-bold text-gray-900">{extractionStatistics.estimands_count}</p>
                  <p className="text-xs text-gray-600">Estimands</p>
                </div>
              )}
              {extractionStatistics.populations_count !== undefined && (
                <div className="bg-gray-50 rounded-lg p-3 text-center">
                  <p className="text-xl font-bold text-gray-900">{extractionStatistics.populations_count}</p>
                  <p className="text-xs text-gray-600">Populations</p>
                </div>
              )}
              {extractionStatistics.sensitivity_analyses_count !== undefined && (
                <div className="bg-gray-50 rounded-lg p-3 text-center">
                  <p className="text-xl font-bold text-gray-900">{extractionStatistics.sensitivity_analyses_count}</p>
                  <p className="text-xs text-gray-600">Sensitivity</p>
                </div>
              )}
              {extractionStatistics.statistical_methods_count !== undefined && (
                <div className="bg-gray-50 rounded-lg p-3 text-center">
                  <p className="text-xl font-bold text-gray-900">{extractionStatistics.statistical_methods_count}</p>
                  <p className="text-xs text-gray-600">Stat Methods</p>
                </div>
              )}
              {extractionStatistics.subgroup_analyses_count !== undefined && (
                <div className="bg-gray-50 rounded-lg p-3 text-center">
                  <p className="text-xl font-bold text-gray-900">{extractionStatistics.subgroup_analyses_count}</p>
                  <p className="text-xs text-gray-600">Subgroups</p>
                </div>
              )}
            </div>

            {/* Boolean flags */}
            <div className="flex flex-wrap gap-2 mt-3">
              {extractionStatistics.has_multiplicity_adjustment !== undefined && (
                <span className={cn(
                  "text-xs px-2 py-1 rounded-full",
                  extractionStatistics.has_multiplicity_adjustment ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-600"
                )}>
                  {extractionStatistics.has_multiplicity_adjustment ? "Has Multiplicity Adjustment" : "No Multiplicity Adjustment"}
                </span>
              )}
              {extractionStatistics.has_missing_data_strategy !== undefined && (
                <span className={cn(
                  "text-xs px-2 py-1 rounded-full",
                  extractionStatistics.has_missing_data_strategy ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-600"
                )}>
                  {extractionStatistics.has_missing_data_strategy ? "Has Missing Data Strategy" : "No Missing Data Strategy"}
                </span>
              )}
            </div>
          </div>
        </div>
      )}
      
      {primaryEndpoints.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-gray-900" />
              </div>
              <h4 className="font-semibold text-foreground">Primary Endpoints Preview</h4>
              <span className="text-xs px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-700">{primaryEndpoints.length}</span>
            </div>
          </div>
          <div className="p-5 space-y-3">
            {primaryEndpoints.slice(0, 2).map((endpoint: any, idx: number) => (
              <EndpointCard key={endpoint.id || idx} endpoint={endpoint} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
            ))}
            {primaryEndpoints.length > 2 && (
              <p className="text-sm text-muted-foreground text-center">+ {primaryEndpoints.length - 2} more primary endpoints</p>
            )}
          </div>
        </div>
      )}
      
      {sapAnalyses?.statistical_methods?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                <Calculator className="w-5 h-5 text-gray-900" />
              </div>
              <h4 className="font-semibold text-foreground">Statistical Methods Preview</h4>
              <span className="text-xs px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-700">{sapAnalyses.statistical_methods.length}</span>
            </div>
          </div>
          <div className="p-5 space-y-3">
            {sapAnalyses.statistical_methods.slice(0, 2).map((method: any, idx: number) => (
              <StatisticalMethodCard key={method.id || idx} method={method} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
            ))}
            {sapAnalyses.statistical_methods.length > 2 && (
              <p className="text-sm text-muted-foreground text-center">+ {sapAnalyses.statistical_methods.length - 2} more statistical methods</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ObjectivesTab({ objectives, onViewSource, onFieldUpdate }: { objectives: any[]; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!objectives || objectives.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Flag className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study objectives defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {objectives.map((objective: any, idx: number) => (
        <ObjectiveCard key={objective.id || idx} objective={objective} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function EndpointsTab({ endpoints, onViewSource, onFieldUpdate, emptyMessage }: { endpoints: any[]; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void; emptyMessage: string }) {
  if (!endpoints || endpoints.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Target className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {endpoints.map((endpoint: any, idx: number) => (
        <EndpointCard key={endpoint.id || idx} endpoint={endpoint} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function EndpointsViewContent({ data, onViewSource, onFieldUpdate }: EndpointsViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const registry = useCoverageRegistry();
  
  useEffect(() => {
    if (registry) {
      registry.markRendered([
        "id",
        "instanceType",
        "name",
        "description",
        "protocol_endpoints",
        "objectives",
        "endpoints",
        "sap_analyses"
      ]);
    }
  }, [registry]);
  
  const objectives = data?.protocol_endpoints?.objectives || data?.objectives || [];
  const endpoints = data?.protocol_endpoints?.endpoints || data?.endpoints || [];
  const estimands = data?.protocol_endpoints?.estimands || [];
  const analysisPopulations = data?.protocol_endpoints?.analysis_populations || [];
  const sapAnalyses = data?.sap_analyses;
  const extractionStatistics = data?.extraction_statistics || data?.protocol_endpoints?.extraction_statistics;
  
  const primaryEndpoints = endpoints.filter((e: any) => 
    e.level?.decode?.toLowerCase().includes("primary") ||
    e.endpoint_level?.decode?.toLowerCase().includes("primary") ||
    e.endpoint_type?.toLowerCase().includes("primary")
  );
  
  const secondaryEndpoints = endpoints.filter((e: any) => 
    e.level?.decode?.toLowerCase().includes("secondary") ||
    e.endpoint_level?.decode?.toLowerCase().includes("secondary") ||
    e.endpoint_type?.toLowerCase().includes("secondary")
  );
  
  const exploratoryEndpoints = endpoints.filter((e: any) => 
    e.level?.decode?.toLowerCase().includes("exploratory") ||
    e.endpoint_level?.decode?.toLowerCase().includes("exploratory") ||
    e.endpoint_type?.toLowerCase().includes("exploratory") ||
    (!e.level?.decode?.toLowerCase().includes("primary") && 
     !e.level?.decode?.toLowerCase().includes("secondary") &&
     !e.endpoint_level?.decode?.toLowerCase().includes("primary") && 
     !e.endpoint_level?.decode?.toLowerCase().includes("secondary") &&
     !e.endpoint_type?.toLowerCase().includes("primary") &&
     !e.endpoint_type?.toLowerCase().includes("secondary"))
  );
  
  const hasSapData = sapAnalyses && (
    sapAnalyses.statistical_methods?.length > 0 ||
    sapAnalyses.subgroup_analyses?.length > 0 ||
    sapAnalyses.sensitivity_analyses?.length > 0 ||
    sapAnalyses.missing_data_handling ||
    sapAnalyses.multiplicity_adjustment
  );
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "objectives", label: "Objectives", icon: Flag, count: objectives.length },
    { id: "primary", label: "Primary", icon: CheckCircle, count: primaryEndpoints.length },
    { id: "secondary", label: "Secondary", icon: Circle, count: secondaryEndpoints.length },
    { id: "exploratory", label: "Exploratory", icon: TrendingUp, count: exploratoryEndpoints.length },
  ];
  
  if (estimands.length > 0) {
    tabs.push({ id: "estimands", label: "Estimands", icon: Activity, count: estimands.length });
  }
  
  if (analysisPopulations.length > 0) {
    tabs.push({ id: "populations", label: "Populations", icon: Users, count: analysisPopulations.length });
  }
  
  if (hasSapData) {
    tabs.push({ id: "sap", label: "SAP", icon: Calculator });
  }
  
  return (
    <div className="space-y-6" data-testid="endpoints-view">
      <SummaryHeader objectives={objectives} endpoints={endpoints} sapAnalyses={sapAnalyses} />
      
      <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-xl overflow-x-auto" role="tablist" data-testid="endpoints-tab-list">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
                activeTab === tab.id
                  ? "bg-white text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-white/50"
              )}
              role="tab"
              aria-selected={activeTab === tab.id}
              data-testid={`tab-${tab.id}`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
              {tab.count !== undefined && tab.count > 0 && (
                <span className="text-xs px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-700">
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
      
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
        >
          {activeTab === "overview" && <OverviewTab objectives={objectives} endpoints={endpoints} sapAnalyses={sapAnalyses} extractionStatistics={extractionStatistics} estimands={estimands} populations={analysisPopulations} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "objectives" && <ObjectivesTab objectives={objectives} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "primary" && <EndpointsTab endpoints={primaryEndpoints} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} emptyMessage="No primary endpoints defined" />}
          {activeTab === "secondary" && <EndpointsTab endpoints={secondaryEndpoints} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} emptyMessage="No secondary endpoints defined" />}
          {activeTab === "exploratory" && <EndpointsTab endpoints={exploratoryEndpoints} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} emptyMessage="No exploratory endpoints defined" />}
          {activeTab === "estimands" && <EstimandsTab estimands={estimands} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "populations" && <AnalysisPopulationsTab populations={analysisPopulations} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "sap" && <SAPTab sapAnalyses={sapAnalyses} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export function EndpointsView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: EndpointsViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Target className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No endpoints data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <EndpointsViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
