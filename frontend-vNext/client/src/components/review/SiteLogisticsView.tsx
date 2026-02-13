import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, ChevronDown, Building2, Users, ClipboardCheck, GraduationCap, Layers,
  Shield, Calendar, Package, Monitor, Truck, Globe, Lock, AlertTriangle,
  CheckCircle, Clock, MapPin, User, UserCheck, Pill, Thermometer, Settings, Hash
} from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { EditableText } from "./EditableValue";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";

interface SiteLogisticsViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "site_selection" | "regulatory" | "personnel" | "training" | "monitoring" | "timeline" | "drug_supply" | "technology" | "vendors";

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
  const siteCount = data?.site_selection?.geographic_requirements?.site_count_target;
  const countryCount = data?.site_selection?.geographic_requirements?.countries?.length || 0;
  const vendorCount = data?.vendor_coordination?.length || 0;
  const hasRegulatory = !!data?.regulatory_ethics;
  const hasPersonnel = !!data?.site_personnel;
  const hasDrugSupply = !!data?.drug_supply_logistics;

  return (
    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="site-logistics-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <Building2 className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Site Operations & Logistics</h3>
          <p className="text-sm text-muted-foreground">Site selection, monitoring, training, and drug supply</p>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Building2 className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Target Sites</span></div>
          <p className="text-2xl font-bold text-gray-900">{siteCount || "N/A"}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Globe className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Countries</span></div>
          <p className="text-2xl font-bold text-gray-900">{countryCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Truck className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Vendors</span></div>
          <p className="text-2xl font-bold text-gray-900">{vendorCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Shield className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Regulatory</span></div>
          <p className="text-sm font-bold text-gray-900">{hasRegulatory ? "Defined" : "N/A"}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Users className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Personnel</span></div>
          <p className="text-sm font-bold text-gray-900">{hasPersonnel ? "Defined" : "N/A"}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Package className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Drug Supply</span></div>
          <p className="text-sm font-bold text-gray-900">{hasDrugSupply ? "Defined" : "N/A"}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const hasSiteSelection = !!data?.site_selection;
  const hasMonitoring = !!data?.monitoring_plan;
  const hasTraining = !!data?.training_requirements;
  
  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Layers className="w-5 h-5 text-gray-600" />
            Site Operations Overview
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Building2 className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasSiteSelection ? "Defined" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Site Selection</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <ClipboardCheck className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasMonitoring ? "Planned" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Monitoring</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <GraduationCap className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasTraining ? "Required" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Training</p>
            </div>
          </div>
        </div>
      </div>
      
      {data.training_requirements && (
        <AccordionSection title="Training Requirements" icon={GraduationCap}>
          <SmartDataRender data={data.training_requirements} onViewSource={onViewSource} />
        </AccordionSection>
      )}
    </div>
  );
}

function SiteSelectionTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  if (!data.site_selection) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Building2 className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No site selection criteria defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Building2 className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Site Selection Criteria</h4>
              <ProvenanceChip provenance={data.site_selection.provenance} onViewSource={onViewSource} />
            </div>
            <SmartDataRender data={data.site_selection} onViewSource={onViewSource} />
          </div>
        </div>
      </div>
    </div>
  );
}

function MonitoringTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const plan = data?.monitoring_plan;
  const basePath = "domainSections.siteOperationsLogistics.data.monitoring_plan";

  if (!plan) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <ClipboardCheck className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No monitoring plan defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Monitoring Approach */}
      <div className="bg-gradient-to-br from-gray-50 to-gray-50 border border-gray-200 rounded-2xl p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
              <ClipboardCheck className="w-6 h-6 text-white" />
            </div>
            <div>
              <h4 className="font-bold text-gray-900 text-lg">Monitoring Plan</h4>
              {plan.monitoring_approach && (
                <span className="inline-flex items-center px-2 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded mt-1">
                  <EditableText
                    value={plan.monitoring_approach.replace(/_/g, " ") || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.monitoring_approach`, v) : undefined}
                  /> approach
                </span>
              )}
            </div>
          </div>
          <ProvenanceChip provenance={plan.provenance} onViewSource={onViewSource} />
        </div>
      </div>

      {/* Site Initiation Visit */}
      {plan.site_initiation_visit && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-green-600" />
            Site Initiation Visit
          </h5>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {plan.site_initiation_visit.required !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Required</span>
                <span className="font-medium text-gray-900">{plan.site_initiation_visit.required ? "Yes" : "No"}</span>
              </div>
            )}
            {plan.site_initiation_visit.timing && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Timing</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={plan.site_initiation_visit.timing || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.site_initiation_visit.timing`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {plan.site_initiation_visit.format && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Format</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={plan.site_initiation_visit.format.replace(/_/g, " ") || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.site_initiation_visit.format`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>
          {plan.site_initiation_visit.activities?.length > 0 && (
            <div className="mt-4">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Activities</span>
              <div className="flex flex-wrap gap-2">
                {plan.site_initiation_visit.activities.map((a: string, i: number) => (
                  <span key={i} className="text-xs bg-green-50 text-green-700 px-2 py-1 rounded">
                    <EditableText
                      value={a || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.site_initiation_visit.activities.${i}`, v) : undefined}
                    />
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Routine Monitoring */}
      {plan.routine_monitoring && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Clock className="w-5 h-5 text-gray-900" />
              Routine Monitoring
            </h5>
            <ProvenanceChip provenance={plan.routine_monitoring.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {plan.routine_monitoring.frequency && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Frequency</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={plan.routine_monitoring.frequency || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.routine_monitoring.frequency`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {plan.routine_monitoring.visit_type && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Visit Type</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={plan.routine_monitoring.visit_type.replace(/_/g, " ") || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.routine_monitoring.visit_type`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {plan.routine_monitoring.sdv_percentage !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">SDV %</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={String(plan.routine_monitoring.sdv_percentage) || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.routine_monitoring.sdv_percentage`, v) : undefined}
                  />%
                </span>
              </div>
            )}
          </div>
          {plan.routine_monitoring.sdv_scope?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">SDV Scope</span>
              <div className="flex flex-wrap gap-2">
                {plan.routine_monitoring.sdv_scope.map((s: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-50 text-gray-700 px-2 py-1 rounded">
                    <EditableText
                      value={s || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.routine_monitoring.sdv_scope.${i}`, v) : undefined}
                    />
                  </span>
                ))}
              </div>
            </div>
          )}
          {plan.routine_monitoring.remote_monitoring_activities?.length > 0 && (
            <div>
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Remote Monitoring Activities</span>
              <div className="flex flex-wrap gap-2">
                {plan.routine_monitoring.remote_monitoring_activities.map((a: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">
                    <EditableText
                      value={a || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.routine_monitoring.remote_monitoring_activities.${i}`, v) : undefined}
                    />
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Triggered Monitoring */}
      {plan.triggered_monitoring && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-gray-600" />
            Triggered Monitoring
          </h5>
          {plan.triggered_monitoring.triggers?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Triggers</span>
              <ul className="space-y-1">
                {plan.triggered_monitoring.triggers.map((t: string, i: number) => (
                  <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                    <AlertTriangle className="w-3 h-3 text-gray-500 mt-1 flex-shrink-0" />
                    <EditableText
                      value={t || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.triggered_monitoring.triggers.${i}`, v) : undefined}
                    />
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {plan.triggered_monitoring.response_timeline && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Response Timeline</span>
                <span className="text-sm text-gray-900">
                  <EditableText
                    value={plan.triggered_monitoring.response_timeline || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.triggered_monitoring.response_timeline`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Close-out Visit */}
      {plan.close_out_visit && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-gray-600" />
              Close-out Visit
            </h5>
            <ProvenanceChip provenance={plan.close_out_visit.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {plan.close_out_visit.timing && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Timing</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={plan.close_out_visit.timing || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.close_out_visit.timing`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {plan.close_out_visit.format && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Format</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={plan.close_out_visit.format.replace(/_/g, " ") || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.close_out_visit.format`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>
          {plan.close_out_visit.activities?.length > 0 && (
            <div className="mt-4">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Activities</span>
              <div className="flex flex-wrap gap-2">
                {plan.close_out_visit.activities.map((a: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">
                    <EditableText
                      value={a || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.close_out_visit.activities.${i}`, v) : undefined}
                    />
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

// NEW TAB: Regulatory & Ethics
function RegulatoryTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const reg = data?.regulatory_ethics;
  if (!reg) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No regulatory/ethics information</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Regulatory Authorities */}
      {reg.regulatory_authorities?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Shield className="w-5 h-5 text-gray-900" />
              Regulatory Authorities ({reg.regulatory_authorities.length})
            </h5>
          </div>
          <div className="divide-y divide-gray-100">
            {reg.regulatory_authorities.map((auth: any, idx: number) => (
              <div key={auth.id || idx} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-gray-900">{auth.authority_name}</p>
                    <div className="flex items-center gap-2 mt-1 text-sm text-muted-foreground">
                      {auth.country_region && <span>{auth.country_region}</span>}
                      {auth.submission_type && <span>• {auth.submission_type}</span>}
                      {auth.approval_status && (
                        <span className={cn("px-2 py-0.5 text-xs rounded",
                          auth.approval_status === "approved" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                        )}>{auth.approval_status}</span>
                      )}
                    </div>
                  </div>
                  <ProvenanceChip provenance={auth.provenance} onViewSource={onViewSource} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Ethics Committees */}
      {reg.ethics_committees?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <UserCheck className="w-5 h-5 text-green-600" />
              Ethics Committees ({reg.ethics_committees.length})
            </h5>
          </div>
          <div className="divide-y divide-gray-100">
            {reg.ethics_committees.map((ec: any, idx: number) => (
              <div key={ec.id || idx} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="inline-flex items-center px-2 py-1 text-xs font-medium bg-green-100 text-green-700 rounded">
                      {ec.committee_type}
                    </span>
                    {ec.centralized_or_local && (
                      <span className="ml-2 text-xs text-muted-foreground">{ec.centralized_or_local}</span>
                    )}
                    {ec.approval_requirements && <p className="text-sm text-gray-700 mt-2 break-words">{ec.approval_requirements}</p>}
                  </div>
                  <ProvenanceChip provenance={ec.provenance} onViewSource={onViewSource} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Informed Consent */}
      {reg.informed_consent && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <FileText className="w-5 h-5 text-gray-600" />
              Informed Consent
            </h5>
            <ProvenanceChip provenance={reg.informed_consent.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {reg.informed_consent.consent_type && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Consent Type</span>
                <span className="font-medium text-gray-900">{reg.informed_consent.consent_type}</span>
              </div>
            )}
            {reg.informed_consent.electronic_consent_allowed !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">E-Consent</span>
                <span className="font-medium text-gray-900">{reg.informed_consent.electronic_consent_allowed ? "Allowed" : "Not Allowed"}</span>
              </div>
            )}
            {reg.informed_consent.assent_required !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Assent Required</span>
                <span className="font-medium text-gray-900">{reg.informed_consent.assent_required ? "Yes" : "No"}</span>
              </div>
            )}
          </div>
          {reg.informed_consent.languages_required?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Languages Required</span>
              <div className="flex flex-wrap gap-2">
                {reg.informed_consent.languages_required.map((l: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-50 text-gray-700 px-2 py-1 rounded">{l}</span>
                ))}
              </div>
            </div>
          )}
          {reg.informed_consent.reconsent_triggers?.length > 0 && (
            <div>
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Reconsent Triggers</span>
              <ul className="space-y-1">
                {reg.informed_consent.reconsent_triggers.map((t: string, i: number) => (
                  <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 mt-2 flex-shrink-0" />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Data Privacy */}
      {reg.data_privacy && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Lock className="w-5 h-5 text-gray-600" />
              Data Privacy
            </h5>
            <ProvenanceChip provenance={reg.data_privacy.provenance} onViewSource={onViewSource} />
          </div>
          {reg.data_privacy.applicable_regulations?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Applicable Regulations</span>
              <div className="flex flex-wrap gap-2">
                {reg.data_privacy.applicable_regulations.map((r: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">{r}</span>
                ))}
              </div>
            </div>
          )}
          {reg.data_privacy.data_transfer_requirements && (
            <p className="text-sm text-gray-700 mb-2 break-words"><strong>Transfer Requirements:</strong> {reg.data_privacy.data_transfer_requirements}</p>
          )}
          {reg.data_privacy.anonymization_requirements && (
            <p className="text-sm text-gray-700 break-words"><strong>Anonymization:</strong> {reg.data_privacy.anonymization_requirements}</p>
          )}
        </div>
      )}
    </div>
  );
}

// Helper component to display source text snippet from provenance
function SourceTextSnippet({ provenance, className }: { provenance: any; className?: string }) {
  const textSnippet = provenance?.text_snippet;
  const sectionNumber = provenance?.section_number;

  if (!textSnippet) return null;

  return (
    <div className={cn("mt-3 p-3 bg-gray-50 border-l-4 border-gray-300 rounded-r-lg", className)}>
      <div className="flex items-center gap-2 mb-1">
        <FileText className="w-3 h-3 text-gray-500" />
        <span className="text-xs font-medium text-gray-500 uppercase">Source Text</span>
        {sectionNumber && (
          <span className="text-xs text-gray-400">Section {sectionNumber}</span>
        )}
      </div>
      <p className="text-sm text-gray-600 italic leading-relaxed">{textSnippet}</p>
    </div>
  );
}

// NEW TAB: Personnel
function PersonnelTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const personnel = data?.site_personnel;
  if (!personnel) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No personnel requirements defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Principal Investigator */}
      {personnel.principal_investigator && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-50 border border-gray-200 rounded-2xl p-5">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
                <User className="w-6 h-6 text-white" />
              </div>
              <div>
                <h4 className="font-bold text-gray-900 text-lg">Principal Investigator</h4>
                {personnel.principal_investigator.time_commitment && (
                  <p className="text-sm text-gray-700">Time: {personnel.principal_investigator.time_commitment}</p>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={personnel.principal_investigator.provenance} onViewSource={onViewSource} />
          </div>
          {personnel.principal_investigator.qualifications_required?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-700 uppercase block mb-2">Qualifications Required</span>
              <ul className="space-y-1">
                {personnel.principal_investigator.qualifications_required.map((q: string, i: number) => (
                  <li key={i} className="text-sm text-gray-800 flex items-start gap-2">
                    <CheckCircle className="w-3 h-3 text-gray-900 mt-1 flex-shrink-0" />
                    {q}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {personnel.principal_investigator.responsibilities?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-700 uppercase block mb-2">Responsibilities</span>
              <div className="flex flex-wrap gap-2">
                {personnel.principal_investigator.responsibilities.map((r: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">{r}</span>
                ))}
              </div>
            </div>
          )}
          {personnel.principal_investigator.delegation_restrictions?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-700 uppercase block mb-2">Delegation Restrictions</span>
              <ul className="space-y-1">
                {personnel.principal_investigator.delegation_restrictions.map((d: string, i: number) => (
                  <li key={i} className="text-sm text-gray-800 flex items-start gap-2">
                    <AlertTriangle className="w-3 h-3 text-gray-500 mt-1 flex-shrink-0" />
                    {d}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <SourceTextSnippet
            provenance={personnel.principal_investigator.provenance}
            className="bg-gray-50/50 border-gray-300"
          />
        </div>
      )}

      {/* Sub-Investigators */}
      {personnel.sub_investigators && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Users className="w-5 h-5 text-gray-600" />
              Sub-Investigators
              {personnel.sub_investigators.minimum_number !== undefined && (
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded ml-2">
                  Min: {personnel.sub_investigators.minimum_number}
                </span>
              )}
            </h5>
            <ProvenanceChip provenance={personnel.sub_investigators.provenance} onViewSource={onViewSource} />
          </div>
          {personnel.sub_investigators.qualifications?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Qualifications</span>
              <div className="flex flex-wrap gap-2">
                {personnel.sub_investigators.qualifications.map((q: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">{q}</span>
                ))}
              </div>
            </div>
          )}
          {personnel.sub_investigators.delegated_duties?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Delegated Duties</span>
              <div className="flex flex-wrap gap-2">
                {personnel.sub_investigators.delegated_duties.map((d: string, i: number) => (
                  <span key={i} className="text-xs bg-green-50 text-green-700 px-2 py-1 rounded">{d}</span>
                ))}
              </div>
            </div>
          )}
          <SourceTextSnippet provenance={personnel.sub_investigators.provenance} />
        </div>
      )}

      {/* Coordinators */}
      {personnel.coordinators && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <UserCheck className="w-5 h-5 text-gray-600" />
              Study Coordinators
              {personnel.coordinators.minimum_number !== undefined && (
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded ml-2">
                  Min: {personnel.coordinators.minimum_number}
                </span>
              )}
            </h5>
            <ProvenanceChip provenance={personnel.coordinators.provenance} onViewSource={onViewSource} />
          </div>
          {personnel.coordinators.experience_required && (
            <p className="text-sm text-gray-700 mb-3 break-words"><strong>Experience:</strong> {personnel.coordinators.experience_required}</p>
          )}
          {personnel.coordinators.responsibilities?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Responsibilities</span>
              <div className="flex flex-wrap gap-2">
                {personnel.coordinators.responsibilities.map((r: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">{r}</span>
                ))}
              </div>
            </div>
          )}
          <SourceTextSnippet provenance={personnel.coordinators.provenance} />
        </div>
      )}

      {/* Other Personnel */}
      {personnel.other_personnel?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Users className="w-5 h-5 text-gray-600" />
              Other Personnel ({personnel.other_personnel.length})
            </h5>
          </div>
          <div className="divide-y divide-gray-100">
            {personnel.other_personnel.map((p: any, idx: number) => (
              <div key={p.id || idx} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-gray-900">{p.role_name}</p>
                    {p.minimum_number !== undefined && (
                      <span className="text-xs text-muted-foreground">Min: {p.minimum_number}</span>
                    )}
                  </div>
                  <ProvenanceChip provenance={p.provenance} onViewSource={onViewSource} />
                </div>
                <SourceTextSnippet provenance={p.provenance} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// NEW TAB: Training
function TrainingTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const training = data?.training_requirements;
  const basePath = "domainSections.siteOperationsLogistics.data.training_requirements";

  if (!training) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <GraduationCap className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No training requirements defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Protocol Training */}
      {training.protocol_training && (
        <div className="bg-gradient-to-br from-green-50 to-gray-50 border border-green-200 rounded-2xl p-5">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-green-600 flex items-center justify-center shadow-md">
                <GraduationCap className="w-6 h-6 text-white" />
              </div>
              <div>
                <h4 className="font-bold text-green-900 text-lg">Protocol Training</h4>
                {training.protocol_training.format && (
                  <span className="text-sm text-green-700">
                    <EditableText
                      value={training.protocol_training.format.replace(/_/g, " ") || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.protocol_training.format`, v) : undefined}
                    />
                  </span>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={training.protocol_training.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {training.protocol_training.duration && (
              <div className="p-3 bg-white rounded-lg border border-green-200">
                <span className="text-xs font-medium text-green-700 uppercase block mb-1">Duration</span>
                <span className="font-medium text-green-900">
                  <EditableText
                    value={training.protocol_training.duration || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.protocol_training.duration`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {training.protocol_training.assessment_required !== undefined && (
              <div className="p-3 bg-white rounded-lg border border-green-200">
                <span className="text-xs font-medium text-green-700 uppercase block mb-1">Assessment</span>
                <span className="font-medium text-green-900">{training.protocol_training.assessment_required ? "Required" : "Not Required"}</span>
              </div>
            )}
            {training.protocol_training.completion_deadline && (
              <div className="p-3 bg-white rounded-lg border border-green-200">
                <span className="text-xs font-medium text-green-700 uppercase block mb-1">Deadline</span>
                <span className="font-medium text-green-900">
                  <EditableText
                    value={training.protocol_training.completion_deadline || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.protocol_training.completion_deadline`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>
          {training.protocol_training.required_for?.length > 0 && (
            <div>
              <span className="text-xs font-medium text-green-700 uppercase block mb-2">Required For</span>
              <div className="flex flex-wrap gap-2">
                {training.protocol_training.required_for.map((r: string, i: number) => (
                  <span key={i} className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                    <EditableText
                      value={r || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.protocol_training.required_for.${i}`, v) : undefined}
                    />
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* GCP Training */}
      {training.gcp_training && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5 text-gray-900" />
            GCP Training
          </h5>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {training.gcp_training.required !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Required</span>
                <span className="font-medium text-gray-900">{training.gcp_training.required ? "Yes" : "No"}</span>
              </div>
            )}
            {training.gcp_training.frequency && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Frequency</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={training.gcp_training.frequency || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.gcp_training.frequency`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {training.gcp_training.certification_required !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Certification</span>
                <span className="font-medium text-gray-900">{training.gcp_training.certification_required ? "Required" : "Not Required"}</span>
              </div>
            )}
          </div>
          {training.gcp_training.accepted_providers?.length > 0 && (
            <div className="mt-4">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Accepted Providers</span>
              <div className="flex flex-wrap gap-2">
                {training.gcp_training.accepted_providers.map((p: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">
                    <EditableText
                      value={p || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.gcp_training.accepted_providers.${i}`, v) : undefined}
                    />
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Specialized Training */}
      {training.specialized_training?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Settings className="w-5 h-5 text-gray-600" />
              Specialized Training ({training.specialized_training.length})
            </h5>
          </div>
          <div className="divide-y divide-gray-100">
            {training.specialized_training.map((t: any, idx: number) => (
              <div key={t.id || idx} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-gray-900">
                      <EditableText
                        value={t.training_name || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.specialized_training.${idx}.training_name`, v) : undefined}
                      />
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      {t.certification_required && <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">Certification Required</span>}
                      {t.renewal_period && (
                        <span className="text-xs text-muted-foreground">
                          Renewal: <EditableText
                            value={t.renewal_period || ""}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.specialized_training.${idx}.renewal_period`, v) : undefined}
                          />
                        </span>
                      )}
                    </div>
                  </div>
                  <ProvenanceChip provenance={t.provenance} onViewSource={onViewSource} />
                </div>
                {t.required_for?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {t.required_for.map((r: string, i: number) => (
                      <span key={i} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                        <EditableText
                          value={r || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.specialized_training.${idx}.required_for.${i}`, v) : undefined}
                        />
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// NEW TAB: Timeline
function TimelineTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const timeline = data?.site_activation_timeline;
  if (!timeline) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Calendar className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No site activation timeline defined</p>
      </div>
    );
  }

  const phases = [
    { key: "site_selection_phase", label: "Site Selection", icon: Building2 },
    { key: "feasibility_assessment", label: "Feasibility Assessment", icon: ClipboardCheck },
    { key: "contract_negotiation", label: "Contract Negotiation", icon: FileText },
    { key: "regulatory_submission", label: "Regulatory Submission", icon: Shield },
    { key: "ethics_approval", label: "Ethics Approval", icon: UserCheck },
    { key: "site_training", label: "Site Training", icon: GraduationCap },
    { key: "site_initiation_visit", label: "Site Initiation Visit", icon: CheckCircle },
    { key: "first_patient_ready", label: "First Patient Ready", icon: User },
  ];

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-50 border border-gray-200 rounded-2xl p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
              <Calendar className="w-6 h-6 text-white" />
            </div>
            <div>
              <h4 className="font-bold text-gray-900 text-lg">Site Activation Timeline</h4>
              <p className="text-sm text-gray-700">Key milestones for site activation</p>
            </div>
          </div>
          <ProvenanceChip provenance={timeline.provenance} onViewSource={onViewSource} />
        </div>
      </div>

      {/* Timeline Phases */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
        <div className="space-y-4">
          {phases.map(({ key, label, icon: Icon }, idx) => {
            const value = timeline[key];
            if (!value) return null;
            return (
              <div key={key} className="flex items-start gap-4">
                <div className="flex flex-col items-center">
                  <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center">
                    <Icon className="w-5 h-5 text-gray-900" />
                  </div>
                  {idx < phases.length - 1 && <div className="w-0.5 h-8 bg-gray-200 mt-2" />}
                </div>
                <div className="flex-1 pb-4">
                  <p className="font-medium text-gray-900">{label}</p>
                  <p className="text-sm text-gray-600 mt-1 break-words">{value}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Critical Path Items */}
      {timeline.critical_path_items?.length > 0 && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-5">
          <h5 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-gray-600" />
            Critical Path Items
          </h5>
          <ul className="space-y-2">
            {timeline.critical_path_items.map((item: string, idx: number) => (
              <li key={idx} className="text-sm text-gray-800 flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mt-2 flex-shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// NEW TAB: Drug Supply
function DrugSupplyTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const supply = data?.drug_supply_logistics;
  const basePath = "domainSections.siteOperationsLogistics.data.drug_supply_logistics";

  if (!supply) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Package className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No drug supply logistics defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Packaging & Labeling */}
      {supply.packaging_labeling && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Package className="w-5 h-5 text-gray-600" />
              Packaging & Labeling
            </h5>
            <ProvenanceChip provenance={supply.packaging_labeling.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {supply.packaging_labeling.blinding_requirements && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Blinding</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={supply.packaging_labeling.blinding_requirements.replace(/_/g, " ") || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.packaging_labeling.blinding_requirements`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {supply.packaging_labeling.kit_design && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Kit Design</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={supply.packaging_labeling.kit_design.replace(/_/g, " ") || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.packaging_labeling.kit_design`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {supply.packaging_labeling.temperature_indicators !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Temp Indicators</span>
                <span className="font-medium text-gray-900">{supply.packaging_labeling.temperature_indicators ? "Yes" : "No"}</span>
              </div>
            )}
            {supply.packaging_labeling.tamper_evident !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Tamper Evident</span>
                <span className="font-medium text-gray-900">{supply.packaging_labeling.tamper_evident ? "Yes" : "No"}</span>
              </div>
            )}
          </div>
          {supply.packaging_labeling.label_languages?.length > 0 && (
            <div className="mt-4">
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Label Languages</span>
              <div className="flex flex-wrap gap-2">
                {supply.packaging_labeling.label_languages.map((l: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-50 text-gray-700 px-2 py-1 rounded">
                    <EditableText
                      value={l || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.packaging_labeling.label_languages.${i}`, v) : undefined}
                    />
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Storage & Distribution */}
      {supply.storage_distribution && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Thermometer className="w-5 h-5 text-gray-900" />
              Storage & Distribution
            </h5>
            <ProvenanceChip provenance={supply.storage_distribution.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {supply.storage_distribution.storage_temperature && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-700 uppercase block mb-1">Storage Temp</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={supply.storage_distribution.storage_temperature || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.storage_distribution.storage_temperature`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {supply.storage_distribution.distribution_model && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Distribution</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={supply.storage_distribution.distribution_model.replace(/_/g, " ") || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.storage_distribution.distribution_model`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {supply.storage_distribution.cold_chain_required !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Cold Chain</span>
                <span className="font-medium text-gray-900">{supply.storage_distribution.cold_chain_required ? "Required" : "Not Required"}</span>
              </div>
            )}
            {supply.storage_distribution.shelf_life_months && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Shelf Life</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={String(supply.storage_distribution.shelf_life_months) || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.storage_distribution.shelf_life_months`, v) : undefined}
                  /> months
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Inventory Management */}
      {supply.inventory_management && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Settings className="w-5 h-5 text-gray-600" />
              Inventory Management
            </h5>
            <ProvenanceChip provenance={supply.inventory_management.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {supply.inventory_management.iwrs_rtsm_system && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">IWRS/RTSM System</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={supply.inventory_management.iwrs_rtsm_system || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.inventory_management.iwrs_rtsm_system`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {supply.inventory_management.resupply_threshold_days && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Resupply Threshold</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={String(supply.inventory_management.resupply_threshold_days) || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.inventory_management.resupply_threshold_days`, v) : undefined}
                  /> days
                </span>
              </div>
            )}
            {supply.inventory_management.expiry_management && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Expiry Management</span>
                <span className="font-medium text-gray-900">
                  <EditableText
                    value={supply.inventory_management.expiry_management || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.inventory_management.expiry_management`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Emergency Unblinding */}
      {supply.emergency_unblinding && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h5 className="font-semibold text-red-900 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-600" />
              Emergency Unblinding
            </h5>
            <ProvenanceChip provenance={supply.emergency_unblinding.provenance} onViewSource={onViewSource} />
          </div>
          {supply.emergency_unblinding.unblinding_allowed !== undefined && (
            <p className="text-sm text-red-800 mb-3">
              <strong>Allowed:</strong> {supply.emergency_unblinding.unblinding_allowed ? "Yes" : "No"}
            </p>
          )}
          {supply.emergency_unblinding.unblinding_triggers?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-red-700 uppercase block mb-2">Triggers</span>
              <ul className="space-y-1">
                {supply.emergency_unblinding.unblinding_triggers.map((t: string, i: number) => (
                  <li key={i} className="text-sm text-red-800 flex items-start gap-2">
                    <AlertTriangle className="w-3 h-3 text-red-500 mt-1 flex-shrink-0" />
                    <EditableText
                      value={t || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.emergency_unblinding.unblinding_triggers.${i}`, v) : undefined}
                    />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {supply.emergency_unblinding.who_can_unblind?.length > 0 && (
            <div>
              <span className="text-xs font-medium text-red-700 uppercase block mb-2">Who Can Unblind</span>
              <div className="flex flex-wrap gap-2">
                {supply.emergency_unblinding.who_can_unblind.map((w: string, i: number) => (
                  <span key={i} className="text-xs bg-red-100 text-red-700 px-2 py-1 rounded">
                    <EditableText
                      value={w || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.emergency_unblinding.who_can_unblind.${i}`, v) : undefined}
                    />
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

// NEW TAB: Technology
function TechnologyTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const tech = data?.technology_systems;
  if (!tech) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Monitor className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No technology systems defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* EDC System */}
      {tech.edc_system && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-50 border border-gray-200 rounded-2xl p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
              <Monitor className="w-6 h-6 text-white" />
            </div>
            <div>
              <h4 className="font-bold text-gray-900 text-lg">EDC System</h4>
              {tech.edc_system.vendor_name && (
                <p className="text-sm text-gray-700">{tech.edc_system.vendor_name}</p>
              )}
            </div>
          </div>
          {tech.edc_system.system_capabilities?.length > 0 && (
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-700 uppercase block mb-2">Capabilities</span>
              <div className="flex flex-wrap gap-2">
                {tech.edc_system.system_capabilities.map((c: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">{c.replace(/_/g, " ")}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* IWRS/RTSM */}
      {tech.iwrs_rtsm && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Settings className="w-5 h-5 text-gray-600" />
            IWRS/RTSM
            {tech.iwrs_rtsm.vendor_name && (
              <span className="text-sm font-normal text-muted-foreground ml-2">({tech.iwrs_rtsm.vendor_name})</span>
            )}
          </h5>
          {tech.iwrs_rtsm.functions?.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {tech.iwrs_rtsm.functions.map((f: string, i: number) => (
                <span key={i} className="text-xs bg-gray-50 text-gray-700 px-2 py-1 rounded">{f}</span>
              ))}
            </div>
          )}
          {tech.iwrs_rtsm.integration_with_edc !== undefined && (
            <p className="text-sm text-gray-700 mt-3 break-words">
              <strong>EDC Integration:</strong> {tech.iwrs_rtsm.integration_with_edc ? "Yes" : "No"}
            </p>
          )}
        </div>
      )}

      {/* ePRO Devices */}
      {tech.epro_devices && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Monitor className="w-5 h-5 text-green-600" />
            ePRO Devices
          </h5>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
            {tech.epro_devices.required !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Required</span>
                <span className="font-medium text-gray-900">{tech.epro_devices.required ? "Yes" : "No"}</span>
              </div>
            )}
            {tech.epro_devices.device_type && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Device Type</span>
                <span className="font-medium text-gray-900">{tech.epro_devices.device_type}</span>
              </div>
            )}
            {tech.epro_devices.training_required !== undefined && (
              <div className="p-3 bg-gray-50 rounded-lg">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-1">Training</span>
                <span className="font-medium text-gray-900">{tech.epro_devices.training_required ? "Required" : "Not Required"}</span>
              </div>
            )}
          </div>
          {tech.epro_devices.instruments_collected?.length > 0 && (
            <div>
              <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Instruments Collected</span>
              <div className="flex flex-wrap gap-2">
                {tech.epro_devices.instruments_collected.map((i: string, idx: number) => (
                  <span key={idx} className="text-xs bg-green-50 text-green-700 px-2 py-1 rounded">{i}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Central Services */}
      {tech.central_services?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Building2 className="w-5 h-5 text-gray-600" />
              Central Services ({tech.central_services.length})
            </h5>
          </div>
          <div className="divide-y divide-gray-100">
            {tech.central_services.map((svc: any, idx: number) => (
              <div key={svc.id || idx} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="inline-flex items-center px-2 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded">
                      {svc.service_type?.replace(/_/g, " ")}
                    </span>
                    {svc.vendor_name && <span className="ml-2 text-sm text-gray-900">{svc.vendor_name}</span>}
                    {svc.turnaround_time && <p className="text-xs text-muted-foreground mt-1">Turnaround: {svc.turnaround_time}</p>}
                  </div>
                  <ProvenanceChip provenance={svc.provenance} onViewSource={onViewSource} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// NEW TAB: Vendors
function VendorsTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const vendors = data?.vendor_coordination || [];
  if (vendors.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Truck className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No vendor coordination defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <p className="text-sm text-gray-700">
          <strong>Vendor Coordination:</strong> {vendors.length} third-party vendors involved in study operations.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {vendors.map((vendor: any, idx: number) => (
          <div key={vendor.id || idx} className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center">
                  <Truck className="w-5 h-5 text-gray-600" />
                </div>
                <div>
                  <span className="inline-flex items-center px-2 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded">
                    {vendor.vendor_type?.replace(/_/g, " ")}
                  </span>
                  {vendor.vendor_name && <p className="font-medium text-gray-900 mt-1">{vendor.vendor_name}</p>}
                </div>
              </div>
              <ProvenanceChip provenance={vendor.provenance} onViewSource={onViewSource} />
            </div>

            {vendor.services_provided?.length > 0 && (
              <div className="mb-3">
                <span className="text-xs font-medium text-gray-600 uppercase block mb-2">Services</span>
                <div className="flex flex-wrap gap-1">
                  {vendor.services_provided.map((s: string, i: number) => (
                    <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">{s}</span>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              {vendor.site_interface_required !== undefined && (
                <span>Site Interface: {vendor.site_interface_required ? "Yes" : "No"}</span>
              )}
              {vendor.training_required !== undefined && (
                <span>Training: {vendor.training_required ? "Required" : "Not Required"}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SiteLogisticsViewContent({ data, onViewSource, onFieldUpdate }: SiteLogisticsViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "site_selection", label: "Site Selection", icon: Building2 },
    { id: "regulatory", label: "Regulatory", icon: Shield },
    { id: "personnel", label: "Personnel", icon: Users },
    { id: "training", label: "Training", icon: GraduationCap },
    { id: "monitoring", label: "Monitoring", icon: ClipboardCheck },
    { id: "timeline", label: "Timeline", icon: Calendar },
    { id: "drug_supply", label: "Drug Supply", icon: Package },
    { id: "technology", label: "Technology", icon: Monitor },
    { id: "vendors", label: "Vendors", icon: Truck },
  ];
  
  return (
    <div className="space-y-6" data-testid="site-logistics-view">
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
          {activeTab === "site_selection" && <SiteSelectionTab data={data} onViewSource={onViewSource} />}
          {activeTab === "regulatory" && <RegulatoryTab data={data} onViewSource={onViewSource} />}
          {activeTab === "personnel" && <PersonnelTab data={data} onViewSource={onViewSource} />}
          {activeTab === "training" && <TrainingTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "monitoring" && <MonitoringTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "timeline" && <TimelineTab data={data} onViewSource={onViewSource} />}
          {activeTab === "drug_supply" && <DrugSupplyTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "technology" && <TechnologyTab data={data} onViewSource={onViewSource} />}
          {activeTab === "vendors" && <VendorsTab data={data} onViewSource={onViewSource} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function SiteLogisticsView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: SiteLogisticsViewProps) {
  if (!data) {
    return (<div className="text-center py-12 text-muted-foreground"><Building2 className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No site logistics data available</p></div>);
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <SiteLogisticsViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
