import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { useCoverageRegistry } from "@/lib/coverage-registry";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, ChevronDown, FlaskConical, Layers, Users, Shuffle,
  Pill, Syringe, Target, BarChart3, Eye, Globe, MapPin, CheckCircle,
  Clock, AlertTriangle, ArrowRight, Settings2
} from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";
import { EditableText } from "./EditableValue";

interface ArmsDesignViewProps {
  studyDesignInfo: any;
  studyArms: any[];
  studyEpochs?: any[];
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "design" | "arms" | "interventions" | "epochs" | "modifications";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function SummaryHeader({ studyDesignInfo, armCount }: { studyDesignInfo: any; armCount: number }) {
  const designType = studyDesignInfo?.designType || "Not specified";
  const allocationRatio = studyDesignInfo?.randomization?.allocationRatio || "N/A";
  const blindingType = studyDesignInfo?.blinding?.blindingType || "N/A";
  const targetEnrollment = studyDesignInfo?.targetEnrollment;
  const plannedSites = studyDesignInfo?.plannedSites;
  const isRandomized = studyDesignInfo?.randomization?.isRandomized;
  
  return (
    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="arms-design-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <FlaskConical className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Study Design</h3>
          <p className="text-sm text-muted-foreground">{designType} • {blindingType}</p>
        </div>
      </div>
      
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-design-type">
          <div className="flex items-center gap-1.5 mb-1">
            <Layers className="w-3.5 h-3.5 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Design</span>
          </div>
          <p className="text-sm font-bold text-gray-900 truncate">{designType}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-blinding">
          <div className="flex items-center gap-1.5 mb-1">
            <Eye className="w-3.5 h-3.5 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Blinding</span>
          </div>
          <p className="text-sm font-bold text-gray-900 truncate">{blindingType}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-randomized">
          <div className="flex items-center gap-1.5 mb-1">
            <Shuffle className="w-3.5 h-3.5 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Randomized</span>
          </div>
          <p className="text-sm font-bold text-gray-900">{isRandomized ? `Yes (${allocationRatio})` : "No"}</p>
        </div>
        
        <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-arms">
          <div className="flex items-center gap-1.5 mb-1">
            <Users className="w-3.5 h-3.5 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Arms</span>
          </div>
          <p className="text-xl font-bold text-gray-900">{armCount || "N/A"}</p>
        </div>
        
        {targetEnrollment && (
          <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-enrollment">
            <div className="flex items-center gap-1.5 mb-1">
              <Target className="w-3.5 h-3.5 text-gray-600" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Enrollment</span>
            </div>
            <p className="text-xl font-bold text-gray-900">{targetEnrollment}</p>
          </div>
        )}
        
        {plannedSites && (
          <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm" data-testid="stat-sites">
            <div className="flex items-center gap-1.5 mb-1">
              <MapPin className="w-3.5 h-3.5 text-gray-600" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Sites</span>
            </div>
            <p className="text-xl font-bold text-gray-900">{plannedSites}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function ArmCard({ arm, index, onViewSource, onFieldUpdate }: { arm: any; index: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [expanded, setExpanded] = useState(false);
  const basePath = `domainSections.studyDesign.data.studyArms.${index}`;
  const armColors = [
    { bg: "from-gray-800 to-gray-900", light: "bg-gray-50", border: "border-gray-200", text: "text-gray-700" },
    { bg: "from-gray-800 to-gray-900", light: "bg-gray-50", border: "border-gray-200", text: "text-gray-700" },
    { bg: "from-gray-800 to-gray-900", light: "bg-gray-50", border: "border-gray-200", text: "text-gray-700" },
    { bg: "from-gray-800 to-gray-900", light: "bg-gray-50", border: "border-gray-200", text: "text-gray-700" },
    { bg: "from-gray-800 to-gray-900", light: "bg-gray-50", border: "border-gray-200", text: "text-gray-700" },
  ];
  
  const color = armColors[index % armColors.length];
  const armType = arm.armType?.decode || arm.armType?.code || "Treatment";
  
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm" data-testid={`arm-card-${arm.id || index}`}>
      <div className="p-5 border-b border-gray-100">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className={cn("w-12 h-12 rounded-xl bg-gradient-to-br flex items-center justify-center flex-shrink-0 shadow-lg", color.bg)}>
              <FlaskConical className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <h4 className="font-bold text-foreground text-lg">
                  <EditableText
                    value={arm.name || arm.label || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.name`, v) : undefined}
                  />
                </h4>
                <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", color.light, color.text)}>
                  {armType}
                </span>
              </div>
              {arm.description && (
                <div className="text-sm text-muted-foreground leading-relaxed">
                  <EditableText
                    value={arm.description}
                    multiline
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.description`, v) : undefined}
                  />
                </div>
              )}
              <div className="flex flex-wrap gap-3 mt-3">
                {arm.plannedSubjects && (
                  <div className="flex items-center gap-1.5 text-sm">
                    <Users className="w-3.5 h-3.5 text-gray-500" />
                    <span className="text-gray-600">Planned:</span>
                    <span className="font-semibold text-gray-900">{arm.plannedSubjects} subjects</span>
                  </div>
                )}
                {arm.allocationRatio && (
                  <div className="flex items-center gap-1.5 text-sm">
                    <Shuffle className="w-3.5 h-3.5 text-gray-500" />
                    <span className="text-gray-600">Ratio:</span>
                    <span className="font-semibold text-gray-900">{arm.allocationRatio}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ProvenanceChip provenance={arm.provenance} onViewSource={onViewSource} />
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              data-testid={`arm-expand-${arm.id || index}`}
            >
              <ChevronDown className={cn("w-5 h-5 transition-transform", expanded && "rotate-180")} />
            </button>
          </div>
        </div>
      </div>
      
      {!expanded && arm.interventions && arm.interventions.length > 0 && (
        <div className="p-5 bg-gray-50/50">
          <div className="flex items-center gap-2 mb-3">
            <Pill className="w-4 h-4 text-gray-500" />
            <span className="text-sm font-semibold text-foreground">Interventions ({arm.interventions.length})</span>
          </div>
          <div className="space-y-4">
            {arm.interventions.map((intervention: any, idx: number) => {
              const dosing = intervention.dosingRegimen;
              const doseStr = dosing ? `${dosing.dose} ${dosing.doseUnit}` : null;
              const routeStr = dosing?.route?.decode || dosing?.route;
              const frequencyStr = dosing?.frequency;
              const interventionPath = `${basePath}.interventions.${idx}`;

              return (
                <div key={idx} className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-3">
                      <Syringe className="w-5 h-5 text-gray-600" />
                      <div>
                        <EditableText
                          value={intervention.name || intervention.label || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${interventionPath}.name`, v) : undefined}
                          className="font-semibold text-foreground text-base"
                        />
                        <div className="flex flex-wrap items-center gap-2 mt-1">
                          {intervention.type && (
                            <EditableText
                              value={intervention.type}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${interventionPath}.type`, v) : undefined}
                              className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700"
                            />
                          )}
                          {intervention.role?.decode && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">{intervention.role.decode}</span>
                          )}
                          {intervention.drugClass && (
                            <EditableText
                              value={intervention.drugClass}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${interventionPath}.drugClass`, v) : undefined}
                              className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700"
                            />
                          )}
                          {intervention.isPlacebo && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">Placebo</span>
                          )}
                          {intervention.isComparator && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">Comparator</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <ProvenanceChip provenance={intervention.provenance} onViewSource={onViewSource} />
                  </div>

                  {dosing && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 pt-3 border-t border-gray-100">
                      {doseStr && (
                        <div className="bg-gray-50 rounded-lg p-2">
                          <span className="text-xs text-gray-500 block">Dose</span>
                          <EditableText
                            value={doseStr}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${interventionPath}.dosingRegimen.dose`, v) : undefined}
                            className="text-sm font-semibold text-gray-900"
                          />
                        </div>
                      )}
                      {routeStr && (
                        <div className="bg-gray-50 rounded-lg p-2">
                          <span className="text-xs text-gray-500 block">Route</span>
                          <EditableText
                            value={routeStr}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${interventionPath}.dosingRegimen.route`, v) : undefined}
                            className="text-sm font-semibold text-gray-900"
                          />
                        </div>
                      )}
                      {frequencyStr && (
                        <div className="bg-gray-50 rounded-lg p-2">
                          <span className="text-xs text-gray-500 block">Frequency</span>
                          <EditableText
                            value={frequencyStr}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${interventionPath}.dosingRegimen.frequency`, v) : undefined}
                            className="text-sm font-semibold text-gray-900"
                          />
                        </div>
                      )}
                      {dosing.cycleLengthDays && (
                        <div className="bg-gray-50 rounded-lg p-2">
                          <span className="text-xs text-gray-500 block">Cycle Length</span>
                          <EditableText
                            value={`${dosing.cycleLengthDays} days`}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${interventionPath}.dosingRegimen.cycleLengthDays`, v) : undefined}
                            className="text-sm font-semibold text-gray-900"
                          />
                        </div>
                      )}
                      {dosing.infusionDurationMinutes && (
                        <div className="bg-gray-50 rounded-lg p-2">
                          <span className="text-xs text-gray-500 block">Infusion Duration</span>
                          <EditableText
                            value={`${dosing.infusionDurationMinutes} min`}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${interventionPath}.dosingRegimen.infusionDurationMinutes`, v) : undefined}
                            className="text-sm font-semibold text-gray-900"
                          />
                        </div>
                      )}
                      {dosing.doseCalculationBasis && (
                        <div className="bg-gray-50 rounded-lg p-2">
                          <span className="text-xs text-gray-500 block">Calculation Basis</span>
                          <EditableText
                            value={dosing.doseCalculationBasis}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${interventionPath}.dosingRegimen.doseCalculationBasis`, v) : undefined}
                            className="text-sm font-semibold text-gray-900"
                          />
                        </div>
                      )}
                    </div>
                  )}
                  
                  {intervention.doseModifications?.reductionLevels?.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-100">
                      <p className="text-xs font-medium text-gray-600 mb-2">Dose Reduction Levels</p>
                      <div className="flex flex-wrap gap-2">
                        {intervention.doseModifications.reductionLevels.map((level: any, lidx: number) => (
                          <span key={lidx} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-lg">
                            Level {level.level}: {level.dose} {level.doseUnit}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {intervention.biomedicalConcept && (
                    <div className="mt-3 pt-3 border-t border-gray-100">
                      <p className="text-xs text-gray-500">
                        <span className="font-medium">Biomedical Concept:</span> {intervention.biomedicalConcept.conceptName}
                        {intervention.biomedicalConcept.cdiscCode && (
                          <span className="ml-1 text-gray-400">({intervention.biomedicalConcept.cdiscCode})</span>
                        )}
                      </p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
      
      {expanded && (
        <div className="p-5 bg-gray-50/50 border-t border-gray-100">
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Complete Arm Data</div>
          <SmartDataRender data={arm} onViewSource={onViewSource} editable={false} />
        </div>
      )}
    </div>
  );
}

function OverviewTab({ studyDesignInfo, studyArms, onViewSource }: { studyDesignInfo: any; studyArms: any[]; onViewSource?: (page: number) => void }) {
  const designType = studyDesignInfo?.designType || "Not specified";
  const allocationRatio = studyDesignInfo?.randomization?.allocationRatio || "N/A";
  const stratFactors = studyDesignInfo?.randomization?.stratificationFactors || [];
  const totalInterventions = studyArms.reduce((sum, arm) => sum + (arm.interventions?.length || 0), 0);

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <FlaskConical className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-bold text-gray-900 text-lg mb-2">Study Design Overview</h4>
            <p className="text-sm text-gray-700 leading-relaxed">
              This section describes the study design, treatment arms, randomization strategy, and interventions being evaluated in the clinical trial.
            </p>
          </div>
        </div>
      </div>
      
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-gray-600" />
            Design Metrics at a Glance
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Layers className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-sm font-bold text-gray-900 line-clamp-2">{designType}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Design Type</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Users className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{studyArms.length}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Study Arms</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Shuffle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{allocationRatio}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Allocation Ratio</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Pill className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{totalInterventions}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Interventions</p>
            </div>
          </div>
        </div>
      </div>
      
      {stratFactors.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-gray-900" />
              </div>
              <h4 className="font-semibold text-foreground">Stratification Factors</h4>
              <span className="text-xs px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-700">{stratFactors.length}</span>
            </div>
          </div>
          <div className="p-5">
            <div className="flex flex-wrap gap-2">
              {stratFactors.map((factor: any, idx: number) => (
                <span key={idx} className="text-sm bg-gray-50 text-gray-700 px-3 py-1.5 rounded-full border border-gray-200 font-medium">
                  {factor.name || factor}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DesignTab({ studyDesignInfo, onViewSource, onFieldUpdate }: { studyDesignInfo: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [expanded, setExpanded] = useState(false);
  
  if (!studyDesignInfo) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <FlaskConical className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study design information available</p>
      </div>
    );
  }
  
  const blinding = studyDesignInfo.blinding;
  const randomization = studyDesignInfo.randomization;
  const countries = studyDesignInfo.countries;
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <FlaskConical className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Study Design Details</h4>
              <div className="flex items-center gap-2">
                <ProvenanceChip provenance={studyDesignInfo.provenance} onViewSource={onViewSource} />
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
                  data-testid="design-expand"
                >
                  <ChevronDown className={cn("w-5 h-5 transition-transform", expanded && "rotate-180")} />
                </button>
              </div>
            </div>
            
            {!expanded && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {studyDesignInfo.designType && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-600 uppercase tracking-wider block mb-1">Design Type</span>
                  <span className="font-semibold text-gray-900">
                    <EditableText
                      value={studyDesignInfo.designType}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.studyDesign.data.studyDesignInfo.designType", v) : undefined}
                    />
                  </span>
                </div>
              )}
              {blinding?.blindingType && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-xs font-medium text-gray-600 uppercase tracking-wider block mb-1">Blinding</span>
                      <span className="font-semibold text-gray-900">{blinding.blindingType}</span>
                    </div>
                    <ProvenanceChip provenance={blinding.provenance} onViewSource={onViewSource} />
                  </div>
                </div>
              )}
              {randomization?.isRandomized !== undefined && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-xs font-medium text-gray-600 uppercase tracking-wider block mb-1">Randomization</span>
                      <span className="font-semibold text-gray-900">
                        {randomization.isRandomized ? "Randomized" : "Non-Randomized"}
                        {randomization.allocationRatio && ` (${randomization.allocationRatio})`}
                      </span>
                    </div>
                    <ProvenanceChip provenance={randomization.provenance} onViewSource={onViewSource} />
                  </div>
                </div>
              )}
              {studyDesignInfo.targetEnrollment && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-600 uppercase tracking-wider block mb-1">Target Enrollment</span>
                  <span className="font-semibold text-gray-900 text-lg">{studyDesignInfo.targetEnrollment} subjects</span>
                </div>
              )}
              {studyDesignInfo.plannedSites && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-600 uppercase tracking-wider block mb-1">Planned Sites</span>
                  <span className="font-semibold text-gray-900 text-lg">{studyDesignInfo.plannedSites} sites</span>
                </div>
              )}
            </div>
            )}
            
            {!expanded && studyDesignInfo.randomization?.stratificationFactors && studyDesignInfo.randomization.stratificationFactors.length > 0 && (
              <div className="mt-4">
                <span className="text-xs font-medium text-gray-600 uppercase tracking-wider block mb-2">Stratification Factors</span>
                <div className="flex flex-wrap gap-2">
                  {studyDesignInfo.randomization.stratificationFactors.map((factor: any, idx: number) => (
                    <span key={idx} className="text-xs bg-white/70 text-gray-700 px-3 py-1.5 rounded-full border border-gray-200 font-medium">
                      {factor.name || factor}
                    </span>
                  ))}
                </div>
              </div>
            )}
            
            {expanded && (
              <SmartDataRender data={studyDesignInfo} onViewSource={onViewSource} editable={false} />
            )}
          </div>
        </div>
      </div>
      
      {!expanded && countries?.values && countries.values.length > 0 && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Globe className="w-5 h-5 text-gray-600" />
              <h4 className="font-semibold text-foreground">Geographic Coverage</h4>
            </div>
            <ProvenanceChip provenance={countries.provenance} onViewSource={onViewSource} />
          </div>
          <div className="flex flex-wrap gap-2">
            {countries.values.map((region: string, idx: number) => (
              <span key={idx} className="px-3 py-1.5 bg-gray-50 text-gray-700 rounded-full text-sm font-medium border border-gray-200">
                {region}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ArmsTab({ studyArms, onViewSource, onFieldUpdate }: { studyArms: any[]; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!studyArms || studyArms.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study arms defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {studyArms.map((arm, idx) => (
        <ArmCard key={arm.id || idx} arm={arm} index={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function InterventionsTab({ studyArms, onViewSource, onFieldUpdate }: { studyArms: any[]; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const allInterventions: { intervention: any; armName: string; armIdx: number; interventionIdx: number }[] = [];
  studyArms.forEach((arm, armIdx) => {
    if (arm.interventions) {
      arm.interventions.forEach((intervention: any, interventionIdx: number) => {
        allInterventions.push({ intervention, armName: arm.name || arm.label, armIdx, interventionIdx });
      });
    }
  });
  
  if (allInterventions.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Pill className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No interventions defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-4">
      {allInterventions.map(({ intervention, armName, armIdx, interventionIdx }, idx) => {
        const dosing = intervention.dosingRegimen;
        const doseStr = dosing ? `${dosing.dose} ${dosing.doseUnit}` : null;
        const routeStr = dosing?.route?.decode || dosing?.route;
        const frequencyStr = dosing?.frequency;
        const basePath = `domainSections.studyDesign.data.studyArms.${armIdx}.interventions.${interventionIdx}`;

        return (
          <div key={idx} className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
            <div className="p-4">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0">
                    <Syringe className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="font-semibold text-foreground">
                        <EditableText
                          value={intervention.name || intervention.label || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.name`, v) : undefined}
                        />
                      </span>
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{armName}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 mt-1">
                      {intervention.type && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">{intervention.type}</span>
                      )}
                      {intervention.role?.decode && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">{intervention.role.decode}</span>
                      )}
                      {intervention.drugClass && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">{intervention.drugClass}</span>
                      )}
                    </div>
                  </div>
                </div>
                <ProvenanceChip provenance={intervention.provenance} onViewSource={onViewSource} />
              </div>
              
              {dosing && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 pt-3 border-t border-gray-100">
                  {doseStr && (
                    <div className="bg-gray-50 rounded-lg p-2">
                      <span className="text-xs text-gray-500 block">Dose</span>
                      <EditableText
                        value={doseStr}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.dosingRegimen.dose`, v) : undefined}
                        className="text-sm font-semibold text-gray-900"
                      />
                    </div>
                  )}
                  {routeStr && (
                    <div className="bg-gray-50 rounded-lg p-2">
                      <span className="text-xs text-gray-500 block">Route</span>
                      <EditableText
                        value={routeStr}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.dosingRegimen.route`, v) : undefined}
                        className="text-sm font-semibold text-gray-900"
                      />
                    </div>
                  )}
                  {frequencyStr && (
                    <div className="bg-gray-50 rounded-lg p-2">
                      <span className="text-xs text-gray-500 block">Frequency</span>
                      <EditableText
                        value={frequencyStr}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.dosingRegimen.frequency`, v) : undefined}
                        className="text-sm font-semibold text-gray-900"
                      />
                    </div>
                  )}
                  {dosing.cycleLengthDays && (
                    <div className="bg-gray-50 rounded-lg p-2">
                      <span className="text-xs text-gray-500 block">Cycle</span>
                      <EditableText
                        value={`${dosing.cycleLengthDays} days`}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.dosingRegimen.cycleLengthDays`, v) : undefined}
                        className="text-sm font-semibold text-gray-900"
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function EpochsTab({ studyEpochs, onViewSource, onFieldUpdate }: { studyEpochs: any[]; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!studyEpochs || studyEpochs.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Clock className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study epochs defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Clock className="w-5 h-5 text-gray-600" />
          <h4 className="font-semibold text-foreground">Study Epochs</h4>
        </div>
        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">{studyEpochs.length} epochs</span>
      </div>

      <div className="relative">
        {/* Timeline visualization */}
        <div className="flex items-stretch gap-2 overflow-x-auto pb-4">
          {studyEpochs.map((epoch: any, idx: number) => (
            <div key={epoch.id || idx} className="flex-shrink-0 min-w-[200px] max-w-[280px]">
              <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm h-full relative">
                {idx < studyEpochs.length - 1 && (
                  <ArrowRight className="absolute -right-4 top-1/2 transform -translate-y-1/2 w-6 h-6 text-gray-300 z-10" />
                )}
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
                    <span className="text-sm font-bold text-gray-700">{epoch.sequenceInStudy || idx + 1}</span>
                  </div>
                  <ProvenanceChip provenance={epoch.provenance} onViewSource={onViewSource} />
                </div>
                <h5 className="font-semibold text-foreground mb-1">{epoch.name || epoch.id}</h5>
                {epoch.epochType && (
                  <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 mb-2">
                    {epoch.epochType?.decode || epoch.epochType}
                  </span>
                )}
                {epoch.durationDays && (
                  <p className="text-sm text-muted-foreground">
                    <Clock className="inline w-3 h-3 mr-1" />
                    {epoch.durationDays} days
                  </p>
                )}
                {epoch.durationDescription && (
                  <p className="text-xs text-muted-foreground mt-1">{epoch.durationDescription}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Detailed list */}
      <div className="space-y-3 mt-4">
        {studyEpochs.map((epoch: any, idx: number) => (
          <div key={epoch.id || `detail-${idx}`} className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center">
                  <Clock className="w-5 h-5 text-gray-600" />
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-foreground">{epoch.name || epoch.id}</span>
                    {epoch.epochType && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">
                        {epoch.epochType?.decode || epoch.epochType}
                      </span>
                    )}
                    {epoch.sequenceInStudy && (
                      <span className="text-xs text-muted-foreground">Sequence: {epoch.sequenceInStudy}</span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-3 text-sm text-muted-foreground">
                    {epoch.durationDays && (
                      <span>Duration: {epoch.durationDays} days</span>
                    )}
                    {epoch.durationDescription && (
                      <span>{epoch.durationDescription}</span>
                    )}
                  </div>
                </div>
              </div>
              <ProvenanceChip provenance={epoch.provenance} onViewSource={onViewSource} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DoseModificationsTab({ studyArms, onViewSource }: { studyArms: any[]; onViewSource?: (page: number) => void }) {
  // Collect all dose modifications from interventions
  const allModifications: { intervention: any; armName: string; modifications: any }[] = [];

  studyArms.forEach(arm => {
    if (arm.interventions) {
      arm.interventions.forEach((intervention: any) => {
        if (intervention.doseModifications) {
          allModifications.push({
            intervention,
            armName: arm.name || arm.label,
            modifications: intervention.doseModifications
          });
        }
      });
    }
  });

  if (allModifications.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Settings2 className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No dose modifications defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {allModifications.map(({ intervention, armName, modifications }, idx) => (
        <div key={idx} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-transparent">
            <div className="flex items-center gap-3">
              <Syringe className="w-5 h-5 text-gray-600" />
              <div>
                <h5 className="font-semibold text-foreground">{intervention.name || intervention.label}</h5>
                <span className="text-xs text-muted-foreground">{armName}</span>
              </div>
            </div>
          </div>

          <div className="p-4 space-y-4">
            {/* Reduction Levels */}
            {modifications.reductionLevels && modifications.reductionLevels.length > 0 && (
              <div>
                <h6 className="text-sm font-medium text-foreground mb-2 flex items-center gap-2">
                  <Layers className="w-4 h-4 text-gray-500" />
                  Dose Reduction Levels
                </h6>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {modifications.reductionLevels.map((level: any, lidx: number) => (
                    <div key={lidx} className="bg-gray-50 rounded-lg p-3 border border-gray-200 text-center">
                      <p className="text-lg font-bold text-gray-900">{level.dose} {level.doseUnit}</p>
                      <p className="text-xs text-gray-600">Level {level.level}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Modification Triggers */}
            {modifications.modificationTriggers && modifications.modificationTriggers.length > 0 && (
              <div>
                <h6 className="text-sm font-medium text-foreground mb-2 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-gray-500" />
                  Modification Triggers
                </h6>
                <div className="space-y-2">
                  {modifications.modificationTriggers.map((trigger: any, tidx: number) => (
                    <div key={tidx} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="font-medium text-gray-900">{trigger.condition}</p>
                          {trigger.toxicityGrade && (
                            <span className="text-xs text-gray-700">Grade {trigger.toxicityGrade}</span>
                          )}
                        </div>
                        <span className={cn(
                          "text-xs px-2 py-0.5 rounded-full font-medium",
                          trigger.action === "Discontinue" ? "bg-red-100 text-red-700" :
                          trigger.action === "Hold" ? "bg-gray-100 text-gray-700" :
                          trigger.action === "Reduce" ? "bg-gray-100 text-gray-700" :
                          "bg-gray-100 text-gray-700"
                        )}>
                          {trigger.action}
                        </span>
                      </div>
                      {trigger.holdCriteria && (
                        <p className="text-xs text-gray-700 mt-1">Hold criteria: {trigger.holdCriteria}</p>
                      )}
                      {trigger.targetLevel && (
                        <p className="text-xs text-gray-700 mt-1">Target level: {trigger.targetLevel}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Permanent Discontinuation Triggers */}
            {modifications.permanentDiscontinuationTriggers && modifications.permanentDiscontinuationTriggers.length > 0 && (
              <div>
                <h6 className="text-sm font-medium text-foreground mb-2 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-500" />
                  Permanent Discontinuation Triggers
                </h6>
                <div className="space-y-2">
                  {modifications.permanentDiscontinuationTriggers.map((trigger: any, tidx: number) => (
                    <div key={tidx} className="bg-red-50 rounded-lg p-3 border border-red-200">
                      <p className="font-medium text-red-900">{typeof trigger === 'string' ? trigger : trigger.condition || trigger.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Rechallenge Criteria */}
            {modifications.rechallengeCriteria && (
              <div>
                <h6 className="text-sm font-medium text-foreground mb-2 flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 text-green-500" />
                  Rechallenge Criteria
                </h6>
                <div className="bg-green-50 rounded-lg p-3 border border-green-200">
                  <p className="text-sm text-green-900">{modifications.rechallengeCriteria}</p>
                </div>
              </div>
            )}

            {/* Maximum Reductions */}
            {modifications.maximumReductions !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <p className="text-sm text-gray-700">
                  <span className="font-medium">Maximum Reductions:</span> {modifications.maximumReductions}
                </p>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function ArmsDesignViewContent({ studyDesignInfo, studyArms, studyEpochs, onViewSource, onFieldUpdate }: ArmsDesignViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const registry = useCoverageRegistry();
  const arms = studyArms || [];
  
  useEffect(() => {
    if (registry) {
      registry.markRendered(["studyDesignInfo", "studyArms"]);
    }
  }, [registry]);
  
  const epochs = studyEpochs || [];
  const totalInterventions = arms.reduce((sum, arm) => sum + (arm.interventions?.length || 0), 0);
  const totalModifications = arms.reduce((sum, arm) =>
    sum + (arm.interventions?.filter((i: any) => i.doseModifications)?.length || 0), 0);

  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "design", label: "Design", icon: FlaskConical },
    { id: "arms", label: "Arms", icon: Users, count: arms.length },
    { id: "interventions", label: "Interventions", icon: Pill, count: totalInterventions },
    { id: "epochs", label: "Epochs", icon: Clock, count: epochs.length > 0 ? epochs.length : undefined },
    { id: "modifications", label: "Dose Mods", icon: Settings2, count: totalModifications > 0 ? totalModifications : undefined },
  ];
  
  return (
    <div className="space-y-6" data-testid="arms-design-view">
      <SummaryHeader studyDesignInfo={studyDesignInfo} armCount={arms.length} />
      
      <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-xl overflow-x-auto" role="tablist" data-testid="arms-tab-list">
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
          {activeTab === "overview" && <OverviewTab studyDesignInfo={studyDesignInfo} studyArms={arms} onViewSource={onViewSource} />}
          {activeTab === "design" && <DesignTab studyDesignInfo={studyDesignInfo} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "arms" && <ArmsTab studyArms={arms} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "interventions" && <InterventionsTab studyArms={arms} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "epochs" && <EpochsTab studyEpochs={epochs} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "modifications" && <DoseModificationsTab studyArms={arms} onViewSource={onViewSource} />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export function ArmsDesignView({ studyDesignInfo, studyArms, studyEpochs, onViewSource, onFieldUpdate, agentDoc, qualityScore }: ArmsDesignViewProps) {
  const arms = studyArms || [];

  if (!studyDesignInfo && arms.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <FlaskConical className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study design data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <ArmsDesignViewContent studyDesignInfo={studyDesignInfo} studyArms={studyArms} studyEpochs={studyEpochs} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
