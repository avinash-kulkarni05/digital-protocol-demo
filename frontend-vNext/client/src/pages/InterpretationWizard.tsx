import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Progress } from "@/components/ui/progress";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  ExternalLink,
  Maximize2,
  Minimize2,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Lightbulb,
  ChevronDown,
  ChevronUp,
  ThumbsUp,
  ThumbsDown,
  Flag,
  Eye,
  X,
  Beaker,
  Layers,
  GitBranch,
  Timer,
  FileText,
  Sparkles,
  ArrowRight,
  Circle,
  AlertTriangle,
  HelpCircle,
  Download,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Document, Page, pdfjs } from 'react-pdf';
import type { SOAInterpretation, SOAWizardStep, InterpretationItem, InterpretationComponent } from "@shared/schema";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  `pdfjs-dist/build/pdf.worker.min.mjs`,
  import.meta.url
).toString();

const INTERPRETATION_WIZARD_URL = "/data/NCT02264990_M14-359_interpretation_wizard.json";

const stepIconMap: Record<string, React.ReactNode> = {
  category: <Layers className="w-4 h-4" />,
  expand: <GitBranch className="w-4 h-4" />,
  fork: <GitBranch className="w-4 h-4" />,
  biotech: <Beaker className="w-4 h-4" />,
  rule: <FileText className="w-4 h-4" />,
  schedule: <Timer className="w-4 h-4" />,
};

interface InterpretationWizardProps {
  onClose: () => void;
  onComplete: () => void;
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

function StepStatusBadge({ status }: { status: string }) {
  switch (status) {
    case "COMPLETED":
      return <Badge className="bg-gray-800 text-white text-xs">Completed</Badge>;
    case "AUTO_APPROVED":
      return <Badge className="bg-gray-700 text-white text-xs">Auto-Approved</Badge>;
    case "PENDING":
      return <Badge variant="outline" className="text-gray-700 border-gray-400 bg-gray-100 text-xs">Pending Review</Badge>;
    case "IN_PROGRESS":
      return <Badge className="bg-primary text-white text-xs">In Progress</Badge>;
    default:
      return null;
  }
}

interface WizardStepperProps {
  steps: SOAWizardStep[];
  currentStepIndex: number;
  onStepClick: (index: number) => void;
}

function WizardStepper({ steps, currentStepIndex, onStepClick }: WizardStepperProps) {
  return (
    <div className="flex flex-col gap-1 py-4">
      {steps.map((step, index) => {
        const isActive = index === currentStepIndex;
        const isCompleted = step.status === "COMPLETED" || step.status === "AUTO_APPROVED";
        const hasPending = step.progress.total > 0 && step.progress.reviewed < step.progress.total;
        const Icon = stepIconMap[step.icon] || <Circle className="w-4 h-4" />;
        
        return (
          <button
            key={step.stepId}
            onClick={() => onStepClick(index)}
            className={cn(
              "flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-all w-full",
              isActive && "bg-primary/10 border-l-4 border-primary",
              !isActive && isCompleted && "hover:bg-gray-100",
              !isActive && !isCompleted && "hover:bg-gray-50"
            )}
            data-testid={`wizard-step-${step.stepId}`}
          >
            <div
              className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                isActive && "bg-primary text-white",
                !isActive && isCompleted && "bg-gray-100 text-gray-800",
                !isActive && !isCompleted && hasPending && "bg-gray-100 text-gray-700",
                !isActive && !isCompleted && !hasPending && "bg-gray-100 text-gray-500"
              )}
            >
              {isCompleted ? <Check className="w-4 h-4" /> : Icon}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={cn(
                  "font-medium text-sm truncate",
                  isActive && "text-primary",
                  !isActive && isCompleted && "text-gray-900",
                  !isActive && !isCompleted && "text-gray-700"
                )}>
                  {step.title}
                </span>
                {step.isCritical && (
                  <AlertTriangle className="w-3 h-3 text-gray-600 shrink-0" />
                )}
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                {step.progress.total > 0 ? (
                  <span className="text-xs text-muted-foreground">
                    {step.progress.reviewed}/{step.progress.total} reviewed
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">
                    {(step.autoApprovedItems?.length || 0)} auto-approved
                  </span>
                )}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

interface ItemCardProps {
  item: InterpretationItem;
  isAutoApproved: boolean;
  onApprove: () => void;
  onReject: () => void;
  onFlag: () => void;
  onViewSource: (pageNumber: number) => void;
  stepId: string;
}

function ItemCard({ item, isAutoApproved, onApprove, onReject, onFlag, onViewSource, stepId }: ItemCardProps) {
  const [expanded, setExpanded] = useState(!isAutoApproved);
  
  const getPageNumber = (): number | null => {
    if (item.provenance?.pageNumber) return item.provenance.pageNumber;
    if (item.proposal?.provenance?.pageNumber) return item.proposal.provenance.pageNumber;
    if (item.components?.[0]?.provenance?.pageNumber) return item.components[0].provenance.pageNumber;
    const proposalComps = item.proposal?.components;
    if (proposalComps?.[0]?.provenance?.pageNumber) return proposalComps[0].provenance.pageNumber;
    return null;
  };

  const getDisplayName = (): string => {
    if (item.activityName) return item.activityName;
    const components = item.components || item.proposal?.components || [];
    if (components.length > 0) {
      const firstSnippet = components[0]?.provenance?.textSnippet;
      if (firstSnippet) {
        const lines = firstSnippet.split('\n');
        if (lines.length > 1) {
          return `${lines[0]} (${components.length} components)`;
        }
      }
      return `${components[0]?.name || 'Activity'} + ${components.length - 1} more`;
    }
    if (item.proposal?.expandedActivities?.length) {
      const first = item.proposal.expandedActivities[0];
      return first._alternativeResolution?.originalActivityName || first.name || 'Activity';
    }
    if (item.reasoning) return item.reasoning;
    return item.type?.replace(/_/g, ' ') || item.itemId || "Interpretation Item";
  };

  const getSubtitle = (): string => {
    if (item.proposal?.resolution) {
      return item.proposal.resolution.replace(/_/g, ' ');
    }
    const components = item.components || item.proposal?.components || [];
    if (components.length > 0 && components[0]?.cdashDomain) {
      return `${components[0].cdashDomain} Domain`;
    }
    return stepId.replace(/_/g, ' ');
  };
  
  const pageNumber = getPageNumber();
  const confidence = item.confidence || 0;
  const status = item.status || (isAutoApproved ? "AUTO_APPROVED" : "PENDING");
  const displayName = getDisplayName();
  const subtitle = getSubtitle();

  return (
    <Card className={cn(
      "overflow-hidden transition-all",
      status === "APPROVED" && "border-gray-300 bg-gray-50/30",
      status === "REJECTED" && "border-gray-300 bg-gray-50/30",
      status === "FLAGGED" && "border-gray-300 bg-gray-50/30",
      item.isCritical && status === "PENDING" && "border-gray-400 ring-1 ring-gray-300"
    )}>
      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <CollapsibleTrigger asChild>
          <div className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50/50">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <div className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                status === "APPROVED" || status === "AUTO_APPROVED" ? "bg-gray-100 text-gray-800" :
                status === "REJECTED" ? "bg-gray-100 text-gray-600" :
                status === "FLAGGED" ? "bg-gray-100 text-gray-700" :
                "bg-gray-100 text-gray-600"
              )}>
                {status === "APPROVED" || status === "AUTO_APPROVED" ? <CheckCircle2 className="w-4 h-4" /> :
                 status === "REJECTED" ? <X className="w-4 h-4" /> :
                 status === "FLAGGED" ? <Flag className="w-4 h-4" /> :
                 <HelpCircle className="w-4 h-4" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm truncate">
                    {displayName}
                  </span>
                  {item.isCritical && (
                    <Badge variant="destructive" className="text-xs">Critical</Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground truncate mt-0.5">
                  {subtitle}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <ConfidenceBadge confidence={confidence} />
                {isAutoApproved && (
                  <Badge variant="secondary" className="text-xs">Auto</Badge>
                )}
                {expanded ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
              </div>
            </div>
          </div>
        </CollapsibleTrigger>
        
        <CollapsibleContent>
          <div className="px-4 pb-4 space-y-4">
            <Separator />
            
            {item.reasoning && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <div className="flex items-start gap-2">
                  <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-xs font-medium text-gray-900 mb-1">AI Reasoning</p>
                    <p className="text-sm text-gray-800">{item.reasoning}</p>
                  </div>
                </div>
              </div>
            )}

            {item.context?.originalText && (
              <div className="bg-gray-50 rounded-lg p-3 border">
                <p className="text-xs font-medium text-gray-500 mb-1">Original Text</p>
                <p className="text-sm text-gray-700 italic">"{item.context.originalText}"</p>
              </div>
            )}

            {item.proposal?.resolution && stepId === "ALTERNATIVES" && (
              <div className="space-y-3">
                <p className="text-sm font-medium">Proposed Resolution</p>
                <RadioGroup defaultValue={item.proposal.resolution} className="space-y-2">
                  {item.alternatives?.map((alt, idx) => (
                    <div key={idx} className="flex items-center space-x-2 p-2 rounded border hover:bg-gray-50">
                      <RadioGroupItem value={alt.resolution} id={`alt-${idx}`} />
                      <Label htmlFor={`alt-${idx}`} className="flex-1 cursor-pointer">
                        <span className="font-medium text-sm">{alt.resolution.replace(/_/g, ' ')}</span>
                        <span className="text-xs text-muted-foreground ml-2">- {alt.reasoning}</span>
                      </Label>
                    </div>
                  ))}
                </RadioGroup>
                
                {item.proposal.expandedActivities && item.proposal.expandedActivities.length > 0 && (
                  <div className="mt-3">
                    <p className="text-xs font-medium text-gray-500 mb-2">Expanded Activities</p>
                    <div className="space-y-2">
                      {item.proposal.expandedActivities.map((act, idx) => (
                        <div key={idx} className="flex items-center gap-2 p-2 bg-gray-50 rounded border text-sm">
                          <ArrowRight className="w-3 h-3 text-gray-400" />
                          <span>{act.name}</span>
                          {act._alternativeResolution?.rationale && (
                            <span className="text-xs text-muted-foreground ml-auto">
                              {act._alternativeResolution.alternativeType}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {(() => {
              const components = item.components || item.proposal?.components || [];
              if (components.length === 0) return null;
              return (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Components ({components.length})</p>
                  <div className="grid gap-2 max-h-60 overflow-y-auto">
                    {components.slice(0, 10).map((comp, idx) => (
                      <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded border text-sm">
                        <div className="flex items-center gap-2">
                          <span>{comp.name}</span>
                          {comp.cdashDomain && (
                            <Badge variant="outline" className="text-xs">{comp.cdashDomain}</Badge>
                          )}
                        </div>
                        {comp.confidence && <ConfidenceBadge confidence={comp.confidence} />}
                      </div>
                    ))}
                    {components.length > 10 && (
                      <p className="text-xs text-muted-foreground text-center py-2">
                        +{components.length - 10} more components
                      </p>
                    )}
                  </div>
                </div>
              );
            })()}

            {(item.provenance?.textSnippet || item.proposal?.provenance?.textSnippet) && (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <p className="text-xs font-medium text-gray-900 mb-1">Source Evidence</p>
                <p className="text-sm text-gray-700 italic">
                  "{item.provenance?.textSnippet || item.proposal?.provenance?.textSnippet}"
                </p>
                {(item.provenance?.rationale || item.proposal?.provenance?.rationale) && (
                  <p className="text-xs text-gray-600 mt-2">
                    {item.provenance?.rationale || item.proposal?.provenance?.rationale}
                  </p>
                )}
              </div>
            )}

            <div className="flex items-center justify-between pt-2">
              <div className="flex items-center gap-2">
                {pageNumber && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onViewSource(pageNumber)}
                    className="text-xs"
                    data-testid={`btn-view-source-${item.itemId}`}
                  >
                    <Eye className="w-3 h-3 mr-1" />
                    View Page {pageNumber}
                  </Button>
                )}
              </div>
              
              {status === "PENDING" && (
                <div className="flex items-center gap-2">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={onFlag}
                          className="text-gray-700 hover:bg-gray-100 hover:border-gray-400"
                          data-testid={`btn-flag-${item.itemId}`}
                        >
                          <Flag className="w-4 h-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Flag for later review</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                  
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={onReject}
                    className="text-gray-600 hover:bg-gray-100 hover:border-gray-400"
                    data-testid={`btn-reject-${item.itemId}`}
                  >
                    <ThumbsDown className="w-4 h-4 mr-1" />
                    Reject
                  </Button>
                  
                  <Button
                    size="sm"
                    onClick={onApprove}
                    className="bg-gray-800 hover:bg-gray-900"
                    data-testid={`btn-approve-${item.itemId}`}
                  >
                    <ThumbsUp className="w-4 h-4 mr-1" />
                    Approve
                  </Button>
                </div>
              )}
              
              {(status === "APPROVED" || status === "AUTO_APPROVED") && (
                <Badge className="bg-gray-100 text-gray-900 border-gray-300">
                  <CheckCircle2 className="w-3 h-3 mr-1" />
                  {status === "AUTO_APPROVED" ? "Auto-Approved" : "Approved"}
                </Badge>
              )}
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}

interface StepContentProps {
  step: SOAWizardStep;
  interpretation: SOAInterpretation;
  onUpdateItemStatus: (itemIndex: number, isAutoApproved: boolean, status: InterpretationItem["status"]) => void;
  onViewSource: (pageNumber: number) => void;
}

function StepContent({ step, interpretation, onUpdateItemStatus, onViewSource }: StepContentProps) {
  const autoApprovedItems = step.autoApprovedItems || [];
  const reviewItems = step.reviewItems || [];
  const totalItems = autoApprovedItems.length + reviewItems.length;
  const [showAutoApproved, setShowAutoApproved] = useState(true);
  
  if (totalItems === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <CheckCircle2 className="w-12 h-12 text-gray-800 mb-4" />
        <h3 className="text-lg font-medium text-gray-900">No Items to Review</h3>
        <p className="text-sm text-muted-foreground mt-2">
          This step has no items requiring review.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">{step.title}</h2>
          <p className="text-sm text-muted-foreground mt-1">{step.description}</p>
        </div>
        <div className="flex items-center gap-2">
          {step.isCritical && (
            <Badge variant="destructive" className="gap-1">
              <AlertTriangle className="w-3 h-3" />
              Critical Step
            </Badge>
          )}
          <StepStatusBadge status={step.status} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4">
          <p className="text-xs text-muted-foreground">Total Items</p>
          <p className="text-2xl font-bold">{totalItems}</p>
        </Card>
        <Card className="p-4 border-gray-300 bg-gray-50">
          <p className="text-xs text-gray-800">Auto-Approved</p>
          <p className="text-2xl font-bold text-gray-800">{autoApprovedItems.length}</p>
        </Card>
        <Card className="p-4 border-gray-300 bg-gray-100">
          <p className="text-xs text-gray-700">Pending Review</p>
          <p className="text-2xl font-bold text-gray-700">{reviewItems.length}</p>
        </Card>
      </div>

      {reviewItems.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Pending Review ({reviewItems.length})</h3>
            {interpretation.wizardConfig.allowBatchOperations && reviewItems.length > 1 && (
              <Button variant="outline" size="sm" className="text-xs">
                <CheckCircle2 className="w-3 h-3 mr-1" />
                Approve All
              </Button>
            )}
          </div>
          <div className="space-y-3">
            {reviewItems.map((item, idx) => (
              <ItemCard
                key={item.itemId || idx}
                item={item}
                isAutoApproved={false}
                stepId={step.stepId}
                onApprove={() => onUpdateItemStatus(idx, false, "APPROVED")}
                onReject={() => onUpdateItemStatus(idx, false, "REJECTED")}
                onFlag={() => onUpdateItemStatus(idx, false, "FLAGGED")}
                onViewSource={onViewSource}
              />
            ))}
          </div>
        </div>
      )}

      {autoApprovedItems.length > 0 && (
        <Collapsible open={showAutoApproved} onOpenChange={setShowAutoApproved}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between h-12 border border-dashed">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-gray-800" />
                <span>Auto-Approved Items ({autoApprovedItems.length})</span>
                <Badge variant="secondary" className="text-xs">High Confidence</Badge>
              </div>
              {showAutoApproved ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-3 space-y-3">
            {autoApprovedItems.map((item, idx) => (
              <ItemCard
                key={item.itemId || `auto-${idx}`}
                item={{ ...item, status: "AUTO_APPROVED" }}
                isAutoApproved={true}
                stepId={step.stepId}
                onApprove={() => {}}
                onReject={() => onUpdateItemStatus(idx, true, "REJECTED")}
                onFlag={() => onUpdateItemStatus(idx, true, "FLAGGED")}
                onViewSource={onViewSource}
              />
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}

export default function InterpretationWizard({ onClose, onComplete }: InterpretationWizardProps) {
  const [interpretation, setInterpretation] = useState<SOAInterpretation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1.0);
  const [pdfExpanded, setPdfExpanded] = useState(false);
  const { toast } = useToast();

  const handleExportInterpretation = async () => {
    try {
      const response = await fetch(INTERPRETATION_WIZARD_URL);
      if (!response.ok) throw new Error("Failed to fetch interpretation data");
      const data = await response.json();
      
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = `interpretation_wizard_export.json`;
      window.document.body.appendChild(link);
      link.click();
      window.document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      toast({
        title: "Export Successful",
        description: "Downloaded interpretation_wizard_export.json",
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

  useEffect(() => {
    async function loadData() {
      try {
        const response = await fetch(INTERPRETATION_WIZARD_URL);
        if (!response.ok) throw new Error("Failed to load interpretation data");
        const data = await response.json();
        setInterpretation(data);
        const firstPendingIndex = data.steps.findIndex((s: SOAWizardStep) => 
          s.status === "PENDING" || (s.reviewItems && s.reviewItems.length > 0)
        );
        if (firstPendingIndex >= 0) {
          setCurrentStepIndex(firstPendingIndex);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const handleUpdateItemStatus = useCallback((itemIndex: number, isAutoApproved: boolean, newStatus: InterpretationItem["status"]) => {
    setInterpretation(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        steps: prev.steps.map((step, idx) => {
          if (idx !== currentStepIndex) return step;
          
          const updatedReviewItems = isAutoApproved 
            ? step.reviewItems 
            : step.reviewItems?.map((item, i) =>
                i === itemIndex ? { ...item, status: newStatus } : item
              );
          const updatedAutoApprovedItems = isAutoApproved
            ? step.autoApprovedItems?.map((item, i) =>
                i === itemIndex ? { ...item, status: newStatus } : item
              )
            : step.autoApprovedItems;
          
          const reviewedCount = (updatedReviewItems || []).filter(
            item => item.status && item.status !== "PENDING"
          ).length;
          const totalPending = (updatedReviewItems || []).length;
          const allReviewed = reviewedCount === totalPending;
          
          return {
            ...step,
            reviewItems: updatedReviewItems,
            autoApprovedItems: updatedAutoApprovedItems,
            progress: {
              ...step.progress,
              reviewed: reviewedCount,
              total: totalPending,
            },
            status: allReviewed && totalPending > 0 ? "COMPLETED" : step.status,
          };
        }),
      };
    });
  }, [currentStepIndex]);

  const handleNextStep = () => {
    if (!interpretation) return;
    if (currentStepIndex < interpretation.steps.length - 1) {
      setCurrentStepIndex(currentStepIndex + 1);
    }
  };

  const handlePrevStep = () => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex(currentStepIndex - 1);
    }
  };

  const handleViewSource = (page: number) => {
    setPageNumber(page);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin mx-auto text-primary mb-4" />
          <p className="text-muted-foreground">Loading interpretation wizard...</p>
        </div>
      </div>
    );
  }

  if (error || !interpretation) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50">
        <div className="text-center">
          <AlertCircle className="w-8 h-8 text-gray-600 mx-auto mb-4" />
          <p className="text-gray-700 font-semibold mb-2">Failed to load wizard</p>
          <p className="text-muted-foreground">{error}</p>
          <Button variant="outline" className="mt-4" onClick={onClose}>
            Go Back
          </Button>
        </div>
      </div>
    );
  }

  const currentStep = interpretation.steps[currentStepIndex];
  const progressPercent = ((currentStepIndex + 1) / interpretation.steps.length) * 100;
  const allPendingReviewed = interpretation.steps.every(step => 
    !step.reviewItems || step.reviewItems.length === 0 || step.reviewItems.every(item => 
      item.status && item.status !== "PENDING"
    )
  );

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={onClose} data-testid="btn-close-wizard">
              <ChevronLeft className="w-4 h-4 mr-1" />
              Back to Extraction
            </Button>
            <Separator orientation="vertical" className="h-6" />
            <div>
              <h1 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <Lightbulb className="w-5 h-5 text-gray-700" />
                Interpretation Review Wizard
              </h1>
              <p className="text-xs text-muted-foreground mt-0.5">
                {interpretation.protocolId}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm">
              <Badge variant="secondary">{interpretation.summary.totalItems} items</Badge>
              <Badge className="bg-gray-100 text-gray-800 border-gray-300">
                {interpretation.summary.autoApproved} auto-approved
              </Badge>
              <Badge className="bg-gray-100 text-gray-700 border-gray-300">
                {interpretation.summary.pendingReview} pending
              </Badge>
            </div>
            <Button 
              variant="outline" 
              size="sm"
              className="h-9 px-3 text-sm font-medium text-gray-700 hover:bg-gray-100 hover:text-gray-900 hover:border-gray-400 transition-colors"
              onClick={handleExportInterpretation}
              data-testid="export-interpretation-json"
            >
              <Download className="h-4 w-4 mr-2" />
              Export Interpretation
            </Button>
          </div>
        </div>
        <div className="mt-4">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
            <span>Step {currentStepIndex + 1} of {interpretation.steps.length}</span>
            <span>{Math.round(progressPercent)}% complete</span>
          </div>
          <Progress value={progressPercent} className="h-2" />
        </div>
      </div>

      <PanelGroup direction="horizontal" className="flex-1">
        <Panel defaultSize={20} minSize={15} maxSize={30} className="bg-white border-r">
          <ScrollArea className="h-full">
            <WizardStepper
              steps={interpretation.steps}
              currentStepIndex={currentStepIndex}
              onStepClick={setCurrentStepIndex}
            />
          </ScrollArea>
        </Panel>

        <Panel defaultSize={45} minSize={30} className={cn(pdfExpanded && "hidden")}>
          <ScrollArea className="h-full">
            <div className="p-6">
              <StepContent
                step={currentStep}
                interpretation={interpretation}
                onUpdateItemStatus={handleUpdateItemStatus}
                onViewSource={handleViewSource}
              />

              <div className="flex items-center justify-between mt-8 pt-6 border-t">
                <Button
                  variant="outline"
                  onClick={handlePrevStep}
                  disabled={currentStepIndex === 0}
                  data-testid="btn-wizard-prev"
                >
                  <ChevronLeft className="w-4 h-4 mr-2" />
                  Previous Step
                </Button>
                
                {currentStepIndex < interpretation.steps.length - 1 ? (
                  <Button onClick={handleNextStep} data-testid="btn-wizard-next">
                    Next Step
                    <ChevronRight className="w-4 h-4 ml-2" />
                  </Button>
                ) : (
                  <Button
                    className="bg-gray-800 hover:bg-gray-900"
                    onClick={onComplete}
                    disabled={!allPendingReviewed}
                    data-testid="btn-wizard-complete"
                  >
                    <Check className="w-4 h-4 mr-2" />
                    Complete & Generate USDM
                  </Button>
                )}
              </div>
            </div>
          </ScrollArea>
        </Panel>

        <PanelResizeHandle className={cn("w-2 bg-gray-200 hover:bg-primary/20 transition-colors cursor-col-resize", pdfExpanded && "hidden")} />

        <Panel defaultSize={35} minSize={25} className="bg-white flex flex-col">
          <div className="h-12 bg-white border-b border-gray-200 flex items-center justify-between px-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={pageNumber <= 1}
                  onClick={() => setPageNumber(p => p - 1)}
                  className="h-8 w-8"
                  data-testid="btn-pdf-prev"
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
                  onClick={() => setPageNumber(p => p + 1)}
                  className="h-8 w-8"
                  data-testid="btn-pdf-next"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
              <Separator orientation="vertical" className="h-4" />
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setScale(s => Math.max(0.5, s - 0.1))}
                  className="h-8 w-8"
                  data-testid="btn-zoom-out"
                >
                  <ZoomOut className="h-4 w-4" />
                </Button>
                <span className="text-xs font-medium w-12 text-center">
                  {Math.round(scale * 100)}%
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setScale(s => Math.min(2.0, s + 0.1))}
                  className="h-8 w-8"
                  data-testid="btn-zoom-in"
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
                onClick={() => setPdfExpanded(!pdfExpanded)}
                data-testid="btn-pdf-expand"
              >
                {pdfExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
              </Button>
            </div>
          </div>
          <div className="flex-1 bg-gray-100 overflow-auto">
            <div className="flex justify-center p-4">
              <Document
                file="/abbvie_m14359_protocol.pdf"
                onLoadSuccess={({ numPages }) => setNumPages(numPages)}
                loading={
                  <div className="flex flex-col items-center gap-2 mt-20">
                    <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    <p className="text-sm text-muted-foreground">Loading PDF...</p>
                  </div>
                }
              >
                <Page
                  pageNumber={pageNumber}
                  scale={scale}
                  renderTextLayer={false}
                  renderAnnotationLayer={false}
                />
              </Document>
            </div>
          </div>
        </Panel>
      </PanelGroup>
    </div>
  );
}
