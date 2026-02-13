import { useState, useEffect, useCallback } from "react";
import { useLocation, useSearch } from "wouter";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { motion, AnimatePresence } from "framer-motion";
import {
  Layers,
  GitBranch,
  Beaker,
  FileText,
  Timer,
  ChevronDown,
  ChevronUp,
  Sparkles,
  CheckCircle2,
  ArrowLeft,
  FlaskConical,
  TestTube,
  Repeat,
  Microscope,
  ZoomIn,
  ZoomOut,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Minimize2,
  Check,
  AlertTriangle,
  BookOpen,
  Download,
} from "lucide-react";
import { Document, Page, pdfjs } from 'react-pdf';
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  `pdfjs-dist/build/pdf.worker.min.mjs`,
  import.meta.url
).toString();

interface AgentKeyOutput {
  field: string;
  description: string;
}

interface DownstreamIntegration {
  system: string;
  useCase: string;
  automationType: string;
  fieldsUsed: string[];
  automationExample: string;
}

interface AgentDefinition {
  stageNumber: number;
  stageName: string;
  displayName: string;
  purpose: string;
  extractionMethodology: string;
  keyOutputs: AgentKeyOutput[];
  downstreamIntegrations: DownstreamIntegration[];
  automationInsights?: { insight: string; description: string }[];
  dataQualityIndicators?: string[];
  humanReviewTriggers?: string[];
}

interface Stage1Mapping {
  activityId: string;
  activityName: string;
  category: string;
  cdashDomain: string;
  cdiscCode: string;
  cdiscDecode: string;
  confidence: number;
  rationale: string;
  source: string;
}

interface Stage1Data {
  stage: number;
  stageName: string;
  success: boolean;
  mappings: Stage1Mapping[];
  metrics: {
    totalActivities: number;
    highConfidence: number;
    needsReview: number;
    cacheHits: number;
  };
  _agentDefinition?: AgentDefinition;
}

interface Stage2Component {
  id: string;
  name: string;
  isRequired: boolean;
  order: number;
  confidence: number;
  cdashDomain: string;
  provenance?: {
    source: string;
    pageNumber: number;
    textSnippet: string;
    rationale: string;
  };
}

interface Stage2Expansion {
  id: string;
  expansionType: string;
  parentActivityId: string;
  parentActivityName: string;
  components: Stage2Component[];
  confidence: number;
  rationale: string;
}

interface Stage2Data {
  stage: number;
  stageName: string;
  success: boolean;
  expansions: Stage2Expansion[];
  _agentDefinition?: AgentDefinition;
}

interface Stage4ExpandedActivity {
  id: string;
  name: string;
  instanceType: string;
  _alternativeResolution?: {
    alternativeType: string;
    confidence: number;
    rationale: string;
  };
}

interface Stage4Expansion {
  id: string;
  originalActivityId: string;
  originalActivityName: string;
  expandedActivities: Stage4ExpandedActivity[];
  confidence: number;
  alternativeType: string;
}

interface Stage4Data {
  stage: number;
  stageName: string;
  success: boolean;
  expansions: Stage4Expansion[];
  decisions: Record<string, {
    activityId: string;
    activityName: string;
    isAlternative: boolean;
    alternativeType: string | null;
    rationale: string;
  }>;
  _agentDefinition?: AgentDefinition;
}

interface ProcessingRequirement {
  stepName: string;
  stepOrder: number;
  description?: string | null;
  centrifugeSpeed?: string | null;
  centrifugeTime?: string | null;
  centrifugeTemperature?: string | null;
  timeConstraint?: string | null;
  inversionCount?: number | null;
  clottingTime?: string | null;
  aliquotCount?: number | null;
  aliquotContainer?: string | null;
  specialInstructions?: string | null;
}

interface StorageRequirement {
  storagePhase: string;
  temperature?: {
    nominal?: number | null;
    min?: number | null;
    max?: number | null;
    description?: string | null;
  };
  equipmentType?: string | null;
  maxDuration?: string | null;
  stabilityLimit?: string | null;
  monitoringRequirements?: string | null;
  excursionLimits?: string | null;
  specialInstructions?: string | null;
}

interface ShippingRequirements {
  destination?: string | null;
  shippingFrequency?: string | null;
  shippingCondition?: string | null;
  temperature?: string | null;
  packagingRequirements?: string | null;
  courierRequirements?: string | null;
}

interface Stage5Enrichment {
  id: string;
  activityId: string;
  activityName: string;
  specimenCollection: {
    specimenType?: { decode: string; code?: string };
    purpose?: { decode: string; code?: string };
    collectionVolume?: { value: number; unit: string };
    collectionContainer?: { decode: string; code?: string };
    fillVolume?: { value: number; unit: string };
    fastingRequired?: boolean;
    processingRequirements?: ProcessingRequirement[];
    storageRequirements?: StorageRequirement[];
    shippingRequirements?: ShippingRequirements;
    _specimenEnrichment?: {
      rationale: string;
      confidence: number;
      specimenCategory?: string;
      footnoteMarkers?: string[];
      pageNumbers?: number[];
    };
  };
  requiresReview?: boolean;
  confidence: number;
}

interface Stage5Data {
  stage: number;
  stageName: string;
  success: boolean;
  enrichments: Stage5Enrichment[];
  _agentDefinition?: AgentDefinition;
}

interface Stage6Condition {
  id: string;
  name: string;
  text: string;
  conditionType: { decode: string; code?: string; codeSystem?: string; instanceType?: string; codeSystemVersion?: string; id?: string };
  criterion?: Record<string, string | { decode: string; code?: string; [key: string]: any }>;
  provenance: {
    text_snippet: string;
    rationale: string;
    footnote_id: string;
    page_number?: number | null;
  };
  sourceFootnoteMarker: string;
}

interface Stage6Data {
  stage: number;
  stageName: string;
  success: boolean;
  conditions: Stage6Condition[];
  metrics: {
    footnotesAnalyzed: number;
    conditionsCreated: number;
  };
  _agentDefinition?: AgentDefinition;
}

interface Stage8Provenance {
  pageNumber?: number;
  tableId?: string;
  colIdx?: number;
}

interface Stage8Expansion {
  id: string;
  originalEncounterId: string;
  originalName: string;
  originalRecurrence: {
    pattern: string;
    type: string;
    startCycle?: number;
    endCycle?: number;
    provenance?: Stage8Provenance;
  };
  expandedEncounterCount: number;
  expandedEncounterIds: string[];
  expandedCycleNumbers: number[];
  saiDuplicationCount: number;
  expandedSaiIds: string[];
  confidence: number;
  source: string;
  rationale: string;
  requiresReview: boolean;
  reviewReason?: string | null;
  provenance?: Stage8Provenance;
}

interface Stage8Decision {
  encounterName: string;
  recurrenceKey?: string;
  shouldExpand: boolean;
  expandedCycles?: number[];
  patternType: string;
  cycleLengthDays: number;
  confidence: number;
  rationale: string;
  source?: string;
  requiresHumanReview: boolean;
  reviewReason?: string | null;
  provenance?: Stage8Provenance | null;
}

interface Stage8Data {
  stage: number;
  stageName: string;
  success: boolean;
  expansions: Stage8Expansion[];
  decisions: Record<string, Stage8Decision>;
  metrics: {
    encountersProcessed: number;
    encountersExpanded: number;
    saisProcessed: number;
    saisDuplicated: number;
    cacheHits: number;
    llmCalls: number;
    expansionRate: number;
  };
  _agentDefinition?: AgentDefinition;
}

interface Stage9Decision {
  activityId: string;
  activityName: string;
  domain?: string | null;
  matchedModules: string[];
  matchRationale?: Record<string, string>;
  confidence: number;
  source?: string;
  requiresHumanReview?: boolean;
}

interface Stage9Metrics {
  totalActivitiesProcessed: number;
  activitiesEnriched: number;
  activitiesNoMatch: number;
  modulesUsed: Record<string, number>;
  cacheHits: number;
  llmCalls: number;
  avgConfidence: number;
}

interface Stage9Data {
  stage: number;
  stageName: string;
  success: boolean;
  decisions: Record<string, Stage9Decision>;
  metrics?: Stage9Metrics;
  _agentDefinition?: AgentDefinition;
}

interface StageConfig {
  id: string;
  label: string;
  icon: React.ElementType;
  color: string;
  description: string;
}

const STAGES: StageConfig[] = [
  { id: "domains", label: "Domain Mapping", icon: Layers, color: "blue", description: "CDISC domain categorization" },
  { id: "expansion", label: "Activity Expansion", icon: GitBranch, color: "green", description: "Component discovery" },
  { id: "alternatives", label: "Alternatives", icon: GitBranch, color: "amber", description: "Alternative resolution" },
  { id: "specimens", label: "Specimens", icon: TestTube, color: "purple", description: "Biospecimen enrichment" },
  { id: "conditions", label: "Conditions", icon: FileText, color: "red", description: "Footnote conditions" },
  { id: "cycles", label: "Cycles", icon: Repeat, color: "cyan", description: "Cycle expansion" },
  { id: "mining", label: "Protocol Mining", icon: Microscope, color: "indigo", description: "Module matching" },
];

// PDF_URL will be determined dynamically in the component based on studyId

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const percent = Math.round(confidence * 100);
  const color = percent >= 95 ? "bg-gray-100 text-gray-900" :
                percent >= 80 ? "bg-gray-100 text-gray-700" :
                               "bg-gray-100 text-gray-600";
  return (
    <span className={cn("px-2 py-0.5 text-xs font-medium rounded-full", color)}>
      {percent}%
    </span>
  );
}

function MetricCard({ value, label, color = "blue" }: { value: number | string; label: string; color?: string }) {
  const colorClasses: Record<string, string> = {
    blue: "text-gray-800",
    green: "text-gray-800",
    amber: "text-gray-700",
    purple: "text-gray-700",
    red: "text-gray-600",
    cyan: "text-gray-700",
  };
  
  return (
    <div className="metric-card" data-testid={`metric-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <p className={cn("metric-value", colorClasses[color] || colorClasses.blue)}>{value}</p>
      <p className="metric-label">{label}</p>
    </div>
  );
}

function AgentDefinitionCard({ agent, color = "blue" }: { agent: AgentDefinition | undefined; color?: string }) {
  const [expanded, setExpanded] = useState(false);
  
  if (!agent) return null;
  
  const colorClasses: Record<string, { bg: string; border: string; text: string; icon: string }> = {
    blue: { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-900", icon: "bg-gray-100 text-gray-800" },
    green: { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-900", icon: "bg-gray-100 text-gray-800" },
    amber: { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: "bg-gray-100 text-gray-700" },
    purple: { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: "bg-gray-200 text-gray-700" },
    red: { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-600", icon: "bg-gray-100 text-gray-600" },
    cyan: { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: "bg-gray-100 text-gray-700" },
    indigo: { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700", icon: "bg-gray-200 text-gray-700" },
  };
  
  const colors = colorClasses[color] || colorClasses.blue;
  
  return (
    <div className={cn("rounded-2xl border p-5 mb-6", colors.bg, colors.border)} data-testid="agent-definition-card">
      <div className="flex items-start gap-4">
        <div className={cn("w-12 h-12 rounded-xl flex items-center justify-center shrink-0", colors.icon)}>
          <Sparkles className="w-6 h-6" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-3 mb-2">
            <h3 className="text-lg font-semibold text-foreground">{agent.displayName}</h3>
            <Badge variant="outline" className="rounded-full text-xs shrink-0">Stage {agent.stageNumber}</Badge>
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed mb-4">{agent.purpose}</p>
          
          <Collapsible open={expanded} onOpenChange={setExpanded}>
            <CollapsibleTrigger className="w-full">
              <div className="flex items-center justify-between p-3 rounded-xl bg-white/60 border border-gray-100 hover:bg-white transition-colors cursor-pointer">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                  <BookOpen className="w-4 h-4" />
                  <span>View Details</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{agent.keyOutputs.length} outputs</span>
                  <span className="text-gray-300">•</span>
                  <span>{agent.downstreamIntegrations.length} integrations</span>
                  {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </div>
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="mt-4 space-y-4">
                <div>
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Key Outputs</h4>
                  <div className="grid grid-cols-2 gap-2">
                    {agent.keyOutputs.map((output, idx) => (
                      <div key={idx} className="p-3 rounded-xl bg-white border text-sm">
                        <span className="font-mono text-xs text-gray-500">{output.field}</span>
                        <p className="text-xs text-muted-foreground mt-1">{output.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div>
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Downstream Integrations</h4>
                  <div className="space-y-2">
                    {agent.downstreamIntegrations.map((integration, idx) => (
                      <div key={idx} className="p-3 rounded-xl bg-white border">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium text-sm">{integration.system}</span>
                          <Badge variant="secondary" className="text-xs rounded-full">{integration.automationType.replace(/_/g, ' ')}</Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">{integration.useCase}</p>
                      </div>
                    ))}
                  </div>
                </div>
                
                {agent.automationInsights && agent.automationInsights.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Automation Insights</h4>
                    <div className="flex flex-wrap gap-2">
                      {agent.automationInsights.map((insight, idx) => (
                        <span key={idx} className="px-3 py-1.5 rounded-full bg-white border text-xs">
                          <span className="font-medium">{insight.insight}:</span> {insight.description}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </div>
    </div>
  );
}

function InsightCard({ 
  title, 
  description, 
  icon: Icon, 
  children, 
  count,
  color = "blue"
}: { 
  title: string; 
  description?: string; 
  icon: React.ElementType; 
  children: React.ReactNode;
  count?: number;
  color?: string;
}) {
  const iconColors: Record<string, string> = {
    blue: "bg-gray-100 text-gray-800",
    green: "bg-gray-100 text-gray-800",
    amber: "bg-gray-100 text-gray-700",
    purple: "bg-gray-200 text-gray-700",
    red: "bg-gray-100 text-gray-600",
    cyan: "bg-gray-100 text-gray-700",
    indigo: "bg-gray-200 text-gray-700",
  };

  return (
    <div className="insight-card">
      <div className="insight-card-header">
        <div className="flex items-center gap-3">
          <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", iconColors[color])}>
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sf-headline text-foreground">{title}</h3>
            {description && <p className="text-sf-caption text-muted-foreground">{description}</p>}
          </div>
        </div>
        {count !== undefined && (
          <Badge variant="secondary" className="rounded-full px-3 py-1 text-sm font-medium">
            {count}
          </Badge>
        )}
      </div>
      <div className="insight-card-content">{children}</div>
    </div>
  );
}

function DomainMappingPanel({ data, onViewSource }: { data: Stage1Data | null; onViewSource: (page: number) => void }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  
  if (!data) return <LoadingState />;
  
  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) newExpanded.delete(id);
    else newExpanded.add(id);
    setExpanded(newExpanded);
  };

  const groupedByDomain = data.mappings.reduce((acc, m) => {
    if (!acc[m.cdashDomain]) acc[m.cdashDomain] = [];
    acc[m.cdashDomain].push(m);
    return acc;
  }, {} as Record<string, Stage1Mapping[]>);

  return (
    <div className="space-y-6 page-transition">
      <AgentDefinitionCard agent={data._agentDefinition} color="blue" />

      <div className="space-y-4">
        {Object.entries(groupedByDomain).map(([domain, mappings]) => (
          <InsightCard 
            key={domain} 
            title={domain}
            description={mappings[0]?.category.replace(/_/g, ' ')}
            icon={Layers}
            count={mappings.length}
            color="blue"
          >
            <div className="space-y-2">
              {mappings.map((m) => (
                <Collapsible key={m.activityId} open={expanded.has(m.activityId)} onOpenChange={() => toggleExpanded(m.activityId)}>
                  <CollapsibleTrigger className="w-full" data-testid={`item-${m.activityId}`}>
                    <div className={cn("collapsible-item", expanded.has(m.activityId) && "expanded")}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="font-medium text-sm">{m.activityName}</span>
                          <Badge variant="outline" className="text-xs rounded-full">{m.cdiscDecode}</Badge>
                        </div>
                        <div className="flex items-center gap-2">
                          <ConfidenceBadge confidence={m.confidence} />
                          {expanded.has(m.activityId) ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                        </div>
                      </div>
                    </div>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className="mt-3 p-4 rounded-xl bg-gray-50/50 border border-gray-200">
                      <div className="flex items-start gap-3">
                        <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                        <div className="flex-1">
                          <p className="text-xs font-medium text-gray-900 mb-2">AI Rationale</p>
                          <p className="text-sm text-gray-800 leading-relaxed">{m.rationale}</p>
                          <div className="flex items-center gap-2 mt-3 flex-wrap">
                            <span className="provenance-chip">Code: {m.cdiscCode}</span>
                            <span className="provenance-chip">Source: {m.source}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              ))}
            </div>
          </InsightCard>
        ))}
      </div>
    </div>
  );
}

function ActivityExpansionPanel({ data, onViewSource }: { data: Stage2Data | null; onViewSource: (page: number) => void }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  
  if (!data) return <LoadingState />;
  
  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) newExpanded.delete(id);
    else newExpanded.add(id);
    setExpanded(newExpanded);
  };

  return (
    <div className="space-y-6 page-transition">
      <AgentDefinitionCard agent={data._agentDefinition} color="green" />

      <div className="space-y-4">
        {data.expansions.map((expansion) => (
          <InsightCard
            key={expansion.id}
            title={expansion.parentActivityName}
            description={`${expansion.components.length} components discovered`}
            icon={GitBranch}
            count={expansion.components.length}
            color="green"
          >
            <Collapsible open={expanded.has(expansion.id)} onOpenChange={() => toggleExpanded(expansion.id)}>
              <CollapsibleTrigger className="w-full" data-testid={`expansion-${expansion.id}`}>
                <div className={cn("collapsible-item", expanded.has(expansion.id) && "expanded")}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-gray-700" />
                      <span className="text-sm text-gray-700">{expansion.rationale}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <ConfidenceBadge confidence={expansion.confidence} />
                      {expanded.has(expansion.id) ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                    </div>
                  </div>
                </div>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="mt-3 space-y-2">
                  {expansion.components.slice(0, 10).map((comp, idx) => (
                    <div key={comp.id} className="flex items-center justify-between p-3 bg-white rounded-xl border text-sm">
                      <div className="flex items-center gap-3">
                        <span className="w-6 h-6 rounded-full bg-gray-100 text-gray-800 flex items-center justify-center text-xs font-medium">{idx + 1}</span>
                        <span className="font-medium">{comp.name}</span>
                        <Badge variant="outline" className="text-xs rounded-full">{comp.cdashDomain}</Badge>
                      </div>
                      <div className="flex items-center gap-2">
                        {comp.provenance?.pageNumber && (
                          <button 
                            onClick={(e) => { e.stopPropagation(); onViewSource(comp.provenance!.pageNumber!); }}
                            className="provenance-chip cursor-pointer hover:bg-gray-100 hover:text-gray-900 transition-colors"
                          >
                            View Page {comp.provenance.pageNumber}
                          </button>
                        )}
                        <ConfidenceBadge confidence={comp.confidence} />
                      </div>
                    </div>
                  ))}
                  {expansion.components.length > 10 && (
                    <p className="text-xs text-center text-muted-foreground py-2">
                      +{expansion.components.length - 10} more components
                    </p>
                  )}
                </div>
              </CollapsibleContent>
            </Collapsible>
          </InsightCard>
        ))}
      </div>
    </div>
  );
}

function AlternativesPanel({ data, onViewSource }: { data: Stage4Data | null; onViewSource: (page: number) => void }) {
  if (!data) return <LoadingState />;

  return (
    <div className="space-y-6 page-transition">
      <AgentDefinitionCard agent={data._agentDefinition} color="amber" />

      <div className="space-y-4">
        {data.expansions.map((expansion) => (
          <InsightCard
            key={expansion.id}
            title={expansion.originalActivityName}
            description={expansion.alternativeType.replace(/_/g, ' ')}
            icon={GitBranch}
            color="amber"
          >
            <div className="space-y-3">
              <div className="p-4 rounded-xl bg-gray-50/50 border border-gray-200">
                <div className="flex items-start gap-3">
                  <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-xs font-medium text-gray-900 mb-2">AI Decision</p>
                    <p className="text-sm text-gray-800">{data.decisions[expansion.originalActivityId]?.rationale}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                {expansion.expandedActivities.map((act, idx) => (
                  <div key={act.id} className="flex items-center justify-between p-3 bg-white rounded-xl border">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center text-gray-700 font-medium text-sm">
                        {idx + 1}
                      </div>
                      <span className="font-medium text-sm">{act.name}</span>
                    </div>
                    {act._alternativeResolution && (
                      <ConfidenceBadge confidence={act._alternativeResolution.confidence} />
                    )}
                  </div>
                ))}
              </div>
            </div>
          </InsightCard>
        ))}
      </div>
    </div>
  );
}

function SpecimensPanel({ data, onViewSource }: { data: Stage5Data | null; onViewSource: (page: number) => void }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  
  if (!data) return <LoadingState />;
  
  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) newExpanded.delete(id);
    else newExpanded.add(id);
    setExpanded(newExpanded);
  };

  const needsReviewCount = data.enrichments.filter(e => e.requiresReview).length;

  return (
    <div className="space-y-6 page-transition">
      <AgentDefinitionCard agent={data._agentDefinition} color="purple" />

      <div className="space-y-4">
        {data.enrichments.map((enrichment) => {
          const spec = enrichment.specimenCollection;
          return (
            <InsightCard
              key={enrichment.id}
              title={enrichment.activityName}
              description={spec?.specimenType?.decode || "Unknown specimen"}
              icon={TestTube}
              color={enrichment.requiresReview ? "amber" : "purple"}
            >
              <Collapsible open={expanded.has(enrichment.id)} onOpenChange={() => toggleExpanded(enrichment.id)}>
                <CollapsibleTrigger className="w-full" data-testid={`specimen-${enrichment.id}`}>
                  <div className={cn("collapsible-item", expanded.has(enrichment.id) && "expanded")}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 flex-wrap">
                        {spec?.purpose?.decode && (
                          <span className="provenance-chip">{spec.purpose.decode}</span>
                        )}
                        {spec?.collectionVolume && (
                          <span className="provenance-chip">
                            {spec.collectionVolume.value} {spec.collectionVolume.unit}
                          </span>
                        )}
                        {spec?.collectionContainer?.decode && (
                          <span className="provenance-chip">{spec.collectionContainer.decode}</span>
                        )}
                        {spec?.fastingRequired && (
                          <span className="provenance-chip bg-gray-100 text-gray-700">Fasting Required</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <ConfidenceBadge confidence={enrichment.confidence} />
                        {expanded.has(enrichment.id) ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                      </div>
                    </div>
                  </div>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="mt-3 space-y-3">
                    {/* Collection Details */}
                    <div className="p-4 rounded-xl bg-gray-50 border">
                      <p className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-3">Collection Details</p>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        {spec?.specimenType?.decode && (
                          <div>
                            <span className="text-muted-foreground">Specimen Type:</span>
                            <span className="ml-2 font-medium">{spec.specimenType.decode}</span>
                          </div>
                        )}
                        {spec?.purpose?.decode && (
                          <div>
                            <span className="text-muted-foreground">Purpose:</span>
                            <span className="ml-2 font-medium">{spec.purpose.decode}</span>
                          </div>
                        )}
                        {spec?.collectionContainer?.decode && (
                          <div>
                            <span className="text-muted-foreground">Container:</span>
                            <span className="ml-2 font-medium">{spec.collectionContainer.decode}</span>
                          </div>
                        )}
                        {spec?.collectionVolume && (
                          <div>
                            <span className="text-muted-foreground">Volume:</span>
                            <span className="ml-2 font-medium">{spec.collectionVolume.value} {spec.collectionVolume.unit}</span>
                          </div>
                        )}
                        {spec?.fillVolume && (
                          <div>
                            <span className="text-muted-foreground">Fill Volume:</span>
                            <span className="ml-2 font-medium">{spec.fillVolume.value} {spec.fillVolume.unit}</span>
                          </div>
                        )}
                        <div>
                          <span className="text-muted-foreground">Fasting:</span>
                          <span className="ml-2 font-medium">{spec?.fastingRequired ? "Required" : "Not Required"}</span>
                        </div>
                      </div>
                    </div>

                    {/* Processing Requirements */}
                    {spec?.processingRequirements && spec.processingRequirements.length > 0 && (
                      <div className="p-4 rounded-xl bg-gray-50/50 border border-gray-200">
                        <p className="text-xs font-medium text-gray-900 uppercase tracking-wide mb-3">Processing Steps</p>
                        <div className="space-y-2">
                          {spec.processingRequirements.map((step, idx) => (
                            <div key={idx} className="flex items-start gap-3 p-2 bg-white rounded-lg border">
                              <div className="w-6 h-6 rounded-full bg-gray-100 text-gray-800 flex items-center justify-center text-xs font-medium shrink-0">
                                {step.stepOrder}
                              </div>
                              <div className="flex-1 text-sm">
                                <p className="font-medium text-gray-800">{step.stepName}</p>
                                {step.timeConstraint && (
                                  <p className="text-gray-800 text-xs mt-1">{step.timeConstraint}</p>
                                )}
                                {step.centrifugeSpeed && (
                                  <p className="text-muted-foreground text-xs">Speed: {step.centrifugeSpeed}</p>
                                )}
                                {step.centrifugeTime && (
                                  <p className="text-muted-foreground text-xs">Duration: {step.centrifugeTime}</p>
                                )}
                                {step.centrifugeTemperature && (
                                  <p className="text-muted-foreground text-xs">Temp: {step.centrifugeTemperature}</p>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Storage Requirements */}
                    {spec?.storageRequirements && spec.storageRequirements.length > 0 && (
                      <div className="p-4 rounded-xl bg-gray-50/50 border border-gray-200">
                        <p className="text-xs font-medium text-gray-900 uppercase tracking-wide mb-3">Storage Requirements</p>
                        <div className="space-y-2">
                          {spec.storageRequirements.map((storage, idx) => (
                            <div key={idx} className="flex items-center gap-3 p-2 bg-white rounded-lg border text-sm">
                              <div className="font-medium text-gray-800 capitalize">{storage.storagePhase.replace(/_/g, ' ')}</div>
                              {storage.temperature?.nominal !== undefined && storage.temperature.nominal !== null && (
                                <span className="provenance-chip bg-gray-100 text-gray-700">{storage.temperature.nominal}°C</span>
                              )}
                              {storage.temperature?.description && (
                                <span className="text-muted-foreground text-xs capitalize">({storage.temperature.description})</span>
                              )}
                              {storage.equipmentType && (
                                <span className="text-muted-foreground text-xs capitalize">{storage.equipmentType.replace(/_/g, ' ')}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Shipping Requirements */}
                    {spec?.shippingRequirements?.destination && (
                      <div className="p-4 rounded-xl bg-gray-50/50 border border-gray-200">
                        <p className="text-xs font-medium text-gray-900 uppercase tracking-wide mb-3">Shipping</p>
                        <div className="grid grid-cols-2 gap-3 text-sm">
                          <div>
                            <span className="text-muted-foreground">Destination:</span>
                            <span className="ml-2 font-medium text-gray-800">{spec.shippingRequirements.destination}</span>
                          </div>
                          {spec.shippingRequirements.shippingCondition && (
                            <div>
                              <span className="text-muted-foreground">Condition:</span>
                              <span className="ml-2 font-medium">{spec.shippingRequirements.shippingCondition}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* AI Rationale */}
                    {spec?._specimenEnrichment && (
                      <div className="p-4 rounded-xl bg-gray-50/50 border border-gray-200">
                        <div className="flex items-start gap-3">
                          <Sparkles className="w-4 h-4 text-gray-600 mt-0.5 shrink-0" />
                          <div className="flex-1">
                            <p className="text-xs font-medium text-gray-900 mb-2">AI Rationale</p>
                            <p className="text-sm text-gray-700 leading-relaxed">{spec._specimenEnrichment.rationale}</p>
                            <div className="flex items-center gap-2 mt-3 flex-wrap">
                              {spec._specimenEnrichment.specimenCategory && (
                                <span className="provenance-chip">Category: {spec._specimenEnrichment.specimenCategory}</span>
                              )}
                              {spec._specimenEnrichment.footnoteMarkers && spec._specimenEnrichment.footnoteMarkers.length > 0 && (
                                <span className="provenance-chip">Footnotes: {spec._specimenEnrichment.footnoteMarkers.join(', ')}</span>
                              )}
                              {spec._specimenEnrichment.pageNumbers && spec._specimenEnrichment.pageNumbers.length > 0 && (
                                <button 
                                  onClick={(e) => { e.stopPropagation(); onViewSource(spec._specimenEnrichment!.pageNumbers![0]); }}
                                  className="provenance-chip cursor-pointer hover:bg-gray-100 hover:text-gray-900 transition-colors"
                                >
                                  View Page {spec._specimenEnrichment.pageNumbers[0]}
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            </InsightCard>
          );
        })}
      </div>
    </div>
  );
}

function ConditionsPanel({ data, onViewSource }: { data: Stage6Data | null; onViewSource: (page: number) => void }) {
  if (!data) return <LoadingState />;

  return (
    <div className="space-y-6 page-transition">
      <AgentDefinitionCard agent={data._agentDefinition} color="red" />

      <div className="space-y-4">
        {data.conditions.map((condition) => (
          <InsightCard
            key={condition.id}
            title={condition.name}
            description={condition.conditionType?.decode ?? 'Unknown'}
            icon={FileText}
            color="red"
          >
            <div className="space-y-3">
              <div className="p-4 rounded-xl bg-gray-50 border">
                <p className="text-sm text-gray-700 leading-relaxed">{condition.text}</p>
              </div>

              {/* Criteria Display */}
              {condition.criterion && Object.keys(condition.criterion).length > 0 && (
                <div className="p-4 rounded-xl bg-white border border-gray-200">
                  <p className="text-xs font-medium text-gray-900 mb-3">Criteria</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(condition.criterion).map(([key, value]) => (
                      <div key={key} className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg border text-sm">
                        <span className="font-medium text-gray-800 capitalize">{key}:</span>
                        <span className="text-gray-600">{typeof value === 'object' && value !== null ? (value as any).decode ?? JSON.stringify(value) : String(value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="p-4 rounded-xl bg-gray-50/50 border border-gray-200">
                <div className="flex items-start gap-3">
                  <Sparkles className="w-4 h-4 text-gray-600 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-xs font-medium text-gray-900 mb-2">AI Rationale</p>
                    <p className="text-sm text-gray-600">{condition.provenance.rationale}</p>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="provenance-chip">Footnote: {condition.sourceFootnoteMarker}</span>
                {condition.provenance.page_number && (
                  <button 
                    onClick={() => onViewSource(condition.provenance.page_number!)}
                    className="provenance-chip cursor-pointer hover:bg-gray-200 hover:text-gray-900 transition-colors"
                  >
                    View Page {condition.provenance.page_number}
                  </button>
                )}
              </div>
            </div>
          </InsightCard>
        ))}
      </div>
    </div>
  );
}

function CyclesPanel({ data, onViewSource }: { data: Stage8Data | null; onViewSource: (page: number) => void }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  
  if (!data) return <LoadingState />;
  
  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) newExpanded.delete(id);
    else newExpanded.add(id);
    setExpanded(newExpanded);
  };

  return (
    <div className="space-y-6 page-transition">
      <AgentDefinitionCard agent={data._agentDefinition} color="cyan" />

      {data.expansions.length > 0 && (
        <InsightCard
          title="Cycle Expansions"
          description={`${data.expansions.length} encounters expanded`}
          icon={Repeat}
          count={data.expansions.length}
          color="cyan"
        >
          <div className="space-y-3">
            {data.expansions.map((exp) => (
              <Collapsible key={exp.id} open={expanded.has(exp.id)} onOpenChange={() => toggleExpanded(exp.id)}>
                <CollapsibleTrigger className="w-full" data-testid={`cycle-${exp.id}`}>
                  <div className={cn("collapsible-item", expanded.has(exp.id) && "expanded")}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="font-medium text-sm">{exp.originalName}</span>
                        <Badge variant="outline" className="text-xs rounded-full">{exp.expandedEncounterCount} encounters</Badge>
                        {exp.requiresReview && (
                          <Badge variant="outline" className="text-xs rounded-full text-gray-600 border-gray-400">Review</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <ConfidenceBadge confidence={exp.confidence} />
                        {expanded.has(exp.id) ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                      </div>
                    </div>
                  </div>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="mt-3 space-y-3">
                    <div className="p-4 rounded-xl bg-gray-50/50 border border-gray-200">
                      <div className="flex items-start gap-3">
                        <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                        <div>
                          <p className="text-xs font-medium text-gray-900 mb-2">AI Rationale</p>
                          <p className="text-sm text-gray-800">{exp.rationale}</p>
                        </div>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="p-3 rounded-xl bg-gray-50 border">
                        <p className="text-xs font-medium text-gray-600 mb-2">Recurrence Pattern</p>
                        <p className="text-sm font-mono">{exp.originalRecurrence.pattern}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          Cycles {exp.originalRecurrence.startCycle} - {exp.originalRecurrence.endCycle}
                        </p>
                      </div>
                      <div className="p-3 rounded-xl bg-gray-50 border">
                        <p className="text-xs font-medium text-gray-600 mb-2">Expansion Results</p>
                        <p className="text-sm">{exp.expandedEncounterCount} encounters created</p>
                        <p className="text-xs text-muted-foreground mt-1">{exp.saiDuplicationCount} SAIs duplicated</p>
                      </div>
                    </div>
                    {exp.provenance?.pageNumber && (
                      <button 
                        onClick={() => onViewSource(exp.provenance!.pageNumber!)}
                        className="provenance-chip cursor-pointer"
                      >
                        View Page {exp.provenance.pageNumber}
                      </button>
                    )}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            ))}
          </div>
        </InsightCard>
      )}

      {Object.keys(data.decisions).length > 0 && (
        <InsightCard
          title="AI Decisions"
          description="Pattern analysis results"
          icon={Sparkles}
          count={Object.keys(data.decisions).length}
          color="indigo"
        >
          <div className="space-y-2">
            {Object.entries(data.decisions).slice(0, 5).map(([encId, decision]) => (
              <div key={encId} className="p-4 rounded-xl bg-gray-50 border">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-sm">{decision.encounterName}</span>
                  <div className="flex items-center gap-2">
                    {decision.shouldExpand ? (
                      <Badge className="bg-gray-100 text-gray-900 text-xs">Will Expand</Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs">No Expansion</Badge>
                    )}
                    <ConfidenceBadge confidence={decision.confidence} />
                  </div>
                </div>
                <p className="text-sm text-muted-foreground">{decision.rationale}</p>
                {decision.requiresHumanReview && (
                  <div className="mt-2 flex items-center gap-2 text-gray-600">
                    <AlertTriangle className="w-3 h-3" />
                    <span className="text-xs">{decision.reviewReason}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </InsightCard>
      )}
    </div>
  );
}

function ProtocolMiningPanel({ data, onViewSource }: { data: Stage9Data | null; onViewSource: (page: number) => void }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  
  if (!data) return <LoadingState />;
  
  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) newExpanded.delete(id);
    else newExpanded.add(id);
    setExpanded(newExpanded);
  };

  const decisions = Object.values(data.decisions);
  const metrics = data.metrics;

  return (
    <div className="space-y-6 page-transition">
      <AgentDefinitionCard agent={data._agentDefinition} color="indigo" />
      
      <InsightCard
        title="Module Matching"
        description="Activities matched to protocol modules"
        icon={Microscope}
        count={decisions.length}
        color="indigo"
      >
        <div className="space-y-2">
          {decisions.map((decision) => (
            <Collapsible 
              key={decision.activityId} 
              open={expanded.has(decision.activityId)} 
              onOpenChange={() => toggleExpanded(decision.activityId)}
            >
              <CollapsibleTrigger className="w-full" data-testid={`mining-${decision.activityId}`}>
                <div className={cn("collapsible-item", expanded.has(decision.activityId) && "expanded")}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-medium text-sm">{decision.activityName}</span>
                      <div className="flex items-center gap-1">
                        {decision.matchedModules.slice(0, 2).map((mod) => (
                          <Badge key={mod} variant="outline" className="text-xs rounded-full">{mod}</Badge>
                        ))}
                        {decision.matchedModules.length > 2 && (
                          <Badge variant="secondary" className="text-xs rounded-full">+{decision.matchedModules.length - 2}</Badge>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <ConfidenceBadge confidence={decision.confidence} />
                      {expanded.has(decision.activityId) ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                    </div>
                  </div>
                </div>
              </CollapsibleTrigger>
              <CollapsibleContent>
                {decision.matchRationale && Object.keys(decision.matchRationale).length > 0 && (
                  <div className="mt-3 space-y-2">
                    {Object.entries(decision.matchRationale).map(([module, rationale]) => (
                      <div key={module} className="p-3 rounded-xl bg-gray-50/50 border border-gray-200">
                        <p className="text-xs font-medium text-gray-900 mb-1">{module}</p>
                        <p className="text-sm text-gray-700">{rationale}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CollapsibleContent>
            </Collapsible>
          ))}
        </div>
      </InsightCard>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-sm text-muted-foreground">Loading insights...</p>
      </div>
    </div>
  );
}

export default function InsightsReviewShell() {
  const [, navigate] = useLocation();
  const searchString = useSearch();
  
  // Get studyId from URL params and determine PDF URL - NO hardcoded default
  const searchParams = new URLSearchParams(searchString);
  const studyId = searchParams.get('studyId') || searchParams.get('protocolId') || null;
  const pdfUrl = studyId ? `/api/protocols/${encodeURIComponent(studyId)}/pdf/annotated` : '';
  
  const [activeStage, setActiveStage] = useState("domains");
  const [stage1Data, setStage1Data] = useState<Stage1Data | null>(null);
  const [stage2Data, setStage2Data] = useState<Stage2Data | null>(null);
  const [stage4Data, setStage4Data] = useState<Stage4Data | null>(null);
  const [stage5Data, setStage5Data] = useState<Stage5Data | null>(null);
  const [stage6Data, setStage6Data] = useState<Stage6Data | null>(null);
  const [stage8Data, setStage8Data] = useState<Stage8Data | null>(null);
  const [stage9Data, setStage9Data] = useState<Stage9Data | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1.0);
  const [pdfExpanded, setPdfExpanded] = useState(false);
  const [contentExpanded, setContentExpanded] = useState(false);
  const { toast } = useToast();

  const getActiveStageData = () => {
    const stageDataMap: Record<string, { data: unknown; label: string; filename: string }> = {
      domains: { data: stage1Data, label: "Domain Mapping", filename: "domain_categorization" },
      expansion: { data: stage2Data, label: "Activity Expansion", filename: "activity_expansion" },
      alternatives: { data: stage4Data, label: "Alternatives", filename: "alternative_resolution" },
      specimens: { data: stage5Data, label: "Specimens", filename: "specimen_enrichment" },
      conditions: { data: stage6Data, label: "Conditions", filename: "conditional_expansion" },
      cycles: { data: stage8Data, label: "Cycles", filename: "cycle_expansion" },
      mining: { data: stage9Data, label: "Protocol Mining", filename: "protocol_mining" },
    };
    return stageDataMap[activeStage] || { data: null, label: "Unknown", filename: "unknown" };
  };

  const handleExportInterpretation = async () => {
    try {
      const { data, label, filename } = getActiveStageData();
      
      if (!data) {
        toast({
          title: "No Data Available",
          description: `No data loaded for ${label}`,
          variant: "destructive",
          duration: 3000,
        });
        return;
      }
      
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = `${filename}_export.json`;
      window.document.body.appendChild(link);
      link.click();
      window.document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      toast({
        title: "Export Successful",
        description: `Downloaded ${filename}_export.json`,
        duration: 3000,
      });
    } catch (err) {
      console.error("Export failed:", err);
      toast({
        title: "Export Failed",
        description: "Could not export interpretation data",
        variant: "destructive",
        duration: 3000,
      });
    }
  };

  const [dataSource, setDataSource] = useState<'database' | 'static' | null>(null);

  useEffect(() => {
    async function loadAllData() {
      if (!studyId) return;

      try {
        // First, try to fetch from the database API
        const latestJob = await api.soa.getLatestJob(studyId);

        if (latestJob?.job_id) {
          // Fetch interpretation stages from database
          const stagesResponse = await api.soa.getInterpretationStages(latestJob.job_id);

          if (stagesResponse?.groups && stagesResponse.groups.length > 0) {
            // Use the first group's stage results (or merge all groups)
            const groupData = stagesResponse.groups[0];
            const stageResults = groupData.stage_results || {};

            // Transform stage results to expected format
            if (stageResults['1']) {
              setStage1Data(stageResults['1'] as Stage1Data);
            }
            if (stageResults['2']) {
              setStage2Data(stageResults['2'] as Stage2Data);
            }
            if (stageResults['4']) {
              setStage4Data(stageResults['4'] as Stage4Data);
            }
            if (stageResults['5']) {
              setStage5Data(stageResults['5'] as Stage5Data);
            }
            if (stageResults['6']) {
              setStage6Data(stageResults['6'] as Stage6Data);
            }
            if (stageResults['8']) {
              setStage8Data(stageResults['8'] as Stage8Data);
            }
            if (stageResults['9']) {
              setStage9Data(stageResults['9'] as Stage9Data);
            }

            setDataSource('database');
            console.log('[InsightsReviewShell] Loaded stage data from database');
            return;
          }
        }
      } catch (err) {
        console.log('[InsightsReviewShell] Database fetch failed, trying static files:', err);
      }

      // Fallback to static files
      try {
        const isM14359 = studyId.includes('M14-359') || studyId.includes('NCT02264990');
        const prefix = isM14359 ? 'M14-359_' : '';

        const fetchJson = async (path: string): Promise<unknown | null> => {
          try {
            const res = await fetch(path);
            if (res.ok) {
              const contentType = res.headers.get('content-type');
              if (contentType && contentType.includes('application/json')) {
                return res.json();
              }
            }
          } catch {}
          return null;
        };

        const fetchWithFallback = async (studyPath: string, defaultPath: string) => {
          if (prefix) {
            const studyData = await fetchJson(studyPath);
            if (studyData) return studyData;
          }
          return fetchJson(defaultPath);
        };

        const [s1, s2, s4, s5, s6, s8, s9] = await Promise.all([
          fetchWithFallback(`/data/${prefix}stage01_domain_categorization.json`, '/data/stage01_domain_categorization.json'),
          fetchWithFallback(`/data/${prefix}stage02_activity_expansion.json`, '/data/stage02_activity_expansion.json'),
          fetchWithFallback(`/data/${prefix}stage04_alternative_resolution.json`, '/data/stage04_alternative_resolution.json'),
          fetchWithFallback(`/data/${prefix}stage05_specimen_enrichment.json`, '/data/stage05_specimen_enrichment.json'),
          fetchWithFallback(`/data/${prefix}stage06_conditional_expansion.json`, '/data/stage06_conditional_expansion.json'),
          fetchWithFallback(`/data/${prefix}stage08_cycle_expansion.json`, '/data/stage08_cycle_expansion.json'),
          fetchWithFallback(`/data/${prefix}stage09_protocol_mining.json`, '/data/stage09_protocol_mining.json'),
        ]);

        setStage1Data(s1 as Stage1Data);
        setStage2Data(s2 as Stage2Data);
        setStage4Data(s4 as Stage4Data);
        setStage5Data(s5 as Stage5Data);
        setStage6Data(s6 as Stage6Data);
        setStage8Data(s8 as Stage8Data);
        setStage9Data(s9 as Stage9Data);
        setDataSource('static');
        console.log('[InsightsReviewShell] Loaded stage data from static files');
      } catch (err) {
        console.error('[InsightsReviewShell] Failed to load stage data:', err);
      }
    }
    loadAllData();
  }, [studyId]);

  const getStageCount = (stageId: string): number => {
    switch (stageId) {
      case "domains": return stage1Data?.mappings.length || 0;
      case "expansion": return stage2Data?.expansions.length || 0;
      case "alternatives": return stage4Data?.expansions.length || 0;
      case "specimens": return stage5Data?.enrichments.length || 0;
      case "conditions": return stage6Data?.conditions.length || 0;
      case "cycles": return Object.keys(stage8Data?.decisions || {}).length;
      case "mining": return Object.keys(stage9Data?.decisions || {}).length;
      default: return 0;
    }
  };

  const handleViewSource = useCallback((page: number) => {
    setPageNumber(page);
  }, []);

  const onDocumentLoadSuccess = useCallback(({ numPages: n }: { numPages: number }) => {
    setNumPages(n);
  }, []);

  const renderActivePanel = () => {
    switch (activeStage) {
      case "domains": return <DomainMappingPanel data={stage1Data} onViewSource={handleViewSource} />;
      case "expansion": return <ActivityExpansionPanel data={stage2Data} onViewSource={handleViewSource} />;
      case "alternatives": return <AlternativesPanel data={stage4Data} onViewSource={handleViewSource} />;
      case "specimens": return <SpecimensPanel data={stage5Data} onViewSource={handleViewSource} />;
      case "conditions": return <ConditionsPanel data={stage6Data} onViewSource={handleViewSource} />;
      case "cycles": return <CyclesPanel data={stage8Data} onViewSource={handleViewSource} />;
      case "mining": return <ProtocolMiningPanel data={stage9Data} onViewSource={handleViewSource} />;
      default: return null;
    }
  };

  // Show error if no protocol is specified
  if (!studyId) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="text-center max-w-md">
          <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-800 mb-2">No Protocol Selected</h2>
          <p className="text-gray-600 mb-6">
            Please select a protocol from the SOA Analysis page to view the interpretation review.
          </p>
          <Button onClick={() => navigate('/soa-analysis')} variant="outline">
            Go to SOA Analysis
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      <header className="shrink-0 border-b bg-white/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" onClick={() => navigate(`/soa-analysis?studyId=${studyId}`)} className="rounded-xl" data-testid="button-back">
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-sf-headline text-foreground">SOA Interpretation</h1>
              <p className="text-sf-caption text-muted-foreground">Review AI-generated interpretations</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {dataSource && (
              <div className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-full border text-sm",
                dataSource === 'database'
                  ? "bg-green-50 border-green-200 text-green-700"
                  : "bg-amber-50 border-amber-200 text-amber-700"
              )}>
                {dataSource === 'database' ? 'Database' : 'Static Files'}
              </div>
            )}
            <Button
              variant="outline"
              size="sm"
              className="h-9 px-3 text-sm font-medium text-gray-700 hover:bg-gray-100 hover:text-gray-900 hover:border-gray-400 transition-colors"
              onClick={handleExportInterpretation}
              data-testid="export-interpretation-json"
            >
              <Download className="h-4 w-4 mr-2" />
              Export {STAGES.find(s => s.id === activeStage)?.label || "Interpretation"}
            </Button>
            <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-gray-100 border border-gray-300">
              <CheckCircle2 className="w-4 h-4 text-gray-800" />
              <span className="text-sm font-medium text-gray-900">All stages complete</span>
            </div>
          </div>
        </div>
      </header>

      {/* Horizontal Stepper */}
      <div className="flex items-center gap-2 px-6 py-4 bg-white border-b border-gray-200 overflow-x-auto">
        {STAGES.map((stage, index) => {
          const Icon = stage.icon;
          const isActive = activeStage === stage.id;
          const count = getStageCount(stage.id);

          return (
            <div key={stage.id} className="flex items-center">
              <button
                onClick={() => setActiveStage(stage.id)}
                className={cn(
                  "flex items-center gap-2 px-3 py-2 rounded-lg transition-all",
                  isActive && "bg-primary/10 text-primary",
                  !isActive && "text-muted-foreground hover:bg-gray-100"
                )}
                data-testid={`step-${stage.id}`}
              >
                <div
                  className={cn(
                    "w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors",
                    isActive && "bg-primary text-white",
                    !isActive && "bg-gray-100 text-gray-500"
                  )}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm hidden lg:inline">{stage.label}</span>
                  {count > 0 && (
                    <Badge variant="secondary" className="text-xs rounded-full">
                      {count}
                    </Badge>
                  )}
                </div>
              </button>
              {index < STAGES.length - 1 && (
                <div className="w-8 h-px bg-gray-200 mx-2" />
              )}
            </div>
          );
        })}
      </div>

      <PanelGroup direction="horizontal" className="flex-1">
        <Panel defaultSize={contentExpanded ? 100 : (pdfExpanded ? 60 : 50)}>
          <div className="h-full flex flex-col">
            <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b bg-white">
              <div className="flex items-center gap-3">
                <Sparkles className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm font-medium">Interpretation Details</span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setContentExpanded(!contentExpanded)}
                className="w-8 h-8 rounded-lg"
                data-testid="button-toggle-content"
              >
                {contentExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
              </Button>
            </div>
            <ScrollArea className="flex-1 h-0">
              <div className="p-6 pb-24">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeStage}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.2 }}
                  >
                    {renderActivePanel()}
                  </motion.div>
                </AnimatePresence>
              </div>
            </ScrollArea>
          </div>
        </Panel>

        {!contentExpanded && (
          <>
            <PanelResizeHandle className="w-1 bg-transparent hover:bg-primary/20 transition-colors" />

            <Panel defaultSize={pdfExpanded ? 50 : 50} minSize={25}>
          <div className="h-full flex flex-col bg-gray-50">
            <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b bg-white">
              <div className="flex items-center gap-3">
                <BookOpen className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm font-medium">Protocol Document</span>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setScale(s => Math.max(0.5, s - 0.1))}
                  className="w-8 h-8 rounded-lg"
                  data-testid="button-zoom-out"
                >
                  <ZoomOut className="w-4 h-4" />
                </Button>
                <span className="text-xs text-muted-foreground w-12 text-center">{Math.round(scale * 100)}%</span>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setScale(s => Math.min(2, s + 0.1))}
                  className="w-8 h-8 rounded-lg"
                  data-testid="button-zoom-in"
                >
                  <ZoomIn className="w-4 h-4" />
                </Button>
                <div className="w-px h-4 bg-gray-200 mx-1" />
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setPdfExpanded(!pdfExpanded)}
                  className="w-8 h-8 rounded-lg"
                  data-testid="button-toggle-pdf"
                >
                  {pdfExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </Button>
              </div>
            </div>
            
            <div className="shrink-0 flex items-center justify-center gap-3 px-4 py-2 border-b bg-white">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setPageNumber(p => Math.max(1, p - 1))}
                disabled={pageNumber <= 1}
                className="w-8 h-8 rounded-lg"
                data-testid="button-prev-page"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {pageNumber} of {numPages}
              </span>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setPageNumber(p => Math.min(numPages, p + 1))}
                disabled={pageNumber >= numPages}
                className="w-8 h-8 rounded-lg"
                data-testid="button-next-page"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>

            <ScrollArea className="flex-1">
              <div className="flex justify-center p-4">
                <Document
                  file={pdfUrl}
                  onLoadSuccess={onDocumentLoadSuccess}
                  loading={<LoadingState />}
                >
                  <Page
                    pageNumber={pageNumber}
                    scale={scale}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                  />
                </Document>
              </div>
            </ScrollArea>
          </div>
            </Panel>
          </>
        )}
      </PanelGroup>
    </div>
  );
}
