import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { useDocument, useFieldUpdate, STUDY_ID } from "@/lib/queries";
import { StudyMetadataView } from "@/components/review/StudyMetadataView";
import { PopulationView } from "@/components/review/PopulationView";
import { ArmsDesignView } from "@/components/review/ArmsDesignView";
import { EndpointsView } from "@/components/review/EndpointsView";
import { SafetyView } from "@/components/review/SafetyView";
import { ConcomitantMedsView } from "@/components/review/ConcomitantMedsView";
import { BiospecimenView } from "@/components/review/BiospecimenView";
import { LabSpecsView } from "@/components/review/LabSpecsView";
import { InformedConsentView } from "@/components/review/InformedConsentView";
import { PROSpecsView } from "@/components/review/PROSpecsView";
import { DataManagementView } from "@/components/review/DataManagementView";
import { SiteLogisticsView } from "@/components/review/SiteLogisticsView";
import { QualityManagementView } from "@/components/review/QualityManagementView";
import { WithdrawalView } from "@/components/review/WithdrawalView";
import { ImagingView } from "@/components/review/ImagingView";
import { PKPDSamplingView } from "@/components/review/PKPDSamplingView";
import { SafetyDecisionPointsView } from "@/components/review/SafetyDecisionPointsView";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Maximize2, Minimize2, ExternalLink, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download } from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { Document, Page, pdfjs } from 'react-pdf';
import { useParams, useSearch } from "wouter";

// Set up the worker for react-pdf
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  `pdfjs-dist/build/pdf.worker.min.mjs`,
  import.meta.url
).toString();

export default function ReviewPage() {
  const params = useParams();
  const searchString = useSearch();
  const section = params.section || "study_metadata";
  
  const studyId = useMemo(() => {
    const searchParams = new URLSearchParams(searchString);
    return searchParams.get('studyId') || STUDY_ID;
  }, [searchString]);
  
  const { data: document, isLoading, error } = useDocument(studyId);
  const { toast } = useToast();

  // Field update hook for editable fields with audit trail
  const fieldUpdate = useFieldUpdate(
    document?.id ?? 0,
    studyId,
    document?.studyTitle ?? "",
    "anonymous" // TODO: Replace with actual user when auth is implemented
  );

  // Handler for field updates from view components
  const handleFieldUpdate = useCallback((path: string, value: any) => {
    console.log("[ReviewPage] handleFieldUpdate called:", { path, value, documentId: document?.id });

    if (!document?.id) {
      console.log("[ReviewPage] Document not loaded, showing error toast");
      toast({
        title: "Error",
        description: "Document not loaded",
        variant: "destructive",
        duration: 3000,
      });
      return;
    }

    console.log("[ReviewPage] Calling fieldUpdate.mutate");
    fieldUpdate.mutate({ path, value }, {
      onSuccess: () => {
        console.log("[ReviewPage] Mutation onSuccess - showing toast");
        toast({
          title: "Field Updated",
          description: "Change saved successfully",
          duration: 2000,
        });
      },
      onError: (error) => {
        console.log("[ReviewPage] Mutation onError:", error);
        toast({
          title: "Update Failed",
          description: error instanceof Error ? error.message : "Could not save changes",
          variant: "destructive",
          duration: 3000,
        });
      },
    });
  }, [document?.id, fieldUpdate, toast]);

  const [pdfExpanded, setPdfExpanded] = useState(false);
  const [dataExpanded, setDataExpanded] = useState(false);
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [scale, setScale] = useState<number>(1.0);

  const pdfProxyUrl = studyId ? `/api/protocols/${encodeURIComponent(studyId)}/pdf/annotated` : '';
  const [pdfData, setPdfData] = useState<{ data: Uint8Array } | null>(null);
  const [pdfLoadError, setPdfLoadError] = useState<string | null>(null);
  const pdfFetchedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!pdfProxyUrl || pdfFetchedRef.current === pdfProxyUrl) return;
    pdfFetchedRef.current = pdfProxyUrl;
    setPdfData(null);
    setPdfLoadError(null);
    fetch(pdfProxyUrl)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.arrayBuffer();
      })
      .then(buffer => {
        setPdfData({ data: new Uint8Array(buffer) });
      })
      .catch(err => {
        console.error('[ReviewPage] PDF fetch error:', err);
        setPdfLoadError(err.message);
      });
  }, [pdfProxyUrl]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading document...</p>
        </div>
      </div>
    );
  }

  if (error || !document) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-gray-700 font-semibold mb-2">Failed to load document</p>
          <p className="text-muted-foreground">{error?.message || "Document not found"}</p>
        </div>
      </div>
    );
  }

  const usdmData = document.usdmData as any;
  const { study, domainSections, agentDocumentation, extractionMetadata } = usdmData;

  // Map section IDs to agent IDs for looking up documentation
  const sectionToAgentId: Record<string, string> = {
    study_metadata: "study_metadata",
    study_population: "study_metadata",
    arms_design: "arms_design",
    endpoints: "endpoints_estimands_sap",
    safety: "adverse_events",
    safety_decision_points: "safety_decision_points",
    medications: "concomitant_medications",
    biospecimen: "biospecimen_handling",
    laboratory_specifications: "laboratory_specifications",
    consent: "informed_consent",
    pro_specifications: "pro_specifications",
    data_management: "data_management",
    site_operations_logistics: "site_operations_logistics",
    quality_management: "quality_management",
    withdrawal_procedures: "withdrawal_procedures",
    imaging_central_reading: "imaging_central_reading",
    pkpd_sampling: "pkpd_sampling",
    soa_analysis: "soa_analysis",
    soa_interpretation: "soa_interpretation"
  };

  const sectionToDomainKey: Record<string, string> = {
    study_metadata: "studyMetadata",
    study_population: "studyMetadata",
    arms_design: "studyDesign",
    endpoints: "endpointsEstimandsSAP",
    safety: "adverseEvents",
    safety_decision_points: "safetyDecisionPoints",
    medications: "concomitantMedications",
    biospecimen: "biospecimenHandling",
    laboratory_specifications: "laboratorySpecifications",
    consent: "informedConsent",
    pro_specifications: "proSpecifications",
    data_management: "dataManagement",
    site_operations_logistics: "siteOperationsLogistics",
    quality_management: "qualityManagement",
    withdrawal_procedures: "withdrawalProcedures",
    imaging_central_reading: "imagingCentralReading",
    pkpd_sampling: "pkpdSampling",
    soa_analysis: "soaAnalysis",
    soa_interpretation: "soaInterpretation"
  };

  const getAgentInfo = (sectionId: string) => {
    const agentId = sectionToAgentId[sectionId];
    const domainKey = sectionToDomainKey[sectionId];
    const qualityData = extractionMetadata?.qualitySummary?.[agentId];
    
    const agentDocFromDomain = domainSections?.[domainKey]?._agentDocumentation;
    const agentDocFromRoot = agentDocumentation?.agents?.[agentId];
    const agentDocData = agentDocFromDomain || agentDocFromRoot;
    
    if (agentDocData) {
      return {
        agentDoc: {
          agentId: agentDocData.agentId || agentId,
          displayName: agentDocData.displayName || agentId,
          purpose: agentDocData.purpose || "",
          scope: agentDocData.scope || "",
          instanceType: agentDocData.instanceType || agentId,
          wave: agentDocData.wave || 1,
          priority: agentDocData.priority || 1,
          keySectionsAnalyzed: agentDocData.keySectionsAnalyzed || [],
          keyInsights: agentDocData.keyInsights || []
        },
        qualityScore: qualityData?.overallScore
      };
    }
    
    return {
      agentDoc: {
        agentId: agentId,
        displayName: agentId,
        purpose: "",
        scope: "",
        instanceType: agentId,
        wave: 1,
        priority: 1,
        keySectionsAnalyzed: [],
        keyInsights: []
      },
      qualityScore: qualityData?.overallScore
    };
  };

  // Map section IDs to readable titles
  const sectionTitles: Record<string, string> = {
    study_metadata: "Study Metadata",
    study_population: "Population",
    arms_design: "Arms & Design",
    endpoints: "Endpoints",
    safety: "Safety & AEs",
    safety_decision_points: "Safety Decisions",
    medications: "Concomitant Meds",
    biospecimen: "Biospecimen",
    laboratory_specifications: "Lab Specs",
    consent: "Informed Consent",
    pro_specifications: "PRO Specs",
    data_management: "Data Management",
    site_operations_logistics: "Site Logistics",
    quality_management: "Quality Mgmt",
    withdrawal_procedures: "Withdrawal",
    imaging_central_reading: "Imaging",
    pkpd_sampling: "PK/PD Sampling",
    soa_analysis: "SOA Analysis",
    soa_interpretation: "SOA Interpretation"
  };

  const currentTitle = sectionTitles[section] || "Review";

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setNumPages(numPages);
  }

  const handleViewSource = (page: number) => {
    // Reset view to split screen if data is expanded
    if (dataExpanded) {
      setDataExpanded(false);
    }
    // Also ensure PDF isn't fully expanded (though it would show anyway, split view is better for context)
    if (pdfExpanded) {
      setPdfExpanded(false);
    }

    // Get page numbering info from extraction metadata for smart offset calculation
    const pageNumberingInfo = extractionMetadata?.pageNumberingInfo;
    const firstNumberedPage = pageNumberingInfo?.firstNumberedPage ?? 1;
    const pageOffset = pageNumberingInfo?.pageOffset ?? 0;

    // Smart logic: determine if this is a preliminary page or numbered page
    let physicalPage: number;
    if (page < firstNumberedPage) {
      // Page number is less than where numbering starts
      // This is likely a preliminary page (cover, TOC) - use as-is
      physicalPage = page;
    } else {
      // Page number is in the numbered section
      // Apply offset to convert printed page → physical page
      physicalPage = page + pageOffset;
    }

    // Ensure physical page is within valid bounds
    if (physicalPage < 1) {
      physicalPage = 1;
    }
    if (numPages && physicalPage > numPages) {
      physicalPage = numPages;
    }

    setPageNumber(physicalPage);
    toast({
      title: `Navigating to Page ${page}`,
      description: pageOffset > 0 ? `Physical page ${physicalPage} in PDF` : "Highlighting source text in the protocol document.",
      duration: 2000,
    });
  };

  const changePage = (offset: number) => {
    setPageNumber(prevPageNumber => prevPageNumber + offset);
  };

  const previousPage = () => changePage(-1);
  const nextPage = () => changePage(1);

  // Toggle Data Expanded
  const toggleDataExpanded = () => {
    setDataExpanded(!dataExpanded);
    if (!dataExpanded) setPdfExpanded(false); // Ensure only one is expanded
  };

  // Toggle PDF Expanded
  const togglePdfExpanded = () => {
    setPdfExpanded(!pdfExpanded);
    if (!pdfExpanded) setDataExpanded(false); // Ensure only one is expanded
  };

  // Export USDM JSON based on current section context
  const handleExportJSON = async () => {
    try {
      // Determine which JSON file to download based on section
      let jsonData: any;
      let filename: string;
      
      // Study Build sections (study_metadata through pkpd_sampling) use the full USDM 4.0 data
      const studyBuildSections = [
        "study_metadata", "study_population", "arms_design", "endpoints",
        "safety", "safety_decision_points", "medications", "biospecimen",
        "laboratory_specifications", "consent", "pro_specifications",
        "data_management", "site_operations_logistics", "quality_management",
        "withdrawal_procedures", "imaging_central_reading", "pkpd_sampling"
      ];
      
      if (studyBuildSections.includes(section)) {
        // Export the full USDM 4.0 document data from the loaded document
        jsonData = document?.usdmData;
        filename = `${studyId}_usdm_4.0_export.json`;
      } else if (section === "soa_analysis" || section === "soa_interpretation") {
        // Export SOA/Interpretation data from the document's domainSections
        // Extract SOA-related data from the full document
        const soaData = {
          studyId,
          studyName: (document?.usdmData as any)?.study?.name || studyId,
          exportType: section === "soa_analysis" ? "SOA Analysis" : "SOA Interpretation",
          exportTimestamp: new Date().toISOString(),
          domainSections: (document?.usdmData as any)?.domainSections || {},
          agentDocumentation: (document?.usdmData as any)?.agentDocumentation || {},
          extractionMetadata: (document?.usdmData as any)?.extractionMetadata || {}
        };
        jsonData = soaData;
        filename = section === "soa_analysis" 
          ? `${studyId}_soa_analysis_export.json`
          : `${studyId}_interpretation_export.json`;
      } else {
        jsonData = document?.usdmData;
        filename = `${studyId}_export.json`;
      }
      
      // Create and trigger download
      const blob = new Blob([JSON.stringify(jsonData, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = filename;
      window.document.body.appendChild(link);
      link.click();
      window.document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      toast({
        title: "Export Successful",
        description: `Downloaded ${filename}`,
        duration: 3000,
      });
    } catch (error) {
      toast({
        title: "Export Failed",
        description: "Could not export JSON data",
        variant: "destructive",
        duration: 3000,
      });
    }
  };

  // Get export button label based on section
  const getExportLabel = () => {
    const studyBuildSections = [
      "study_metadata", "study_population", "arms_design", "endpoints",
      "safety", "safety_decision_points", "medications", "biospecimen",
      "laboratory_specifications", "consent", "pro_specifications",
      "data_management", "site_operations_logistics", "quality_management",
      "withdrawal_procedures", "imaging_central_reading", "pkpd_sampling"
    ];
    
    if (studyBuildSections.includes(section)) {
      return "Export USDM 4.0";
    } else if (section === "soa_analysis") {
      return "Export SOA USDM";
    } else if (section === "soa_interpretation") {
      return "Export Interpretation";
    }
    return "Export JSON";
  };

  return (
    <div className="h-[calc(100vh-64px)] overflow-hidden bg-gray-50/50">
      <PanelGroup direction="horizontal" className="h-full">
        {/* Main Content - Review Area */}
        <Panel defaultSize={50} minSize={25} className={cn(pdfExpanded && "hidden")}>
          <div className="h-full flex flex-col">
            <ScrollArea className="flex-1">
              <div className="p-8 mx-auto pb-24 max-w-3xl">
                <div className="flex justify-end gap-2 mb-4">
                  <Button 
                    variant="outline" 
                    size="sm"
                    className="h-9 px-3 text-sm font-medium text-gray-700 hover:bg-gray-100 hover:text-gray-900 hover:border-gray-400 transition-colors"
                    onClick={handleExportJSON}
                    data-testid="export-usdm-json"
                  >
                    <Download className="h-4 w-4 mr-2" />
                    {getExportLabel()}
                  </Button>
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="h-9 w-9 text-muted-foreground hover:bg-gray-100"
                    onClick={toggleDataExpanded}
                  >
                    {dataExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                  </Button>
                </div>

            {section === "study_metadata" && (
              <StudyMetadataView data={study} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("study_metadata")} />
            )}

            {section === "study_population" && (
              <PopulationView data={study.studyPopulation} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("study_population")} />
            )}

            {section === "arms_design" && (
              <ArmsDesignView
                studyDesignInfo={study.studyDesignInfo}
                studyArms={domainSections?.studyDesign?.data?.studyArms || []}
                onViewSource={handleViewSource}
                onFieldUpdate={handleFieldUpdate}
                {...getAgentInfo("arms_design")}
              />
            )}

            {section === "endpoints" && (
              <EndpointsView data={domainSections?.endpointsEstimandsSAP?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("endpoints")} />
            )}

            {section === "safety" && (
              <SafetyView data={domainSections?.adverseEvents?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("safety")} />
            )}

            {section === "safety_decision_points" && (
              <SafetyDecisionPointsView data={domainSections?.safetyDecisionPoints?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("safety_decision_points")} />
            )}

            {section === "medications" && (
              <ConcomitantMedsView data={domainSections?.concomitantMedications?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("medications")} />
            )}

            {section === "biospecimen" && (
              <BiospecimenView data={domainSections?.biospecimenHandling?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("biospecimen")} />
            )}

            {section === "laboratory_specifications" && (
              <LabSpecsView data={domainSections?.laboratorySpecifications?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("laboratory_specifications")} />
            )}

            {section === "consent" && (
              <InformedConsentView data={domainSections?.informedConsent?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("consent")} />
            )}

            {section === "pro_specifications" && (
              <PROSpecsView data={domainSections?.proSpecifications?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("pro_specifications")} />
            )}

            {section === "data_management" && (
              <DataManagementView data={domainSections?.dataManagement?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("data_management")} />
            )}

            {section === "site_operations_logistics" && (
              <SiteLogisticsView data={domainSections?.siteOperationsLogistics?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("site_operations_logistics")} />
            )}

            {section === "quality_management" && domainSections?.qualityManagement?.data && (
              <QualityManagementView
                data={domainSections.qualityManagement.data}
                onViewSource={handleViewSource}
                onFieldUpdate={handleFieldUpdate}
                {...getAgentInfo("quality_management")}
              />
            )}

            {section === "withdrawal_procedures" && (
              <WithdrawalView data={domainSections?.withdrawalProcedures?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("withdrawal_procedures")} />
            )}

            {section === "imaging_central_reading" && (
              <ImagingView data={domainSections?.imagingCentralReading?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("imaging_central_reading")} />
            )}

            {section === "pkpd_sampling" && (
              <PKPDSamplingView data={domainSections?.pkpdSampling?.data} onViewSource={handleViewSource} onFieldUpdate={handleFieldUpdate} {...getAgentInfo("pkpd_sampling")} />
            )}
            
            <div className="mt-12 flex justify-center pb-8">
              <Button size="lg" className="rounded-full px-8 h-12 bg-primary hover:bg-gray-800 text-white shadow-lg shadow-gray-500/20 text-base font-semibold transition-all hover:scale-105 active:scale-95">
                Mark Section as Complete
              </Button>
            </div>
              </div>
            </ScrollArea>
          </div>
        </Panel>

        {/* Draggable Resize Handle */}
        <PanelResizeHandle className={cn(
          "w-2 bg-gray-200 hover:bg-gray-400 active:bg-gray-500 transition-colors cursor-col-resize relative group",
          (pdfExpanded || dataExpanded) && "hidden"
        )}>
          <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-1 bg-gray-400 group-hover:bg-gray-600 rounded-full opacity-50" />
        </PanelResizeHandle>

        {/* PDF Viewer Panel */}
        <Panel defaultSize={50} minSize={25} className={cn(dataExpanded && "hidden")}>
          <div className="h-full flex flex-col bg-white border-l border-border shadow-xl">
            {/* PDF Toolbar */}
        <div className="h-12 bg-white/90 backdrop-blur border-b border-border flex items-center justify-between px-4 sticky top-0 z-20 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
               <Button variant="ghost" size="icon" disabled={pageNumber <= 1} onClick={previousPage} className="h-8 w-8">
                 <ChevronLeft className="h-4 w-4" />
               </Button>
               <span className="text-sm font-medium tabular-nums w-16 text-center">
                 {pageNumber} / {numPages || '--'}
               </span>
               <Button variant="ghost" size="icon" disabled={pageNumber >= numPages} onClick={nextPage} className="h-8 w-8">
                 <ChevronRight className="h-4 w-4" />
               </Button>
            </div>
            <div className="h-4 w-px bg-gray-200 mx-1" />
             <div className="flex items-center gap-1">
               <Button variant="ghost" size="icon" onClick={() => setScale(s => Math.max(0.5, s - 0.1))} className="h-8 w-8">
                 <ZoomOut className="h-4 w-4" />
               </Button>
               <span className="text-xs font-medium w-12 text-center">
                 {Math.round(scale * 100)}%
               </span>
               <Button variant="ghost" size="icon" onClick={() => setScale(s => Math.min(2.0, s + 0.1))} className="h-8 w-8">
                 <ZoomIn className="h-4 w-4" />
               </Button>
            </div>
          </div>

          <div className="flex items-center gap-1">
             <Button 
              variant="ghost" 
              size="sm" 
              className="h-8 w-8 p-0 hover:bg-gray-100"
              onClick={() => window.open(pdfProxyUrl || '/protocol.pdf', '_blank')}
            >
              <ExternalLink className="w-4 h-4 text-muted-foreground" />
            </Button>
            <Button 
              variant="ghost" 
              size="sm" 
              className="h-8 w-8 p-0 hover:bg-gray-100"
              onClick={togglePdfExpanded}
            >
              {pdfExpanded ? <Minimize2 className="w-4 h-4 text-muted-foreground" /> : <Maximize2 className="w-4 h-4 text-muted-foreground" />}
            </Button>
          </div>
        </div>

        {/* PDF Content */}
        <div className="flex-1 w-full h-full bg-gray-100 overflow-hidden relative">
           <ScrollArea className="h-full w-full">
             <div className="flex justify-center p-8 min-h-full">
               {pdfLoadError ? (
                  <div className="flex flex-col items-center gap-2 mt-20 text-gray-600">
                    <span className="font-medium">Failed to load PDF</span>
                    <Button variant="outline" onClick={() => { pdfFetchedRef.current = null; setPdfLoadError(null); }}>Retry</Button>
                  </div>
                ) : pdfData ? (
                  <Document
                    file={pdfData}
                    onLoadSuccess={onDocumentLoadSuccess}
                    loading={
                      <div className="flex flex-col items-center gap-2 mt-20">
                        <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                        <span className="text-sm text-muted-foreground">Loading PDF Document...</span>
                      </div>
                    }
                    error={
                      <div className="flex flex-col items-center gap-2 mt-20 text-gray-600">
                        <span className="font-medium">Failed to load PDF</span>
                        <Button variant="outline" onClick={() => { pdfFetchedRef.current = null; setPdfLoadError(null); }}>Retry</Button>
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
                  <div className="flex flex-col items-center gap-2 mt-20">
                    <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                    <span className="text-sm text-muted-foreground">Loading PDF Document...</span>
                  </div>
                )}
             </div>
           </ScrollArea>
            </div>
          </div>
        </Panel>
      </PanelGroup>
    </div>
  );
}