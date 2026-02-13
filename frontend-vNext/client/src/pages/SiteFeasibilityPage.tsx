import { useState, useMemo, useEffect } from "react";
import { useLocation } from "wouter";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ArrowLeft, MapPin, Users, ChevronDown, ChevronRight, Filter, Plus, Check, X, AlertTriangle, CheckCircle2, XCircle, Building2, Info, Database, FileText } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { Site, getUSSites, calculateEligiblePatients, sortSitesByEligibility, healthcareSystems, CriteriaContext } from "@/lib/mockSiteData";
import type { QebValidationData, FunnelStage as QebFunnelStage, QueryableBlock, AtomicCriterion } from "@/lib/qebValidation";
import usdmData from "@/lib/usdm-data.json";

interface Criterion {
  id: string;
  name: string;
  type: "inclusion" | "exclusion";
  queryableStatus: "fully_queryable" | "partially_queryable" | "requires_manual" | "screening" | "not_applicable";
  protocolText: string;
  clinicalDescription: string;
  omopConcepts: Array<{conceptId: number; conceptName: string; domain: string; vocabularyId: string; conceptCode?: string | null}>;
  atomicIds: string[];
}

interface FunnelStageWithCriteria {
  id: string;
  name: string;
  description: string;
  order: number;
  criteria: Criterion[];
}

function USMapVisualization({ sites, activeStageIds, criteriaContext }: { sites: Site[]; activeStageIds: string[]; criteriaContext: CriteriaContext[] }) {
  const maxEligible = useMemo(() => {
    return Math.max(...sites.map(s => calculateEligiblePatients(s, activeStageIds, criteriaContext)), 1);
  }, [sites, activeStageIds, criteriaContext]);

  const getMarkerRadius = (site: Site): number => {
    const eligible = calculateEligiblePatients(site, activeStageIds, criteriaContext);
    const ratio = eligible / maxEligible;
    return 6 + ratio * 14;
  };

  const usCenter: [number, number] = [39.5, -98.35];

  return (
    <div className="relative w-full h-full rounded-xl overflow-hidden border border-gray-200">
      <MapContainer
        center={usCenter}
        zoom={4}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%" }}
        className="rounded-xl"
      >
        <TileLayer
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        />
        {sites.map((site) => {
          const eligible = calculateEligiblePatients(site, activeStageIds, criteriaContext);
          const radius = getMarkerRadius(site);

          return (
            <CircleMarker
              key={site.siteId}
              center={[site.lat, site.lng]}
              radius={radius}
              pathOptions={{
                fillColor: "#1f2937",
                fillOpacity: 0.85,
                color: "#fff",
                weight: 2,
              }}
            >
              <Popup>
                <div className="min-w-[160px]">
                  <p className="font-semibold text-gray-900 text-sm leading-tight">{site.siteName}</p>
                  <p className="text-xs text-gray-500 mt-1">{site.city}, {site.stateCode}</p>
                  <div className="mt-2 pt-2 border-t border-gray-100 flex items-center justify-between">
                    <span className="text-xs text-gray-500">Eligible</span>
                    <span className="font-bold text-gray-900">{eligible.toLocaleString()}</span>
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>

      <div className="absolute top-3 right-3 z-[1000] bg-white/90 backdrop-blur-sm rounded-lg px-3 py-1.5 border border-gray-200 shadow-sm">
        <span className="text-xs font-medium text-gray-700">{sites.length} sites</span>
      </div>
    </div>
  );
}

export default function SiteFeasibilityPage() {
  const [, navigate] = useLocation();
  const [qebData, setQebData] = useState<QebValidationData | null>(null);
  const [expandedStages, setExpandedStages] = useState<Set<string>>(new Set());
  const [activeStages, setActiveStages] = useState<Set<string>>(new Set());
  const [selectedCriteria, setSelectedCriteria] = useState<Set<string>>(new Set());
  const [selectedSystem] = useState<string>("sys_ascension");
  const [logisticsModalSite, setLogisticsModalSite] = useState<Site | null>(null);
  const [qebDetailModal, setQebDetailModal] = useState<Criterion | null>(null);
  const [selectedAtomics, setSelectedAtomics] = useState<Set<string>>(new Set());

  const siteOperationsLogistics = (usdmData as any)?.domainSections?.siteOperationsLogistics?.data;
  
  const atomicLookup = useMemo(() => {
    if (!qebData) return new Map<string, AtomicCriterion>();
    const lookup = new Map<string, AtomicCriterion>();
    qebData.atomicCriteria.forEach(atomic => lookup.set(atomic.atomicId, atomic));
    return lookup;
  }, [qebData]);

  useEffect(() => {
    if (qebData) {
      const queryableAtomics = new Set<string>();
      qebData.atomicCriteria.forEach(atomic => {
        if (atomic.queryableStatus === "fully_queryable" || atomic.queryableStatus === "partially_queryable") {
          queryableAtomics.add(atomic.atomicId);
        }
      });
      setSelectedAtomics(queryableAtomics);
    }
  }, [qebData]);

  const toggleAtomic = (atomicId: string) => {
    setSelectedAtomics(prev => {
      const next = new Set(prev);
      if (next.has(atomicId)) {
        next.delete(atomicId);
      } else {
        next.add(atomicId);
      }
      return next;
    });
  };

  useEffect(() => {
    fetch('/data/NCT02264990_qeb_output.json')
      .then(res => res.json())
      .then((data: QebValidationData) => setQebData(data))
      .catch(err => console.error('Failed to load QEB data:', err));
  }, []);

  const stagesWithCriteria = useMemo((): FunnelStageWithCriteria[] => {
    if (!qebData) return [];
    
    const qebLookup = new Map<string, QueryableBlock>();
    qebData.queryableBlocks.forEach(qeb => qebLookup.set(qeb.qebId, qeb));

    return qebData.funnelStages.map(stage => {
      const criteria: Criterion[] = stage.qebIds
        .map(qebId => {
          const qeb = qebLookup.get(qebId);
          if (!qeb) return null;
          return {
            id: qeb.qebId,
            name: `${qeb.qebId}: ${qeb.clinicalName}`,
            type: qeb.criterionType,
            queryableStatus: qeb.queryableStatus as Criterion["queryableStatus"],
            protocolText: qeb.protocolText,
            clinicalDescription: qeb.clinicalDescription,
            omopConcepts: (qeb.omopConcepts || []) as Criterion["omopConcepts"],
            atomicIds: qeb.atomicIds || []
          } as Criterion;
        })
        .filter((c): c is Criterion => c !== null);

      return {
        id: stage.stageId,
        name: stage.stageName,
        description: stage.stageDescription,
        order: stage.stageOrder,
        criteria
      };
    });
  }, [qebData]);

  const ascensionSystem = healthcareSystems.find(s => s.systemId === "sys_ascension");
  
  const sites = useMemo(() => {
    const usSites = getUSSites();
    return usSites.filter(s => s.systemId === selectedSystem);
  }, [selectedSystem]);

  const activeStageIds = useMemo(() => {
    return Array.from(activeStages).filter(stageId => {
      const stage = stagesWithCriteria.find(s => s.id === stageId);
      if (!stage) return false;
      return stage.criteria.some(c => selectedCriteria.has(c.id));
    });
  }, [activeStages, selectedCriteria, stagesWithCriteria]);

  const criteriaContext = useMemo((): CriteriaContext[] => {
    return stagesWithCriteria
      .filter(stage => activeStages.has(stage.id))
      .map(stage => ({
        stageId: stage.id,
        totalCriteria: stage.criteria.length,
        selectedCriteria: stage.criteria.filter(c => selectedCriteria.has(c.id)).length
      }));
  }, [stagesWithCriteria, activeStages, selectedCriteria]);

  const totalEligible = useMemo(() => {
    return sites.reduce((sum, site) => sum + calculateEligiblePatients(site, activeStageIds, criteriaContext), 0);
  }, [sites, activeStageIds, criteriaContext]);

  const totalPatients = useMemo(() => {
    return sites.reduce((sum, site) => sum + site.totalPatients, 0);
  }, [sites]);

  const rankedSites = useMemo(() => {
    return sortSitesByEligibility(sites, activeStageIds, criteriaContext);
  }, [sites, activeStageIds, criteriaContext]);

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

  const addStageToFunnel = (stage: FunnelStageWithCriteria) => {
    setActiveStages(prev => new Set(prev).add(stage.id));
    setExpandedStages(prev => new Set(prev).add(stage.id));
    setSelectedCriteria(prev => {
      const next = new Set(prev);
      stage.criteria.forEach(c => next.add(c.id));
      return next;
    });
  };

  const removeStageFromFunnel = (stage: FunnelStageWithCriteria) => {
    setActiveStages(prev => {
      const next = new Set(prev);
      next.delete(stage.id);
      return next;
    });
    setSelectedCriteria(prev => {
      const next = new Set(prev);
      stage.criteria.forEach(c => next.delete(c.id));
      return next;
    });
  };

  const toggleCriterion = (criterionId: string) => {
    setSelectedCriteria(prev => {
      const next = new Set(prev);
      if (next.has(criterionId)) {
        next.delete(criterionId);
      } else {
        next.add(criterionId);
      }
      return next;
    });
  };

  const getStageSelectedCount = (stage: FunnelStageWithCriteria) => {
    return stage.criteria.filter(c => selectedCriteria.has(c.id)).length;
  };

  const isStageActive = (stageId: string) => activeStages.has(stageId);

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <header className="border-b border-gray-200 bg-white px-6 py-3 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/eligibility-analysis")}
              className="text-gray-500 hover:text-gray-900"
              data-testid="btn-back-to-wizard"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
            <Separator orientation="vertical" className="h-6" />
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-gray-900">Site360</h1>
              <p className="text-xs text-gray-500">{ascensionSystem?.systemName}</p>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <div className="text-right">
              <p className="text-xs text-gray-500">Eligible Patients</p>
              <p className="text-lg font-bold text-gray-900">{totalEligible.toLocaleString()}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-500">Conversion Rate</p>
              <p className="text-lg font-bold text-gray-900">
                {totalPatients > 0 ? Math.round((totalEligible / totalPatients) * 100) : 0}%
              </p>
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        <aside className="w-[400px] flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
          <div className="p-4 border-b border-gray-100">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-gray-400" />
              <h2 className="font-semibold text-gray-900">Funnel Stages</h2>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              {activeStages.size} of {stagesWithCriteria.length} stages in funnel
            </p>
          </div>
          
          <ScrollArea className="flex-1">
            <div className="p-2">
              {stagesWithCriteria.map((stage, idx) => {
                const isExpanded = expandedStages.has(stage.id);
                const isActive = isStageActive(stage.id);
                const selectedCount = getStageSelectedCount(stage);

                return (
                  <div key={stage.id} className="mb-2">
                    <div className={cn(
                      "rounded-lg border overflow-hidden transition-all",
                      isActive 
                        ? "border-gray-300 bg-white shadow-sm" 
                        : "border-gray-100 bg-gray-50"
                    )}>
                      <div className="flex items-center gap-2 p-3">
                        {!isActive ? (
                          <button
                            onClick={() => addStageToFunnel(stage)}
                            className="w-6 h-6 rounded-full bg-gray-200 hover:bg-gray-900 hover:text-white flex items-center justify-center transition-colors flex-shrink-0"
                            data-testid={`add-stage-${stage.id}`}
                          >
                            <Plus className="w-3.5 h-3.5" />
                          </button>
                        ) : (
                          <button
                            onClick={() => removeStageFromFunnel(stage)}
                            className="w-6 h-6 rounded-full bg-gray-900 text-white hover:bg-red-500 flex items-center justify-center transition-colors flex-shrink-0 group"
                            data-testid={`remove-stage-${stage.id}`}
                          >
                            <Check className="w-3.5 h-3.5 group-hover:hidden" />
                            <X className="w-3.5 h-3.5 hidden group-hover:block" />
                          </button>
                        )}
                        
                        <button
                          onClick={() => isActive && toggleStageExpanded(stage.id)}
                          className={cn(
                            "flex-1 text-left flex items-center gap-2 min-w-0",
                            !isActive && "opacity-60"
                          )}
                          disabled={!isActive}
                        >
                          <div className={cn(
                            "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0",
                            isActive ? "bg-gray-900 text-white" : "bg-gray-300 text-gray-600"
                          )}>
                            {idx + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className={cn(
                              "text-sm font-medium truncate",
                              isActive ? "text-gray-900" : "text-gray-500"
                            )}>
                              {stage.name}
                            </p>
                            {isActive && (
                              <p className="text-xs text-gray-400">
                                {selectedCount}/{stage.criteria.length} criteria
                              </p>
                            )}
                          </div>
                          {isActive && (
                            isExpanded ? (
                              <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
                            ) : (
                              <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
                            )
                          )}
                        </button>
                      </div>
                      
                      {isActive && isExpanded && (
                        <div className="border-t border-gray-100 bg-gray-50/50">
                          <div className="p-2 space-y-1">
                            {stage.criteria.map(criterion => {
                              const isQueryable = criterion.queryableStatus === "fully_queryable" || criterion.queryableStatus === "partially_queryable";
                              const isScreening = criterion.queryableStatus === "screening";
                              const isNotApplicable = criterion.queryableStatus === "not_applicable";
                              const isDisabled = isScreening || isNotApplicable;

                              return (
                                <div
                                  key={criterion.id}
                                  className={cn(
                                    "flex items-start gap-2 p-2 rounded-md transition-colors",
                                    isDisabled ? "opacity-50 cursor-not-allowed" : "hover:bg-white cursor-pointer"
                                  )}
                                >
                                  <Checkbox
                                    checked={isQueryable && selectedCriteria.has(criterion.id)}
                                    onCheckedChange={() => !isDisabled && toggleCriterion(criterion.id)}
                                    disabled={isDisabled}
                                    className="mt-0.5"
                                  />
                                  <button
                                    onClick={() => setQebDetailModal(criterion)}
                                    className="flex-1 min-w-0 text-left"
                                  >
                                    <span className={cn(
                                      "text-xs leading-relaxed block",
                                      isDisabled ? "text-gray-400" : selectedCriteria.has(criterion.id) ? "text-gray-900" : "text-gray-500"
                                    )}>
                                      {criterion.name}
                                    </span>
                                    <div className="flex items-center gap-1 mt-1 flex-wrap">
                                      <Badge 
                                        variant="outline" 
                                        className={cn(
                                          "text-[9px] uppercase",
                                          criterion.type === "exclusion" 
                                            ? "border-red-200 text-red-600" 
                                            : "border-blue-200 text-blue-600"
                                        )}
                                      >
                                        {criterion.type}
                                      </Badge>
                                      <Badge 
                                        variant="outline" 
                                        className={cn(
                                          "text-[9px] uppercase",
                                          isQueryable ? "border-green-200 text-green-600 bg-green-50" :
                                          isScreening ? "border-yellow-200 text-yellow-600 bg-yellow-50" :
                                          "border-gray-200 text-gray-400 bg-gray-50"
                                        )}
                                      >
                                        {criterion.queryableStatus?.replace(/_/g, ' ')}
                                      </Badge>
                                    </div>
                                  </button>
                                  <button
                                    onClick={() => setQebDetailModal(criterion)}
                                    className="p-1 hover:bg-gray-200 rounded transition-colors flex-shrink-0"
                                    data-testid={`btn-qeb-detail-${criterion.id}`}
                                  >
                                    <Info className="w-3.5 h-3.5 text-gray-400" />
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        </aside>

        <main className="flex-1 flex flex-col min-w-0 p-4 gap-4">
          <div className="h-[45%] min-h-[250px]">
            <USMapVisualization sites={sites} activeStageIds={activeStageIds} criteriaContext={criteriaContext} />
          </div>

          <div className="flex-1 bg-white rounded-xl border border-gray-200 flex flex-col min-h-0">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between flex-shrink-0">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-gray-900">Site Rankings</h3>
                <Badge variant="outline" className="text-xs">{sites.length} sites</Badge>
              </div>
              <div className="flex items-center gap-4 text-xs text-gray-500">
                <span>
                  {activeStages.size === 0 
                    ? "Showing total patient population" 
                    : `Filtered by ${activeStages.size} stage${activeStages.size > 1 ? 's' : ''}`
                  }
                </span>
              </div>
            </div>
            
            <ScrollArea className="flex-1">
              <TooltipProvider>
                <div className="p-3 space-y-2">
                  {rankedSites.map((site, idx) => {
                    const eligible = calculateEligiblePatients(site, activeStageIds, criteriaContext);
                    const percentage = site.totalPatients > 0 
                      ? Math.round((eligible / site.totalPatients) * 100) 
                      : 0;

                    return (
                      <div
                        key={site.siteId}
                        className={cn(
                          "flex items-center gap-3 p-3 rounded-lg border transition-all",
                          site.hasCompetingNSCLCTrial && "border-l-4 border-l-red-500",
                          idx === 0 && !site.hasCompetingNSCLCTrial
                            ? "bg-gray-900 text-white border-gray-900" 
                            : idx === 0 && site.hasCompetingNSCLCTrial
                            ? "bg-gray-900 text-white border-gray-900"
                            : "bg-white border-gray-100 hover:border-gray-200"
                        )}
                        data-testid={`site-row-${site.siteId}`}
                      >
                        <div className={cn(
                          "w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0",
                          idx === 0 ? "bg-white text-gray-900" : "bg-gray-100 text-gray-600"
                        )}>
                          {idx + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className={cn(
                              "text-sm font-medium truncate",
                              idx === 0 ? "text-white" : "text-gray-900"
                            )}>
                              {site.siteName}
                            </p>
                            {site.hasCompetingNSCLCTrial && (
                              <Tooltip>
                                <TooltipTrigger>
                                  <span className="flex items-center gap-1 px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-[10px] font-medium">
                                    <AlertTriangle className="w-3 h-3" />
                                    Competing NSCLC Trial
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p>Site is running a competing NSCLC trial</p>
                                </TooltipContent>
                              </Tooltip>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-1">
                            <div className={cn(
                              "flex items-center gap-1 text-xs",
                              idx === 0 ? "text-gray-300" : "text-gray-500"
                            )}>
                              <MapPin className="w-3 h-3" />
                              {site.city}, {site.stateCode}
                            </div>
                            <button
                              onClick={() => setLogisticsModalSite(site)}
                              className={cn(
                                "flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium transition-colors",
                                idx === 0 
                                  ? "bg-white/20 text-white hover:bg-white/30" 
                                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                              )}
                              data-testid={`btn-site-logistics-${site.siteId}`}
                            >
                              <Building2 className="w-3 h-3" />
                              Site Logistics
                            </button>
                          </div>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <p className={cn(
                            "text-lg font-bold",
                            idx === 0 ? "text-white" : "text-gray-900"
                          )}>
                            {eligible.toLocaleString()}
                          </p>
                          <div className="flex items-center gap-2">
                            <div className={cn(
                              "w-16 h-1 rounded-full overflow-hidden",
                              idx === 0 ? "bg-gray-700" : "bg-gray-200"
                            )}>
                              <div
                                className={cn(
                                  "h-full rounded-full",
                                  idx === 0 ? "bg-white" : "bg-gray-500"
                                )}
                                style={{ width: `${Math.min(percentage, 100)}%` }}
                              />
                            </div>
                            <span className={cn(
                              "text-xs",
                              idx === 0 ? "text-gray-300" : "text-gray-500"
                            )}>
                              {percentage}%
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </TooltipProvider>
            </ScrollArea>
          </div>
        </main>
      </div>

      <Dialog open={!!logisticsModalSite} onOpenChange={(open) => !open && setLogisticsModalSite(null)}>
        <DialogContent className="max-w-lg z-[2000]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Building2 className="w-5 h-5 text-gray-600" />
              Site Logistics
            </DialogTitle>
          </DialogHeader>
          {logisticsModalSite && siteOperationsLogistics && (
            <div className="space-y-4">
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="font-medium text-gray-900 text-sm">{logisticsModalSite.siteName}</p>
                <p className="text-xs text-gray-500">{logisticsModalSite.city}, {logisticsModalSite.state}</p>
              </div>
              
              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Facility Requirements</h4>
                {siteOperationsLogistics.site_selection?.facility_requirements?.equipment_required?.map((equip: string, i: number) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-gray-100">
                    <span className="text-sm text-gray-700">{equip}</span>
                    <span className="flex items-center gap-1 text-green-600 text-xs">
                      <CheckCircle2 className="w-4 h-4" />
                      Available
                    </span>
                  </div>
                ))}
                
                {siteOperationsLogistics.site_selection?.facility_requirements?.laboratory_capabilities?.map((cap: string, i: number) => (
                  <div key={`lab-${i}`} className="flex items-center justify-between py-2 border-b border-gray-100">
                    <span className="text-sm text-gray-700">{cap}</span>
                    <span className="flex items-center gap-1 text-green-600 text-xs">
                      <CheckCircle2 className="w-4 h-4" />
                      Available
                    </span>
                  </div>
                ))}
                
                {siteOperationsLogistics.site_selection?.facility_requirements?.pharmacy_capabilities && (
                  <div className="flex items-center justify-between py-2 border-b border-gray-100">
                    <span className="text-sm text-gray-700">Pharmacy Capability</span>
                    <span className="flex items-center gap-1 text-green-600 text-xs">
                      <CheckCircle2 className="w-4 h-4" />
                      Available
                    </span>
                  </div>
                )}
                
                {siteOperationsLogistics.site_selection?.facility_requirements?.storage_capabilities && (
                  <div className="flex items-center justify-between py-2 border-b border-gray-100">
                    <span className="text-sm text-gray-700">Storage: {siteOperationsLogistics.site_selection.facility_requirements.storage_capabilities}</span>
                    <span className="flex items-center gap-1 text-green-600 text-xs">
                      <CheckCircle2 className="w-4 h-4" />
                      Compliant
                    </span>
                  </div>
                )}
              </div>
              
                          </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!qebDetailModal} onOpenChange={(open) => !open && setQebDetailModal(null)}>
        <DialogContent className="max-w-xl z-[2000]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Database className="w-5 h-5 text-gray-600" />
              Atomic Criteria Details
            </DialogTitle>
          </DialogHeader>
          {qebDetailModal && (
            <div className="space-y-4 max-h-[60vh] overflow-y-auto">
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="font-medium text-gray-900 text-sm">{qebDetailModal.id}</p>
                <p className="text-xs text-gray-500 mt-1">{qebDetailModal.name.split(': ')[1]}</p>
                <div className="flex items-center gap-2 mt-2">
                  <Badge 
                    variant="outline" 
                    className={cn(
                      "text-[10px] uppercase",
                      qebDetailModal.type === "exclusion" 
                        ? "border-red-200 text-red-600" 
                        : "border-blue-200 text-blue-600"
                    )}
                  >
                    {qebDetailModal.type}
                  </Badge>
                  <Badge 
                    variant="outline" 
                    className={cn(
                      "text-[10px] uppercase",
                      qebDetailModal.queryableStatus === "fully_queryable" || qebDetailModal.queryableStatus === "partially_queryable"
                        ? "border-green-200 text-green-600 bg-green-50" 
                        : qebDetailModal.queryableStatus === "screening"
                        ? "border-yellow-200 text-yellow-600 bg-yellow-50"
                        : "border-gray-200 text-gray-400 bg-gray-50"
                    )}
                  >
                    {qebDetailModal.queryableStatus?.replace(/_/g, ' ')}
                  </Badge>
                </div>
              </div>
              
              <div className="space-y-3">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <FileText className="w-4 h-4 text-gray-400" />
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Original Protocol Text</h4>
                  </div>
                  <div className="bg-blue-50 border border-blue-100 rounded-lg p-3">
                    <p className="text-sm text-gray-700 italic">"{qebDetailModal.protocolText}"</p>
                  </div>
                </div>
                
                <div>
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Clinical Description</h4>
                  <p className="text-sm text-gray-700">{qebDetailModal.clinicalDescription}</p>
                </div>
                
                {qebDetailModal.atomicIds && qebDetailModal.atomicIds.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      Atomic Criteria ({qebDetailModal.atomicIds.length})
                    </h4>
                    <div className="space-y-2">
                      {qebDetailModal.atomicIds.map((atomicId) => {
                        const atomic = atomicLookup.get(atomicId);
                        if (!atomic) return null;
                        
                        const isQueryable = atomic.queryableStatus === "fully_queryable" || atomic.queryableStatus === "partially_queryable";
                        const isSelected = selectedAtomics.has(atomicId);
                        
                        return (
                          <div 
                            key={atomicId} 
                            className={cn(
                              "rounded-lg p-3 border transition-colors",
                              isQueryable 
                                ? "bg-white border-gray-200 hover:border-gray-300" 
                                : "bg-gray-50 border-gray-100 opacity-60"
                            )}
                          >
                            <div className="flex items-start gap-3">
                              <Checkbox
                                checked={isQueryable && isSelected}
                                onCheckedChange={() => isQueryable && toggleAtomic(atomicId)}
                                disabled={!isQueryable}
                                className="mt-0.5"
                              />
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-xs font-mono text-gray-500">{atomicId}</span>
                                  <Badge 
                                    variant="outline" 
                                    className={cn(
                                      "text-[9px] uppercase",
                                      isQueryable 
                                        ? "border-green-200 text-green-600 bg-green-50" 
                                        : "border-gray-200 text-gray-400"
                                    )}
                                  >
                                    {atomic.queryableStatus?.replace(/_/g, ' ')}
                                  </Badge>
                                  <Badge 
                                    variant="outline" 
                                    className="text-[9px] uppercase border-gray-200 text-gray-500"
                                  >
                                    {atomic.category?.replace(/_/g, ' ')}
                                  </Badge>
                                </div>
                                <p className="text-sm text-gray-900 mt-1">{atomic.atomicText}</p>
                                
                                {atomic.omopQuery?.sql && (
                                  <div className="mt-2">
                                    <div className="flex items-center gap-1 mb-1">
                                      <Database className="w-3 h-3 text-blue-500" />
                                      <span className="text-[10px] font-semibold text-blue-600 uppercase">SQL Query</span>
                                    </div>
                                    <div className="bg-gray-900 rounded p-2 overflow-x-auto">
                                      <code className="text-[10px] text-green-400 font-mono whitespace-pre-wrap break-all">
                                        {atomic.omopQuery.sql}
                                      </code>
                                    </div>
                                  </div>
                                )}
                                
                                {atomic.fhirQuery && (
                                  <div className="mt-2">
                                    <div className="flex items-center gap-1 mb-1">
                                      <FileText className="w-3 h-3 text-orange-500" />
                                      <span className="text-[10px] font-semibold text-orange-600 uppercase">FHIR Query</span>
                                    </div>
                                    <div className="bg-orange-50 border border-orange-100 rounded p-2">
                                      <div className="text-[10px] text-gray-700">
                                        <span className="font-semibold">Resource:</span> {atomic.fhirQuery.resourceType}
                                      </div>
                                      {atomic.fhirQuery.searchParams && (
                                        <div className="text-[10px] text-gray-600 mt-1 font-mono break-all">
                                          {atomic.fhirQuery.searchParams}
                                        </div>
                                      )}
                                      {atomic.fhirQuery.codes && atomic.fhirQuery.codes.length > 0 && (
                                        <div className="mt-1 flex flex-wrap gap-1">
                                          {atomic.fhirQuery.codes.map((code: {system: string; code: string; display: string}, ci: number) => (
                                            <Badge key={ci} variant="outline" className="text-[9px] bg-white border-orange-200 text-orange-700">
                                              {code.display || code.code}
                                            </Badge>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                )}
                                
                                {atomic.omopQuery?.conceptNames && atomic.omopQuery.conceptNames.length > 0 && (
                                  <div className="flex items-center gap-1 mt-2 flex-wrap">
                                    <span className="text-xs text-gray-400">OMOP Concepts:</span>
                                    {atomic.omopQuery.conceptNames.slice(0, 3).map((name, i) => (
                                      <Badge key={i} variant="outline" className="text-[9px] bg-blue-50 border-blue-100 text-blue-700">
                                        {name}
                                      </Badge>
                                    ))}
                                    {atomic.omopQuery.conceptNames.length > 3 && (
                                      <span className="text-xs text-gray-400">+{atomic.omopQuery.conceptNames.length - 3} more</span>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <p className="text-xs text-gray-500 mt-3 italic">
                      Deselecting atomic criteria will recalculate site rankings based on remaining queryable criteria.
                    </p>
                  </div>
                )}
                
                {qebDetailModal.omopConcepts && qebDetailModal.omopConcepts.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">OMOP Concepts</h4>
                    <div className="space-y-2">
                      {qebDetailModal.omopConcepts.map((concept, i) => (
                        <div key={i} className="bg-gray-50 rounded-lg p-2 border border-gray-100">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-gray-900">{concept.conceptName}</span>
                            <Badge variant="outline" className="text-[9px]">{concept.domain}</Badge>
                          </div>
                          <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
                            <span>ID: {concept.conceptId}</span>
                            <span>•</span>
                            <span>{concept.vocabularyId}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              
                          </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
