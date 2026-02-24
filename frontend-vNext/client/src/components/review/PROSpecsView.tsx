import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, ChevronDown, ClipboardList, Smartphone, Calendar, Activity, Layers, Clock, CheckCircle, Globe, Target, BarChart3 } from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { EditableText } from "./EditableValue";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";

interface PROSpecsViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "instruments" | "administration" | "epro";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function AccordionSection({ title, icon: Icon, children, defaultOpen = false, count }: { title: string; icon: React.ElementType; children: React.ReactNode; defaultOpen?: boolean; count?: number; }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white">
      <button type="button" onClick={() => setIsOpen(!isOpen)} className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors text-left">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center"><Icon className="w-4 h-4 text-gray-900" /></div>
          <span className="font-semibold text-foreground">{title}</span>
          {count !== undefined && <span className="text-xs text-muted-foreground bg-gray-100 px-2 py-0.5 rounded-full">{count}</span>}
        </div>
        <motion.div animate={{ rotate: isOpen ? 180 : 0 }} transition={{ duration: 0.2 }}><ChevronDown className="w-5 h-5 text-gray-400" /></motion.div>
      </button>
      <AnimatePresence initial={false}>
        {isOpen && (<motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}><div className="p-4 pt-0 border-t border-gray-100">{children}</div></motion.div>)}
      </AnimatePresence>
    </div>
  );
}

// Component to render CDISC Biomedical Concept objects properly
function CDISCConceptCard({ concept }: { concept: any }) {
  if (!concept) return null;

  // Handle simple string case
  if (typeof concept === 'string') {
    return (
      <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
        <span className="text-sm text-gray-900">{concept}</span>
      </div>
    );
  }

  const domain = concept.domain;
  const cdiscCode = concept.cdiscCode || concept.code;
  const conceptName = concept.conceptName || concept.decode || concept.name;
  const rationale = concept.rationale;
  const confidence = concept.confidence;

  return (
    <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 space-y-3">
      {/* Header with domain badge and code */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          {domain && (
            <span className="inline-flex items-center px-2 py-1 text-xs font-bold bg-gray-900 text-white rounded">
              {domain}
            </span>
          )}
          {cdiscCode && (
            <span className="inline-flex items-center px-2 py-1 text-xs font-mono bg-gray-100 text-gray-800 rounded border border-gray-300">
              {cdiscCode}
            </span>
          )}
        </div>
        {confidence !== undefined && (
          <span className={cn(
            "inline-flex items-center px-2 py-1 text-xs font-medium rounded",
            confidence >= 0.9 ? "bg-green-100 text-green-700" :
            confidence >= 0.7 ? "bg-yellow-100 text-yellow-700" :
            "bg-gray-100 text-gray-600"
          )}>
            {Math.round(confidence * 100)}% confidence
          </span>
        )}
      </div>

      {/* Concept Name */}
      {conceptName && (
        <div>
          <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Concept Name</span>
          <span className="text-sm font-medium text-gray-900">{conceptName}</span>
        </div>
      )}

      {/* Rationale */}
      {rationale && (
        <div>
          <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Rationale</span>
          <span className="text-sm text-gray-800 italic">{rationale}</span>
        </div>
      )}
    </div>
  );
}

function SummaryHeader({ data }: { data: any }) {
  const instrumentCount = data?.pro_instruments?.length || 0;
  const hasEpro = !!data?.epro_system;
  return (
    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="pro-specs-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <ClipboardList className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">PRO Specifications</h3>
          <p className="text-sm text-muted-foreground">Patient-reported outcomes and ePRO systems</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><ClipboardList className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">PRO Instruments</span></div>
          <p className="text-2xl font-bold text-gray-900">{instrumentCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Smartphone className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">ePRO System</span></div>
          <p className="text-lg font-bold text-gray-900">{hasEpro ? "Configured" : "Not specified"}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const instrumentCount = data?.pro_instruments?.length || 0;
  const hasEpro = !!data?.epro_system;
  
  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Layers className="w-5 h-5 text-gray-600" />
            PRO Overview
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <ClipboardList className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{instrumentCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">PRO Instruments</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Smartphone className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasEpro ? "Configured" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">ePRO System</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function InstrumentCard({ instrument, idx, onViewSource, onFieldUpdate }: { instrument: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [showAllData, setShowAllData] = useState(false);
  const basePath = `domainSections.proSpecifications.data.pro_instruments.${idx}`;

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4" data-testid={`instrument-${instrument.id}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <ClipboardList className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <EditableText
              value={instrument.instrument_name}
              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.instrument_name`, v) : undefined}
              className="font-semibold text-foreground"
            />
            {instrument.instrument_type && (<span className="text-xs bg-gray-50 text-gray-700 rounded-full px-2 py-0.5 border border-gray-200">{instrument.instrument_type?.decode || instrument.instrument_type}</span>)}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={instrument.provenance} onViewSource={onViewSource} />
          <button
            onClick={() => setShowAllData(!showAllData)}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
            data-testid={`expand-instrument-${instrument.id}`}
          >
            <ChevronDown className={cn("w-4 h-4 text-gray-500 transition-transform", showAllData && "rotate-180")} />
          </button>
        </div>
      </div>
      {instrument.administration && (
        <div className="mt-3 grid grid-cols-2 gap-3">
          {instrument.administration.timing && (<div className="bg-gray-50 rounded-lg p-2 border border-gray-200"><span className="text-xs text-muted-foreground">Timing:</span> <EditableText value={instrument.administration.timing} onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.administration.timing`, v) : undefined} className="text-sm font-medium" /></div>)}
          {instrument.administration.method && (<div className="bg-gray-50 rounded-lg p-2 border border-gray-200"><span className="text-xs text-muted-foreground">Method:</span> <EditableText value={instrument.administration.method} onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.administration.method`, v) : undefined} className="text-sm font-medium" /></div>)}
        </div>
      )}
      
      <AnimatePresence>
        {showAllData && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-3 pt-3 border-t border-gray-200">
              <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Complete Data</div>
              <SmartDataRender data={instrument} onViewSource={onViewSource} editable={false} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function InstrumentsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const instruments = data.pro_instruments || [];

  if (instruments.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <ClipboardList className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No PRO instruments defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {instruments.map((instrument: any, idx: number) => (
        <InstrumentCard key={instrument.id || idx} instrument={instrument} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

// NEW TAB: Administration Schedule
function AdministrationTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const administration = data?.administration;
  const instruments = data?.pro_instruments || [];
  const basePath = "domainSections.proSpecifications.data";

  if (!administration && instruments.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Clock className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No administration schedule defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Administration Schedule */}
      {administration && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
                <Clock className="w-6 h-6 text-white" />
              </div>
              <h4 className="font-bold text-gray-900 text-lg">Administration Schedule</h4>
            </div>
            <ProvenanceChip provenance={administration.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {administration.frequency && (
              <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Frequency</span>
                <EditableText
                  value={administration.frequency}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.administration.frequency`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
            {administration.compliance_threshold && (
              <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Compliance Threshold</span>
                <EditableText
                  value={`${administration.compliance_threshold}%`}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.administration.compliance_threshold`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
            {administration.completion_requirements && (
              <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Completion Requirements</span>
                <EditableText
                  value={administration.completion_requirements}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.administration.completion_requirements`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
          </div>

          {/* Timepoints */}
          {administration.timepoints?.length > 0 && (
            <div className="mt-4">
              <h5 className="text-sm font-medium text-gray-800 mb-3">Assessment Timepoints ({administration.timepoints.length})</h5>
              <div className="flex flex-wrap gap-2">
                {administration.timepoints.map((tp: any, idx: number) => (
                  <span key={idx} className="inline-flex items-center px-3 py-1 bg-white/80 text-gray-900 text-sm rounded-full border border-gray-200">
                    {typeof tp === 'string' ? tp : tp.timepoint_name || tp.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Instrument Details (deep fields) */}
      {instruments.length > 0 && (
        <div className="space-y-4">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <ClipboardList className="w-5 h-5 text-gray-600" />
            Instrument Details
          </h4>
          {instruments.map((instrument: any, idx: number) => (
            <div key={instrument.id || idx} className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
              <div className="flex items-start justify-between mb-3">
                <EditableText
                  value={instrument.instrument_name}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.pro_instruments.${idx}.instrument_name`, v) : undefined}
                  className="font-medium text-foreground"
                />
                <ProvenanceChip provenance={instrument.provenance} onViewSource={onViewSource} />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {instrument.validation_status && (
                  <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Validation Status</span>
                    <EditableText
                      value={instrument.validation_status}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.pro_instruments.${idx}.validation_status`, v) : undefined}
                      className={cn("text-sm font-medium", instrument.validation_status === 'validated' ? 'text-green-700' : 'text-gray-900')}
                    />
                  </div>
                )}
                {instrument.disease_or_condition && (
                  <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Disease/Condition</span>
                    <EditableText
                      value={instrument.disease_or_condition}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.pro_instruments.${idx}.disease_or_condition`, v) : undefined}
                      className="text-sm font-medium text-gray-900"
                    />
                  </div>
                )}
                {instrument.number_of_items && (
                  <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Number of Items</span>
                    <EditableText
                      value={instrument.number_of_items}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.pro_instruments.${idx}.number_of_items`, v) : undefined}
                      className="text-sm font-medium text-gray-900"
                    />
                  </div>
                )}
                {instrument.recall_period && (
                  <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Recall Period</span>
                    <EditableText
                      value={instrument.recall_period}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.pro_instruments.${idx}.recall_period`, v) : undefined}
                      className="text-sm font-medium text-gray-900"
                    />
                  </div>
                )}
              </div>

              {/* Language Versions */}
              {instrument.language_versions?.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <div className="flex items-center gap-2 mb-2">
                    <Globe className="w-4 h-4 text-gray-600" />
                    <span className="text-sm font-medium text-gray-700">Language Versions ({instrument.language_versions.length})</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {instrument.language_versions.map((lang: string, langIdx: number) => (
                      <span key={langIdx} className="inline-flex items-center px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded">
                        {lang}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Scoring Domains */}
              {instrument.scoring_domains?.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <div className="flex items-center gap-2 mb-2">
                    <BarChart3 className="w-4 h-4 text-gray-600" />
                    <span className="text-sm font-medium text-gray-700">Scoring Domains ({instrument.scoring_domains.length})</span>
                  </div>
                  <div className="space-y-2">
                    {instrument.scoring_domains.map((domain: any, domIdx: number) => (
                      <div key={domIdx} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <span className="font-medium text-gray-900">{domain.domain_name || domain.name || domain}</span>
                        {domain.scoring_method && <span className="text-xs text-gray-600 ml-2">({domain.scoring_method})</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* CDISC Biomedical Concept */}
              {instrument.biomedicalConcept && (
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <div className="flex items-center gap-2 mb-2">
                    <Target className="w-4 h-4 text-gray-600" />
                    <span className="text-sm font-medium text-gray-700">CDISC Biomedical Concept</span>
                  </div>
                  <CDISCConceptCard concept={instrument.biomedicalConcept} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EproTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  if (!data.epro_system) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Smartphone className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No ePRO system configured</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Smartphone className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-3">ePRO System</h4>
            <SmartDataRender data={data.epro_system} onViewSource={onViewSource} />
          </div>
        </div>
      </div>
    </div>
  );
}

function PROSpecsViewContent({ data, onViewSource, onFieldUpdate }: PROSpecsViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  
  
  const instruments = data.pro_instruments || [];
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "instruments", label: "Instruments", icon: ClipboardList, count: instruments.length },
    { id: "administration", label: "Administration", icon: Clock },
    { id: "epro", label: "ePRO", icon: Smartphone },
  ];
  
  return (
    <div className="space-y-6" data-testid="pro-specs-view">
      <SummaryHeader data={data} />
      
      <div className="bg-gray-100 p-1 rounded-xl flex gap-1 overflow-x-auto">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex-shrink-0 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200",
                activeTab === tab.id
                  ? "bg-white text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-gray-50"
              )}
              data-testid={`tab-${tab.id}`}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{tab.label}</span>
              {tab.count !== undefined && (
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
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
        >
          {activeTab === "overview" && <OverviewTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "instruments" && <InstrumentsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "administration" && <AdministrationTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "epro" && <EproTab data={data} onViewSource={onViewSource} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function PROSpecsView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: PROSpecsViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <ClipboardList className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No PRO specifications available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <PROSpecsViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
