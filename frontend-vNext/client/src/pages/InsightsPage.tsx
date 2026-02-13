import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import {
  Layers,
  GitBranch,
  Beaker,
  FileText,
  Timer,
  ChevronDown,
  ChevronUp,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  ArrowLeft,
  FlaskConical,
  TestTube,
  Clock,
  FileWarning,
  Repeat,
  Database,
  BookOpen,
  Target,
  Microscope,
} from "lucide-react";

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
}

interface Stage5Enrichment {
  id: string;
  activityId: string;
  activityName: string;
  specimenCollection: {
    specimenType?: { decode: string; code?: string };
    purpose?: { decode: string };
    collectionVolume?: { value: number; unit: string };
    fillVolume?: { value: number; unit: string };
    collectionContainer?: { decode: string };
    fastingRequired?: boolean;
    processingRequirements?: Array<{
      stepName: string;
      stepOrder: number;
      centrifugeSpeed?: string;
      centrifugeTime?: string;
      centrifugeTemperature?: string;
      timeConstraint?: string;
      inversionCount?: string;
      aliquotContainer?: string;
    }>;
    storageRequirements?: Array<{
      storagePhase: string;
      temperature?: { nominal: number; description: string };
      equipmentType?: string;
      maxDuration?: string;
    }>;
    shippingRequirements?: {
      destination?: string;
      shippingCondition?: string;
    };
    _specimenEnrichment?: {
      rationale: string;
      confidence: number;
      pageNumbers?: number[];
      footnoteMarkers?: string[];
      specimenCategory?: string;
    };
  };
  biospecimenRequirements?: {
    specimenType?: { decode: string };
    collectionContainer?: { decode: string };
    purpose?: { decode: string };
  };
  requiresReview?: boolean;
  reviewReason?: string;
  confidence: number;
}

interface Stage5Data {
  stage: number;
  stageName: string;
  success: boolean;
  enrichments: Stage5Enrichment[];
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
  cachedAt?: string;
  modelName?: string;
  provenance?: Stage8Provenance | null;
  isOpenEnded?: boolean;
  protocolContext?: unknown;
}

interface Stage8ReviewItem {
  id: string;
  encounterId: string;
  encounterName: string;
  recurrenceKey?: string;
  reason: string;
  context?: {
    recurrence?: {
      pattern?: string;
      type?: string;
      startCycle?: number;
      endCycle?: number;
    };
    originalEncounter?: {
      name?: string;
      visitType?: string;
    };
  };
  suggestedAction?: string;
  priority: string;
  stage?: string;
  createdAt?: string;
}

interface Stage8Data {
  stage: number;
  stageName: string;
  success: boolean;
  expansions: Stage8Expansion[];
  decisions: Record<string, Stage8Decision>;
  discrepancies: unknown[];
  reviewItems: Stage8ReviewItem[];
  metrics: {
    encountersProcessed: number;
    encountersWithRecurrence: number;
    encountersExpanded: number;
    encountersCreated: number;
    encountersSkipped: number;
    saisProcessed: number;
    saisDuplicated: number;
    saisCreated: number;
    uniquePatternsAnalyzed: number;
    cacheHits: number;
    llmCalls: number;
    validationFlags: number;
    eventDrivenFlagged: number;
    reviewItemsCount: number;
    expansionRate: number;
  };
}

interface Stage9Enrichment {
  id: string;
  activityId: string;
  activityName: string;
  stage?: string;
  timestamp?: string;
  overallConfidence: number;
  sourcesUsed: string[];
  requiresHumanReview: boolean;
  biospecimenEnrichment?: {
    biobankConsentRequired?: boolean | null;
    consentType?: string | null;
    shortTermStorage?: string | null;
    longTermStorageConditions?: string | null;
    futureResearchUses?: string[];
    geneticTestingIncluded?: boolean | null;
    geneticConsentRequired?: boolean | null;
    retentionPeriod?: string | null;
    destructionPolicy?: string | null;
    shippingRequirements?: string | null;
    provenance?: unknown[];
  };
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
  modelUsed?: string;
  timestamp?: string;
}

interface Stage9Metrics {
  totalActivitiesProcessed: number;
  activitiesEnriched: number;
  activitiesNoMatch: number;
  modulesUsed: Record<string, number>;
  cacheHits: number;
  llmCalls: number;
  avgConfidence: number;
  processingTimeSeconds: number;
  errorCount: number;
  reviewItemCount: number;
}

interface Stage9Data {
  stage: number;
  stageName: string;
  success: boolean;
  enrichments: Stage9Enrichment[];
  decisions: Record<string, Stage9Decision>;
  metrics?: Stage9Metrics;
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const percent = Math.round(confidence * 100);
  const color = percent >= 95 ? "bg-gray-100 text-gray-900 border-gray-300" :
                percent >= 80 ? "bg-gray-100 text-gray-700 border-gray-300" :
                               "bg-gray-100 text-gray-600 border-gray-300";
  return (
    <Badge variant="outline" className={cn("text-xs font-medium", color)}>
      {percent}%
    </Badge>
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
  color?: "blue" | "green" | "amber" | "purple" | "red";
}) {
  const colorClasses = {
    blue: "from-gray-50 to-gray-100/50 border-gray-200",
    green: "from-gray-50 to-gray-100/50 border-gray-200",
    amber: "from-gray-50 to-gray-100/50 border-gray-200",
    purple: "from-gray-50 to-gray-100/50 border-gray-200",
    red: "from-gray-50 to-gray-100/50 border-gray-200",
  };
  const iconColors = {
    blue: "text-gray-800 bg-gray-100",
    green: "text-gray-800 bg-gray-100",
    amber: "text-gray-700 bg-gray-100",
    purple: "text-gray-700 bg-gray-200",
    red: "text-gray-600 bg-gray-100",
  };

  return (
    <Card className={cn("overflow-hidden bg-gradient-to-br", colorClasses[color])}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center", iconColors[color])}>
              <Icon className="w-5 h-5" />
            </div>
            <div>
              <CardTitle className="text-lg">{title}</CardTitle>
              {description && <CardDescription className="text-sm">{description}</CardDescription>}
            </div>
          </div>
          {count !== undefined && (
            <Badge variant="secondary" className="text-sm">
              {count} items
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function DomainCategorizationTab({ data }: { data: Stage1Data | null }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (!data) return <div className="p-6 text-center text-muted-foreground" data-testid="loading-domains">Loading...</div>;

  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpanded(newExpanded);
  };

  const groupedByDomain = data.mappings.reduce((acc, m) => {
    if (!acc[m.cdashDomain]) acc[m.cdashDomain] = [];
    acc[m.cdashDomain].push(m);
    return acc;
  }, {} as Record<string, Stage1Mapping[]>);

  return (
    <div className="space-y-6" data-testid="tab-content-domains">
      <div className="grid grid-cols-4 gap-4">
        <Card className="p-4 text-center" data-testid="metric-total-activities">
          <p className="text-2xl font-bold text-gray-800">{data.metrics.totalActivities}</p>
          <p className="text-xs text-muted-foreground">Total Activities</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-high-confidence">
          <p className="text-2xl font-bold text-gray-800">{data.metrics.highConfidence}</p>
          <p className="text-xs text-muted-foreground">High Confidence</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-needs-review">
          <p className="text-2xl font-bold text-gray-700">{data.metrics.needsReview}</p>
          <p className="text-xs text-muted-foreground">Needs Review</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-cdisc-domains">
          <p className="text-2xl font-bold text-gray-700">{Object.keys(groupedByDomain).length}</p>
          <p className="text-xs text-muted-foreground">CDISC Domains</p>
        </Card>
      </div>

      <div className="space-y-4">
        {Object.entries(groupedByDomain).map(([domain, mappings]) => (
          <InsightCard 
            key={domain} 
            title={`${domain} - ${mappings[0]?.category.replace(/_/g, ' ')}`}
            icon={Layers}
            count={mappings.length}
            color="blue"
          >
            <div className="space-y-2">
              {mappings.map((m) => (
                <Collapsible key={m.activityId} open={expanded.has(m.activityId)} onOpenChange={() => toggleExpanded(m.activityId)}>
                  <CollapsibleTrigger className="w-full" data-testid={`collapsible-mapping-${m.activityId}`}>
                    <div className="flex items-center justify-between p-3 bg-white/60 rounded-lg hover:bg-white/80 transition-colors">
                      <div className="flex items-center gap-3">
                        <span className="font-medium text-sm" data-testid={`text-activity-${m.activityId}`}>{m.activityName}</span>
                        <Badge variant="outline" className="text-xs">{m.cdiscDecode}</Badge>
                      </div>
                      <div className="flex items-center gap-2">
                        <ConfidenceBadge confidence={m.confidence} />
                        {expanded.has(m.activityId) ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </div>
                    </div>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className="px-3 pb-3 pt-1">
                      <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <div className="flex items-start gap-2">
                          <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                          <div>
                            <p className="text-xs font-medium text-gray-900 mb-1">AI Rationale</p>
                            <p className="text-sm text-gray-800">{m.rationale}</p>
                            <div className="flex items-center gap-2 mt-2">
                              <Badge variant="secondary" className="text-xs">Code: {m.cdiscCode}</Badge>
                              <Badge variant="secondary" className="text-xs">Source: {m.source}</Badge>
                            </div>
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

function ActivityExpansionTab({ data }: { data: Stage2Data | null }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (!data) return <div className="p-6 text-center text-muted-foreground" data-testid="loading-expansion">Loading...</div>;

  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpanded(newExpanded);
  };

  return (
    <div className="space-y-6" data-testid="tab-content-expansion">
      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4 text-center" data-testid="metric-activities-expanded">
          <p className="text-2xl font-bold text-gray-800">{data.expansions.length}</p>
          <p className="text-xs text-muted-foreground">Activities Expanded</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-components-found">
          <p className="text-2xl font-bold text-gray-800">
            {data.expansions.reduce((acc, e) => acc + e.components.length, 0)}
          </p>
          <p className="text-xs text-muted-foreground">Components Found</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-expansion-confidence">
          <p className="text-2xl font-bold text-gray-700">
            {Math.round(data.expansions.reduce((acc, e) => acc + e.confidence, 0) / data.expansions.length * 100)}%
          </p>
          <p className="text-xs text-muted-foreground">Avg Confidence</p>
        </Card>
      </div>

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
              <CollapsibleTrigger className="w-full" data-testid={`collapsible-expansion-${expansion.id}`}>
                <div className="flex items-center justify-between p-3 bg-white/60 rounded-lg hover:bg-white/80 transition-colors">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-gray-700" />
                    <span className="text-sm text-gray-900">{expansion.rationale}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ConfidenceBadge confidence={expansion.confidence} />
                    {expanded.has(expansion.id) ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </div>
                </div>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="mt-3 space-y-2">
                  {expansion.components.slice(0, 15).map((comp, idx) => (
                    <div key={comp.id} className="flex items-center justify-between p-2 bg-white/70 rounded border text-sm">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground w-6">{idx + 1}.</span>
                        <span className="font-medium">{comp.name}</span>
                        <Badge variant="outline" className="text-xs">{comp.cdashDomain}</Badge>
                      </div>
                      <div className="flex items-center gap-2">
                        {comp.provenance?.pageNumber && (
                          <Badge variant="secondary" className="text-xs">Page {comp.provenance.pageNumber}</Badge>
                        )}
                        <ConfidenceBadge confidence={comp.confidence} />
                      </div>
                    </div>
                  ))}
                  {expansion.components.length > 15 && (
                    <p className="text-xs text-center text-muted-foreground py-2">
                      +{expansion.components.length - 15} more components
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

function AlternativeResolutionTab({ data }: { data: Stage4Data | null }) {
  if (!data) return <div className="p-6 text-center text-muted-foreground" data-testid="loading-alternatives">Loading...</div>;

  return (
    <div className="space-y-6" data-testid="tab-content-alternatives">
      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4 text-center" data-testid="metric-alternatives-detected">
          <p className="text-2xl font-bold text-gray-700">{data.expansions.length}</p>
          <p className="text-xs text-muted-foreground">Alternatives Detected</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-activities-created">
          <p className="text-2xl font-bold text-gray-800">
            {data.expansions.reduce((acc, e) => acc + e.expandedActivities.length, 0)}
          </p>
          <p className="text-xs text-muted-foreground">Activities Created</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-not-alternatives">
          <p className="text-2xl font-bold text-gray-800">
            {Object.values(data.decisions).filter(d => !d.isAlternative).length}
          </p>
          <p className="text-xs text-muted-foreground">Not Alternatives</p>
        </Card>
      </div>

      {data.expansions.map((expansion) => (
        <InsightCard
          key={expansion.id}
          title={expansion.originalActivityName}
          description={`${expansion.alternativeType.replace(/_/g, ' ')} alternatives`}
          icon={GitBranch}
          color="amber"
        >
          <div className="space-y-3">
            <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
              <div className="flex items-start gap-2">
                <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-medium text-gray-900 mb-1">AI Decision</p>
                  <p className="text-sm text-gray-800">
                    {data.decisions[expansion.originalActivityId]?.rationale}
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              {expansion.expandedActivities.map((act, idx) => (
                <div key={act.id} className="flex items-center justify-between p-3 bg-white/70 rounded-lg border">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center text-gray-700 font-medium text-sm">
                      {idx + 1}
                    </div>
                    <span className="font-medium">{act.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">
                      {act._alternativeResolution?.alternativeType.replace(/_/g, ' ')}
                    </Badge>
                    {act._alternativeResolution?.confidence && (
                      <ConfidenceBadge confidence={act._alternativeResolution.confidence} />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </InsightCard>
      ))}

      {Object.entries(data.decisions).filter(([_, d]) => !d.isAlternative).length > 0 && (
        <InsightCard
          title="Activities Kept As-Is"
          description="These activities were analyzed but not split"
          icon={CheckCircle2}
          color="green"
        >
          <div className="space-y-2">
            {Object.entries(data.decisions).filter(([_, d]) => !d.isAlternative).map(([id, decision]) => (
              <div key={id} className="flex items-center justify-between p-3 bg-white/70 rounded-lg border">
                <span className="font-medium text-sm">{decision.activityName}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground max-w-xs truncate">{decision.rationale}</span>
                  <CheckCircle2 className="w-4 h-4 text-gray-800" />
                </div>
              </div>
            ))}
          </div>
        </InsightCard>
      )}
    </div>
  );
}

function SpecimenEnrichmentTab({ data }: { data: Stage5Data | null }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (!data) return <div className="p-6 text-center text-muted-foreground" data-testid="loading-specimens">Loading...</div>;

  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpanded(newExpanded);
  };

  const needsReviewCount = data.enrichments.filter(e => e.requiresReview).length;
  const specimenCategories = new Set(data.enrichments.map(e => e.specimenCollection?._specimenEnrichment?.specimenCategory).filter(Boolean));

  return (
    <div className="space-y-6" data-testid="tab-content-specimens">
      <div className="grid grid-cols-4 gap-4">
        <Card className="p-4 text-center" data-testid="metric-specimens-enriched">
          <p className="text-2xl font-bold text-gray-700">{data.enrichments.length}</p>
          <p className="text-xs text-muted-foreground">Specimens Enriched</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-specimen-types">
          <p className="text-2xl font-bold text-gray-800">
            {new Set(data.enrichments.map(e => e.specimenCollection?.specimenType?.decode)).size}
          </p>
          <p className="text-xs text-muted-foreground">Specimen Types</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-specimen-categories">
          <p className="text-2xl font-bold text-gray-700">{specimenCategories.size}</p>
          <p className="text-xs text-muted-foreground">Categories</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-specimen-review">
          <p className="text-2xl font-bold text-gray-600">{needsReviewCount}</p>
          <p className="text-xs text-muted-foreground">Needs Review</p>
        </Card>
      </div>

      <div className="space-y-4">
        {data.enrichments.map((enrichment) => (
          <InsightCard
            key={enrichment.id}
            title={enrichment.activityName}
            description={enrichment.specimenCollection?.specimenType?.decode || "Unknown specimen"}
            icon={TestTube}
            color={enrichment.requiresReview ? "amber" : "purple"}
          >
            <Collapsible open={expanded.has(enrichment.id)} onOpenChange={() => toggleExpanded(enrichment.id)}>
              <CollapsibleTrigger className="w-full" data-testid={`collapsible-specimen-${enrichment.id}`}>
                <div className="flex items-center justify-between p-3 bg-white/60 rounded-lg hover:bg-white/80 transition-colors">
                  <div className="flex items-center gap-2 flex-wrap">
                    {enrichment.specimenCollection?._specimenEnrichment?.specimenCategory && (
                      <Badge variant="outline" className="text-xs capitalize">
                        {enrichment.specimenCollection._specimenEnrichment.specimenCategory}
                      </Badge>
                    )}
                    {enrichment.specimenCollection?.collectionVolume && (
                      <Badge variant="secondary" className="text-xs">
                        {enrichment.specimenCollection.collectionVolume.value} {enrichment.specimenCollection.collectionVolume.unit}
                      </Badge>
                    )}
                    {enrichment.specimenCollection?.collectionContainer?.decode && (
                      <Badge variant="secondary" className="text-xs">
                        {enrichment.specimenCollection.collectionContainer.decode}
                      </Badge>
                    )}
                    {enrichment.specimenCollection?.purpose?.decode && (
                      <Badge variant="outline" className="text-xs text-gray-700 border-gray-300">
                        {enrichment.specimenCollection.purpose.decode}
                      </Badge>
                    )}
                    {enrichment.specimenCollection?.fastingRequired && (
                      <Badge variant="outline" className="text-xs text-gray-700 border-gray-300">
                        Fasting Required
                      </Badge>
                    )}
                    {enrichment.requiresReview && (
                      <Badge variant="outline" className="text-xs text-gray-600 border-gray-300">
                        Needs Review
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <ConfidenceBadge confidence={enrichment.confidence} />
                    {expanded.has(enrichment.id) ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </div>
                </div>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="mt-3 space-y-3">
                  {enrichment.specimenCollection?._specimenEnrichment?.rationale && (
                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                      <div className="flex items-start gap-2">
                        <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                        <div>
                          <p className="text-xs font-medium text-gray-900 mb-1">AI Rationale</p>
                          <p className="text-sm text-gray-700">{enrichment.specimenCollection._specimenEnrichment.rationale}</p>
                          <div className="flex items-center gap-2 mt-2 flex-wrap">
                            {enrichment.specimenCollection._specimenEnrichment.pageNumbers?.map((page, idx) => (
                              <Badge key={idx} variant="secondary" className="text-xs">Page {page}</Badge>
                            ))}
                            {enrichment.specimenCollection._specimenEnrichment.footnoteMarkers?.map((fn, idx) => (
                              <Badge key={idx} variant="outline" className="text-xs">Footnote {fn}</Badge>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {enrichment.reviewReason && (
                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                      <div className="flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 text-gray-600 mt-0.5 shrink-0" />
                        <div>
                          <p className="text-xs font-medium text-gray-900 mb-1">Review Reason</p>
                          <p className="text-sm text-gray-700">{enrichment.reviewReason}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {enrichment.specimenCollection?.processingRequirements && enrichment.specimenCollection.processingRequirements.length > 0 && (
                    <div className="bg-white/70 rounded-lg p-3 border">
                      <p className="text-xs font-medium text-gray-700 mb-2">Processing Steps</p>
                      <div className="space-y-2">
                        {enrichment.specimenCollection.processingRequirements.map((step, idx) => (
                          <div key={idx} className="flex items-start gap-2 text-sm">
                            <span className="w-5 h-5 rounded-full bg-gray-100 text-gray-700 text-xs flex items-center justify-center shrink-0 mt-0.5">
                              {step.stepOrder}
                            </span>
                            <div>
                              <span className="font-medium">{step.stepName}</span>
                              <div className="flex flex-wrap gap-1 mt-1">
                                {step.centrifugeSpeed && <Badge variant="outline" className="text-xs">{step.centrifugeSpeed}</Badge>}
                                {step.centrifugeTime && <Badge variant="outline" className="text-xs">{step.centrifugeTime}</Badge>}
                                {step.centrifugeTemperature && <Badge variant="outline" className="text-xs">{step.centrifugeTemperature}</Badge>}
                                {step.inversionCount && <Badge variant="outline" className="text-xs">{step.inversionCount} inversions</Badge>}
                                {step.aliquotContainer && <Badge variant="outline" className="text-xs">{step.aliquotContainer}</Badge>}
                              </div>
                              {step.timeConstraint && <p className="text-xs text-muted-foreground mt-1">{step.timeConstraint}</p>}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {enrichment.specimenCollection?.storageRequirements && enrichment.specimenCollection.storageRequirements.length > 0 && (
                    <div className="bg-white/70 rounded-lg p-3 border">
                      <p className="text-xs font-medium text-gray-700 mb-2">Storage Requirements</p>
                      {enrichment.specimenCollection.storageRequirements.map((storage, idx) => (
                        <div key={idx} className="flex items-center gap-2 text-sm flex-wrap">
                          <Badge variant="outline" className="text-xs capitalize">{storage.storagePhase.replace(/_/g, ' ')}</Badge>
                          {storage.temperature && (
                            <Badge variant="secondary" className="text-xs">{storage.temperature.nominal}°C</Badge>
                          )}
                          {storage.temperature?.description && (
                            <span className="text-muted-foreground">({storage.temperature.description})</span>
                          )}
                          {storage.equipmentType && (
                            <Badge variant="outline" className="text-xs">{storage.equipmentType.replace(/_/g, ' ')}</Badge>
                          )}
                          {storage.maxDuration && (
                            <span className="text-muted-foreground">Max: {storage.maxDuration}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {enrichment.specimenCollection?.shippingRequirements && (enrichment.specimenCollection.shippingRequirements.destination || enrichment.specimenCollection.shippingRequirements.shippingCondition) && (
                    <div className="bg-white/70 rounded-lg p-3 border">
                      <p className="text-xs font-medium text-gray-700 mb-2">Shipping Requirements</p>
                      <div className="flex items-center gap-2 text-sm flex-wrap">
                        {enrichment.specimenCollection.shippingRequirements.destination && (
                          <Badge variant="secondary" className="text-xs">{enrichment.specimenCollection.shippingRequirements.destination}</Badge>
                        )}
                        {enrichment.specimenCollection.shippingRequirements.shippingCondition && (
                          <Badge variant="outline" className="text-xs capitalize">{enrichment.specimenCollection.shippingRequirements.shippingCondition.replace(/_/g, ' ')}</Badge>
                        )}
                      </div>
                    </div>
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

function ConditionalExpansionTab({ data }: { data: Stage6Data | null }) {
  if (!data) return <div className="p-6 text-center text-muted-foreground" data-testid="loading-conditions">Loading...</div>;

  return (
    <div className="space-y-6" data-testid="tab-content-conditions">
      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4 text-center" data-testid="metric-conditions-found">
          <p className="text-2xl font-bold text-gray-600">{data.conditions.length}</p>
          <p className="text-xs text-muted-foreground">Conditions Found</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-footnotes-analyzed">
          <p className="text-2xl font-bold text-gray-800">{data.metrics.footnotesAnalyzed}</p>
          <p className="text-xs text-muted-foreground">Footnotes Analyzed</p>
        </Card>
        <Card className="p-4 text-center" data-testid="metric-condition-rate">
          <p className="text-2xl font-bold text-gray-800">
            {Math.round((data.conditions.length / data.metrics.footnotesAnalyzed) * 100)}%
          </p>
          <p className="text-xs text-muted-foreground">Condition Rate</p>
        </Card>
      </div>

      <div className="space-y-4">
        {data.conditions.map((condition) => (
          <InsightCard
            key={condition.id}
            title={condition.name}
            description={`Footnote ${condition.sourceFootnoteMarker}`}
            icon={FileText}
            color="red"
          >
            <div className="space-y-3">
              <div className="p-3 bg-white/70 rounded-lg border">
                <p className="text-sm font-medium text-gray-900 mb-2">Condition Text</p>
                <p className="text-sm text-gray-700 italic">"{condition.text}"</p>
              </div>

              {/* Criteria Display */}
              {condition.criterion && Object.keys(condition.criterion).length > 0 && (
                <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                  <p className="text-sm font-medium text-gray-900 mb-2">Criteria</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(condition.criterion).map(([key, value]) => (
                      <div key={key} className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white rounded-lg border text-sm">
                        <span className="font-medium text-gray-700 capitalize">{key}:</span>
                        <span className="text-gray-600">{typeof value === 'object' && value !== null ? (value as any).decode ?? JSON.stringify(value) : String(value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-xs">
                  Type: {condition.conditionType?.decode ?? 'Unknown'}
                </Badge>
                <Badge variant="secondary" className="text-xs">
                  {condition.provenance.footnote_id}
                </Badge>
              </div>

              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <div className="flex items-start gap-2">
                  <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-xs font-medium text-gray-900 mb-1">AI Interpretation</p>
                    <p className="text-sm text-gray-800">{condition.provenance.rationale}</p>
                    <p className="text-xs text-gray-600 mt-2 italic">
                      Source: "{condition.provenance.text_snippet}"
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </InsightCard>
        ))}
      </div>
    </div>
  );
}

function CycleExpansionTab({ data }: { data: Stage8Data | null }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (!data) return <div className="p-6 text-center text-muted-foreground" data-testid="loading-cycles">Loading...</div>;

  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpanded(newExpanded);
  };

  const decisions = Object.entries(data.decisions);
  const needsReview = decisions.filter(([_, d]) => d.requiresHumanReview);
  const metrics = data.metrics;

  return (
    <div className="space-y-6" data-testid="tab-content-cycles">
      <div className="grid grid-cols-4 gap-3 mb-2">
        <Card className="p-3 text-center" data-testid="metric-encounters-processed">
          <p className="text-xl font-bold text-gray-800">{metrics.encountersProcessed}</p>
          <p className="text-xs text-muted-foreground">Encounters</p>
        </Card>
        <Card className="p-3 text-center" data-testid="metric-sais-processed">
          <p className="text-xl font-bold text-gray-700">{metrics.saisProcessed}</p>
          <p className="text-xs text-muted-foreground">SAIs Processed</p>
        </Card>
        <Card className="p-3 text-center" data-testid="metric-cache-hits">
          <p className="text-xl font-bold text-gray-700">{metrics.cacheHits}</p>
          <p className="text-xs text-muted-foreground">Cache Hits</p>
        </Card>
        <Card className="p-3 text-center" data-testid="metric-llm-calls">
          <p className="text-xl font-bold text-gray-700">{metrics.llmCalls}</p>
          <p className="text-xs text-muted-foreground">LLM Calls</p>
        </Card>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Card className="p-3 text-center" data-testid="metric-review-items-count">
          <p className="text-xl font-bold text-gray-600">{metrics.reviewItemsCount}</p>
          <p className="text-xs text-muted-foreground">Review Items</p>
        </Card>
        <Card className="p-3 text-center" data-testid="metric-expansion-rate">
          <p className="text-xl font-bold text-gray-700">{Math.round(metrics.expansionRate * 100)}%</p>
          <p className="text-xs text-muted-foreground">Expansion Rate</p>
        </Card>
        <Card className="p-3 text-center" data-testid="metric-validation-flags">
          <p className="text-xl font-bold text-gray-700">{metrics.validationFlags}</p>
          <p className="text-xs text-muted-foreground">Validation Flags</p>
        </Card>
      </div>

      {data.reviewItems && data.reviewItems.length > 0 && (
        <InsightCard
          title="Review Items"
          description="Items flagged for human review with context"
          icon={FileWarning}
          count={data.reviewItems.length}
          color="red"
        >
          <div className="space-y-3">
            {data.reviewItems.map((item) => (
              <Collapsible key={item.id} open={expanded.has(item.id)} onOpenChange={() => toggleExpanded(item.id)}>
                <CollapsibleTrigger className="w-full" data-testid={`collapsible-review-${item.id}`}>
                  <div className="flex items-center justify-between p-3 bg-white/70 rounded-lg hover:bg-white/90 transition-colors border border-gray-200">
                    <div className="flex items-center gap-3">
                      <AlertTriangle className="w-4 h-4 text-gray-600" />
                      <span className="font-medium text-sm">{item.encounterName}</span>
                      <Badge variant="outline" className={cn("text-xs", 
                        item.priority === 'high' ? "bg-gray-100 text-gray-900 border-gray-300" :
                        item.priority === 'medium' ? "bg-gray-100 text-gray-700 border-gray-300" :
                        "bg-gray-50 text-gray-600 border-gray-200"
                      )}>
                        {item.priority}
                      </Badge>
                    </div>
                    {expanded.has(item.id) ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </div>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="px-3 pb-3 pt-2 space-y-3">
                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                      <p className="text-sm text-gray-900 font-medium mb-1">Reason</p>
                      <p className="text-sm text-gray-700">{item.reason}</p>
                    </div>
                    
                    {item.context?.recurrence && (
                      <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <p className="text-sm text-gray-900 font-medium mb-2">Recurrence Pattern</p>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          {item.context.recurrence.pattern && (
                            <div>
                              <span className="text-gray-600">Pattern:</span>{" "}
                              <span className="text-gray-800">{item.context.recurrence.pattern}</span>
                            </div>
                          )}
                          {item.context.recurrence.type && (
                            <div>
                              <span className="text-gray-600">Type:</span>{" "}
                              <span className="text-gray-800">{item.context.recurrence.type}</span>
                            </div>
                          )}
                          {item.context.recurrence.startCycle && (
                            <div>
                              <span className="text-gray-600">Start:</span>{" "}
                              <span className="text-gray-800">Cycle {item.context.recurrence.startCycle}</span>
                            </div>
                          )}
                          {item.context.recurrence.endCycle && (
                            <div>
                              <span className="text-gray-600">End:</span>{" "}
                              <span className="text-gray-800">Cycle {item.context.recurrence.endCycle}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {item.context?.originalEncounter && (
                      <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <p className="text-sm text-gray-900 font-medium mb-2">Original Encounter</p>
                        <div className="text-sm">
                          {item.context.originalEncounter.name && (
                            <div>
                              <span className="text-gray-600">Name:</span>{" "}
                              <span className="text-gray-800">{item.context.originalEncounter.name}</span>
                            </div>
                          )}
                          {item.context.originalEncounter.visitType && (
                            <div>
                              <span className="text-gray-600">Visit Type:</span>{" "}
                              <span className="text-gray-800">{item.context.originalEncounter.visitType}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {item.suggestedAction && (
                      <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <div className="flex items-start gap-2">
                          <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                          <div>
                            <p className="text-sm text-gray-900 font-medium mb-1">Suggested Action</p>
                            <p className="text-sm text-gray-700">{item.suggestedAction}</p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            ))}
          </div>
        </InsightCard>
      )}

      {needsReview.length > 0 && (
        <InsightCard
          title="Patterns Requiring Review"
          description="These recurrence patterns need human input"
          icon={AlertTriangle}
          count={needsReview.length}
          color="amber"
        >
          <div className="space-y-3">
            {needsReview.map(([encId, decision]) => (
              <div key={encId} className="p-4 bg-white/70 rounded-lg border border-gray-300">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Repeat className="w-4 h-4 text-gray-700" />
                    <span className="font-medium">{decision.encounterName}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs bg-gray-100 border-gray-300 text-gray-700">
                      {decision.patternType.replace(/_/g, ' ')}
                    </Badge>
                    {decision.provenance?.pageNumber && (
                      <Badge variant="secondary" className="text-xs">
                        Page {decision.provenance.pageNumber}
                      </Badge>
                    )}
                  </div>
                </div>

                <p className="text-sm text-gray-700 mb-2">{decision.rationale}</p>

                {decision.reviewReason && (
                  <div className="bg-gray-50 rounded p-2 border border-gray-200">
                    <p className="text-xs text-gray-700">
                      <AlertTriangle className="w-3 h-3 inline mr-1" />
                      {decision.reviewReason}
                    </p>
                  </div>
                )}

                <div className="flex items-center gap-2 mt-3 flex-wrap">
                  <Badge variant="secondary" className="text-xs">
                    Cycle Length: {decision.cycleLengthDays} days
                  </Badge>
                  {decision.isOpenEnded && (
                    <Badge variant="outline" className="text-xs text-gray-700 border-gray-400">
                      Open-ended
                    </Badge>
                  )}
                  {decision.provenance?.tableId && (
                    <Badge variant="outline" className="text-xs">
                      Table: {decision.provenance.tableId}
                    </Badge>
                  )}
                  {decision.provenance?.colIdx !== undefined && (
                    <Badge variant="outline" className="text-xs">
                      Col: {decision.provenance.colIdx}
                    </Badge>
                  )}
                  {decision.modelName && (
                    <Badge variant="outline" className="text-xs text-gray-800 border-gray-300">
                      {decision.modelName}
                    </Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        </InsightCard>
      )}

      {data.expansions && data.expansions.length > 0 && (
        <InsightCard
          title="Cycle Expansions"
          description="Encounters that were expanded into multiple cycles"
          icon={GitBranch}
          count={data.expansions.length}
          color="purple"
        >
          <div className="space-y-3">
            {data.expansions.map((exp) => (
              <Collapsible key={exp.id} open={expanded.has(exp.id)} onOpenChange={() => toggleExpanded(exp.id)}>
                <CollapsibleTrigger className="w-full" data-testid={`collapsible-expansion-${exp.id}`}>
                  <div className="flex items-center justify-between p-3 bg-white/70 rounded-lg hover:bg-white/90 transition-colors border border-gray-200">
                    <div className="flex items-center gap-3">
                      <GitBranch className="w-4 h-4 text-gray-700" />
                      <span className="font-medium text-sm">{exp.originalName}</span>
                      <Badge variant="outline" className="text-xs font-mono bg-gray-50">{exp.originalEncounterId}</Badge>
                      <Badge variant="outline" className="text-xs bg-gray-100 border-gray-300 text-gray-700">
                        {exp.expandedEncounterCount} encounters
                      </Badge>
                      {exp.requiresReview && (
                        <Badge variant="outline" className="text-xs bg-gray-100 border-gray-300 text-gray-700">
                          Needs Review
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <ConfidenceBadge confidence={exp.confidence} />
                      {expanded.has(exp.id) ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </div>
                  </div>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="px-3 pb-3 pt-2 space-y-3">
                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                      <div className="flex items-start gap-2">
                        <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                        <div>
                          <p className="text-xs font-medium text-gray-900 mb-1">AI Rationale</p>
                          <p className="text-sm text-gray-800">{exp.rationale}</p>
                          {exp.reviewReason && (
                            <p className="text-sm text-gray-700 mt-2 italic">Review Reason: {exp.reviewReason}</p>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <p className="text-xs font-medium text-gray-900 mb-2">Recurrence Pattern</p>
                        <div className="space-y-1 text-sm">
                          <div><span className="text-gray-600">Pattern:</span> <span className="text-gray-800 font-mono">{exp.originalRecurrence.pattern}</span></div>
                          <div><span className="text-gray-600">Type:</span> <span className="text-gray-800">{exp.originalRecurrence.type.replace(/_/g, ' ')}</span></div>
                          {exp.originalRecurrence.startCycle !== undefined && (
                            <div><span className="text-gray-600">Cycles:</span> <span className="text-gray-800">{exp.originalRecurrence.startCycle} - {exp.originalRecurrence.endCycle}</span></div>
                          )}
                          {exp.originalRecurrence.provenance?.pageNumber && (
                            <div><span className="text-gray-600">Source:</span> <span className="text-gray-800">Page {exp.originalRecurrence.provenance.pageNumber}, {exp.originalRecurrence.provenance.tableId}</span></div>
                          )}
                        </div>
                      </div>

                      <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <p className="text-xs font-medium text-gray-900 mb-2">Expansion Results</p>
                        <div className="space-y-1 text-sm">
                          <div><span className="text-gray-600">Encounters Created:</span> <span className="text-gray-800 font-bold">{exp.expandedEncounterCount}</span></div>
                          <div><span className="text-gray-600">SAIs Duplicated:</span> <span className="text-gray-800 font-bold">{exp.saiDuplicationCount}</span></div>
                          <div><span className="text-gray-600">Source:</span> <span className="text-gray-800">{exp.source}</span></div>
                        </div>
                      </div>
                    </div>

                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                      <p className="text-xs font-medium text-gray-700 mb-2">Expanded Encounter IDs</p>
                      <div className="flex flex-wrap gap-1">
                        {exp.expandedEncounterIds.map((id) => (
                          <Badge key={id} variant="outline" className="text-xs font-mono">{id}</Badge>
                        ))}
                      </div>
                    </div>

                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                      <p className="text-xs font-medium text-gray-700 mb-2">Expanded SAI IDs ({exp.expandedSaiIds.length} total)</p>
                      <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                        {exp.expandedSaiIds.slice(0, 20).map((id) => (
                          <Badge key={id} variant="outline" className="text-xs font-mono text-gray-600">{id}</Badge>
                        ))}
                        {exp.expandedSaiIds.length > 20 && (
                          <Badge variant="secondary" className="text-xs">+{exp.expandedSaiIds.length - 20} more</Badge>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant="secondary" className="text-xs">Cycles: {exp.expandedCycleNumbers.join(', ')}</Badge>
                      {exp.provenance?.pageNumber && (
                        <Badge variant="outline" className="text-xs">Page {exp.provenance.pageNumber}</Badge>
                      )}
                      {exp.provenance?.tableId && (
                        <Badge variant="outline" className="text-xs">Table: {exp.provenance.tableId}</Badge>
                      )}
                      {exp.provenance?.colIdx !== undefined && (
                        <Badge variant="outline" className="text-xs">Col: {exp.provenance.colIdx}</Badge>
                      )}
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>
            ))}
          </div>
        </InsightCard>
      )}

      {decisions.filter(([_, d]) => !d.requiresHumanReview).length > 0 && (
        <InsightCard
          title="Auto-Resolved Patterns"
          description="These patterns were resolved automatically"
          icon={CheckCircle2}
          color="green"
        >
          <div className="space-y-3">
            {decisions.filter(([_, d]) => !d.requiresHumanReview).map(([encId, decision]) => (
              <Collapsible key={encId} open={expanded.has(`decision-${encId}`)} onOpenChange={() => toggleExpanded(`decision-${encId}`)}>
                <CollapsibleTrigger className="w-full" data-testid={`collapsible-decision-${encId}`}>
                  <div className="flex items-center justify-between p-3 bg-white/70 rounded-lg hover:bg-white/90 transition-colors border border-gray-200">
                    <div className="flex items-center gap-3">
                      {decision.shouldExpand ? (
                        <GitBranch className="w-4 h-4 text-gray-700" />
                      ) : (
                        <CheckCircle2 className="w-4 h-4 text-gray-800" />
                      )}
                      <span className="font-medium text-sm">{decision.encounterName}</span>
                      {decision.recurrenceKey && decision.recurrenceKey !== "NONE" && (
                        <Badge variant="outline" className="text-xs font-mono bg-gray-50">{decision.recurrenceKey}</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={cn("text-xs", 
                        decision.shouldExpand ? "bg-gray-100 text-gray-900 border-gray-300" : "bg-gray-50 text-gray-600 border-gray-200"
                      )}>
                        {decision.shouldExpand ? "Expanded" : "Not Expanded"}
                      </Badge>
                      <ConfidenceBadge confidence={decision.confidence} />
                      {expanded.has(`decision-${encId}`) ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </div>
                  </div>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="px-3 pb-3 pt-2 space-y-3">
                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                      <div className="flex items-start gap-2">
                        <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                        <div>
                          <p className="text-xs font-medium text-gray-900 mb-1">AI Rationale</p>
                          <p className="text-sm text-gray-800">{decision.rationale}</p>
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <p className="text-xs font-medium text-gray-900 mb-2">Pattern Details</p>
                        <div className="space-y-1 text-sm">
                          <div><span className="text-gray-600">Type:</span> <span className="text-gray-800">{decision.patternType.replace(/_/g, ' ')}</span></div>
                          <div><span className="text-gray-600">Cycle Length:</span> <span className="text-gray-800 font-bold">{decision.cycleLengthDays} days</span></div>
                          {decision.expandedCycles && decision.expandedCycles.length > 0 && (
                            <div><span className="text-gray-600">Expanded Cycles:</span> <span className="text-gray-800">{decision.expandedCycles.join(', ')}</span></div>
                          )}
                        </div>
                      </div>

                      <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                        <p className="text-xs font-medium text-gray-700 mb-2">Processing Info</p>
                        <div className="space-y-1 text-sm">
                          {decision.source && (
                            <div><span className="text-gray-600">Source:</span> <span className="text-gray-800">{decision.source}</span></div>
                          )}
                          {decision.modelName && (
                            <div><span className="text-gray-600">Model:</span> <span className="text-gray-800">{decision.modelName}</span></div>
                          )}
                          {decision.cachedAt && (
                            <div><span className="text-gray-600">Cached:</span> <span className="text-gray-800 text-xs">{new Date(decision.cachedAt).toLocaleString()}</span></div>
                          )}
                        </div>
                      </div>
                    </div>

                    {decision.protocolContext && (
                      <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <p className="text-xs font-medium text-gray-900 mb-2">Protocol Context</p>
                        <pre className="text-xs text-gray-800 whitespace-pre-wrap overflow-x-auto">
                          {JSON.stringify(decision.protocolContext as Record<string, unknown>, null, 2)}
                        </pre>
                      </div>
                    )}

                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant="outline" className="text-xs font-mono bg-gray-50">{encId}</Badge>
                      {decision.provenance?.pageNumber && (
                        <Badge variant="outline" className="text-xs">Page {decision.provenance.pageNumber}</Badge>
                      )}
                      {decision.provenance?.tableId && (
                        <Badge variant="outline" className="text-xs">Table: {decision.provenance.tableId}</Badge>
                      )}
                      {decision.provenance?.colIdx !== undefined && (
                        <Badge variant="outline" className="text-xs">Col: {decision.provenance.colIdx}</Badge>
                      )}
                      {decision.isOpenEnded && (
                        <Badge variant="outline" className="text-xs text-gray-700 border-gray-400">Open-ended</Badge>
                      )}
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>
            ))}
          </div>
        </InsightCard>
      )}
    </div>
  );
}

function ProtocolMiningTab({ data }: { data: Stage9Data | null }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (!data) return <div className="p-6 text-center text-muted-foreground" data-testid="loading-mining">Loading...</div>;

  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpanded(newExpanded);
  };

  const decisions = Object.values(data.decisions);
  const decisionsWithRationale = decisions.filter(d => d.matchRationale && Object.keys(d.matchRationale).length > 0);
  const metrics = data.metrics;

  return (
    <div className="space-y-6" data-testid="tab-content-mining">
      <div className="grid grid-cols-5 gap-3">
        <Card className="p-3 text-center" data-testid="metric-total-processed">
          <p className="text-xl font-bold text-gray-800">{metrics?.totalActivitiesProcessed || decisions.length}</p>
          <p className="text-xs text-muted-foreground">Total Processed</p>
        </Card>
        <Card className="p-3 text-center" data-testid="metric-mining-enriched">
          <p className="text-xl font-bold text-gray-800">{metrics?.activitiesEnriched || data.enrichments.length}</p>
          <p className="text-xs text-muted-foreground">Enriched</p>
        </Card>
        <Card className="p-3 text-center" data-testid="metric-llm-calls">
          <p className="text-xl font-bold text-gray-700">{metrics?.llmCalls || 0}</p>
          <p className="text-xs text-muted-foreground">LLM Calls</p>
        </Card>
        <Card className="p-3 text-center" data-testid="metric-mining-confidence">
          <p className="text-xl font-bold text-gray-700">
            {Math.round((metrics?.avgConfidence || 0) * 100)}%
          </p>
          <p className="text-xs text-muted-foreground">Avg Confidence</p>
        </Card>
        <Card className="p-3 text-center" data-testid="metric-processing-time">
          <p className="text-xl font-bold text-gray-800">{Math.round(metrics?.processingTimeSeconds || 0)}s</p>
          <p className="text-xs text-muted-foreground">Processing Time</p>
        </Card>
      </div>

      {metrics?.modulesUsed && Object.keys(metrics.modulesUsed).length > 0 && (
        <InsightCard
          title="Module Usage Breakdown"
          description="How many activities used each protocol section"
          icon={Database}
          color="blue"
        >
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(metrics.modulesUsed).sort((a, b) => b[1] - a[1]).map(([module, count]) => (
              <div key={module} className="flex items-center justify-between p-2 bg-white/70 rounded-lg border">
                <span className="text-sm font-medium">{module.replace(/_/g, ' ')}</span>
                <Badge variant="secondary" className="text-xs">{count} activities</Badge>
              </div>
            ))}
          </div>
        </InsightCard>
      )}

      <InsightCard
        title="AI Module Matching Decisions"
        description="Why each activity was matched to specific protocol sections"
        icon={Sparkles}
        count={decisionsWithRationale.length}
        color="purple"
      >
        <div className="space-y-3 max-h-[500px] overflow-y-auto">
          {decisionsWithRationale.slice(0, 30).map((decision) => (
            <Collapsible key={decision.activityId} open={expanded.has(decision.activityId)} onOpenChange={() => toggleExpanded(decision.activityId)}>
              <CollapsibleTrigger className="w-full" data-testid={`collapsible-decision-${decision.activityId}`}>
                <div className="flex items-center justify-between p-3 bg-white/70 rounded-lg hover:bg-white/90 transition-colors border">
                  <div className="flex items-center gap-3">
                    <BookOpen className="w-4 h-4 text-gray-700" />
                    <span className="font-medium text-sm">{decision.activityName}</span>
                    <Badge variant="outline" className="text-xs">{decision.activityId}</Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">{decision.matchedModules.length} modules</Badge>
                    <ConfidenceBadge confidence={decision.confidence} />
                    {expanded.has(decision.activityId) ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </div>
                </div>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="px-3 pb-3 pt-2 space-y-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    {decision.matchedModules.map((module, idx) => (
                      <Badge key={idx} variant="outline" className="text-xs bg-gray-100 text-gray-700 border-gray-300">
                        {module.replace(/_/g, ' ')}
                      </Badge>
                    ))}
                    {decision.modelUsed && (
                      <Badge variant="outline" className="text-xs text-gray-800 border-gray-300">
                        {decision.modelUsed}
                      </Badge>
                    )}
                  </div>

                  {decision.matchRationale && Object.keys(decision.matchRationale).length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-gray-600">AI Rationale for Each Module:</p>
                      {Object.entries(decision.matchRationale).map(([module, rationale]) => (
                        <div key={module} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                          <div className="flex items-start gap-2">
                            <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                            <div>
                              <p className="text-xs font-medium text-gray-900 mb-1">{module.replace(/_/g, ' ')}</p>
                              <p className="text-sm text-gray-800">{rationale}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </CollapsibleContent>
            </Collapsible>
          ))}
          {decisionsWithRationale.length > 30 && (
            <p className="text-xs text-center text-muted-foreground py-2">
              +{decisionsWithRationale.length - 30} more decisions
            </p>
          )}
        </div>
      </InsightCard>

      <InsightCard
        title="Enriched Activities Summary"
        description="Activities with additional protocol context applied"
        icon={Microscope}
        count={data.enrichments.length}
        color="green"
      >
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {data.enrichments.slice(0, 20).map((enrichment) => (
            <div key={enrichment.id} className="flex items-center justify-between p-3 bg-white/70 rounded-lg border">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm">{enrichment.activityName}</span>
                {enrichment.requiresHumanReview && (
                  <Badge variant="outline" className="text-xs bg-gray-100 text-gray-700 border-gray-300">
                    Review Needed
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-2">
                {enrichment.sourcesUsed.slice(0, 2).map((source, idx) => (
                  <Badge key={idx} variant="outline" className="text-xs">
                    {source.replace(/_/g, ' ')}
                  </Badge>
                ))}
                {enrichment.sourcesUsed.length > 2 && (
                  <Badge variant="secondary" className="text-xs">
                    +{enrichment.sourcesUsed.length - 2}
                  </Badge>
                )}
                <ConfidenceBadge confidence={enrichment.overallConfidence} />
              </div>
            </div>
          ))}
          {data.enrichments.length > 20 && (
            <p className="text-xs text-center text-muted-foreground py-2">
              +{data.enrichments.length - 20} more enrichments
            </p>
          )}
        </div>
      </InsightCard>
    </div>
  );
}

interface InsightsPageProps {
  onBack?: () => void;
}

export default function InsightsPage({ onBack }: InsightsPageProps) {
  const [stage1Data, setStage1Data] = useState<Stage1Data | null>(null);
  const [stage2Data, setStage2Data] = useState<Stage2Data | null>(null);
  const [stage4Data, setStage4Data] = useState<Stage4Data | null>(null);
  const [stage5Data, setStage5Data] = useState<Stage5Data | null>(null);
  const [stage6Data, setStage6Data] = useState<Stage6Data | null>(null);
  const [stage8Data, setStage8Data] = useState<Stage8Data | null>(null);
  const [stage9Data, setStage9Data] = useState<Stage9Data | null>(null);
  const [activeTab, setActiveTab] = useState("domains");

  useEffect(() => {
    const loadData = async () => {
      try {
        const [s1, s2, s4, s5, s6, s8, s9] = await Promise.all([
          fetch('/data/stage01_domain_categorization.json').then(r => r.json()),
          fetch('/data/stage02_activity_expansion.json').then(r => r.json()),
          fetch('/data/stage04_alternative_resolution.json').then(r => r.json()),
          fetch('/data/stage05_specimen_enrichment.json').then(r => r.json()),
          fetch('/data/stage06_conditional_expansion.json').then(r => r.json()),
          fetch('/data/stage08_cycle_expansion.json').then(r => r.json()),
          fetch('/data/stage09_protocol_mining.json').then(r => r.json()),
        ]);
        setStage1Data(s1);
        setStage2Data(s2);
        setStage4Data(s4);
        setStage5Data(s5);
        setStage6Data(s6);
        setStage8Data(s8);
        setStage9Data(s9);
      } catch (error) {
        console.error('Error loading stage data:', error);
      }
    };
    loadData();
  }, []);

  const tabs = [
    { id: "domains", label: "Domain Mapping", icon: Layers, count: stage1Data?.mappings.length },
    { id: "expansion", label: "Activity Expansion", icon: GitBranch, count: stage2Data?.expansions.length },
    { id: "alternatives", label: "Alternatives", icon: Target, count: stage4Data?.expansions.length },
    { id: "specimens", label: "Specimens", icon: TestTube, count: stage5Data?.enrichments.length },
    { id: "conditions", label: "Conditions", icon: FileText, count: stage6Data?.conditions.length },
    { id: "cycles", label: "Cycles", icon: Repeat, count: Object.keys(stage8Data?.decisions || {}).length },
    { id: "mining", label: "Protocol Mining", icon: Database, count: stage9Data?.enrichments.length },
  ];

  return (
    <div className="absolute inset-0 flex flex-col bg-gray-50">
      <div className="bg-white border-b px-6 py-4 shrink-0">
        <div className="flex items-center gap-4">
          {onBack && (
            <Button variant="ghost" size="sm" onClick={onBack} data-testid="btn-back-insights">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
          )}
          <div className="flex-1">
            <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-gray-700" />
              AI Extraction Insights
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Discover what the AI learned from the clinical trial protocol
            </p>
          </div>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
        <div className="bg-white border-b px-6 shrink-0">
          <TabsList className="h-12 bg-transparent gap-1">
            {tabs.map((tab) => (
              <TabsTrigger
                key={tab.id}
                value={tab.id}
                className="data-[state=active]:bg-primary/10 data-[state=active]:text-primary px-4"
                data-testid={`tab-${tab.id}`}
              >
                <tab.icon className="w-4 h-4 mr-2" />
                {tab.label}
                {tab.count !== undefined && tab.count > 0 && (
                  <Badge variant="secondary" className="ml-2 text-xs">
                    {tab.count}
                  </Badge>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="p-6">
            <TabsContent value="domains" className="mt-0">
              <DomainCategorizationTab data={stage1Data} />
            </TabsContent>
            <TabsContent value="expansion" className="mt-0">
              <ActivityExpansionTab data={stage2Data} />
            </TabsContent>
            <TabsContent value="alternatives" className="mt-0">
              <AlternativeResolutionTab data={stage4Data} />
            </TabsContent>
            <TabsContent value="specimens" className="mt-0">
              <SpecimenEnrichmentTab data={stage5Data} />
            </TabsContent>
            <TabsContent value="conditions" className="mt-0">
              <ConditionalExpansionTab data={stage6Data} />
            </TabsContent>
            <TabsContent value="cycles" className="mt-0">
              <CycleExpansionTab data={stage8Data} />
            </TabsContent>
            <TabsContent value="mining" className="mt-0">
              <ProtocolMiningTab data={stage9Data} />
            </TabsContent>
          </div>
        </div>
      </Tabs>
    </div>
  );
}
