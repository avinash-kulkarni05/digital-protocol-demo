import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, UserCheck, AlertTriangle, Gift, DollarSign, Heart, LayoutGrid, ChevronDown, Lock, Shield, ClipboardList, Clock, Info } from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { EditableText } from "./EditableValue";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";

interface InformedConsentViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "procedures" | "risks" | "benefits" | "confidentiality";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function SummaryHeader({ data }: { data: any }) {
  const riskCount = data?.risks?.specific_risks?.length || 0;
  return (
    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="consent-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center shadow-md">
          <UserCheck className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Informed Consent</h3>
          <p className="text-sm text-muted-foreground">Study overview, risks, benefits, and compensation</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><UserCheck className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Overview</span></div>
          <p className="text-lg font-bold text-gray-900">{data?.study_overview ? "Defined" : "N/A"}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><AlertTriangle className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Risks Identified</span></div>
          <p className="text-2xl font-bold text-gray-900">{riskCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Gift className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Benefits</span></div>
          <p className="text-lg font-bold text-gray-900">{data?.benefits ? "Defined" : "N/A"}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  return (
    <div className="space-y-6">
      {data.study_overview && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
              <UserCheck className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-start justify-between gap-3 mb-2">
                <h4 className="font-bold text-gray-900 text-lg">Study Purpose</h4>
                <ProvenanceChip provenance={data.study_overview.provenance} onViewSource={onViewSource} />
              </div>
              <div className="text-sm text-gray-700 leading-relaxed">
                <EditableText
                  value={data.study_overview.study_purpose || ""}
                  multiline
                  onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.informedConsent.data.study_overview.study_purpose", v) : undefined}
                />
              </div>
            </div>
          </div>
        </div>
      )}
      
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Heart className="w-5 h-5 text-gray-600" />
            Consent Summary
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <UserCheck className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{data.study_overview ? "Yes" : "No"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Study Overview</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <AlertTriangle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{data.risks?.specific_risks?.length || 0}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Risks</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <DollarSign className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{data.compensation_costs ? "Defined" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Compensation</p>
            </div>
          </div>
        </div>
      </div>
      
      {data.compensation_costs && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <h4 className="font-semibold text-foreground flex items-center gap-2">
              <DollarSign className="w-5 h-5 text-gray-600" />
              Compensation & Costs
            </h4>
            <ProvenanceChip provenance={data.compensation_costs.provenance} onViewSource={onViewSource} />
          </div>
          <div className="space-y-4">
            {data.compensation_costs.covered_costs && data.compensation_costs.covered_costs.length > 0 && (
              <div>
                <h5 className="text-sm font-medium text-gray-700 mb-2">Covered Costs</h5>
                <ul className="space-y-2">
                  {data.compensation_costs.covered_costs.map((cost: string, idx: number) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                      <span className="w-1.5 h-1.5 rounded-full bg-gray-800 mt-1.5 flex-shrink-0" />
                      <EditableText
                        value={cost}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`domainSections.informedConsent.data.compensation_costs.covered_costs.${idx}`, v) : undefined}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {data.compensation_costs.participant_costs && data.compensation_costs.participant_costs.length > 0 && (
              <div>
                <h5 className="text-sm font-medium text-gray-700 mb-2">Participant Costs</h5>
                <ul className="space-y-2">
                  {data.compensation_costs.participant_costs.map((cost: string, idx: number) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                      <span className="w-1.5 h-1.5 rounded-full bg-gray-600 mt-1.5 flex-shrink-0" />
                      <EditableText
                        value={cost}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`domainSections.informedConsent.data.compensation_costs.participant_costs.${idx}`, v) : undefined}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {data.compensation_costs.injury_compensation && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <h5 className="text-sm font-medium text-gray-800 mb-1">Injury Compensation</h5>
                <p className="text-sm text-gray-700">{data.compensation_costs.injury_compensation}</p>
              </div>
            )}
            
            {data.compensation_costs.travel_reimbursement && (
              <div>
                <h5 className="text-sm font-medium text-gray-700 mb-1">Travel Reimbursement</h5>
                <p className="text-sm text-gray-600">{data.compensation_costs.travel_reimbursement}</p>
              </div>
            )}
            
            {data.compensation_costs.participant_compensation && (
              <div>
                <h5 className="text-sm font-medium text-gray-700 mb-1">Participant Compensation</h5>
                <p className="text-sm text-gray-600">{data.compensation_costs.participant_compensation}</p>
              </div>
            )}
            
            {data.compensation_costs.payment_schedule && (
              <div>
                <h5 className="text-sm font-medium text-gray-700 mb-1">Payment Schedule</h5>
                <p className="text-sm text-gray-600">{data.compensation_costs.payment_schedule}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// NEW TAB: Study Procedures
function ProceduresTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const procedures = data?.study_procedures;
  if (!procedures || !Array.isArray(procedures) || procedures.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <ClipboardList className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study procedures defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {procedures.map((procedure: any, idx: number) => (
        <div key={procedure.procedure_id || idx} className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center">
                <ClipboardList className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h4 className="font-semibold text-foreground">{procedure.procedure_name}</h4>
                {procedure.is_optional && (
                  <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded mt-1 inline-block">Optional</span>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={procedure.provenance} onViewSource={onViewSource} />
          </div>

          {procedure.description && (
            <p className="text-sm text-gray-700 mb-3">{procedure.description}</p>
          )}

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {procedure.frequency && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Frequency</span>
                <span className="text-sm font-medium text-gray-900">{procedure.frequency}</span>
              </div>
            )}
            {procedure.duration && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Duration</span>
                <span className="text-sm font-medium text-gray-900">{procedure.duration}</span>
              </div>
            )}
          </div>
        </div>
      ))}

      {/* Study Duration Overview */}
      {data.study_overview?.duration && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-5 h-5 text-gray-600" />
            <span className="font-semibold text-foreground">Study Duration</span>
          </div>
          <p className="text-sm text-gray-700">{data.study_overview.duration}</p>
        </div>
      )}

      {/* Procedures Summary */}
      {data.study_overview?.procedures_summary && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <Info className="w-5 h-5 text-gray-600" />
            <span className="font-semibold text-foreground">Procedures Summary</span>
          </div>
          <p className="text-sm text-gray-700">{data.study_overview.procedures_summary}</p>
        </div>
      )}
    </div>
  );
}

// Helper to safely render a value that might be a primitive or an object with value/provenance
function renderValue(val: any): string {
  if (val === null || val === undefined) return '';
  if (typeof val === 'string') return val;
  if (typeof val === 'boolean') return val ? 'Yes' : 'No';
  if (typeof val === 'number') return String(val);
  if (typeof val === 'object') {
    if (val.value !== undefined) return renderValue(val.value);
    if (val.decode !== undefined) return val.decode;
    return JSON.stringify(val);
  }
  return String(val);
}

// Special Consent Card - renders complex consent objects nicely
function SpecialConsentCard({
  title,
  consent,
  onViewSource
}: {
  title: string;
  consent: any;
  onViewSource?: (page: number) => void;
}) {
  // Handle simple string value
  if (typeof consent === 'string') {
    return (
      <div className="bg-white/70 rounded-lg p-4 border border-purple-200">
        <span className="text-xs font-medium text-purple-700 uppercase block mb-2">{title}</span>
        <p className="text-sm text-purple-900">{consent}</p>
      </div>
    );
  }

  // Handle boolean value
  if (typeof consent === 'boolean') {
    return (
      <div className="bg-white/70 rounded-lg p-4 border border-purple-200">
        <span className="text-xs font-medium text-purple-700 uppercase block mb-2">{title}</span>
        <p className="text-sm text-purple-900">{consent ? 'Yes' : 'No'}</p>
      </div>
    );
  }

  // Handle complex object
  const description = consent.description || consent.summary;
  const isRequired = consent.required;
  const isOptional = consent.required === false || consent.opt_out_allowed;
  const futureUse = consent.future_use;
  const resultsDisclosure = consent.results_disclosure;
  const provenance = consent.provenance;

  return (
    <div className="bg-white rounded-lg p-4 border border-purple-200 shadow-sm">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-purple-900">{title}</span>
          {isRequired === true && (
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200">
              Required
            </span>
          )}
          {isOptional && (
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-700 border border-green-200">
              Optional
            </span>
          )}
        </div>
        {provenance && <ProvenanceChip provenance={provenance} onViewSource={onViewSource} />}
      </div>

      {description && (
        <p className="text-sm text-gray-700 mb-3">{description}</p>
      )}

      <div className="flex flex-wrap gap-2">
        {futureUse !== undefined && (
          <span className={cn(
            "text-[10px] font-medium px-2 py-1 rounded-full border",
            futureUse
              ? "bg-amber-50 text-amber-700 border-amber-200"
              : "bg-gray-50 text-gray-600 border-gray-200"
          )}>
            Future Use: {futureUse ? 'Yes' : 'No'}
          </span>
        )}
        {consent.opt_out_allowed !== undefined && (
          <span className={cn(
            "text-[10px] font-medium px-2 py-1 rounded-full border",
            consent.opt_out_allowed
              ? "bg-blue-50 text-blue-700 border-blue-200"
              : "bg-gray-50 text-gray-600 border-gray-200"
          )}>
            Opt-out: {consent.opt_out_allowed ? 'Allowed' : 'Not Allowed'}
          </span>
        )}
        {consent.separate_consent !== undefined && (
          <span className="text-[10px] font-medium px-2 py-1 rounded-full bg-purple-100 text-purple-700 border border-purple-200">
            Separate Consent: {consent.separate_consent ? 'Yes' : 'No'}
          </span>
        )}
      </div>

      {resultsDisclosure && (
        <div className="mt-3 pt-3 border-t border-purple-100">
          <span className="text-xs font-medium text-purple-600 block mb-1">Results Disclosure</span>
          <p className="text-sm text-gray-600">{resultsDisclosure}</p>
        </div>
      )}

      {consent.retention_period && (
        <div className="mt-2">
          <span className="text-xs font-medium text-purple-600 block mb-1">Retention Period</span>
          <p className="text-sm text-gray-600">{consent.retention_period}</p>
        </div>
      )}

      {consent.withdrawal_process && (
        <div className="mt-2">
          <span className="text-xs font-medium text-purple-600 block mb-1">Withdrawal</span>
          <p className="text-sm text-gray-600">{consent.withdrawal_process}</p>
        </div>
      )}
    </div>
  );
}

// NEW TAB: Confidentiality & Privacy
function ConfidentialityTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const confidentiality = data?.confidentiality;
  const voluntary = data?.voluntary_participation;
  const specialConsents = data?.special_consents;

  if (!confidentiality && !voluntary && !specialConsents) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Lock className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No confidentiality information defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Confidentiality */}
      {confidentiality && (
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-2xl p-5">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center shadow-md">
                <Lock className="w-6 h-6 text-white" />
              </div>
              <h4 className="font-bold text-blue-900 text-lg">Confidentiality</h4>
            </div>
            <ProvenanceChip provenance={confidentiality.provenance} onViewSource={onViewSource} />
          </div>
          <div className="space-y-3">
            {confidentiality.privacy_protections && (
              <div className="bg-white/70 rounded-lg p-3 border border-blue-200">
                <span className="text-xs font-medium text-blue-700 uppercase block mb-1">Privacy Protections</span>
                <span className="text-sm text-blue-900">{renderValue(confidentiality.privacy_protections)}</span>
              </div>
            )}
            {confidentiality.data_retention && (
              <div className="bg-white/70 rounded-lg p-3 border border-blue-200">
                <span className="text-xs font-medium text-blue-700 uppercase block mb-1">Data Retention</span>
                <span className="text-sm text-blue-900">{renderValue(confidentiality.data_retention)}</span>
              </div>
            )}
            {confidentiality.data_use_restrictions && (
              <div className="bg-white/70 rounded-lg p-3 border border-blue-200">
                <span className="text-xs font-medium text-blue-700 uppercase block mb-1">Data Use Restrictions</span>
                <span className="text-sm text-blue-900">{renderValue(confidentiality.data_use_restrictions)}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Voluntary Participation */}
      {voluntary && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5 text-gray-600" />
            Voluntary Participation
          </h5>
          <div className="space-y-3">
            {voluntary.statement_of_rights && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Statement of Rights</span>
                <span className="text-sm text-gray-700">{renderValue(voluntary.statement_of_rights)}</span>
              </div>
            )}
            {voluntary.withdrawal_process && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Withdrawal Process</span>
                <span className="text-sm text-gray-700">{renderValue(voluntary.withdrawal_process)}</span>
              </div>
            )}
            {voluntary.consequences_of_withdrawal && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase block mb-1">Consequences of Withdrawal</span>
                <span className="text-sm text-gray-700">{renderValue(voluntary.consequences_of_withdrawal)}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Special Consents */}
      {specialConsents && (
        <div className="bg-purple-50 border border-purple-200 rounded-xl p-5">
          <h5 className="font-semibold text-purple-900 mb-4 flex items-center gap-2">
            <Heart className="w-5 h-5 text-purple-600" />
            Special Consents
          </h5>
          <div className="space-y-4">
            {specialConsents.genetic_testing && (
              <SpecialConsentCard
                title="Genetic Testing"
                consent={specialConsents.genetic_testing}
                onViewSource={onViewSource}
              />
            )}
            {specialConsents.future_research && (
              <SpecialConsentCard
                title="Future Research"
                consent={specialConsents.future_research}
                onViewSource={onViewSource}
              />
            )}
            {specialConsents.secondary_data_use && (
              <SpecialConsentCard
                title="Secondary Data Use"
                consent={specialConsents.secondary_data_use}
                onViewSource={onViewSource}
              />
            )}
            {specialConsents.biobanking && (
              <SpecialConsentCard
                title="Biobanking"
                consent={specialConsents.biobanking}
                onViewSource={onViewSource}
              />
            )}
            {specialConsents.photography && (
              <SpecialConsentCard
                title="Photography/Video"
                consent={specialConsents.photography}
                onViewSource={onViewSource}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function RiskCard({ risk, onViewSource }: { risk: any; onViewSource?: (page: number) => void }) {
  const [showAllData, setShowAllData] = useState(false);
  
  return (
    <div className="bg-gray-50 rounded-xl p-4 border border-gray-200" data-testid={`risk-${risk.id || risk.risk_name}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-4 h-4 text-gray-600" />
          </div>
          <div>
            <span className="font-medium text-gray-700">{risk.risk_name || risk}</span>
            {risk.risk_description && (
              <p className="text-sm text-gray-700 mt-1">{risk.risk_description}</p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowAllData(!showAllData)}
          className="p-1 hover:bg-gray-200 rounded transition-colors flex-shrink-0"
          data-testid={`expand-risk-${risk.id || risk.risk_name}`}
        >
          <ChevronDown className={cn("w-4 h-4 text-gray-500 transition-transform", showAllData && "rotate-180")} />
        </button>
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
              <SmartDataRender data={risk} onViewSource={onViewSource} editable={false} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function RisksTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const risks = data?.risks;
  
  if (!risks) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No risks defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-4">
      {risks.risk_summary && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h4 className="font-semibold text-foreground mb-2">Risk Summary</h4>
          <p className="text-sm text-muted-foreground">{risks.risk_summary}</p>
        </div>
      )}
      
      {risks.specific_risks && risks.specific_risks.length > 0 && (
        <div className="space-y-3">
          {risks.specific_risks.slice(0, 15).map((risk: any, idx: number) => (
            <RiskCard key={idx} risk={risk} onViewSource={onViewSource} />
          ))}
        </div>
      )}
    </div>
  );
}

function BenefitsTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  if (!data?.benefits) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Gift className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No benefits defined</p>
      </div>
    );
  }

  const benefits = data.benefits;

  // Support both naming conventions from different extraction versions
  const potentialBenefits = benefits.potential_benefits || benefits.direct_benefits;
  const societalBenefits = benefits.societal_benefits || benefits.indirect_benefits;
  const benefitStatement = benefits.benefit_statement;
  const noBenefitStatement = benefits.no_benefit_statement || benefits.no_direct_benefit;

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3 mb-4">
        <h4 className="font-semibold text-foreground flex items-center gap-2">
          <Gift className="w-5 h-5 text-gray-600" />
          Benefits
        </h4>
        <ProvenanceChip provenance={benefits.provenance} onViewSource={onViewSource} />
      </div>
      <div className="space-y-4">
        {typeof benefits === 'string' ? (
          <p className="text-sm text-gray-700">{benefits}</p>
        ) : (
          <>
            {benefitStatement && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <p className="text-sm text-gray-800">{benefitStatement}</p>
              </div>
            )}
            {potentialBenefits && (
              <div>
                <h5 className="text-sm font-medium text-gray-700 mb-2">Potential Benefits</h5>
                {Array.isArray(potentialBenefits) ? (
                  <ul className="space-y-2">
                    {potentialBenefits.map((benefit: string, idx: number) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                        <span className="w-1.5 h-1.5 rounded-full bg-gray-800 mt-1.5 flex-shrink-0" />
                        {benefit}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-600">{potentialBenefits}</p>
                )}
              </div>
            )}
            {societalBenefits && (
              <div>
                <h5 className="text-sm font-medium text-gray-700 mb-2">Societal Benefits</h5>
                {Array.isArray(societalBenefits) ? (
                  <ul className="space-y-2">
                    {societalBenefits.map((benefit: string, idx: number) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                        <span className="w-1.5 h-1.5 rounded-full bg-gray-700 mt-1.5 flex-shrink-0" />
                        {benefit}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-600">{societalBenefits}</p>
                )}
              </div>
            )}
            {noBenefitStatement && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <h5 className="text-sm font-medium text-gray-800 mb-1">Important Note</h5>
                <p className="text-sm text-gray-700">{noBenefitStatement}</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function InformedConsentViewContent({ data, onViewSource, onFieldUpdate }: InformedConsentViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: LayoutGrid },
    { id: "procedures", label: "Procedures", icon: ClipboardList, count: data.study_procedures?.length || 0 },
    { id: "risks", label: "Risks", icon: AlertTriangle, count: data.risks?.specific_risks?.length || 0 },
    { id: "benefits", label: "Benefits", icon: Gift },
    { id: "confidentiality", label: "Privacy", icon: Lock },
  ];
  
  return (
    <div className="space-y-6" data-testid="consent-view">
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
          {activeTab === "procedures" && <ProceduresTab data={data} onViewSource={onViewSource} />}
          {activeTab === "risks" && <RisksTab data={data} onViewSource={onViewSource} />}
          {activeTab === "benefits" && <BenefitsTab data={data} onViewSource={onViewSource} />}
          {activeTab === "confidentiality" && <ConfidentialityTab data={data} onViewSource={onViewSource} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function InformedConsentView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: InformedConsentViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <UserCheck className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No consent data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <InformedConsentViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
