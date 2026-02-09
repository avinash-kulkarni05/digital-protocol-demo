import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, ChevronDown, ChevronRight, Shield, AlertTriangle, AlertCircle,
  Activity, Clock, CheckCircle, XCircle, Heart, Layers, BarChart3,
  Users, Eye, BookOpen, Zap, List, GitBranch, Send
} from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";
import { EditableText } from "./EditableValue";

interface SafetyViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "ae_definitions" | "sae_criteria" | "aesi" | "grading" | "dlt" | "causality" | "reporting" | "committees";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

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

function SummaryHeader({ data }: { data: any }) {
  const saeCriteriaCount = data?.sae_criteria?.criteria?.length || 0;
  const aesiCount = data?.aesi_list?.length || 0;
  const hasAEDefinitions = !!data?.ae_definitions;
  const hasSAECriteria = !!data?.sae_criteria;
  const hasGradingSystem = !!data?.grading_system;
  const committeesCount = data?.safety_committees?.length || 0;
  
  return (
    <div className="bg-gradient-to-br from-slate-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="safety-summary-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Safety & Adverse Events</h3>
          <p className="text-sm text-muted-foreground">AE definitions, SAE criteria, AESI, and safety monitoring</p>
        </div>
      </div>
      
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-ae-definitions">
          <div className="flex items-center gap-2 mb-1">
            <Activity className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">AE Defs</span>
          </div>
          <p className="text-lg font-bold text-gray-900">{hasAEDefinitions ? "Yes" : "No"}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-sae-criteria">
          <div className="flex items-center gap-2 mb-1">
            <AlertCircle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">SAE</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{saeCriteriaCount}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-aesi">
          <div className="flex items-center gap-2 mb-1">
            <Eye className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">AESI</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{aesiCount}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-grading">
          <div className="flex items-center gap-2 mb-1">
            <List className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Grading</span>
          </div>
          <p className="text-lg font-bold text-gray-900">{hasGradingSystem ? "Yes" : "No"}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-committees">
          <div className="flex items-center gap-2 mb-1">
            <Users className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Committees</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{committeesCount}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-dlt">
          <div className="flex items-center gap-2 mb-1">
            <Zap className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">DLT</span>
          </div>
          <p className="text-lg font-bold text-gray-900">{data?.dlt_criteria?.has_dlt_criteria ? "Yes" : "No"}</p>
        </div>
      </div>
    </div>
  );
}

function AESICard({ aesi, idx, onViewSource, onFieldUpdate }: { aesi: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [showAllData, setShowAllData] = useState(false);
  const basePath = `domainSections.adverseEvents.data.aesi_list.${idx}`;
  
  return (
    <div className="bg-gray-50 rounded-xl border border-gray-200 overflow-hidden" data-testid={`aesi-card-${aesi.id}`}>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1">
            <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
              <Eye className="w-4 h-4 text-gray-700" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className="font-medium text-foreground">
                  <EditableText
                    value={aesi.aesi_name || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.aesi_name`, v) : undefined}
                  />
                </span>
                {aesi.expedited_reporting && (
                  <span className="text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded-full">Expedited Reporting</span>
                )}
              </div>
              {aesi.meddra_pt && (
                <div className="text-xs text-muted-foreground">
                  MedDRA PT: <EditableText
                    value={aesi.meddra_pt}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.meddra_pt`, v) : undefined}
                  />
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ProvenanceChip provenance={aesi.provenance} onViewSource={onViewSource} />
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              className="p-1 hover:bg-gray-200 rounded transition-colors"
              data-testid={`expand-aesi-${aesi.id}`}
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
            <div className="px-4 pb-4 pt-2 border-t border-gray-200 bg-white space-y-3">
              {aesi.rationale && (
                <div>
                  <span className="text-xs font-medium text-muted-foreground uppercase">Rationale</span>
                  <div className="text-sm text-foreground mt-0.5">
                    <EditableText
                      value={aesi.rationale}
                      multiline
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.rationale`, v) : undefined}
                    />
                  </div>
                </div>
              )}
              
              {aesi.special_monitoring && (
                <div>
                  <span className="text-xs font-medium text-muted-foreground uppercase">Special Monitoring</span>
                  <p className="text-sm text-foreground mt-0.5">{aesi.special_monitoring}</p>
                </div>
              )}
              
              <div className="mt-3 pt-3 border-t border-gray-200">
                <button
                  type="button"
                  onClick={() => setShowAllData(!showAllData)}
                  className="flex items-center gap-2 text-xs font-medium text-gray-600 hover:text-gray-900 transition-colors"
                  data-testid={`toggle-all-data-aesi-${aesi.id}`}
                >
                  <ChevronDown className={cn("w-4 h-4 transition-transform", showAllData && "rotate-180")} />
                  {showAllData ? "Hide Complete Data" : "Show Complete Data"}
                </button>
                
                <AnimatePresence>
                  {showAllData && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="mt-3 p-4 bg-gray-50 rounded-lg border border-gray-200">
                        <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Complete Data</div>
                        <SmartDataRender data={aesi} onViewSource={onViewSource} editable={false} />
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const hasAEDefinitions = !!data?.ae_definitions;
  const hasSAECriteria = !!data?.sae_criteria;
  const saeCriteriaCount = data?.sae_criteria?.criteria?.length || 0;
  const aesiCount = data?.aesi_list?.length || 0;
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Shield className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-2">Safety Overview</h4>
            <p className="text-sm text-gray-700 leading-relaxed">
              This section defines the safety monitoring framework for the clinical trial, including adverse event definitions, 
              serious adverse event criteria, adverse events of special interest (AESI), and reporting requirements.
            </p>
          </div>
        </div>
      </div>
      
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-gray-600" />
            Safety Metrics at a Glance
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Activity className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasAEDefinitions ? "Defined" : "Not Defined"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">AE Definitions</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <AlertCircle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{saeCriteriaCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">SAE Criteria</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Eye className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{aesiCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">AESI</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Shield className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasSAECriteria ? "Complete" : "Incomplete"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">SAE Framework</p>
            </div>
          </div>
        </div>
      </div>
      
      {data?.grading_system && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <List className="w-5 h-5 text-gray-900" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground">Grading System</h4>
                  <div className="text-sm text-muted-foreground">
                    <EditableText
                      value={data.grading_system.system_name || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.grading_system.system_name", v) : undefined}
                    />
                    {" "}
                    <EditableText
                      value={data.grading_system.system_version || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.grading_system.system_version", v) : undefined}
                    />
                  </div>
                </div>
              </div>
              <ProvenanceChip provenance={data.grading_system.provenance} onViewSource={onViewSource} />
            </div>
          </div>
        </div>
      )}
      
      {data?.coding_dictionary && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <BookOpen className="w-5 h-5 text-gray-900" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground">Coding Dictionary</h4>
                  <div className="text-sm text-muted-foreground">
                    <EditableText
                      value={data.coding_dictionary.dictionary_name || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.coding_dictionary.dictionary_name", v) : undefined}
                    />
                    {" "}
                    <EditableText
                      value={data.coding_dictionary.dictionary_version || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.coding_dictionary.dictionary_version", v) : undefined}
                    />
                  </div>
                </div>
              </div>
              <ProvenanceChip provenance={data.coding_dictionary.provenance} onViewSource={onViewSource} />
            </div>
          </div>
        </div>
      )}
      
      {data?.ae_definitions?.ae_definition && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <Activity className="w-5 h-5 text-gray-900" />
                </div>
                <h4 className="font-semibold text-foreground">AE Definition Summary</h4>
              </div>
              <ProvenanceChip provenance={data.ae_definitions?.provenance} onViewSource={onViewSource} />
            </div>
          </div>
          <div className="p-5">
            <div className="text-sm text-muted-foreground leading-relaxed">
              <EditableText
                value={data.ae_definitions.ae_definition || ""}
                multiline
                onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.ae_definitions.ae_definition", v) : undefined}
              />
            </div>
          </div>
        </div>
      )}

      {data?.sae_criteria?.sae_definition && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <AlertCircle className="w-5 h-5 text-gray-900" />
                </div>
                <h4 className="font-semibold text-foreground">SAE Definition Summary</h4>
              </div>
              <ProvenanceChip provenance={data.sae_criteria?.provenance} onViewSource={onViewSource} />
            </div>
          </div>
          <div className="p-5">
            <div className="text-sm text-muted-foreground leading-relaxed">
              <EditableText
                value={data.sae_criteria.sae_definition || ""}
                multiline
                onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.sae_criteria.sae_definition", v) : undefined}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AEDefinitionsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!data) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Activity className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No adverse event definitions available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Activity className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Adverse Event Definition</h4>
              <ProvenanceChip provenance={data.provenance} onViewSource={onViewSource} />
            </div>

            <div className="text-sm text-gray-700 leading-relaxed mb-4">
              <EditableText
                value={data.ae_definition}
                multiline
                onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.ae_definitions.ae_definition", v) : undefined}
              />
            </div>
            
            <div className="space-y-3">
              {data.teae_definition && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">TEAE Definition</span>
                  <div className="text-sm text-gray-900">
                    <EditableText
                      value={data.teae_definition}
                      multiline
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.ae_definitions.teae_definition", v) : undefined}
                    />
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {data.collection_start && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="w-4 h-4 text-gray-900" />
                      <span className="text-xs font-medium text-gray-900 uppercase tracking-wider">Collection Start</span>
                    </div>
                    <div className="text-sm font-medium text-gray-900">
                      <EditableText
                        value={data.collection_start}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.ae_definitions.collection_start", v) : undefined}
                      />
                    </div>
                  </div>
                )}
                {data.collection_end && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="w-4 h-4 text-gray-900" />
                      <span className="text-xs font-medium text-gray-900 uppercase tracking-wider">Collection End</span>
                    </div>
                    <div className="text-sm font-medium text-gray-900">
                      <EditableText
                        value={data.collection_end}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.ae_definitions.collection_end", v) : undefined}
                      />
                    </div>
                  </div>
                )}
                {data.collection_end_days && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="w-4 h-4 text-gray-900" />
                      <span className="text-xs font-medium text-gray-900 uppercase tracking-wider">Collection Days</span>
                    </div>
                    <p className="text-sm font-medium text-gray-900">{data.collection_end_days} days</p>
                  </div>
                )}
              </div>
              
              {data.pre_existing_condition_handling && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Pre-existing Conditions</span>
                  <div className="text-sm text-gray-900">
                    <EditableText
                      value={data.pre_existing_condition_handling}
                      multiline
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.ae_definitions.pre_existing_condition_handling", v) : undefined}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SAECriteriaTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!data) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <AlertCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No SAE criteria defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <AlertCircle className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Serious Adverse Event (SAE) Criteria</h4>
              <ProvenanceChip provenance={data.provenance} onViewSource={onViewSource} />
            </div>

            {data.sae_definition && (
              <div className="text-sm text-gray-700 leading-relaxed mb-4">
                <EditableText
                  value={data.sae_definition}
                  multiline
                  onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.adverseEvents.data.sae_criteria.sae_definition", v) : undefined}
                />
              </div>
            )}
            
            {data.criteria && data.criteria.length > 0 && (
              <div className="space-y-2">
                {data.criteria.map((criterion: any, idx: number) => (
                  <div key={criterion.id || idx} className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2 flex-1">
                        <AlertTriangle className="w-4 h-4 text-gray-600 mt-0.5 flex-shrink-0" />
                        <div className="flex-1">
                          <span className="text-sm font-medium text-gray-900">
                            <EditableText
                              value={criterion.criterion_type?.decode || criterion.definition || ""}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`domainSections.adverseEvents.data.sae_criteria.criteria.${idx}.definition`, v) : undefined}
                            />
                          </span>
                          {criterion.definition && criterion.criterion_type?.decode && (
                            <div className="text-xs text-gray-700 mt-1">
                              <EditableText
                                value={criterion.definition}
                                multiline
                                onSave={onFieldUpdate ? (v) => onFieldUpdate(`domainSections.adverseEvents.data.sae_criteria.criteria.${idx}.definition`, v) : undefined}
                              />
                            </div>
                          )}
                          {criterion.exclusions && criterion.exclusions.length > 0 && (
                            <div className="mt-2">
                              <span className="text-xs font-medium text-muted-foreground uppercase">Exclusions:</span>
                              <ul className="text-xs text-gray-600 list-disc list-inside mt-1">
                                {criterion.exclusions.map((exclusion: string, exIdx: number) => (
                                  <li key={exIdx}>
                                    <EditableText
                                      value={exclusion}
                                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`domainSections.adverseEvents.data.sae_criteria.criteria.${idx}.exclusions.${exIdx}`, v) : undefined}
                                    />
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </div>
                      <ProvenanceChip provenance={criterion.provenance} onViewSource={onViewSource} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function AESITab({ aesiList, onViewSource, onFieldUpdate }: { aesiList: any[]; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!aesiList || aesiList.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Eye className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No adverse events of special interest defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm mb-4">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Eye className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-2">Adverse Events of Special Interest (AESI)</h4>
            <p className="text-sm text-gray-700 leading-relaxed">
              These are adverse events that require special monitoring and expedited reporting based on the known safety profile of the investigational product.
            </p>
          </div>
        </div>
      </div>
      
      {aesiList.map((aesi: any, idx: number) => (
        <AESICard key={aesi.id || idx} aesi={aesi} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function GradingTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  if (!data?.grading_system) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <List className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No grading system defined</p>
      </div>
    );
  }
  
  const grading = data.grading_system;
  const coding = data.coding_dictionary;
  const dlt = data.dlt_criteria;
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <List className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <h4 className="font-bold text-gray-900 text-lg">Grading System</h4>
                <p className="text-sm text-muted-foreground">{grading.system_name} {grading.system_version}</p>
              </div>
              <ProvenanceChip provenance={grading.provenance} onViewSource={onViewSource} />
            </div>
            
            {grading.grade_definitions && grading.grade_definitions.length > 0 && (
              <div className="space-y-2">
                {grading.grade_definitions.map((grade: any, idx: number) => (
                  <div key={idx} className="bg-white/70 rounded-lg p-3 border border-gray-200 flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center font-bold text-gray-700">
                      {grade.grade}
                    </div>
                    <div>
                      <span className="text-sm font-medium text-gray-900">{grade.label}</span>
                      {grade.definition && grade.definition !== grade.label && (
                        <p className="text-xs text-gray-600">{grade.definition}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
      
      {coding && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <BookOpen className="w-5 h-5 text-gray-900" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground">Coding Dictionary</h4>
                  <p className="text-sm text-muted-foreground">{coding.dictionary_name} {coding.dictionary_version || ''}</p>
                </div>
              </div>
              <ProvenanceChip provenance={coding.provenance} onViewSource={onViewSource} />
            </div>
          </div>
        </div>
      )}
      
      {dlt && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <Zap className="w-5 h-5 text-gray-900" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground">Dose Limiting Toxicity (DLT) Criteria</h4>
                  <p className="text-sm text-muted-foreground">
                    {dlt.has_dlt_criteria ? "DLT criteria are defined" : "No DLT criteria defined"}
                  </p>
                </div>
              </div>
              <ProvenanceChip provenance={dlt.provenance} onViewSource={onViewSource} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DLTTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const dlt = data?.dlt_criteria;

  if (!dlt || !dlt.has_dlt_criteria) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Zap className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No dose limiting toxicity criteria defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Zap className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Dose Limiting Toxicity (DLT) Criteria</h4>
              <ProvenanceChip provenance={dlt.provenance} onViewSource={onViewSource} />
            </div>
            <p className="text-sm text-gray-700 leading-relaxed">
              Criteria for determining dose limiting toxicities and maximum tolerated dose.
            </p>
          </div>
        </div>
      </div>

      {/* Observation Period */}
      {dlt.dlt_observation_period && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                <Clock className="w-5 h-5 text-gray-900" />
              </div>
              <h4 className="font-semibold text-foreground">DLT Observation Period</h4>
            </div>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {dlt.dlt_observation_period.duration_days && (
                <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Duration</span>
                  <p className="text-sm font-medium text-gray-900">{dlt.dlt_observation_period.duration_days} days</p>
                </div>
              )}
              {dlt.dlt_observation_period.start_reference && (
                <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Start Reference</span>
                  <p className="text-sm text-gray-900">{dlt.dlt_observation_period.start_reference}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* DLT Definitions */}
      {dlt.dlt_definitions && dlt.dlt_definitions.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-gray-900" />
              </div>
              <h4 className="font-semibold text-foreground">DLT Definitions</h4>
              <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">{dlt.dlt_definitions.length}</span>
            </div>
          </div>
          <div className="p-5 space-y-3">
            {dlt.dlt_definitions.map((def: any, idx: number) => (
              <div key={def.id || idx} className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0 font-bold text-gray-700 text-sm">
                    {def.id || idx + 1}
                  </div>
                  <div className="flex-1">
                    {def.category && (
                      <span className="text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded-full mb-2 inline-block">
                        {def.category}
                      </span>
                    )}
                    <p className="text-sm text-gray-900 font-medium">{def.description}</p>

                    <div className="flex flex-wrap gap-3 mt-2">
                      {def.grade_threshold && (
                        <span className="text-xs text-gray-600">
                          Grade: <span className="font-medium">{def.grade_threshold}</span>
                        </span>
                      )}
                      {def.duration_requirement && (
                        <span className="text-xs text-gray-600">
                          Duration: <span className="font-medium">{def.duration_requirement}</span>
                        </span>
                      )}
                    </div>

                    {def.exceptions && def.exceptions.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-gray-200">
                        <span className="text-xs font-medium text-muted-foreground uppercase">Exceptions:</span>
                        <ul className="text-xs text-gray-600 list-disc list-inside mt-1">
                          {def.exceptions.map((exception: string, exIdx: number) => (
                            <li key={exIdx}>{exception}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* MTD Determination */}
      {dlt.mtd_determination && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                <Activity className="w-5 h-5 text-gray-900" />
              </div>
              <h4 className="font-semibold text-foreground">MTD Determination</h4>
            </div>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {dlt.mtd_determination.method && (
                <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Method</span>
                  <p className="text-sm text-gray-900">{dlt.mtd_determination.method}</p>
                </div>
              )}
              {dlt.mtd_determination.dlt_rate_threshold !== undefined && (
                <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">DLT Rate Threshold</span>
                  <p className="text-sm font-medium text-gray-900">
                    {(dlt.mtd_determination.dlt_rate_threshold * 100).toFixed(0)}%
                  </p>
                </div>
              )}
              {dlt.mtd_determination.minimum_patients && (
                <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Minimum Patients</span>
                  <p className="text-sm font-medium text-gray-900">{dlt.mtd_determination.minimum_patients}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CommitteesTab({ committees, onViewSource }: { committees: any[]; onViewSource?: (page: number) => void }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!committees || committees.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No safety committees defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm mb-4">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Users className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-2">Safety Committees</h4>
            <p className="text-sm text-gray-700 leading-relaxed">
              Independent committees responsible for oversight and adjudication of safety data.
            </p>
          </div>
        </div>
      </div>

      {committees.map((committee: any, idx: number) => {
        const hasDetails = committee.review_frequency || committee.responsibilities?.length > 0 || committee.charter_reference;
        const isExpanded = expandedId === (committee.id || idx.toString());

        return (
          <div key={committee.id || idx} className="bg-gray-50 rounded-xl border border-gray-200 overflow-hidden" data-testid={`committee-${committee.id}`}>
            <div className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 flex-1">
                  <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
                    <Users className="w-4 h-4 text-gray-700" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="font-medium text-foreground">{committee.committee_name}</span>
                      {committee.committee_type?.decode && (
                        <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">
                          {committee.committee_type.decode}
                        </span>
                      )}
                      {committee.review_frequency && (
                        <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">
                          {committee.review_frequency}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <ProvenanceChip provenance={committee.provenance} onViewSource={onViewSource} />
                  {hasDetails && (
                    <button
                      type="button"
                      onClick={() => setExpandedId(isExpanded ? null : (committee.id || idx.toString()))}
                      className="p-1 hover:bg-gray-200 rounded transition-colors"
                    >
                      {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
                    </button>
                  )}
                </div>
              </div>
            </div>

            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="px-4 pb-4 pt-2 border-t border-gray-200 bg-white space-y-3">
                    {committee.review_frequency && (
                      <div className="flex items-start gap-2">
                        <Clock className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                        <div>
                          <span className="text-xs font-medium text-muted-foreground uppercase">Review Frequency</span>
                          <p className="text-sm text-foreground">{committee.review_frequency}</p>
                        </div>
                      </div>
                    )}

                    {committee.responsibilities && committee.responsibilities.length > 0 && (
                      <div>
                        <span className="text-xs font-medium text-muted-foreground uppercase">Responsibilities</span>
                        <ul className="mt-1 space-y-1">
                          {committee.responsibilities.map((resp: string, ridx: number) => (
                            <li key={ridx} className="flex items-start gap-2 text-sm text-gray-700">
                              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 mt-2 flex-shrink-0" />
                              <span>{resp}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {committee.charter_reference && (
                      <div className="flex items-start gap-2">
                        <BookOpen className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                        <div>
                          <span className="text-xs font-medium text-muted-foreground uppercase">Charter Reference</span>
                          <p className="text-sm text-foreground">{committee.charter_reference}</p>
                        </div>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}

function CausalityTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  if (!data) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <GitBranch className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No causality assessment data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <GitBranch className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Causality Assessment</h4>
              <ProvenanceChip provenance={data.provenance} onViewSource={onViewSource} />
            </div>

            {data.method_description && (
              <p className="text-sm text-gray-700 leading-relaxed mb-4">{data.method_description}</p>
            )}

            {/* Assessment Method and Assessor */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              {data.assessment_method && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Assessment Method</span>
                  <p className="text-sm text-gray-900">{data.assessment_method}</p>
                </div>
              )}
              {data.assessor && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Assessor</span>
                  <p className="text-sm text-gray-900">{data.assessor}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {data.categories && data.categories.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h4 className="font-semibold text-foreground flex items-center gap-2">
              <GitBranch className="w-5 h-5 text-gray-600" />
              Causality Categories
            </h4>
          </div>
          <div className="p-5 space-y-3">
            {data.categories.map((category: any, idx: number) => (
              <div key={category.id || idx} className="bg-gray-50 rounded-xl p-4 border border-gray-200" data-testid={`causality-category-${category.id || idx}`}>
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-gray-200 flex items-center justify-center flex-shrink-0">
                    <GitBranch className="w-4 h-4 text-gray-700" />
                  </div>
                  <div className="flex-1">
                    <span className="font-medium text-gray-900">
                      {category.category_type?.decode || "Unknown Category"}
                    </span>
                    {category.definition && (
                      <p className="text-sm text-gray-600 mt-1 leading-relaxed">{category.definition}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ReportingTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  if (!data) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Send className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No reporting procedures data available</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Send className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Reporting Procedures</h4>
              <ProvenanceChip provenance={data.provenance} onViewSource={onViewSource} />
            </div>
            <p className="text-sm text-gray-700 leading-relaxed">
              Guidelines for reporting adverse events, serious adverse events, and other safety-related events.
            </p>
          </div>
        </div>
      </div>
      
      {data.routine_ae_reporting && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <Activity className="w-5 h-5 text-gray-900" />
                </div>
                <h4 className="font-semibold text-foreground">Routine AE Reporting</h4>
              </div>
              <ProvenanceChip provenance={data.routine_ae_reporting.provenance} onViewSource={onViewSource} />
            </div>
          </div>
          <div className="p-5 space-y-3">
            {data.routine_ae_reporting.timeline_description && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Timeline</span>
                <p className="text-sm text-gray-700">{data.routine_ae_reporting.timeline_description}</p>
              </div>
            )}
            {data.routine_ae_reporting.timeline_hours && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <div className="flex items-center gap-2 mb-1">
                  <Clock className="w-4 h-4 text-gray-900" />
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider">Timeline (Hours)</span>
                </div>
                <p className="text-sm font-medium text-gray-900">{data.routine_ae_reporting.timeline_hours} hours</p>
              </div>
            )}
            {data.routine_ae_reporting.method && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Method</span>
                <p className="text-sm text-gray-700">{data.routine_ae_reporting.method}</p>
              </div>
            )}
          </div>
        </div>
      )}
      
      {data.sae_reporting && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <AlertCircle className="w-5 h-5 text-gray-900" />
                </div>
                <h4 className="font-semibold text-foreground">SAE Reporting</h4>
              </div>
              <ProvenanceChip provenance={data.sae_reporting.provenance} onViewSource={onViewSource} />
            </div>
          </div>
          <div className="p-5 space-y-3">
            {data.sae_reporting.initial_report_hours && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <div className="flex items-center gap-2 mb-1">
                  <Clock className="w-4 h-4 text-gray-900" />
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider">Initial Report Timeline</span>
                </div>
                <p className="text-sm font-medium text-gray-900">{data.sae_reporting.initial_report_hours} hours</p>
              </div>
            )}
            {data.sae_reporting.recipients && data.sae_reporting.recipients.length > 0 && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Recipients</span>
                <div className="flex flex-wrap gap-2">
                  {data.sae_reporting.recipients.map((recipient: string, idx: number) => (
                    <span key={idx} className="text-xs bg-gray-200 text-gray-700 px-2 py-1 rounded-full">{recipient}</span>
                  ))}
                </div>
              </div>
            )}
            {data.sae_reporting.method && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Method</span>
                <p className="text-sm text-gray-700">{data.sae_reporting.method}</p>
              </div>
            )}
          </div>
        </div>
      )}
      
      {data.pregnancy_reporting && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <Heart className="w-5 h-5 text-gray-900" />
                </div>
                <h4 className="font-semibold text-foreground">Pregnancy Reporting</h4>
              </div>
              <ProvenanceChip provenance={data.pregnancy_reporting.provenance} onViewSource={onViewSource} />
            </div>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {data.pregnancy_reporting.timeline_hours && (
                <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                  <div className="flex items-center gap-2 mb-1">
                    <Clock className="w-4 h-4 text-gray-900" />
                    <span className="text-xs font-medium text-gray-900 uppercase tracking-wider">Timeline</span>
                  </div>
                  <p className="text-sm font-medium text-gray-900">{data.pregnancy_reporting.timeline_hours} hours</p>
                </div>
              )}
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Outcome Tracking</span>
                <p className="text-sm font-medium text-gray-900">{data.pregnancy_reporting.outcome_tracking ? "Yes" : "No"}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Partner Pregnancy</span>
                <p className="text-sm font-medium text-gray-900">{data.pregnancy_reporting.partner_pregnancy ? "Required" : "Not Required"}</p>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {data.expedited_reporting_criteria && data.expedited_reporting_criteria.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                <Zap className="w-5 h-5 text-gray-900" />
              </div>
              <h4 className="font-semibold text-foreground">Expedited Reporting Criteria</h4>
            </div>
          </div>
          <div className="p-5 space-y-2">
            {data.expedited_reporting_criteria.map((criterion: string, idx: number) => (
              <div key={idx} className="bg-gray-50 rounded-lg p-3 border border-gray-200 flex items-start gap-2">
                <Zap className="w-4 h-4 text-gray-600 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-gray-700">{criterion}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      
      {data.unblinding_procedures && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                <Eye className="w-5 h-5 text-gray-900" />
              </div>
              <h4 className="font-semibold text-foreground">Unblinding Procedures</h4>
            </div>
          </div>
          <div className="p-5">
            <p className="text-sm text-gray-700 leading-relaxed">{data.unblinding_procedures}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function SafetyViewContent({ data, onViewSource, onFieldUpdate }: SafetyViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  
  
  const saeCriteriaCount = data?.sae_criteria?.criteria?.length || 0;
  const aesiCount = data?.aesi_list?.length || 0;
  const committeesCount = data?.safety_committees?.length || 0;
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "ae_definitions", label: "AE Definitions", icon: Activity, count: data?.ae_definitions ? 1 : 0 },
    { id: "sae_criteria", label: "SAE Criteria", icon: AlertCircle, count: saeCriteriaCount },
  ];
  
  if (aesiCount > 0) {
    tabs.push({ id: "aesi", label: "AESI", icon: Eye, count: aesiCount });
  }
  
  if (data?.grading_system || data?.coding_dictionary) {
    tabs.push({ id: "grading", label: "Grading & Coding", icon: List });
  }

  if (data?.dlt_criteria?.has_dlt_criteria) {
    tabs.push({ id: "dlt", label: "DLT Criteria", icon: Zap, count: data.dlt_criteria.dlt_definitions?.length || 0 });
  }
  
  if (committeesCount > 0) {
    tabs.push({ id: "committees", label: "Committees", icon: Users, count: committeesCount });
  }
  
  if (data?.causality_assessment) {
    tabs.push({ id: "causality", label: "Causality", icon: GitBranch, count: data.causality_assessment.categories?.length || 0 });
  }
  
  if (data?.reporting_procedures) {
    tabs.push({ id: "reporting", label: "Reporting", icon: Send });
  }
  
  return (
    <div className="space-y-6" data-testid="safety-view">
      <SummaryHeader data={data} />
      
      <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-xl overflow-x-auto" role="tablist" data-testid="safety-tab-list">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex-shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
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
          {activeTab === "overview" && <OverviewTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "ae_definitions" && <AEDefinitionsTab data={data.ae_definitions} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "sae_criteria" && <SAECriteriaTab data={data.sae_criteria} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "aesi" && <AESITab aesiList={data.aesi_list} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "grading" && <GradingTab data={data} onViewSource={onViewSource} />}
          {activeTab === "dlt" && <DLTTab data={data} onViewSource={onViewSource} />}
          {activeTab === "committees" && <CommitteesTab committees={data.safety_committees} onViewSource={onViewSource} />}
          {activeTab === "causality" && <CausalityTab data={data.causality_assessment} onViewSource={onViewSource} />}
          {activeTab === "reporting" && <ReportingTab data={data.reporting_procedures} onViewSource={onViewSource} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function SafetyView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: SafetyViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No safety data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <SafetyViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
