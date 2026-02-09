import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, ChevronDown, Shield, AlertTriangle, Activity,
  Clock, CheckCircle, XCircle, Layers, Syringe, Gauge,
  StopCircle, TrendingDown, Heart, Hash, BarChart3,
  ArrowUpDown, Percent, Minus, RefreshCw, AlertCircle
} from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";
import { EditableText } from "./EditableValue";

interface SafetyDecisionPointsViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "decision_points" | "categories" | "stopping_rules" | "dose_levels" | "organ_adjustments";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function SummaryHeader({ data }: { data: any }) {
  const decisionPointsCount = data?.decision_points?.length || 0;
  const totalRulesCount = data?.decision_points?.reduce((acc: number, dp: any) =>
    acc + (dp.decision_rules?.length || 0), 0) || 0;
  const categoriesCount = data?.discovered_categories?.length || 0;
  const stoppingRulesCount = data?.stopping_rules_summary?.stopping_conditions?.length || 0;
  const doseLevelsCount = data?.dose_modification_levels?.levels?.length || 0;
  const organAdjustmentsCount = data?.organ_specific_adjustments?.length || 0;

  return (
    <div className="bg-gradient-to-br from-slate-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="safety-decisions-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Safety Decision Points</h3>
          <p className="text-sm text-muted-foreground">Dose modification guidelines</p>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-decision-points">
          <div className="flex items-center gap-2 mb-1">
            <Gauge className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Decision Points</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{decisionPointsCount}</p>
        </div>

        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-total-rules">
          <div className="flex items-center gap-2 mb-1">
            <Layers className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total Rules</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{totalRulesCount}</p>
        </div>

        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-categories">
          <div className="flex items-center gap-2 mb-1">
            <BarChart3 className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Categories</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{categoriesCount}</p>
        </div>

        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-stopping-rules">
          <div className="flex items-center gap-2 mb-1">
            <StopCircle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Stopping Rules</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{stoppingRulesCount}</p>
        </div>

        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-dose-levels">
          <div className="flex items-center gap-2 mb-1">
            <TrendingDown className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Dose Levels</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{doseLevelsCount}</p>
        </div>

        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-organ-adjustments">
          <div className="flex items-center gap-2 mb-1">
            <Heart className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Organ Adj.</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{organAdjustmentsCount}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const decisionPointsCount = data?.decision_points?.length || 0;
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Shield className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Safety Decision Framework</h4>
              <ProvenanceChip provenance={data?.provenance} onViewSource={onViewSource} />
            </div>
            <p className="text-sm text-gray-700 leading-relaxed">
              This section defines the dose modification guidelines and decision rules for managing adverse events and toxicities during the trial.
            </p>
          </div>
        </div>
      </div>
      
      {data?.decision_points && data.decision_points.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h4 className="font-semibold text-foreground flex items-center gap-2">
              <Activity className="w-5 h-5 text-gray-600" />
              Decision Points Summary
            </h4>
          </div>
          <div className="p-5 space-y-3">
            {data.decision_points.map((dp: any, idx: number) => (
              <div key={dp.id || idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-100">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
                    <AlertTriangle className="w-4 h-4 text-gray-900" />
                  </div>
                  <div>
                    <div className="text-sm font-medium text-foreground">
                      <EditableText
                        value={dp.parameter_name || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`domainSections.safetyDecisionPoints.data.decision_points.${idx}.parameter_name`, v) : undefined}
                      />
                    </div>
                    <div className="text-xs text-muted-foreground">
                      <EditableText
                        value={dp.parameter_category || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`domainSections.safetyDecisionPoints.data.decision_points.${idx}.parameter_category`, v) : undefined}
                      />
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-gray-900 bg-gray-50 px-2 py-1 rounded">
                    {dp.decision_rules?.length || 0} rules
                  </span>
                  <ProvenanceChip provenance={dp.provenance} onViewSource={onViewSource} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function getRuleTypeColor(ruleType: string) {
  switch (ruleType) {
    case "dose_hold":
      return { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: Clock };
    case "dose_reduce":
      return { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: ChevronDown };
    case "dose_discontinue":
      return { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: XCircle };
    case "dose_modify":
      return { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: Activity };
    case "dose_hold_reduce":
      return { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: Syringe };
    default:
      return { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: Activity };
  }
}

function formatRuleType(ruleType: string) {
  return ruleType?.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase()) || "Unknown";
}

function DecisionPointCard({ decisionPoint, idx, onViewSource, onFieldUpdate }: { decisionPoint: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showAllData, setShowAllData] = useState(false);
  const basePath = `domainSections.safetyDecisionPoints.data.decision_points.${idx}`;
  
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm" data-testid={`decision-point-${decisionPoint.id}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-5 flex items-center justify-between hover:bg-gray-50 transition-colors"
        data-testid={`toggle-decision-point-${decisionPoint.id}`}
      >
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
            <AlertTriangle className="w-5 h-5 text-white" />
          </div>
          <div className="text-left">
            <h4 className="font-semibold text-foreground">{decisionPoint.parameter_name}</h4>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs text-muted-foreground">{decisionPoint.parameter_category}</span>
              {decisionPoint.measurement_type && (
                <>
                  <span className="text-xs text-muted-foreground">•</span>
                  <span className="text-xs text-muted-foreground">{decisionPoint.measurement_type}</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-gray-900 bg-gray-50 px-2 py-1 rounded">
            {decisionPoint.decision_rules?.length || 0} rules
          </span>
          <ProvenanceChip provenance={decisionPoint.provenance} onViewSource={onViewSource} />
          <ChevronDown className={cn("w-5 h-5 text-muted-foreground transition-transform", isExpanded && "rotate-180")} />
        </div>
      </button>
      
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-t border-gray-100 p-5 space-y-4 bg-gray-50/50">
              {decisionPoint.monitoring_requirements && (
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                  <h5 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                    <Clock className="w-4 h-4" />
                    Monitoring Requirements
                  </h5>
                  <div className="space-y-1">
                    {decisionPoint.monitoring_requirements.method && (
                      <div className="text-sm text-gray-700">
                        <span className="font-medium">Method:</span>{" "}
                        <EditableText
                          value={decisionPoint.monitoring_requirements.method || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.monitoring_requirements.method`, v) : undefined}
                        />
                      </div>
                    )}
                    {decisionPoint.monitoring_requirements.frequency && (
                      <div className="text-sm text-gray-700">
                        <span className="font-medium">Frequency:</span>{" "}
                        <EditableText
                          value={decisionPoint.monitoring_requirements.frequency || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.monitoring_requirements.frequency`, v) : undefined}
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}

              {decisionPoint.decision_rules && decisionPoint.decision_rules.length > 0 && (
                <div className="space-y-3">
                  <h5 className="text-sm font-semibold text-foreground">Decision Rules</h5>
                  {decisionPoint.decision_rules.map((rule: any, ruleIdx: number) => {
                    const colors = getRuleTypeColor(rule.rule_type);
                    const IconComponent = colors.icon;
                    const rulePath = `${basePath}.decision_rules.${ruleIdx}`;

                    return (
                      <div
                        key={rule.rule_id || ruleIdx}
                        className={cn("rounded-lg p-4 border", colors.bg, colors.border)}
                        data-testid={`rule-${rule.rule_id}`}
                      >
                        <div className="flex items-start justify-between gap-3 mb-3">
                          <div className="flex items-center gap-2">
                            <IconComponent className={cn("w-4 h-4", colors.text)} />
                            <span className={cn("text-sm font-semibold", colors.text)}>
                              <EditableText
                                value={rule.rule_type || ""}
                                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${rulePath}.rule_type`, v) : undefined}
                              />
                            </span>
                            {rule.conditions?.grade && (
                              <span className={cn("text-xs font-medium px-2 py-0.5 rounded", colors.bg, colors.text, "border", colors.border)}>
                                Grade <EditableText
                                  value={rule.conditions.grade || ""}
                                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${rulePath}.conditions.grade`, v) : undefined}
                                />
                              </span>
                            )}
                          </div>
                          <ProvenanceChip provenance={rule.provenance} onViewSource={onViewSource} />
                        </div>

                        {rule.rule_description && (
                          <div className={cn("text-sm mb-3", colors.text)}>
                            <EditableText
                              value={rule.rule_description || ""}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${rulePath}.rule_description`, v) : undefined}
                            />
                          </div>
                        )}

                        {rule.actions && rule.actions.length > 0 && (
                          <div className="space-y-2 mt-3">
                            {rule.actions.map((action: any, actionIdx: number) => (
                              <div key={actionIdx} className="flex items-start gap-2">
                                <CheckCircle className={cn("w-4 h-4 mt-0.5 flex-shrink-0", colors.text)} />
                                <div>
                                  <span className={cn("text-xs font-medium uppercase", colors.text)}>
                                    <EditableText
                                      value={action.action_type?.replace(/_/g, " ") || ""}
                                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${rulePath}.actions.${actionIdx}.action_type`, v) : undefined}
                                    />
                                  </span>
                                  {action.action_description && (
                                    <div className={cn("text-sm mt-0.5", colors.text.replace("700", "800"))}>
                                      <EditableText
                                        value={action.action_description || ""}
                                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${rulePath}.actions.${actionIdx}.action_description`, v) : undefined}
                                      />
                                    </div>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        {rule.recovery_criteria && (rule.recovery_criteria.timeframe || rule.recovery_criteria.anc_required) && (
                          <div className="mt-3 pt-3 border-t border-dashed" style={{ borderColor: "inherit" }}>
                            <p className={cn("text-xs font-medium", colors.text)}>Recovery Criteria:</p>
                            {rule.recovery_criteria.anc_required && (
                              <div className={cn("text-sm", colors.text)}>
                                Required:{" "}
                                <EditableText
                                  value={rule.recovery_criteria.anc_required || ""}
                                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${rulePath}.recovery_criteria.anc_required`, v) : undefined}
                                />
                              </div>
                            )}
                            {rule.recovery_criteria.timeframe && (
                              <div className={cn("text-sm", colors.text)}>
                                Timeframe:{" "}
                                <EditableText
                                  value={rule.recovery_criteria.timeframe || ""}
                                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${rulePath}.recovery_criteria.timeframe`, v) : undefined}
                                />
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              
              <div className="mt-4 pt-4 border-t border-gray-200">
                <button
                  onClick={() => setShowAllData(!showAllData)}
                  className="flex items-center gap-2 text-xs font-medium text-gray-600 hover:text-gray-900 transition-colors"
                  data-testid={`toggle-all-data-${decisionPoint.id}`}
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
                      <div className="mt-3 p-4 bg-white rounded-lg border border-gray-200">
                        <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Complete Data</div>
                        <SmartDataRender data={decisionPoint} onViewSource={onViewSource} editable={false} />
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

function DecisionPointsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!data?.decision_points || data.decision_points.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No decision points defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {data.decision_points.map((dp: any, idx: number) => (
        <DecisionPointCard key={dp.id || idx} decisionPoint={dp} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

// NEW TAB: Categories Tab - discovered_categories[]
function CategoriesTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const categories = data?.discovered_categories || [];
  const basePath = "domainSections.safetyDecisionPoints.data.discovered_categories";

  if (categories.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No safety parameter categories discovered</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <p className="text-sm text-blue-700">
          <strong>Discovered Categories:</strong> {categories.length} safety parameter categories identified in this protocol.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {categories.map((category: any, idx: number) => (
          <div
            key={category.category_id || idx}
            className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm"
          >
            <div className="flex items-start justify-between gap-3 mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-indigo-100 flex items-center justify-center">
                  <BarChart3 className="w-5 h-5 text-indigo-600" />
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900">
                    <EditableText
                      value={category.category_name || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.category_name`, v) : undefined}
                    />
                  </h4>
                  {category.category_id && (
                    <p className="text-xs text-muted-foreground">
                      <EditableText
                        value={category.category_id || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.category_id`, v) : undefined}
                      />
                    </p>
                  )}
                </div>
              </div>
              <ProvenanceChip provenance={category.provenance} onViewSource={onViewSource} />
            </div>

            {category.category_description && (
              <div className="text-sm text-gray-700 mb-3">
                <EditableText
                  value={category.category_description || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.category_description`, v) : undefined}
                />
              </div>
            )}

            {category.parameters_count !== undefined && category.parameters_count !== null && (
              <div className="flex items-center gap-2 p-2 bg-gray-50 rounded-lg">
                <Hash className="w-4 h-4 text-gray-500" />
                <span className="text-sm text-gray-700">
                  <strong>{category.parameters_count}</strong> parameters
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// NEW TAB: Stopping Rules Tab - stopping_rules_summary
function StoppingRulesTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const summary = data?.stopping_rules_summary;
  const basePath = "domainSections.safetyDecisionPoints.data.stopping_rules_summary";

  if (!summary) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <StopCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No stopping rules defined</p>
      </div>
    );
  }

  const conditions = summary.stopping_conditions || [];

  return (
    <div className="space-y-6">
      {/* Summary Card */}
      <div className="bg-red-50 border border-red-200 rounded-xl p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-red-100 flex items-center justify-center">
              <StopCircle className="w-6 h-6 text-red-600" />
            </div>
            <div>
              <h4 className="font-bold text-red-900">Stopping Rules Summary</h4>
              <p className="text-sm text-red-700">
                {summary.total_permanent_stopping_conditions !== undefined
                  ? `${summary.total_permanent_stopping_conditions} permanent stopping conditions`
                  : `${conditions.length} stopping conditions defined`}
              </p>
            </div>
          </div>
          <ProvenanceChip provenance={summary.provenance} onViewSource={onViewSource} />
        </div>
      </div>

      {/* Stopping Conditions List */}
      {conditions.length > 0 && (
        <div className="space-y-3">
          <h5 className="font-semibold text-foreground flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-red-600" />
            Stopping Conditions
          </h5>

          {conditions.map((condition: any, idx: number) => (
            <div
              key={condition.condition_id || idx}
              className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center text-sm font-bold text-red-700">
                    {idx + 1}
                  </div>
                  <div>
                    {condition.condition_type && (
                      <span className="inline-block px-2 py-1 text-xs font-medium bg-red-100 text-red-700 rounded">
                        <EditableText
                          value={condition.condition_type || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.stopping_conditions.${idx}.condition_type`, v) : undefined}
                        />
                      </span>
                    )}
                    {condition.condition_id && (
                      <span className="text-xs text-muted-foreground ml-2">
                        ID: <EditableText
                          value={condition.condition_id || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.stopping_conditions.${idx}.condition_id`, v) : undefined}
                        />
                      </span>
                    )}
                  </div>
                </div>
                <ProvenanceChip provenance={condition.provenance} onViewSource={onViewSource} />
              </div>

              {condition.description && (
                <div className="text-sm text-gray-700 mb-3">
                  <EditableText
                    value={condition.description || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.stopping_conditions.${idx}.description`, v) : undefined}
                  />
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {condition.trigger_threshold && (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-1">
                      <AlertTriangle className="w-4 h-4 text-amber-600" />
                      <span className="text-xs font-medium text-amber-800 uppercase">Trigger Threshold</span>
                    </div>
                    <div className="text-sm text-amber-900">
                      <EditableText
                        value={condition.trigger_threshold || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.stopping_conditions.${idx}.trigger_threshold`, v) : undefined}
                      />
                    </div>
                  </div>
                )}

                {condition.action && (
                  <div className="p-3 bg-gray-50 border border-gray-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-1">
                      <XCircle className="w-4 h-4 text-gray-600" />
                      <span className="text-xs font-medium text-gray-700 uppercase">Action</span>
                    </div>
                    <div className="text-sm text-gray-800">
                      <EditableText
                        value={condition.action || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.stopping_conditions.${idx}.action`, v) : undefined}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Fallback for no conditions */}
      {conditions.length === 0 && (
        <div className="text-center py-8 text-muted-foreground">
          <p>No individual stopping conditions specified</p>
        </div>
      )}
    </div>
  );
}

// NEW TAB: Dose Levels Tab - dose_modification_levels
function DoseLevelsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const doseInfo = data?.dose_modification_levels;
  const basePath = "domainSections.safetyDecisionPoints.data.dose_modification_levels";

  if (!doseInfo) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <TrendingDown className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No dose modification levels defined</p>
      </div>
    );
  }

  const levels = doseInfo.levels || [];

  return (
    <div className="space-y-6">
      {/* Overview Card */}
      <div className="bg-purple-50 border border-purple-200 rounded-xl p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-purple-100 flex items-center justify-center">
              <TrendingDown className="w-6 h-6 text-purple-600" />
            </div>
            <div>
              <h4 className="font-bold text-purple-900">Dose Modification Levels</h4>
              <div className="flex items-center gap-2 mt-1">
                {doseInfo.has_defined_levels !== undefined && (
                  <span className={cn(
                    "inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded",
                    doseInfo.has_defined_levels
                      ? "bg-green-100 text-green-700"
                      : "bg-gray-100 text-gray-600"
                  )}>
                    {doseInfo.has_defined_levels ? (
                      <>
                        <CheckCircle className="w-3 h-3" />
                        Defined Levels
                      </>
                    ) : (
                      <>
                        <Minus className="w-3 h-3" />
                        No Defined Levels
                      </>
                    )}
                  </span>
                )}
                {doseInfo.re_escalation_allowed !== undefined && (
                  <span className={cn(
                    "inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded",
                    doseInfo.re_escalation_allowed
                      ? "bg-blue-100 text-blue-700"
                      : "bg-gray-100 text-gray-600"
                  )}>
                    <RefreshCw className="w-3 h-3" />
                    Re-escalation {doseInfo.re_escalation_allowed ? "Allowed" : "Not Allowed"}
                  </span>
                )}
              </div>
            </div>
          </div>
          <ProvenanceChip provenance={doseInfo.provenance} onViewSource={onViewSource} />
        </div>

        {/* Minimum Dose & Re-escalation Criteria */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          {doseInfo.minimum_dose && (
            <div className="p-3 bg-white rounded-lg border border-purple-200">
              <div className="flex items-center gap-2 mb-1">
                <ArrowUpDown className="w-4 h-4 text-purple-600" />
                <span className="text-xs font-medium text-purple-700 uppercase">Minimum Dose</span>
              </div>
              <div className="text-sm text-purple-900">
                <EditableText
                  value={doseInfo.minimum_dose || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.minimum_dose`, v) : undefined}
                />
              </div>
            </div>
          )}

          {doseInfo.re_escalation_criteria && (
            <div className="p-3 bg-white rounded-lg border border-purple-200">
              <div className="flex items-center gap-2 mb-1">
                <RefreshCw className="w-4 h-4 text-purple-600" />
                <span className="text-xs font-medium text-purple-700 uppercase">Re-escalation Criteria</span>
              </div>
              <div className="text-sm text-purple-900">
                <EditableText
                  value={doseInfo.re_escalation_criteria || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.re_escalation_criteria`, v) : undefined}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Dose Levels Table */}
      {levels.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100">
            <h5 className="font-semibold text-foreground flex items-center gap-2">
              <Layers className="w-5 h-5 text-gray-600" />
              Dose Levels ({levels.length})
            </h5>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Level</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Name</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Dose %</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Absolute Dose</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {levels.map((level: any, idx: number) => (
                  <tr key={level.level_id || idx} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-purple-100 text-purple-700 font-semibold text-sm">
                        <EditableText
                          value={level.level_id || String(idx + 1)}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.levels.${idx}.level_id`, v) : undefined}
                        />
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {level.level_name ? (
                        <EditableText
                          value={level.level_name || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.levels.${idx}.level_name`, v) : undefined}
                        />
                      ) : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      {level.dose_percentage !== undefined && level.dose_percentage !== null ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 text-sm font-medium bg-purple-100 text-purple-700 rounded">
                          <Percent className="w-3 h-3" />
                          <EditableText
                            value={String(level.dose_percentage || "")}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.levels.${idx}.dose_percentage`, v) : undefined}
                          />%
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {level.absolute_dose ? (
                        <EditableText
                          value={level.absolute_dose || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.levels.${idx}.absolute_dose`, v) : undefined}
                        />
                      ) : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <ProvenanceChip provenance={level.provenance} onViewSource={onViewSource} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Fallback */}
      {levels.length === 0 && (
        <div className="text-center py-8 text-muted-foreground">
          <p>No individual dose levels specified</p>
        </div>
      )}
    </div>
  );
}

// NEW TAB: Organ Adjustments Tab - organ_specific_adjustments[]
function OrganAdjustmentsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const adjustments = data?.organ_specific_adjustments || [];
  const basePath = "domainSections.safetyDecisionPoints.data.organ_specific_adjustments";

  if (adjustments.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Heart className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No organ-specific adjustments defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-teal-50 border border-teal-200 rounded-lg p-4">
        <p className="text-sm text-teal-700">
          <strong>Organ-Specific Adjustments:</strong> {adjustments.length} organ/system-specific dose adjustments identified.
        </p>
      </div>

      <div className="space-y-4">
        {adjustments.map((adjustment: any, idx: number) => (
          <div
            key={adjustment.id || idx}
            className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm"
          >
            <div className="p-5">
              <div className="flex items-start justify-between gap-3 mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-teal-100 flex items-center justify-center">
                    <Heart className="w-6 h-6 text-teal-600" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-gray-900">
                      <EditableText
                        value={adjustment.organ_system || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.organ_system`, v) : undefined}
                      />
                    </h4>
                    {adjustment.organ_system_detail && (
                      <div className="text-sm text-muted-foreground">
                        <EditableText
                          value={adjustment.organ_system_detail || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.organ_system_detail`, v) : undefined}
                        />
                      </div>
                    )}
                    {adjustment.id && (
                      <p className="text-xs text-muted-foreground">ID: {adjustment.id}</p>
                    )}
                  </div>
                </div>
                <ProvenanceChip provenance={adjustment.provenance} onViewSource={onViewSource} />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {adjustment.adjustment_trigger && (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className="w-4 h-4 text-amber-600" />
                      <span className="text-xs font-semibold text-amber-800 uppercase">Trigger</span>
                    </div>
                    <div className="text-sm text-amber-900">
                      <EditableText
                        value={adjustment.adjustment_trigger || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.adjustment_trigger`, v) : undefined}
                      />
                    </div>
                  </div>
                )}

                {adjustment.adjustment_action && (
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <Activity className="w-4 h-4 text-blue-600" />
                      <span className="text-xs font-semibold text-blue-800 uppercase">Action</span>
                    </div>
                    <div className="text-sm text-blue-900">
                      <EditableText
                        value={adjustment.adjustment_action || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.adjustment_action`, v) : undefined}
                      />
                    </div>
                  </div>
                )}

                {adjustment.monitoring_requirements && (
                  <div className="p-3 bg-gray-50 border border-gray-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <Clock className="w-4 h-4 text-gray-600" />
                      <span className="text-xs font-semibold text-gray-700 uppercase">Monitoring</span>
                    </div>
                    <div className="text-sm text-gray-800">
                      <EditableText
                        value={adjustment.monitoring_requirements || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.monitoring_requirements`, v) : undefined}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SafetyDecisionPointsViewContent({ data, onViewSource, onFieldUpdate }: SafetyDecisionPointsViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "decision_points", label: "Decision Points", icon: AlertTriangle, count: data?.decision_points?.length },
    { id: "categories", label: "Categories", icon: BarChart3, count: data?.discovered_categories?.length },
    { id: "stopping_rules", label: "Stopping Rules", icon: StopCircle, count: data?.stopping_rules_summary?.stopping_conditions?.length },
    { id: "dose_levels", label: "Dose Levels", icon: TrendingDown, count: data?.dose_modification_levels?.levels?.length },
    { id: "organ_adjustments", label: "Organ Adj.", icon: Heart, count: data?.organ_specific_adjustments?.length },
  ];
  
return (
    <div className="space-y-6" data-testid="safety-decision-points-view">
      <SummaryHeader data={data} />
      
      <div className="flex items-center gap-2 border-b border-gray-200 pb-1 overflow-x-auto">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex-shrink-0 whitespace-nowrap flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t-lg transition-colors",
                activeTab === tab.id
                  ? "bg-white border border-b-0 border-gray-200 text-foreground -mb-px"
                  : "text-muted-foreground hover:text-foreground hover:bg-gray-50"
              )}
              data-testid={`tab-${tab.id}`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
              {tab.count !== undefined && (
                <span className={cn(
                  "text-xs px-1.5 py-0.5 rounded",
                  activeTab === tab.id ? "bg-gray-100 text-gray-700" : "bg-gray-100 text-gray-600"
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
          {activeTab === "decision_points" && <DecisionPointsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "categories" && <CategoriesTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "stopping_rules" && <StoppingRulesTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "dose_levels" && <DoseLevelsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "organ_adjustments" && <OrganAdjustmentsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function SafetyDecisionPointsView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: SafetyDecisionPointsViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground" data-testid="no-safety-decisions">
        <Shield className="w-16 h-16 mx-auto mb-4 opacity-30" />
        <p className="text-lg font-medium">No safety decision points data available</p>
        <p className="text-sm mt-1">Safety decision guidelines will appear here once extracted.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <SafetyDecisionPointsViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
