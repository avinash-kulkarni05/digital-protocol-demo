import { useState } from "react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, ChevronDown, FlaskConical, ClipboardCheck, Building2, Award,
  Layers, TestTube, Calendar, Clock, Beaker, AlertTriangle, Scale,
  Heart, Activity, Dna, Droplets, Settings, AlertCircle, Hash, Shield
} from "lucide-react";
import { SmartDataRender } from "./SmartDataRender";
import { AgentInsightsHeader } from "./AgentInsightsHeader";
import { ProvenanceChip } from "@/components/ui/ProvenanceChip";
import { extractProvenance } from "@/lib/provenance-utils";
import { EditableText } from "./EditableValue";

interface LabSpecsViewProps {
  data: any;
  onViewSource?: (page: number) => void;
  onFieldUpdate?: (path: string, value: any) => void;
  agentDoc?: any;
  qualityScore?: number;
}

type TabId = "overview" | "central_lab" | "panels" | "tests" | "schedule" | "dose_mods" | "eligibility" | "critical_values" | "pregnancy" | "pk_biomarkers";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ElementType;
  count?: number;
}

// ProvenanceChip is now imported from @/components/ui/ProvenanceChip

function AccordionSection({ title, icon: Icon, children, defaultOpen = false, count }: { title: string; icon: React.ElementType; children: React.ReactNode; defaultOpen?: boolean; count?: number; }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white">
      <button type="button" onClick={() => setIsOpen(!isOpen)} className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors text-left">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center"><Icon className="w-4 h-4 text-gray-900" /></div>
          <span className="font-semibold text-foreground">{title}</span>
          {count !== undefined && <span className="text-xs text-muted-foreground bg-gray-100 px-2 py-0.5 rounded-full">{count}</span>}
        </div>
        <motion.div animate={{ rotate: isOpen ? 180 : 0 }} transition={{ duration: 0.2 }}><ChevronDown className="w-5 h-5 text-gray-400" /></motion.div>
      </button>
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}>
            <div className="p-4 pt-0 border-t border-gray-100">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SummaryHeader({ data }: { data: any }) {
  const panelCount = data?.discovered_panels?.length || 0;
  const vendorName = data?.central_laboratory?.vendor_name || "Not specified";
  return (
    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-6 mb-6 border border-gray-200" data-testid="lab-specs-header">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center shadow-md">
          <FlaskConical className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-lg text-foreground">Laboratory Specifications</h3>
          <p className="text-sm text-muted-foreground">Central lab and test panels</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><Building2 className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Central Lab</span></div>
          <p className="text-lg font-bold text-gray-900 truncate">{vendorName}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 mb-1"><ClipboardCheck className="w-4 h-4 text-gray-600" /><span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Test Panels</span></div>
          <p className="text-2xl font-bold text-gray-900">{panelCount}</p>
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const panelCount = data?.discovered_panels?.length || 0;
  const vendorName = data?.central_laboratory?.vendor_name || "Not specified";
  const hasEligibilityCriteria = !!data?.eligibility_lab_criteria;

  return (
    <div className="space-y-6">
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Layers className="w-5 h-5 text-gray-600" />
            Laboratory Overview
          </h4>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <Building2 className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-sm font-bold text-gray-900 truncate">{vendorName}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Central Lab</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <ClipboardCheck className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-2xl font-bold text-gray-900">{panelCount}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Test Panels</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <TestTube className="w-6 h-6 text-gray-600 mx-auto mb-2" />
              <p className="text-lg font-bold text-gray-900">{hasEligibilityCriteria ? "Yes" : "No"}</p>
              <p className="text-xs text-gray-900 font-medium uppercase tracking-wider">Eligibility Criteria</p>
            </div>
          </div>
        </div>
      </div>
      
      {data.eligibility_lab_criteria && (
        <AccordionSection title="Eligibility Lab Criteria" icon={FlaskConical}>
          <SmartDataRender data={data.eligibility_lab_criteria} onViewSource={onViewSource} />
        </AccordionSection>
      )}
    </div>
  );
}

function CentralLabTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  if (!data.central_laboratory) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Building2 className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No central laboratory information available</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center flex-shrink-0 shadow-md">
            <Building2 className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h4 className="font-bold text-gray-900 text-lg">Central Laboratory</h4>
              <ProvenanceChip provenance={data.central_laboratory.provenance} onViewSource={onViewSource} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {data.central_laboratory.vendor_name && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Vendor</span>
                  <span className="font-semibold text-gray-900">
                    <EditableText
                      value={data.central_laboratory.vendor_name}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.laboratorySpecifications.data.central_laboratory.vendor_name", v) : undefined}
                    />
                  </span>
                </div>
              )}
              {data.central_laboratory.data_transfer_method && (
                <div className="bg-white/70 rounded-lg p-3 border border-gray-200">
                  <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-1">Data Transfer</span>
                  <span className="font-semibold text-gray-900">
                    <EditableText
                      value={data.central_laboratory.data_transfer_method}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate("domainSections.laboratorySpecifications.data.central_laboratory.data_transfer_method", v) : undefined}
                    />
                  </span>
                </div>
              )}
            </div>
            {data.central_laboratory.accreditations?.length > 0 && (
              <div className="mt-3">
                <span className="text-xs font-medium text-gray-900 uppercase tracking-wider block mb-2">Accreditations</span>
                <div className="flex flex-wrap gap-2">
                  {data.central_laboratory.accreditations.map((acc: string, idx: number) => (
                    <span key={idx} className="text-xs bg-white/70 text-gray-700 px-3 py-1.5 rounded-full border border-gray-200 font-medium flex items-center gap-1">
                      <Award className="w-3 h-3" /> {acc}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function PanelCard({ panel, idx, onViewSource, onFieldUpdate }: { panel: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const tests = panel.tests || panel.panel_details?.tests || [];
  const basePath = `domainSections.laboratorySpecifications.data.discovered_panels.${idx}`;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
            <ClipboardCheck className="w-5 h-5 text-gray-600" />
          </div>
          <div className="text-left">
            <span className="font-semibold text-foreground">
              <EditableText
                value={panel.panel_name || ""}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.panel_name`, v) : undefined}
              />
            </span>
            {panel.panel_code && (
              <p className="text-xs text-muted-foreground">
                LOINC: <EditableText
                  value={panel.panel_code || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.panel_code`, v) : undefined}
                />
              </p>
            )}
            <p className="text-sm text-muted-foreground">{panel.test_count || tests.length} tests</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {panel.panel_category && (
            <span className="text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full border border-gray-200">
              <EditableText
                value={panel.panel_category || ""}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.panel_category`, v) : undefined}
              />
            </span>
          )}
          <ProvenanceChip provenance={panel.provenance} onViewSource={onViewSource} />
          <motion.div animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
            <ChevronDown className="w-5 h-5 text-gray-400" />
          </motion.div>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="px-4 pb-4 border-t border-gray-100 pt-3 space-y-4">
              {/* Biomedical Concept */}
              {panel.biomedicalConcept && (
                <div className="p-2 bg-gray-50 rounded-lg border border-gray-200">
                  <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-1">CDISC Biomedical Concept</span>
                  <div className="flex flex-wrap gap-2 text-xs">
                    {panel.biomedicalConcept.code && (
                      <span className="bg-white px-2 py-1 rounded border border-gray-200">Code: {panel.biomedicalConcept.code}</span>
                    )}
                    {panel.biomedicalConcept.decode && (
                      <span className="bg-white px-2 py-1 rounded border border-gray-200">{panel.biomedicalConcept.decode}</span>
                    )}
                  </div>
                </div>
              )}
              <SmartDataRender
                data={panel}
                onViewSource={onViewSource}
                excludeFields={["panel_name", "panel_code", "panel_category", "provenance", "biomedicalConcept", "test_count"]}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function PanelsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const panels = data.discovered_panels || [];

  if (panels.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <ClipboardCheck className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No laboratory panels defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {panels.map((panel: any, idx: number) => (
        <PanelCard key={panel.id || idx} panel={panel} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function TestCard({ test, idx, onViewSource, onFieldUpdate }: { test: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const basePath = `domainSections.laboratorySpecifications.data.laboratory_tests.${idx}`;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden" data-testid={`test-card-${test.test_id || test.id}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
            <Beaker className="w-5 h-5 text-gray-600" />
          </div>
          <div className="text-left">
            <span className="font-semibold text-foreground">
              <EditableText
                value={test.test_name || test.name || `Test ${test.test_id || test.id}`}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.test_name`, v) : undefined}
              />
            </span>
            {test.test_code && (
              <p className="text-sm text-muted-foreground">
                LOINC: <EditableText
                  value={test.test_code || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.test_code`, v) : undefined}
                />
              </p>
            )}
            {test.panel_ref && (
              <p className="text-xs text-gray-500">
                Panel: <EditableText
                  value={test.panel_ref || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.panel_ref`, v) : undefined}
                />
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {test.fasting_required && (
            <span className="text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full border border-gray-200">Fasting</span>
          )}
          <ProvenanceChip provenance={test.provenance} onViewSource={onViewSource} />
          <motion.div animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
            <ChevronDown className="w-5 h-5 text-gray-400" />
          </motion.div>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="px-4 pb-4 border-t border-gray-100 pt-3 space-y-4">
              {/* Collection Details */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {test.collection_container && (
                  <div className="bg-gray-50 rounded-lg p-2">
                    <span className="text-xs text-gray-500 block">Container</span>
                    <span className="text-sm font-medium text-gray-900">
                      <EditableText
                        value={test.collection_container || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.collection_container`, v) : undefined}
                      />
                    </span>
                  </div>
                )}
                {test.collection_volume && (
                  <div className="bg-gray-50 rounded-lg p-2">
                    <span className="text-xs text-gray-500 block">Volume</span>
                    <span className="text-sm font-medium text-gray-900">
                      <EditableText
                        value={test.collection_volume || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.collection_volume`, v) : undefined}
                      />
                    </span>
                  </div>
                )}
                {test.special_handling && (
                  <div className="bg-gray-50 rounded-lg p-2 col-span-2">
                    <span className="text-xs text-gray-500 block">Special Handling</span>
                    <span className="text-sm font-medium text-gray-900">
                      <EditableText
                        value={test.special_handling || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.special_handling`, v) : undefined}
                      />
                    </span>
                  </div>
                )}
              </div>

              {/* Reference Ranges */}
              {test.reference_ranges?.length > 0 && (
                <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                  <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-2">Reference Ranges</span>
                  <div className="space-y-2">
                    {test.reference_ranges.map((range: any, rIdx: number) => (
                      <div key={rIdx} className="flex items-center gap-3 text-sm">
                        {range.population && (
                          <span className="text-gray-500">
                            <EditableText
                              value={range.population || ""}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.reference_ranges.${rIdx}.population`, v) : undefined}
                            />:
                          </span>
                        )}
                        <span className="font-medium text-gray-900">
                          {range.low !== undefined && range.high !== undefined
                            ? `${range.low} - ${range.high}`
                            : (
                              <EditableText
                                value={range.text || "N/A"}
                                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.reference_ranges.${rIdx}.text`, v) : undefined}
                              />
                            )}
                          {range.unit && (
                            <> <EditableText
                              value={range.unit || ""}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.reference_ranges.${rIdx}.unit`, v) : undefined}
                            /></>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Critical Values */}
              {test.critical_values?.length > 0 && (
                <div className="p-3 bg-red-50 rounded-lg border border-red-200">
                  <span className="text-xs font-medium text-red-700 uppercase tracking-wider block mb-2">Critical Values</span>
                  <div className="space-y-2">
                    {test.critical_values.map((cv: any, cvIdx: number) => (
                      <div key={cvIdx} className="flex items-center justify-between text-sm">
                        <span className="text-gray-700">
                          <EditableText
                            value={cv.type || ""}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.critical_values.${cvIdx}.type`, v) : undefined}
                          />: <EditableText
                            value={cv.value || ""}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.critical_values.${cvIdx}.value`, v) : undefined}
                          /> <EditableText
                            value={cv.unit || ""}
                            onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.critical_values.${cvIdx}.unit`, v) : undefined}
                          />
                        </span>
                        {cv.action_required && (
                          <span className="text-xs bg-red-100 text-red-800 px-2 py-0.5 rounded">
                            <EditableText
                              value={cv.action_required || ""}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.critical_values.${cvIdx}.action_required`, v) : undefined}
                            />
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Clinical Significance */}
              {test.clinical_significance && (
                <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                  <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Clinical Significance</span>
                  <p className="text-sm text-gray-900">
                    <EditableText
                      value={test.clinical_significance || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.clinical_significance`, v) : undefined}
                    />
                  </p>
                </div>
              )}

              {/* Biomedical Concept */}
              {test.biomedicalConcept && (
                <div className="p-2 bg-gray-50 rounded-lg border border-gray-200">
                  <span className="text-xs font-medium text-gray-700 uppercase tracking-wider block mb-1">CDISC Biomedical Concept</span>
                  <div className="flex flex-wrap gap-2 text-xs">
                    {test.biomedicalConcept.code && (
                      <span className="bg-white px-2 py-1 rounded border border-gray-200">
                        Code: <EditableText
                          value={test.biomedicalConcept.code || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.biomedicalConcept.code`, v) : undefined}
                        />
                      </span>
                    )}
                    {test.biomedicalConcept.decode && (
                      <span className="bg-white px-2 py-1 rounded border border-gray-200">
                        <EditableText
                          value={test.biomedicalConcept.decode || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.biomedicalConcept.decode`, v) : undefined}
                        />
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Remaining Fields */}
              <SmartDataRender
                data={test}
                onViewSource={onViewSource}
                excludeFields={["test_name", "name", "test_id", "id", "test_code", "panel_ref", "provenance", "fasting_required", "collection_container", "collection_volume", "special_handling", "reference_ranges", "critical_values", "clinical_significance", "biomedicalConcept"]}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function TestsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const tests = data.laboratory_tests || [];

  if (tests.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Beaker className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No laboratory tests defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="tests-tab-content">
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 mb-4">
        <p className="text-sm text-gray-800">
          <strong>{tests.length}</strong> laboratory tests defined with panel references and specifications.
        </p>
      </div>
      {tests.map((test: any, idx: number) => (
        <TestCard key={test.test_id || test.id || idx} test={test} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

function ScheduleCard({ schedule, idx, onViewSource, onFieldUpdate }: { schedule: any; idx: number; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const timepoints = schedule.timepoints || [];
  const basePath = `domainSections.laboratorySpecifications.data.testing_schedule.${idx}`;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden" data-testid={`schedule-card-${schedule.schedule_id || schedule.id}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
            <Calendar className="w-5 h-5 text-gray-800" />
          </div>
          <div className="text-left">
            <span className="font-semibold text-foreground">
              <EditableText
                value={schedule.schedule_id || `Schedule ${schedule.id}`}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.schedule_id`, v) : undefined}
              />
            </span>
            {schedule.test_or_panel_ref && (
              <p className="text-sm text-gray-800">
                Panel: <EditableText
                  value={schedule.test_or_panel_ref || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.test_or_panel_ref`, v) : undefined}
                />
              </p>
            )}
            <p className="text-sm text-muted-foreground">{timepoints.length} timepoints</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceChip provenance={schedule.provenance} onViewSource={onViewSource} />
          <motion.div animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
            <ChevronDown className="w-5 h-5 text-gray-400" />
          </motion.div>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="px-4 pb-4 border-t border-gray-100 pt-3 space-y-4">
              {timepoints.length > 0 && (
                <div className="space-y-2">
                  <h5 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                    <Clock className="w-4 h-4" /> Timepoints
                  </h5>
                  <div className="grid gap-2">
                    {timepoints.map((tp: any, tpIdx: number) => (
                      <div key={tpIdx} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium text-gray-900">
                            <EditableText
                              value={tp.timepoint_name || ""}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.timepoints.${tpIdx}.timepoint_name`, v) : undefined}
                            />
                          </span>
                          {tp.timepoint_type && (
                            <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">
                              <EditableText
                                value={tp.timepoint_type || ""}
                                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.timepoints.${tpIdx}.timepoint_type`, v) : undefined}
                              />
                            </span>
                          )}
                        </div>
                        {tp.window && (
                          <p className="text-sm text-gray-600">
                            Window: <EditableText
                              value={tp.window || ""}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.timepoints.${tpIdx}.window`, v) : undefined}
                            />
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="pt-2 border-t border-gray-200">
                <SmartDataRender data={schedule} onViewSource={onViewSource} />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ScheduleTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const schedules = data.testing_schedule || [];

  if (schedules.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Calendar className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No testing schedule defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="schedule-tab-content">
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 mb-4">
        <p className="text-sm text-gray-800">
          <strong>{schedules.length}</strong> testing schedules with timepoint definitions and panel references.
        </p>
      </div>
      {schedules.map((schedule: any, idx: number) => (
        <ScheduleCard key={schedule.schedule_id || schedule.id || idx} schedule={schedule} idx={idx} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
      ))}
    </div>
  );
}

// Lab-Based Dose Modifications Tab
function DoseModsTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const modifications = data?.lab_based_dose_modifications || [];
  const basePath = "domainSections.laboratorySpecifications.data.lab_based_dose_modifications";

  if (modifications.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Scale className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No lab-based dose modifications defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 mb-4">
        <p className="text-sm text-gray-800">
          <strong>{modifications.length}</strong> lab-based dose modification rules defined.
        </p>
      </div>
      {modifications.map((mod: any, idx: number) => (
        <div key={mod.modification_id || idx} className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
                <Scale className="w-5 h-5 text-gray-600" />
              </div>
              <div>
                <span className="font-medium text-foreground">
                  <EditableText
                    value={mod.parameter_name || mod.modification_id || `Modification ${idx + 1}`}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.parameter_name`, v) : undefined}
                  />
                </span>
                {mod.reference_type && (
                  <span className="ml-2 text-xs bg-gray-50 text-gray-700 px-2 py-0.5 rounded-full border border-gray-200">
                    <EditableText
                      value={mod.reference_type || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.reference_type`, v) : undefined}
                    />
                  </span>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={mod.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {mod.trigger_condition && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Trigger Condition</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={mod.trigger_condition || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.trigger_condition`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {mod.operator && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Operator</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={mod.operator || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.operator`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {mod.threshold_value !== undefined && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Threshold</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={String(mod.threshold_value) || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.threshold_value`, v) : undefined}
                  /> <EditableText
                    value={mod.threshold_unit || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.threshold_unit`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>

          {mod.required_action && (
            <div className="mt-3 p-3 bg-red-50 rounded-lg border border-red-200">
              <span className="text-xs font-medium text-red-700 uppercase tracking-wider block mb-1">Required Action</span>
              <p className="text-sm text-gray-900">
                <EditableText
                  value={mod.required_action || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.required_action`, v) : undefined}
                />
              </p>
            </div>
          )}

          {mod.recovery_criteria && (
            <div className="mt-3 p-3 bg-green-50 rounded-lg border border-green-200">
              <span className="text-xs font-medium text-green-700 uppercase tracking-wider block mb-1">Recovery Criteria</span>
              <p className="text-sm text-gray-900">
                <EditableText
                  value={mod.recovery_criteria || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.recovery_criteria`, v) : undefined}
                />
              </p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// Eligibility Lab Criteria Tab
function EligibilityTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const criteria = data?.eligibility_lab_criteria || [];
  const basePath = "domainSections.laboratorySpecifications.data.eligibility_lab_criteria";

  if (criteria.length === 0 && !data?.eligibility_lab_criteria) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No eligibility lab criteria defined</p>
      </div>
    );
  }

  // Handle both array and object formats
  const criteriaList = Array.isArray(criteria) ? criteria : [criteria];

  return (
    <div className="space-y-4">
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 mb-4">
        <p className="text-sm text-gray-800">
          <strong>{criteriaList.length}</strong> eligibility lab criteria defining inclusion/exclusion requirements.
        </p>
      </div>
      {criteriaList.map((crit: any, idx: number) => (
        <div key={crit.criteria_id || idx} className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className={cn(
                "w-10 h-10 rounded-xl flex items-center justify-center",
                crit.criteria_type === "exclusion" ? "bg-red-100" : "bg-green-100"
              )}>
                <Shield className={cn(
                  "w-5 h-5",
                  crit.criteria_type === "exclusion" ? "text-red-600" : "text-green-600"
                )} />
              </div>
              <div>
                <span className="font-medium text-foreground">
                  <EditableText
                    value={crit.parameter_name || crit.criteria_id || `Criteria ${idx + 1}`}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.parameter_name`, v) : undefined}
                  />
                </span>
                {crit.criteria_type && (
                  <span className={cn(
                    "ml-2 text-xs px-2 py-0.5 rounded-full border",
                    crit.criteria_type === "exclusion"
                      ? "bg-red-50 text-red-700 border-red-200"
                      : "bg-green-50 text-green-700 border-green-200"
                  )}>
                    <EditableText
                      value={crit.criteria_type || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.criteria_type`, v) : undefined}
                    />
                  </span>
                )}
              </div>
            </div>
            <ProvenanceChip provenance={crit.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {crit.condition && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Condition</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={crit.condition || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.condition`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {crit.operator && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Operator</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={crit.operator || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.operator`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {crit.threshold_value !== undefined && (
              <div className="bg-gray-50 rounded-lg p-2">
                <span className="text-xs text-gray-500 block">Threshold</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={String(crit.threshold_value) || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.threshold_value`, v) : undefined}
                  /> <EditableText
                    value={crit.threshold_unit || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.${idx}.threshold_unit`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// Critical Value Reporting Tab
function CriticalValuesTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const criticalReporting = data?.critical_value_reporting;
  const abnormalGrading = data?.abnormal_result_grading;
  const criticalBasePath = "domainSections.laboratorySpecifications.data.critical_value_reporting";
  const abnormalBasePath = "domainSections.laboratorySpecifications.data.abnormal_result_grading";

  if (!criticalReporting && !abnormalGrading) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No critical value reporting defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Critical Value Reporting */}
      {criticalReporting && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-red-100 rounded-xl flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-red-600" />
            </div>
            <h4 className="font-semibold text-foreground">Critical Value Reporting</h4>
            <ProvenanceChip provenance={criticalReporting.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
            {criticalReporting.notification_timeline && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Notification Timeline</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={criticalReporting.notification_timeline || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${criticalBasePath}.notification_timeline`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {criticalReporting.documentation_requirements && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Documentation</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={criticalReporting.documentation_requirements || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${criticalBasePath}.documentation_requirements`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>

          {criticalReporting.notification_recipients?.length > 0 && (
            <div className="mb-4">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-2">Notification Recipients</span>
              <div className="flex flex-wrap gap-2">
                {criticalReporting.notification_recipients.map((recipient: string, idx: number) => (
                  <span key={idx} className="px-3 py-1 bg-gray-100 text-gray-700 text-sm rounded-full border border-gray-200">
                    <EditableText
                      value={recipient || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${criticalBasePath}.notification_recipients.${idx}`, v) : undefined}
                    />
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Critical Value List */}
          {criticalReporting.critical_value_list?.length > 0 && (
            <div className="mt-4">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-2">Critical Value List</span>
              <div className="space-y-2">
                {criticalReporting.critical_value_list.map((cv: any, idx: number) => (
                  <div key={idx} className="bg-red-50 rounded-lg p-3 border border-red-200">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">
                        <EditableText
                          value={cv.parameter || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${criticalBasePath}.critical_value_list.${idx}.parameter`, v) : undefined}
                        />
                      </span>
                      <div className="flex items-center gap-2 text-sm">
                        {cv.critical_low !== undefined && (
                          <span className="text-gray-700">
                            Low: <EditableText
                              value={String(cv.critical_low) || ""}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${criticalBasePath}.critical_value_list.${idx}.critical_low`, v) : undefined}
                            /> <EditableText
                              value={cv.unit || ""}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${criticalBasePath}.critical_value_list.${idx}.unit`, v) : undefined}
                            />
                          </span>
                        )}
                        {cv.critical_high !== undefined && (
                          <span className="text-red-700">
                            High: <EditableText
                              value={String(cv.critical_high) || ""}
                              onSave={onFieldUpdate ? (v) => onFieldUpdate(`${criticalBasePath}.critical_value_list.${idx}.critical_high`, v) : undefined}
                            /> {cv.unit || ""}
                          </span>
                        )}
                      </div>
                    </div>
                    {cv.clinical_action && (
                      <p className="text-sm text-gray-600 mt-1">
                        <EditableText
                          value={cv.clinical_action || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${criticalBasePath}.critical_value_list.${idx}.clinical_action`, v) : undefined}
                        />
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Abnormal Result Grading */}
      {abnormalGrading && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
              <Activity className="w-5 h-5 text-gray-600" />
            </div>
            <h4 className="font-semibold text-foreground">Abnormal Result Grading</h4>
            <ProvenanceChip provenance={abnormalGrading.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {abnormalGrading.grading_system && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Grading System</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={abnormalGrading.grading_system || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${abnormalBasePath}.grading_system`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {abnormalGrading.grading_version && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Version</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={abnormalGrading.grading_version || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${abnormalBasePath}.grading_version`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {abnormalGrading.clinically_significant_threshold && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Clinically Significant Threshold</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={abnormalGrading.clinically_significant_threshold || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${abnormalBasePath}.clinically_significant_threshold`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {abnormalGrading.ae_reporting_threshold && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">AE Reporting Threshold</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={abnormalGrading.ae_reporting_threshold || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${abnormalBasePath}.ae_reporting_threshold`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Pregnancy Testing Tab
function PregnancyTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const pregnancy = data?.pregnancy_testing;
  const basePath = "domainSections.laboratorySpecifications.data.pregnancy_testing";

  if (!pregnancy) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Heart className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No pregnancy testing requirements defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
            <Heart className="w-5 h-5 text-gray-600" />
          </div>
          <h4 className="font-semibold text-foreground">Pregnancy Testing Requirements</h4>
          <ProvenanceChip provenance={pregnancy.provenance} onViewSource={onViewSource} />
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {pregnancy.required !== undefined && (
            <div className="bg-gray-50 rounded-lg p-3">
              <span className="text-xs text-gray-500 block">Required</span>
              <span className={cn("text-sm font-medium", pregnancy.required ? "text-green-700" : "text-gray-900")}>
                {pregnancy.required ? "Yes" : "No"}
              </span>
            </div>
          )}
          {pregnancy.applicable_population && (
            <div className="bg-gray-50 rounded-lg p-3">
              <span className="text-xs text-gray-500 block">Applicable Population</span>
              <span className="text-sm font-medium text-gray-900">
                <EditableText
                  value={pregnancy.applicable_population || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.applicable_population`, v) : undefined}
                />
              </span>
            </div>
          )}
          {pregnancy.test_type && (
            <div className="bg-gray-50 rounded-lg p-3">
              <span className="text-xs text-gray-500 block">Test Type</span>
              <span className="text-sm font-medium text-gray-900">
                <EditableText
                  value={pregnancy.test_type || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.test_type`, v) : undefined}
                />
              </span>
            </div>
          )}
          {pregnancy.timing && (
            <div className="bg-gray-50 rounded-lg p-3">
              <span className="text-xs text-gray-500 block">Timing</span>
              <span className="text-sm font-medium text-gray-900">
                <EditableText
                  value={pregnancy.timing || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.timing`, v) : undefined}
                />
              </span>
            </div>
          )}
          {pregnancy.sensitivity && (
            <div className="bg-gray-50 rounded-lg p-3">
              <span className="text-xs text-gray-500 block">Sensitivity</span>
              <span className="text-sm font-medium text-gray-900">
                <EditableText
                  value={pregnancy.sensitivity || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.sensitivity`, v) : undefined}
                />
              </span>
            </div>
          )}
        </div>

        {pregnancy.action_if_positive && (
          <div className="mt-4 p-3 bg-red-50 rounded-lg border border-red-200">
            <span className="text-xs font-medium text-red-700 uppercase tracking-wider block mb-1">Action if Positive</span>
            <p className="text-sm text-gray-900">
              <EditableText
                value={pregnancy.action_if_positive || ""}
                onSave={onFieldUpdate ? (v) => onFieldUpdate(`${basePath}.action_if_positive`, v) : undefined}
              />
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// PK & Biomarker Samples Tab
function PKBiomarkersTab({ data, onViewSource, onFieldUpdate }: { data: any; onViewSource?: (page: number) => void; onFieldUpdate?: (path: string, value: any) => void }) {
  const pkSamples = data?.pharmacokinetic_samples;
  const biomarkerSamples = data?.biomarker_samples;
  const localLabReqs = data?.local_lab_requirements;
  const sampleCollectionReqs = data?.sample_collection_requirements;
  const pkPath = "domainSections.laboratorySpecifications.data.pharmacokinetic_samples";
  const biomarkerPath = "domainSections.laboratorySpecifications.data.biomarker_samples";
  const localLabPath = "domainSections.laboratorySpecifications.data.local_lab_requirements";
  const sampleCollPath = "domainSections.laboratorySpecifications.data.sample_collection_requirements";

  if (!pkSamples && !biomarkerSamples && !localLabReqs && !sampleCollectionReqs) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Dna className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p>No PK/biomarker sampling defined</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Pharmacokinetic Samples */}
      {pkSamples && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
              <Activity className="w-5 h-5 text-gray-900" />
            </div>
            <h4 className="font-semibold text-foreground">Pharmacokinetic Samples</h4>
            <ProvenanceChip provenance={pkSamples.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {pkSamples.pk_sampling_required !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">PK Sampling Required</span>
                <span className={cn("text-sm font-medium", pkSamples.pk_sampling_required ? "text-green-700" : "text-gray-900")}>
                  {pkSamples.pk_sampling_required ? "Yes" : "No"}
                </span>
              </div>
            )}
            {pkSamples.sample_type && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Sample Type</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={pkSamples.sample_type || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${pkPath}.sample_type`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {pkSamples.volume_per_sample && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Volume/Sample</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={pkSamples.volume_per_sample || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${pkPath}.volume_per_sample`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>

          {pkSamples.analytes?.length > 0 && (
            <div className="mt-4">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-2">Analytes</span>
              <div className="flex flex-wrap gap-2">
                {pkSamples.analytes.map((analyte: string, idx: number) => (
                  <span key={idx} className="px-3 py-1 bg-gray-50 text-gray-700 text-sm rounded-full border border-gray-200">
                    <EditableText
                      value={analyte || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${pkPath}.analytes.${idx}`, v) : undefined}
                    />
                  </span>
                ))}
              </div>
            </div>
          )}

          {pkSamples.timepoints_description && (
            <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Timepoints</span>
              <p className="text-sm text-gray-900">
                <EditableText
                  value={pkSamples.timepoints_description || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${pkPath}.timepoints_description`, v) : undefined}
                />
              </p>
            </div>
          )}

          {pkSamples.processing_requirements && (
            <div className="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-1">Processing Requirements</span>
              <p className="text-sm text-gray-900">
                <EditableText
                  value={pkSamples.processing_requirements || ""}
                  onSave={onFieldUpdate ? (v) => onFieldUpdate(`${pkPath}.processing_requirements`, v) : undefined}
                />
              </p>
            </div>
          )}
        </div>
      )}

      {/* Biomarker Samples */}
      {biomarkerSamples && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
              <Dna className="w-5 h-5 text-gray-600" />
            </div>
            <h4 className="font-semibold text-foreground">Biomarker Samples</h4>
            <ProvenanceChip provenance={biomarkerSamples.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 gap-3 mb-4">
            {biomarkerSamples.biomarker_sampling_required !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Biomarker Sampling Required</span>
                <span className={cn("text-sm font-medium", biomarkerSamples.biomarker_sampling_required ? "text-green-700" : "text-gray-900")}>
                  {biomarkerSamples.biomarker_sampling_required ? "Yes" : "No"}
                </span>
              </div>
            )}
            {biomarkerSamples.optional_consent_required !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Optional Consent Required</span>
                <span className={cn("text-sm font-medium", biomarkerSamples.optional_consent_required ? "text-gray-700" : "text-gray-900")}>
                  {biomarkerSamples.optional_consent_required ? "Yes" : "No"}
                </span>
              </div>
            )}
          </div>

          {biomarkerSamples.biomarkers?.length > 0 && (
            <div className="space-y-2">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block">Biomarkers</span>
              {biomarkerSamples.biomarkers.map((bm: any, idx: number) => (
                <div key={idx} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-gray-900">
                      <EditableText
                        value={bm.name || ""}
                        onSave={onFieldUpdate ? (v) => onFieldUpdate(`${biomarkerPath}.biomarkers.${idx}.name`, v) : undefined}
                      />
                    </span>
                    {bm.purpose && (
                      <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                        <EditableText
                          value={bm.purpose || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${biomarkerPath}.biomarkers.${idx}.purpose`, v) : undefined}
                        />
                      </span>
                    )}
                  </div>
                  <div className="flex gap-4 text-sm text-gray-600">
                    {bm.sample_type && (
                      <span>
                        Sample: <EditableText
                          value={bm.sample_type || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${biomarkerPath}.biomarkers.${idx}.sample_type`, v) : undefined}
                        />
                      </span>
                    )}
                    {bm.timing && (
                      <span>
                        Timing: <EditableText
                          value={bm.timing || ""}
                          onSave={onFieldUpdate ? (v) => onFieldUpdate(`${biomarkerPath}.biomarkers.${idx}.timing`, v) : undefined}
                        />
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Local Lab Requirements */}
      {localLabReqs && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
              <Building2 className="w-5 h-5 text-gray-600" />
            </div>
            <h4 className="font-semibold text-foreground">Local Lab Requirements</h4>
            <ProvenanceChip provenance={localLabReqs.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            {localLabReqs.local_lab_allowed !== undefined && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Local Lab Allowed</span>
                <span className={cn("text-sm font-medium", localLabReqs.local_lab_allowed ? "text-green-700" : "text-red-700")}>
                  {localLabReqs.local_lab_allowed ? "Yes" : "No"}
                </span>
              </div>
            )}
            {localLabReqs.certification_requirements && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Certification</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={localLabReqs.certification_requirements || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${localLabPath}.certification_requirements`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>

          {localLabReqs.allowed_tests?.length > 0 && (
            <div className="mt-4">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider block mb-2">Allowed Tests</span>
              <div className="flex flex-wrap gap-2">
                {localLabReqs.allowed_tests.map((test: string, idx: number) => (
                  <span key={idx} className="px-3 py-1 bg-gray-100 text-gray-700 text-sm rounded-full border border-gray-200">
                    <EditableText
                      value={test || ""}
                      onSave={onFieldUpdate ? (v) => onFieldUpdate(`${localLabPath}.allowed_tests.${idx}`, v) : undefined}
                    />
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Sample Collection Requirements */}
      {sampleCollectionReqs && (
        <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
              <Droplets className="w-5 h-5 text-gray-600" />
            </div>
            <h4 className="font-semibold text-foreground">Sample Collection Requirements</h4>
            <ProvenanceChip provenance={sampleCollectionReqs.provenance} onViewSource={onViewSource} />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {sampleCollectionReqs.fasting_requirements && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Fasting Requirements</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={sampleCollectionReqs.fasting_requirements || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${sampleCollPath}.fasting_requirements`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {sampleCollectionReqs.timing_requirements && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Timing Requirements</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={sampleCollectionReqs.timing_requirements || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${sampleCollPath}.timing_requirements`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {sampleCollectionReqs.processing_requirements && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Processing Requirements</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={sampleCollectionReqs.processing_requirements || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${sampleCollPath}.processing_requirements`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {sampleCollectionReqs.storage_requirements && (
              <div className="bg-gray-50 rounded-lg p-3">
                <span className="text-xs text-gray-500 block">Storage Requirements</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={sampleCollectionReqs.storage_requirements || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${sampleCollPath}.storage_requirements`, v) : undefined}
                  />
                </span>
              </div>
            )}
            {sampleCollectionReqs.shipping_requirements && (
              <div className="bg-gray-50 rounded-lg p-3 col-span-2">
                <span className="text-xs text-gray-500 block">Shipping Requirements</span>
                <span className="text-sm font-medium text-gray-900">
                  <EditableText
                    value={sampleCollectionReqs.shipping_requirements || ""}
                    onSave={onFieldUpdate ? (v) => onFieldUpdate(`${sampleCollPath}.shipping_requirements`, v) : undefined}
                  />
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function LabSpecsViewContent({ data, onViewSource, onFieldUpdate }: LabSpecsViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  const panels = data.discovered_panels || [];
  const tests = data.laboratory_tests || [];
  const schedules = data.testing_schedule || [];
  const doseModifications = data.lab_based_dose_modifications || [];
  const eligibilityCriteria = data.eligibility_lab_criteria || [];

  const tabs: Tab[] = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "central_lab", label: "Central Lab", icon: Building2 },
    { id: "panels", label: "Panels", icon: ClipboardCheck, count: panels.length },
    { id: "tests", label: "Tests", icon: Beaker, count: tests.length },
    { id: "schedule", label: "Schedule", icon: Calendar, count: schedules.length },
    { id: "dose_mods", label: "Dose Mods", icon: Scale, count: doseModifications.length },
    { id: "eligibility", label: "Eligibility", icon: Shield, count: Array.isArray(eligibilityCriteria) ? eligibilityCriteria.length : (eligibilityCriteria ? 1 : 0) },
    { id: "critical_values", label: "Critical Values", icon: AlertTriangle, count: data.critical_value_reporting ? 1 : 0 },
    { id: "pregnancy", label: "Pregnancy", icon: Heart, count: data.pregnancy_testing ? 1 : 0 },
    { id: "pk_biomarkers", label: "PK/Biomarkers", icon: Dna, count: (data.pharmacokinetic_samples || data.biomarker_samples) ? 1 : 0 },
  ];
  
  return (
    <div className="space-y-6" data-testid="lab-specs-view">
      <SummaryHeader data={data} />
      
      <div className="bg-gray-100 p-1 rounded-xl flex gap-1 overflow-x-auto">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex-shrink-0 whitespace-nowrap flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200",
                activeTab === tab.id
                  ? "bg-white text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-gray-50"
              )}
              data-testid={`tab-${tab.id}`}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{tab.label}</span>
              {tab.count !== undefined && (
                <span className={cn(
                  "text-xs px-1.5 py-0.5 rounded-full",
                  activeTab === tab.id ? "bg-gray-100 text-gray-700" : "bg-gray-200 text-gray-600"
                )}>
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
          {activeTab === "central_lab" && <CentralLabTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "panels" && <PanelsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "tests" && <TestsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "schedule" && <ScheduleTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "dose_mods" && <DoseModsTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "eligibility" && <EligibilityTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "critical_values" && <CriticalValuesTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "pregnancy" && <PregnancyTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
          {activeTab === "pk_biomarkers" && <PKBiomarkersTab data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />}
        </motion.div>
      </AnimatePresence>
      
    </div>
  );
}

export function LabSpecsView({ data, onViewSource, onFieldUpdate, agentDoc, qualityScore }: LabSpecsViewProps) {
  if (!data) {
    return (<div className="text-center py-12 text-muted-foreground"><FlaskConical className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No laboratory data available</p></div>);
  }

  return (
    <div className="space-y-6">
      <AgentInsightsHeader agentDoc={agentDoc} qualityScore={qualityScore} />
      <LabSpecsViewContent data={data} onViewSource={onViewSource} onFieldUpdate={onFieldUpdate} />
    </div>
  );
}
