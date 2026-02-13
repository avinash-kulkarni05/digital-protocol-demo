import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  Shield, AlertTriangle, ChevronDown, ChevronRight, FileText,
  Activity, Target, Gauge, AlertCircle, CheckCircle, TrendingUp,
  Users, Building, ClipboardList, BarChart3, Layers, Eye, Percent
} from "lucide-react";
import { UnmappedDataSection } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { EditableText } from "./EditableValue";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";

interface QualityManagementViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "ctq" | "risks" | "monitoring" | "sdv" | "processes";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

function SeverityBadge({ level }: { level: number }) {
  const config = level >= 4 
    ? { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", label: "Critical" }
    : level >= 3
    ? { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", label: "High" }
    : level >= 2
    ? { bg: "bg-yellow-50", border: "border-yellow-200", text: "text-yellow-700", label: "Medium" }
    : { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", label: "Low" };
  
  return (
    <span className={cn("px-2 py-0.5 text-xs font-medium rounded-full border", config.bg, config.border, config.text)}>
      {config.label}
    </span>
  );
}

function ImpactBadge({ impact }: { impact: string }) {
  const lower = (impact || "").toLowerCase();
  const config = lower.includes("catastrophic") || lower.includes("critical")
    ? { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700" }
    : lower.includes("major") || lower.includes("high")
    ? { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700" }
    : lower.includes("moderate") || lower.includes("medium")
    ? { bg: "bg-yellow-50", border: "border-yellow-200", text: "text-yellow-700" }
    : { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700" };
  
  return (
    <span className={cn("px-2 py-0.5 text-xs font-medium rounded-full border", config.bg, config.border, config.text)}>
      {impact}
    </span>
  );
}

function ProbabilityBadge({ probability }: { probability: string }) {
  const lower = (probability || "").toLowerCase();
  const config = lower.includes("certain") || lower.includes("very high")
    ? { bg: "bg-gray-50", text: "text-gray-700" }
    : lower.includes("likely") || lower.includes("high")
    ? { bg: "bg-gray-50", text: "text-gray-700" }
    : lower.includes("possible") || lower.includes("medium")
    ? { bg: "bg-yellow-50", text: "text-yellow-700" }
    : { bg: "bg-gray-50", text: "text-gray-700" };
  
  return (
    <span className={cn("px-2 py-0.5 text-xs font-medium rounded-full", config.bg, config.text)}>
      {probability}
    </span>
  );
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function AccordionSection({ 
  title, 
  icon: Icon, 
  children, 
  defaultOpen = false,
  badge,
  count
}: { 
  title: string; 
  icon: React.ElementType; 
  children: React.ReactNode; 
  defaultOpen?: boolean;
  badge?: React.ReactNode;
  count?: number;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white" data-testid={`accordion-${title.toLowerCase().replace(/\s+/g, '-')}`}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors text-left"
        data-testid={`accordion-toggle-${title.toLowerCase().replace(/\s+/g, '-')}`}
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
            <Icon className="w-4 h-4 text-gray-600" />
          </div>
          <span className="font-semibold text-foreground">{title}</span>
          {count !== undefined && (
            <span className="text-xs text-muted-foreground bg-gray-100 px-2 py-0.5 rounded-full">{count}</span>
          )}
          {badge}
        </div>
        <motion.div
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown className="w-5 h-5 text-gray-400" />
        </motion.div>
      </button>
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
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

function SummaryHeader({ data }: { data: any }) {
  const rbqm = data?.rbqm;
  const ractRegister = rbqm?.ract_register;
  
  const ctqFactors = ractRegister?.critical_to_quality_factors || [];
  const emergentRisks = ractRegister?.emergent_systemic_risks || [];
  const skris = ractRegister?.strategic_risk_indicators || [];
  
  const criticalRisks = emergentRisks.filter((r: any) => 
    (r.impact_severity || "").toLowerCase().includes("catastrophic") ||
    (r.impact_severity || "").toLowerCase().includes("critical")
  ).length;
  
  const highRisks = emergentRisks.filter((r: any) => 
    (r.impact_severity || "").toLowerCase().includes("major")
  ).length;
  
  return (
    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="qm-summary-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Quality Management Overview</h3>
          <p className="text-sm text-muted-foreground">Risk-Based Quality Management (RBQM)</p>
        </div>
      </div>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-ctq-factors">
          <div className="flex items-center gap-2 mb-1">
            <Target className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">CTQ Factors</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{ctqFactors.length}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-systemic-risks">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Systemic Risks</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{emergentRisks.length}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-critical-risks">
          <div className="flex items-center gap-2 mb-1">
            <AlertCircle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Critical/Major</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{criticalRisks + highRisks}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-kris">
          <div className="flex items-center gap-2 mb-1">
            <Gauge className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">KRIs</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{skris.length}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const rbqm = data?.rbqm;
  const provenance = rbqm?.provenance;
  const strategicSummary = rbqm?.ract_register?.strategic_summary;
  const ractRegister = rbqm?.ract_register;
  
  const ctqCount = ractRegister?.critical_to_quality_factors?.length || 0;
  const riskCount = ractRegister?.emergent_systemic_risks?.length || 0;
  const kriCount = ractRegister?.strategic_risk_indicators?.length || 0;
  
  return (
    <div className="space-y-6">
      {provenance && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
              <Activity className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-start justify-between gap-3 mb-2">
                <h4 className="font-bold text-gray-900 text-lg">RBQM Approach</h4>
                <ProvenanceChip provenance={provenance} onViewSource={onViewSource} />
              </div>
              {provenance.derived?.reasoning && (
                <p className="text-sm text-gray-700 leading-relaxed">{provenance.derived.reasoning}</p>
              )}
              {provenance.derived?.supporting_context && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {provenance.derived.supporting_context.map((ctx: string, idx: number) => (
                    <span key={idx} className="text-xs bg-white/70 text-gray-700 px-3 py-1.5 rounded-full border border-gray-200 font-medium">
                      {ctx}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      
      {strategicSummary?.provenance && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <FileText className="w-5 h-5 text-gray-600" />
                </div>
                <h4 className="font-semibold text-foreground">Strategic Summary</h4>
              </div>
              <ProvenanceChip provenance={strategicSummary.provenance} onViewSource={onViewSource} />
            </div>
          </div>
          {strategicSummary.provenance.derived?.reasoning && (
            <div className="p-5">
              <p className="text-sm text-muted-foreground leading-relaxed">{strategicSummary.provenance.derived.reasoning}</p>
            </div>
          )}
        </div>
      )}
      
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-gray-600" />
            Quality Metrics at a Glance
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Target className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{ctqCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">CTQ Factors</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <AlertTriangle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{riskCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Systemic Risks</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Gauge className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{kriCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Key Risk Indicators</p>
            </div>
          </div>
        </div>
      </div>
      
      {data?.monitoring?.sdv_strategy && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <ClipboardList className="w-5 h-5 text-gray-900" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground">SDV Strategy Overview</h4>
                  <p className="text-sm text-muted-foreground">Source Data Verification approach</p>
                </div>
              </div>
              <ProvenanceChip provenance={data.monitoring.sdv_strategy.provenance} onViewSource={onViewSource} />
            </div>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-gray-50 rounded-xl p-4 text-center">
                <p className="text-lg font-bold text-foreground capitalize">{data.monitoring.sdv_strategy.overall_approach?.replace(/_/g, ' ') || 'Risk-based'}</p>
                <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mt-1">Approach</p>
              </div>
              <div className="bg-gray-50 rounded-xl p-4 text-center">
                <p className="text-lg font-bold text-foreground">{data.monitoring.sdv_strategy.default_sdv_percentage || 0}%</p>
                <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mt-1">Default SDV</p>
              </div>
              <div className="bg-gray-50 rounded-xl p-4 text-center">
                <p className="text-lg font-bold text-foreground">{data.monitoring.sdv_strategy.remote_sdv_enabled ? 'Yes' : 'No'}</p>
                <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mt-1">Remote SDV</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CTQFactorsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const ctqFactors = data?.rbqm?.ract_register?.critical_to_quality_factors || [];
  const basePath = "domainSections.qualityManagement.data.rbqm.ract_register.critical_to_quality_factors";

  if (ctqFactors.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Target className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No Critical-to-Quality factors defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {ctqFactors.map((ctq: any, idx: number) => (
        <div key={ctq.ctq_id || idx} className="bg-white border border-gray-200 rounded-xl overflow-hidden" data-testid={`ctq-card-${ctq.ctq_id || idx}`}>
          <div className="p-4 border-b border-gray-100 bg-gradient-to-r from-gray-50/50 to-transparent">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
                  <Target className="w-5 h-5 text-gray-900" />
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-bold text-gray-900 uppercase">
                      <EditableText
                        value={ctq.ctq_id || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.ctq_id`, v) : undefined}
                      />
                    </span>
                    <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
                      <EditableText
                        value={ctq.ctq_category || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.ctq_category`, v) : undefined}
                      />
                    </span>
                    <SeverityBadge level={ctq.severity_score || 3} />
                  </div>
                  <h4 className="font-semibold text-foreground mt-1">
                    <EditableText
                      value={ctq.factor || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.factor`, v) : undefined}
                    />
                  </h4>
                </div>
              </div>
              <ProvenanceChip provenance={ctq.provenance} onViewSource={onViewSource} />
            </div>
          </div>

          <div className="p-4 space-y-4">
            {ctq.clinical_reasoning && (
              <div>
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Clinical Reasoning</span>
                <p className="text-sm text-foreground leading-relaxed">
                  <EditableText
                    value={ctq.clinical_reasoning || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.clinical_reasoning`, v) : undefined}
                  />
                </p>
              </div>
            )}

            {ctq.failure_mode && (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-1">Failure Mode</span>
                <p className="text-sm text-gray-700">
                  <EditableText
                    value={ctq.failure_mode || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.failure_mode`, v) : undefined}
                  />
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs font-medium text-muted-foreground block mb-1">Severity Score</span>
                <span className="text-lg font-bold text-foreground">
                  <EditableText
                    value={String(ctq.severity_score || "N/A")}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.severity_score`, v) : undefined}
                  />/5
                </span>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs font-medium text-muted-foreground block mb-1">Probability Score</span>
                <span className="text-lg font-bold text-foreground">
                  <EditableText
                    value={String(ctq.probability_score || "N/A")}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.probability_score`, v) : undefined}
                  />/5
                </span>
              </div>
            </div>

            {ctq.linked_risk_ids && ctq.linked_risk_ids.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-medium text-muted-foreground">Linked Risks:</span>
                {ctq.linked_risk_ids.map((riskId: string, rIdx: number) => (
                  <span key={riskId} className="text-xs bg-gray-50 text-gray-700 border border-gray-200 px-2 py-0.5 rounded-full">
                    <EditableText
                      value={riskId || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.linked_risk_ids.${rIdx}`, v) : undefined}
                    />
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function RisksTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const emergentRisks = data?.rbqm?.ract_register?.emergent_systemic_risks || [];
  const skris = data?.rbqm?.ract_register?.strategic_risk_indicators || [];
  const riskBasePath = "domainSections.qualityManagement.data.rbqm.ract_register.emergent_systemic_risks";
  const kriBasePath = "domainSections.qualityManagement.data.rbqm.ract_register.strategic_risk_indicators";

  return (
    <div className="space-y-6">
      <AccordionSection
        title="Emergent Systemic Risks"
        icon={AlertTriangle}
        count={emergentRisks.length}
        defaultOpen
      >
        {emergentRisks.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No emergent risks identified</p>
        ) : (
          <div className="space-y-4">
            {emergentRisks.map((risk: any, idx: number) => (
              <div key={risk.risk_id || idx} className="border border-gray-200 rounded-xl overflow-hidden" data-testid={`risk-card-${risk.risk_id || idx}`}>
                <div className="p-4 bg-gradient-to-r from-gray-50/50 to-transparent border-b border-gray-100">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="text-xs font-bold text-gray-900 uppercase">
                          <EditableText
                            value={risk.risk_id || ""}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${riskBasePath}.${idx}.risk_id`, v) : undefined}
                          />
                        </span>
                        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
                          <EditableText
                            value={risk.risk_type?.replace(/_/g, ' ') || ""}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${riskBasePath}.${idx}.risk_type`, v) : undefined}
                          />
                        </span>
                        <ImpactBadge impact={risk.impact_severity} />
                        <ProbabilityBadge probability={risk.probability} />
                      </div>
                      <h4 className="font-semibold text-foreground">
                        <EditableText
                          value={risk.risk_description || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${riskBasePath}.${idx}.risk_description`, v) : undefined}
                        />
                      </h4>
                    </div>
                    <ProvenanceChip provenance={risk.provenance} onViewSource={onViewSource} />
                  </div>
                </div>

                <div className="p-4 space-y-3">
                  {risk.affected_domains && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-medium text-muted-foreground">Affected Domains:</span>
                      {risk.affected_domains.map((domain: string, dIdx: number) => (
                        <span key={domain} className="text-xs bg-gray-50 text-gray-700 border border-gray-200 px-2 py-0.5 rounded-full">
                          <EditableText
                            value={domain || ""}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${riskBasePath}.${idx}.affected_domains.${dIdx}`, v) : undefined}
                          />
                        </span>
                      ))}
                    </div>
                  )}

                  {risk.trigger_conditions && (
                    <div>
                      <span className="text-xs font-medium text-muted-foreground block mb-1">Trigger Conditions</span>
                      <p className="text-sm text-foreground">
                        <EditableText
                          value={risk.trigger_conditions || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${riskBasePath}.${idx}.trigger_conditions`, v) : undefined}
                        />
                      </p>
                    </div>
                  )}

                  {risk.monitoring_approach && (
                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                      <span className="text-xs font-medium text-gray-700 block mb-1">Monitoring Approach</span>
                      <p className="text-sm text-gray-700">
                        <EditableText
                          value={risk.monitoring_approach || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${riskBasePath}.${idx}.monitoring_approach`, v) : undefined}
                        />
                      </p>
                    </div>
                  )}

                  {risk.contingency_plan && (
                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                      <span className="text-xs font-medium text-gray-700 block mb-1">Contingency Plan</span>
                      <p className="text-sm text-gray-700">
                        <EditableText
                          value={risk.contingency_plan || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${riskBasePath}.${idx}.contingency_plan`, v) : undefined}
                        />
                      </p>
                    </div>
                  )}

                  {risk.quantitative_estimate && (
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-gray-400" />
                      <span className="text-sm text-muted-foreground">Estimate: <strong className="text-foreground">
                        <EditableText
                          value={risk.quantitative_estimate || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${riskBasePath}.${idx}.quantitative_estimate`, v) : undefined}
                        />
                      </strong></span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </AccordionSection>

      <AccordionSection
        title="Strategic Risk Indicators (KRIs)"
        icon={Gauge}
        count={skris.length}
      >
        {skris.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No KRIs defined</p>
        ) : (
          <div className="space-y-4">
            {skris.map((kri: any, idx: number) => (
              <div key={kri.kri_id || idx} className="border border-gray-200 rounded-xl overflow-hidden" data-testid={`kri-card-${kri.kri_id || idx}`}>
                <div className="p-4 bg-gradient-to-r from-gray-50/50 to-transparent border-b border-gray-100">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="text-xs font-bold text-gray-900 uppercase">
                          <EditableText
                            value={kri.kri_id || ""}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${kriBasePath}.${idx}.kri_id`, v) : undefined}
                          />
                        </span>
                        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
                          <EditableText
                            value={kri.category?.replace(/_/g, ' ') || ""}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${kriBasePath}.${idx}.category`, v) : undefined}
                          />
                        </span>
                        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-700 rounded-full">
                          <EditableText
                            value={kri.kri_type?.replace(/_/g, ' ') || ""}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${kriBasePath}.${idx}.kri_type`, v) : undefined}
                          />
                        </span>
                      </div>
                      <p className="font-medium text-foreground">
                        <EditableText
                          value={kri.metric || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${kriBasePath}.${idx}.metric`, v) : undefined}
                        />
                      </p>
                    </div>
                    <ProvenanceChip provenance={kri.provenance} onViewSource={onViewSource} />
                  </div>
                </div>

                <div className="p-4 space-y-3">
                  {kri.rationale && (
                    <p className="text-sm text-muted-foreground">
                      <EditableText
                        value={kri.rationale || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${kriBasePath}.${idx}.rationale`, v) : undefined}
                      />
                    </p>
                  )}

                  {kri.thresholds && (
                    <div className="grid grid-cols-3 gap-2">
                      {Object.entries(kri.thresholds).map(([level, config]: [string, any]) => {
                        const colors = {
                          green: "bg-gray-50 border-gray-200 text-gray-700",
                          amber: "bg-gray-50 border-gray-200 text-gray-700",
                          red: "bg-gray-50 border-gray-200 text-gray-700"
                        };
                        return (
                          <div key={level} className={cn("rounded-lg p-2 border text-center", colors[level as keyof typeof colors] || "bg-gray-50")}>
                            <span className="text-xs font-bold uppercase block">{level}</span>
                            <span className="text-sm font-medium">
                              <EditableText
                                value={config.range || ""}
                                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${kriBasePath}.${idx}.thresholds.${level}.range`, v) : undefined}
                              />
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    {kri.frequency && (
                      <span><strong>Frequency:</strong> <EditableText
                        value={kri.frequency || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${kriBasePath}.${idx}.frequency`, v) : undefined}
                      /></span>
                    )}
                    {kri.data_sources && <span><strong>Sources:</strong> {kri.data_sources.join(', ')}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </AccordionSection>
    </div>
  );
}

function SDVStrategyCard({ strategy, onViewSource, onFieldUpdate }: { strategy: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!strategy) return null;

  const provenance = strategy.provenance;
  const pageNumber = provenance?.explicit?.page_number || provenance?.page_number;
  const basePath = "domainSections.qualityManagement.data.monitoring.sdv_strategy";

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden" data-testid="sdv-strategy-card">
      <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50/50 to-transparent">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
              <ClipboardList className="w-5 h-5 text-gray-900" />
            </div>
            <div>
              <h4 className="font-semibold text-foreground">SDV Strategy</h4>
              <p className="text-sm text-muted-foreground">
                <EditableText
                  value={strategy.overall_approach?.replace(/_/g, ' ') || 'Risk-based approach'}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.overall_approach`, v) : undefined}
                />
              </p>
            </div>
          </div>
          {pageNumber && (
            <ProvenanceChip provenance={provenance} onViewSource={onViewSource} />
          )}
        </div>
      </div>

      <div className="p-5 space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="bg-gray-50 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full bg-gray-400"></div>
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Remote SDV</span>
            </div>
            <p className="text-lg font-bold text-foreground">{strategy.remote_sdv_enabled ? 'Enabled' : 'Disabled'}</p>
          </div>
          <div className="bg-gray-50 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full bg-gray-400"></div>
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Default SDV</span>
            </div>
            <p className="text-lg font-bold text-foreground">
              <EditableText
                value={String(strategy.default_sdv_percentage || 0)}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.default_sdv_percentage`, v) : undefined}
              />%
            </p>
          </div>
        </div>

        {strategy.sdv_reduction_criteria?.enabled && (
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
            <div className="flex items-start justify-between mb-3">
              <h5 className="font-medium text-gray-900 flex items-center gap-2">
                <TrendingUp className="w-4 h-4" />
                SDV Reduction Criteria
              </h5>
              {(strategy.sdv_reduction_criteria.provenance?.explicit?.page_number || strategy.sdv_reduction_criteria.provenance?.page_number) && (
                <ProvenanceChip provenance={strategy.sdv_reduction_criteria.provenance} onViewSource={onViewSource} />
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="bg-white/70 rounded-lg p-3 text-center">
                <span className="text-xs text-gray-700 block mb-1">Reduced SDV</span>
                <span className="text-lg font-bold text-gray-700">
                  <EditableText
                    value={String(strategy.sdv_reduction_criteria.reduced_sdv_percentage || 0)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_reduction_criteria.reduced_sdv_percentage`, v) : undefined}
                  />%
                </span>
              </div>
              <div className="bg-white/70 rounded-lg p-3 text-center">
                <span className="text-xs text-gray-700 block mb-1">Min Subjects</span>
                <span className="text-lg font-bold text-gray-700">
                  <EditableText
                    value={String(strategy.sdv_reduction_criteria.minimum_subjects_enrolled || 0)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_reduction_criteria.minimum_subjects_enrolled`, v) : undefined}
                  />
                </span>
              </div>
              <div className="bg-white/70 rounded-lg p-3 text-center">
                <span className="text-xs text-gray-700 block mb-1">Error Threshold</span>
                <span className="text-lg font-bold text-gray-700">
                  <EditableText
                    value={String(strategy.sdv_reduction_criteria.error_rate_threshold_percent || 0)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_reduction_criteria.error_rate_threshold_percent`, v) : undefined}
                  />%
                </span>
              </div>
            </div>
            {strategy.sdv_reduction_criteria.provenance?.derived?.reasoning && (
              <p className="text-sm text-gray-700 mt-3 leading-relaxed">{strategy.sdv_reduction_criteria.provenance.derived.reasoning}</p>
            )}
          </div>
        )}

        {strategy.sdv_escalation_criteria && (
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
            <div className="flex items-start justify-between mb-3">
              <h5 className="font-medium text-gray-900 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" />
                SDV Escalation Criteria
              </h5>
              {(strategy.sdv_escalation_criteria.provenance?.explicit?.page_number || strategy.sdv_escalation_criteria.provenance?.page_number) && (
                <ProvenanceChip provenance={strategy.sdv_escalation_criteria.provenance} onViewSource={onViewSource} />
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="bg-white/70 rounded-lg p-3 text-center">
                <span className="text-xs text-gray-700 block mb-1">Escalated SDV</span>
                <span className="text-lg font-bold text-gray-700">
                  <EditableText
                    value={String(strategy.sdv_escalation_criteria.escalated_sdv_percentage || 0)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_escalation_criteria.escalated_sdv_percentage`, v) : undefined}
                  />%
                </span>
              </div>
              <div className="bg-white/70 rounded-lg p-3 text-center">
                <span className="text-xs text-gray-700 block mb-1">Error Threshold</span>
                <span className="text-lg font-bold text-gray-700">
                  <EditableText
                    value={String(strategy.sdv_escalation_criteria.error_rate_threshold_percent || 0)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_escalation_criteria.error_rate_threshold_percent`, v) : undefined}
                  />%
                </span>
              </div>
            </div>
            {strategy.sdv_escalation_criteria.critical_data_100_percent && (
              <div className="mt-3">
                <span className="text-xs font-medium text-gray-700 block mb-2">100% SDV Critical Data Points:</span>
                <div className="flex flex-wrap gap-2">
                  {strategy.sdv_escalation_criteria.critical_data_100_percent.map((item: string, idx: number) => (
                    <span key={idx} className="text-xs bg-white/70 text-gray-700 border border-gray-300 px-2 py-1 rounded-full">
                      <EditableText
                        value={item.replace(/_/g, ' ') || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_escalation_criteria.critical_data_100_percent.${idx}`, v) : undefined}
                      />
                    </span>
                  ))}
                </div>
              </div>
            )}
            {strategy.sdv_escalation_criteria.provenance?.derived?.reasoning && (
              <p className="text-sm text-gray-700 mt-3 leading-relaxed">{strategy.sdv_escalation_criteria.provenance.derived.reasoning}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MonitoringVisitsCard({ visits, onViewSource, onFieldUpdate }: { visits: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!visits) return null;

  const provenance = visits.provenance;
  const pageNumber = provenance?.explicit?.page_number || provenance?.page_number;
  const basePath = "domainSections.qualityManagement.data.monitoring.monitoring_visits";

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden" data-testid="monitoring-visits-card">
      <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50/50 to-transparent">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
              <Users className="w-5 h-5 text-gray-900" />
            </div>
            <div>
              <h4 className="font-semibold text-foreground">Monitoring Visits</h4>
              <p className="text-sm text-muted-foreground">Site monitoring and inspections</p>
            </div>
          </div>
          {pageNumber && (
            <ProvenanceChip provenance={provenance} onViewSource={onViewSource} />
          )}
        </div>
      </div>

      <div className="p-5 space-y-4">
        {visits.close_out_visit && (
          <div className="bg-gray-50 rounded-xl p-4">
            <h5 className="font-medium text-foreground mb-3">Close-out Visit</h5>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Format:</span>
                <span className="text-sm font-medium text-foreground capitalize">
                  <EditableText
                    value={visits.close_out_visit.format?.replace(/_/g, ' ') || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.close_out_visit.format`, v) : undefined}
                  />
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Timing:</span>
                <span className="text-sm font-medium text-foreground">
                  <EditableText
                    value={visits.close_out_visit.timing?.replace(/_/g, ' ') || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.close_out_visit.timing`, v) : undefined}
                  />
                </span>
              </div>
            </div>
            {visits.close_out_visit.activities && visits.close_out_visit.activities.length > 0 && (
              <div>
                <span className="text-xs font-medium text-muted-foreground block mb-2">Activities:</span>
                <ul className="space-y-1.5">
                  {visits.close_out_visit.activities.map((activity: string, idx: number) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-foreground">
                      <CheckCircle className="w-4 h-4 text-gray-600 mt-0.5 flex-shrink-0" />
                      <span>
                        <EditableText
                          value={activity || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.close_out_visit.activities.${idx}`, v) : undefined}
                        />
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {(visits.close_out_visit.provenance?.explicit?.page_number || visits.close_out_visit.provenance?.page_number) && (
              <div className="mt-3 pt-3 border-t border-gray-200">
                <ProvenanceChip provenance={visits.close_out_visit.provenance} onViewSource={onViewSource} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MonitoringTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const monitoring = data?.monitoring;
  const sdvStrategy = monitoring?.sdv_strategy;
  const monitoringVisits = monitoring?.monitoring_visits;
  const rbqmMonitoring = data?.rbqm?.monitoring_strategy;

  const hasContent = sdvStrategy || monitoringVisits || rbqmMonitoring ||
    (monitoring && Object.keys(monitoring).filter(k => k !== 'provenance' && k !== 'sdv_strategy' && k !== 'monitoring_visits').length > 0);

  if (!hasContent) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Activity className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No monitoring details available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {sdvStrategy && (
        <SDVStrategyCard strategy={sdvStrategy} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      )}

      {monitoringVisits && (
        <MonitoringVisitsCard visits={monitoringVisits} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      )}

      {rbqmMonitoring && (
        <AccordionSection title="RBQM Monitoring Strategy" icon={Gauge}>
          <div className="bg-gray-50 rounded-lg p-4">
            <p className="text-sm text-foreground leading-relaxed">
              <EditableText
                value={typeof rbqmMonitoring === 'string' ? rbqmMonitoring : rbqmMonitoring.description || 'Risk-based quality monitoring approach'}
                onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.qualityManagement.data.rbqm.monitoring_strategy.description", v) : undefined}
              />
            </p>
          </div>
        </AccordionSection>
      )}
    </div>
  );
}

function formatNestedValue(value: any, depth: number = 0): React.ReactNode {
  if (value === null || value === undefined) return <span className="text-muted-foreground italic">Not specified</span>;
  if (typeof value === 'boolean') return <span className="font-medium">{value ? 'Yes' : 'No'}</span>;
  if (typeof value === 'string') return <span className="text-foreground">{value}</span>;
  if (typeof value === 'number') return <span className="font-medium">{String(value)}</span>;
  
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground italic">None</span>;
    if (value.every(item => typeof item === 'string' || typeof item === 'number')) {
      return (
        <div className="flex flex-wrap gap-1.5 mt-1">
          {value.map((item, idx) => (
            <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full">
              {String(item).replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      );
    }
    return (
      <ul className="space-y-2 mt-2">
        {value.map((item, idx) => {
          let displayValue: React.ReactNode;
          if (typeof item === 'object' && item !== null) {
            const stringField = ['name', 'description', 'value', 'title', 'label'].find(
              f => typeof item[f] === 'string' || typeof item[f] === 'number'
            );
            displayValue = stringField ? String(item[stringField]) : formatNestedValue(item, depth + 1);
          } else {
            displayValue = String(item);
          }
          return (
            <li key={idx} className="flex items-start gap-2 text-sm">
              <CheckCircle className="w-4 h-4 text-gray-600 mt-0.5 flex-shrink-0" />
              <div className="flex-1">{displayValue}</div>
            </li>
          );
        })}
      </ul>
    );
  }
  
  if (typeof value === 'object') {
    const entries = Object.entries(value).filter(([k]) => k !== 'provenance' && k !== 'instanceType');
    if (entries.length === 0) return <span className="text-muted-foreground italic">No details</span>;
    
    if (depth > 1) {
      return (
        <div className="text-sm text-foreground">
          {entries.map(([k, v], idx) => (
            <span key={k}>
              {k.replace(/_/g, ' ')}: {typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean' ? String(v) : '...'}
              {idx < entries.length - 1 && ', '}
            </span>
          ))}
        </div>
      );
    }
    
    return (
      <div className={cn("space-y-2", depth > 0 ? "mt-1 pl-3 border-l-2 border-gray-200" : "mt-2")}>
        {entries.map(([k, v]) => (
          <div key={k} className="text-sm">
            <span className="text-muted-foreground capitalize">{k.replace(/_/g, ' ')}: </span>
            {formatNestedValue(v, depth + 1)}
          </div>
        ))}
      </div>
    );
  }
  
  return <span className="text-foreground">{String(value)}</span>;
}

function renderValue(value: any): React.ReactNode {
  return formatNestedValue(value, 0);
}

// NEW TAB: SDV Strategy
function SDVTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const sdvStrategy = data?.sdv_strategy;
  const monitoring = data?.monitoring;
  const basePath = "domainSections.qualityManagement.data.sdv_strategy";
  const monitoringPath = "domainSections.qualityManagement.data.monitoring";

  if (!sdvStrategy && !monitoring) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Eye className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No SDV strategy defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* SDV Strategy Overview */}
      {sdvStrategy && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-50 border border-gray-200 rounded-2xl p-5">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
                <Eye className="w-6 h-6 text-white" />
              </div>
              <div>
                <h4 className="font-bold text-gray-900 text-lg">SDV Strategy</h4>
                {sdvStrategy.overall_approach && (
                  <span className="text-sm text-gray-700">
                    <EditableText
                      value={sdvStrategy.overall_approach || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.overall_approach`, v) : undefined}
                    />
                  </span>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={sdvStrategy.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {sdvStrategy.default_sdv_percentage !== undefined && (
              <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Default SDV %</span>
                <span className="text-xl font-bold text-gray-900">
                  <EditableText
                    value={String(sdvStrategy.default_sdv_percentage)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.default_sdv_percentage`, v) : undefined}
                  />%
                </span>
              </div>
            )}
            {sdvStrategy.remote_sdv_enabled !== undefined && (
              <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Remote SDV</span>
                <span className="text-sm font-medium text-gray-900">
                  {sdvStrategy.remote_sdv_enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Critical Data 100% SDV */}
      {sdvStrategy?.critical_data_100_percent?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-green-600" />
              Critical Data - 100% SDV ({sdvStrategy.critical_data_100_percent.length})
            </h5>
          </div>
          <div className="p-5">
            <div className="flex flex-wrap gap-2">
              {sdvStrategy.critical_data_100_percent.map((item: string, idx: number) => (
                <span key={idx} className="inline-flex items-center px-3 py-1 bg-green-50 text-green-700 text-sm rounded-full border border-green-200">
                  <EditableText
                    value={item || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.critical_data_100_percent.${idx}`, v) : undefined}
                  />
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* SDV Reduction Criteria */}
      {sdvStrategy?.sdv_reduction_criteria && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-5">
          <h5 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-gray-600 rotate-180" />
            SDV Reduction Criteria
          </h5>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {sdvStrategy.sdv_reduction_criteria.enabled !== undefined && (
              <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Enabled</span>
                <span className="text-sm font-medium text-gray-900">
                  {sdvStrategy.sdv_reduction_criteria.enabled ? 'Yes' : 'No'}
                </span>
              </div>
            )}
            {sdvStrategy.sdv_reduction_criteria.minimum_subjects_enrolled && (
              <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Min Subjects</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={String(sdvStrategy.sdv_reduction_criteria.minimum_subjects_enrolled)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_reduction_criteria.minimum_subjects_enrolled`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {sdvStrategy.sdv_reduction_criteria.error_rate_threshold_percent !== undefined && (
              <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Error Rate Threshold</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={String(sdvStrategy.sdv_reduction_criteria.error_rate_threshold_percent)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_reduction_criteria.error_rate_threshold_percent`, v) : undefined}
                  />%
                </span>
              </div>
            )}
            {sdvStrategy.sdv_reduction_criteria.reduced_sdv_percentage !== undefined && (
              <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Reduced SDV %</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={String(sdvStrategy.sdv_reduction_criteria.reduced_sdv_percentage)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_reduction_criteria.reduced_sdv_percentage`, v) : undefined}
                  />%
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* SDV Escalation Criteria */}
      {sdvStrategy?.sdv_escalation_criteria && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5">
          <h5 className="font-semibold text-red-900 mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-red-600" />
            SDV Escalation Criteria
          </h5>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {sdvStrategy.sdv_escalation_criteria.error_rate_threshold_percent !== undefined && (
              <div className="bg-white/70 rounded-lg p-3 border border-red-200">
                <span className="text-xs font-medium text-red-700 uppercase block mb-1">Error Rate Threshold</span>
                <span className="text-sm font-medium text-red-900">
                  <EditableText
                    value={String(sdvStrategy.sdv_escalation_criteria.error_rate_threshold_percent)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_escalation_criteria.error_rate_threshold_percent`, v) : undefined}
                  />%
                </span>
              </div>
            )}
            {sdvStrategy.sdv_escalation_criteria.escalated_sdv_percentage !== undefined && (
              <div className="bg-white/70 rounded-lg p-3 border border-red-200">
                <span className="text-xs font-medium text-red-700 uppercase block mb-1">Escalated SDV %</span>
                <span className="text-sm font-medium text-red-900">
                  <EditableText
                    value={String(sdvStrategy.sdv_escalation_criteria.escalated_sdv_percentage)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_escalation_criteria.escalated_sdv_percentage`, v) : undefined}
                  />%
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Monitoring Strategy */}
      {monitoring?.strategy && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-gray-600" />
            Monitoring Strategy
          </h5>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
              <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Strategy Type</span>
              <span className="text-sm font-medium text-gray-900">
                <EditableText
                  value={monitoring.strategy || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${monitoringPath}.strategy`, v) : undefined}
                />
              </span>
            </div>
            {monitoring.rationale && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200 col-span-2">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Rationale</span>
                <span className="text-sm text-gray-700">
                  <EditableText
                    value={monitoring.rationale || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${monitoringPath}.rationale`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {monitoring.centralized_monitoring_enabled !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Centralized Monitoring</span>
                <span className="text-sm font-medium text-gray-900">
                  {monitoring.centralized_monitoring_enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ProcessesTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const processImprovement = data?.process_improvement;
  const vendorManagement = data?.vendor_management;
  const processPath = "domainSections.qualityManagement.data.process_improvement";
  const vendorPath = "domainSections.qualityManagement.data.vendor_management";

  const hasProcessData = processImprovement && Object.keys(processImprovement).filter(k => k !== 'provenance').length > 0;
  const hasVendorData = vendorManagement && Object.keys(vendorManagement).filter(k => k !== 'provenance').length > 0;

  if (!hasProcessData && !hasVendorData) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <ClipboardList className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No process details available</p>
        <p className="text-sm mt-1">Process improvement and vendor management information will appear here when available.</p>
      </div>
    );
  }

  // Helper function to render editable values
  const renderEditableValue = (value: any, fieldPath: string): React.ReactNode => {
    if (value === null || value === undefined) return <span className="text-muted-foreground italic">Not specified</span>;
    if (typeof value === 'boolean') return <span className="font-medium">{value ? 'Yes' : 'No'}</span>;
    if (typeof value === 'string') return (
      <EditableText
        value={value}
        onSave={onFieldUpdate ? (v) => onFieldUpdate(fieldPath, v) : undefined}
      />
    );
    if (typeof value === 'number') return (
      <EditableText
        value={String(value)}
        onSave={onFieldUpdate ? (v) => onFieldUpdate(fieldPath, v) : undefined}
      />
    );

    if (Array.isArray(value)) {
      if (value.length === 0) return <span className="text-muted-foreground italic">None</span>;
      if (value.every(item => typeof item === 'string' || typeof item === 'number')) {
        return (
          <div className="flex flex-wrap gap-1.5 mt-1">
            {value.map((item, idx) => (
              <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full">
                <EditableText
                  value={String(item).replace(/_/g, ' ')}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${fieldPath}.${idx}`, v) : undefined}
                />
              </span>
            ))}
          </div>
        );
      }
      return (
        <ul className="space-y-2 mt-2">
          {value.map((item, idx) => {
            const displayValue = typeof item === 'object' && item !== null
              ? JSON.stringify(item)
              : String(item);
            return (
              <li key={idx} className="flex items-start gap-2 text-sm">
                <CheckCircle className="w-4 h-4 text-gray-600 mt-0.5 flex-shrink-0" />
                <EditableText
                  value={displayValue}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${fieldPath}.${idx}`, v) : undefined}
                />
              </li>
            );
          })}
        </ul>
      );
    }

    if (typeof value === 'object') {
      const entries = Object.entries(value).filter(([k]) => k !== 'provenance' && k !== 'instanceType');
      if (entries.length === 0) return <span className="text-muted-foreground italic">No details</span>;
      return (
        <div className="space-y-2 mt-2">
          {entries.map(([k, v]) => (
            <div key={k} className="text-sm">
              <span className="text-muted-foreground capitalize">{k.replace(/_/g, ' ')}: </span>
              {typeof v === 'string' || typeof v === 'number' ? (
                <EditableText
                  value={String(v)}
                  onSave={onFieldUpdate ? (val) => onFieldUpdate(`${fieldPath}.${k}`, val) : undefined}
                />
              ) : (
                renderValue(v)
              )}
            </div>
          ))}
        </div>
      );
    }

    return <span className="text-foreground">{String(value)}</span>;
  };

  return (
    <div className="space-y-6">
      {hasProcessData && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50/50 to-transparent">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <ClipboardList className="w-5 h-5 text-gray-900" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground">Process Improvement & CAPA</h4>
                  <p className="text-sm text-muted-foreground">Corrective and Preventive Actions</p>
                </div>
              </div>
              <ProvenanceChip provenance={processImprovement.provenance} onViewSource={onViewSource} />
            </div>
          </div>
          <div className="p-5 space-y-4">
            {Object.entries(processImprovement).filter(([key]) => key !== 'provenance').map(([key, value]: [string, any]) => (
              <div key={key} className="bg-gray-50 rounded-xl p-4">
                <h5 className="text-sm font-medium text-foreground mb-2 capitalize">{key.replace(/_/g, ' ')}</h5>
                {renderEditableValue(value, `${processPath}.${key}`)}
              </div>
            ))}
          </div>
        </div>
      )}

      {hasVendorData && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50/50 to-transparent">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <Building className="w-5 h-5 text-gray-900" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground">Vendor Management</h4>
                  <p className="text-sm text-muted-foreground">Third-party oversight and qualification</p>
                </div>
              </div>
              <ProvenanceChip provenance={vendorManagement.provenance} onViewSource={onViewSource} />
            </div>
          </div>
          <div className="p-5 space-y-4">
            {Object.entries(vendorManagement).filter(([key]) => key !== 'provenance').map(([key, value]: [string, any]) => (
              <div key={key} className="bg-gray-50 rounded-xl p-4">
                <h5 className="text-sm font-medium text-foreground mb-2 capitalize">{key.replace(/_/g, ' ')}</h5>
                {renderEditableValue(value, `${vendorPath}.${key}`)}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function QualityManagementViewContent({ data, onViewSource, onFieldUpdate }: QualityManagementViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  
  
  const ctqFactors = data?.rbqm?.ract_register?.critical_to_quality_factors || [];
  const emergentRisks = data?.rbqm?.ract_register?.emergent_systemic_risks || [];
  const skris = data?.rbqm?.ract_register?.strategic_risk_indicators || [];
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "ctq", label: "CTQ Factors", icon: Target, count: ctqFactors.length },
    { id: "risks", label: "Risks & KRIs", icon: AlertTriangle, count: emergentRisks.length + skris.length },
    { id: "monitoring", label: "Monitoring", icon: Activity },
    { id: "sdv", label: "SDV Strategy", icon: Eye },
    { id: "processes", label: "Processes", icon: ClipboardList },
  ];
  
  return (
    <div className="space-y-6" data-testid="quality-management-view">
      <SummaryHeader data={data} />
      
      <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-xl overflow-x-auto" role="tablist" aria-label="Quality Management sections" data-testid="qm-tab-navigation">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-controls={`tabpanel-${tab.id}`}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
                activeTab === tab.id
                  ? "bg-white text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-white/50"
              )}
              data-testid={`tab-${tab.id}`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
              {tab.count !== undefined && tab.count > 0 && (
                <span className={cn(
                  "text-xs px-1.5 py-0.5 rounded-full",
                  activeTab === tab.id ? "bg-gray-100 text-gray-700" : "bg-gray-200 text-gray-600"
                )}>
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
          role="tabpanel"
          id={`tabpanel-${activeTab}`}
          aria-labelledby={`tab-${activeTab}`}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.15 }}
        >
          {activeTab === "overview" && <OverviewTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "ctq" && <CTQFactorsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "risks" && <RisksTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "monitoring" && <MonitoringTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "sdv" && <SDVTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "processes" && <ProcessesTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function QualityManagementView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: QualityManagementViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No quality management data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <QualityManagementViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
