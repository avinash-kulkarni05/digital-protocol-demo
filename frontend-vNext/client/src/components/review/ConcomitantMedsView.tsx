import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, ChevronDown, Pill, XCircle, AlertTriangle,
  CheckCircle, ShieldAlert, Heart, Layers, Zap, Clock, Syringe, Timer, Leaf
} from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";
import { EditableText } from "./EditableValue";

interface ConcomitantMedsViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "prohibited" | "allowed" | "interactions" | "requirements" | "washout";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

// Helper to extract string value from CDISC Code objects or plain strings
function getStringValue(value: any, fallback: string = ""): string {
  if (!value) return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'object') {
    // Handle CDISC Code objects with decode property
    if (value.decode) return String(value.decode);
    // Handle objects with value property
    if (value.value) return String(value.value);
    // Handle objects with name property
    if (value.name) return String(value.name);
    // Handle objects with text property
    if (value.text) return String(value.text);
  }
  return fallback;
}

function AccordionSection({ 
  title, 
  icon: Icon, 
  children, 
  defaultOpen = false,
  count,
  variant = "default"
}: { 
  title: string; 
  icon: React.ElementType; 
  children: React.ReactNode; 
  defaultOpen?: boolean;
  count?: number;
  variant?: "default" | "prohibited" | "restricted" | "allowed" | "rescue";
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  
  const variantStyles = {
    default: { bg: "bg-gray-100", icon: "text-gray-600" },
    prohibited: { bg: "bg-gray-100", icon: "text-gray-900" },
    restricted: { bg: "bg-gray-100", icon: "text-gray-900" },
    allowed: { bg: "bg-gray-100", icon: "text-gray-900" },
    rescue: { bg: "bg-gray-100", icon: "text-gray-900" }
  };
  
  const style = variantStyles[variant];
  
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white" data-testid={`accordion-${title.toLowerCase().replace(/\s+/g, '-')}`}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors text-left"
        data-testid={`accordion-toggle-${title.toLowerCase().replace(/\s+/g, '-')}`}
      >
        <div className="flex items-center gap-3">
          <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center", style.bg)}>
            <Icon className={cn("w-4 h-4", style.icon)} />
          </div>
          <span className="font-semibold text-foreground">{title}</span>
          {count !== undefined && (
            <span className="text-xs text-muted-foreground bg-gray-100 px-2 py-0.5 rounded-full">{count}</span>
          )}
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
  const prohibited = data?.prohibited_medications?.length || 0;
  const restricted = data?.restricted_medications?.length || 0;
  const allowed = data?.allowed_medications?.length || 0;
  const interactions = data?.drug_interactions?.length || 0;
  const requirements = data?.required_medications?.length || 0;
  
  return (
    <div className="bg-gradient-to-br from-slate-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="meds-summary-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center shadow-md">
          <Pill className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Concomitant Medications</h3>
          <p className="text-sm text-muted-foreground">Medication guidelines and restrictions</p>
        </div>
      </div>
      
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-prohibited">
          <div className="flex items-center gap-2 mb-1">
            <XCircle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Prohibited</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{prohibited}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-restricted">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Restricted</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{restricted}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-allowed">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Allowed</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{allowed}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-interactions">
          <div className="flex items-center gap-2 mb-1">
            <Zap className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Interactions</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{interactions}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-required">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Required</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{requirements}</p>
        </div>
      </div>
    </div>
  );
}

function MedicationCard({
  med,
  idx,
  variant,
  onViewSource,
  onFieldUpdate
}: {
  med: any;
  idx: number;
  variant: "prohibited" | "restricted" | "allowed";
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
}) {
  const [showAllData, setShowAllData] = useState(false);
  const basePath = `domainSections.concomitantMedications.data.${variant}_medications.${idx}`;

  const configs = {
    prohibited: {
      bg: "bg-gray-50",
      border: "border-gray-200",
      iconBg: "bg-gray-100",
      iconColor: "text-gray-600",
      tagBg: "bg-gray-50",
      tagText: "text-gray-700",
      tagBorder: "border-gray-200"
    },
    restricted: {
      bg: "bg-gray-50",
      border: "border-gray-200",
      iconBg: "bg-gray-100",
      iconColor: "text-gray-600",
      tagBg: "bg-gray-50",
      tagText: "text-gray-700",
      tagBorder: "border-gray-200"
    },
    allowed: {
      bg: "bg-gray-50",
      border: "border-gray-200",
      iconBg: "bg-gray-100",
      iconColor: "text-gray-600",
      tagBg: "bg-gray-50",
      tagText: "text-gray-700",
      tagBorder: "border-gray-200"
    }
  };

  const config = configs[variant];
  const title = getStringValue(med.medication_class) || getStringValue(med.medication_type) || "Medication";
  const descriptionRaw = variant === "prohibited"
    ? med.prohibition_reason_detail
    : variant === "restricted"
    ? med.restriction_details
    : med.allowance_details;
  const description = getStringValue(descriptionRaw);

  return (
    <div className={cn("rounded-xl p-4 border", config.bg, config.border)}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", config.iconBg)}>
            <Pill className={cn("w-5 h-5", config.iconColor)} />
          </div>
          <div>
            <h4 className="font-semibold text-foreground">
              <EditableText
                value={title}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.medication_class`, v) : undefined}
              />
            </h4>
            {description && (
              <div className="text-sm text-muted-foreground mt-1">
                <EditableText
                  value={description}
                  multiline
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${variant === "prohibited" ? "prohibition_reason_detail" : variant === "restricted" ? "restriction_details" : "allowance_details"}`, v) : undefined}
                />
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Prohibition period badge */}
          {variant === "prohibited" && med.prohibition_period?.decode && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-200 text-gray-700">
              {med.prohibition_period.decode}
            </span>
          )}
          <ProvenanceChip provenance={med.provenance} onViewSource={onViewSource} />
          <button
            onClick={() => setShowAllData(!showAllData)}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
            data-testid={`expand-med-${med.id}`}
          >
            <ChevronDown className={cn("w-4 h-4 text-gray-500 transition-transform", showAllData && "rotate-180")} />
          </button>
        </div>
      </div>

      {med.specific_drugs && med.specific_drugs.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {med.specific_drugs.map((drug: string, idx: number) => (
            <span key={idx} className={cn("text-xs px-2.5 py-1 rounded-full border", config.tagBg, config.tagText, config.tagBorder)}>
              {drug}
            </span>
          ))}
        </div>
      )}

      {/* Restricted Medication Conditions */}
      {variant === "restricted" && med.conditions && (
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2">
          {med.conditions.max_dose && (
            <div className="bg-white/70 rounded-lg p-2 border border-gray-200">
              <span className="text-xs text-gray-500 block">Max Dose</span>
              <span className="text-sm font-medium text-gray-900">{med.conditions.max_dose}</span>
            </div>
          )}
          {med.conditions.max_duration_days && (
            <div className="bg-white/70 rounded-lg p-2 border border-gray-200">
              <span className="text-xs text-gray-500 block">Max Duration</span>
              <span className="text-sm font-medium text-gray-900">{med.conditions.max_duration_days} days</span>
            </div>
          )}
          {med.conditions.approval_required_from && (
            <div className="bg-white/70 rounded-lg p-2 border border-gray-200">
              <span className="text-xs text-gray-500 block">Approval Required</span>
              <span className="text-sm font-medium text-gray-900">{med.conditions.approval_required_from}</span>
            </div>
          )}
          {med.conditions.monitoring_requirements && (
            <div className="bg-white/70 rounded-lg p-2 border border-gray-200">
              <span className="text-xs text-gray-500 block">Monitoring</span>
              <span className="text-sm font-medium text-gray-900">{med.conditions.monitoring_requirements}</span>
            </div>
          )}
          {med.conditions.timing_restriction && (
            <div className="bg-white/70 rounded-lg p-2 border border-gray-200 col-span-2">
              <span className="text-xs text-gray-500 block">Timing Restriction</span>
              <span className="text-sm font-medium text-gray-900">{med.conditions.timing_restriction}</span>
            </div>
          )}
          {med.conditions.clinical_scenario && (
            <div className="bg-white/70 rounded-lg p-2 border border-gray-200 col-span-2">
              <span className="text-xs text-gray-500 block">Clinical Scenario</span>
              <span className="text-sm font-medium text-gray-900">{med.conditions.clinical_scenario}</span>
            </div>
          )}
        </div>
      )}

      {/* Rationale */}
      {med.rationale && (
        <div className="mt-3 p-2 bg-white/70 rounded-lg border border-gray-200">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Rationale</span>
          <p className="text-sm text-gray-900">{med.rationale}</p>
        </div>
      )}

      {/* Prohibition period detail */}
      {variant === "prohibited" && med.prohibition_period_detail && (
        <div className="mt-3 p-2 bg-white/70 rounded-lg border border-gray-200">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Prohibition Period Details</span>
          <p className="text-sm text-gray-900">{med.prohibition_period_detail}</p>
        </div>
      )}

      {/* Biomedical Concept */}
      {med.biomedicalConcept && (
        <div className="mt-3 p-2 bg-purple-50 rounded-lg border border-purple-200">
          <span className="text-xs font-medium text-purple-700 uppercase tracking-wider block mb-1">CDISC Biomedical Concept</span>
          <div className="flex flex-wrap gap-2 text-xs">
            {med.biomedicalConcept.code && (
              <span className="bg-white px-2 py-1 rounded border border-purple-200">Code: {med.biomedicalConcept.code}</span>
            )}
            {med.biomedicalConcept.decode && (
              <span className="bg-white px-2 py-1 rounded border border-purple-200">{med.biomedicalConcept.decode}</span>
            )}
          </div>
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
              <SmartDataRender
                data={med}
                onViewSource={onViewSource}
                editable={false}
                excludeFields={["medication_class", "medication_type", "prohibition_reason_detail", "restriction_details", "allowance_details", "specific_drugs", "provenance", "conditions", "rationale", "prohibition_period", "prohibition_period_detail", "biomedicalConcept"]}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function RescueMedicationCard({ med, onViewSource }: { med: any; onViewSource?: (page: number) => void }) {
  const [showAllData, setShowAllData] = useState(false);

  return (
    <div className="bg-gray-50 rounded-xl p-4 border border-gray-200" data-testid={`rescue-med-${med.id}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
            <Heart className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <h4 className="font-semibold text-foreground">{med.medication_name || "Rescue Medication"}</h4>
            {med.medication_class && (
              <p className="text-sm text-muted-foreground">{med.medication_class}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={med.provenance} onViewSource={onViewSource} />
          <button
            onClick={() => setShowAllData(!showAllData)}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
            data-testid={`expand-rescue-med-${med.id}`}
          >
            <ChevronDown className={cn("w-4 h-4 text-gray-500 transition-transform", showAllData && "rotate-180")} />
          </button>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        {med.indication && (
          <div className="text-sm">
            <span className="font-medium text-gray-700">Indication: </span>
            <span className="text-gray-600">{med.indication}</span>
          </div>
        )}
        {med.dosing_instructions && (
          <div className="text-sm">
            <span className="font-medium text-gray-700">Dosing: </span>
            <span className="text-gray-600">{med.dosing_instructions}</span>
          </div>
        )}
        {med.documentation_required !== undefined && (
          <div className="text-sm">
            <span className="font-medium text-gray-700">Documentation Required: </span>
            <span className={cn("px-2 py-0.5 rounded-full text-xs",
              med.documentation_required ? "bg-gray-200 text-gray-700" : "bg-gray-100 text-gray-600"
            )}>
              {med.documentation_required ? "Yes" : "No"}
            </span>
          </div>
        )}
      </div>

      {/* Impact on Endpoints */}
      {med.impact_on_endpoints && (
        <div className="mt-3 p-2 bg-amber-50 rounded-lg border border-amber-200">
          <span className="text-xs font-medium text-amber-700 uppercase tracking-wider block mb-1">Impact on Endpoints</span>
          <p className="text-sm text-gray-900">{med.impact_on_endpoints}</p>
        </div>
      )}

      {/* Biomedical Concept */}
      {med.biomedicalConcept && (
        <div className="mt-3 p-2 bg-purple-50 rounded-lg border border-purple-200">
          <span className="text-xs font-medium text-purple-700 uppercase tracking-wider block mb-1">CDISC Biomedical Concept</span>
          <div className="flex flex-wrap gap-2 text-xs">
            {med.biomedicalConcept.code && (
              <span className="bg-white px-2 py-1 rounded border border-purple-200">Code: {med.biomedicalConcept.code}</span>
            )}
            {med.biomedicalConcept.decode && (
              <span className="bg-white px-2 py-1 rounded border border-purple-200">{med.biomedicalConcept.decode}</span>
            )}
          </div>
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
              <SmartDataRender
                data={med}
                onViewSource={onViewSource}
                editable={false}
                excludeFields={["medication_name", "medication_class", "indication", "dosing_instructions", "documentation_required", "provenance", "impact_on_endpoints", "biomedicalConcept"]}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function VaccinePolicySection({ vaccinePolicy, onViewSource }: { vaccinePolicy: any; onViewSource?: (page: number) => void }) {
  if (!vaccinePolicy) return null;
  
  return (
    <AccordionSection 
      title="Vaccine Policy" 
      icon={Syringe}
      variant="default"
      defaultOpen
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="bg-gray-50 rounded-xl p-4 border border-gray-200 text-center">
            <XCircle className={cn("w-6 h-6 mx-auto mb-2", vaccinePolicy.live_vaccines_prohibited ? "text-gray-700" : "text-gray-400")} />
            <p className="text-sm font-medium text-gray-700">Live Vaccines</p>
            <p className="text-xs text-gray-500">{vaccinePolicy.live_vaccines_prohibited ? "Prohibited" : "Allowed"}</p>
          </div>
          
          {vaccinePolicy.live_vaccine_washout_days && (
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-200 text-center">
              <Clock className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-sm font-medium text-gray-700">Washout Period</p>
              <p className="text-xs text-gray-500">{vaccinePolicy.live_vaccine_washout_days} days</p>
            </div>
          )}
          
          <div className="bg-gray-50 rounded-xl p-4 border border-gray-200 text-center">
            <CheckCircle className={cn("w-6 h-6 mx-auto mb-2", vaccinePolicy.inactivated_vaccines_allowed ? "text-gray-700" : "text-gray-400")} />
            <p className="text-sm font-medium text-gray-700">Inactivated Vaccines</p>
            <p className="text-xs text-gray-500">{vaccinePolicy.inactivated_vaccines_allowed ? "Allowed" : "Not Allowed"}</p>
          </div>
        </div>
        
        {vaccinePolicy.specific_restrictions && vaccinePolicy.specific_restrictions.length > 0 && (
          <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
            <h5 className="font-medium text-sm text-gray-700 mb-2">Specific Restrictions</h5>
            <ul className="space-y-1">
              {vaccinePolicy.specific_restrictions.map((restriction: string, idx: number) => (
                <li key={idx} className="text-sm text-gray-600 flex items-start gap-2">
                  <span className="text-gray-400">•</span>
                  {restriction}
                </li>
              ))}
            </ul>
          </div>
        )}
        
        {vaccinePolicy.provenance && (
          <div className="flex justify-end">
            <ProvenanceChip provenance={vaccinePolicy.provenance} onViewSource={onViewSource} />
          </div>
        )}
      </div>
    </AccordionSection>
  );
}

function OverviewTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const prohibited = data?.prohibited_medications?.length || 0;
  const restricted = data?.restricted_medications?.length || 0;
  const allowed = data?.allowed_medications?.length || 0;
  const interactions = data?.drug_interactions?.length || 0;
  const requirements = data?.required_medications?.length || 0;
  const rescueMeds = data?.rescue_medications || [];
  
  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Layers className="w-5 h-5 text-gray-600" />
            Medication Overview
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <XCircle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{prohibited}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Prohibited</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <AlertTriangle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{restricted}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Restricted</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <CheckCircle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{allowed}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Allowed</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Zap className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{interactions}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Interactions</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Clock className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{requirements}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Required</p>
            </div>
          </div>
        </div>
      </div>
      
      <VaccinePolicySection vaccinePolicy={data.vaccine_policy} onViewSource={onViewSource} />
      
      <HerbalSupplementsSection policy={data.herbal_supplements_policy} onViewSource={onViewSource} />
      
      {rescueMeds && rescueMeds.length > 0 && (
        <AccordionSection 
          title="Rescue Medications" 
          icon={Heart}
          variant="rescue"
          count={rescueMeds.length}
        >
          <div className="space-y-3">
            {Array.isArray(rescueMeds) ? (
              rescueMeds.map((med: any, idx: number) => (
                <RescueMedicationCard key={med.id || idx} med={med} onViewSource={onViewSource} />
              ))
            ) : (
              <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                <p className="text-sm text-gray-700">{String(rescueMeds)}</p>
              </div>
            )}
          </div>
        </AccordionSection>
      )}
    </div>
  );
}

function ProhibitedTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const prohibited = data.prohibited_medications || [];
  const restricted = data.restricted_medications || [];
  
  if (prohibited.length === 0 && restricted.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <XCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No prohibited or restricted medications defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      {prohibited.length > 0 && (
        <AccordionSection 
          title="Prohibited Medications" 
          icon={XCircle} 
          count={prohibited.length}
          defaultOpen
          variant="prohibited"
        >
          <div className="space-y-3">
            {prohibited.map((med: any, idx: number) => (
              <MedicationCard key={med.id || idx} med={med} idx={idx} variant="prohibited" onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
            ))}
          </div>
        </AccordionSection>
      )}

      {restricted.length > 0 && (
        <AccordionSection
          title="Restricted Medications"
          icon={AlertTriangle}
          count={restricted.length}
          defaultOpen
          variant="restricted"
        >
          <div className="space-y-3">
            {restricted.map((med: any, idx: number) => (
              <MedicationCard key={med.id || idx} med={med} idx={idx} variant="restricted" onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
            ))}
          </div>
        </AccordionSection>
      )}
    </div>
  );
}

function AllowedTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const allowed = data.allowed_medications || [];

  if (allowed.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <CheckCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No allowed medications defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {allowed.map((med: any, idx: number) => (
        <MedicationCard key={med.id || idx} med={med} idx={idx} variant="allowed" onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function InteractionCard({ interaction, idx, onViewSource, onFieldUpdate }: { interaction: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [showAllData, setShowAllData] = useState(false);
  const basePath = `domainSections.concomitantMedications.data.drug_interactions.${idx}`;

  const severityColors: Record<string, string> = {
    "Major": "bg-gray-800 text-white",
    "Moderate": "bg-gray-600 text-white",
    "Minor": "bg-gray-400 text-white",
  };

  const interactionType = getStringValue(interaction.interaction_type, "Drug Interaction");
  const severityValue = getStringValue(interaction.severity);
  const clinicalEffect = getStringValue(interaction.clinical_effect);
  const managementValue = getStringValue(interaction.management);
  const managementDetail = getStringValue(interaction.management_detail);

  return (
    <div className="bg-gray-50 rounded-xl p-4 border border-gray-200" data-testid={`interaction-${interaction.id}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
            <Zap className="w-5 h-5 text-gray-600" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="font-semibold text-foreground">
                <EditableText
                  value={interactionType}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.interaction_type.decode`, v) : undefined}
                />
              </h4>
              {severityValue && (
                <span className={cn("text-xs px-2 py-0.5 rounded-full", severityColors[severityValue] || "bg-gray-200 text-gray-700")}>
                  <EditableText
                    value={severityValue}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.severity.decode`, v) : undefined}
                  />
                </span>
              )}
            </div>
            {clinicalEffect && (
              <div className="text-sm text-muted-foreground mt-1">
                <EditableText
                  value={clinicalEffect}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.clinical_effect`, v) : undefined}
                />
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={interaction.provenance} onViewSource={onViewSource} />
          <button
            onClick={() => setShowAllData(!showAllData)}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
            data-testid={`expand-interaction-${interaction.id}`}
          >
            <ChevronDown className={cn("w-4 h-4 text-gray-500 transition-transform", showAllData && "rotate-180")} />
          </button>
        </div>
      </div>

      {/* Affected Drugs */}
      {interaction.affected_drugs && Array.isArray(interaction.affected_drugs) && interaction.affected_drugs.length > 0 && (
        <div className="mt-3">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-2">Affected Drugs</span>
          <div className="flex flex-wrap gap-2">
            {interaction.affected_drugs.map((drug: any, drugIdx: number) => (
              <span key={drugIdx} className="text-xs px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                <EditableText
                  value={getStringValue(drug)}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.affected_drugs.${drugIdx}`, v) : undefined}
                />
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 space-y-2">
        {managementValue && (
          <div className="text-sm">
            <span className="font-medium text-gray-700">Management: </span>
            <span className="text-gray-600">
              <EditableText
                value={managementValue}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.management.decode`, v) : undefined}
              />
            </span>
          </div>
        )}
        {managementDetail && (
          <div className="text-sm">
            <span className="font-medium text-gray-700">Details: </span>
            <span className="text-gray-600">
              <EditableText
                value={managementDetail}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.management_detail`, v) : undefined}
              />
            </span>
          </div>
        )}
      </div>

      {/* Biomedical Concept */}
      {interaction.biomedicalConcept && (
        <div className="mt-3 p-2 bg-purple-50 rounded-lg border border-purple-200">
          <span className="text-xs font-medium text-purple-700 uppercase tracking-wider block mb-1">CDISC Biomedical Concept</span>
          <div className="flex flex-wrap gap-2 text-xs">
            {interaction.biomedicalConcept.code && (
              <span className="bg-white px-2 py-1 rounded border border-purple-200">Code: {interaction.biomedicalConcept.code}</span>
            )}
            {interaction.biomedicalConcept.decode && (
              <span className="bg-white px-2 py-1 rounded border border-purple-200">{interaction.biomedicalConcept.decode}</span>
            )}
          </div>
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
              <SmartDataRender
                data={interaction}
                onViewSource={onViewSource}
                editable={false}
                excludeFields={["interaction_type", "severity", "clinical_effect", "management", "management_detail", "provenance", "affected_drugs", "biomedicalConcept"]}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function InteractionsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const interactions = data.drug_interactions || [];

  if (interactions.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Zap className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No drug interactions defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {interactions.map((interaction: any, idx: number) => (
        <InteractionCard key={interaction.id || idx} interaction={interaction} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function RequiredMedicationCard({ med, idx, onViewSource, onFieldUpdate }: { med: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [showAllData, setShowAllData] = useState(false);
  const basePath = `domainSections.concomitantMedications.data.required_medications.${idx}`;

  return (
    <div className="bg-gray-50 rounded-xl p-4 border border-gray-200" data-testid={`required-med-${med.id}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
            <Clock className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="font-semibold text-foreground">
                <EditableText
                  value={getStringValue(med.medication_name, "Required Medication")}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.medication_name`, v) : undefined}
                />
              </h4>
              {getStringValue(med.requirement_type) && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-gray-200 text-gray-700">
                  <EditableText
                    value={getStringValue(med.requirement_type)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.requirement_type.decode`, v) : undefined}
                  />
                </span>
              )}
            </div>
            {getStringValue(med.medication_class) && (
              <div className="text-sm text-muted-foreground">
                <EditableText
                  value={getStringValue(med.medication_class)}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.medication_class`, v) : undefined}
                />
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={med.provenance} onViewSource={onViewSource} />
          <button
            onClick={() => setShowAllData(!showAllData)}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
            data-testid={`expand-required-med-${med.id}`}
          >
            <ChevronDown className={cn("w-4 h-4 text-gray-500 transition-transform", showAllData && "rotate-180")} />
          </button>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        {getStringValue(med.purpose) && (
          <div className="text-sm">
            <span className="font-medium text-gray-700">Purpose: </span>
            <span className="text-gray-600">
              <EditableText
                value={getStringValue(med.purpose)}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.purpose`, v) : undefined}
              />
            </span>
          </div>
        )}

        {med.timing && typeof med.timing === 'object' && (
          <div className="text-sm">
            <span className="font-medium text-gray-700">Timing: </span>
            <span className="text-gray-600">
              <EditableText
                value={getStringValue(med.timing?.timing_description)}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.timing.timing_description`, v) : undefined}
              />
              {getStringValue(med.timing?.relative_to) && (
                <> (relative to <EditableText
                  value={getStringValue(med.timing.relative_to)}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.timing.relative_to`, v) : undefined}
                />)</>
              )}
            </span>
          </div>
        )}

        {med.dosing && typeof med.dosing === 'object' && (
          <div className="text-sm">
            <span className="font-medium text-gray-700">Dosing: </span>
            <span className="text-gray-600">
              {getStringValue(med.dosing?.dose) && (
                <EditableText
                  value={getStringValue(med.dosing.dose)}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.dosing.dose`, v) : undefined}
                />
              )}
              {getStringValue(med.dosing?.route) && (
                <>, <EditableText
                  value={getStringValue(med.dosing.route)}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.dosing.route`, v) : undefined}
                /></>
              )}
              {getStringValue(med.dosing?.frequency) && (
                <>, <EditableText
                  value={getStringValue(med.dosing.frequency)}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.dosing.frequency`, v) : undefined}
                /></>
              )}
            </span>
          </div>
        )}

        {med.alternatives && Array.isArray(med.alternatives) && med.alternatives.length > 0 && (
          <div className="mt-2">
            <span className="text-sm font-medium text-gray-700">Alternatives: </span>
            <div className="flex flex-wrap gap-2 mt-1">
              {med.alternatives.map((alt: any, altIdx: number) => (
                <span key={altIdx} className="text-xs px-2.5 py-1 rounded-full bg-gray-100 border border-gray-200 text-gray-600">
                  <EditableText
                    value={getStringValue(alt)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.alternatives.${altIdx}`, v) : undefined}
                  />
                </span>
              ))}
            </div>
          </div>
        )}
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
              <SmartDataRender data={med} onViewSource={onViewSource} editable={false} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function RequirementsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const requirements = Array.isArray(data?.required_medications) ? data.required_medications : [];

  if (requirements.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Clock className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No required medications defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {requirements.map((med: any, idx: number) => {
        // Skip invalid medication entries
        if (!med || typeof med !== 'object') return null;
        return (
          <RequiredMedicationCard key={med.id || idx} med={med} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
        );
      })}
    </div>
  );
}

function WashoutCard({ washout, idx, onViewSource, onFieldUpdate }: { washout: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [showAllData, setShowAllData] = useState(false);
  const basePath = `domainSections.concomitantMedications.data.washout_requirements.${idx}`;

  const medicationClass = getStringValue(washout.medication_class, "Washout Requirement");
  const washoutDescription = getStringValue(washout.washout_description);
  const rationale = getStringValue(washout.rationale);
  const appliesTo = getStringValue(washout.applies_to);

  return (
    <div className="bg-gray-50 rounded-xl p-4 border border-gray-200" data-testid={`washout-${washout.id}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
            <Timer className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="font-semibold text-foreground">
                <EditableText
                  value={medicationClass}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.medication_class`, v) : undefined}
                />
              </h4>
              {washout.washout_duration_days && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-gray-200 text-gray-700">
                  <EditableText
                    value={String(washout.washout_duration_days) || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.washout_duration_days`, v) : undefined}
                  /> days
                </span>
              )}
            </div>
            {washoutDescription && (
              <div className="text-sm text-muted-foreground mt-1">
                <EditableText
                  value={washoutDescription}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.washout_description`, v) : undefined}
                />
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={washout.provenance} onViewSource={onViewSource} />
          <button
            onClick={() => setShowAllData(!showAllData)}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
            data-testid={`expand-washout-${washout.id}`}
          >
            <ChevronDown className={cn("w-4 h-4 text-gray-500 transition-transform", showAllData && "rotate-180")} />
          </button>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        {rationale && (
          <div className="text-sm">
            <span className="font-medium text-gray-700">Rationale: </span>
            <span className="text-gray-600">
              <EditableText
                value={rationale}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.rationale`, v) : undefined}
              />
            </span>
          </div>
        )}
        {appliesTo && (
          <div className="text-sm">
            <span className="font-medium text-gray-700">Applies to: </span>
            <span className="text-gray-600">
              <EditableText
                value={appliesTo}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.applies_to.decode`, v) : undefined}
              />
            </span>
          </div>
        )}
        {washout.specific_drugs && Array.isArray(washout.specific_drugs) && washout.specific_drugs.length > 0 && (
          <div className="mt-2">
            <span className="text-sm font-medium text-gray-700">Specific drugs: </span>
            <div className="flex flex-wrap gap-2 mt-1">
              {washout.specific_drugs.map((drug: any, drugIdx: number) => (
                <span key={drugIdx} className="text-xs px-2.5 py-1 rounded-full bg-gray-100 border border-gray-200 text-gray-600">
                  <EditableText
                    value={getStringValue(drug)}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.specific_drugs.${drugIdx}`, v) : undefined}
                  />
                </span>
              ))}
            </div>
          </div>
        )}
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
              <SmartDataRender data={washout} onViewSource={onViewSource} editable={false} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function WashoutTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const washouts = data.washout_requirements || [];

  if (washouts.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Timer className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No washout requirements defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm mb-4">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Timer className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-2">Washout Requirements</h4>
            <p className="text-sm text-gray-700 leading-relaxed">
              Required medication washout periods before study participation or specific study activities.
            </p>
          </div>
        </div>
      </div>

      {washouts.map((washout: any, idx: number) => (
        <WashoutCard key={washout.id || idx} washout={washout} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function HerbalSupplementsSection({ policy, onViewSource }: { policy: any; onViewSource?: (page: number) => void }) {
  if (!policy) return null;
  
  return (
    <AccordionSection 
      title="Herbal Supplements Policy" 
      icon={Leaf}
      variant="default"
    >
      <div className="space-y-4">
        {policy.rationale && (
          <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
            <p className="text-sm text-gray-700">{policy.rationale}</p>
          </div>
        )}
        
        {policy.prohibited_supplements && policy.prohibited_supplements.length > 0 && (
          <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
            <h5 className="font-medium text-sm text-gray-700 mb-2">Prohibited Supplements</h5>
            <div className="flex flex-wrap gap-2">
              {policy.prohibited_supplements.map((supplement: string, idx: number) => (
                <span key={idx} className="text-xs px-2.5 py-1 rounded-full bg-gray-200 text-gray-700 border border-gray-300">
                  {supplement}
                </span>
              ))}
            </div>
          </div>
        )}
        
        {policy.provenance && (
          <div className="flex justify-end">
            <ProvenanceChip provenance={policy.provenance} onViewSource={onViewSource} />
          </div>
        )}
      </div>
    </AccordionSection>
  );
}

function ConcomitantMedsViewContent({ data, onViewSource, onFieldUpdate }: ConcomitantMedsViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  
  
  const prohibited = data.prohibited_medications || [];
  const restricted = data.restricted_medications || [];
  const allowed = data.allowed_medications || [];
  const interactions = data.drug_interactions || [];
  const requirements = data.required_medications || [];
  
  const washouts = data.washout_requirements || [];
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "prohibited", label: "Prohibited", icon: XCircle, count: prohibited.length + restricted.length },
    { id: "allowed", label: "Allowed", icon: CheckCircle, count: allowed.length },
    { id: "interactions", label: "Interactions", icon: Zap, count: interactions.length },
    { id: "requirements", label: "Required", icon: Clock, count: requirements.length },
  ];
  
  if (washouts.length > 0) {
    tabs.push({ id: "washout", label: "Washout", icon: Timer, count: washouts.length });
  }
  
  return (
    <div className="space-y-6" data-testid="concomitant-meds-view">
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
                  activeTab === tab.id
                    ? tab.id === "prohibited" ? "bg-gray-100 text-gray-700" : "bg-gray-100 text-gray-700"
                    : "bg-gray-200 text-gray-600"
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
          {activeTab === "overview" && <OverviewTab data={data} onViewSource={onViewSource} />}
          {activeTab === "prohibited" && <ProhibitedTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "allowed" && <AllowedTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "interactions" && <InteractionsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "requirements" && <RequirementsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "washout" && <WashoutTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function ConcomitantMedsView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: ConcomitantMedsViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Pill className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No medication data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <ConcomitantMedsViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
