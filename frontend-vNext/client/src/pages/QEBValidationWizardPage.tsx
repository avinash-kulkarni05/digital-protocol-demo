import { useState, useEffect, useMemo, useRef, createContext, useContext } from "react";
import { useSearch, useLocation } from "wouter";
import { api, getPdfUrl, type EligibilitySectionInfo } from "@/lib/api";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import {
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  Check,
  AlertTriangle,
  AlertCircle,
  Loader2,
  Database,
  Search,
  Filter,
  Zap,
  FileText,
  Play,
  Eye,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  Users,
  Activity,
  Layers,
  TrendingDown,
  Target,
  Shield,
  Lock,
  Unlock,
  Sparkles,
  ArrowRight,
  Info,
  BarChart3,
  Settings2,
  Fingerprint,
  ClipboardCheck,
  ArrowDownRight,
  MousePointerClick,
  MousePointer,
  Circle,
  Lightbulb,
  MapPin,
  Maximize2,
  Minimize2,
  ZoomIn,
  ZoomOut,
  BookOpen,
} from "lucide-react";
import { Document, Page, pdfjs } from 'react-pdf';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  `pdfjs-dist/build/pdf.worker.min.mjs`,
  import.meta.url
).toString();
import {
  type QebValidationData,
  type QueryableBlock,
  type AtomicCriterion,
  type WizardStep,
  type QueryabilityClassification,
  type OmopConcept,
  deriveQebData,
  WIZARD_STEPS,
  searchMockOmop,
} from "@/lib/qebValidation";
import { InfoTooltip, ELIGIBILITY_TOOLTIPS } from "@/components/eligibility/InfoTooltip";
import { CriterionCard, SectionHeader } from "@/components/eligibility/CriterionCard";
import { CriteriaFilterBar, filterCriteria, DEFAULT_FILTER_STATE, type FilterState } from "@/components/eligibility/CriteriaFilterBar";

// Logic Expression Tree Types and Parser
interface LogicNode {
  type: 'AND' | 'OR' | 'NOT' | 'ATOMIC';
  id?: string;
  children?: LogicNode[];
}

function parseLogicExpression(expr: string): LogicNode {
  expr = expr.trim();
  
  // Handle empty expression
  if (!expr) return { type: 'AND', children: [] };
  
  // Tokenize
  const tokens: string[] = [];
  let current = '';
  let depth = 0;
  
  for (let i = 0; i < expr.length; i++) {
    const char = expr[i];
    if (char === '(') {
      if (depth === 0 && current.trim()) {
        tokens.push(current.trim());
        current = '';
      }
      depth++;
      current += char;
    } else if (char === ')') {
      depth--;
      current += char;
      if (depth === 0) {
        tokens.push(current.trim());
        current = '';
      }
    } else if (depth === 0 && (char === ' ' || char === '\t')) {
      if (current.trim()) {
        tokens.push(current.trim());
        current = '';
      }
    } else {
      current += char;
    }
  }
  if (current.trim()) tokens.push(current.trim());
  
  // Check if the entire expression is wrapped in parentheses
  if (tokens.length === 1 && tokens[0].startsWith('(') && tokens[0].endsWith(')')) {
    return parseLogicExpression(tokens[0].slice(1, -1));
  }
  
  // Find top-level OR (lowest precedence)
  let orIndex = -1;
  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i].toUpperCase() === 'OR') {
      orIndex = i;
      break;
    }
  }
  
  if (orIndex > 0) {
    const left = tokens.slice(0, orIndex).join(' ');
    const right = tokens.slice(orIndex + 1).join(' ');
    return {
      type: 'OR',
      children: [parseLogicExpression(left), parseLogicExpression(right)]
    };
  }
  
  // Find top-level AND
  let andIndex = -1;
  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i].toUpperCase() === 'AND') {
      andIndex = i;
      break;
    }
  }
  
  if (andIndex > 0) {
    const left = tokens.slice(0, andIndex).join(' ');
    const right = tokens.slice(andIndex + 1).join(' ');
    return {
      type: 'AND',
      children: [parseLogicExpression(left), parseLogicExpression(right)]
    };
  }
  
  // Handle NOT
  if (tokens.length >= 2 && tokens[0].toUpperCase() === 'NOT') {
    return {
      type: 'NOT',
      children: [parseLogicExpression(tokens.slice(1).join(' '))]
    };
  }
  
  // Single atomic
  const atomicMatch = expr.match(/^(A\d+)$/);
  if (atomicMatch) {
    return { type: 'ATOMIC', id: atomicMatch[1] };
  }
  
  // Try unwrapping parentheses
  if (expr.startsWith('(') && expr.endsWith(')')) {
    return parseLogicExpression(expr.slice(1, -1));
  }
  
  return { type: 'ATOMIC', id: expr };
}

// Flatten consecutive same-type operators for cleaner display
function flattenLogicTree(node: LogicNode): LogicNode {
  if (node.type === 'ATOMIC') return node;
  if (!node.children) return node;
  
  const flattenedChildren = node.children.map(flattenLogicTree);
  
  if (node.type === 'AND' || node.type === 'OR') {
    const newChildren: LogicNode[] = [];
    for (const child of flattenedChildren) {
      if (child.type === node.type && child.children) {
        newChildren.push(...child.children);
      } else {
        newChildren.push(child);
      }
    }
    return { type: node.type, children: newChildren };
  }
  
  return { ...node, children: flattenedChildren };
}

// Logic Tree Visual Component
function LogicTreeNode({ 
  node, 
  atomicLookup, 
  depth = 0 
}: { 
  node: LogicNode; 
  atomicLookup: Map<string, AtomicCriterion>;
  depth?: number;
}) {
  const [collapsed, setCollapsed] = useState(false);
  
  if (node.type === 'ATOMIC') {
    const atomic = node.id ? atomicLookup.get(node.id) : null;
    const isQueryable = atomic?.queryabilityClassification.category === "QUERYABLE";
    const conceptNames = atomic?.omopQuery?.conceptNames || [];
    
    return (
      <div className="py-1.5 pl-1">
        <div className="flex items-start gap-2">
          <div className={cn(
            "w-2 h-2 rounded-full flex-shrink-0 mt-1",
            isQueryable ? "bg-gray-700" : "bg-gray-400"
          )} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <span className="font-mono text-xs text-gray-600 flex-shrink-0">{node.id}</span>
              {isQueryable ? (
                <Badge className="bg-gray-100 text-gray-700 text-[8px]">SQL</Badge>
              ) : (
                <Badge className="bg-gray-100 text-gray-500 text-[8px]">MANUAL</Badge>
              )}
            </div>
            {atomic && (
              <p className="text-[11px] text-gray-700 leading-relaxed mb-1">
                {atomic.atomicText}
              </p>
            )}
            {conceptNames.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {conceptNames.slice(0, 3).map((name: string, ci: number) => (
                  <Badge key={ci} variant="outline" className="text-[8px] bg-white border-gray-300 text-gray-700">
                    {name}
                  </Badge>
                ))}
                {conceptNames.length > 3 && (
                  <Badge variant="outline" className="text-[8px] bg-gray-50 text-gray-500">
                    +{conceptNames.length - 3}
                  </Badge>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }
  
  const operatorStyles = {
    AND: { bg: 'bg-gray-50', border: 'border-gray-300', text: 'text-gray-700', icon: '∩' },
    OR: { bg: 'bg-gray-50', border: 'border-gray-300', text: 'text-gray-700', icon: '∪' },
    NOT: { bg: 'bg-gray-50', border: 'border-gray-300', text: 'text-gray-600', icon: '¬' },
  };
  
  const style = operatorStyles[node.type] || operatorStyles.AND;
  const childCount = node.children?.length || 0;
  
  return (
    <div className={cn("rounded-lg border", style.bg, style.border, depth > 0 && "ml-3 mt-1")}>
      <button 
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 px-3 py-1.5 w-full text-left"
      >
        <span className={cn("font-mono text-xs font-semibold", style.text)}>
          {style.icon} {node.type}
        </span>
        <span className="text-[10px] text-gray-400">({childCount})</span>
        {childCount > 0 && (
          collapsed ? <ChevronRight className="w-3 h-3 text-gray-400 ml-auto" /> : <ChevronDown className="w-3 h-3 text-gray-400 ml-auto" />
        )}
      </button>
      {!collapsed && node.children && (
        <div className="px-2 pb-2 space-y-0.5">
          {node.children.map((child, idx) => (
            <LogicTreeNode key={idx} node={child} atomicLookup={atomicLookup} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

// Eligibility data is now fetched from the database via api.eligibility methods

interface WizardContextType {
  data: QebValidationData;
  derived: ReturnType<typeof deriveQebData>;
  selectedQebId: string | null;
  setSelectedQebId: (id: string | null) => void;
  overrides: Map<string, QueryabilityClassification["category"]>;
  setOverride: (atomicId: string, category: QueryabilityClassification["category"]) => void;
  conceptCorrections: Map<string, number[]>;
  setConceptCorrection: (atomicId: string, conceptIds: number[]) => void;
  stageApprovals: Map<string, boolean>;
  setStageApproval: (stageId: string, approved: boolean) => void;
  allStagesApproved: boolean;
  goToStep: (step: WizardStep) => void;
}

const WizardContext = createContext<WizardContextType | null>(null);

function useWizard() {
  const ctx = useContext(WizardContext);
  if (!ctx) throw new Error("useWizard must be used within WizardProvider");
  return ctx;
}

function WizardStepper({ 
  currentStep, 
  onStepClick 
}: { 
  currentStep: WizardStep; 
  onStepClick: (step: WizardStep) => void;
}) {
  const currentIndex = WIZARD_STEPS.findIndex(s => s.id === currentStep);
  
  return (
    <div className="px-8 py-4 bg-white/80 backdrop-blur-xl border-b border-gray-100 sticky top-0 z-10">
      <div className="flex items-center justify-center">
        <div className="inline-flex items-center bg-gray-100/80 rounded-full p-1 gap-1">
          {WIZARD_STEPS.map((step, index) => {
            const isActive = step.id === currentStep;
            const isPast = index < currentIndex;
            
            return (
              <button
                key={step.id}
                onClick={() => onStepClick(step.id)}
                className={cn(
                  "relative flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all duration-300 whitespace-nowrap",
                  isActive && "bg-white text-gray-900 shadow-sm",
                  !isActive && isPast && "text-gray-600 hover:text-gray-900",
                  !isActive && !isPast && "text-gray-400 hover:text-gray-600"
                )}
                data-testid={`wizard-step-${step.id}`}
              >
                {isPast && !isActive && (
                  <Check className="w-3.5 h-3.5 text-gray-600" />
                )}
                <span>{step.title}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function OverviewScreen() {
  const { data, derived, goToStep, allStagesApproved, conceptCorrections, overrides } = useWizard();
  const { classificationCounts, unmappedAtomics, killerQebs } = derived;
  const total = data.summary?.totalAtomicsConsolidated ?? 0;
  
  const queryablePercent = ((classificationCounts.queryable / total) * 100).toFixed(0);
  const uncorrectedAtomics = unmappedAtomics.filter(a => {
    const corrections = conceptCorrections.get(a.atomicId);
    return !corrections || corrections.length === 0;
  });
  const conceptsRemaining = uncorrectedAtomics.length;
  const hasOverrides = overrides.size > 0;

  const [leftExpanded, setLeftExpanded] = useState(false);
  const [pdfExpanded, setPdfExpanded] = useState(false);
  const [numPages, setNumPages] = useState<number>(0);
  const eligibilityStartPage = data.summary.eligibilitySectionPages?.start || 1;
  const [currentPage, setCurrentPage] = useState(eligibilityStartPage);
  const [scale, setScale] = useState(1.0);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTER_STATE);

  // Use the protocol ID from data to get the correct annotated PDF
  const pdfUrl = getPdfUrl(data.protocolId);

  // Filter criteria based on current filters
  const filteredCriteria = useMemo(() => {
    return filterCriteria(
      data.queryableBlocks ?? [],
      data.atomicCriteria ?? [],
      filters,
      derived.atomicLookup
    );
  }, [data.queryableBlocks, data.atomicCriteria, filters, derived.atomicLookup]);

  const filteredInclusion = useMemo(() =>
    filteredCriteria
      .filter(qeb => qeb.criterionType === "inclusion")
      .sort((a, b) => {
        const aNum = parseInt(a.originalCriterionId.replace(/\D/g, '')) || 0;
        const bNum = parseInt(b.originalCriterionId.replace(/\D/g, '')) || 0;
        return aNum - bNum;
      }),
    [filteredCriteria]
  );

  const filteredExclusion = useMemo(() =>
    filteredCriteria
      .filter(qeb => qeb.criterionType === "exclusion")
      .sort((a, b) => {
        const aNum = parseInt(a.originalCriterionId.replace(/\D/g, '')) || 0;
        const bNum = parseInt(b.originalCriterionId.replace(/\D/g, '')) || 0;
        return aNum - bNum;
      }),
    [filteredCriteria]
  );

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    if (eligibilityStartPage > 1 && eligibilityStartPage <= numPages) {
      setCurrentPage(eligibilityStartPage);
    }
  };

  const checklist = [
    {
      id: "concepts",
      label: "Map OMOP Concepts",
      description: conceptsRemaining > 0 
        ? `${conceptsRemaining} unmapped concept${conceptsRemaining > 1 ? 's' : ''} need mapping`
        : "All concepts from executable criteria mapped",
      status: conceptsRemaining === 0 ? "complete" : "action_required",
      action: () => goToStep("assurance"),
      priority: 1,
    },
    {
      id: "classifications", 
      label: "Review AI Classifications",
      description: hasOverrides 
        ? `${overrides.size} override${overrides.size > 1 ? 's' : ''} applied`
        : "Review and override if needed",
      status: "optional",
      action: () => goToStep("assurance"),
      priority: 2,
    },
    {
      id: "funnel",
      label: "Build & Approve Funnel",
      description: allStagesApproved
        ? "All stages approved"
        : `${data.funnelStages?.length ?? 0} stages to review and approve`,
      status: allStagesApproved ? "complete" : "pending",
      action: () => goToStep("funnel"),
      priority: 3,
    },
  ];

  const hasBlockers = conceptsRemaining > 0;

  return (
    <div className="h-full flex flex-col">
      <PanelGroup direction="horizontal" className="flex-1">
        <Panel defaultSize={leftExpanded ? 100 : (pdfExpanded ? 0 : 60)} minSize={pdfExpanded ? 0 : 35}>
          <div className="h-full flex flex-col bg-white rounded-l-xl border-r border-gray-200">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50/50">
              <div className="flex items-center gap-2">
                <ClipboardCheck className="w-4 h-4 text-gray-500" />
                <span className="font-medium text-gray-700 text-sm">Criteria Overview</span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setLeftExpanded(!leftExpanded);
                  if (!leftExpanded) setPdfExpanded(false);
                }}
                className="h-7 w-7 p-0"
              >
                {leftExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
              </Button>
            </div>
            
            <ScrollArea className="flex-1 p-4">
              <div className="space-y-6">
                {/* Hero Status Card */}
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <h2 className="text-2xl font-semibold tracking-tight text-gray-900">
                        Eligibility Criteria Review
                      </h2>
                      <p className="text-gray-500 mt-1 text-sm">
                        {data.protocolId} • {data.therapeuticArea}
                      </p>
                    </div>
                    {hasBlockers ? (
                      <div className="flex items-center gap-2 bg-gray-50 border border-gray-300 rounded-full px-3 py-1.5">
                        <div className="w-2 h-2 rounded-full bg-gray-500 animate-pulse" />
                        <span className="text-gray-700 font-medium text-xs">Action Required</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 bg-gray-50 border border-gray-300 rounded-full px-3 py-1.5">
                        <div className="w-2 h-2 rounded-full bg-gray-700" />
                        <span className="text-gray-700 font-medium text-xs">Ready to Review</span>
                      </div>
                    )}
                  </div>
                  
                  {/* Enhanced Flow Diagram with Tooltips */}
                  <div className="flex items-center justify-center gap-1 py-4 overflow-x-auto">
                    {/* Protocol Criteria Card */}
                    <div className="flex flex-col items-center min-w-0">
                      <div className="bg-gradient-to-b from-gray-50 to-gray-100 border-2 border-gray-300 rounded-xl px-4 py-3 text-center min-w-[100px] relative">
                        <div className="absolute -top-1 -right-1">
                          <InfoTooltip
                            content="Original eligibility criteria extracted from the protocol document, split into inclusion and exclusion categories."
                            size="sm"
                          />
                        </div>
                        <div className="text-2xl font-bold text-gray-900">{(data.summary?.inclusionQEBs ?? 0) + (data.summary?.exclusionQEBs ?? 0)}</div>
                        <div className="text-[11px] font-semibold text-gray-700 mt-0.5">Protocol Criteria</div>
                        <div className="flex items-center justify-center gap-2 mt-1">
                          <span className="inline-flex items-center text-[9px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 font-medium">
                            {data.summary?.inclusionQEBs ?? 0} Inc
                          </span>
                          <span className="inline-flex items-center text-[9px] px-1.5 py-0.5 rounded bg-gray-200 text-gray-700 font-medium">
                            {data.summary?.exclusionQEBs ?? 0} Exc
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Transformation Arrow 1 */}
                    <div className="flex flex-col items-center shrink-0 px-1">
                      <ArrowRight className="w-5 h-5 text-gray-400" />
                      <span className="text-[8px] text-gray-400 font-medium mt-0.5 whitespace-nowrap">Decomposition</span>
                    </div>

                    {/* Sub-Criteria Card */}
                    <div className="flex flex-col items-center min-w-0">
                      <div className="bg-gradient-to-b from-gray-50 to-gray-100 border-2 border-gray-300 rounded-xl px-4 py-3 text-center min-w-[100px] relative">
                        <div className="absolute -top-1 -right-1">
                          <InfoTooltip
                            content={ELIGIBILITY_TOOLTIPS.decomposition}
                            size="sm"
                          />
                        </div>
                        <div className="text-2xl font-bold text-gray-800">{data.atomicCriteria?.length ?? 0}</div>
                        <div className="text-[11px] font-semibold text-gray-700 mt-0.5">Sub-Criteria</div>
                        <div className="text-[9px] text-gray-500 mt-0.5">Decomposed & Normalized</div>
                      </div>
                    </div>

                    {/* Transformation Arrow 2 */}
                    <div className="flex flex-col items-center shrink-0 px-1">
                      <ArrowRight className="w-5 h-5 text-gray-400" />
                      <span className="text-[8px] text-gray-400 font-medium mt-0.5 whitespace-nowrap">Grouping</span>
                    </div>

                    {/* Clinical Groups Card */}
                    <div className="flex flex-col items-center min-w-0">
                      <div className="bg-gradient-to-b from-gray-50 to-gray-100 border-2 border-gray-300 rounded-xl px-4 py-3 text-center min-w-[100px] relative">
                        <div className="absolute -top-1 -right-1">
                          <InfoTooltip
                            content={ELIGIBILITY_TOOLTIPS.clinicalGroup}
                            size="sm"
                          />
                        </div>
                        <div className="text-2xl font-bold text-gray-800">{data.funnelStages?.length ?? 0}</div>
                        <div className="text-[11px] font-semibold text-gray-700 mt-0.5">Clinical Groups</div>
                        <div className="text-[9px] text-gray-500 mt-0.5">Funnel Stages</div>
                      </div>
                    </div>

                    {/* Transformation Arrow 3 */}
                    <div className="flex flex-col items-center shrink-0 px-1">
                      <ArrowRight className="w-5 h-5 text-gray-400" />
                      <span className="text-[8px] text-gray-400 font-medium mt-0.5 whitespace-nowrap">Validation</span>
                    </div>

                    {/* Query Ready Progress Card */}
                    <div className="flex flex-col items-center min-w-0">
                      <div className="bg-gradient-to-b from-gray-50 to-gray-100 border-2 border-gray-300 rounded-xl px-4 py-3 text-center min-w-[100px] relative">
                        <div className="absolute -top-1 -right-1">
                          <InfoTooltip
                            content={ELIGIBILITY_TOOLTIPS.queryableStatus}
                            size="sm"
                          />
                        </div>
                        <div className="text-2xl font-bold text-gray-800">{queryablePercent}%</div>
                        <div className="text-[11px] font-semibold text-gray-700 mt-0.5">Query-Ready</div>
                        <div className="flex items-center justify-center gap-1.5 mt-1.5">
                          <div className="flex items-center gap-1">
                            <div className="w-1.5 h-1.5 rounded-full bg-gray-500" />
                            <span className="text-[8px] text-gray-600">{classificationCounts.queryable}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <div className="w-1.5 h-1.5 rounded-full bg-gray-500" />
                            <span className="text-[8px] text-gray-600">{classificationCounts.screeningOnly}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <div className="w-1.5 h-1.5 rounded-full bg-gray-400" />
                            <span className="text-[8px] text-gray-500">{classificationCounts.notApplicable}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Query Status Legend */}
                  <div className="flex items-center justify-center gap-4 mt-2 pb-2">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 rounded-full bg-gray-500" />
                      <span className="text-[10px] text-gray-600">Fully Queryable</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 rounded-full bg-gray-500" />
                      <span className="text-[10px] text-gray-600">Screening Only</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 rounded-full bg-gray-400" />
                      <span className="text-[10px] text-gray-600">Manual Review</span>
                    </div>
                  </div>
                </div>

                {/* Extracted Criteria */}
                <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden flex-1 flex flex-col">
                  <div className="px-4 py-3 border-b border-gray-100 bg-gray-50/50 space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-gray-900 text-sm flex items-center gap-2">
                        <ClipboardCheck className="w-4 h-4 text-gray-600" />
                        Extracted Criteria
                        <InfoTooltip
                          content="Eligibility criteria extracted from the protocol, organized by inclusion and exclusion. Each criterion shows its queryability status and clinical category."
                          size="sm"
                        />
                      </h3>
                      <div className="flex items-center gap-3 text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <div className="w-2 h-2 rounded-full bg-gray-700" />
                          {data.summary?.inclusionQEBs ?? 0} Inclusion
                        </span>
                        <span className="flex items-center gap-1">
                          <div className="w-2 h-2 rounded-full bg-gray-400" />
                          {data.summary?.exclusionQEBs ?? 0} Exclusion
                        </span>
                      </div>
                    </div>
                    {/* Search and Filter Bar */}
                    <CriteriaFilterBar
                      queryableBlocks={data.queryableBlocks ?? []}
                      atomicCriteria={data.atomicCriteria ?? []}
                      filters={filters}
                      onFiltersChange={setFilters}
                      filteredCount={filteredCriteria.length}
                      totalCount={(data.queryableBlocks ?? []).length}
                    />
                  </div>
                  <ScrollArea className="flex-1">
                    <div className="space-y-0">
                      {/* Inclusion Criteria Section */}
                      {(filters.type === "all" || filters.type === "inclusion") && filteredInclusion.length > 0 && (
                        <div>
                          <SectionHeader
                            type="inclusion"
                            count={filteredInclusion.length}
                          />
                          <div className="p-3 space-y-3 bg-gray-50/30">
                            {filteredInclusion.map((qeb, idx) => (
                              <CriterionCard
                                key={qeb.qebId}
                                qeb={qeb}
                                index={idx + 1}
                                type="inclusion"
                                atomicLookup={derived.atomicLookup}
                                onViewProvenance={(pageNumber) => setCurrentPage(pageNumber)}
                              />
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Exclusion Criteria Section */}
                      {(filters.type === "all" || filters.type === "exclusion") && filteredExclusion.length > 0 && (
                        <div>
                          <SectionHeader
                            type="exclusion"
                            count={filteredExclusion.length}
                          />
                          <div className="p-3 space-y-3 bg-gray-100/30">
                            {filteredExclusion.map((qeb, idx) => (
                              <CriterionCard
                                key={qeb.qebId}
                                qeb={qeb}
                                index={idx + 1}
                                type="exclusion"
                                atomicLookup={derived.atomicLookup}
                                onViewProvenance={(pageNumber) => setCurrentPage(pageNumber)}
                              />
                            ))}
                          </div>
                        </div>
                      )}

                      {/* No Results Message */}
                      {filteredCriteria.length === 0 && (
                        <div className="p-8 text-center">
                          <Search className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                          <p className="text-sm text-gray-500 mb-1">No criteria match your filters</p>
                          <p className="text-xs text-gray-400">Try adjusting your search or filter settings</p>
                          <Button
                            variant="outline"
                            size="sm"
                            className="mt-4"
                            onClick={() => setFilters(DEFAULT_FILTER_STATE)}
                          >
                            Clear all filters
                          </Button>
                        </div>
                      )}
                    </div>
                  </ScrollArea>
                </div>
              </div>
            </ScrollArea>
          </div>
        </Panel>

        {!leftExpanded && (
          <>
            <PanelResizeHandle className="w-1.5 bg-gray-100 hover:bg-gray-200 transition-colors cursor-col-resize" />
            
            <Panel defaultSize={pdfExpanded ? 100 : 40} minSize={25}>
              <div className="h-full flex flex-col bg-gray-50 rounded-r-xl">
                <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-white">
                  <div className="flex items-center gap-2">
                    <BookOpen className="w-4 h-4 text-gray-500" />
                    <span className="font-medium text-gray-700 text-sm">Protocol Document</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setScale(Math.max(0.5, scale - 0.1))}
                      className="h-7 w-7 p-0"
                    >
                      <ZoomOut className="w-4 h-4" />
                    </Button>
                    <span className="text-xs text-gray-500 w-12 text-center">{Math.round(scale * 100)}%</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setScale(Math.min(2, scale + 0.1))}
                      className="h-7 w-7 p-0"
                    >
                      <ZoomIn className="w-4 h-4" />
                    </Button>
                    <div className="w-px h-4 bg-gray-200 mx-1" />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setPdfExpanded(!pdfExpanded);
                        if (!pdfExpanded) setLeftExpanded(false);
                      }}
                      className="h-7 w-7 p-0"
                    >
                      {pdfExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                    </Button>
                  </div>
                </div>
                
                {numPages > 0 && (
                  <div className="flex items-center justify-center gap-2 px-4 py-2 border-b border-gray-100 bg-gray-50/50">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                      disabled={currentPage <= 1}
                      className="h-7 w-7 p-0"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <div className="flex items-center gap-1">
                      <Input
                        type="number"
                        min={1}
                        max={numPages}
                        value={currentPage}
                        onChange={(e) => {
                          const page = parseInt(e.target.value);
                          if (page >= 1 && page <= numPages) {
                            setCurrentPage(page);
                          }
                        }}
                        className="w-14 h-7 text-center text-sm"
                      />
                      <span className="text-sm text-gray-500">/ {numPages}</span>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCurrentPage(Math.min(numPages, currentPage + 1))}
                      disabled={currentPage >= numPages}
                      className="h-7 w-7 p-0"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                )}
                
                <div className="flex-1 overflow-auto p-4">
                  <Document
                    file={pdfUrl}
                    onLoadSuccess={onDocumentLoadSuccess}
                    loading={
                      <div className="flex items-center justify-center h-full">
                        <Loader2 className="w-8 h-8 text-gray-400 animate-spin" />
                      </div>
                    }
                    error={
                      <div className="flex flex-col items-center justify-center h-full text-gray-500">
                        <FileText className="w-12 h-12 mb-2 text-gray-300" />
                        <p className="text-sm">Unable to load PDF</p>
                      </div>
                    }
                  >
                    <Page 
                      pageNumber={currentPage} 
                      scale={scale}
                      className="mx-auto shadow-lg"
                      renderTextLayer={false}
                      renderAnnotationLayer={false}
                    />
                  </Document>
                </div>
              </div>
            </Panel>
          </>
        )}
      </PanelGroup>
    </div>
  );
}

function QebOverviewScreen() {
  const { data, derived } = useWizard();
  const { qebLookup, atomicLookup, stageQebMap } = derived;
  const [selectedQeb, setSelectedQeb] = useState<QueryableBlock | null>(null);
  const [maximizedPanel, setMaximizedPanel] = useState<'left' | 'right' | null>(null);
  
  // Build reverse mapping: QEB -> stages it appears in
  const qebToStages = useMemo(() => {
    const mapping = new Map<string, string[]>();
    data.funnelStages?.forEach(stage => {
      stage.qebIds.forEach(qebId => {
        if (!mapping.has(qebId)) {
          mapping.set(qebId, []);
        }
        mapping.get(qebId)!.push(stage.stageName);
      });
    });
    return mapping;
  }, [data.funnelStages]);

  // Sort QEBs by their original criterion order (same as protocol)
  const sortedQebs = useMemo(() => {
    return [...(data.queryableBlocks ?? [])].sort((a, b) => {
      // First sort by type (inclusion before exclusion)
      if (a.criterionType !== b.criterionType) {
        return a.criterionType === "inclusion" ? -1 : 1;
      }
      // Then by original criterion ID number
      const aNum = parseInt(a.originalCriterionId.replace(/\D/g, '')) || 0;
      const bNum = parseInt(b.originalCriterionId.replace(/\D/g, '')) || 0;
      return aNum - bNum;
    });
  }, [data.queryableBlocks]);
  
  const inclusionQebs = sortedQebs.filter(q => q.criterionType === "inclusion");
  const exclusionQebs = sortedQebs.filter(q => q.criterionType === "exclusion");

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h2 className="text-3xl font-semibold tracking-tight text-gray-900">Criteria Map</h2>
        <p className="text-gray-500 mt-2 text-lg">
          Understand how criteria are combined with logical operators
        </p>
      </div>

      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden" style={{ height: '600px' }}>
        <PanelGroup direction="horizontal">
          {/* Criteria List - Left Panel */}
          <Panel 
            defaultSize={maximizedPanel === 'right' ? 0 : maximizedPanel === 'left' ? 100 : 55} 
            minSize={maximizedPanel === 'right' ? 0 : 20}
            className={cn(maximizedPanel === 'right' && 'hidden')}
          >
            <div className="h-full flex flex-col">
              <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-100">
                <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">Criteria List</span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  onClick={() => setMaximizedPanel(maximizedPanel === 'left' ? null : 'left')}
                >
                  {maximizedPanel === 'left' ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                </Button>
              </div>
              <ScrollArea className="flex-1 p-4">
                <div className="space-y-6">
                  {/* Inclusion Criteria */}
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-1.5 h-5 bg-gray-700 rounded-full" />
                      <h4 className="text-xs font-semibold text-gray-800 uppercase tracking-wider">Inclusion Criteria</h4>
                      <span className="text-[10px] text-gray-400 ml-auto">{inclusionQebs.length} criteria</span>
                    </div>
                    <div className="space-y-2">
                      {inclusionQebs.map((qeb, idx) => {
                        const isSelected = selectedQeb?.qebId === qeb.qebId;
                        return (
                          <button
                            key={qeb.qebId}
                            onClick={() => setSelectedQeb(qeb)}
                            className={cn(
                              "w-full p-3 rounded-xl text-left transition-all",
                              isSelected 
                                ? "bg-gray-100 border-2 border-gray-400" 
                                : "bg-white border border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                            )}
                          >
                            <div className="flex items-center gap-3">
                              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-50 border border-gray-300 text-gray-700 flex items-center justify-center text-[10px] font-medium">
                                {idx + 1}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                  <p className="text-sm font-medium text-gray-900 truncate">{qeb.clinicalName}</p>
                                  <Badge className={cn(
                                    "text-[9px] flex-shrink-0",
                                    qeb.internalLogic === "AND" ? "bg-gray-100 text-gray-700" :
                                    qeb.internalLogic === "OR" ? "bg-gray-100 text-gray-700" : "bg-gray-100 text-gray-700"
                                  )}>
                                    {qeb.internalLogic}
                                  </Badge>
                                  <Badge variant="outline" className="text-[9px] flex-shrink-0">
                                    {qeb.atomicCount} atomics
                                  </Badge>
                                </div>
                                <p className="text-xs text-gray-500 truncate">{qeb.clinicalCategory}</p>
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Exclusion Criteria */}
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-1.5 h-5 bg-gray-400 rounded-full" />
                      <h4 className="text-xs font-semibold text-gray-800 uppercase tracking-wider">Exclusion Criteria</h4>
                      <span className="text-[10px] text-gray-400 ml-auto">{exclusionQebs.length} criteria</span>
                    </div>
                    <div className="space-y-2">
                      {exclusionQebs.map((qeb, idx) => {
                        const isSelected = selectedQeb?.qebId === qeb.qebId;
                        return (
                          <button
                            key={qeb.qebId}
                            onClick={() => setSelectedQeb(qeb)}
                            className={cn(
                              "w-full p-3 rounded-xl text-left transition-all",
                              isSelected 
                                ? "bg-gray-100 border-2 border-gray-400" 
                                : "bg-white border border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                            )}
                          >
                            <div className="flex items-center gap-3">
                              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-50 border border-gray-300 text-gray-500 flex items-center justify-center text-[10px] font-medium">
                                {idx + 1}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                  <p className="text-sm font-medium text-gray-900 truncate">{qeb.clinicalName}</p>
                                  <Badge className={cn(
                                    "text-[9px] flex-shrink-0",
                                    qeb.internalLogic === "AND" ? "bg-gray-100 text-gray-700" :
                                    qeb.internalLogic === "OR" ? "bg-gray-100 text-gray-700" : "bg-gray-100 text-gray-700"
                                  )}>
                                    {qeb.internalLogic}
                                  </Badge>
                                  <Badge variant="outline" className="text-[9px] flex-shrink-0">
                                    {qeb.atomicCount} atomics
                                  </Badge>
                                </div>
                                <p className="text-xs text-gray-500 truncate">{qeb.clinicalCategory}</p>
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </ScrollArea>
            </div>
          </Panel>

          {/* Resize Handle */}
          {maximizedPanel === null && (
            <PanelResizeHandle className="w-1.5 bg-gray-100 hover:bg-gray-200 transition-colors cursor-col-resize" />
          )}

          {/* Detail Inspector - Right Panel */}
          <Panel 
            defaultSize={maximizedPanel === 'left' ? 0 : maximizedPanel === 'right' ? 100 : 45} 
            minSize={maximizedPanel === 'left' ? 0 : 20}
            className={cn(maximizedPanel === 'left' && 'hidden')}
          >
            <div className="h-full flex flex-col">
              <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-100">
                <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">Detail Inspector</span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  onClick={() => setMaximizedPanel(maximizedPanel === 'right' ? null : 'right')}
                >
                  {maximizedPanel === 'right' ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                </Button>
              </div>
              <ScrollArea className="flex-1 p-4">
                {selectedQeb ? (
              <Card className="border border-gray-200 shadow-sm rounded-2xl overflow-hidden">
                <CardHeader className="bg-gray-50 border-b border-gray-100 pb-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-lg text-gray-900">{selectedQeb.clinicalName}</CardTitle>
                      <p className="text-sm text-gray-500 font-mono">{selectedQeb.qebId}</p>
                    </div>
                    <Badge className={cn(
                      selectedQeb.internalLogic === "AND" ? "bg-gray-100 text-gray-700" :
                      selectedQeb.internalLogic === "OR" ? "bg-gray-100 text-gray-700" : "bg-gray-100 text-gray-700"
                    )}>
                      {selectedQeb.internalLogic}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="p-4 space-y-4">
                  {/* Criterion Type */}
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Type</p>
                    <Badge className={cn(
                      selectedQeb.criterionType === "inclusion" 
                        ? "bg-gray-100 text-gray-700" 
                        : "bg-gray-200 text-gray-700"
                    )}>
                      {selectedQeb.criterionType === "inclusion" ? "Inclusion" : "Exclusion"}
                    </Badge>
                  </div>

                  {/* Criteria Text */}
                  {selectedQeb.protocolText && (
                    <div>
                      <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Criteria Text</p>
                      <div className="bg-gray-50 border border-gray-300 rounded-lg p-3 max-h-32 overflow-y-auto">
                        <p className="text-sm text-gray-700 leading-relaxed">
                          {selectedQeb.protocolText}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Logic Expression Tree */}
                  {selectedQeb.sqlLogicExplanation && (
                    <div>
                      <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Logic Structure</p>
                      <div className="bg-gray-50 rounded-xl p-3 max-h-72 overflow-y-auto border border-gray-100">
                        {(() => {
                          const parsed = parseLogicExpression(selectedQeb.sqlLogicExplanation);
                          const flattened = flattenLogicTree(parsed);
                          return <LogicTreeNode node={flattened} atomicLookup={atomicLookup} />;
                        })()}
                      </div>
                      <div className="mt-2 flex items-center gap-4 text-[10px] text-gray-400">
                        <div className="flex items-center gap-1">
                          <div className="w-2 h-2 rounded-full bg-gray-700" />
                          <span>Queryable</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <div className="w-2 h-2 rounded-full bg-gray-400" />
                          <span>Manual</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Raw SQL Expression (collapsed) */}
                  {selectedQeb.sqlLogicExplanation && (
                    <Collapsible>
                      <CollapsibleTrigger className="flex items-center gap-2 text-xs text-gray-400 hover:text-gray-600">
                        <ChevronRight className="w-3 h-3" />
                        <span>View raw expression</span>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <code className="text-[10px] bg-gray-100 p-2 rounded block font-mono text-gray-600 mt-2 break-all">
                          {selectedQeb.sqlLogicExplanation}
                        </code>
                      </CollapsibleContent>
                    </Collapsible>
                  )}

                  {/* Stage Usage */}
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Used in Stages</p>
                    <div className="flex flex-wrap gap-1">
                      {(qebToStages.get(selectedQeb.qebId) || []).map(stage => (
                        <Badge key={stage} variant="outline">{stage}</Badge>
                      ))}
                    </div>
                  </div>

                  {/* Individual Atomic SQL */}
                  {(() => {
                    const atomicsWithSql = selectedQeb.atomicIds
                      .map(id => ({ id, atomic: atomicLookup.get(id) }))
                      .filter(({ atomic }) => atomic?.omopQuery?.sqlTemplate);
                    
                    if (atomicsWithSql.length === 0) return null;
                    
                    return (
                      <div>
                        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                          Atomic SQL Queries ({atomicsWithSql.length})
                        </p>
                        <div className="space-y-2 max-h-48 overflow-y-auto">
                          {atomicsWithSql.map(({ id, atomic }) => (
                            <div key={id} className="bg-gray-900 rounded-lg p-3 border border-gray-700">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-[10px] font-mono text-gray-400">{id}</span>
                                <Badge className="bg-gray-800 text-gray-300 text-[8px]">SQL</Badge>
                              </div>
                              <pre className="text-[11px] font-mono text-gray-400 whitespace-pre-wrap leading-relaxed">
                                {atomic?.omopQuery?.sqlTemplate
                                  ?.replace(/\bSELECT\b/gi, 'SELECT')
                                  .replace(/\bFROM\b/gi, '\n  FROM')
                                  .replace(/\bWHERE\b/gi, '\n  WHERE')
                                  .replace(/\bAND\b/gi, '\n    AND')}
                              </pre>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })()}

                  {/* Individual Atomic FHIR Queries */}
                  {(() => {
                    const atomicsWithFhir = selectedQeb.atomicIds
                      .map(id => ({ id, atomic: atomicLookup.get(id) }))
                      .filter(({ atomic }) => atomic?.fhirQuery?.resourceType);
                    
                    if (atomicsWithFhir.length === 0) return null;
                    
                    return (
                      <div>
                        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                          Atomic FHIR Queries ({atomicsWithFhir.length})
                        </p>
                        <div className="space-y-2 max-h-48 overflow-y-auto">
                          {atomicsWithFhir.map(({ id, atomic }) => (
                            <div key={id} className="bg-gray-50 rounded-lg p-3 border border-gray-300">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-[10px] font-mono text-gray-600">{id}</span>
                                <Badge className="bg-gray-100 text-gray-700 text-[8px]">FHIR</Badge>
                              </div>
                              <div className="space-y-1">
                                <div className="text-[11px] text-gray-700">
                                  <span className="font-semibold">Resource:</span> {atomic?.fhirQuery?.resourceType}
                                </div>
                                {atomic?.fhirQuery?.searchParams && (
                                  <div className="text-[10px] font-mono text-gray-600 bg-white rounded px-2 py-1 break-all">
                                    {atomic.fhirQuery.searchParams}
                                  </div>
                                )}
                                {atomic?.fhirQuery?.codes && atomic.fhirQuery.codes.length > 0 && (
                                  <div className="flex flex-wrap gap-1 mt-1">
                                    {atomic.fhirQuery.codes.map((code, ci) => (
                                      <Badge key={ci} variant="outline" className="text-[9px] bg-white border-gray-300 text-gray-700">
                                        {code.display || code.code}
                                      </Badge>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })()}
                </CardContent>
              </Card>
            ) : (
              <Card className="border border-dashed border-gray-200 rounded-2xl bg-gray-50/50">
                <CardContent className="p-8 text-center">
                  <MousePointer className="w-8 h-8 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-400">Click on a QEB tile to view its logic tree</p>
                </CardContent>
              </Card>
                )}
              </ScrollArea>
            </div>
          </Panel>
        </PanelGroup>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="border-gray-200">
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-bold text-gray-900">{data.queryableBlocks?.length ?? 0}</div>
            <div className="text-sm text-gray-500">Total Criteria</div>
          </CardContent>
        </Card>
        <Card className="border-gray-200">
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-bold text-gray-700">{inclusionQebs.length}</div>
            <div className="text-sm text-gray-500">Inclusion</div>
          </CardContent>
        </Card>
        <Card className="border-gray-200">
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-bold text-gray-500">{exclusionQebs.length}</div>
            <div className="text-sm text-gray-500">Exclusion</div>
          </CardContent>
        </Card>
        <Card className="border-gray-200">
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-bold text-gray-600">{sortedQebs.filter(q => q.internalLogic === "COMPLEX").length}</div>
            <div className="text-sm text-gray-500">Complex Logic</div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function FunnelScreen() {
  const [, navigate] = useLocation();
  const { data, derived, setSelectedQebId, goToStep, stageApprovals, setStageApproval, allStagesApproved } = useWizard();
  const { stageQebMap, killerQebs, unmappedAtomics, classificationCounts } = derived;
  const { toast } = useToast();
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [inspectedCriteria, setInspectedCriteria] = useState<QueryableBlock | null>(null);
  const [expandedStages, setExpandedStages] = useState<Set<string>>(new Set());
  
  const toggleStageExpanded = (stageId: string) => {
    setExpandedStages(prev => {
      const next = new Set(prev);
      if (next.has(stageId)) {
        next.delete(stageId);
      } else {
        next.add(stageId);
      }
      return next;
    });
  };
  
  const killerQebIds = new Set(killerQebs.map(q => q.qebId));
  const basePopulation = 10000;

  // Calculate cumulative patient counts at each stage
  const stageMetrics = useMemo(() => {
    let remaining = basePopulation;
    return (data.funnelStages ?? []).map((stage, idx) => {
      const qebs = stageQebMap.get(stage.stageId) || [];
      const eliminationRate = qebs.reduce((acc, q) => {
        return acc + (q.estimatedEliminationRate || 0);
      }, 0);
      const eliminated = Math.floor(remaining * (eliminationRate / 100));
      const afterStage = Math.max(remaining - eliminated, 0);
      const result = {
        stage,
        qebs,
        hasKiller: qebs.some(q => killerQebIds.has(q.qebId)),
        patientsBefore: remaining,
        eliminated,
        patientsAfter: afterStage,
        percentRemaining: (afterStage / basePopulation) * 100,
        eliminationRate,
      };
      remaining = afterStage;
      return result;
    });
  }, [data.funnelStages, stageQebMap, killerQebIds, basePopulation]);

  const finalPatients = stageMetrics[stageMetrics.length - 1]?.patientsAfter || 0;

  const handleStageApproval = (stageId: string, stageName: string) => {
    // Guard against duplicate approvals
    if (stageApprovals.get(stageId)) {
      toast({
        title: "Already Approved",
        description: `${stageName} has already been approved`,
      });
      return;
    }
    
    const currentApprovedCount = Array.from(stageApprovals.values()).filter(Boolean).length;
    const newApprovedCount = currentApprovedCount + 1;
    const totalStages = data.funnelStages?.length ?? 0;
    
    setStageApproval(stageId, true);
    toast({
      title: "Stage Approved",
      description: newApprovedCount >= totalStages 
        ? "All stages approved! Ready for execution."
        : `${stageName} approved (${newApprovedCount}/${totalStages})`,
    });
  };

  const handleApproveAll = () => {
    const unapprovedStages = (data.funnelStages ?? []).filter(stage => !stageApprovals.get(stage.stageId));
    if (unapprovedStages.length === 0) {
      toast({
        title: "Already Approved",
        description: "All stages have already been approved",
      });
      return;
    }
    
    unapprovedStages.forEach(stage => {
      setStageApproval(stage.stageId, true);
    });
    
    toast({
      title: "All Stages Approved",
      description: `${unapprovedStages.length} stages approved. Ready for execution!`,
    });
  };

  return (
    <div className="h-[calc(100vh-180px)] flex gap-4">
      {/* Left Rail: Stage List - Fixed width */}
      <div className="w-56 flex-shrink-0 bg-white rounded-2xl border border-gray-200 p-4 shadow-sm overflow-hidden flex flex-col">
        <div className="mb-4 pb-3 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900">Stages</h3>
          <p className="text-xs text-gray-500 mt-1">{data.funnelStages?.length ?? 0} total</p>
        </div>
        
        <ScrollArea className="flex-1">
          <div className="space-y-1 pr-2">
            {stageMetrics.map((metric, idx) => {
              const isSelected = selectedStage === metric.stage.stageId;
              const isApproved = stageApprovals.get(metric.stage.stageId);
              
              return (
                <button
                  key={metric.stage.stageId}
                  onClick={() => {
                    setSelectedStage(metric.stage.stageId);
                    setInspectedCriteria(null);
                  }}
                  className={cn(
                    "w-full text-left p-3 rounded-xl transition-all",
                    isSelected ? "bg-gray-900 text-white" : "hover:bg-gray-50",
                    !isSelected && isApproved && "bg-gray-100"
                  )}
                  data-testid={`stage-btn-${idx}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-semibold",
                        isSelected ? "bg-white text-gray-900" : isApproved ? "bg-gray-900 text-white" : "bg-gray-200 text-gray-600"
                      )}>
                        {isApproved ? <Check className="w-3 h-3" /> : idx + 1}
                      </span>
                      <span className={cn(
                        "font-medium text-sm truncate max-w-[100px]",
                        isSelected ? "text-white" : "text-gray-900"
                      )}>
                        {metric.stage.stageName}
                      </span>
                    </div>
                    <span className={cn(
                      "text-xs",
                      isSelected ? "text-gray-400" : "text-gray-400"
                    )}>
                      {metric.qebs.length}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </ScrollArea>
      </div>

      {/* Center: Stage Details */}
      <div className="flex-1 bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
        <div className="p-5 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-gray-900">Funnel Studio</h2>
            <p className="text-sm text-gray-500 mt-1">Review and approve each stage</p>
          </div>
          <div className="flex items-center gap-3">
            {!allStagesApproved && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleApproveAll}
                className="border-gray-300"
                data-testid="btn-approve-all-stages"
              >
                Approve All
              </Button>
            )}
            <div className={cn(
              "px-3 py-1.5 rounded-full text-sm font-medium",
              allStagesApproved ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-600"
            )}>
              {Array.from(stageApprovals.values()).filter(Boolean).length}/{data.funnelStages?.length ?? 0} Approved
            </div>
          </div>
        </div>

        <ScrollArea className="flex-1 p-5">
          <div className="space-y-3">
            {stageMetrics.map((metric, idx) => {
              const isSelected = selectedStage === metric.stage.stageId;
              const isApproved = stageApprovals.get(metric.stage.stageId);
              const inclusionQebs = metric.qebs.filter(q => q.criterionType === "inclusion");
              const exclusionQebs = metric.qebs.filter(q => q.criterionType === "exclusion");
              
              return (
                <div key={metric.stage.stageId}>
                  {/* Stage connector */}
                  {idx > 0 && (
                    <div className="flex items-center justify-center py-2">
                      <div className="w-px h-4 bg-gray-200" />
                    </div>
                  )}
                  
                  <div
                    className={cn(
                      "p-5 rounded-2xl border transition-all cursor-pointer",
                      isSelected 
                        ? "border-gray-900 bg-white shadow-lg" 
                        : "border-gray-200 bg-gray-50/50 hover:border-gray-300"
                    )}
                    onClick={() => {
                      setSelectedStage(metric.stage.stageId);
                      setInspectedCriteria(null);
                    }}
                  >
                    {/* Stage Header */}
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold",
                          isApproved ? "bg-gray-900 text-white" : "bg-gray-200 text-gray-600"
                        )}>
                          {isApproved ? <Check className="w-4 h-4" /> : idx + 1}
                        </div>
                        <div>
                          <h3 className="font-semibold text-gray-900">{metric.stage.stageName}</h3>
                          <p className="text-xs text-gray-500 mt-0.5">{metric.stage.stageDescription}</p>
                        </div>
                      </div>
                      <span className="text-xs text-gray-400">{metric.qebs.length} QEBs</span>
                    </div>

                    {/* Criteria List - Simplified */}
                    <div className="space-y-2">
                      {/* Inclusions */}
                      {inclusionQebs.length > 0 && (
                        <div>
                          <p className="text-[10px] text-gray-400 uppercase tracking-wide mb-2">Inclusions</p>
                          <div className="space-y-1">
                            {inclusionQebs.map((qeb) => (
                              <button
                                key={qeb.qebId}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setInspectedCriteria(qeb);
                                }}
                                className={cn(
                                  "w-full px-3 py-2 rounded-lg text-sm text-left transition-all flex items-center justify-between",
                                  inspectedCriteria?.qebId === qeb.qebId
                                    ? "bg-gray-900 text-white"
                                    : "bg-white border border-gray-200 text-gray-700 hover:border-gray-400"
                                )}
                                data-testid={`criteria-pill-${qeb.qebId}`}
                              >
                                <span className="truncate">
                                  <span className="font-mono text-gray-400 mr-1">{qeb.qebId}:</span>
                                  {qeb.clinicalName}
                                </span>
                                <ChevronRight className={cn(
                                  "w-4 h-4 flex-shrink-0",
                                  inspectedCriteria?.qebId === qeb.qebId ? "text-gray-400" : "text-gray-300"
                                )} />
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                      
                      {/* Exclusions */}
                      {exclusionQebs.length > 0 && (
                        <div>
                          <p className="text-[10px] text-gray-400 uppercase tracking-wide mb-2 mt-3">Exclusions</p>
                          <div className="space-y-1">
                            {exclusionQebs.map((qeb) => (
                              <button
                                key={qeb.qebId}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setInspectedCriteria(qeb);
                                }}
                                className={cn(
                                  "w-full px-3 py-2 rounded-lg text-sm text-left transition-all flex items-center justify-between",
                                  inspectedCriteria?.qebId === qeb.qebId
                                    ? "bg-gray-900 text-white"
                                    : "bg-white border border-gray-200 text-gray-700 hover:border-gray-400"
                                )}
                                data-testid={`criteria-pill-${qeb.qebId}`}
                              >
                                <span className="truncate">
                                  <span className="font-mono text-gray-400 mr-1">{qeb.qebId}:</span>
                                  {qeb.clinicalName}
                                </span>
                                <ChevronRight className={cn(
                                  "w-4 h-4 flex-shrink-0",
                                  inspectedCriteria?.qebId === qeb.qebId ? "text-gray-400" : "text-gray-300"
                                )} />
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Approval Button */}
                    {isSelected && !isApproved && (
                      <div className="mt-4 pt-4 border-t border-gray-100">
                        <Button
                          size="sm"
                          className="bg-gray-900 hover:bg-gray-800 w-full"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleStageApproval(metric.stage.stageId, metric.stage.stageName);
                          }}
                          data-testid={`approve-stage-${idx}`}
                        >
                          <Check className="w-4 h-4 mr-2" />
                          Approve Stage
                        </Button>
                      </div>
                    )}
                    
                    {isApproved && (
                      <div className="flex items-center gap-2 text-gray-500 mt-3 pt-3 border-t border-gray-100">
                        <Check className="w-4 h-4" />
                        <span className="text-xs">Approved</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>

        {/* Footer */}
        <div className="p-4 border-t border-gray-100 flex items-center justify-end gap-3">
          <Button variant="outline" onClick={() => goToStep("assurance")}>
            Back
          </Button>
          <Button 
            className="bg-gray-900 hover:bg-gray-800"
            onClick={() => navigate("/site-feasibility")}
            data-testid="btn-site360-analysis"
          >
            Site360 Analysis
            <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
        </div>
      </div>

      {/* Right Panel: Inspector */}
      <div className="w-72 flex-shrink-0 bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
        <div className="p-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900">Details</h3>
        </div>

        <ScrollArea className="flex-1 p-4">
          {inspectedCriteria ? (
            <div className="space-y-4">
              {/* Header */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className={cn(
                    "px-2 py-0.5 rounded text-[10px] font-medium uppercase",
                    inspectedCriteria.criterionType === "inclusion" 
                      ? "bg-gray-100 text-gray-600" 
                      : "bg-gray-200 text-gray-700"
                  )}>
                    {inspectedCriteria.criterionType}
                  </span>
                </div>
                <h4 className="font-semibold text-gray-900">{inspectedCriteria.clinicalName}</h4>
                <p className="text-sm text-gray-500 mt-1">{inspectedCriteria.clinicalDescription}</p>
              </div>

              <Separator />

              {/* Protocol text */}
              <div>
                <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide mb-2">Criteria Text</p>
                <p className="text-sm text-gray-600 bg-gray-50 p-3 rounded-lg border border-gray-100">
                  {inspectedCriteria.protocolText}
                </p>
              </div>

              {/* Metrics */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-[10px] text-gray-400 uppercase">Logic</p>
                  <p className="text-sm font-semibold text-gray-900 mt-1">{inspectedCriteria.internalLogic}</p>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-[10px] text-gray-400 uppercase">Atomics</p>
                  <p className="text-sm font-semibold text-gray-900 mt-1">{inspectedCriteria.atomicCount}</p>
                </div>
              </div>

              {/* Atomic Criteria List */}
              <div>
                <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide mb-2">
                  Atomic Criteria ({inspectedCriteria.atomicIds.length})
                </p>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {inspectedCriteria.atomicIds.map((atomicId) => {
                    const atomic = derived.atomicLookup.get(atomicId);
                    return (
                      <div key={atomicId} className="p-2 bg-gray-50 rounded-lg border border-gray-100">
                        <p className="font-mono text-[10px] text-gray-400 mb-1">{atomicId}</p>
                        <p className="text-xs text-gray-700 line-clamp-2">
                          {atomic?.atomicText || atomicId}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Combined SQL */}
              {inspectedCriteria.combinedSql && (
                <div>
                  <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide mb-2">Combined SQL</p>
                  <div className="bg-gray-900 rounded-lg p-3 max-h-64 overflow-auto">
                    <pre className="text-[11px] font-mono text-gray-300 whitespace-pre-wrap">
                      {inspectedCriteria.combinedSql
                        .replace(/\bSELECT\b/gi, '\nSELECT')
                        .replace(/\bFROM\b/gi, '\nFROM')
                        .replace(/\bWHERE\b/gi, '\nWHERE')
                        .replace(/\bAND\b/gi, '\n  AND')
                        .replace(/\bOR\b/gi, '\n  OR')
                        .replace(/\bJOIN\b/gi, '\nJOIN')
                        .replace(/\bLEFT JOIN\b/gi, '\nLEFT JOIN')
                        .replace(/\bINNER JOIN\b/gi, '\nINNER JOIN')
                        .replace(/\bGROUP BY\b/gi, '\nGROUP BY')
                        .replace(/\bORDER BY\b/gi, '\nORDER BY')
                        .replace(/\bHAVING\b/gi, '\nHAVING')
                        .replace(/\bUNION\b/gi, '\n\nUNION')
                        .replace(/\bINTERSECT\b/gi, '\n\nINTERSECT')
                        .replace(/\bEXCEPT\b/gi, '\n\nEXCEPT')
                        .trim()}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-12">
              <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                <Info className="w-6 h-6 text-gray-400" />
              </div>
              <p className="text-sm text-gray-500">Select a criteria to view details</p>
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  );
}

function UnmappedConceptsScreen() {
  const { derived, conceptCorrections, setConceptCorrection } = useWizard();
  const { unmappedAtomics, qebLookup } = derived;
  const [searchTerms, setSearchTerms] = useState<Record<string, string>>({});
  const [searchResults, setSearchResults] = useState<Record<string, OmopConcept[]>>({});
  const [selectedConcepts, setSelectedConcepts] = useState<Record<string, number | null>>({});

  const handleSearch = (atomicId: string) => {
    const term = searchTerms[atomicId] || "";
    if (term.length > 2) {
      setSearchResults(prev => ({
        ...prev,
        [atomicId]: searchMockOmop(term),
      }));
    }
  };

  const handleSelectConcept = (atomicId: string, conceptId: number) => {
    setSelectedConcepts(prev => ({
      ...prev,
      [atomicId]: conceptId,
    }));
    setConceptCorrection(atomicId, [conceptId]);
  };

  const fixedCount = Array.from(conceptCorrections.keys()).length;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl bg-white border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-gray-900">
              Fix Unmapped OMOP Concepts
            </h2>
            <p className="text-gray-500 mt-1">
              {unmappedAtomics.length} atomics need OMOP concept mapping
            </p>
          </div>
          <Badge className={cn(
            "text-sm",
            fixedCount === unmappedAtomics.length ? "bg-gray-100 text-gray-700" : "bg-gray-100 text-gray-700"
          )}>
            {fixedCount}/{unmappedAtomics.length} fixed
          </Badge>
        </div>

        <div className="space-y-4">
          {unmappedAtomics.slice(0, 10).map(atomic => {
            const parentQeb = qebLookup.get(`QEB_${atomic.originalCriterionId}`);
            const results = searchResults[atomic.atomicId] || [];
            const selected = selectedConcepts[atomic.atomicId];
            const isCorrected = conceptCorrections.has(atomic.atomicId);
            
            return (
              <Card key={atomic.atomicId} className={cn(
                "border",
                isCorrected ? "border-gray-300 bg-gray-50" : "border-gray-300"
              )}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      {isCorrected ? (
                        <CheckCircle2 className="w-5 h-5 text-gray-700" />
                      ) : (
                        <AlertTriangle className="w-5 h-5 text-gray-600" />
                      )}
                      <div>
                        <p className="font-mono text-sm text-gray-700">{atomic.atomicId}</p>
                        <p className="font-medium text-gray-900">"{atomic.atomicText}"</p>
                      </div>
                    </div>
                    <Badge variant="outline" className="text-xs">
                      {parentQeb?.clinicalName || atomic.originalCriterionId}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-xs text-gray-500">
                    <strong>LLM Reasoning:</strong> {atomic.queryabilityClassification.reasoning}
                  </p>
                  
                  <div className="flex gap-2">
                    <Input
                      placeholder="Search OMOP concepts..."
                      value={searchTerms[atomic.atomicId] || ""}
                      onChange={(e) => setSearchTerms(prev => ({
                        ...prev,
                        [atomic.atomicId]: e.target.value,
                      }))}
                      className="flex-1"
                      data-testid={`search-input-${atomic.atomicId}`}
                    />
                    <Button 
                      variant="outline" 
                      size="sm"
                      onClick={() => handleSearch(atomic.atomicId)}
                      data-testid={`search-btn-${atomic.atomicId}`}
                    >
                      <Search className="w-4 h-4" />
                    </Button>
                  </div>

                  {results.length > 0 && (
                    <div className="space-y-2 border rounded-lg p-2 bg-white">
                      <p className="text-xs font-medium text-gray-500">Results:</p>
                      {results.map(concept => (
                        <button
                          key={concept.conceptId}
                          onClick={() => handleSelectConcept(atomic.atomicId, concept.conceptId!)}
                          className={cn(
                            "w-full text-left p-2 rounded text-sm transition-colors",
                            selected === concept.conceptId 
                              ? "bg-gray-900 text-white" 
                              : "hover:bg-gray-100"
                          )}
                          data-testid={`concept-option-${concept.conceptId}`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-xs">{concept.conceptId}</span>
                            <Badge variant="outline" className="text-xs">
                              {concept.vocabularyId}
                            </Badge>
                          </div>
                          <p className="font-medium">{concept.conceptName}</p>
                          <p className="text-xs text-gray-500">Domain: {concept.domain}</p>
                        </button>
                      ))}
                    </div>
                  )}

                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" className="text-xs">
                      Mark as Screening-Only
                    </Button>
                    <Button variant="ghost" size="sm" className="text-xs">
                      Skip for Now
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
          
          {unmappedAtomics.length > 10 && (
            <p className="text-center text-sm text-gray-500">
              ... and {unmappedAtomics.length - 10} more
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function ClassificationsScreen() {
  const { data, derived, overrides, setOverride } = useWizard();
  const [filter, setFilter] = useState<"all" | QueryabilityClassification["category"]>("all");
  
  const filteredAtomics = useMemo(() => {
    if (filter === "all") return data.atomicCriteria ?? [];
    return (data.atomicCriteria ?? []).filter(a =>
      overrides.get(a.atomicId) === filter ||
      (!overrides.has(a.atomicId) && a.queryabilityClassification.category === filter)
    );
  }, [data.atomicCriteria, filter, overrides]);

  const categoryIcon = (cat: QueryabilityClassification["category"]) => {
    switch (cat) {
      case "QUERYABLE": return <Check className="w-4 h-4" />;
      case "SCREENING_ONLY": return <Clock className="w-4 h-4" />;
      case "NOT_APPLICABLE": return <XCircle className="w-4 h-4" />;
    }
  };

  const categoryColor = (cat: QueryabilityClassification["category"]) => {
    switch (cat) {
      case "QUERYABLE": return "bg-gray-800 text-white";
      case "SCREENING_ONLY": return "bg-gray-500 text-white";
      case "NOT_APPLICABLE": return "bg-gray-300 text-gray-700";
    }
  };

  const overrideCount = overrides.size;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl bg-white border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-gray-900">
              Review Classifications
            </h2>
            <p className="text-gray-500 mt-1">
              Override LLM decisions if needed
            </p>
          </div>
          <Badge className="bg-gray-100 text-gray-700">
            {overrideCount} overrides made
          </Badge>
        </div>

        <div className="flex gap-2 mb-4 flex-wrap">
          {(["all", "QUERYABLE", "SCREENING_ONLY", "NOT_APPLICABLE"] as const).map(cat => (
            <Button
              key={cat}
              variant={filter === cat ? "default" : "outline"}
              size="sm"
              onClick={() => setFilter(cat)}
              className={filter === cat ? "bg-gray-900" : ""}
              data-testid={`filter-${cat.toLowerCase()}`}
            >
              {cat === "all" ? "All" : cat.replace("_", " ")}
              <Badge variant="secondary" className="ml-2 text-xs">
                {cat === "all"
                  ? data.atomicCriteria?.length ?? 0
                  : (data.atomicCriteria ?? []).filter(a => a.queryabilityClassification.category === cat).length
                }
              </Badge>
            </Button>
          ))}
        </div>

        <div className="space-y-3">
          {filteredAtomics.slice(0, 15).map(atomic => {
            const currentCategory = overrides.get(atomic.atomicId) || atomic.queryabilityClassification.category;
            const isOverridden = overrides.has(atomic.atomicId);
            
            return (
              <Card key={atomic.atomicId} className={cn(
                "border",
                isOverridden && "border-gray-300 bg-gray-50"
              )}>
                <CardContent className="py-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3 flex-1">
                      <div className={cn("w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0", categoryColor(currentCategory))}>
                        {categoryIcon(currentCategory)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-mono text-xs text-gray-500">{atomic.atomicId}</span>
                          <Badge variant="outline" className="text-xs">
                            {atomic.originalCriterionId}
                          </Badge>
                          {isOverridden && (
                            <Badge className="bg-gray-700 text-white text-xs">
                              OVERRIDDEN
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-gray-900 font-medium">
                          "{atomic.atomicText}"
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          Confidence: {(atomic.queryabilityClassification.confidence * 100).toFixed(0)}% — {atomic.queryabilityClassification.reasoning}
                        </p>
                      </div>
                    </div>
                    <div className="flex gap-2 flex-shrink-0">
                      {currentCategory !== "QUERYABLE" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setOverride(atomic.atomicId, "QUERYABLE")}
                          data-testid={`override-queryable-${atomic.atomicId}`}
                        >
                          → QUERYABLE
                        </Button>
                      )}
                      {currentCategory !== "SCREENING_ONLY" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setOverride(atomic.atomicId, "SCREENING_ONLY")}
                        >
                          → SCREENING
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
          
          {filteredAtomics.length > 15 && (
            <p className="text-center text-sm text-gray-500">
              ... and {filteredAtomics.length - 15} more
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function DataAssuranceScreen() {
  const { data, derived, overrides, setOverride, conceptCorrections, setConceptCorrection, selectedQebId, setSelectedQebId, goToStep } = useWizard();
  const { unmappedAtomics, qebLookup, atomicLookup } = derived;
  const { toast } = useToast();
  
  // Auto-select the right step based on what needs attention
  // Only count unmapped atomics that haven't been corrected (must have at least one concept mapped)
  const uncorrectedAtomics = unmappedAtomics.filter(a => {
    const corrections = conceptCorrections.get(a.atomicId);
    return !corrections || corrections.length === 0;
  });
  const conceptsRemaining = uncorrectedAtomics.length;
  const initialStep = conceptsRemaining > 0 ? "concepts" : "classifications";
  const [activeStep, setActiveStep] = useState<"concepts" | "classifications">(initialStep);
  
  const [searchTerms, setSearchTerms] = useState<Record<string, string>>({});
  const [searchResults, setSearchResults] = useState<Record<string, OmopConcept[]>>({});
  const [selectedConcepts, setSelectedConcepts] = useState<Record<string, number | null>>({});
  const [classFilter, setClassFilter] = useState<"all" | QueryabilityClassification["category"]>("all");
  const [visibleConcepts, setVisibleConcepts] = useState(5);
  const [visibleClassifications, setVisibleClassifications] = useState(10);
  const [expandedAtomics, setExpandedAtomics] = useState<Set<string>>(new Set());

  const toggleAtomicExpanded = (atomicId: string) => {
    setExpandedAtomics(prev => {
      const next = new Set(prev);
      if (next.has(atomicId)) {
        next.delete(atomicId);
      } else {
        next.add(atomicId);
      }
      return next;
    });
  };

  const handleSearch = (atomicId: string) => {
    const term = searchTerms[atomicId] || "";
    if (term.length > 2) {
      setSearchResults(prev => ({
        ...prev,
        [atomicId]: searchMockOmop(term),
      }));
    }
  };

  const handleSelectConcept = (atomicId: string, conceptId: number) => {
    setSelectedConcepts(prev => ({ ...prev, [atomicId]: conceptId }));
    setConceptCorrection(atomicId, [conceptId]);
    // Calculate remaining after this correction - subtract 1 since current correction isn't in conceptCorrections yet
    const remaining = conceptsRemaining - 1;
    toast({
      title: "Concept Mapped",
      description: remaining > 0 ? `${remaining} concept${remaining > 1 ? 's' : ''} remaining` : "All concepts mapped!",
    });
  };
  
  const handleOverride = (atomicId: string, category: QueryabilityClassification["category"]) => {
    setOverride(atomicId, category);
    toast({
      title: "Classification Updated",
      description: `Changed to ${category.replace("_", " ").toLowerCase()}`,
    });
  };

  const filteredAtomics = useMemo(() => {
    if (classFilter === "all") return data.atomicCriteria ?? [];
    return (data.atomicCriteria ?? []).filter(a =>
      overrides.get(a.atomicId) === classFilter ||
      (!overrides.has(a.atomicId) && a.queryabilityClassification.category === classFilter)
    );
  }, [data.atomicCriteria, classFilter, overrides]);

  const categoryIcon = (cat: QueryabilityClassification["category"]) => {
    switch (cat) {
      case "QUERYABLE": return <Check className="w-4 h-4" />;
      case "SCREENING_ONLY": return <Clock className="w-4 h-4" />;
      case "NOT_APPLICABLE": return <XCircle className="w-4 h-4" />;
    }
  };

  const categoryColor = (cat: QueryabilityClassification["category"]) => {
    switch (cat) {
      case "QUERYABLE": return "bg-gray-800 text-white";
      case "SCREENING_ONLY": return "bg-gray-500 text-white";
      case "NOT_APPLICABLE": return "bg-gray-300 text-gray-700";
    }
  };

  const overrideCount = overrides.size;
  const allConceptsFixed = conceptsRemaining === 0;

  // Steps for the sequential flow
  const steps = [
    { id: "concepts", label: "Map Concepts", done: allConceptsFixed, count: conceptsRemaining },
    { id: "classifications", label: "Review Classifications", done: false, count: overrideCount },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Progress Header */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Data Assurance Review</h2>
            <p className="text-sm text-gray-500 mt-1">Fix data issues to ensure accurate query execution</p>
          </div>
          <Button
            variant="outline"
            onClick={() => goToStep("funnel")}
            className="text-gray-600"
          >
            Continue to Funnel
            <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
        </div>

        {/* Step Indicators */}
        <div className="flex gap-4">
          {steps.map((step, index) => (
            <button
              key={step.id}
              onClick={() => setActiveStep(step.id as "concepts" | "classifications")}
              className={cn(
                "flex-1 p-4 rounded-xl border-2 transition-all text-left",
                activeStep === step.id 
                  ? "border-gray-900 bg-gray-50" 
                  : step.done 
                    ? "border-gray-300 bg-gray-50"
                    : "border-gray-200 hover:border-gray-300"
              )}
              data-testid={`step-${step.id}`}
            >
              <div className="flex items-center gap-3">
                <div className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium",
                  step.done 
                    ? "bg-gray-700 text-white"
                    : activeStep === step.id
                      ? "bg-gray-900 text-white"
                      : "bg-gray-200 text-gray-600"
                )}>
                  {step.done ? <Check className="w-4 h-4" /> : index + 1}
                </div>
                <div>
                  <p className={cn(
                    "font-medium",
                    step.done ? "text-gray-700" : "text-gray-900"
                  )}>{step.label}</p>
                  <p className="text-xs text-gray-500">
                    {step.id === "concepts" 
                      ? step.done ? "All concepts mapped" : `${step.count} to fix`
                      : `${step.count} overrides applied`
                    }
                  </p>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="p-6">
          {activeStep === "concepts" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">Map OMOP Concepts</h3>
                <Badge className={cn(
                  conceptsRemaining === 0 ? "bg-gray-100 text-gray-700" : "bg-gray-100 text-gray-700"
                )}>
                  {conceptsRemaining} remaining
                </Badge>
              </div>

              {conceptsRemaining === 0 ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-3 p-4 bg-gray-50 border border-gray-300 rounded-xl">
                    <CheckCircle2 className="w-6 h-6 text-gray-600 flex-shrink-0" />
                    <div>
                      <h4 className="font-medium text-gray-800">All Concepts Mapped</h4>
                      <p className="text-sm text-gray-700">No unmapped OMOP concepts detected</p>
                    </div>
                  </div>
                  
                  <div className="border border-gray-200 rounded-xl overflow-hidden">
                    <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
                      <h4 className="text-sm font-semibold text-gray-700">Mapped Concepts Overview</h4>
                    </div>
                    <div className="max-h-80 overflow-y-auto">
                      {data.atomicCriteria
                        .filter(a => a.omopQuery?.conceptIds?.some(id => id && id !== 0))
                        .slice(0, 20)
                        .map(atomic => (
                          <div key={atomic.atomicId} className="px-4 py-3 border-b border-gray-100 last:border-b-0 hover:bg-gray-50">
                            <div className="flex items-start gap-3">
                              <div className="w-2 h-2 rounded-full bg-gray-700 mt-2 flex-shrink-0" />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-gray-800 mb-2">{atomic.atomicText}</p>
                                <div className="flex flex-wrap gap-1.5">
                                  {atomic.omopQuery?.conceptIds?.slice(0, 4).map((conceptId, idx) => {
                                    const conceptName = atomic.omopQuery?.conceptNames?.[idx];
                                    const vocabularyId = atomic.omopQuery?.vocabularyIds?.[idx];
                                    if (!conceptId || conceptId === 0) return null;
                                    return (
                                      <div key={idx} className="inline-flex items-center gap-1 bg-gray-100 rounded-md px-2 py-1">
                                        <span className="font-mono text-[10px] text-gray-600">{conceptId}</span>
                                        <span className="text-[10px] text-gray-800">{conceptName}</span>
                                        {vocabularyId && (
                                          <Badge className="bg-gray-100 text-gray-700 text-[8px] ml-1">{vocabularyId}</Badge>
                                        )}
                                      </div>
                                    );
                                  })}
                                  {(atomic.omopQuery?.conceptIds?.filter(id => id && id !== 0).length || 0) > 4 && (
                                    <Badge variant="outline" className="text-[10px] bg-gray-50">
                                      +{(atomic.omopQuery?.conceptIds?.filter(id => id && id !== 0).length || 0) - 4} more
                                    </Badge>
                                  )}
                                </div>
                              </div>
                              <Badge className="bg-gray-100 text-gray-700 text-[10px] flex-shrink-0">
                                {atomic.omopQuery?.conceptIds?.filter(id => id && id !== 0).length || 0} concepts
                              </Badge>
                            </div>
                          </div>
                        ))}
                      {(data.atomicCriteria ?? []).filter(a => a.omopQuery?.conceptIds?.some(id => id && id !== 0)).length > 20 && (
                        <div className="px-4 py-2 text-center text-xs text-gray-500 bg-gray-50">
                          +{(data.atomicCriteria ?? []).filter(a => a.omopQuery?.conceptIds?.some(id => id && id !== 0)).length - 20} more mapped criteria
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  {uncorrectedAtomics.slice(0, visibleConcepts).map(atomic => {
                    const parentQeb = qebLookup.get(`QEB_${atomic.originalCriterionId}`);
                    const results = searchResults[atomic.atomicId] || [];
                    const selected = selectedConcepts[atomic.atomicId];
                    
                    return (
                      <Card key={atomic.atomicId} className="border-2 border-gray-300">
                        <CardContent className="p-4 space-y-3">
                          <div className="flex items-start justify-between">
                            <div className="flex items-center gap-2">
                              <AlertTriangle className="w-5 h-5 text-gray-600" />
                              <div>
                                <p className="font-medium text-gray-900">"{atomic.atomicText}"</p>
                                <p className="text-xs text-gray-500 mt-1">
                                  {parentQeb?.clinicalName || atomic.originalCriterionId}
                                </p>
                              </div>
                            </div>
                          </div>
                          
                          <div className="flex gap-2">
                            <Input
                              placeholder="Search OMOP concepts..."
                              value={searchTerms[atomic.atomicId] || ""}
                              onChange={(e) => setSearchTerms(prev => ({ ...prev, [atomic.atomicId]: e.target.value }))}
                              className="flex-1"
                              data-testid={`search-input-${atomic.atomicId}`}
                            />
                            <Button variant="outline" size="sm" onClick={() => handleSearch(atomic.atomicId)}>
                              <Search className="w-4 h-4" />
                            </Button>
                          </div>

                          {results.length > 0 && (
                            <div className="space-y-1 border rounded-lg p-2 bg-white">
                              {results.map(concept => (
                                <button
                                  key={concept.conceptId}
                                  onClick={() => handleSelectConcept(atomic.atomicId, concept.conceptId!)}
                                  className={cn(
                                    "w-full text-left p-2 rounded text-sm transition-colors",
                                    selected === concept.conceptId ? "bg-gray-900 text-white" : "hover:bg-gray-100"
                                  )}
                                >
                                  <div className="flex items-center justify-between">
                                    <span className="font-mono text-xs">{concept.conceptId}</span>
                                    <Badge variant="outline" className="text-xs">{concept.vocabularyId}</Badge>
                                  </div>
                                  <p className="font-medium">{concept.conceptName}</p>
                                </button>
                              ))}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    );
                  })}
                  {uncorrectedAtomics.length > visibleConcepts && (
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={() => setVisibleConcepts(prev => prev + 10)}
                      data-testid="btn-show-more-concepts"
                    >
                      <ChevronDown className="w-4 h-4 mr-2" />
                      Show More ({uncorrectedAtomics.length - visibleConcepts} remaining)
                    </Button>
                  )}
                </>
              )}
            </div>
          )}

          {activeStep === "classifications" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">Override Classifications</h3>
                <Badge className="bg-gray-100 text-gray-700">{overrideCount} overrides</Badge>
              </div>

              <div className="flex gap-2 mb-4 flex-wrap">
                {(["all", "QUERYABLE", "SCREENING_ONLY", "NOT_APPLICABLE"] as const).map(cat => (
                  <Button
                    key={cat}
                    variant={classFilter === cat ? "default" : "outline"}
                    size="sm"
                    onClick={() => setClassFilter(cat)}
                    className={classFilter === cat ? "bg-gray-900" : ""}
                  >
                    {cat === "all" ? "All" : cat.replace("_", " ")}
                  </Button>
                ))}
              </div>

              <div className="space-y-2">
                {filteredAtomics.slice(0, visibleClassifications).map(atomic => {
                  const currentCategory = overrides.get(atomic.atomicId) || atomic.queryabilityClassification.category;
                  const isOverridden = overrides.has(atomic.atomicId);
                  const isExpanded = expandedAtomics.has(atomic.atomicId);
                  const hasOmopData = atomic.omopQuery && (atomic.omopQuery.conceptIds?.length > 0 || atomic.omopQuery.sqlTemplate);
                  
                  return (
                    <Card key={atomic.atomicId} className={cn(
                      "border transition-all",
                      isOverridden && "border-gray-300 bg-gray-50"
                    )}>
                      <CardContent className="py-3">
                        <div 
                          className="flex items-start justify-between gap-4 cursor-pointer"
                          onClick={() => toggleAtomicExpanded(atomic.atomicId)}
                          data-testid={`atomic-row-${atomic.atomicId}`}
                        >
                          <div className="flex items-start gap-3 flex-1">
                            <div className={cn("w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0", categoryColor(currentCategory))}>
                              {categoryIcon(currentCategory)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="text-sm text-gray-900 font-medium">"{atomic.atomicText}"</p>
                                {hasOmopData && (
                                  <ChevronDown className={cn(
                                    "w-4 h-4 text-gray-400 transition-transform",
                                    isExpanded && "rotate-180"
                                  )} />
                                )}
                              </div>
                              <p className="text-xs text-gray-500 mt-1">
                                {atomic.queryabilityClassification.reasoning}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0" onClick={e => e.stopPropagation()}>
                            <Badge className={cn(
                              "text-xs",
                              currentCategory === "QUERYABLE" && "bg-gray-100 text-gray-700",
                              currentCategory === "SCREENING_ONLY" && "bg-gray-100 text-gray-700",
                              currentCategory === "NOT_APPLICABLE" && "bg-gray-100 text-gray-700"
                            )}>
                              {currentCategory === "QUERYABLE" ? "Queryable" : 
                               currentCategory === "SCREENING_ONLY" ? "Screening Only" : "N/A"}
                            </Badge>
                            {currentCategory !== "QUERYABLE" && (
                              <Button variant="outline" size="sm" onClick={() => handleOverride(atomic.atomicId, "QUERYABLE")}>
                                Mark Queryable
                              </Button>
                            )}
                            {currentCategory !== "SCREENING_ONLY" && (
                              <Button variant="ghost" size="sm" onClick={() => handleOverride(atomic.atomicId, "SCREENING_ONLY")}>
                                Mark Screening
                              </Button>
                            )}
                          </div>
                        </div>
                        
                        {isExpanded && hasOmopData && (
                          <div className="mt-4 pt-4 border-t border-gray-100 space-y-4">
                            {atomic.omopQuery?.conceptIds && atomic.omopQuery.conceptIds.length > 0 && (
                              <div>
                                <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2 flex items-center gap-2">
                                  <Database className="w-3 h-3" />
                                  OMOP Concepts
                                </h4>
                                <div className="space-y-1">
                                  {atomic.omopQuery.conceptIds.map((conceptId, idx) => (
                                    <div key={idx} className="flex items-center gap-3 text-sm bg-gray-50 rounded-lg px-3 py-2">
                                      <Badge variant="outline" className="font-mono text-xs">
                                        {conceptId || "unmapped"}
                                      </Badge>
                                      <span className="text-gray-700">
                                        {atomic.omopQuery?.conceptNames?.[idx] || "Unknown concept"}
                                      </span>
                                      {atomic.omopQuery?.vocabularyIds?.[idx] && (
                                        <Badge className="bg-gray-200 text-gray-600 text-xs">
                                          {atomic.omopQuery.vocabularyIds[idx]}
                                        </Badge>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                            
                            {atomic.omopQuery?.sqlTemplate && (
                              <div>
                                <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2 flex items-center gap-2">
                                  <FileText className="w-3 h-3" />
                                  SQL Query
                                </h4>
                                <pre className="text-xs bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto font-mono">
                                  {atomic.omopQuery.sqlTemplate}
                                </pre>
                              </div>
                            )}
                            
                            {atomic.fhirQuery?.resourceType && (
                              <div>
                                <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2 flex items-center gap-2">
                                  <Activity className="w-3 h-3" />
                                  FHIR Query
                                </h4>
                                <div className="bg-gray-50 border border-gray-300 rounded-lg p-3">
                                  <div className="flex items-center gap-2 mb-2">
                                    <Badge className="bg-gray-100 text-gray-700 text-xs">
                                      {atomic.fhirQuery.resourceType}
                                    </Badge>
                                    {atomic.fhirQuery.queryExecutable && (
                                      <Badge className="bg-gray-100 text-gray-700 text-[10px]">Executable</Badge>
                                    )}
                                  </div>
                                  {atomic.fhirQuery.searchParams && (
                                    <pre className="text-xs bg-white rounded p-2 overflow-x-auto font-mono text-gray-700 border border-gray-200">
                                      {atomic.fhirQuery.searchParams}
                                    </pre>
                                  )}
                                  {atomic.fhirQuery.codes && atomic.fhirQuery.codes.length > 0 && (
                                    <div className="mt-2 flex flex-wrap gap-1">
                                      {atomic.fhirQuery.codes.map((code, ci) => (
                                        <Badge key={ci} variant="outline" className="text-[9px] bg-white border-gray-300 text-gray-700">
                                          {code.display || code.code}
                                        </Badge>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
                {filteredAtomics.length > visibleClassifications && (
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => setVisibleClassifications(prev => prev + 20)}
                    data-testid="btn-show-more-classifications"
                  >
                    <ChevronDown className="w-4 h-4 mr-2" />
                    Show More ({filteredAtomics.length - visibleClassifications} remaining)
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function QEBDetailScreen() {
  const { data, derived, selectedQebId, setSelectedQebId, goToStep } = useWizard();
  const { qebLookup, atomicLookup } = derived;
  
  const qeb = selectedQebId ? qebLookup.get(selectedQebId) : null;
  
  if (!qeb) {
    return (
      <div className="space-y-6">
        <div className="rounded-2xl bg-white border border-gray-200 p-6 shadow-sm">
          <h2 className="text-2xl font-semibold tracking-tight text-gray-900 mb-4">
            Criteria Group Details
          </h2>
          <p className="text-gray-500 mb-4">Select a criteria group from the list below to view details:</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(data.queryableBlocks ?? []).map(block => (
              <Card 
                key={block.qebId}
                className="cursor-pointer hover:border-gray-400 transition-colors"
                onClick={() => setSelectedQebId(block.qebId)}
                data-testid={`qeb-card-${block.qebId}`}
              >
                <CardContent className="py-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="font-mono text-xs">
                      {block.qebId}
                    </Badge>
                    <Badge className={block.criterionType === "inclusion" ? "bg-gray-700" : "bg-gray-500"}>
                      {block.criterionType}
                    </Badge>
                    {block.isKillerCriterion && (
                      <Badge className="bg-gray-900">
                        <Zap className="w-3 h-3 mr-1" />
                        HIGH IMPACT
                      </Badge>
                    )}
                  </div>
                  <p className="font-medium text-gray-900 mt-2">{block.clinicalName}</p>
                  <p className="text-xs text-gray-500">{block.atomicCount} atomics • Stage {block.funnelStageOrder}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const atomics = qeb.atomicIds.map(id => atomicLookup.get(id)).filter((a): a is AtomicCriterion => !!a);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl bg-white border border-gray-200 p-6 shadow-sm">
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Button variant="ghost" size="sm" onClick={() => setSelectedQebId(null)}>
                <ChevronLeft className="w-4 h-4 mr-1" />
                Back
              </Button>
            </div>
            <h2 className="text-2xl font-semibold tracking-tight text-gray-900 flex items-center gap-2">
              {qeb.qebId}: {qeb.clinicalName}
              {qeb.isKillerCriterion && (
                <Badge className="bg-gray-900">
                  <Zap className="w-3 h-3 mr-1" />
                  HIGH IMPACT
                </Badge>
              )}
            </h2>
            <p className="text-gray-500 mt-1">
              Stage {qeb.funnelStageOrder}: {qeb.funnelStage}
            </p>
          </div>
          <div className="text-right">
            <Badge className={qeb.criterionType === "inclusion" ? "bg-gray-700" : "bg-gray-500"}>
              {qeb.criterionType}
            </Badge>
            <p className="text-xs text-gray-500 mt-1">
              {qeb.queryableStatus.replace("_", " ")}
            </p>
            {qeb.estimatedEliminationRate && (
              <p className="text-sm font-semibold text-gray-900 mt-1">
                {qeb.estimatedEliminationRate}% elimination
              </p>
            )}
          </div>
        </div>

        <Card className="mb-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <FileText className="w-4 h-4" />
              Criteria Text
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-gray-700 whitespace-pre-wrap">{qeb.protocolText}</p>
          </CardContent>
        </Card>

        <Card className="mb-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Activity className="w-4 h-4" />
              Atomics ({qeb.atomicCount})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {atomics.map(atomic => (
                <div key={atomic.atomicId} className="flex items-center gap-2 text-sm">
                  {atomic.queryabilityClassification.category === "QUERYABLE" ? (
                    <Check className="w-4 h-4 text-gray-700" />
                  ) : atomic.queryabilityClassification.category === "SCREENING_ONLY" ? (
                    <Clock className="w-4 h-4 text-gray-500" />
                  ) : (
                    <XCircle className="w-4 h-4 text-gray-400" />
                  )}
                  <span className="font-mono text-xs text-gray-500">{atomic.atomicId}:</span>
                  <span className="text-gray-900">{atomic.atomicText}</span>
                  <Badge variant="outline" className="text-xs">
                    {atomic.queryabilityClassification.category}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="mb-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Database className="w-4 h-4" />
              Combined SQL
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-gray-500 mb-2">Logic: {qeb.sqlLogicExplanation}</p>
            <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-xs overflow-x-auto max-h-48">
              <code>{qeb.combinedSql}</code>
            </pre>
          </CardContent>
        </Card>

        {qeb.omopConcepts.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">OMOP Concepts ({qeb.omopConcepts.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {qeb.omopConcepts.map((concept, idx) => (
                  <Badge key={idx} variant="outline" className="text-xs">
                    {concept.conceptId} - {concept.conceptName}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function ExecuteScreen() {
  const { data, derived, overrides, conceptCorrections, goToStep, allStagesApproved, stageApprovals } = useWizard();
  const { stageQebMap, classificationCounts, unmappedAtomics } = derived;
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionPhase, setExecutionPhase] = useState<"idle" | "connecting" | "querying" | "aggregating" | "complete">("idle");
  const [currentStageIndex, setCurrentStageIndex] = useState(0);
  const [results, setResults] = useState<{stage: string; count: number; percentage: number; queryTime: number; status: "pending" | "running" | "complete"}[] | null>(null);
  const [analystNotes, setAnalystNotes] = useState("");
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [finalApproval, setFinalApproval] = useState(false);
  const [, navigate] = useLocation();

  const basePopulation = 10000;
  const dataSources = [
    { name: "OMOP CDM", status: "connected", records: "10,000", type: "EHR" },
    { name: "Claims DB", status: "connected", records: "8,450", type: "Claims" },
    { name: "Lab Results", status: "connected", records: "9,200", type: "Lab" },
  ];

  const handleExecute = () => {
    setIsExecuting(true);
    setExecutionPhase("connecting");
    
    const stages = [
      { stage: "Base Population", count: 10000, percentage: 100, queryTime: 0.12 },
      { stage: "Stage 1: Disease Indication", count: 850, percentage: 8.5, queryTime: 1.23 },
      { stage: "Stage 2: Prior Therapy", count: 720, percentage: 7.2, queryTime: 0.89 },
      { stage: "Stage 3: Performance Status", count: 650, percentage: 6.5, queryTime: 0.45 },
      { stage: "Stage 4: Tumor Assessment", count: 580, percentage: 5.8, queryTime: 1.67 },
      { stage: "Stage 5: Medical History", count: 520, percentage: 5.2, queryTime: 0.78 },
      { stage: "Stage 6: Lab Values", count: 480, percentage: 4.8, queryTime: 1.12 },
      { stage: "Stage 7: Drug Sensitivity", count: 450, percentage: 4.5, queryTime: 0.56 },
      { stage: "Stage 8: Consent/Compliance", count: 420, percentage: 4.2, queryTime: 0.23 },
    ];

    // Simulate execution phases
    setTimeout(() => setExecutionPhase("querying"), 500);
    
    // Initialize results with pending status
    setResults(stages.map(s => ({ ...s, status: "pending" as const })));
    
    // Simulate progressive execution
    let idx = 0;
    const interval = setInterval(() => {
      if (idx >= stages.length) {
        clearInterval(interval);
        setExecutionPhase("aggregating");
        setTimeout(() => {
          setExecutionPhase("complete");
          setIsExecuting(false);
          setShowApprovalModal(true);
        }, 800);
        return;
      }
      
      setCurrentStageIndex(idx);
      setResults(prev => prev?.map((r, i) => ({
        ...r,
        status: i < idx ? "complete" : i === idx ? "running" : "pending"
      })) || null);
      
      setTimeout(() => {
        setResults(prev => prev?.map((r, i) => ({
          ...r,
          status: i <= idx ? "complete" : "pending"
        })) || null);
      }, 400);
      
      idx++;
    }, 600);
  };

  // Check if all unmapped atomics have been corrected (must have at least one concept mapped)
  const uncorrectedAtomics = unmappedAtomics.filter(a => {
    const corrections = conceptCorrections.get(a.atomicId);
    return !corrections || corrections.length === 0;
  });
  const allConceptsMapped = uncorrectedAtomics.length === 0;
  
  const readinessChecks = [
    { label: "All stages approved", status: allStagesApproved, action: "funnel" as WizardStep },
    { label: "OMOP concepts mapped", status: allConceptsMapped, action: "assurance" as WizardStep },
    { label: "Classification overrides reviewed", status: true, action: "assurance" as WizardStep },
    { label: "Data source connected", status: true, action: null },
  ];
  const allChecksPass = readinessChecks.every(c => c.status);

  return (
    <div className="h-[calc(100vh-180px)] flex gap-4">
      {/* Left Panel: Configuration & Status */}
      <div className="w-80 flex-shrink-0 space-y-4 overflow-y-auto">
        {/* Readiness Panel */}
        <div className="bg-white rounded-2xl border border-gray-200 p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Shield className="w-5 h-5 text-gray-700" />
            <h3 className="font-semibold text-gray-900">Execution Readiness</h3>
          </div>
          <div className="space-y-2">
            {readinessChecks.map((check, i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {check.status ? (
                    <CheckCircle2 className="w-4 h-4 text-gray-700" />
                  ) : (
                    <XCircle className="w-4 h-4 text-gray-500" />
                  )}
                  <span className={cn(
                    "text-sm",
                    check.status ? "text-gray-700" : "text-gray-600"
                  )}>{check.label}</span>
                </div>
                {!check.status && check.action && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs text-gray-500 hover:text-gray-900"
                    onClick={() => goToStep(check.action!)}
                  >
                    Fix
                    <ChevronRight className="w-3 h-3 ml-1" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Data Sources Panel */}
        <div className="bg-white rounded-2xl border border-gray-200 p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Database className="w-5 h-5 text-gray-700" />
            <h3 className="font-semibold text-gray-900">Data Sources</h3>
          </div>
          <div className="space-y-2">
            {dataSources.map((source, i) => (
              <div key={i} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-gray-700" />
                  <span className="text-sm font-medium text-gray-900">{source.name}</span>
                </div>
                <Badge variant="outline" className="text-xs">{source.records}</Badge>
              </div>
            ))}
          </div>
        </div>

        {/* Summary Stats */}
        <div className="bg-white rounded-2xl border border-gray-200 p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="w-5 h-5 text-gray-700" />
            <h3 className="font-semibold text-gray-900">Validation Summary</h3>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Criteria Groups</span>
              <span className="font-medium">{data.summary?.totalQEBs ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Atomic Criteria</span>
              <span className="font-medium">{data.summary?.totalAtomicsConsolidated ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Queryable</span>
              <span className="font-medium text-gray-700">{classificationCounts.queryable}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Overrides Applied</span>
              <span className="font-medium">{overrides.size}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Concept Fixes</span>
              <span className="font-medium">{conceptCorrections.size}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Center: Execution Canvas */}
      <div className="flex-1 bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
        <div className="p-4 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Execution Command Center</h2>
            <p className="text-sm text-gray-500">
              {executionPhase === "idle" && "Configure and launch your patient feasibility query"}
              {executionPhase === "connecting" && "Connecting to data sources..."}
              {executionPhase === "querying" && `Executing stage ${currentStageIndex + 1} of ${(data.funnelStages?.length ?? 0) + 1}...`}
              {executionPhase === "aggregating" && "Aggregating results..."}
              {executionPhase === "complete" && "Execution complete - Review results below"}
            </p>
          </div>
          <Badge className={cn(
            executionPhase === "idle" && "bg-gray-100 text-gray-700",
            executionPhase === "connecting" && "bg-gray-100 text-gray-700",
            executionPhase === "querying" && "bg-gray-100 text-gray-700",
            executionPhase === "aggregating" && "bg-gray-100 text-gray-700",
            executionPhase === "complete" && "bg-gray-100 text-gray-700"
          )}>
            {executionPhase === "idle" && "Ready"}
            {executionPhase === "connecting" && <><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Connecting</>}
            {executionPhase === "querying" && <><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Running</>}
            {executionPhase === "aggregating" && <><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Finalizing</>}
            {executionPhase === "complete" && <><CheckCircle2 className="w-3 h-3 mr-1" /> Complete</>}
          </Badge>
        </div>

        <ScrollArea className="flex-1 p-4">
          {!results ? (
            <div className="flex flex-col items-center justify-center h-full py-12">
              {allChecksPass ? (
                <>
                  <div className="w-24 h-24 rounded-full bg-gray-100 flex items-center justify-center mb-6">
                    <Play className="w-12 h-12 text-gray-700" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">Ready to Execute</h3>
                  <p className="text-sm text-gray-500 text-center max-w-md mb-6">
                    Your eligibility funnel has been validated and is ready to run against the patient database.
                    This will query {basePopulation.toLocaleString()} patients across {data.funnelStages?.length ?? 0} stages.
                  </p>
                  <Button
                    size="lg"
                    className="px-8 bg-gray-900 hover:bg-gray-800"
                    disabled={isExecuting}
                    onClick={handleExecute}
                    data-testid="btn-execute-main"
                  >
                    <Sparkles className="w-5 h-5 mr-2" />
                    Execute Funnel Query
                  </Button>
                </>
              ) : (
                <>
                  <div className="w-24 h-24 rounded-full bg-gray-100 flex items-center justify-center mb-6">
                    <AlertTriangle className="w-12 h-12 text-gray-600" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">Action Required</h3>
                  <p className="text-sm text-gray-500 text-center max-w-md mb-4">
                    Complete the following items before you can execute the feasibility query:
                  </p>
                  <div className="space-y-2 mb-6">
                    {readinessChecks.filter(c => !c.status).map((check, i) => (
                      <div key={i} className="flex items-center gap-2 text-gray-700 bg-gray-50 px-4 py-2 rounded-lg">
                        <XCircle className="w-4 h-4" />
                        <span className="text-sm font-medium">{check.label}</span>
                      </div>
                    ))}
                  </div>
                  {(() => {
                    const firstBlocker = readinessChecks.find(c => !c.status && c.action);
                    return firstBlocker ? (
                      <Button
                        size="lg"
                        className="px-8 bg-gray-600 hover:bg-gray-700"
                        onClick={() => goToStep(firstBlocker.action!)}
                        data-testid="btn-fix-blockers"
                      >
                        <ArrowRight className="w-5 h-5 mr-2" />
                        {firstBlocker.action === "funnel" ? "Go to Funnel Studio" : "Go to Data Assurance"}
                      </Button>
                    ) : null;
                  })()}
                </>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {/* Live execution waterfall */}
              {results.map((result, idx) => (
                <div
                  key={idx}
                  className={cn(
                    "p-4 rounded-xl border-2 transition-all",
                    result.status === "running" && "border-gray-400 bg-gray-50",
                    result.status === "complete" && "border-gray-300 bg-gray-50",
                    result.status === "pending" && "border-gray-100 bg-gray-50 opacity-50"
                  )}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      {result.status === "pending" && (
                        <div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center">
                          <Clock className="w-3 h-3 text-gray-400" />
                        </div>
                      )}
                      {result.status === "running" && (
                        <div className="w-6 h-6 rounded-full bg-gray-500 flex items-center justify-center">
                          <Loader2 className="w-3 h-3 text-white animate-spin" />
                        </div>
                      )}
                      {result.status === "complete" && (
                        <div className="w-6 h-6 rounded-full bg-gray-700 flex items-center justify-center">
                          <Check className="w-3 h-3 text-white" />
                        </div>
                      )}
                      <span className="font-medium text-gray-900">{result.stage}</span>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      {result.status === "complete" && (
                        <>
                          <span className="text-gray-500">{result.queryTime.toFixed(2)}s</span>
                          <span className="font-bold text-gray-900">{result.count.toLocaleString()}</span>
                        </>
                      )}
                    </div>
                  </div>
                  {result.status !== "pending" && (
                    <div className="relative h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "absolute left-0 top-0 h-full rounded-full transition-all duration-500",
                          result.status === "running" ? "bg-gray-500" : "bg-gray-700"
                        )}
                        style={{ width: `${result.percentage}%` }}
                      />
                    </div>
                  )}
                </div>
              ))}

              {/* Final result summary */}
              {executionPhase === "complete" && results && (
                <div className="mt-6 p-6 bg-gradient-to-r from-gray-700 to-gray-600 rounded-2xl text-white">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <Target className="w-6 h-6" />
                        <span className="text-lg font-semibold">Eligible Patient Cohort</span>
                      </div>
                      <p className="text-gray-300 text-sm">
                        Total execution time: {results.reduce((a, r) => a + r.queryTime, 0).toFixed(2)}s
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="text-4xl font-bold">{results[results.length - 1].count.toLocaleString()}</span>
                      <p className="text-gray-300 text-sm">
                        {results[results.length - 1].percentage.toFixed(2)}% of base
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </ScrollArea>

        {/* Action footer */}
        <div className="p-4 border-t border-gray-100 bg-gray-50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {finalApproval && (
              <Badge className="bg-gray-100 text-gray-700">
                <Fingerprint className="w-3 h-3 mr-1" />
                Analyst Approved
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {executionPhase === "complete" && (
              <>
                <Button variant="outline" onClick={() => {
                  setResults(null);
                  setExecutionPhase("idle");
                  setFinalApproval(false);
                }}>
                  <RefreshCw className="w-4 h-4 mr-1" />
                  Re-run
                </Button>
                <Button
                  className="bg-gray-900 hover:bg-gray-800"
                  disabled={!finalApproval}
                >
                  <ArrowRight className="w-4 h-4 mr-1" />
                  Export Results
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Right Panel: Analyst Notes */}
      <div className="w-72 flex-shrink-0 bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
        <div className="p-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-gray-700" />
            <h3 className="font-semibold text-gray-900">Analyst Notes</h3>
          </div>
        </div>
        <div className="flex-1 p-4">
          <textarea
            className="w-full h-full min-h-[200px] p-3 text-sm border border-gray-200 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-gray-900"
            placeholder="Add notes about this feasibility run..."
            value={analystNotes}
            onChange={(e) => setAnalystNotes(e.target.value)}
          />
        </div>
        {executionPhase === "complete" && !finalApproval && (
          <div className="p-4 border-t border-gray-100">
            <Button
              className="w-full bg-gray-900 hover:bg-gray-800"
              onClick={() => setFinalApproval(true)}
              data-testid="btn-final-approval"
            >
              <Fingerprint className="w-4 h-4 mr-1" />
              Approve Results
            </Button>
            <p className="text-xs text-gray-500 text-center mt-2">
              Your approval is required before export
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// Eligibility extraction state type
type EligibilityExtractionState = 'idle' | 'detecting_sections' | 'awaiting_section_confirmation' | 'extracting' | 'interpreting' | 'validating' | 'completed' | 'failed';

export default function QEBValidationWizardPage() {
  const searchString = useSearch();
  const [, navigate] = useLocation();

  const [data, setData] = useState<QebValidationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [currentStep, setCurrentStep] = useState<WizardStep>("overview");
  const [selectedQebId, setSelectedQebId] = useState<string | null>(null);
  const [overrides, setOverrides] = useState(new Map<string, QueryabilityClassification["category"]>());
  const [conceptCorrections, setConceptCorrections] = useState(new Map<string, number[]>());
  const [stageApprovals, setStageApprovals] = useState(new Map<string, boolean>());
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // Eligibility extraction state
  const [extractionState, setExtractionState] = useState<EligibilityExtractionState>('idle');
  const [extractionJobId, setExtractionJobId] = useState<string | null>(null);
  const [phaseProgress, setPhaseProgress] = useState<{ phase: string; progress: number; stage?: number } | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Section confirmation state (similar to SOA page confirmation)
  const [showSectionConfirmModal, setShowSectionConfirmModal] = useState(false);
  const [detectedSections, setDetectedSections] = useState<EligibilitySectionInfo[]>([]);
  const [editableSections, setEditableSections] = useState<EligibilitySectionInfo[]>([]);
  const [pdfPageNumber, setPdfPageNumber] = useState(1);
  const [pdfNumPages, setPdfNumPages] = useState(0);
  const [pdfScale, setPdfScale] = useState(1.0);

  const studyId = useMemo(() => {
    const params = new URLSearchParams(searchString);
    const id = params.get("studyId");
    return id || null;
  }, [searchString]);

  // Subscribe to SSE events for extraction progress
  const subscribeToEvents = (jobId: string) => {
    // Close any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    console.log('[Eligibility] Subscribing to SSE events for job:', jobId);
    const eventSource = api.eligibility.subscribeToEvents(jobId);
    eventSourceRef.current = eventSource;

    eventSource.addEventListener('progress', (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[Eligibility] Progress event:', data);
        setExtractionState(data.status as EligibilityExtractionState);
        if (data.phase_progress) {
          setPhaseProgress(data.phase_progress);
        }

        // Show section confirmation modal when awaiting confirmation
        if (data.status === 'awaiting_section_confirmation' && data.detected_sections?.sections) {
          const sections = data.detected_sections.sections as EligibilitySectionInfo[];
          console.log('[Eligibility] Detected sections:', sections);
          setDetectedSections(sections);
          setEditableSections(sections);
          setShowSectionConfirmModal(true);
          setLoading(false);
          // Navigate to first section page
          if (sections[0]?.pageStart) {
            setPdfPageNumber(sections[0].pageStart);
          }
        }
      } catch (err) {
        console.error('[Eligibility] Failed to parse progress event:', err);
      }
    });

    eventSource.addEventListener('complete', async (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[Eligibility] Complete event:', data);
        eventSource.close();
        eventSourceRef.current = null;

        if (data.status === 'completed') {
          setExtractionState('completed');
          // Load the results
          const results = await api.eligibility.getResults(jobId);
          // Prefer qeb_result from Stage 12 (contains queryableBlocks, atomicCriteria, funnelStages)
          if (results.qeb_result?.qeb_output?.queryableBlocks) {
            setData(results.qeb_result.qeb_output as QebValidationData);
          } else if (results.feasibility_result?.queryableBlocks) {
            // Fallback for backward compatibility
            setData(results.feasibility_result as QebValidationData);
          } else if (results.feasibility_result) {
            setData(results.feasibility_result as QebValidationData);
          } else {
            setError(`Eligibility extraction completed but no QEB data found. The feasibility analysis may not have been run.`);
          }
          setLoading(false);
        } else if (data.status === 'failed') {
          setExtractionState('failed');
          setError(data.error_message || 'Eligibility extraction failed');
          setLoading(false);
        }
      } catch (err) {
        console.error('[Eligibility] Failed to handle complete event:', err);
        setError('Failed to process extraction results');
        setLoading(false);
      }
    });

    eventSource.addEventListener('error', (event) => {
      console.error('[Eligibility] SSE error:', event);
      // Don't close on error - may be temporary network issue
    });
  };

  useEffect(() => {
    async function startOrLoadExtraction() {
      if (!studyId) {
        setError("No studyId provided in URL. Please navigate from a protocol page.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        // Step 1: Check for existing eligibility job
        console.log('[Eligibility] Checking for existing job for:', studyId);
        const jobInfo = await api.eligibility.getLatestJob(studyId);
        console.log('[Eligibility] Latest job info:', jobInfo);

        // Case 1: Completed job with results - load directly
        if (jobInfo.has_job && jobInfo.status === 'completed') {
          console.log('[Eligibility] Loading completed job results:', jobInfo.job_id);
          setExtractionJobId(jobInfo.job_id!);
          setExtractionState('completed');

          const results = await api.eligibility.getResults(jobInfo.job_id!);
          console.log('[Eligibility] Results received:', results);

          // Prefer qeb_result from Stage 12 (contains queryableBlocks, atomicCriteria, funnelStages)
          if (results.qeb_result?.qeb_output?.queryableBlocks) {
            setData(results.qeb_result.qeb_output as QebValidationData);
          } else if (results.feasibility_result?.queryableBlocks) {
            // Fallback for backward compatibility
            setData(results.feasibility_result as QebValidationData);
          } else if (results.feasibility_result) {
            setData(results.feasibility_result as QebValidationData);
          } else {
            setError(`Eligibility extraction completed but no QEB data found for: ${studyId}. The feasibility analysis may not have been run.`);
          }
          setLoading(false);
          return;
        }

        // Case 2: Job awaiting section confirmation - show confirmation UI
        if (jobInfo.has_job && jobInfo.status === 'awaiting_section_confirmation') {
          console.log('[Eligibility] Resuming from section confirmation');
          setExtractionJobId(jobInfo.job_id!);
          setExtractionState('awaiting_section_confirmation');

          // Get job status to retrieve detected sections
          const jobStatus = await api.eligibility.getJobStatus(jobInfo.job_id!);
          if (jobStatus.detected_sections?.sections) {
            const sections = jobStatus.detected_sections.sections;
            setDetectedSections(sections);
            setEditableSections(sections);
            setShowSectionConfirmModal(true);
            if (sections[0]?.pageStart) {
              setPdfPageNumber(sections[0].pageStart);
            }
          }
          setLoading(false);
          return;
        }

        // Case 3: Job in progress - subscribe to SSE events
        if (jobInfo.has_job && ['detecting_sections', 'extracting', 'interpreting', 'validating'].includes(jobInfo.status || '')) {
          console.log('[Eligibility] Resuming in-progress job:', jobInfo.job_id);
          setExtractionJobId(jobInfo.job_id!);
          setExtractionState(jobInfo.status as EligibilityExtractionState);
          subscribeToEvents(jobInfo.job_id!);
          return;
        }

        // Case 4: No job, or job failed - start fresh extraction
        console.log('[Eligibility] Starting new extraction for:', studyId);

        const response = await api.eligibility.startExtraction(studyId);
        console.log('[Eligibility] Extraction started:', response);
        setExtractionJobId(response.job_id);

        // Check if backend returned awaiting_section_confirmation (failed job with sections)
        if (response.status === 'awaiting_section_confirmation') {
          console.log('[Eligibility] Failed job reset to section confirmation');
          setExtractionState('awaiting_section_confirmation');

          // Get detected sections from job
          const jobStatus = await api.eligibility.getJobStatus(response.job_id);
          if (jobStatus.detected_sections?.sections) {
            const sections = jobStatus.detected_sections.sections;
            setDetectedSections(sections);
            setEditableSections(sections);
            setShowSectionConfirmModal(true);
            if (sections[0]?.pageStart) {
              setPdfPageNumber(sections[0].pageStart);
            }
          }
          setLoading(false);
          return;
        }

        // Normal flow - detecting sections
        setExtractionState('detecting_sections');
        // Subscribe to SSE events for progress updates
        subscribeToEvents(response.job_id);

      } catch (err) {
        console.error('[Eligibility] Failed to start/load extraction:', err);
        setError(err instanceof Error ? err.message : 'Failed to start eligibility extraction');
        setExtractionState('failed');
        setLoading(false);
      }
    }

    startOrLoadExtraction();

    // Cleanup SSE on unmount
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [studyId]);

  const derived = useMemo(() => {
    if (!data) return null;
    return deriveQebData(data);
  }, [data]);

  useEffect(() => {
    if (scrollAreaRef.current) {
      const viewport = scrollAreaRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (viewport) {
        viewport.scrollTo({ top: 0, behavior: 'instant' });
      }
    }
  }, [currentStep]);

  const goToStep = (step: WizardStep) => {
    setCurrentStep(step);
  };
  
  const setOverride = (atomicId: string, category: QueryabilityClassification["category"]) => {
    setOverrides(prev => new Map(prev).set(atomicId, category));
  };
  
  const setConceptCorrection = (atomicId: string, conceptIds: number[]) => {
    setConceptCorrections(prev => new Map(prev).set(atomicId, conceptIds));
  };

  const setStageApproval = (stageId: string, approved: boolean) => {
    setStageApprovals(prev => new Map(prev).set(stageId, approved));
  };

  // Handle section confirmation (human-in-the-loop checkpoint)
  const handleConfirmSections = async (useOriginal: boolean) => {
    if (!extractionJobId) return;

    setShowSectionConfirmModal(false);
    setLoading(true);
    setExtractionState('extracting');

    try {
      const sectionsToUse = useOriginal ? detectedSections : editableSections;
      console.log('[Eligibility] Confirming sections:', sectionsToUse);
      await api.eligibility.confirmSections(extractionJobId, sectionsToUse);
      // Continue listening for progress events
      subscribeToEvents(extractionJobId);
    } catch (err) {
      console.error('[Eligibility] Error confirming sections:', err);
      setError(err instanceof Error ? err.message : 'Failed to confirm sections');
      setExtractionState('failed');
      setLoading(false);
    }
  };

  // Handle section edit (update page ranges)
  const handleSectionEdit = (index: number, field: 'pageStart' | 'pageEnd', value: number) => {
    setEditableSections(prev => {
      const updated = [...prev];
      const section = updated[index];
      const newPageStart = field === 'pageStart' ? value : section.pageStart;
      const newPageEnd = field === 'pageEnd' ? value : section.pageEnd;
      updated[index] = {
        ...section,
        [field]: value,
        pages: Array.from(
          { length: Math.max(0, newPageEnd - newPageStart + 1) },
          (_, i) => newPageStart + i
        ),
      };
      return updated;
    });
  };

  const allStagesApproved = useMemo(() => {
    if (!data?.funnelStages) return false;
    const stages = data.funnelStages;
    return stages.length > 0 && stages.every(stage => stageApprovals.get(stage.stageId) === true);
  }, [data, stageApprovals]);

  const handlePrev = () => {
    const idx = WIZARD_STEPS.findIndex(s => s.id === currentStep);
    if (idx > 0) {
      setCurrentStep(WIZARD_STEPS[idx - 1].id);
    }
  };

  const handleNext = () => {
    const idx = WIZARD_STEPS.findIndex(s => s.id === currentStep);
    if (idx < WIZARD_STEPS.length - 1) {
      setCurrentStep(WIZARD_STEPS[idx + 1].id);
    }
  };

  // Section confirmation view with PDF viewer - split layout (similar to SOA)
  if (showSectionConfirmModal) {
    return (
      <div className="flex flex-col h-full bg-gray-50">
        {/* Header */}
        <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-6 h-6 text-gray-600" />
            <div>
              <h1 className="text-lg font-semibold text-gray-800">Eligibility Sections Detected</h1>
              <p className="text-sm text-muted-foreground">
                Verify the detected sections and click on page numbers to preview in PDF
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => handleConfirmSections(false)}
              disabled={editableSections.length === 0}
            >
              Use Edited Sections
            </Button>
            <Button
              onClick={() => handleConfirmSections(true)}
              disabled={detectedSections.length === 0}
            >
              <Check className="w-4 h-4 mr-2" />
              Confirm & Continue
            </Button>
          </div>
        </div>

        {/* Split Panel Layout */}
        <PanelGroup direction="horizontal" className="flex-1">
          {/* Left Panel - Section Cards */}
          <Panel defaultSize={40} minSize={30}>
            <ScrollArea className="h-full">
              <div className="p-6 space-y-4">
                <div className="text-sm text-muted-foreground mb-4">
                  We detected <span className="font-semibold text-gray-800">{editableSections.length}</span> eligibility section(s).
                  Click on page numbers to view in PDF.
                </div>

                {editableSections.map((section, index) => (
                  <Card key={section.id} className="overflow-hidden">
                    <CardHeader className="py-3 px-4 bg-gray-50 border-b">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base font-semibold">{section.title}</CardTitle>
                        <Badge variant={section.type === 'inclusion' ? 'default' : 'secondary'}>
                          {section.type}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="p-4">
                      <div className="grid grid-cols-2 gap-4 mb-3">
                        <div>
                          <label className="text-sm text-gray-600">Start Page</label>
                          <Input
                            type="number"
                            value={section.pageStart}
                            onChange={(e) => handleSectionEdit(index, 'pageStart', parseInt(e.target.value) || 1)}
                            className="mt-1"
                            min={1}
                          />
                        </div>
                        <div>
                          <label className="text-sm text-gray-600">End Page</label>
                          <Input
                            type="number"
                            value={section.pageEnd}
                            onChange={(e) => handleSectionEdit(index, 'pageEnd', parseInt(e.target.value) || 1)}
                            className="mt-1"
                            min={section.pageStart}
                          />
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        <span className="text-sm text-muted-foreground mr-1">Pages:</span>
                        {section.pages.map((page) => (
                          <Button
                            key={page}
                            variant={pdfPageNumber === page ? "default" : "outline"}
                            size="sm"
                            className="h-7 px-2 text-xs"
                            onClick={() => setPdfPageNumber(page)}
                          >
                            {page}
                          </Button>
                        ))}
                      </div>
                      <div className="mt-2 text-xs text-muted-foreground">
                        Confidence: {(section.confidence * 100).toFixed(0)}%
                      </div>
                    </CardContent>
                  </Card>
                ))}

                {editableSections.length === 0 && (
                  <div className="text-center py-12 text-muted-foreground">
                    <AlertCircle className="w-10 h-10 mx-auto mb-3 text-gray-400" />
                    <p className="font-medium">No eligibility sections detected</p>
                    <p className="text-sm">Please check the PDF document.</p>
                  </div>
                )}
              </div>
            </ScrollArea>
          </Panel>

          <PanelResizeHandle className="w-2 bg-gray-200 hover:bg-primary/20 transition-colors cursor-col-resize" />

          {/* Right Panel - PDF Viewer */}
          <Panel defaultSize={60} minSize={40} className="bg-white flex flex-col">
            {/* PDF Toolbar */}
            <div className="h-12 bg-white border-b border-gray-200 flex items-center justify-between px-4">
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setPdfPageNumber(p => Math.max(1, p - 1))}>
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <span className="text-sm">
                  Page {pdfPageNumber} of {pdfNumPages}
                </span>
                <Button variant="outline" size="sm" onClick={() => setPdfPageNumber(p => Math.min(pdfNumPages, p + 1))}>
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setPdfScale(s => Math.max(0.5, s - 0.1))}>
                  <ZoomOut className="w-4 h-4" />
                </Button>
                <span className="text-sm w-12 text-center">{Math.round(pdfScale * 100)}%</span>
                <Button variant="outline" size="sm" onClick={() => setPdfScale(s => Math.min(2, s + 0.1))}>
                  <ZoomIn className="w-4 h-4" />
                </Button>
              </div>
            </div>

            {/* PDF Document */}
            <ScrollArea className="flex-1">
              <div className="flex justify-center p-4">
                <Document
                  file={`http://localhost:8080/api/v1/protocols/${studyId}/pdf/annotated`}
                  onLoadSuccess={({ numPages }) => setPdfNumPages(numPages)}
                  loading={<Loader2 className="w-8 h-8 animate-spin" />}
                >
                  <Page
                    pageNumber={pdfPageNumber}
                    scale={pdfScale}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                  />
                </Document>
              </div>
            </ScrollArea>
          </Panel>
        </PanelGroup>
      </div>
    );
  }

  if (loading) {
    // Show extraction progress UI when extraction is running
    const getProgressMessage = () => {
      switch (extractionState) {
        case 'detecting_sections':
          return 'Detecting eligibility sections in protocol...';
        case 'awaiting_section_confirmation':
          return 'Waiting for section confirmation...';
        case 'extracting':
          return 'Extracting eligibility criteria...';
        case 'interpreting':
          return `Interpreting criteria (Stage ${phaseProgress?.stage || '...'})...`;
        case 'validating':
          return 'Validating extraction quality...';
        default:
          return 'Loading eligibility criteria data...';
      }
    };

    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-4 max-w-md">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <span className="text-muted-foreground text-center">{getProgressMessage()}</span>
          {phaseProgress && (
            <div className="w-full">
              <Progress value={phaseProgress.progress} className="h-2" />
              <span className="text-xs text-muted-foreground mt-1 block text-center">
                {phaseProgress.phase}: {phaseProgress.progress}%
              </span>
            </div>
          )}
          {extractionState !== 'idle' && extractionState !== 'completed' && (
            <span className="text-xs text-muted-foreground">
              This may take a few minutes for complex protocols
            </span>
          )}
        </div>
      </div>
    );
  }

  if (error || !data || !derived) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-4 text-gray-600">
          <AlertCircle className="w-8 h-8" />
          <span>{error || "Failed to load data"}</span>
          <Button variant="outline" onClick={() => window.location.reload()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  const wizardContext: WizardContextType = {
    data,
    derived,
    selectedQebId,
    setSelectedQebId,
    overrides,
    setOverride,
    conceptCorrections,
    setConceptCorrection,
    stageApprovals,
    setStageApproval,
    allStagesApproved,
    goToStep,
  };

  const currentStepIndex = WIZARD_STEPS.findIndex(s => s.id === currentStep);

  return (
    <WizardContext.Provider value={wizardContext}>
      <div className="h-full flex flex-col bg-gradient-to-b from-gray-50 to-white">
        <WizardStepper currentStep={currentStep} onStepClick={goToStep} />
        
        <ScrollArea className="flex-1">
          <div className="px-4 py-6">
            {currentStep === "overview" && <OverviewScreen />}
            {currentStep === "qeb-overview" && <QebOverviewScreen />}
            {currentStep === "funnel" && <FunnelScreen />}
            {currentStep === "assurance" && <DataAssuranceScreen />}
            {currentStep === "execute" && <ExecuteScreen />}

            <div className="flex items-center justify-between pt-8 mt-8 border-t border-gray-100">
              <Button
                variant="ghost"
                onClick={handlePrev}
                disabled={currentStepIndex === 0}
                className="text-gray-600 hover:text-gray-900 hover:bg-gray-100/50 rounded-full px-6"
                data-testid="btn-prev-step"
              >
                <ChevronLeft className="w-4 h-4 mr-2" />
                Previous
              </Button>
              {currentStepIndex < WIZARD_STEPS.length - 1 ? (
                <Button 
                  onClick={handleNext} 
                  className="bg-gray-900 hover:bg-gray-800 text-white rounded-full px-6 shadow-sm"
                  data-testid="btn-next-step"
                >
                  Continue
                  <ChevronRight className="w-4 h-4 ml-2" />
                </Button>
              ) : (
                <Button 
                  className="bg-gray-700 hover:bg-gray-800 text-white rounded-full px-6 shadow-sm" 
                  onClick={() => navigate("/")}
                  data-testid="btn-complete"
                >
                  <Check className="w-4 h-4 mr-2" />
                  Complete Validation
                </Button>
              )}
            </div>
          </div>
        </ScrollArea>
      </div>
    </WizardContext.Provider>
  );
}
