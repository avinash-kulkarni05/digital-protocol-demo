import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, Droplets, FlaskConical, Thermometer,
  Package, Truck, Beaker, LayoutGrid, ChevronDown,
  TestTube, Clock, Building2, Calendar, Settings,
  Shield, FileCheck, Boxes, AlertCircle, Scale,
  ClipboardList, MapPin, Layers, RefreshCw, Hash
} from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";
import { EditableText } from "./EditableValue";

interface BiospecimenViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "specimens" | "containers" | "schedule" | "processing" | "storage" | "shipping" | "kits" | "quality" | "regulatory";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

// Helper function to safely render Code objects that might be {decode: "string"} or {code: "string"}
function renderCodeValue(value: any): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object' && value.decode) return value.decode;
  if (typeof value === 'object' && value.code) return value.code;
  return String(value);
}

function SummaryHeader({ data }: { data: any }) {
  const specimenCount = data?.discovered_specimen_types?.length || 0;
  const totalVolume = data?.volume_summary?.total_blood_volume || "N/A";
  const perVisitMax = data?.volume_summary?.per_visit_maximum || "N/A";
  
  return (
    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="biospecimen-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center shadow-md">
          <Droplets className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Biospecimen Handling</h3>
          <p className="text-sm text-muted-foreground">Sample collection, storage, and shipping</p>
        </div>
      </div>
      
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Specimen Types</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{specimenCount}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <Droplets className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total Volume</span>
          </div>
          <p className="text-lg font-bold text-gray-900">{totalVolume}</p>
        </div>
        
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <Beaker className="w-4 h-4 text-gray-600" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Per Visit Max</span>
          </div>
          <p className="text-lg font-bold text-gray-900">{perVisitMax}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  return (
    <div className="space-y-6">
      {/* Central Laboratory */}
      {data.central_laboratory && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-gray-900 to-gray-700 flex items-center justify-center flex-shrink-0 shadow-md">
              <Building2 className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-3">
                <h4 className="font-bold text-gray-900 text-lg">Central Laboratory</h4>
                <ProvenanceChip provenance={data.central_laboratory.provenance} onViewSource={onViewSource} />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {data.central_laboratory.name && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Lab Name</span>
                    <span className="font-semibold text-gray-900">
                      <EditableText
                        value={data.central_laboratory.name}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.biospecimenHandling.data.central_laboratory.name", v) : undefined}
                      />
                    </span>
                  </div>
                )}
                {data.central_laboratory.location && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Location</span>
                    <span className="font-semibold text-gray-900">
                      <EditableText
                        value={data.central_laboratory.location}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.biospecimenHandling.data.central_laboratory.location", v) : undefined}
                      />
                    </span>
                  </div>
                )}
                {data.central_laboratory.contact_info && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Contact</span>
                    <span className="font-semibold text-gray-900">
                      <EditableText
                        value={data.central_laboratory.contact_info}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.biospecimenHandling.data.central_laboratory.contact_info", v) : undefined}
                      />
                    </span>
                  </div>
                )}
              </div>
              {/* Accreditations */}
              {data.central_laboratory.accreditations?.length > 0 && (
                <div className="mt-3">
                  <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-2">Accreditations</span>
                  <div className="flex flex-wrap gap-2">
                    {data.central_laboratory.accreditations.map((accred: string, idx: number) => (
                      <span key={idx} className="px-2.5 py-1 bg-gray-100 text-gray-800 text-xs font-medium rounded-full border border-gray-200">
                        {accred}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Volume Summary - Enhanced with deep fields */}
      {data.volume_summary && (
        <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
              <Droplets className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-3">
                <h4 className="font-bold text-gray-900 text-lg">Volume Summary</h4>
                <ProvenanceChip provenance={data.volume_summary.provenance} onViewSource={onViewSource} />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {data.volume_summary.total_blood_volume && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Total Blood Volume</span>
                    <span className="font-semibold text-gray-900">
                      <EditableText
                        value={data.volume_summary.total_blood_volume}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.biospecimenHandling.data.volume_summary.total_blood_volume", v) : undefined}
                      />
                    </span>
                  </div>
                )}
                {data.volume_summary.total_blood_volume_per_visit && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Per Visit Volume</span>
                    <span className="font-semibold text-gray-900">
                      <EditableText
                        value={data.volume_summary.total_blood_volume_per_visit}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.biospecimenHandling.data.volume_summary.total_blood_volume_per_visit", v) : undefined}
                      />
                    </span>
                  </div>
                )}
                {data.volume_summary.total_blood_volume_per_subject && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Per Subject Volume</span>
                    <span className="font-semibold text-gray-900">
                      <EditableText
                        value={data.volume_summary.total_blood_volume_per_subject}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.biospecimenHandling.data.volume_summary.total_blood_volume_per_subject", v) : undefined}
                      />
                    </span>
                  </div>
                )}
                {data.volume_summary.per_visit_maximum && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Per Visit Maximum</span>
                    <span className="font-semibold text-gray-900">
                      <EditableText
                        value={data.volume_summary.per_visit_maximum}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.biospecimenHandling.data.volume_summary.per_visit_maximum", v) : undefined}
                      />
                    </span>
                  </div>
                )}
                {data.volume_summary.maximum_single_draw && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Max Single Draw</span>
                    <span className="font-semibold text-gray-900">
                      <EditableText
                        value={data.volume_summary.maximum_single_draw}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.biospecimenHandling.data.volume_summary.maximum_single_draw", v) : undefined}
                      />
                    </span>
                  </div>
                )}
                {data.volume_summary.safety_threshold && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Safety Threshold</span>
                    <span className="font-semibold text-gray-900">
                      <EditableText
                        value={data.volume_summary.safety_threshold}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.biospecimenHandling.data.volume_summary.safety_threshold", v) : undefined}
                      />
                    </span>
                  </div>
                )}
              </div>
              {/* Additional deep fields */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
                {data.volume_summary.pediatric_adjustments && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Pediatric Adjustments</span>
                    <span className="text-sm text-gray-900">{data.volume_summary.pediatric_adjustments}</span>
                  </div>
                )}
                {data.volume_summary.volume_limit_compliance && (
                  <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Volume Limit Compliance</span>
                    <span className="text-sm text-gray-900">{data.volume_summary.volume_limit_compliance}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Biospecimen Overview Stats */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Package className="w-5 h-5 text-gray-600" />
            Biospecimen Overview
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <FlaskConical className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{data.discovered_specimen_types?.length || 0}</p>
              <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Specimen Types</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <TestTube className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{data.collection_containers?.length || 0}</p>
              <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Containers</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Calendar className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{data.collection_schedule?.length || 0}</p>
              <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Schedule Items</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Settings className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{data.processing_requirements?.length || 0}</p>
              <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Processing Steps</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Thermometer className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{Array.isArray(data.storage_requirements) ? data.storage_requirements.length : (data.storage_requirements ? 1 : 0)}</p>
              <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Storage Reqs</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SpecimenCard({ specimen, onViewSource }: { specimen: any; onViewSource?: (page: number) => void }) {
  const [showAllData, setShowAllData] = useState(false);

  // Determine purpose display
  const purposeDisplay = specimen.purpose?.decode || specimen.purpose?.code || specimen.purpose;

  return (
    <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm" data-testid={`specimen-${specimen.id}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
            <FlaskConical className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <span className="font-medium text-foreground">{specimen.specimen_name || specimen.specimen_type}</span>
            {specimen.specimen_subtype && (
              <span className="ml-2 text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                {specimen.specimen_subtype}
              </span>
            )}
            {specimen.purpose_description && (
              <p className="text-sm text-muted-foreground">{specimen.purpose_description}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {purposeDisplay && (
            <span className="text-xs bg-gray-50 text-gray-700 rounded-full px-2.5 py-1 border border-gray-200">
              {purposeDisplay}
            </span>
          )}
          {specimen.collection_count && (
            <span className="text-xs bg-gray-50 text-gray-700 rounded-full px-2.5 py-1 border border-gray-200">
              {specimen.collection_count} collections
            </span>
          )}
          <ProvenanceChip provenance={specimen.provenance} onViewSource={onViewSource} />
          <button
            type="button"
            onClick={() => setShowAllData(!showAllData)}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
            data-testid={`expand-specimen-${specimen.id}`}
          >
            <ChevronDown className={cn("w-4 h-4 text-gray-500 transition-transform", showAllData && "rotate-180")} />
          </button>
        </div>
      </div>

      {/* Quick Display of Key Fields */}
      <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2">
        {specimen.specimen_subtype && (
          <div className="bg-gray-50 rounded-lg p-2 text-center">
            <span className="text-xs text-gray-500 block">Subtype</span>
            <span className="text-sm font-medium text-gray-900">{renderCodeValue(specimen.specimen_subtype)}</span>
          </div>
        )}
        {specimen.volume && (
          <div className="bg-gray-50 rounded-lg p-2 text-center">
            <span className="text-xs text-gray-500 block">Volume</span>
            <span className="text-sm font-medium text-gray-900">{renderCodeValue(specimen.volume)}</span>
          </div>
        )}
        {specimen.collection_method && (
          <div className="bg-gray-50 rounded-lg p-2 text-center">
            <span className="text-xs text-gray-500 block">Collection Method</span>
            <span className="text-sm font-medium text-gray-900">{renderCodeValue(specimen.collection_method)}</span>
          </div>
        )}
        {specimen.testing_lab && (
          <div className="bg-gray-50 rounded-lg p-2 text-center">
            <span className="text-xs text-gray-500 block">Testing Lab</span>
            <span className="text-sm font-medium text-gray-900">{renderCodeValue(specimen.testing_lab)}</span>
          </div>
        )}
      </div>

      {/* Biomedical Concept */}
      {specimen.biomedicalConcept && (
        <div className="mt-3 p-2 bg-gray-50 rounded-lg border border-gray-200">
          <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-1">CDISC Biomedical Concept</span>
          <div className="flex flex-wrap gap-2 text-xs">
            {specimen.biomedicalConcept.code && (
              <span className="bg-white px-2 py-1 rounded border border-gray-200">
                Code: {specimen.biomedicalConcept.code}
              </span>
            )}
            {specimen.biomedicalConcept.decode && (
              <span className="bg-white px-2 py-1 rounded border border-gray-200">
                {specimen.biomedicalConcept.decode}
              </span>
            )}
            {specimen.biomedicalConcept.codeSystem && (
              <span className="bg-white px-2 py-1 rounded border border-gray-200 text-gray-500">
                {specimen.biomedicalConcept.codeSystem}
              </span>
            )}
          </div>
        </div>
      )}

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
              <SmartDataRender
                data={specimen}
                onViewSource={onViewSource}
                editable={false}
                excludeFields={["provenance", "specimen_name", "specimen_type", "specimen_subtype", "purpose", "purpose_description", "biomedicalConcept", "collection_count", "volume", "collection_method", "testing_lab"]}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SpecimensTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const specimens = data?.discovered_specimen_types || [];
  
  if (specimens.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <FlaskConical className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No specimen types defined</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-3">
      {specimens.map((specimen: any, idx: number) => (
        <SpecimenCard key={specimen.id || idx} specimen={specimen} onViewSource={onViewSource} />
      ))}
    </div>
  );
}

// Collection Containers Tab
function ContainersTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const containers = data?.collection_containers || [];

  if (containers.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <TestTube className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No collection containers defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {containers.map((container: any, idx: number) => (
        <div key={container.container_id || idx} className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
                <TestTube className="w-5 h-5 text-gray-600" />
              </div>
              <div>
                <span className="font-medium text-foreground">{container.container_name || container.container_id}</span>
                {container.tube_type && (
                  <span className="ml-2 text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full border border-gray-200">
                    {container.tube_type}
                  </span>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={container.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {container.tube_color && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Tube Color</span>
                <span className="text-sm font-medium text-gray-900">{container.tube_color}</span>
              </div>
            )}
            {container.anticoagulant && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Anticoagulant</span>
                <span className="text-sm font-medium text-gray-900">{container.anticoagulant}</span>
              </div>
            )}
            {container.preservative && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Preservative</span>
                <span className="text-sm font-medium text-gray-900">{container.preservative}</span>
              </div>
            )}
            {container.volume_capacity && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Capacity</span>
                <span className="text-sm font-medium text-gray-900">{container.volume_capacity}</span>
              </div>
            )}
            {container.fill_volume && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Fill Volume</span>
                <span className="text-sm font-medium text-gray-900">{container.fill_volume}</span>
              </div>
            )}
            {container.specimen_ref && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Specimen Ref</span>
                <span className="text-sm font-medium text-gray-900">{container.specimen_ref}</span>
              </div>
            )}
          </div>

          {container.special_instructions && (
            <div className="mt-3 p-2 bg-yellow-50 rounded-lg border border-yellow-200">
              <span className="text-xs font-medium text-yellow-700 uppercase tracking-wider block mb-1">Special Instructions</span>
              <p className="text-sm text-gray-900">{container.special_instructions}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// Collection Schedule Tab
function ScheduleTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const schedule = data?.collection_schedule || [];

  if (schedule.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Calendar className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No collection schedule defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {schedule.map((item: any, idx: number) => (
        <div key={item.schedule_id || idx} className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-green-100 rounded-xl flex items-center justify-center">
                <Calendar className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <span className="font-medium text-foreground">{item.schedule_id || `Schedule ${idx + 1}`}</span>
                {item.timepoint_type && (
                  <span className="ml-2 text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full border border-green-200">
                    {renderCodeValue(item.timepoint_type)}
                  </span>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={item.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {item.specimen_ref && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Specimen</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.specimen_ref)}</span>
              </div>
            )}
            {item.relative_time && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Relative Time</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.relative_time)}</span>
              </div>
            )}
            {item.collection_window && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Collection Window</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.collection_window)}</span>
              </div>
            )}
            {item.number_of_samples && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block"># Samples</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.number_of_samples)}</span>
              </div>
            )}
            {item.volume_per_sample && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Volume/Sample</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.volume_per_sample)}</span>
              </div>
            )}
            {item.fasting_required !== undefined && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Fasting Required</span>
                <span className={cn("text-sm font-medium", item.fasting_required ? "text-gray-600" : "text-gray-900")}>
                  {item.fasting_required ? "Yes" : "No"}
                </span>
              </div>
            )}
            {item.fasting_duration && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Fasting Duration</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.fasting_duration)}</span>
              </div>
            )}
          </div>

          {item.special_conditions && (
            <div className="mt-3 p-2 bg-gray-50 rounded-lg border border-gray-200">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-1">Special Conditions</span>
              <p className="text-sm text-gray-900">{renderCodeValue(item.special_conditions)}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// Processing Requirements Tab
function ProcessingTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const processing = data?.processing_requirements || [];

  if (processing.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Settings className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No processing requirements defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {processing.map((item: any, idx: number) => (
        <div key={item.processing_id || idx} className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
                <Settings className="w-5 h-5 text-gray-600" />
              </div>
              <div>
                <span className="font-medium text-foreground">{item.processing_step || item.processing_id || `Step ${idx + 1}`}</span>
                {item.step_order && (
                  <span className="ml-2 text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full border border-gray-200">
                    Step {item.step_order}
                  </span>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={item.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {item.specimen_ref && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Specimen</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.specimen_ref)}</span>
              </div>
            )}
            {item.time_constraint && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Time Constraint</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.time_constraint)}</span>
              </div>
            )}
            {item.time_zero_reference && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Time Zero Ref</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.time_zero_reference)}</span>
              </div>
            )}
            {item.temperature_during_processing && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Temperature</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.temperature_during_processing)}</span>
              </div>
            )}
          </div>

          {/* Centrifuge Settings */}
          {(item.centrifuge_speed || item.centrifuge_time || item.centrifuge_temperature) && (
            <div className="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-2">Centrifuge Settings</span>
              <div className="grid grid-cols-3 gap-3">
                {item.centrifuge_speed && (
                  <div>
                    <span className="text-xs text-gray-500 block">Speed</span>
                    <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.centrifuge_speed)}</span>
                  </div>
                )}
                {item.centrifuge_time && (
                  <div>
                    <span className="text-xs text-gray-500 block">Time</span>
                    <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.centrifuge_time)}</span>
                  </div>
                )}
                {item.centrifuge_temperature && (
                  <div>
                    <span className="text-xs text-gray-500 block">Temperature</span>
                    <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.centrifuge_temperature)}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Aliquot Settings */}
          {(item.aliquot_count || item.aliquot_volume || item.aliquot_container) && (
            <div className="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-2">Aliquot Settings</span>
              <div className="grid grid-cols-3 gap-3">
                {item.aliquot_count && (
                  <div>
                    <span className="text-xs text-gray-500 block">Count</span>
                    <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.aliquot_count)}</span>
                  </div>
                )}
                {item.aliquot_volume && (
                  <div>
                    <span className="text-xs text-gray-500 block">Volume</span>
                    <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.aliquot_volume)}</span>
                  </div>
                )}
                {item.aliquot_container && (
                  <div>
                    <span className="text-xs text-gray-500 block">Container</span>
                    <span className="text-sm font-medium text-gray-900">{renderCodeValue(item.aliquot_container)}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {item.special_instructions && (
            <div className="mt-3 p-2 bg-yellow-50 rounded-lg border border-yellow-200">
              <span className="text-xs font-medium text-yellow-700 uppercase tracking-wider block mb-1">Special Instructions</span>
              <p className="text-sm text-gray-900">{renderCodeValue(item.special_instructions)}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// Enhanced Storage Tab with deep fields
function StorageTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const storageReqs = Array.isArray(data?.storage_requirements)
    ? data.storage_requirements
    : data?.storage_requirements ? [data.storage_requirements] : [];

  if (storageReqs.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Thermometer className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No storage requirements defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {storageReqs.map((storage: any, idx: number) => (
        <div key={storage.storage_id || idx} className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
                <Thermometer className="w-5 h-5 text-gray-600" />
              </div>
              <div>
                <span className="font-medium text-foreground">{renderCodeValue(storage.specimen_type) || renderCodeValue(storage.specimen_ref) || `Storage ${idx + 1}`}</span>
                {storage.storage_phase && (
                  <span className="ml-2 text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full border border-gray-200">
                    {renderCodeValue(storage.storage_phase)}
                  </span>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={storage.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {storage.temperature && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Temperature</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(storage.temperature)}</span>
              </div>
            )}
            {storage.equipment_type && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Equipment Type</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(storage.equipment_type)}</span>
              </div>
            )}
            {storage.duration && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Duration</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(storage.duration)}</span>
              </div>
            )}
            {storage.stability_limit && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Stability Limit</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(storage.stability_limit)}</span>
              </div>
            )}
          </div>

          {/* Monitoring & Backup */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            {storage.monitoring_requirements && (
              <div className="p-2 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Monitoring Requirements</span>
                <p className="text-sm text-gray-900">{renderCodeValue(storage.monitoring_requirements)}</p>
              </div>
            )}
            {storage.backup_requirements && (
              <div className="p-2 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Backup Requirements</span>
                <p className="text-sm text-gray-900">{renderCodeValue(storage.backup_requirements)}</p>
              </div>
            )}
          </div>

          {storage.excursion_limits && (
            <div className="mt-3 p-2 bg-red-50 rounded-lg border border-red-200">
              <span className="text-xs font-medium text-red-700 uppercase tracking-wider block mb-1">Excursion Limits</span>
              <p className="text-sm text-gray-900">{renderCodeValue(storage.excursion_limits)}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// Shipping Requirements Tab
function ShippingTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const shippingReqs = Array.isArray(data?.shipping_requirements)
    ? data.shipping_requirements
    : data?.shipping_requirements ? [data.shipping_requirements] : [];

  if (shippingReqs.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Truck className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No shipping requirements defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {shippingReqs.map((shipping: any, idx: number) => (
        <div key={shipping.shipping_id || idx} className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
                <Truck className="w-5 h-5 text-gray-900" />
              </div>
              <div>
                <span className="font-medium text-foreground">{renderCodeValue(shipping.specimen_type) || renderCodeValue(shipping.specimen_ref) || `Shipping ${idx + 1}`}</span>
              </div>
            </div>
            <ProvenanceChip provenance={shipping.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {shipping.origin_description && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Origin</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(shipping.origin_description)}</span>
              </div>
            )}
            {shipping.destination && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Destination</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(shipping.destination)}</span>
              </div>
            )}
            {shipping.shipping_frequency && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Frequency</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(shipping.shipping_frequency)}</span>
              </div>
            )}
            {shipping.temperature && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Temperature</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(shipping.temperature)}</span>
              </div>
            )}
            {shipping.temperature_monitor && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Temp Monitor</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(shipping.temperature_monitor)}</span>
              </div>
            )}
            {shipping.courier_requirements && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Courier</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(shipping.courier_requirements)}</span>
              </div>
            )}
            {shipping.un_classification && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">UN Classification</span>
                <span className="text-sm font-medium text-gray-900">{renderCodeValue(shipping.un_classification)}</span>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            {shipping.packaging_requirements && (
              <div className="p-2 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Packaging</span>
                <p className="text-sm text-gray-900">{renderCodeValue(shipping.packaging_requirements)}</p>
              </div>
            )}
            {shipping.manifest_requirements && (
              <div className="p-2 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Manifest Requirements</span>
                <p className="text-sm text-gray-900">{renderCodeValue(shipping.manifest_requirements)}</p>
              </div>
            )}
            {shipping.customs_requirements && (
              <div className="p-2 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Customs Requirements</span>
                <p className="text-sm text-gray-900">{renderCodeValue(shipping.customs_requirements)}</p>
              </div>
            )}
            {shipping.contingency_procedures && (
              <div className="p-2 bg-yellow-50 rounded-lg border border-yellow-200">
                <span className="text-xs font-medium text-yellow-700 uppercase tracking-wider block mb-1">Contingency Procedures</span>
                <p className="text-sm text-gray-900">{renderCodeValue(shipping.contingency_procedures)}</p>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// Kit Specifications Tab
function KitsTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const kitSpecs = data?.kit_specifications;

  if (!kitSpecs) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Boxes className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No kit specifications defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
            <Boxes className="w-5 h-5 text-gray-600" />
          </div>
          <h4 className="font-semibold text-foreground">Kit Specifications</h4>
          <ProvenanceChip provenance={kitSpecs.provenance} onViewSource={onViewSource} />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {kitSpecs.kit_provider && (
            <div className="bg-gray-50 rounded-lg p-3">
              <span className="text-xs text-gray-500 block">Kit Provider</span>
              <span className="text-sm font-medium text-gray-900">{kitSpecs.kit_provider}</span>
            </div>
          )}
          {kitSpecs.barcode_format && (
            <div className="bg-gray-50 rounded-lg p-3">
              <span className="text-xs text-gray-500 block">Barcode Format</span>
              <span className="text-sm font-medium text-gray-900">{kitSpecs.barcode_format}</span>
            </div>
          )}
          {kitSpecs.kit_ordering && (
            <div className="bg-gray-50 rounded-lg p-3">
              <span className="text-xs text-gray-500 block">Kit Ordering</span>
              <span className="text-sm font-medium text-gray-900">{kitSpecs.kit_ordering}</span>
            </div>
          )}
        </div>

        {kitSpecs.kit_components?.length > 0 && (
          <div className="mt-4">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-2">Kit Components</span>
            <div className="flex flex-wrap gap-2">
              {kitSpecs.kit_components.map((component: string, idx: number) => (
                <span key={idx} className="px-3 py-1 bg-gray-50 text-gray-800 text-sm rounded-full border border-gray-200">
                  {component}
                </span>
              ))}
            </div>
          </div>
        )}

        {kitSpecs.labeling_requirements && (
          <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Labeling Requirements</span>
            <p className="text-sm text-gray-900">{kitSpecs.labeling_requirements}</p>
          </div>
        )}

        {kitSpecs.label_content && (
          <div className="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Label Content</span>
            <p className="text-sm text-gray-900">{kitSpecs.label_content}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// Quality Requirements Tab
function QualityTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const qualityReqs = data?.quality_requirements;

  if (!qualityReqs) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No quality requirements defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
            <Shield className="w-5 h-5 text-gray-600" />
          </div>
          <h4 className="font-semibold text-foreground">Quality Requirements</h4>
          <ProvenanceChip provenance={qualityReqs.provenance} onViewSource={onViewSource} />
        </div>

        <div className="space-y-4">
          {qualityReqs.acceptance_criteria && (
            <div className="p-3 bg-green-50 rounded-lg border border-green-200">
              <span className="text-xs font-medium text-green-700 uppercase tracking-wider block mb-1">Acceptance Criteria</span>
              <p className="text-sm text-gray-900">{qualityReqs.acceptance_criteria}</p>
            </div>
          )}

          {qualityReqs.rejection_criteria && (
            <div className="p-3 bg-red-50 rounded-lg border border-red-200">
              <span className="text-xs font-medium text-red-700 uppercase tracking-wider block mb-1">Rejection Criteria</span>
              <p className="text-sm text-gray-900">{qualityReqs.rejection_criteria}</p>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {qualityReqs.minimum_volume && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Minimum Volume</span>
                <span className="text-sm font-medium text-gray-900">{qualityReqs.minimum_volume}</span>
              </div>
            )}
            {qualityReqs.chain_of_custody && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Chain of Custody</span>
                <span className="text-sm font-medium text-gray-900">{qualityReqs.chain_of_custody}</span>
              </div>
            )}
          </div>

          {qualityReqs.documentation_requirements && (
            <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Documentation Requirements</span>
              <p className="text-sm text-gray-900">{qualityReqs.documentation_requirements}</p>
            </div>
          )}

          {qualityReqs.quality_metrics && (
            <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-1">Quality Metrics</span>
              <p className="text-sm text-gray-900">{qualityReqs.quality_metrics}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Regulatory Requirements Tab
function RegulatoryTab({ data, onViewSource }: { data: any; onViewSource?: (page: number) => void }) {
  const regulatoryReqs = data?.regulatory_requirements;

  if (!regulatoryReqs) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <FileCheck className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No regulatory requirements defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
            <FileCheck className="w-5 h-5 text-gray-600" />
          </div>
          <h4 className="font-semibold text-foreground">Regulatory Requirements</h4>
          <ProvenanceChip provenance={regulatoryReqs.provenance} onViewSource={onViewSource} />
        </div>

        <div className="space-y-4">
          {/* Consent Requirements */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {regulatoryReqs.informed_consent_requirements && (
              <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Informed Consent</span>
                <p className="text-sm text-gray-900">{regulatoryReqs.informed_consent_requirements}</p>
              </div>
            )}
            {regulatoryReqs.genetic_consent && (
              <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-1">Genetic Consent</span>
                <p className="text-sm text-gray-900">{regulatoryReqs.genetic_consent}</p>
              </div>
            )}
            {regulatoryReqs.future_use_consent && (
              <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-1">Future Use Consent</span>
                <p className="text-sm text-gray-900">{regulatoryReqs.future_use_consent}</p>
              </div>
            )}
          </div>

          {/* Privacy & Export */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {regulatoryReqs.privacy_requirements && (
              <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Privacy Requirements</span>
                <p className="text-sm text-gray-900">{regulatoryReqs.privacy_requirements}</p>
              </div>
            )}
            {regulatoryReqs.export_requirements && (
              <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Export Requirements</span>
                <p className="text-sm text-gray-900">{regulatoryReqs.export_requirements}</p>
              </div>
            )}
          </div>

          {/* Retention & Destruction */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {regulatoryReqs.retention_period && (
              <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-1">Retention Period</span>
                <p className="text-sm text-gray-900">{regulatoryReqs.retention_period}</p>
              </div>
            )}
            {regulatoryReqs.destruction_procedures && (
              <div className="p-3 bg-red-50 rounded-lg border border-red-200">
                <span className="text-xs font-medium text-red-700 uppercase tracking-wider block mb-1">Destruction Procedures</span>
                <p className="text-sm text-gray-900">{regulatoryReqs.destruction_procedures}</p>
              </div>
            )}
          </div>

          {regulatoryReqs.withdrawal_procedures && (
            <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Withdrawal Procedures</span>
              <p className="text-sm text-gray-900">{regulatoryReqs.withdrawal_procedures}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function BiospecimenViewContent({ data, onViewSource, onFieldUpdate }: BiospecimenViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  // Count storage and shipping items (handle both array and object formats)
  const storageCount = Array.isArray(data.storage_requirements)
    ? data.storage_requirements.length
    : data.storage_requirements ? 1 : 0;
  const shippingCount = Array.isArray(data.shipping_requirements)
    ? data.shipping_requirements.length
    : data.shipping_requirements ? 1 : 0;

  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: LayoutGrid },
    { id: "specimens", label: "Specimens", icon: FlaskConical, count: data.discovered_specimen_types?.length || 0 },
    { id: "containers", label: "Containers", icon: TestTube, count: data.collection_containers?.length || 0 },
    { id: "schedule", label: "Schedule", icon: Calendar, count: data.collection_schedule?.length || 0 },
    { id: "processing", label: "Processing", icon: Settings, count: data.processing_requirements?.length || 0 },
    { id: "storage", label: "Storage", icon: Thermometer, count: storageCount },
    { id: "shipping", label: "Shipping", icon: Truck, count: shippingCount },
    { id: "kits", label: "Kits", icon: Boxes, count: data.kit_specifications ? 1 : 0 },
    { id: "quality", label: "Quality", icon: Shield, count: data.quality_requirements ? 1 : 0 },
    { id: "regulatory", label: "Regulatory", icon: FileCheck, count: data.regulatory_requirements ? 1 : 0 },
  ];
  
  return (
    <div className="space-y-6" data-testid="biospecimen-view">
      <SummaryHeader data={data} />
      
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
          {activeTab === "specimens" && <SpecimensTab data={data} onViewSource={onViewSource} />}
          {activeTab === "containers" && <ContainersTab data={data} onViewSource={onViewSource} />}
          {activeTab === "schedule" && <ScheduleTab data={data} onViewSource={onViewSource} />}
          {activeTab === "processing" && <ProcessingTab data={data} onViewSource={onViewSource} />}
          {activeTab === "storage" && <StorageTab data={data} onViewSource={onViewSource} />}
          {activeTab === "shipping" && <ShippingTab data={data} onViewSource={onViewSource} />}
          {activeTab === "kits" && <KitsTab data={data} onViewSource={onViewSource} />}
          {activeTab === "quality" && <QualityTab data={data} onViewSource={onViewSource} />}
          {activeTab === "regulatory" && <RegulatoryTab data={data} onViewSource={onViewSource} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function BiospecimenView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: BiospecimenViewProps) {
  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Droplets className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No biospecimen data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <BiospecimenViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
