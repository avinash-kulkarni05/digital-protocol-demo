import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, ChevronDown, Scan, Eye, Target, Star, Layers, Users, CheckCircle, Settings, GraduationCap, Image } from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { EditableText } from "./EditableValue";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";

interface ImagingViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "modalities" | "criteria" | "reading" | "bicr";

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

function SummaryHeader({ data }: { data: any }) {
  const modalityCount = data?.imaging_modalities?.length || 0;
  const criteria = data?.response_criteria?.primary_criteria || "Not specified";
  const hasCentralReading = !!data?.central_reading;
  return (
    <div className="bg-gradient-to-br from-slate-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="imaging-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <Scan className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Imaging & Central Reading</h3>
          <p className="text-sm text-muted-foreground">Response criteria and imaging modalities</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Target className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Response Criteria</span></div>
          <p className="text-sm font-bold text-gray-900 truncate">{criteria}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Scan className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Modalities</span></div>
          <p className="text-2xl font-bold text-gray-900">{modalityCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Eye className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Central Reading</span></div>
          <p className="text-lg font-bold text-gray-900">{hasCentralReading ? "Yes" : "No"}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const modalityCount = data?.imaging_modalities?.length || 0;
  const hasCentralReading = !!data?.central_reading;
  
  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Layers className="w-5 h-5 text-gray-600" />
            Imaging Overview
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Target className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-sm font-bold text-gray-900">{data?.response_criteria?.primary_criteria || "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Response Criteria</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Scan className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{modalityCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Modalities</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Eye className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasCentralReading ? "Yes" : "No"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Central Reading</p>
            </div>
          </div>
        </div>
      </div>
      
      {data.response_criteria && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
              <Target className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-start justify-between gap-3 mb-3">
                <h4 className="font-bold text-gray-900 text-lg">Response Criteria</h4>
                <ProvenanceChip provenance={data.response_criteria.provenance} onViewSource={onViewSource} />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Primary Criteria</span>
                  <EditableText
                    value={data.response_criteria.primary_criteria}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.imagingCentralReading.data.response_criteria.primary_criteria", v) : undefined}
                    className="font-semibold text-gray-900"
                  />
                </div>
                {data.response_criteria.criteria_version && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Version</span>
                    <EditableText
                      value={data.response_criteria.criteria_version}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.imagingCentralReading.data.response_criteria.criteria_version", v) : undefined}
                      className="font-semibold text-gray-900"
                    />
                  </div>
                )}
              </div>
              {data.response_criteria.modifications && (
                <EditableText
                  value={data.response_criteria.modifications}
                  multiline
                  onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.imagingCentralReading.data.response_criteria.modifications", v) : undefined}
                  className="text-sm text-gray-700 mt-3"
                />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ModalityCard({ modality, idx, onViewSource, onFieldUpdate }: { modality: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [showAllData, setShowAllData] = useState(false);
  const basePath = `domainSections.imagingCentralReading.data.imaging_modalities.${idx}`;

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
            <Scan className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <EditableText
                value={modality.modality_type}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.modality_type`, v) : undefined}
                className="font-medium text-foreground"
              />
              {modality.preferred_modality && (<span className="text-xs bg-gray-50 text-gray-700 rounded-full px-2 py-0.5 border border-gray-200 flex items-center gap-1"><Star className="w-3 h-3" /> Preferred</span>)}
            </div>
            {modality.body_regions?.length > 0 && (<p className="text-sm text-muted-foreground">{modality.body_regions.join(', ')}</p>)}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={modality.provenance} onViewSource={onViewSource} />
          <button
            onClick={() => setShowAllData(!showAllData)}
            className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
            data-testid={`expand-modality-${idx}`}
          >
            <motion.div animate={{ rotate: showAllData ? 180 : 0 }} transition={{ duration: 0.2 }}>
              <ChevronDown className="w-4 h-4 text-gray-500" />
            </motion.div>
          </button>
        </div>
      </div>
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
              <SmartDataRender data={modality} onViewSource={onViewSource} editable={false} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ModalitiesTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const modalities = data.imaging_modalities || [];

  if (modalities.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Scan className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No imaging modalities defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {modalities.map((modality: any, idx: number) => (
        <ModalityCard key={modality.modality_id || idx} modality={modality} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

// NEW TAB: Response Criteria Details
function CriteriaTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const criteria = data?.response_criteria;
  const basePath = "domainSections.imagingCentralReading.data.response_criteria";

  if (!criteria) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Target className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No response criteria defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Primary Criteria */}
      <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-2xl p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center shadow-md">
              <Target className="w-6 h-6 text-white" />
            </div>
            <div>
              <h4 className="font-bold text-blue-900 text-lg">Primary Criteria</h4>
              <EditableText
                value={criteria.primary_criteria}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.primary_criteria`, v) : undefined}
                className="text-sm text-blue-700"
              />
            </div>
          </div>
          <ProvenanceChip provenance={criteria.provenance} onViewSource={onViewSource} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {criteria.criteria_version && (
            <div className="p-3 bg-white rounded-lg border border-blue-200">
              <span className="text-xs font-medium text-blue-700 uppercase block mb-1">Version</span>
              <EditableText
                value={criteria.criteria_version}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.criteria_version`, v) : undefined}
                className="font-medium text-blue-900"
              />
            </div>
          )}
        </div>
      </div>

      {/* Secondary Criteria */}
      {criteria.secondary_criteria?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Target className="w-5 h-5 text-gray-600" />
              Secondary Criteria ({criteria.secondary_criteria.length})
            </h5>
          </div>
          <div className="divide-y divide-gray-100">
            {criteria.secondary_criteria.map((sec: any, idx: number) => (
              <div key={idx} className="p-4">
                <EditableText
                  value={typeof sec === 'string' ? sec : sec.criteria_name || sec.name}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.secondary_criteria.${idx}${typeof sec === 'string' ? '' : '.criteria_name'}`, v) : undefined}
                  className="text-sm text-gray-700"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modifications */}
      {criteria.modifications && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
          <h5 className="font-semibold text-amber-900 mb-2 flex items-center gap-2">
            <Settings className="w-5 h-5 text-amber-600" />
            Modifications
          </h5>
          <EditableText
            value={criteria.modifications}
            multiline
            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.modifications`, v) : undefined}
            className="text-sm text-amber-800"
          />
        </div>
      )}
    </div>
  );
}

// NEW TAB: BICR (Blinded Independent Central Review)
function BICRTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const bicr = data?.bicr || data?.central_reading;
  const basePath = data?.bicr ? "domainSections.imagingCentralReading.data.bicr" : "domainSections.imagingCentralReading.data.central_reading";

  if (!bicr) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No BICR requirements defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* BICR Overview */}
      <div className="bg-gradient-to-br from-purple-50 to-indigo-50 border border-purple-200 rounded-2xl p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-purple-600 flex items-center justify-center shadow-md">
              <Users className="w-6 h-6 text-white" />
            </div>
            <div>
              <h4 className="font-bold text-purple-900 text-lg">Blinded Independent Central Review</h4>
              {bicr.bicr_required !== undefined && (
                <span className={cn("text-sm px-2 py-0.5 rounded mt-1 inline-block",
                  bicr.bicr_required ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-700"
                )}>
                  {bicr.bicr_required ? "Required" : "Not Required"}
                </span>
              )}
            </div>
          </div>
          <ProvenanceChip provenance={bicr.provenance} onViewSource={onViewSource} />
        </div>
      </div>

      {/* Reader Qualifications */}
      {bicr.reader_qualifications && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <GraduationCap className="w-5 h-5 text-gray-600" />
            Reader Qualifications
          </h5>
          <SmartDataRender data={bicr.reader_qualifications} onViewSource={onViewSource} excludeFields={["provenance"]} />
        </div>
      )}

      {/* Reader Training */}
      {bicr.reader_training && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <GraduationCap className="w-5 h-5 text-gray-600" />
            Reader Training
          </h5>
          <SmartDataRender data={bicr.reader_training} onViewSource={onViewSource} excludeFields={["provenance"]} />
        </div>
      )}

      {/* Image Quality Requirements */}
      {bicr.image_quality_requirements && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <Image className="w-5 h-5 text-gray-600" />
            Image Quality Requirements
          </h5>
          <SmartDataRender data={bicr.image_quality_requirements} onViewSource={onViewSource} excludeFields={["provenance"]} />
        </div>
      )}

      {/* Adjudication Procedures */}
      {bicr.adjudication_procedures && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-gray-600" />
            Adjudication Procedures
          </h5>
          <SmartDataRender data={bicr.adjudication_procedures} onViewSource={onViewSource} excludeFields={["provenance"]} />
        </div>
      )}

      {/* Fallback for all other BICR data */}
      {Object.keys(bicr).filter(k => !['provenance', 'bicr_required', 'reader_qualifications', 'reader_training', 'image_quality_requirements', 'adjudication_procedures'].includes(k)).length > 0 && (
        <AccordionSection title="Additional BICR Details" icon={Eye}>
          <SmartDataRender
            data={bicr}
            onViewSource={onViewSource}
            excludeFields={["provenance", "bicr_required", "reader_qualifications", "reader_training", "image_quality_requirements", "adjudication_procedures"]}
          />
        </AccordionSection>
      )}
    </div>
  );
}

function ReadingTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  if (!data.central_reading) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Eye className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No central reading information available</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Eye className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-3">Central Reading</h4>
            <SmartDataRender data={data.central_reading} onViewSource={onViewSource} />
          </div>
        </div>
      </div>
    </div>
  );
}

function ImagingViewContent({ data, onViewSource, onFieldUpdate }: ImagingViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  
  
  const modalities = data.imaging_modalities || [];
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "modalities", label: "Modalities", icon: Scan, count: modalities.length },
    { id: "criteria", label: "Criteria", icon: Target },
    { id: "reading", label: "Reading", icon: Eye },
    { id: "bicr", label: "BICR", icon: Users },
  ];
  
  return (
    <div className="space-y-6" data-testid="imaging-view">
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
          {activeTab === "modalities" && <ModalitiesTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "criteria" && <CriteriaTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "reading" && <ReadingTab data={data} onViewSource={onViewSource} />}
          {activeTab === "bicr" && <BICRTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function ImagingView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: ImagingViewProps) {
  if (!data) {
    return (<div className="text-center py-12 text-muted-foreground"><Scan className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No imaging data available</p></div>);
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <ImagingViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
