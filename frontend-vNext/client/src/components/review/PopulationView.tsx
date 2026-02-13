import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { useCoverageRegistry } from "@/lib/coverage-registry";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, ChevronDown, Users, Heart, Calendar, Activity,
  CheckCircle, XCircle, AlertTriangle, UserCheck, Target, Layers, BarChart3
} from "lucide-react";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";
import { EditableText, EditableNumber } from "./EditableValue";

interface PopulationViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "inclusion" | "exclusion";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function formatTargetDisease(targetDisease: any): string {
  if (!targetDisease) return "Not specified";
  if (typeof targetDisease === 'string') return targetDisease;
  if (typeof targetDisease === 'object') {
    const name = targetDisease.name || "";
    const stage = targetDisease.stage || "";
    return name ? (stage ? `${name} (${stage})` : name) : "Not specified";
  }
  return "Not specified";
}

function formatAgeRange(ageRange: any): string {
  if (!ageRange) return "Not specified";
  if (typeof ageRange === 'string') return ageRange;
  if (typeof ageRange === 'object') {
    const minAge = ageRange.minAge ? `${ageRange.minAge}` : "0";
    const unit = ageRange.unit || "years";
    if (ageRange.maxAgeNoLimit) {
      return `${minAge}+ ${unit}`;
    }
    const maxAge = ageRange.maxAge ? `${ageRange.maxAge}` : null;
    return maxAge ? `${minAge}-${maxAge} ${unit}` : `${minAge}+ ${unit}`;
  }
  return "Not specified";
}

function formatSex(sex: any): string {
  if (!sex) return "Not specified";
  if (typeof sex === 'string') return sex;
  if (Array.isArray(sex)) return sex.join(", ");
  if (typeof sex === 'object') {
    if (sex.allowed && Array.isArray(sex.allowed)) {
      return sex.allowed.map((s: any) => typeof s === 'string' ? s : s.decode || s.value || String(s)).join(", ");
    }
  }
  return "Not specified";
}

function formatPerformanceStatus(ps: any): string {
  if (!ps) return "Not specified";
  if (typeof ps === 'string') return ps;
  if (typeof ps === 'object') {
    const scale = ps.scale || ps.scaleName || "";
    const values = ps.allowedValues;
    if (Array.isArray(values) && values.length > 0) {
      return scale ? `${scale}: ${values.join(", ")}` : values.join(", ");
    }
    if (scale) return scale;
  }
  return "Not specified";
}

function SummaryHeader({ data }: { data: any }) {
  const inclusionCount = data?.keyInclusionSummary?.values?.length || 0;
  const exclusionCount = data?.keyExclusionSummary?.values?.length || 0;
  
  return (
    <div className="bg-gradient-to-br from-slate-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="population-summary-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <Users className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Study Population</h3>
          <p className="text-sm text-muted-foreground">Eligibility criteria and demographics</p>
        </div>
      </div>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-target-disease">
          <div className="flex items-center gap-2 mb-1">
            <Target className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Target</span>
          </div>
          <p className="text-sm font-bold text-gray-900 line-clamp-2">{formatTargetDisease(data?.targetDisease)}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-age-range">
          <div className="flex items-center gap-2 mb-1">
            <Calendar className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Age Range</span>
          </div>
          <p className="text-lg font-bold text-gray-900">{formatAgeRange(data?.ageRange)}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-inclusion">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Inclusion</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{inclusionCount}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-exclusion">
          <div className="flex items-center gap-2 mb-1">
            <XCircle className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Exclusion</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{exclusionCount}</p>
        </div>
      </div>
    </div>
  );
}

function CriteriaList({
  items,
  type,
  provenance,
  onViewSource,
  onFieldUpdate
}: {
  items: string[];
  type: "inclusion" | "exclusion";
  provenance?: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
}) {
  const config = type === "inclusion"
    ? { icon: CheckCircle, bg: "bg-gray-50", iconColor: "text-gray-600", border: "border-gray-200" }
    : { icon: XCircle, bg: "bg-gray-50", iconColor: "text-gray-600", border: "border-gray-200" };

  const basePath = type === "inclusion"
    ? "study.studyPopulation.keyInclusionSummary.values"
    : "study.studyPopulation.keyExclusionSummary.values";

  return (
    <div className="space-y-2">
      {items.map((item, idx) => (
        <div key={idx} className={cn("flex items-start gap-3 p-3 rounded-lg", config.bg, "border", config.border)}>
          <config.icon className={cn("w-4 h-4 mt-0.5 flex-shrink-0", config.iconColor)} />
          <div className="text-sm text-foreground flex-1">
            <EditableText
              value={item}
              multiline
              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}`, v) : undefined}
            />
          </div>
        </div>
      ))}
      {provenance && (
        <div className="flex justify-end pt-2">
          <ProvenanceChip provenance={provenance} onViewSource={onViewSource} />
        </div>
      )}
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const inclusionCount = data?.keyInclusionSummary?.values?.length || 0;
  const exclusionCount = data?.keyExclusionSummary?.values?.length || 0;
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Users className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-2">Population Overview</h4>
            <p className="text-sm text-gray-700 leading-relaxed">
              This section defines the target population for the clinical trial, including eligibility criteria for inclusion and exclusion of participants.
            </p>
          </div>
        </div>
      </div>
      
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-gray-600" />
            Population Metrics at a Glance
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Target className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-sm font-bold text-gray-900 line-clamp-2">{formatTargetDisease(data?.targetDisease)}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Target Disease</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Calendar className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{formatAgeRange(data?.ageRange)}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Age Range</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <CheckCircle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{inclusionCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Inclusion Criteria</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <XCircle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{exclusionCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Exclusion Criteria</p>
            </div>
          </div>
        </div>
      </div>
      
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Heart className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-2">
              <h4 className="font-bold text-gray-900 text-lg">Target Disease</h4>
              <ProvenanceChip provenance={data?.provenance} onViewSource={onViewSource} />
            </div>
            <div className="text-sm text-gray-700 leading-relaxed">
              {data?.targetDisease?.name ? (
                <EditableText
                  value={data.targetDisease.name}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate("study.studyPopulation.targetDisease.name", v) : undefined}
                />
              ) : (
                <span>{formatTargetDisease(data?.targetDisease)}</span>
              )}
              {data?.targetDisease?.stage && (
                <span className="ml-1">
                  (<EditableText
                    value={data.targetDisease.stage}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate("study.studyPopulation.targetDisease.stage", v) : undefined}
                  />)
                </span>
              )}
            </div>

            <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
              {data?.ageRange && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Age Range</span>
                  <div className="font-semibold text-gray-900">
                    <EditableNumber
                      value={data.ageRange.minAge || 0}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("study.studyPopulation.ageRange.minAge", v) : undefined}
                    />
                    <span> - </span>
                    {data.ageRange.maxAgeNoLimit ? (
                      <span>No Limit</span>
                    ) : (
                      <EditableNumber
                        value={data.ageRange.maxAge || 999}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("study.studyPopulation.ageRange.maxAge", v) : undefined}
                      />
                    )}
                    <span> {data.ageRange.unit || "years"}</span>
                  </div>
                </div>
              )}
              {data?.sex && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Sex</span>
                  <span className="font-semibold text-gray-900">{formatSex(data.sex)}</span>
                </div>
              )}
              {data?.performanceStatus && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Performance Status</span>
                  <div className="font-semibold text-gray-900">
                    <EditableText
                      value={data.performanceStatus.scale || data.performanceStatus.scaleName || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("study.studyPopulation.performanceStatus.scale", v) : undefined}
                    />
                    {data.performanceStatus.allowedValues?.length > 0 && (
                      <span>: {data.performanceStatus.allowedValues.join(", ")}</span>
                    )}
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

function InclusionTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const items = data?.keyInclusionSummary?.values || [];

  if (items.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <CheckCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No inclusion criteria defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <CheckCircle className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Key Inclusion Criteria</h4>
              <ProvenanceChip provenance={data.keyInclusionSummary?.provenance} onViewSource={onViewSource} />
            </div>
            <p className="text-sm text-gray-700 leading-relaxed mb-4">
              Participants must meet all of the following criteria to be eligible for enrollment.
            </p>
          </div>
        </div>
      </div>

      <CriteriaList
        items={items}
        type="inclusion"
        onViewSource={onViewSource}
        onFieldUpdate={onFieldUpdate}
      />
    </div>
  );
}

function ExclusionTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const items = data?.keyExclusionSummary?.values || [];

  if (items.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <XCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No exclusion criteria defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <XCircle className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Key Exclusion Criteria</h4>
              <ProvenanceChip provenance={data.keyExclusionSummary?.provenance} onViewSource={onViewSource} />
            </div>
            <p className="text-sm text-gray-700 leading-relaxed mb-4">
              Participants meeting any of the following criteria will be excluded from the study.
            </p>
          </div>
        </div>
      </div>

      <CriteriaList
        items={items}
        type="exclusion"
        onViewSource={onViewSource}
        onFieldUpdate={onFieldUpdate}
      />
    </div>
  );
}

function PopulationViewContent({ data, onViewSource, onFieldUpdate }: PopulationViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const registry = useCoverageRegistry();
  
  useEffect(() => {
    if (registry) {
      registry.markRendered([
        "targetDisease", "ageRange", "sex", "performanceStatus",
        "keyInclusionSummary", "keyExclusionSummary", "provenance"
      ]);
    }
  }, [registry]);
  
  const inclusionCount = data?.keyInclusionSummary?.values?.length || 0;
  const exclusionCount = data?.keyExclusionSummary?.values?.length || 0;
  
  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "inclusion", label: "Inclusion Criteria", icon: CheckCircle, count: inclusionCount },
    { id: "exclusion", label: "Exclusion Criteria", icon: XCircle, count: exclusionCount },
  ];
  
  return (
    <div className="space-y-6" data-testid="population-view">
      <SummaryHeader data={data} />
      
      <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-xl overflow-x-auto" role="tablist" data-testid="population-tab-list">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
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
          {activeTab === "inclusion" && <InclusionTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "exclusion" && <ExclusionTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export function PopulationView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: PopulationViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No population data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <PopulationViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
