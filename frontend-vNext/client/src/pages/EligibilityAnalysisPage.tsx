import { useState, useEffect, useMemo, useRef } from "react";
import { useSearch, useLocation } from "wouter";
import { api, getPdfUrl } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/esm/Page/AnnotationLayer.css';
import 'react-pdf/dist/esm/Page/TextLayer.css';
import {
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  Database,
  AlertCircle,
  Loader2,
  ClipboardCheck,
  Minus,
  Plus,
  Activity,
  ZoomIn,
  ZoomOut,
  ExternalLink,
  Maximize2,
  Minimize2,
} from "lucide-react";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  `pdfjs-dist/build/pdf.worker.min.mjs`,
  import.meta.url,
).toString();

function FormattedCriteriaText({ text }: { text: string }) {
  const lines = text.split(/\n|(?<=\.)\s+(?=[A-Z])|(?<=\))\s+(?=[A-Z])/);
  
  const elements: React.ReactNode[] = [];
  let currentListItems: string[] = [];
  let currentListType: 'numbered' | 'bullet' | null = null;

  const flushList = (key: string) => {
    if (currentListItems.length > 0 && currentListType) {
      if (currentListType === 'numbered') {
        elements.push(
          <ol key={key} className="list-decimal list-inside space-y-1 my-2 ml-2">
            {currentListItems.map((item: string, i: number) => (
              <li key={i} className="text-sm text-gray-700">{item}</li>
            ))}
          </ol>
        );
      } else {
        elements.push(
          <ul key={key} className="list-disc list-inside space-y-1 my-2 ml-2">
            {currentListItems.map((item: string, i: number) => (
              <li key={i} className="text-sm text-gray-700">{item}</li>
            ))}
          </ul>
        );
      }
      currentListItems = [];
      currentListType = null;
    }
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) return;

    const numberedMatch = trimmed.match(/^(\d+)\.\s*(.+)/);
    const bulletMatch = trimmed.match(/^[•\-\*]\s*(.+)/);
    const letterMatch = trimmed.match(/^([a-z])\)\s*(.+)/i);

    if (numberedMatch || letterMatch) {
      if (currentListType === 'bullet') {
        flushList(`list-${idx}`);
      }
      currentListType = 'numbered';
      currentListItems.push(numberedMatch ? numberedMatch[2] : letterMatch![2]);
    } else if (bulletMatch) {
      if (currentListType === 'numbered') {
        flushList(`list-${idx}`);
      }
      currentListType = 'bullet';
      currentListItems.push(bulletMatch[1]);
    } else {
      flushList(`list-${idx}`);
      elements.push(
        <p key={`p-${idx}`} className="text-sm text-gray-900 mb-1">
          {trimmed}
        </p>
      );
    }
  });

  flushList('list-final');

  return <div className="space-y-1">{elements.length > 0 ? elements : <p className="text-sm text-gray-900">{text}</p>}</div>;
}

// Eligibility data is now fetched from the database via api.eligibility methods

interface OmopConcept {
  concept_id: number;
  concept_code: string;
  concept_name: string;
  vocabulary_id: string;
  domain_id: string;
  concept_class_id: string;
  standard_concept: string;
  match_type: string;
}

interface ExpressionNode {
  nodeId: string;
  nodeType: "operator" | "atomic" | "temporal";
  operator?: "AND" | "OR" | "NOT";
  operands?: ExpressionNode[];
  atomicText?: string;
  omopTable?: string;
  omopConcepts?: OmopConcept[];
  strategy?: string;
  numericConstraintStructured?: {
    value: number;
    operator: string;
    unit: string;
    parameter: string;
  };
  temporalConstraint?: {
    operator: string;
    anchor: string;
  };
  operand?: ExpressionNode;
}

interface AtomicCriterion {
  atomicId: string;
  atomicText: string;
  omopTable: string;
  strategy?: string;
  omopConcepts?: OmopConcept[];
}

interface Criterion {
  criterionId: string;
  originalCriterionId?: string;
  originalText: string;
  type: "Inclusion" | "Exclusion";
  expression?: ExpressionNode;
  atomicCriteria?: AtomicCriterion[];
  sqlTemplate?: string;
  decompositionStrategy?: string;
}

interface CriteriaData {
  protocolId: string;
  criteria: Criterion[];
}




function ExpressionTreeNode({ 
  node, 
  depth = 0, 
  expandAll,
  atomicCriteriaMap = {}
}: { 
  node: ExpressionNode; 
  depth?: number; 
  expandAll?: boolean;
  atomicCriteriaMap?: Record<string, AtomicCriterion>;
}) {
  const [isManuallyToggled, setIsManuallyToggled] = useState(false);
  const [manualExpanded, setManualExpanded] = useState(depth < 2);
  const prevExpandAll = useRef(expandAll);
  
  useEffect(() => {
    if (prevExpandAll.current !== expandAll) {
      setIsManuallyToggled(false);
      prevExpandAll.current = expandAll;
    }
  }, [expandAll]);
  
  const effectiveExpanded = isManuallyToggled 
    ? manualExpanded 
    : (expandAll !== undefined ? expandAll : depth < 2);
  
  const handleToggle = (open: boolean) => {
    setIsManuallyToggled(true);
    setManualExpanded(open);
  };

  if (node.nodeType === "atomic") {
    const atomicData = atomicCriteriaMap[node.nodeId];
    const omopConcepts = atomicData?.omopConcepts || [];
    
    return (
      <div className="flex items-start gap-3 py-2 px-3 bg-gray-50 rounded-lg border border-gray-200">
        <div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0 mt-0.5">
          <ClipboardCheck className="w-3 h-3 text-gray-600" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-900 font-medium">{node.atomicText}</p>
          {node.omopTable && (
            <div className="flex items-center gap-2 mt-1">
              <Badge variant="outline" className="text-xs bg-white">
                <Database className="w-3 h-3 mr-1" />
                {node.omopTable}
              </Badge>
            </div>
          )}
          {omopConcepts.length > 0 && (
            <div className="mt-3 space-y-2">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">OMOP Concepts</p>
              <div className="space-y-1.5">
                {omopConcepts.map((concept) => (
                  <div 
                    key={concept.concept_id} 
                    className="flex items-start gap-3 p-2 bg-white border border-gray-100 rounded-md"
                  >
                    <div className="flex-shrink-0">
                      <Badge variant="outline" className="font-mono text-xs">
                        {concept.concept_id}
                      </Badge>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 leading-tight">
                        {concept.concept_name}
                      </p>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
                        <span className="text-xs text-gray-500">
                          <span className="font-medium">{concept.vocabulary_id}</span>: {concept.concept_code}
                        </span>
                        <span className="text-xs text-gray-400">•</span>
                        <span className="text-xs text-gray-500">{concept.domain_id}</span>
                        <span className="text-xs text-gray-400">•</span>
                        <Badge 
                          variant="outline" 
                          className={cn(
                            "text-[10px] h-4",
                            concept.match_type === "exact" ? "border-green-300 text-green-700 bg-green-50" : "border-gray-300"
                          )}
                        >
                          {concept.match_type}
                        </Badge>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {node.numericConstraintStructured && (
            <p className="text-xs text-gray-500 mt-1">
              {node.numericConstraintStructured.parameter} {node.numericConstraintStructured.operator} {node.numericConstraintStructured.value} {node.numericConstraintStructured.unit}
            </p>
          )}
        </div>
      </div>
    );
  }

  if (node.nodeType === "temporal" && node.operand) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Activity className="w-3 h-3" />
          <span className="font-medium">{node.temporalConstraint?.operator}</span>
          <span className="italic">{node.temporalConstraint?.anchor}</span>
        </div>
        <div className="ml-4 border-l-2 border-gray-300 pl-4">
          <ExpressionTreeNode node={node.operand} depth={depth + 1} expandAll={expandAll} atomicCriteriaMap={atomicCriteriaMap} />
        </div>
      </div>
    );
  }

  if (node.nodeType === "operator" && node.operands) {
    const operatorColor = node.operator === "AND" ? "bg-gray-800" : node.operator === "OR" ? "bg-gray-600" : "bg-gray-500";
    const operatorLabel = node.operator === "NOT" ? "NOT" : node.operator;

    return (
      <Collapsible open={effectiveExpanded} onOpenChange={handleToggle}>
        <CollapsibleTrigger className="w-full">
          <div className="flex items-center gap-2 py-1 hover:bg-gray-50 rounded-lg px-2 transition-colors">
            <Badge className={cn("text-xs text-white", operatorColor)}>
              {operatorLabel}
            </Badge>
            <span className="text-xs text-gray-500">
              {node.operands.length} condition{node.operands.length !== 1 ? 's' : ''}
            </span>
            {effectiveExpanded ? (
              <ChevronUp className="w-4 h-4 text-gray-400 ml-auto" />
            ) : (
              <ChevronDown className="w-4 h-4 text-gray-400 ml-auto" />
            )}
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-2 ml-4 border-l-2 border-gray-300 pl-4 space-y-2">
            {node.operands.map((operand, idx) => (
              <ExpressionTreeNode key={operand.nodeId || idx} node={operand} depth={depth + 1} expandAll={expandAll} atomicCriteriaMap={atomicCriteriaMap} />
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>
    );
  }

  return null;
}

function CriterionCard({ criterion }: { criterion: Criterion }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandAllTree, setExpandAllTree] = useState(false);
  const isInclusion = criterion.type === "Inclusion";
  
  const atomicCriteriaMap = useMemo(() => {
    const map: Record<string, AtomicCriterion> = {};
    (criterion.atomicCriteria || []).forEach((ac) => {
      map[ac.atomicId] = ac;
    });
    return map;
  }, [criterion.atomicCriteria]);

  return (
    <Card className="overflow-hidden">
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer hover:bg-gray-50 transition-colors">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0",
                  isInclusion ? "bg-gray-100 text-gray-700" : "bg-gray-200 text-gray-600"
                )}>
                  {isInclusion ? (
                    <Plus className="w-4 h-4" />
                  ) : (
                    <Minus className="w-4 h-4" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="outline" className="text-xs">
                      {criterion.criterionId}
                    </Badge>
                    <Badge className={cn(
                      "text-xs",
                      isInclusion ? "bg-gray-800 text-white" : "bg-gray-600 text-white"
                    )}>
                      {criterion.type}
                    </Badge>
                    <span className="text-xs text-gray-500">
                      {(criterion.atomicCriteria || []).length} atomic criteria
                    </span>
                  </div>
                  <FormattedCriteriaText text={criterion.originalText} />
                </div>
              </div>
              {isExpanded ? (
                <ChevronUp className="w-5 h-5 text-gray-400 flex-shrink-0" />
              ) : (
                <ChevronDown className="w-5 h-5 text-gray-400 flex-shrink-0" />
              )}
            </div>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="pt-0">
            <Separator className="mb-4" />
            
            {criterion.decompositionStrategy && (
              <div className="mb-4 p-3 bg-gray-50 rounded-lg">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">Decomposition Strategy</p>
                <p className="text-sm text-gray-700">{criterion.decompositionStrategy}</p>
              </div>
            )}

            <div className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Expression Tree</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setExpandAllTree(!expandAllTree)}
                  className="text-xs h-7"
                  data-testid="button-expand-all-tree"
                >
                  {expandAllTree ? (
                    <>
                      <ChevronUp className="w-3 h-3 mr-1" />
                      Collapse All
                    </>
                  ) : (
                    <>
                      <ChevronDown className="w-3 h-3 mr-1" />
                      Expand All
                    </>
                  )}
                </Button>
              </div>
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                {criterion.expression ? (
                  <ExpressionTreeNode node={criterion.expression} expandAll={expandAllTree} atomicCriteriaMap={atomicCriteriaMap} />
                ) : (
                  <p className="text-sm text-gray-500">No expression tree available</p>
                )}
              </div>
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}

function CriteriaDecompositionView({ data }: { data: CriteriaData }) {
  const inclusionCriteria = data.criteria.filter(c => c.type === "Inclusion");
  const exclusionCriteria = data.criteria.filter(c => c.type === "Exclusion");

  return (
    <div className="space-y-6">
      <div className="rounded-2xl bg-white border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-semibold tracking-tight text-gray-900">
              Criteria Decomposition
            </h3>
            <p className="text-gray-500 mt-1">
              Protocol {data.protocolId} - {data.criteria.length} criteria extracted
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-gray-800" />
              <span className="text-xs text-gray-600">{inclusionCriteria.length} Inclusion</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-gray-500" />
              <span className="text-xs text-gray-600">{exclusionCriteria.length} Exclusion</span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <h4 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <Plus className="w-5 h-5" />
            Inclusion Criteria
          </h4>
          <div className="space-y-3">
            {inclusionCriteria.map(criterion => (
              <CriterionCard key={criterion.criterionId} criterion={criterion} />
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <h4 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <Minus className="w-5 h-5" />
            Exclusion Criteria
          </h4>
          <div className="space-y-3">
            {exclusionCriteria.map(criterion => (
              <CriterionCard key={criterion.criterionId} criterion={criterion} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}


export default function EligibilityAnalysisPage() {
  const searchString = useSearch();
  const [, navigate] = useLocation();
  const [criteriaData, setCriteriaData] = useState<CriteriaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [pageNumber, setPageNumber] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1.0);
  const [pdfExpanded, setPdfExpanded] = useState(false);
  const [dataExpanded, setDataExpanded] = useState(false);

  const studyId = useMemo(() => {
    const params = new URLSearchParams(searchString);
    const id = params.get("studyId");
    return id || null;
  }, [searchString]);

  const pdfUrl = studyId ? getPdfUrl(studyId) : '';

  const togglePdfExpanded = () => {
    setPdfExpanded(!pdfExpanded);
    if (!pdfExpanded) setDataExpanded(false);
  };

  const toggleDataExpanded = () => {
    setDataExpanded(!dataExpanded);
    if (!dataExpanded) setPdfExpanded(false);
  };

  useEffect(() => {
    async function loadData() {
      if (!studyId) {
        setError("No studyId provided in URL. Please navigate from a protocol page.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        // Step 1: Get latest eligibility job for this protocol from database
        console.log("Fetching latest eligibility job for:", studyId);
        const jobInfo = await api.eligibility.getLatestJob(studyId);
        console.log("Job info received:", jobInfo);

        if (!jobInfo.has_job) {
          setError(`No eligibility extraction found for: ${studyId}. Please run eligibility extraction first.`);
          setLoading(false);
          return;
        }

        if (jobInfo.status !== "completed") {
          setError(`Eligibility extraction not complete (status: ${jobInfo.status}). Please wait for extraction to finish.`);
          setLoading(false);
          return;
        }

        // Step 2: Get full results from the completed job
        console.log("Fetching results for job:", jobInfo.job_id);
        const results = await api.eligibility.getResults(jobInfo.job_id!);
        console.log("Results received:", results);

        // Extract criteria from usdm_data
        const criteria = results.usdm_data?.criteria || [];

        if (criteria.length === 0) {
          setError(`Eligibility extraction completed but no criteria found for: ${studyId}`);
          setLoading(false);
          return;
        }

        setCriteriaData({
          protocolId: studyId,
          criteria: criteria,
        });
      } catch (err) {
        console.error("Failed to load eligibility data:", err);
        setError(err instanceof Error ? err.message : "Failed to load eligibility data from database");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [studyId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <span className="text-muted-foreground">Loading eligibility data...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-4 text-gray-600">
          <AlertCircle className="w-8 h-8" />
          <span>{error}</span>
          <Button variant="outline" onClick={() => window.location.reload()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <PanelGroup direction="horizontal" className="flex-1">
        <Panel defaultSize={50} minSize={30} className={cn(pdfExpanded && "hidden")}>
          <div className="h-full flex flex-col min-w-0">
            <div className="flex-1 overflow-auto min-w-0">
              <ScrollArea className="h-full">
                <div className="p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div />
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={toggleDataExpanded}
                      className="h-9 w-9"
                    >
                      {dataExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                    </Button>
                  </div>

                  {criteriaData && (
                    <CriteriaDecompositionView data={criteriaData} />
                  )}
                  
                  <div className="mt-8 pt-6 border-t border-gray-200">
                    <div className="rounded-2xl bg-white border border-gray-200 p-6 shadow-sm">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-lg font-semibold text-gray-900">
                            Ready for Criteria Validation?
                          </h3>
                          <p className="text-sm text-gray-500 mt-1">
                            Proceed to validate eligibility criteria groups and generate a patient feasibility funnel
                          </p>
                        </div>
                        <Button 
                          className="bg-gray-900 hover:bg-gray-800"
                          onClick={() => navigate(`/eligibility-analysis/qeb-validation?studyId=${studyId}`)}
                          data-testid="btn-proceed-qeb-validation"
                        >
                          Proceed to Criteria Validation
                          <ChevronRight className="w-4 h-4 ml-2" />
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              </ScrollArea>
            </div>
          </div>
        </Panel>

        <PanelResizeHandle className={cn("w-2 bg-gray-200 hover:bg-primary/20 transition-colors cursor-col-resize", (pdfExpanded || dataExpanded) && "hidden")} />

        <Panel defaultSize={50} minSize={30} className={cn("bg-white flex flex-col", dataExpanded && "hidden")}>
          <div className="h-12 bg-white border-b border-gray-200 flex items-center justify-between px-4 sticky top-0 z-20">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={pageNumber <= 1}
                  onClick={() => setPageNumber((p) => p - 1)}
                  className="h-8 w-8"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-sm font-medium tabular-nums w-16 text-center">
                  {pageNumber} / {numPages || "--"}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={pageNumber >= numPages}
                  onClick={() => setPageNumber((p) => p + 1)}
                  className="h-8 w-8"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
              <div className="h-4 w-px bg-gray-200 mx-1" />
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}
                  className="h-8 w-8"
                >
                  <ZoomOut className="h-4 w-4" />
                </Button>
                <span className="text-xs font-medium w-12 text-center">
                  {Math.round(scale * 100)}%
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setScale((s) => Math.min(2.0, s + 0.1))}
                  className="h-8 w-8"
                >
                  <ZoomIn className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => pdfUrl && window.open(pdfUrl, '_blank')}
              >
                <ExternalLink className="w-4 h-4 text-muted-foreground" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={togglePdfExpanded}
              >
                {pdfExpanded ? (
                  <Minimize2 className="w-4 h-4 text-muted-foreground" />
                ) : (
                  <Maximize2 className="w-4 h-4 text-muted-foreground" />
                )}
              </Button>
            </div>
          </div>

          <div className="flex-1 w-full h-full bg-gray-100 overflow-hidden">
            <ScrollArea className="h-full w-full">
              <div className="flex justify-center p-8 min-h-full">
                {pdfUrl ? (
                  <Document
                    file={pdfUrl}
                    onLoadSuccess={({ numPages }) => setNumPages(numPages)}
                    loading={
                      <div className="flex flex-col items-center gap-2 mt-20">
                        <Loader2 className="w-8 h-8 animate-spin text-primary" />
                        <span className="text-sm text-muted-foreground">Loading PDF Document...</span>
                      </div>
                    }
                    error={
                      <div className="flex flex-col items-center gap-2 mt-20 text-gray-600">
                        <span className="font-medium">Failed to load PDF</span>
                        <Button variant="outline" onClick={() => window.location.reload()}>
                          Retry
                        </Button>
                      </div>
                    }
                    className="shadow-xl"
                  >
                    <Page
                      pageNumber={pageNumber}
                      scale={scale}
                      className="bg-white shadow-sm"
                      renderTextLayer={false}
                      renderAnnotationLayer={false}
                    />
                  </Document>
                ) : (
                  <div className="flex flex-col items-center gap-2 mt-20 text-gray-500">
                    <AlertCircle className="w-8 h-8" />
                    <span className="text-sm">No protocol selected</span>
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        </Panel>
      </PanelGroup>
    </div>
  );
}
