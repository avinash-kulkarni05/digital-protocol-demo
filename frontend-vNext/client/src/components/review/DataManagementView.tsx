import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, Database, Server, Shield, CheckSquare, LayoutGrid, Settings,
  Send, Archive, Lock, ChevronDown, Globe, RefreshCw, Clock, FileCheck,
  AlertTriangle, Users, BarChart3, Calendar, Hash, Layers, Building2, Truck
} from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { EditableText } from "./EditableValue";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";

interface DataManagementViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "edc" | "standards" | "quality" | "database" | "transfers" | "archival";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function SummaryHeader({ data }: { data: any }) {
  const vendorName = data?.edc_specifications?.vendor_name || "Not specified";
  const capCount = data?.edc_specifications?.system_capabilities?.length || 0;
  const integrationCount = data?.edc_specifications?.integration_systems?.length || 0;
  const crfModuleCount = data?.edc_specifications?.crf_modules?.length || 0;
  const hasDbLock = !!data?.database_management?.final_database_lock;
  const transferCount =
    (data?.data_transfers?.central_lab ? 1 : 0) +
    (data?.data_transfers?.imaging ? 1 : 0) +
    (data?.data_transfers?.epro ? 1 : 0) +
    (data?.data_transfers?.external_adjudication ? 1 : 0) +
    (data?.data_transfers?.dsmb_exports ? 1 : 0);

  return (
    <div className="bg-gradient-to-br from-slate-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="data-mgmt-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <Database className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Data Management</h3>
          <p className="text-sm text-muted-foreground">EDC, data standards, and quality controls</p>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <Server className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">EDC Vendor</span>
          </div>
          <p className="text-sm font-bold text-gray-900 truncate">{vendorName}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <CheckSquare className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Capabilities</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{capCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <RefreshCw className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Integrations</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{integrationCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <Layers className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">CRF Modules</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{crfModuleCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <Send className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Data Transfers</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{transferCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <Lock className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">DB Lock Plan</span>
          </div>
          <p className="text-sm font-bold text-gray-900">{hasDbLock ? "Defined" : "N/A"}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const vendorName = data?.edc_specifications?.vendor_name;
  const capabilities = data?.edc_specifications?.system_capabilities || [];
  const hasStandards = !!data?.data_standards;
  const hasQuality = !!data?.data_quality;
  
  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Database className="w-5 h-5 text-gray-600" />
            Data Management Overview
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Server className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{vendorName || "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">EDC Vendor</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Shield className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasStandards ? "Defined" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Data Standards</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <CheckSquare className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasQuality ? "Defined" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Quality Controls</p>
            </div>
          </div>
        </div>
      </div>
      
      {capabilities.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h4 className="font-semibold text-foreground mb-3">System Capabilities</h4>
          <div className="flex flex-wrap gap-2">
            {capabilities.map((cap: string, idx: number) => (
              <span key={idx} className="text-xs bg-gray-50 text-gray-700 px-3 py-1.5 rounded-full border border-gray-200 font-medium">{cap}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function EDCTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const edc = data?.edc_specifications;
  const [expandedModule, setExpandedModule] = useState<string | null>(null);
  const basePath = "domainSections.dataManagement.data.edc_specifications";

  if (!edc) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Server className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No EDC specifications available</p>
      </div>
    );
  }

  const integrations = edc.integration_systems || [];
  const crfModules = edc.crf_modules || [];
  const languages = edc.language_requirements || [];

  return (
    <div className="space-y-6">
      {/* EDC Overview */}
      <div className="bg-gradient-to-br from-gray-50 to-gray-50 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Database className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">EDC Specifications</h4>
              <ProvenanceChip provenance={edc.provenance} onViewSource={onViewSource} />
            </div>
            {edc.vendor_name && (
              <div className="bg-white/70 rounded-lg p-3 border border-gray-200 mb-3">
                <span className="text-xs font-medium text-gray-800 uppercase tracking-wider block mb-1">Vendor</span>
                <EditableText
                  value={edc.vendor_name}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.vendor_name`, v) : undefined}
                  className="font-semibold text-gray-900"
                />
              </div>
            )}

            {/* System Capabilities */}
            {edc.system_capabilities?.length > 0 && (
              <div className="mb-3">
                <span className="text-xs font-medium text-gray-800 uppercase tracking-wider block mb-2">System Capabilities</span>
                <div className="flex flex-wrap gap-2">
                  {edc.system_capabilities.map((cap: string, idx: number) => (
                    <span key={idx} className="text-xs bg-white/70 text-gray-700 px-3 py-1.5 rounded-full border border-gray-200 font-medium">
                      {cap.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Language Requirements */}
            {languages.length > 0 && (
              <div>
                <span className="text-xs font-medium text-gray-800 uppercase tracking-wider block mb-2">Language Requirements</span>
                <div className="flex flex-wrap gap-2">
                  {languages.map((lang: string, idx: number) => (
                    <span key={idx} className="inline-flex items-center gap-1 text-xs bg-gray-100 text-gray-800 px-3 py-1.5 rounded-full font-medium">
                      <Globe className="w-3 h-3" />
                      {lang}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Integration Systems */}
      {integrations.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <RefreshCw className="w-5 h-5 text-gray-600" />
              Integration Systems ({integrations.length})
            </h5>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">System Type</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Vendor</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Transfer Frequency</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Transfer Method</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {integrations.map((integration: any, idx: number) => (
                  <tr key={integration.id || idx} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <EditableText
                        value={integration.system_type?.replace(/_/g, " ") || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.integration_systems.${idx}.system_type`, v) : undefined}
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded"
                      />
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      <EditableText
                        value={integration.vendor_name || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.integration_systems.${idx}.vendor_name`, v) : undefined}
                      />
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      <EditableText
                        value={integration.transfer_frequency?.replace(/_/g, " ") || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.integration_systems.${idx}.transfer_frequency`, v) : undefined}
                      />
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      <EditableText
                        value={integration.transfer_method?.replace(/_/g, " ") || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.integration_systems.${idx}.transfer_method`, v) : undefined}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <ProvenanceChip provenance={integration.provenance} onViewSource={onViewSource} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* CRF Modules */}
      {crfModules.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Layers className="w-5 h-5 text-gray-600" />
              CRF Modules ({crfModules.length})
            </h5>
          </div>
          <div className="divide-y divide-gray-100">
            {crfModules.map((module: any, idx: number) => (
              <div key={module.id || idx} className="p-4">
                <button
                  type="button"
                  onClick={() => setExpandedModule(expandedModule === module.id ? null : module.id)}
                  className="w-full flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
                      <Layers className="w-4 h-4 text-gray-600" />
                    </div>
                    <div className="text-left">
                      <EditableText
                        value={module.module_name}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.crf_modules.${idx}.module_name`, v) : undefined}
                        className="font-medium text-gray-900"
                      />
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        {module.id && <span>{module.id}</span>}
                        {module.is_repeating && (
                          <span className="px-1.5 py-0.5 bg-gray-100 text-gray-700 rounded">Repeating</span>
                        )}
                        {module.forms?.length > 0 && <span>{module.forms.length} forms</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <ProvenanceChip provenance={module.provenance} onViewSource={onViewSource} />
                    <ChevronDown className={cn("w-4 h-4 text-gray-400 transition-transform", expandedModule === module.id && "rotate-180")} />
                  </div>
                </button>

                <AnimatePresence>
                  {expandedModule === module.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="mt-3 pl-11 space-y-3">
                        {module.forms?.length > 0 && (
                          <div>
                            <span className="text-xs font-medium text-gray-600 uppercase">Forms</span>
                            <div className="flex flex-wrap gap-1.5 mt-1">
                              {module.forms.map((form: string, fIdx: number) => (
                                <span key={fIdx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">
                                  {form}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        {module.visit_schedule?.length > 0 && (
                          <div>
                            <span className="text-xs font-medium text-gray-600 uppercase">Visit Schedule</span>
                            <div className="flex flex-wrap gap-1.5 mt-1">
                              {module.visit_schedule.map((visit: string, vIdx: number) => (
                                <span key={vIdx} className="text-xs bg-gray-50 text-gray-700 px-2 py-1 rounded">
                                  {visit}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StandardsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const standards = data?.data_standards;
  const basePath = "domainSections.dataManagement.data.data_standards";

  if (!standards) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No data standards defined</p>
      </div>
    );
  }

  const ct = standards.controlled_terminology || {};

  return (
    <div className="space-y-6">
      {/* CDISC Standards Overview */}
      <div className="bg-gradient-to-br from-green-50 to-gray-50 border border-green-200 rounded-2xl p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-green-600 flex items-center justify-center shadow-md">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <div>
              <h4 className="font-bold text-green-900 text-lg">CDISC Data Standards</h4>
              <p className="text-sm text-green-700">Regulatory submission requirements</p>
            </div>
          </div>
          <ProvenanceChip provenance={standards.provenance} onViewSource={onViewSource} />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {standards.sdtm_version && (
            <div className="bg-white rounded-lg p-3 border border-green-200">
              <span className="text-xs font-medium text-green-700 uppercase block mb-1">SDTM Version</span>
              <EditableText
                value={standards.sdtm_version}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdtm_version`, v) : undefined}
                className="font-semibold text-green-900"
              />
            </div>
          )}
          {standards.sdtm_ig_version && (
            <div className="bg-white rounded-lg p-3 border border-green-200">
              <span className="text-xs font-medium text-green-700 uppercase block mb-1">SDTM-IG</span>
              <EditableText
                value={standards.sdtm_ig_version}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdtm_ig_version`, v) : undefined}
                className="font-semibold text-green-900"
              />
            </div>
          )}
          {standards.adam_version && (
            <div className="bg-white rounded-lg p-3 border border-green-200">
              <span className="text-xs font-medium text-green-700 uppercase block mb-1">ADaM Version</span>
              <EditableText
                value={standards.adam_version}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.adam_version`, v) : undefined}
                className="font-semibold text-green-900"
              />
            </div>
          )}
          {standards.define_xml_version && (
            <div className="bg-white rounded-lg p-3 border border-green-200">
              <span className="text-xs font-medium text-green-700 uppercase block mb-1">Define-XML</span>
              <EditableText
                value={standards.define_xml_version}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.define_xml_version`, v) : undefined}
                className="font-semibold text-green-900"
              />
            </div>
          )}
        </div>
      </div>

      {/* Requirements Badges */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
        <h5 className="font-semibold text-foreground mb-3 flex items-center gap-2">
          <FileCheck className="w-5 h-5 text-gray-600" />
          Documentation Requirements
        </h5>
        <div className="flex flex-wrap gap-3">
          {standards.define_xml_required !== undefined && (
            <span className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-full",
              standards.define_xml_required ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
            )}>
              {standards.define_xml_required ? <CheckSquare className="w-4 h-4" /> : <LayoutGrid className="w-4 h-4" />}
              Define-XML {standards.define_xml_required ? "Required" : "Not Required"}
            </span>
          )}
          {standards.adrg_required !== undefined && (
            <span className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-full",
              standards.adrg_required ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
            )}>
              {standards.adrg_required ? <CheckSquare className="w-4 h-4" /> : <LayoutGrid className="w-4 h-4" />}
              ADRG {standards.adrg_required ? "Required" : "Not Required"}
            </span>
          )}
          {standards.sdrg_required !== undefined && (
            <span className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-full",
              standards.sdrg_required ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
            )}>
              {standards.sdrg_required ? <CheckSquare className="w-4 h-4" /> : <LayoutGrid className="w-4 h-4" />}
              SDRG {standards.sdrg_required ? "Required" : "Not Required"}
            </span>
          )}
        </div>
      </div>

      {/* Controlled Terminology */}
      {(ct.cdisc_ct_version || ct.meddra_version || ct.whodrug_version || ct.snomed_version) && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-gray-600" />
            Controlled Terminology Versions
          </h5>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {ct.cdisc_ct_version && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">CDISC CT</span>
                <EditableText
                  value={ct.cdisc_ct_version}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.controlled_terminology.cdisc_ct_version`, v) : undefined}
                  className="font-medium text-gray-900"
                />
              </div>
            )}
            {ct.meddra_version && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">MedDRA</span>
                <EditableText
                  value={ct.meddra_version}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.controlled_terminology.meddra_version`, v) : undefined}
                  className="font-medium text-gray-900"
                />
              </div>
            )}
            {ct.whodrug_version && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">WHODrug</span>
                <EditableText
                  value={ct.whodrug_version}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.controlled_terminology.whodrug_version`, v) : undefined}
                  className="font-medium text-gray-900"
                />
              </div>
            )}
            {ct.snomed_version && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">SNOMED</span>
                <EditableText
                  value={ct.snomed_version}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.controlled_terminology.snomed_version`, v) : undefined}
                  className="font-medium text-gray-900"
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Fallback for additional fields */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
        <h5 className="font-semibold text-foreground mb-3">Additional Details</h5>
        <SmartDataRender
          data={standards}
          excludeFields={["provenance", "instanceType", "sdtm_version", "sdtm_ig_version", "adam_version", "define_xml_version", "define_xml_required", "adrg_required", "sdrg_required", "controlled_terminology"]}
          onViewSource={onViewSource}
        />
      </div>
    </div>
  );
}

function QualityTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const quality = data?.data_quality;
  const basePath = "domainSections.dataManagement.data.data_quality";

  if (!quality) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <CheckSquare className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No data quality controls defined</p>
      </div>
    );
  }

  const editChecks = quality.edit_checks || {};
  const sdvStrategy = quality.sdv_strategy || {};
  const queryMgmt = quality.query_management || {};
  const dataReview = quality.data_review || {};

  return (
    <div className="space-y-6">
      {/* SDV Strategy */}
      {Object.keys(sdvStrategy).length > 0 && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-50 border border-gray-200 rounded-2xl p-5">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-gray-600 flex items-center justify-center shadow-md">
                <CheckSquare className="w-6 h-6 text-white" />
              </div>
              <div>
                <h4 className="font-bold text-gray-900 text-lg">SDV Strategy</h4>
                <p className="text-sm text-gray-700">Source Data Verification approach</p>
              </div>
            </div>
            <ProvenanceChip provenance={quality.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {sdvStrategy.approach && (
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Approach</span>
                <EditableText
                  value={sdvStrategy.approach.replace(/_/g, " ")}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_strategy.approach`, v) : undefined}
                  className="font-semibold text-gray-900"
                />
              </div>
            )}
            {sdvStrategy.sdv_percentage !== undefined && (
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">SDV Percentage</span>
                <EditableText
                  value={`${sdvStrategy.sdv_percentage}%`}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_strategy.sdv_percentage`, v) : undefined}
                  className="font-semibold text-gray-900"
                />
              </div>
            )}
            {sdvStrategy.sdv_timing && (
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">SDV Timing</span>
                <EditableText
                  value={sdvStrategy.sdv_timing.replace(/_/g, " ")}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sdv_strategy.sdv_timing`, v) : undefined}
                  className="font-semibold text-gray-900"
                />
              </div>
            )}
          </div>

          {sdvStrategy.critical_data_points?.length > 0 && (
            <div className="mt-4">
              <span className="text-xs font-medium text-gray-700 uppercase block mb-2">Critical Data Points (100% SDV)</span>
              <div className="flex flex-wrap gap-2">
                {sdvStrategy.critical_data_points.map((point: string, idx: number) => (
                  <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-3 py-1.5 rounded-full font-medium">
                    {point}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Edit Checks */}
      {(editChecks.standard_checks?.length > 0 || editChecks.protocol_specific_checks?.length > 0) && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-gray-600" />
              Edit Checks
            </h5>
            {editChecks.auto_query_enabled !== undefined && (
              <span className={cn(
                "inline-flex items-center gap-1.5 px-2 py-1 text-xs font-medium rounded",
                editChecks.auto_query_enabled ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
              )}>
                Auto-Query {editChecks.auto_query_enabled ? "Enabled" : "Disabled"}
              </span>
            )}
          </div>

          {editChecks.standard_checks?.length > 0 && (
            <div className="mb-4">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Standard Checks</span>
              <div className="flex flex-wrap gap-2">
                {editChecks.standard_checks.map((check: string, idx: number) => (
                  <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-3 py-1.5 rounded-full">
                    {check.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}

          {editChecks.protocol_specific_checks?.length > 0 && (
            <div>
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Protocol-Specific Checks</span>
              <ul className="space-y-1">
                {editChecks.protocol_specific_checks.map((check: string, idx: number) => (
                  <li key={idx} className="text-sm text-gray-700 flex items-start gap-2 break-words">
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 mt-2 flex-shrink-0" />
                    <span className="break-words">{check}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Query Management */}
      {(queryMgmt.resolution_target_days || queryMgmt.escalation_threshold_days || queryMgmt.auto_query_triggers?.length > 0) && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Clock className="w-5 h-5 text-gray-600" />
            Query Management
          </h5>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {queryMgmt.resolution_target_days && (
              <div className="p-3 bg-gray-50 border border-gray-200 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Resolution Target</span>
                <span className="font-semibold text-gray-900">{queryMgmt.resolution_target_days} days</span>
              </div>
            )}
            {queryMgmt.escalation_threshold_days && (
              <div className="p-3 bg-gray-50 border border-gray-200 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Escalation Threshold</span>
                <span className="font-semibold text-gray-900">{queryMgmt.escalation_threshold_days} days</span>
              </div>
            )}
          </div>

          {queryMgmt.auto_query_triggers?.length > 0 && (
            <div>
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Auto-Query Triggers</span>
              <div className="flex flex-wrap gap-2">
                {queryMgmt.auto_query_triggers.map((trigger: string, idx: number) => (
                  <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-3 py-1.5 rounded-full">
                    {trigger}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Data Review */}
      {(dataReview.medical_review_frequency || dataReview.statistical_review_frequency || dataReview.data_review_committee !== undefined) && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Users className="w-5 h-5 text-gray-600" />
            Data Review
          </h5>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {dataReview.medical_review_frequency && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Medical Review</span>
                <span className="font-medium text-gray-900">{dataReview.medical_review_frequency.replace(/_/g, " ")}</span>
              </div>
            )}
            {dataReview.statistical_review_frequency && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Statistical Review</span>
                <span className="font-medium text-gray-900">{dataReview.statistical_review_frequency.replace(/_/g, " ")}</span>
              </div>
            )}
            {dataReview.data_review_committee !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Review Committee</span>
                <span className="font-medium text-gray-900">{dataReview.data_review_committee ? "Yes" : "No"}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// NEW TAB: Database Management Tab
function DatabaseTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const dbMgmt = data?.database_management;
  const basePath = "domainSections.dataManagement.data.database_management";

  if (!dbMgmt) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Lock className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No database management specifications</p>
      </div>
    );
  }

  const design = dbMgmt.database_design || {};
  const interimLocks = dbMgmt.interim_locks || [];
  const finalLock = dbMgmt.final_database_lock || {};

  return (
    <div className="space-y-6">
      {/* Database Design */}
      {(design.external_data_sources?.length > 0 || design.calculated_fields?.length > 0 || design.derived_variables?.length > 0) && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-start justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Database className="w-5 h-5 text-gray-600" />
              Database Design
            </h5>
            <ProvenanceChip provenance={dbMgmt.provenance} onViewSource={onViewSource} />
          </div>

          {design.external_data_sources?.length > 0 && (
            <div className="mb-4">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">External Data Sources</span>
              <div className="flex flex-wrap gap-2">
                {design.external_data_sources.map((source: string, idx: number) => (
                  <span key={idx} className="inline-flex items-center gap-1 text-xs bg-gray-50 text-gray-700 px-3 py-1.5 rounded-full font-medium">
                    <Building2 className="w-3 h-3" />
                    {source.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {design.calculated_fields?.length > 0 && (
              <div>
                <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Calculated Fields</span>
                <div className="flex flex-wrap gap-1.5">
                  {design.calculated_fields.map((field: string, idx: number) => (
                    <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">{field}</span>
                  ))}
                </div>
              </div>
            )}
            {design.derived_variables?.length > 0 && (
              <div>
                <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Derived Variables</span>
                <div className="flex flex-wrap gap-1.5">
                  {design.derived_variables.map((variable: string, idx: number) => (
                    <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">{variable}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Interim Locks */}
      {interimLocks.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Lock className="w-5 h-5 text-gray-600" />
              Interim Database Locks ({interimLocks.length})
            </h5>
          </div>
          <div className="divide-y divide-gray-100">
            {interimLocks.map((lock: any, idx: number) => (
              <div key={lock.id || idx} className="p-4">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center text-sm font-bold text-gray-700">
                      {idx + 1}
                    </div>
                    <div>
                      <EditableText
                        value={lock.lock_name}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.interim_locks.${idx}.lock_name`, v) : undefined}
                        className="font-medium text-gray-900"
                      />
                      {lock.scope && (
                        <span className="text-xs text-muted-foreground">{lock.scope.replace(/_/g, " ")} scope</span>
                      )}
                    </div>
                  </div>
                  <ProvenanceChip provenance={lock.provenance} onViewSource={onViewSource} />
                </div>
                {lock.trigger && (
                  <EditableText
                    value={lock.trigger}
                    multiline
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.interim_locks.${idx}.trigger`, v) : undefined}
                    className="text-sm text-gray-700 ml-11 break-words"
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Final Database Lock */}
      {Object.keys(finalLock).length > 0 && (
        <div className="bg-gradient-to-br from-red-50 to-gray-50 border border-red-200 rounded-2xl p-5">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-red-600 flex items-center justify-center shadow-md">
                <Lock className="w-6 h-6 text-white" />
              </div>
              <div>
                <h4 className="font-bold text-red-900 text-lg">Final Database Lock</h4>
                {finalLock.timeline_days_from_lplv && (
                  <p className="text-sm text-red-700">{finalLock.timeline_days_from_lplv} days from LPLV</p>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={finalLock.provenance} onViewSource={onViewSource} />
          </div>

          {finalLock.trigger_event && (
            <div className="bg-white rounded-lg p-3 border border-red-200 mb-4">
              <span className="text-xs font-medium text-red-700 uppercase block mb-1">Trigger Event</span>
              <EditableText
                value={finalLock.trigger_event}
                multiline
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.final_database_lock.trigger_event`, v) : undefined}
                className="text-sm text-red-900 break-words"
              />
            </div>
          )}

          {finalLock.prerequisites?.length > 0 && (
            <div className="mb-4">
              <span className="text-xs font-medium text-red-700 uppercase block mb-2">Prerequisites</span>
              <ul className="space-y-1">
                {finalLock.prerequisites.map((prereq: string, idx: number) => (
                  <li key={idx} className="text-sm text-red-800 flex items-start gap-2">
                    <CheckSquare className="w-4 h-4 text-red-600 mt-0.5 flex-shrink-0" />
                    <span className="break-words">{prereq}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {finalLock.signoff_required?.length > 0 && (
            <div>
              <span className="text-xs font-medium text-red-700 uppercase block mb-2">Sign-off Required From</span>
              <div className="flex flex-wrap gap-2">
                {finalLock.signoff_required.map((dept: string, idx: number) => (
                  <span key={idx} className="text-xs bg-red-100 text-red-700 px-3 py-1.5 rounded-full font-medium">
                    {dept.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// NEW TAB: Data Transfers Tab
function TransfersTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const transfers = data?.data_transfers;
  const basePath = "domainSections.dataManagement.data.data_transfers";

  if (!transfers) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Send className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No data transfer specifications</p>
      </div>
    );
  }

  const sections = [
    { key: "central_lab", label: "Central Laboratory", icon: Building2, color: "blue" },
    { key: "imaging", label: "Imaging", icon: LayoutGrid, color: "purple" },
    { key: "epro", label: "ePRO", icon: Users, color: "green" },
    { key: "external_adjudication", label: "External Adjudication", icon: CheckSquare, color: "amber" },
    { key: "dsmb_exports", label: "DSMB Exports", icon: Shield, color: "red" },
  ];

  return (
    <div className="space-y-6">
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex items-start justify-between">
        <p className="text-sm text-gray-700">
          <strong>Data Transfer Specifications:</strong> Configuration for external data integrations and exports.
        </p>
        <ProvenanceChip provenance={transfers.provenance} onViewSource={onViewSource} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {sections.map(({ key, label, icon: Icon, color }) => {
          const section = transfers[key];
          if (!section || Object.keys(section).length === 0) return null;

          const colorClasses: Record<string, { bg: string; border: string; text: string; iconBg: string }> = {
            blue: { bg: "from-gray-50 to-gray-50", border: "border-gray-200", text: "text-gray-900", iconBg: "bg-gray-900" },
            purple: { bg: "from-gray-50 to-gray-50", border: "border-gray-200", text: "text-gray-900", iconBg: "bg-gray-600" },
            green: { bg: "from-green-50 to-gray-50", border: "border-green-200", text: "text-green-900", iconBg: "bg-green-600" },
            amber: { bg: "from-gray-50 to-gray-50", border: "border-gray-200", text: "text-gray-900", iconBg: "bg-gray-600" },
            red: { bg: "from-red-50 to-gray-50", border: "border-red-200", text: "text-red-900", iconBg: "bg-red-600" },
          };
          const colors = colorClasses[color];

          return (
            <div key={key} className={cn("bg-gradient-to-br rounded-xl p-5 border", colors.bg, colors.border)}>
              <div className="flex items-center justify-between gap-3 mb-4">
                <div className="flex items-center gap-3">
                  <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center shadow-sm", colors.iconBg)}>
                    <Icon className="w-5 h-5 text-white" />
                  </div>
                  <h5 className={cn("font-semibold", colors.text)}>{label}</h5>
                </div>
                <ProvenanceChip provenance={section.provenance} onViewSource={onViewSource} />
              </div>

              <div className="space-y-3">
                {section.vendor_name && (
                  <div className="bg-white/70 rounded-lg p-2 text-sm">
                    <span className="font-medium text-gray-600">Vendor:</span>{" "}
                    <EditableText
                      value={section.vendor_name}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${key}.vendor_name`, v) : undefined}
                      className="text-gray-900"
                    />
                  </div>
                )}
                {section.transfer_frequency && (
                  <div className="bg-white/70 rounded-lg p-2 text-sm">
                    <span className="font-medium text-gray-600">Frequency:</span>{" "}
                    <EditableText
                      value={section.transfer_frequency.replace(/_/g, " ")}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${key}.transfer_frequency`, v) : undefined}
                      className="text-gray-900"
                    />
                  </div>
                )}
                {section.transfer_method && (
                  <div className="bg-white/70 rounded-lg p-2 text-sm">
                    <span className="font-medium text-gray-600">Method:</span>{" "}
                    <EditableText
                      value={section.transfer_method.replace(/_/g, " ")}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${key}.transfer_method`, v) : undefined}
                      className="text-gray-900"
                    />
                  </div>
                )}
                {section.data_reconciliation !== undefined && (
                  <div className="bg-white/70 rounded-lg p-2 text-sm">
                    <span className="font-medium text-gray-600">Reconciliation:</span>{" "}
                    <span className="text-gray-900">{section.data_reconciliation ? "Yes" : "No"}</span>
                  </div>
                )}
                {section.blinding_maintained !== undefined && (
                  <div className="bg-white/70 rounded-lg p-2 text-sm">
                    <span className="font-medium text-gray-600">Blinding Maintained:</span>{" "}
                    <span className="text-gray-900">{section.blinding_maintained ? "Yes" : "No"}</span>
                  </div>
                )}
                {section.unblinded_access !== undefined && (
                  <div className="bg-white/70 rounded-lg p-2 text-sm">
                    <span className="font-medium text-gray-600">Unblinded Access:</span>{" "}
                    <span className="text-gray-900">{section.unblinded_access ? "Yes" : "No"}</span>
                  </div>
                )}
                {section.export_frequency && (
                  <div className="bg-white/70 rounded-lg p-2 text-sm">
                    <span className="font-medium text-gray-600">Export Frequency:</span>{" "}
                    <span className="text-gray-900">{section.export_frequency.replace(/_/g, " ")}</span>
                  </div>
                )}

                {/* Arrays */}
                {section.data_collected?.length > 0 && (
                  <div>
                    <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Data Collected</span>
                    <div className="flex flex-wrap gap-1">
                      {section.data_collected.map((item: string, idx: number) => (
                        <span key={idx} className="text-xs bg-white/70 text-gray-700 px-2 py-1 rounded">{item}</span>
                      ))}
                    </div>
                  </div>
                )}
                {section.instruments_collected?.length > 0 && (
                  <div>
                    <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Instruments</span>
                    <div className="flex flex-wrap gap-1">
                      {section.instruments_collected.map((item: string, idx: number) => (
                        <span key={idx} className="text-xs bg-white/70 text-gray-700 px-2 py-1 rounded">{item}</span>
                      ))}
                    </div>
                  </div>
                )}
                {section.adjudication_types?.length > 0 && (
                  <div>
                    <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Adjudication Types</span>
                    <div className="flex flex-wrap gap-1">
                      {section.adjudication_types.map((item: string, idx: number) => (
                        <span key={idx} className="text-xs bg-white/70 text-gray-700 px-2 py-1 rounded">{item}</span>
                      ))}
                    </div>
                  </div>
                )}
                {section.data_included?.length > 0 && (
                  <div>
                    <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Data Included</span>
                    <div className="flex flex-wrap gap-1">
                      {section.data_included.map((item: string, idx: number) => (
                        <span key={idx} className="text-xs bg-white/70 text-gray-700 px-2 py-1 rounded">{item}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// NEW TAB: Data Archival Tab
function ArchivalTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const archival = data?.data_archival;
  const basePath = "domainSections.dataManagement.data.data_archival";

  if (!archival) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Archive className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No data archival specifications</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Archival Overview */}
      <div className="bg-gradient-to-br from-slate-50 to-gray-100 border border-gray-200 rounded-2xl p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-gray-800 flex items-center justify-center shadow-md">
              <Archive className="w-6 h-6 text-white" />
            </div>
            <div>
              <h4 className="font-bold text-gray-900 text-lg">Data Archival Specifications</h4>
              <p className="text-sm text-gray-600">Retention and destruction policies</p>
            </div>
          </div>
          <ProvenanceChip provenance={archival.provenance} onViewSource={onViewSource} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {archival.retention_period_years && (
            <div className="bg-white rounded-lg p-4 border border-gray-200">
              <div className="flex items-center gap-2 mb-1">
                <Calendar className="w-4 h-4 text-gray-500" />
                <span className="text-xs font-medium text-gray-600 uppercase">Retention Period</span>
              </div>
              <p className="text-2xl font-bold text-gray-900">{archival.retention_period_years} years</p>
            </div>
          )}
          {archival.archival_location && (
            <div className="bg-white rounded-lg p-4 border border-gray-200">
              <div className="flex items-center gap-2 mb-1">
                <Building2 className="w-4 h-4 text-gray-500" />
                <span className="text-xs font-medium text-gray-600 uppercase">Location</span>
              </div>
              <p className="text-lg font-semibold text-gray-900">{archival.archival_location.replace(/_/g, " ")}</p>
            </div>
          )}
        </div>
      </div>

      {/* Archival Formats */}
      {archival.archival_format?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <FileText className="w-5 h-5 text-gray-600" />
            Archival Formats
          </h5>
          <div className="flex flex-wrap gap-2">
            {archival.archival_format.map((format: string, idx: number) => (
              <span key={idx} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-gray-100 text-gray-700 rounded-full">
                <FileText className="w-3.5 h-3.5" />
                {format.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Retention Basis */}
      {archival.retention_basis && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <Shield className="w-5 h-5 text-gray-600" />
            Retention Basis
          </h5>
          <EditableText
            value={archival.retention_basis}
            multiline
            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.retention_basis`, v) : undefined}
            className="text-sm text-gray-700 break-words"
          />
        </div>
      )}

      {/* Destruction Policy */}
      {archival.destruction_policy && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5">
          <h5 className="font-semibold text-red-900 mb-3 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-600" />
            Destruction Policy
          </h5>
          <EditableText
            value={archival.destruction_policy}
            multiline
            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.destruction_policy`, v) : undefined}
            className="text-sm text-red-800 break-words"
          />
        </div>
      )}
    </div>
  );
}

function DataManagementViewContent({ data, onViewSource, onFieldUpdate }: DataManagementViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: LayoutGrid },
    { id: "edc", label: "EDC", icon: Server },
    { id: "standards", label: "Standards", icon: Shield },
    { id: "quality", label: "Quality", icon: CheckSquare },
    { id: "database", label: "Database", icon: Lock },
    { id: "transfers", label: "Transfers", icon: Send },
    { id: "archival", label: "Archival", icon: Archive },
  ];
  
  return (
    <div className="space-y-6" data-testid="data-mgmt-view">
      <SummaryHeader data={data} />
      
      <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-xl overflow-x-auto" role="tablist">
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
          {activeTab === "edc" && <EDCTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "standards" && <StandardsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "quality" && <QualityTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "database" && <DatabaseTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "transfers" && <TransfersTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "archival" && <ArchivalTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function DataManagementView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: DataManagementViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Database className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No data management info available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <DataManagementViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
