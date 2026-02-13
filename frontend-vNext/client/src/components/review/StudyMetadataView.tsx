import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, ChevronDown, Layers, Calendar, Hash, Building2,
  Beaker, Users, Clock, Globe, CheckCircle, LayoutGrid, Target,
  MapPin, Shuffle, Eye, FlaskConical, Timer, BarChart3, FileCode,
  Dna, Microscope, TrendingUp, AlertCircle, Activity, Copy, Check,
  HeartPulse, Pill, ClipboardList, UserCheck, AlertTriangle
} from "lucide-react";
import { EditableText, EditableNumber } from "./EditableValue";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";

interface StudyMetadataViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "design" | "population" | "milestones" | "analyses" | "identifiers" | "versions";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function SummaryHeader({ study }: { study: any }) {
  const phase = study?.studyPhase?.decode || study?.studyPhase?.code || "N/A";
  const type = study?.studyType?.decode || study?.studyType?.code || "N/A";
  const identifierCount = study?.studyIdentifiers?.length || 0;
  const versionCount = study?.studyProtocolVersions?.length || 0;
  
  return (
    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="study-metadata-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center shadow-md">
          <Beaker className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Study Overview</h3>
          <p className="text-sm text-muted-foreground">{study?.name || "Clinical Trial Protocol"}</p>
        </div>
      </div>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-phase">
          <div className="flex items-center gap-2 mb-1">
            <Layers className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Phase</span>
          </div>
          <p className="text-xl font-bold text-gray-900">{phase}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-type">
          <div className="flex items-center gap-2 mb-1">
            <Beaker className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Type</span>
          </div>
          <p className="text-lg font-bold text-gray-900 truncate">{type}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-identifiers">
          <div className="flex items-center gap-2 mb-1">
            <Hash className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Identifiers</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{identifierCount}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid="stat-versions">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Versions</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{versionCount}</p>
        </div>
      </div>
    </div>
  );
}

function InfoCard({
  label,
  value,
  icon: Icon,
  provenance,
  onViewSource,
  colorClass = "blue",
  fieldPath,
  onFieldUpdate
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  provenance?: any;
  onViewSource?: (page: number) => void;
  colorClass?: string;
  fieldPath?: string;
  onFieldUpdate?: (path: string, value: any) => void;
}) {
  // Debug: log when Version card renders
  if (label === "Version") {
    console.log("[InfoCard Version] Rendering with:", { fieldPath, hasOnFieldUpdate: !!onFieldUpdate, value });
  }

  const colors: Record<string, { bg: string; icon: string; text: string }> = {
    blue: { bg: "bg-gray-50", icon: "text-gray-600", text: "text-gray-900" },
    indigo: { bg: "bg-gray-50", icon: "text-gray-600", text: "text-gray-900" },
    emerald: { bg: "bg-gray-50", icon: "text-gray-600", text: "text-gray-900" },
    amber: { bg: "bg-gray-50", icon: "text-gray-600", text: "text-gray-900" },
  };

  const color = colors[colorClass] || colors.blue;

  // Create onSave handler with debug logging
  const handleSave = fieldPath && onFieldUpdate
    ? (newValue: string) => {
        console.log("[InfoCard] handleSave called:", { fieldPath, newValue });
        onFieldUpdate(fieldPath, newValue);
      }
    : undefined;

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", color.bg)}>
            <Icon className={cn("w-5 h-5", color.icon)} />
          </div>
          <div>
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block">{label}</span>
            <div className={cn("font-semibold mt-1", color.text)}>
              <EditableText
                value={value}
                onSave={handleSave}
              />
            </div>
          </div>
        </div>
        <ProvenanceChip provenance={provenance} onViewSource={onViewSource} />
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const sponsorName = data.sponsorName?.value || data.sponsorName;
  const indication = data.indication?.value || data.indication;
  const therapeuticArea = data.therapeuticArea?.value || data.therapeuticArea;

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <FileText className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-2">
              <h4 className="font-bold text-gray-900 text-lg">Official Title</h4>
              <ProvenanceChip provenance={data.provenance} onViewSource={onViewSource} />
            </div>
            <div className="text-sm text-gray-700 leading-relaxed">
              <EditableText
                value={data.officialTitle}
                placeholder="No official title specified"
                multiline
                onSave={onFieldUpdate ? (newValue) => onFieldUpdate("study.officialTitle", newValue) : undefined}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <InfoCard
          label="Study Name"
          value={data.name}
          icon={Beaker}
          provenance={data.provenance}
          onViewSource={onViewSource}
          colorClass="blue"
          fieldPath="study.name"
          onFieldUpdate={onFieldUpdate}
        />
        <InfoCard
          label="Study Phase"
          value={data.studyPhase?.decode || data.studyPhase?.code}
          icon={Layers}
          provenance={data.studyPhase?.provenance}
          onViewSource={onViewSource}
          colorClass="indigo"
          fieldPath="study.studyPhase.decode"
          onFieldUpdate={onFieldUpdate}
        />
        <InfoCard
          label="Study Type"
          value={data.studyType?.decode || data.studyType?.code}
          icon={Beaker}
          provenance={data.studyType?.provenance}
          onViewSource={onViewSource}
          colorClass="emerald"
          fieldPath="study.studyType.decode"
          onFieldUpdate={onFieldUpdate}
        />
        <InfoCard
          label="Version"
          value={data.version}
          icon={Clock}
          provenance={data.provenance || extractProvenance(data, 'version')}
          onViewSource={onViewSource}
          colorClass="amber"
          fieldPath="study.version"
          onFieldUpdate={onFieldUpdate}
        />
        {sponsorName && (
          <InfoCard
            label="Sponsor"
            value={sponsorName}
            icon={Building2}
            provenance={data.sponsorName?.provenance}
            onViewSource={onViewSource}
            colorClass="indigo"
            fieldPath={data.sponsorName?.value ? "study.sponsorName.value" : "study.sponsorName"}
            onFieldUpdate={onFieldUpdate}
          />
        )}
        {indication && (
          <InfoCard
            label="Indication"
            value={indication}
            icon={Target}
            provenance={data.indication?.provenance}
            onViewSource={onViewSource}
            colorClass="emerald"
            fieldPath={data.indication?.value ? "study.indication.value" : "study.indication"}
            onFieldUpdate={onFieldUpdate}
          />
        )}
        {therapeuticArea && (
          <InfoCard
            label="Therapeutic Area"
            value={therapeuticArea}
            icon={FlaskConical}
            provenance={data.therapeuticArea?.provenance}
            onViewSource={onViewSource}
            colorClass="blue"
            fieldPath={data.therapeuticArea?.value ? "study.therapeuticArea.value" : "study.therapeuticArea"}
            onFieldUpdate={onFieldUpdate}
          />
        )}
        {data.isPivotal !== undefined && (
          <InfoCard
            label="Pivotal Study"
            value={data.isPivotal ? "Yes" : "No"}
            icon={CheckCircle}
            provenance={data.isPivotal_provenance || data.provenance}
            onViewSource={onViewSource}
            colorClass="amber"
          />
        )}
      </div>
    </div>
  );
}

function DesignTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const designInfo = data?.studyDesignInfo;

  if (!designInfo) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Shuffle className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study design information available</p>
      </div>
    );
  }

  const blinding = designInfo.blinding;
  const randomization = designInfo.randomization;
  const countries = designInfo.countries;

  return (
    <div className="space-y-6">
      {/* Basic Design Info */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {designInfo.designType && (
          <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <Shuffle className="w-4 h-4 text-gray-600" />
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Design Type</span>
              </div>
              <ProvenanceChip provenance={designInfo.provenance} onViewSource={onViewSource} />
            </div>
            <div className="font-semibold text-foreground">
              <EditableText
                value={designInfo.designType}
                onSave={onFieldUpdate ? (newValue) => onFieldUpdate("study.studyDesignInfo.designType", newValue) : undefined}
              />
            </div>
          </div>
        )}

        {designInfo.targetEnrollment && (
          <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-gray-600" />
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Target Enrollment</span>
              </div>
              <ProvenanceChip provenance={designInfo.provenance} onViewSource={onViewSource} />
            </div>
            <div className="text-2xl font-bold text-gray-900">
              <EditableNumber
                value={designInfo.targetEnrollment}
                onSave={onFieldUpdate ? (newValue) => onFieldUpdate("study.studyDesignInfo.targetEnrollment", newValue) : undefined}
              />
            </div>
          </div>
        )}

        {designInfo.plannedSites && (
          <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <MapPin className="w-4 h-4 text-gray-600" />
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Planned Sites</span>
              </div>
              <ProvenanceChip provenance={designInfo.provenance || designInfo.plannedSites_provenance} onViewSource={onViewSource} />
            </div>
            <div className="text-2xl font-bold text-gray-800">
              <EditableNumber
                value={designInfo.plannedSites}
                onSave={onFieldUpdate ? (newValue) => onFieldUpdate("study.studyDesignInfo.plannedSites", newValue) : undefined}
              />
            </div>
          </div>
        )}
      </div>

      {/* Randomization Details */}
      {randomization && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Shuffle className="w-5 h-5 text-gray-600" />
              <h4 className="font-semibold text-foreground">Randomization</h4>
            </div>
            <ProvenanceChip provenance={randomization.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {randomization.isRandomized !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Status</span>
                <span className={cn(
                  "text-sm font-semibold px-2 py-0.5 rounded-full",
                  randomization.isRandomized ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-700"
                )}>
                  {randomization.isRandomized ? "Randomized" : "Non-Randomized"}
                </span>
              </div>
            )}
            {randomization.allocationRatio && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Allocation Ratio</span>
                <span className="font-semibold text-foreground">{randomization.allocationRatio}</span>
              </div>
            )}
            {randomization.allocationMethod && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Allocation Method</span>
                <span className="font-medium text-foreground text-sm">{randomization.allocationMethod}</span>
              </div>
            )}
            {randomization.blockSize && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Block Size</span>
                <span className="font-semibold text-foreground">{randomization.blockSize}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Blinding Details */}
      {blinding && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Eye className="w-5 h-5 text-gray-600" />
              <h4 className="font-semibold text-foreground">Blinding</h4>
            </div>
            <ProvenanceChip provenance={blinding.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {blinding.blindingType && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Blinding Type</span>
                <span className="font-semibold text-foreground">{blinding.blindingType}</span>
              </div>
            )}
            {blinding.whoIsBlinded && blinding.whoIsBlinded.length > 0 && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-2">Who Is Blinded</span>
                <div className="flex flex-wrap gap-2">
                  {blinding.whoIsBlinded.map((role: string, idx: number) => (
                    <span key={idx} className="px-2 py-1 bg-white rounded-md text-sm font-medium text-gray-700 border border-gray-200">
                      {role}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Geographic Coverage */}
      {countries?.values && countries.values.length > 0 && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Globe className="w-5 h-5 text-gray-600" />
              <h4 className="font-semibold text-foreground">Geographic Coverage</h4>
            </div>
            <ProvenanceChip provenance={countries.provenance} onViewSource={onViewSource} />
          </div>
          <div className="flex flex-wrap gap-2">
            {countries.values.map((country: string, idx: number) => (
              <span key={idx} className="px-3 py-1.5 bg-gray-50 text-gray-700 rounded-full text-sm font-medium">
                {country}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PopulationTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const population = data?.studyPopulation;

  if (!population) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study population information available</p>
      </div>
    );
  }

  const targetDisease = population.targetDisease;
  const ageRange = population.ageRange;
  const sex = population.sex;
  const performanceStatus = population.performanceStatus;
  const priorTherapy = population.priorTherapyRequirements;
  const biomarkers = population.biomarkerRequirements || [];
  const keyInclusion = population.keyInclusionSummary;
  const keyExclusion = population.keyExclusionSummary;

  return (
    <div className="space-y-6">
      {/* Target Disease Section */}
      {targetDisease && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Target className="w-5 h-5 text-gray-600" />
              <h4 className="font-semibold text-foreground">Target Disease</h4>
            </div>
            <ProvenanceChip provenance={targetDisease.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {targetDisease.name && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Disease Name</span>
                <span className="font-medium text-foreground">{targetDisease.name}</span>
              </div>
            )}
            {targetDisease.stage && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Stage</span>
                <span className="font-medium text-foreground">{targetDisease.stage}</span>
              </div>
            )}
            {targetDisease.histology && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Histology</span>
                <span className="font-medium text-foreground">{targetDisease.histology}</span>
              </div>
            )}
            {targetDisease.meddraCode && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">MedDRA Code</span>
                <span className="font-medium text-foreground font-mono text-sm">{targetDisease.meddraCode}</span>
              </div>
            )}
            {targetDisease.icdCode && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">ICD-10 Code</span>
                <span className="font-medium text-foreground font-mono text-sm">{targetDisease.icdCode}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Demographics Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Age Range */}
        {ageRange && (
          <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Users className="w-4 h-4 text-gray-600" />
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Age Range</span>
                </div>
                <div className="font-semibold text-foreground">
                  {ageRange.minAge || 0} - {ageRange.maxAgeNoLimit ? "No Limit" : `${ageRange.maxAge || 999}`} {ageRange.unit || "years"}
                </div>
              </div>
              <ProvenanceChip provenance={ageRange.provenance || population?.provenance} onViewSource={onViewSource} />
            </div>
          </div>
        )}

        {/* Sex */}
        {sex?.allowed && sex.allowed.length > 0 && (
          <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <UserCheck className="w-4 h-4 text-gray-600" />
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Sex</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {sex.allowed.map((s: any, idx: number) => (
                    <span key={idx} className="px-2 py-1 bg-gray-100 rounded-md text-sm font-medium text-gray-700">
                      {s.decode || s.code}
                    </span>
                  ))}
                </div>
              </div>
              <ProvenanceChip provenance={sex.provenance} onViewSource={onViewSource} />
            </div>
          </div>
        )}

        {/* Performance Status */}
        {performanceStatus && (
          <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Activity className="w-4 h-4 text-gray-600" />
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Performance Status</span>
                </div>
                <div className="font-semibold text-foreground">
                  {performanceStatus.scale}: {performanceStatus.allowedValues?.join(", ") || "N/A"}
                </div>
              </div>
              <ProvenanceChip provenance={performanceStatus.provenance} onViewSource={onViewSource} />
            </div>
          </div>
        )}
      </div>

      {/* Prior Therapy Requirements */}
      {priorTherapy && (priorTherapy.required?.length > 0 || priorTherapy.minPriorLines || priorTherapy.maxPriorLines) && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Pill className="w-5 h-5 text-gray-600" />
              <h4 className="font-semibold text-foreground">Prior Therapy Requirements</h4>
            </div>
            <ProvenanceChip provenance={priorTherapy.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            {priorTherapy.minPriorLines !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200 text-center">
                <p className="text-2xl font-bold text-gray-900">{priorTherapy.minPriorLines}</p>
                <p className="text-xs font-medium text-gray-600 uppercase tracking-wider">Min Prior Lines</p>
              </div>
            )}
            {priorTherapy.maxPriorLines !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200 text-center">
                <p className="text-2xl font-bold text-gray-900">{priorTherapy.maxPriorLines}</p>
                <p className="text-xs font-medium text-gray-600 uppercase tracking-wider">Max Prior Lines</p>
              </div>
            )}
          </div>
          {priorTherapy.required && priorTherapy.required.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Required Therapies</p>
              <div className="flex flex-wrap gap-2">
                {priorTherapy.required.map((therapy: string, idx: number) => (
                  <span key={idx} className="px-3 py-1.5 bg-gray-100 rounded-full text-sm font-medium text-gray-700">
                    {therapy}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Biomarker Requirements */}
      {biomarkers.length > 0 && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Dna className="w-5 h-5 text-gray-600" />
            <h4 className="font-semibold text-foreground">Biomarker Requirements</h4>
            <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">{biomarkers.length}</span>
          </div>
          <div className="space-y-3">
            {biomarkers.map((biomarker: any, idx: number) => (
              <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
                <div className="flex items-center gap-3">
                  <Dna className="w-4 h-4 text-gray-500" />
                  <div>
                    <span className="font-medium text-foreground">{biomarker.name}</span>
                    {biomarker.requirement && (
                      <span className={cn(
                        "ml-2 text-xs px-2 py-0.5 rounded-full",
                        biomarker.requirement === "Required" ? "bg-green-100 text-green-700" :
                        biomarker.requirement === "Exclusion" ? "bg-red-100 text-red-700" :
                        "bg-gray-100 text-gray-700"
                      )}>
                        {biomarker.requirement}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {biomarker.testingRequired !== undefined && (
                    <span className="text-xs text-muted-foreground">
                      Testing: {biomarker.testingRequired ? "Required" : "Optional"}
                    </span>
                  )}
                  <ProvenanceChip provenance={biomarker.provenance} onViewSource={onViewSource} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Key Inclusion Criteria */}
      {keyInclusion?.values && keyInclusion.values.length > 0 && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-green-600" />
              <h4 className="font-semibold text-foreground">Key Inclusion Criteria</h4>
              <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">{keyInclusion.values.length}</span>
            </div>
            <ProvenanceChip provenance={keyInclusion.provenance} onViewSource={onViewSource} />
          </div>
          <ul className="space-y-2">
            {keyInclusion.values.map((criterion: string, idx: number) => (
              <li key={idx} className="flex items-start gap-2 text-sm text-foreground">
                <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                <span>{criterion}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Key Exclusion Criteria */}
      {keyExclusion?.values && keyExclusion.values.length > 0 && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-600" />
              <h4 className="font-semibold text-foreground">Key Exclusion Criteria</h4>
              <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700">{keyExclusion.values.length}</span>
            </div>
            <ProvenanceChip provenance={keyExclusion.provenance} onViewSource={onViewSource} />
          </div>
          <ul className="space-y-2">
            {keyExclusion.values.map((criterion: string, idx: number) => (
              <li key={idx} className="flex items-start gap-2 text-sm text-foreground">
                <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                <span>{criterion}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Screen Failure Rate */}
      {(population.estimatedScreenFailureRate !== undefined || population.screenFailureRateMethod) && (
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 className="w-4 h-4 text-gray-600" />
            <span className="font-medium text-foreground">Screening Statistics</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {population.estimatedScreenFailureRate !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Est. Screen Failure Rate</span>
                <span className="text-xl font-bold text-gray-900">{Math.round(population.estimatedScreenFailureRate * 100)}%</span>
              </div>
            )}
            {population.screenFailureRateMethod && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1">Method</span>
                <span className="font-medium text-foreground">{population.screenFailureRateMethod}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MilestoneCard({ milestone, label, icon: Icon, onViewSource }: { milestone: any; label: string; icon: React.ElementType; onViewSource?: (page: number) => void }) {
  if (!milestone) return null;

  const date = milestone.date || milestone;
  const dateType = milestone.dateType;
  const description = milestone.description;

  return (
    <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Icon className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
          </div>
          <p className="font-semibold text-foreground">{date || "Not specified"}</p>
          {dateType && (
            <span className={cn(
              "inline-block mt-1 text-xs px-2 py-0.5 rounded-full",
              dateType === "Actual" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-700"
            )}>
              {dateType}
            </span>
          )}
          {description && (
            <p className="text-sm text-muted-foreground mt-1">{description}</p>
          )}
        </div>
        <ProvenanceChip provenance={milestone.provenance} onViewSource={onViewSource} />
      </div>
    </div>
  );
}

function MilestonesTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const milestones = data?.studyMilestones;

  if (!milestones) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Timer className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study milestones available</p>
      </div>
    );
  }

  const durations = milestones.estimatedDurations;
  const hasKeyDates = milestones.studyStartDate || milestones.firstSubjectScreened ||
    milestones.firstSubjectRandomized || milestones.enrollmentCompletionDate ||
    milestones.primaryCompletionDate || milestones.studyCompletionDate;

  return (
    <div className="space-y-6">
      {/* Key Study Dates */}
      {hasKeyDates && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl p-5 border border-gray-200">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-gray-600" />
              <h4 className="font-semibold text-foreground">Key Study Dates</h4>
            </div>
            <ProvenanceChip provenance={milestones.provenance} onViewSource={onViewSource} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <MilestoneCard
              milestone={milestones.studyStartDate}
              label="Study Start"
              icon={Calendar}
              onViewSource={onViewSource}
            />
            <MilestoneCard
              milestone={milestones.firstSubjectScreened}
              label="First Subject Screened"
              icon={Users}
              onViewSource={onViewSource}
            />
            <MilestoneCard
              milestone={milestones.firstSubjectRandomized}
              label="First Subject Randomized"
              icon={Shuffle}
              onViewSource={onViewSource}
            />
            <MilestoneCard
              milestone={milestones.enrollmentCompletionDate}
              label="Enrollment Complete"
              icon={Users}
              onViewSource={onViewSource}
            />
            <MilestoneCard
              milestone={milestones.primaryCompletionDate}
              label="Primary Completion"
              icon={Target}
              onViewSource={onViewSource}
            />
            <MilestoneCard
              milestone={milestones.studyCompletionDate}
              label="Study Completion"
              icon={CheckCircle}
              onViewSource={onViewSource}
            />
          </div>
        </div>
      )}

      {/* Estimated Durations */}
      {durations && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Timer className="w-5 h-5 text-gray-600" />
              <h4 className="font-semibold text-foreground">Estimated Durations</h4>
            </div>
            <ProvenanceChip provenance={durations.provenance || milestones.estimatedDurations?.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {durations.screeningPeriodDays && (
              <div className="bg-gray-50 rounded-xl p-4 text-center border border-gray-200">
                <p className="text-2xl font-bold text-gray-900">{durations.screeningPeriodDays}</p>
                <p className="text-xs font-medium text-gray-700 uppercase tracking-wider">Screening (Days)</p>
              </div>
            )}
            {durations.enrollmentPeriodMonths && (
              <div className="bg-gray-50 rounded-xl p-4 text-center border border-gray-200">
                <p className="text-2xl font-bold text-gray-900">{durations.enrollmentPeriodMonths}</p>
                <p className="text-xs font-medium text-gray-700 uppercase tracking-wider">Enrollment (Months)</p>
              </div>
            )}
            {durations.followUpPeriodMonths && (
              <div className="bg-gray-50 rounded-xl p-4 text-center border border-gray-200">
                <p className="text-2xl font-bold text-gray-900">{durations.followUpPeriodMonths}</p>
                <p className="text-xs font-medium text-gray-700 uppercase tracking-wider">Follow-up (Months)</p>
              </div>
            )}
            {durations.totalStudyDurationMonths && (
              <div className="bg-gray-50 rounded-xl p-4 text-center border border-gray-200">
                <p className="text-2xl font-bold text-gray-900">{durations.totalStudyDurationMonths}</p>
                <p className="text-xs font-medium text-gray-700 uppercase tracking-wider">Total (Months)</p>
              </div>
            )}
          </div>

          {durations.treatmentPeriodDescription && (
            <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Treatment Period</p>
              <p className="text-sm text-foreground">{durations.treatmentPeriodDescription}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function formatScopeId(scopeId: string): string {
  const scopeLabels: Record<string, string> = {
    "clinicaltrials.gov": "ClinicalTrials.gov",
    "eudract": "EudraCT",
    "fda_ind": "FDA IND",
    "sponsor": "Sponsor ID",
  };
  return scopeLabels[scopeId] || scopeId?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || "Identifier";
}

function IdentifierCard({ identifier, idx, onViewSource }: { identifier: any; idx: number; onViewSource?: (page: number) => void }) {
  const [showAllData, setShowAllData] = useState(false);
  const identifierId = identifier.id || identifier.identifier || "Unknown";
  const scopeId = identifier.scopeId || identifier.identifierType?.decode || identifier.identifierType?.code || "Identifier";
  const scopeLabel = formatScopeId(scopeId);
  
  return (
    <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center border border-gray-200">
            {scopeId.includes("sponsor") || scopeLabel.includes("Sponsor") ? (
              <Building2 className="w-5 h-5 text-gray-600" />
            ) : scopeId.includes("clinical") || scopeId.includes("eudract") ? (
              <Globe className="w-5 h-5 text-gray-600" />
            ) : scopeId.includes("fda") ? (
              <FileText className="w-5 h-5 text-gray-600" />
            ) : (
              <Hash className="w-5 h-5 text-gray-600" />
            )}
          </div>
          <div>
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider block">
              {scopeLabel}
            </span>
            <p className="font-semibold text-foreground">{identifierId}</p>
            {identifier.scope?.organisationName && (
              <p className="text-sm text-muted-foreground">{identifier.scope.organisationName}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={identifier.provenance} onViewSource={onViewSource} />
          <button
            onClick={() => setShowAllData(!showAllData)}
            className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
            data-testid={`expand-identifier-${idx}`}
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
              <SmartDataRender data={identifier} onViewSource={onViewSource} editable={false} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function IdentifiersTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const identifiers = data?.studyIdentifiers || [];
  
  if (identifiers.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Hash className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study identifiers defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-3">
      {identifiers.map((identifier: any, idx: number) => (
        <IdentifierCard key={(identifier.id || identifier.identifier || "id") + idx} identifier={identifier} idx={idx} onViewSource={onViewSource} />
      ))}
    </div>
  );
}

function VersionCard({ version, idx, onViewSource }: { version: any; idx: number; onViewSource?: (page: number) => void }) {
  const [showAllData, setShowAllData] = useState(false);
  
  return (
    <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center">
            <Calendar className="w-5 h-5 text-gray-900" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-foreground">Version {version.version || version.versionNumber}</span>
              {version.publicTitle && (
                <span className="text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full">{version.publicTitle}</span>
              )}
            </div>
            {version.effectiveDate && (
              <p className="text-sm text-muted-foreground mt-1">Effective: {version.effectiveDate}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={version.provenance} onViewSource={onViewSource} />
          <button
            onClick={() => setShowAllData(!showAllData)}
            className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
            data-testid={`expand-version-${idx}`}
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
              <SmartDataRender data={version} onViewSource={onViewSource} editable={false} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function VersionsTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const versions = data?.studyProtocolVersions || [];
  
  if (versions.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Clock className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No protocol versions defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-3">
      {versions.map((version: any, idx: number) => (
        <VersionCard key={version.id || idx} version={version} idx={idx} onViewSource={onViewSource} />
      ))}
    </div>
  );
}

function AnalysesTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const interimAnalyses = data?.studyMilestones?.interimAnalyses || data?.interimAnalyses || [];

  if (interimAnalyses.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <TrendingUp className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No interim analyses defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-gray-600" />
          <h4 className="font-semibold text-foreground">Interim Analyses</h4>
        </div>
        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">{interimAnalyses.length} analyses</span>
      </div>

      {interimAnalyses.map((analysis: any, idx: number) => (
        <div key={analysis.id || idx} className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center">
                <span className="font-bold text-gray-700">{analysis.id || `IA${idx + 1}`}</span>
              </div>
              <div>
                <h5 className="font-semibold text-foreground">{analysis.name || `Interim Analysis ${idx + 1}`}</h5>
                {analysis.timing && (
                  <p className="text-sm text-muted-foreground">{analysis.timing}</p>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={analysis.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {analysis.plannedEventCount !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200 text-center">
                <p className="text-xl font-bold text-gray-900">{analysis.plannedEventCount}</p>
                <p className="text-xs font-medium text-gray-600 uppercase tracking-wider">Planned Events</p>
              </div>
            )}
            {analysis.purpose && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">Purpose</p>
                <span className={cn(
                  "text-sm font-medium px-2 py-0.5 rounded-full",
                  analysis.purpose === "Efficacy" ? "bg-green-100 text-green-700" :
                  analysis.purpose === "Futility" ? "bg-gray-100 text-gray-700" :
                  analysis.purpose === "Safety" ? "bg-red-100 text-red-700" :
                  "bg-gray-100 text-gray-700"
                )}>
                  {analysis.purpose}
                </span>
              </div>
            )}
            {analysis.alphaSpent !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200 text-center">
                <p className="text-xl font-bold text-gray-900">{(analysis.alphaSpent * 100).toFixed(1)}%</p>
                <p className="text-xs font-medium text-gray-600 uppercase tracking-wider">Alpha Spent</p>
              </div>
            )}
            {analysis.stoppingBoundary && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">Stopping Boundary</p>
                <p className="text-sm font-medium text-foreground">{analysis.stoppingBoundary}</p>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function StudyMetadataViewContent({ data, onViewSource, onFieldUpdate }: StudyMetadataViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  // Calculate counts for tabs
  const populationCount = (data?.studyPopulation?.biomarkerRequirements?.length || 0) +
    (data?.studyPopulation?.keyInclusionSummary?.values?.length || 0) +
    (data?.studyPopulation?.keyExclusionSummary?.values?.length || 0);
  const analysesCount = data?.studyMilestones?.interimAnalyses?.length || data?.interimAnalyses?.length || 0;

  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: LayoutGrid },
    { id: "design", label: "Design", icon: Shuffle },
    { id: "population", label: "Population", icon: Users, count: populationCount > 0 ? populationCount : undefined },
    { id: "milestones", label: "Milestones", icon: Timer },
    { id: "analyses", label: "Analyses", icon: TrendingUp, count: analysesCount > 0 ? analysesCount : undefined },
    { id: "identifiers", label: "Identifiers", icon: Hash, count: data.studyIdentifiers?.length || 0 },
    { id: "versions", label: "Versions", icon: Clock, count: data.studyProtocolVersions?.length || 0 },
  ];
  
  return (
    <div className="space-y-6" data-testid="study-metadata-view">
      <SummaryHeader study={data} />
      
      <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-xl overflow-x-auto" role="tablist">
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
          {activeTab === "design" && <DesignTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "population" && <PopulationTab data={data} onViewSource={onViewSource} />}
          {activeTab === "milestones" && <MilestonesTab data={data} onViewSource={onViewSource} />}
          {activeTab === "analyses" && <AnalysesTab data={data} onViewSource={onViewSource} />}
          {activeTab === "identifiers" && <IdentifiersTab data={data} onViewSource={onViewSource} />}
          {activeTab === "versions" && <VersionsTab data={data} onViewSource={onViewSource} />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export function StudyMetadataView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: StudyMetadataViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Beaker className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No study metadata available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <StudyMetadataViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
