import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, ChevronDown, LogOut, UserX, Calendar, CheckCircle, Layers, ClipboardList, Shield, UserMinus, AlertTriangle, Lock, Database } from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { EditableText } from "./EditableValue";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";

interface WithdrawalViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "types" | "consent" | "followup" | "procedures";

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
  const typeCount = data?.discontinuation_types?.length || 0;
  const hasVisit = !!data?.discontinuation_visit;
  return (
    <div className="bg-gradient-to-br from-slate-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="withdrawal-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <LogOut className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Withdrawal Procedures</h3>
          <p className="text-sm text-muted-foreground">Discontinuation types and visit procedures</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><UserX className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Discontinuation Types</span></div>
          <p className="text-2xl font-bold text-gray-900">{typeCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Calendar className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Discontinuation Visit</span></div>
          <p className="text-lg font-bold text-gray-900">{hasVisit ? "Defined" : "N/A"}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const typeCount = data?.discontinuation_types?.length || 0;
  const hasVisit = !!data?.discontinuation_visit;
  
  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Layers className="w-5 h-5 text-gray-600" />
            Withdrawal Overview
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <UserX className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{typeCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Discontinuation Types</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Calendar className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasVisit ? "Defined" : "N/A"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Discontinuation Visit</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function TypeCard({ type, idx, onViewSource, onFieldUpdate }: { type: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [showAllData, setShowAllData] = useState(false);
  const basePath = `domainSections.withdrawalProcedures.data.discontinuation_types.${idx}`;

  return (
    <div className={cn("rounded-xl p-4 border", type.allows_continued_followup ? "bg-gray-50 border-gray-200" : "bg-gray-50 border-gray-200")}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", type.allows_continued_followup ? "bg-gray-100" : "bg-gray-100")}>
            <LogOut className={cn("w-5 h-5", type.allows_continued_followup ? "text-gray-600" : "text-gray-600")} />
          </div>
          <div>
            <EditableText
              value={type.type_name?.decode || type.type_name}
              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.type_name`, v) : undefined}
              className="font-semibold text-foreground"
            />
            <span className={cn("text-xs rounded-full px-2 py-0.5 mt-1 inline-block", type.allows_continued_followup ? "bg-gray-100 text-gray-700" : "bg-gray-100 text-gray-700")}>
              {type.allows_continued_followup ? "Follow-up allowed" : "No follow-up"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={type.provenance} onViewSource={onViewSource} />
          <button
            onClick={() => setShowAllData(!showAllData)}
            className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
            data-testid={`expand-type-${idx}`}
          >
            <motion.div animate={{ rotate: showAllData ? 180 : 0 }} transition={{ duration: 0.2 }}>
              <ChevronDown className="w-4 h-4 text-gray-500" />
            </motion.div>
          </button>
        </div>
      </div>
      {type.definition && (
        <EditableText
          value={type.definition}
          multiline
          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.definition`, v) : undefined}
          className="text-sm text-muted-foreground mt-3"
        />
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
              <SmartDataRender data={type} onViewSource={onViewSource} editable={false} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function TypesTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const types = data.discontinuation_types || [];

  if (types.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <UserX className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No discontinuation types defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {types.map((type: any, idx: number) => (
        <TypeCard key={type.id || idx} type={type} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

// NEW TAB: Consent Withdrawal
function ConsentTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const consent = data?.consent_withdrawal;
  const basePath = "domainSections.withdrawalProcedures.data.consent_withdrawal";

  if (!consent) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No consent withdrawal information defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Right to Withdraw */}
      {consent.right_to_withdraw && (
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-2xl p-5">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center shadow-md">
                <Shield className="w-6 h-6 text-white" />
              </div>
              <div>
                <h4 className="font-bold text-blue-900 text-lg">Right to Withdraw</h4>
              </div>
            </div>
            <ProvenanceChip provenance={consent.provenance} onViewSource={onViewSource} />
          </div>
          <EditableText
            value={consent.right_to_withdraw}
            multiline
            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.right_to_withdraw`, v) : undefined}
            className="text-sm text-blue-800 leading-relaxed"
          />
        </div>
      )}

      {/* Withdrawal Process */}
      {consent.withdrawal_process && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h5 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <ClipboardList className="w-5 h-5 text-gray-600" />
            Withdrawal Process
          </h5>
          <EditableText
            value={consent.withdrawal_process}
            multiline
            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.withdrawal_process`, v) : undefined}
            className="text-sm text-gray-700"
          />
        </div>
      )}

      {/* Data Handling Options */}
      {consent.data_handling_options?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Database className="w-5 h-5 text-gray-600" />
              Data Handling Options ({consent.data_handling_options.length})
            </h5>
          </div>
          <div className="divide-y divide-gray-100">
            {consent.data_handling_options.map((opt: any, idx: number) => (
              <div key={opt.option || idx} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="inline-flex items-center px-2 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded">
                      {opt.option?.decode || opt.option}
                    </span>
                    {opt.description && <p className="text-sm text-gray-700 mt-2">{opt.description}</p>}
                    {opt.conditions && <p className="text-xs text-muted-foreground mt-1">Conditions: {opt.conditions}</p>}
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

// NEW TAB: Follow-up & Lost to Follow-up
function FollowupTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const hasLostToFollowup = !!data?.lost_to_followup;
  const hasEarlyTermination = !!data?.early_termination_criteria;
  const hasReplacement = !!data?.replacement_subject_criteria;
  const hasDeviation = !!data?.protocol_deviation_handling;

  if (!hasLostToFollowup && !hasEarlyTermination && !hasReplacement && !hasDeviation) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <UserMinus className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No follow-up procedures defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Lost to Follow-up */}
      {data.lost_to_followup && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
          <div className="flex items-start justify-between mb-3">
            <h5 className="font-semibold text-amber-900 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
              Lost to Follow-up Procedures
            </h5>
            <ProvenanceChip provenance={data.lost_to_followup.provenance} onViewSource={onViewSource} />
          </div>
          <SmartDataRender data={data.lost_to_followup} onViewSource={onViewSource} excludeFields={["provenance"]} />
        </div>
      )}

      {/* Early Termination Criteria */}
      {data.early_termination_criteria && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5">
          <div className="flex items-start justify-between mb-3">
            <h5 className="font-semibold text-red-900 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-600" />
              Early Termination Criteria
            </h5>
            <ProvenanceChip provenance={data.early_termination_criteria.provenance} onViewSource={onViewSource} />
          </div>
          <SmartDataRender data={data.early_termination_criteria} onViewSource={onViewSource} excludeFields={["provenance"]} />
        </div>
      )}

      {/* Replacement Subject Criteria */}
      {data.replacement_subject_criteria && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-start justify-between mb-3">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <UserX className="w-5 h-5 text-gray-600" />
              Replacement Subject Criteria
            </h5>
            <ProvenanceChip provenance={data.replacement_subject_criteria.provenance} onViewSource={onViewSource} />
          </div>
          <SmartDataRender data={data.replacement_subject_criteria} onViewSource={onViewSource} excludeFields={["provenance"]} />
        </div>
      )}

      {/* Protocol Deviation Handling */}
      {data.protocol_deviation_handling && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-start justify-between mb-3">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <ClipboardList className="w-5 h-5 text-gray-600" />
              Protocol Deviation Handling
            </h5>
            <ProvenanceChip provenance={data.protocol_deviation_handling.provenance} onViewSource={onViewSource} />
          </div>
          <SmartDataRender data={data.protocol_deviation_handling} onViewSource={onViewSource} excludeFields={["provenance"]} />
        </div>
      )}
    </div>
  );
}

function ProceduresTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  if (!data.discontinuation_visit) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Calendar className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No discontinuation visit procedures defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Calendar className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-3">Discontinuation Visit</h4>
            <SmartDataRender data={data.discontinuation_visit} onViewSource={onViewSource} />
          </div>
        </div>
      </div>
    </div>
  );
}

function WithdrawalViewContent({ data, onViewSource, onFieldUpdate }: WithdrawalViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  
  
  const types = data.discontinuation_types || [];
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "types", label: "Types", icon: UserX, count: types.length },
    { id: "consent", label: "Consent", icon: Shield },
    { id: "followup", label: "Follow-up", icon: UserMinus },
    { id: "procedures", label: "Procedures", icon: Calendar },
  ];
  
  return (
    <div className="space-y-6" data-testid="withdrawal-view">
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
          {activeTab === "types" && <TypesTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "consent" && <ConsentTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "followup" && <FollowupTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "procedures" && <ProceduresTab data={data} onViewSource={onViewSource} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function WithdrawalView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: WithdrawalViewProps) {
  if (!data) {
    return (<div className="text-center py-12 text-muted-foreground"><LogOut className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No withdrawal data available</p></div>);
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <WithdrawalViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
