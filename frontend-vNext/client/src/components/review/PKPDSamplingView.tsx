import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, ChevronDown, Droplets, Activity, Shield, TrendingUp, Layers, TestTube, Dna, Settings, Clock, BarChart3 } from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { EditableText } from "./EditableValue";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";

interface PKPDSamplingViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "pk_sampling" | "analytes" | "pd_biomarkers" | "parameters";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function AccordionSection({ title, icon: Icon, children, defaultOpen = false }: { title: string; icon: React.ElementType; children: React.ReactNode; defaultOpen?: boolean; }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white">
      <button type="button" onClick={() => setIsOpen(!isOpen)} className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors text-left">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center"><Icon className="w-4 h-4 text-gray-900" /></div>
          <span className="font-semibold text-foreground">{title}</span>
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
  const hasPKSampling = !!data?.pk_sampling;
  const hasPKParams = !!data?.pk_parameters;
  const hasImmunogenicity = !!data?.immunogenicity;
  return (
    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="pkpd-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <Droplets className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">PK/PD Sampling</h3>
          <p className="text-sm text-muted-foreground">Pharmacokinetic and pharmacodynamic assessments</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Droplets className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">PK Sampling</span></div>
          <p className="text-lg font-bold text-gray-900">{hasPKSampling ? "Defined" : "N/A"}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><TrendingUp className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">PK Parameters</span></div>
          <p className="text-lg font-bold text-gray-900">{hasPKParams ? "Specified" : "N/A"}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Shield className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Immunogenicity</span></div>
          <p className="text-lg font-bold text-gray-900">{hasImmunogenicity ? "Assessed" : "N/A"}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const hasPKSampling = !!data?.pk_sampling;
  const hasPKParams = !!data?.pk_parameters;
  const hasImmunogenicity = !!data?.immunogenicity;
  
  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Layers className="w-5 h-5 text-gray-600" />
            PK/PD Overview
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Droplets className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasPKSampling ? "Defined" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">PK Sampling</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <TrendingUp className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasPKParams ? "Specified" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">PK Parameters</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Shield className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasImmunogenicity ? "Assessed" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Immunogenicity</p>
            </div>
          </div>
        </div>
      </div>
      
      {data.immunogenicity && (
        <AccordionSection title="Immunogenicity" icon={Shield}>
          <SmartDataRender data={data.immunogenicity} onViewSource={onViewSource} />
        </AccordionSection>
      )}
    </div>
  );
}

function PKSamplingTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  if (!data.pk_sampling) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Droplets className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No PK sampling schedule defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Droplets className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">PK Sampling Schedule</h4>
              <ProvenanceChip provenance={data.pk_sampling.provenance} onViewSource={onViewSource} />
            </div>
            <SmartDataRender data={data.pk_sampling} onViewSource={onViewSource} />
          </div>
        </div>
      </div>
    </div>
  );
}

// NEW TAB: PK Analytes
function AnalytesTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const analytes = data?.pk_analytes || data?.pk_sampling?.analytes;
  const basePath = data?.pk_analytes ? "domainSections.pkpdSampling.data.pk_analytes" : "domainSections.pkpdSampling.data.pk_sampling.analytes";

  if (!analytes || analytes.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <TestTube className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No PK analytes defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {analytes.map((analyte: any, idx: number) => (
        <div key={analyte.analyte_id || analyte.name || idx} className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center">
                <TestTube className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <EditableText
                  value={analyte.analyte_name || analyte.name}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.analyte_name`, v) : undefined}
                  className="font-semibold text-foreground"
                />
                {analyte.analyte_type && (
                  <EditableText
                    value={analyte.analyte_type}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.analyte_type`, v) : undefined}
                    className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded"
                  />
                )}
              </div>
            </div>
            <ProvenanceChip provenance={analyte.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {analyte.matrix && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Matrix</span>
                <EditableText
                  value={analyte.matrix}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.matrix`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
            {analyte.assay_method && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Assay Method</span>
                <EditableText
                  value={analyte.assay_method}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.assay_method`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
            {analyte.lloq && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">LLOQ</span>
                <EditableText
                  value={`${analyte.lloq} ${analyte.lloq_unit || ''}`}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.lloq`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
            {analyte.validation_status && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Validation</span>
                <EditableText
                  value={analyte.validation_status}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.validation_status`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
          </div>

          {/* Bioanalytical specs */}
          {analyte.bioanalytical_specs && (
            <AccordionSection title="Bioanalytical Specifications" icon={Settings} defaultOpen={false}>
              <SmartDataRender data={analyte.bioanalytical_specs} onViewSource={onViewSource} excludeFields={["provenance"]} />
            </AccordionSection>
          )}
        </div>
      ))}
    </div>
  );
}

// NEW TAB: PD Biomarkers
function PDBiomarkersTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const biomarkers = data?.pd_biomarkers || data?.biomarkers;
  const basePath = data?.pd_biomarkers ? "domainSections.pkpdSampling.data.pd_biomarkers" : "domainSections.pkpdSampling.data.biomarkers";

  if (!biomarkers || biomarkers.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Dna className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No PD biomarkers defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {biomarkers.map((biomarker: any, idx: number) => (
        <div key={biomarker.biomarker_id || biomarker.name || idx} className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-green-100 rounded-xl flex items-center justify-center">
                <Dna className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <EditableText
                  value={biomarker.biomarker_name || biomarker.name}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.biomarker_name`, v) : undefined}
                  className="font-semibold text-foreground"
                />
                {biomarker.biomarker_type && (
                  <EditableText
                    value={biomarker.biomarker_type?.decode || biomarker.biomarker_type}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.biomarker_type`, v) : undefined}
                    className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded"
                  />
                )}
              </div>
            </div>
            <ProvenanceChip provenance={biomarker.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {biomarker.purpose && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Purpose</span>
                <EditableText
                  value={biomarker.purpose}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.purpose`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
            {biomarker.sample_type && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Sample Type</span>
                <EditableText
                  value={biomarker.sample_type}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.sample_type`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
            {biomarker.assay_method && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Assay Method</span>
                <EditableText
                  value={biomarker.assay_method}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.assay_method`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
            {biomarker.cutoff_value && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Cut-off Value</span>
                <EditableText
                  value={biomarker.cutoff_value}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.cutoff_value`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
            {biomarker.validation_status && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Validation</span>
                <EditableText
                  value={biomarker.validation_status}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.validation_status`, v) : undefined}
                  className="text-sm font-medium text-gray-900"
                />
              </div>
            )}
          </div>

          {/* Sampling Schedule */}
          {biomarker.sampling_schedule && (
            <div className="mt-3 pt-3 border-t border-gray-200">
              <div className="flex items-center gap-2 mb-2">
                <Clock className="w-4 h-4 text-gray-600" />
                <span className="text-sm font-medium text-gray-700">Sampling Schedule</span>
              </div>
              <SmartDataRender data={biomarker.sampling_schedule} onViewSource={onViewSource} excludeFields={["provenance"]} />
            </div>
          )}
        </div>
      ))}

      {/* Population PK/PD Analysis */}
      {data.population_pk_pd && (
        <AccordionSection title="Population PK/PD Analysis" icon={BarChart3} defaultOpen={false}>
          <SmartDataRender data={data.population_pk_pd} onViewSource={onViewSource} excludeFields={["provenance"]} />
        </AccordionSection>
      )}

      {/* Exposure-Response Analysis */}
      {data.exposure_response && (
        <AccordionSection title="Exposure-Response Analysis" icon={TrendingUp} defaultOpen={false}>
          <SmartDataRender data={data.exposure_response} onViewSource={onViewSource} excludeFields={["provenance"]} />
        </AccordionSection>
      )}
    </div>
  );
}

function ParametersTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  if (!data.pk_parameters) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <TrendingUp className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No PK parameters defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <TrendingUp className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-3">PK Parameters</h4>
            <SmartDataRender data={data.pk_parameters} onViewSource={onViewSource} />
          </div>
        </div>
      </div>
    </div>
  );
}

function PKPDSamplingViewContent({ data, onViewSource, onFieldUpdate }: PKPDSamplingViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "pk_sampling", label: "PK Sampling", icon: Droplets },
    { id: "analytes", label: "Analytes", icon: TestTube },
    { id: "pd_biomarkers", label: "PD Biomarkers", icon: Dna },
    { id: "parameters", label: "Parameters", icon: TrendingUp },
  ];
  
  return (
    <div className="space-y-6" data-testid="pkpd-view">
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
          {activeTab === "pk_sampling" && <PKSamplingTab data={data} onViewSource={onViewSource} />}
          {activeTab === "analytes" && <AnalytesTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "pd_biomarkers" && <PDBiomarkersTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "parameters" && <ParametersTab data={data} onViewSource={onViewSource} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function PKPDSamplingView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: PKPDSamplingViewProps) {
  if (!data) {
    return (<div className="text-center py-12 text-muted-foreground"><Droplets className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No PK/PD data available</p></div>);
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <PKPDSamplingViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
