import { useState, useEffect, useReducer, useMemo, useCallback, useRef } from "react";
import { useSearch, useLocation } from "wouter";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  SelectGroup,
  SelectLabel,
} from "@/components/ui/select";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  ExternalLink,
  Maximize2,
  Minimize2,
  Table2,
  Calendar,
  ClipboardCheck,
  FileText,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  Merge,
  Split,
  Plus,
  Minus,
  Columns,
  Undo2,
  Redo2,
  Trash2,
  Download,
  ChevronDown,
  Edit2,
  FileWarning,
  Expand,
  Pencil,
  X,
} from "lucide-react";
import { api, getPdfUrl, type SOAJobStatus, type SOAPageInfo, type SOAPerTableResults, type SOATableResult, type MergePlan, type MergePlanConfirmation as MergePlanConfirmationType, type ClassificationReviewData, type ClassificationProfile } from "@/lib/api";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { MergePlanConfirmation } from "@/components/soa/MergePlanConfirmation";
import { ClassificationReview } from "@/components/soa/ClassificationReview";
import { SOACompletionSummary } from "@/components/soa/SOACompletionSummary";
import { InterpretationResultsView } from "@/components/soa/InterpretationResultsView";
import InsightsReviewShell from "@/pages/InsightsReviewShell";
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';
import type { SOAExtraction, SOATable, SOAActivity, SOAVisit } from "@shared/schema";
import { EditableText } from "@/components/review/EditableValue";
import { useDocument, useFieldUpdate } from "@/lib/queries";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  `pdfjs-dist/build/pdf.worker.min.mjs`,
  import.meta.url
).toString();

// Data URLs are now determined dynamically in the component based on studyId
const M14_031_EXTRACTION_URL = "/data/abbvie_NCT02755597_extraction_review_1765337157404.json";
const M14_031_USDM_URL = "/data/abbvie_NCT02755597_soa_usdm_draft_1765337167895.json";
const M14_359_EXTRACTION_URL = "/data/NCT02264990_M14-359_extraction_review_1765388805472.json";
const M14_359_USDM_URL = "/data/NCT02264990_M14-359_soa_usdm_draft_1765388805467.json";

const wizardSteps = [
  {
    id: "table_structure",
    title: "SOA Grid",
    description: "Review extracted table layout and structure",
    icon: Table2,
  },
  {
    id: "visits_activities",
    title: "Visits & Activities",
    description: "Review visits with their scheduled activities",
    icon: Calendar,
  },
  {
    id: "footnotes",
    title: "Footnotes",
    description: "Review footnote references and classifications",
    icon: FileText,
  },
];

// Compute grid highlights by comparing raw (pre-interpretation) vs interpreted USDM
interface ActivityExpansion {
  componentCount: number;
  components: { name: string; isRequired?: boolean; order?: number }[];
  confidence: number;
  source: string;
}

interface GridHighlights {
  newActivityIds: Set<string>;
  newVisitIds: Set<string>;
  expandedActivities: Map<string, ActivityExpansion>; // activityId -> expansion info
}

function computeGridHighlights(rawUsdm: any, interpretedTable: SOATable): GridHighlights {
  const result: GridHighlights = {
    newActivityIds: new Set(),
    newVisitIds: new Set(),
    expandedActivities: new Map(),
  };

  if (!rawUsdm) return result;

  // Detect activities with Stage 2 expansion metadata
  const interpActivities = Array.isArray(interpretedTable.activities) ? interpretedTable.activities : [];
  for (const activity of interpActivities) {
    const expansion = (activity as any)._expansion;
    if (expansion && expansion.componentCount > 0) {
      result.expandedActivities.set(activity.id, {
        componentCount: expansion.componentCount,
        components: (expansion.components || []).map((c: any) => ({
          name: c.name || c.displayName || 'Unknown',
          isRequired: c.isRequired,
          order: c.order,
        })),
        confidence: expansion.confidence || 0,
        source: expansion.source || '',
      });
    }
  }

  // Build sets of raw activity and visit IDs
  const rawActivities = rawUsdm.activities || [];
  const rawVisits = rawUsdm.visits || rawUsdm.encounters || [];
  const rawActivityIds = new Set(rawActivities.map((a: any) => a.id));
  const rawVisitIds = new Set(rawVisits.map((v: any) => v.id));

  // Find new activities (in interpreted but not in raw)
  for (const activity of interpActivities) {
    if (!rawActivityIds.has(activity.id)) {
      result.newActivityIds.add(activity.id);
    }
  }

  // Find new visits (in interpreted but not in raw)
  const interpVisits = Array.isArray(interpretedTable.visits) ? interpretedTable.visits : [];
  for (const visit of interpVisits) {
    if (!rawVisitIds.has(visit.id)) {
      result.newVisitIds.add(visit.id);
    }
  }

  return result;
}

// Helper to group consecutive visits by parentVisit for multi-row headers
const computeVisitGroups = (visits: any[]) => {
  const hasGroups = visits.some(v => v.parentVisit);
  if (!hasGroups) return null;

  const groups: { label: string; colSpan: number; startIdx: number }[] = [];
  let i = 0;
  while (i < visits.length) {
    const parentVisit = visits[i].parentVisit;
    if (parentVisit) {
      let span = 1;
      while (i + span < visits.length && visits[i + span].parentVisit === parentVisit) {
        span++;
      }
      groups.push({ label: parentVisit, colSpan: span, startIdx: i });
      i += span;
    } else {
      groups.push({ label: visits[i].displayName, colSpan: 1, startIdx: i });
      i++;
    }
  }
  return groups;
};

// Helper function to format visit timing based on unit (day, hour, week, cycle)
const formatVisitTiming = (timing: { value: number | null; unit?: string } | undefined): string => {
  if (!timing || timing.value === null || timing.value === undefined) return "—";

  const unit = timing.unit?.toLowerCase() || "day";

  switch(unit) {
    case "hour":
    case "hours":
      return `${timing.value}h`;
    case "cycle":
    case "cycles":
      return `Cycle ${timing.value}`;
    case "week":
    case "weeks":
      return `Week ${timing.value}`;
    case "day":
    case "days":
    default:
      return `Day ${timing.value}`;
  }
};

// Helper function to get the unit label for editable timing badge
const getTimingUnitLabel = (timing: { unit?: string } | undefined): string => {
  if (!timing?.unit) return "Day";

  const unit = timing.unit.toLowerCase();
  switch(unit) {
    case "hour":
    case "hours":
      return "Hour";
    case "cycle":
    case "cycles":
      return "Cycle";
    case "week":
    case "weeks":
      return "Week";
    case "day":
    case "days":
    default:
      return "Day";
  }
};

type WizardStepStatus = "completed" | "current" | "pending";

interface StepperProps {
  steps: typeof wizardSteps;
  currentStepIndex: number;
  onStepClick: (index: number) => void;
  stepStatuses: Record<string, WizardStepStatus>;
}

/**
 * Build a reverse lookup from footnotes' appliesTo → Map<entityKey, markers[]>.
 * Handles both flat array format ("ACT-001@ENC-002") and structured object format.
 * Keys: visitId, activityId, or "activityId@visitId" for cells.
 */
function buildFootnoteReverseLookup(
  footnotes: Array<{ marker: string; appliesTo?: any }> | undefined
): Map<string, string[]> {
  const lookup = new Map<string, string[]>();
  if (!footnotes) return lookup;

  const addEntry = (key: string, marker: string) => {
    const existing = lookup.get(key);
    if (existing) {
      if (!existing.includes(marker)) existing.push(marker);
    } else {
      lookup.set(key, [marker]);
    }
  };

  for (const fn of footnotes) {
    const at = fn.appliesTo;
    if (!at) continue;
    const marker = fn.marker;

    if (Array.isArray(at)) {
      // Flat format from backend: ["ACT-001@ENC-002", "ENC-001", "ACT-003", ...]
      // Only register at the exact level provided — do NOT bubble cell refs up
      for (const ref of at) {
        if (typeof ref === 'string' && ref) addEntry(ref, marker);
        // "ACT-001@ENC-002" → cell-level key (exact match)
        // "ENC-001" → visit-level key (LLM explicitly said whole-visit)
        // "ACT-003" → activity-level key (LLM explicitly said whole-activity)
      }
    } else if (typeof at === 'object') {
      // Structured format from extraction_review_generator: { visits, activities, cells }
      for (const v of (at.visits || [])) addEntry(v, marker);
      for (const a of (at.activities || [])) addEntry(a, marker);
      for (const c of (at.cells || [])) {
        addEntry(`${c.activityId}@${c.visitId}`, marker);
      }
    }
  }

  return lookup;
}

function WizardStepper({ steps, currentStepIndex, onStepClick, stepStatuses }: StepperProps) {
  return (
    <div className="flex items-center justify-center py-4 bg-white border-b border-gray-200">
      <div className="flex items-center gap-0">
        {steps.map((step, index) => {
          const status = stepStatuses[step.id] || "pending";
          const isActive = index === currentStepIndex;
          const isCompleted = status === "completed";
          const isLast = index === steps.length - 1;

          return (
            <div key={step.id} className="flex items-center">
              {/* Step Circle and Label */}
              <button
                onClick={() => onStepClick(index)}
                className="flex flex-col items-center gap-1.5 group"
                data-testid={`step-${step.id}`}
                role="tab"
                aria-selected={isActive}
                aria-label={`${step.title}: ${step.description}`}
              >
                {/* Numbered Circle */}
                <div
                  className={cn(
                    "w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold transition-all duration-300 border-2",
                    isActive && "bg-primary text-white border-primary shadow-md",
                    !isActive && isCompleted && "bg-primary text-white border-primary",
                    !isActive && !isCompleted && "bg-white text-gray-400 border-gray-300 group-hover:border-gray-400"
                  )}
                >
                  {isCompleted && !isActive ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    index + 1
                  )}
                </div>
                {/* Step Label */}
                <span
                  className={cn(
                    "text-xs font-medium whitespace-nowrap transition-colors",
                    isActive && "text-primary",
                    !isActive && isCompleted && "text-gray-700",
                    !isActive && !isCompleted && "text-gray-400"
                  )}
                >
                  {step.title}
                </span>
              </button>

              {/* Connector Line */}
              {!isLast && (
                <div className="w-24 mx-2 flex items-center -mt-5">
                  <div
                    className={cn(
                      "h-0.5 w-full transition-colors duration-300",
                      index < currentStepIndex ? "bg-primary" : "bg-gray-300"
                    )}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface CellPosition {
  row: number;
  col: number;
}

interface Selection {
  anchor: CellPosition | null;
  focus: CellPosition | null;
  cells: Set<string>;
}

interface MergeInfo {
  rowSpan: number;
  colSpan: number;
  mergeGroupId: string;
  isMergedChild: boolean;
  parentRow?: number;
  parentCol?: number;
}

interface EditableCell {
  value: string;
  visitId: string;
  footnoteRefs: string[];
  provenance: { pageNumber: number; boundingBox?: { x: number; y: number; width: number; height: number } } | null;
  merge?: MergeInfo;
}

interface EditableRow {
  activityId: string;
  activityName: string;
  cells: EditableCell[];
}

interface EditableTableState {
  visits: SOATable["visits"];
  activities: SOATable["activities"];
  grid: EditableRow[];
  legend: Record<string, string>;
  footnotes: SOATable["footnotes"];
}

interface TableEditorState {
  table: EditableTableState | null;
  selection: Selection;
  history: EditableTableState[];
  historyIndex: number;
  isEditing: boolean;
}

type TableAction =
  | { type: "INIT_TABLE"; table: SOATable }
  | { type: "SET_SELECTION"; selection: Selection }
  | { type: "CLEAR_SELECTION" }
  | { type: "TOGGLE_CELL_SELECTION"; row: number; col: number; shiftKey: boolean }
  | { type: "MERGE_CELLS" }
  | { type: "SPLIT_CELLS" }
  | { type: "ADD_ROW"; afterIndex: number }
  | { type: "REMOVE_ROW"; index: number }
  | { type: "ADD_COLUMN"; afterIndex: number }
  | { type: "REMOVE_COLUMN"; index: number }
  | { type: "UPDATE_CELL"; row: number; col: number; value: string }
  | { type: "UNDO" }
  | { type: "REDO" }
  | { type: "TOGGLE_EDIT_MODE" };

function cellKey(row: number, col: number): string {
  return `${row}-${col}`;
}

function parseKey(key: string): CellPosition {
  const [row, col] = key.split("-").map(Number);
  return { row, col };
}

function getSelectionBounds(cells: Set<string>): { minRow: number; maxRow: number; minCol: number; maxCol: number } | null {
  if (cells.size === 0) return null;
  let minRow = Infinity, maxRow = -Infinity, minCol = Infinity, maxCol = -Infinity;
  cells.forEach(key => {
    const { row, col } = parseKey(key);
    minRow = Math.min(minRow, row);
    maxRow = Math.max(maxRow, row);
    minCol = Math.min(minCol, col);
    maxCol = Math.max(maxCol, col);
  });
  return { minRow, maxRow, minCol, maxCol };
}

function isRectangularSelection(cells: Set<string>): boolean {
  if (cells.size <= 1) return true;
  const bounds = getSelectionBounds(cells);
  if (!bounds) return false;
  const expectedSize = (bounds.maxRow - bounds.minRow + 1) * (bounds.maxCol - bounds.minCol + 1);
  return cells.size === expectedSize;
}

function initTableFromSOA(table: SOATable): EditableTableState {
  // Safely handle potentially non-array data from USDM
  const visits = Array.isArray(table.visits) ? table.visits : [];
  const activities = Array.isArray(table.activities) ? table.activities : [];
  const grid = table.matrix?.grid && Array.isArray(table.matrix.grid) ? table.matrix.grid : [];
  const footnotes = Array.isArray(table.footnotes) ? table.footnotes : [];

  return {
    visits: [...visits],
    activities: [...activities],
    grid: grid.map(row => ({
      activityId: row.activityId,
      activityName: row.activityName,
      cells: Array.isArray(row.cells) ? row.cells.map(cell => ({
        value: cell.value,
        visitId: cell.visitId,
        footnoteRefs: Array.isArray(cell.footnoteRefs) ? [...cell.footnoteRefs] : [],
        provenance: cell.provenance ? { ...cell.provenance } : null,
      })) : [],
    })),
    legend: table.matrix?.legend ? { ...table.matrix.legend } : { symbols: {} },
    footnotes: [...footnotes],
  };
}

function tableReducer(state: TableEditorState, action: TableAction): TableEditorState {
  switch (action.type) {
    case "INIT_TABLE": {
      const editableTable = initTableFromSOA(action.table);
      return {
        ...state,
        table: editableTable,
        history: [editableTable],
        historyIndex: 0,
        selection: { anchor: null, focus: null, cells: new Set() },
      };
    }

    case "TOGGLE_EDIT_MODE":
      return { ...state, isEditing: !state.isEditing };

    case "SET_SELECTION":
      return { ...state, selection: action.selection };

    case "CLEAR_SELECTION":
      return { ...state, selection: { anchor: null, focus: null, cells: new Set() } };

    case "TOGGLE_CELL_SELECTION": {
      const { row, col, shiftKey } = action;
      const newCells = new Set(state.selection.cells);
      const key = cellKey(row, col);
      
      if (shiftKey && state.selection.anchor) {
        const minRow = Math.min(state.selection.anchor.row, row);
        const maxRow = Math.max(state.selection.anchor.row, row);
        const minCol = Math.min(state.selection.anchor.col, col);
        const maxCol = Math.max(state.selection.anchor.col, col);
        newCells.clear();
        for (let r = minRow; r <= maxRow; r++) {
          for (let c = minCol; c <= maxCol; c++) {
            newCells.add(cellKey(r, c));
          }
        }
        return {
          ...state,
          selection: { anchor: state.selection.anchor, focus: { row, col }, cells: newCells },
        };
      }
      
      if (newCells.has(key)) {
        newCells.delete(key);
      } else {
        newCells.add(key);
      }
      return {
        ...state,
        selection: { anchor: { row, col }, focus: { row, col }, cells: newCells },
      };
    }

    case "MERGE_CELLS": {
      if (!state.table || !isRectangularSelection(state.selection.cells) || state.selection.cells.size < 2) {
        return state;
      }
      const bounds = getSelectionBounds(state.selection.cells);
      if (!bounds) return state;

      const newGrid = state.table.grid.map((row, ri) => ({
        ...row,
        cells: row.cells.map((cell, ci) => {
          if (ri >= bounds.minRow && ri <= bounds.maxRow && ci >= bounds.minCol && ci <= bounds.maxCol) {
            const isParent = ri === bounds.minRow && ci === bounds.minCol;
            const mergeGroupId = `merge-${bounds.minRow}-${bounds.minCol}`;
            return {
              ...cell,
              merge: {
                rowSpan: isParent ? bounds.maxRow - bounds.minRow + 1 : 1,
                colSpan: isParent ? bounds.maxCol - bounds.minCol + 1 : 1,
                mergeGroupId,
                isMergedChild: !isParent,
                parentRow: bounds.minRow,
                parentCol: bounds.minCol,
              },
            };
          }
          return cell;
        }),
      }));

      const newTable = { ...state.table, grid: newGrid };
      const newHistory = [...state.history.slice(0, state.historyIndex + 1), newTable];
      return {
        ...state,
        table: newTable,
        history: newHistory.slice(-20),
        historyIndex: Math.min(newHistory.length - 1, 19),
        selection: { anchor: null, focus: null, cells: new Set() },
      };
    }

    case "SPLIT_CELLS": {
      if (!state.table || state.selection.cells.size === 0) return state;

      const cellsToSplit = new Set<string>();
      state.selection.cells.forEach(key => {
        const { row, col } = parseKey(key);
        const cell = state.table!.grid[row]?.cells[col];
        if (cell?.merge?.mergeGroupId) {
          state.table!.grid.forEach((r, ri) => {
            r.cells.forEach((c, ci) => {
              if (c.merge?.mergeGroupId === cell.merge?.mergeGroupId) {
                cellsToSplit.add(cellKey(ri, ci));
              }
            });
          });
        }
      });

      if (cellsToSplit.size === 0) return state;

      const newGrid = state.table.grid.map((row, ri) => ({
        ...row,
        cells: row.cells.map((cell, ci) => {
          if (cellsToSplit.has(cellKey(ri, ci))) {
            const { merge, ...rest } = cell;
            return rest as EditableCell;
          }
          return cell;
        }),
      }));

      const newTable = { ...state.table, grid: newGrid };
      const newHistory = [...state.history.slice(0, state.historyIndex + 1), newTable];
      return {
        ...state,
        table: newTable,
        history: newHistory.slice(-20),
        historyIndex: Math.min(newHistory.length - 1, 19),
        selection: { anchor: null, focus: null, cells: new Set() },
      };
    }

    case "ADD_ROW": {
      if (!state.table) return state;
      const { afterIndex } = action;
      const newId = `activity-new-${Date.now()}`;
      const newRow: EditableRow = {
        activityId: newId,
        activityName: "New Activity",
        cells: state.table.visits.map(v => ({
          value: "",
          visitId: v.id,
          footnoteRefs: [],
          provenance: null,
        })),
      };
      const newGrid = [...state.table.grid];
      newGrid.splice(afterIndex + 1, 0, newRow);
      
      const newActivity: SOAActivity = {
        id: newId,
        displayName: "New Activity",
        originalText: "New Activity",
        rowIndex: afterIndex + 1,
        category: null,
        footnoteRefs: [],
        provenance: { pageNumber: 1 },
      };
      const newActivities = [...state.table.activities];
      newActivities.splice(afterIndex + 1, 0, newActivity);

      const newTable = { ...state.table, grid: newGrid, activities: newActivities };
      const newHistory = [...state.history.slice(0, state.historyIndex + 1), newTable];
      return {
        ...state,
        table: newTable,
        history: newHistory.slice(-20),
        historyIndex: Math.min(newHistory.length - 1, 19),
      };
    }

    case "REMOVE_ROW": {
      if (!state.table || state.table.grid.length <= 1) return state;
      const { index } = action;
      const newGrid = state.table.grid.filter((_, i) => i !== index);
      const newActivities = state.table.activities.filter((_, i) => i !== index);
      const newTable = { ...state.table, grid: newGrid, activities: newActivities };
      const newHistory = [...state.history.slice(0, state.historyIndex + 1), newTable];
      return {
        ...state,
        table: newTable,
        history: newHistory.slice(-20),
        historyIndex: Math.min(newHistory.length - 1, 19),
        selection: { anchor: null, focus: null, cells: new Set() },
      };
    }

    case "ADD_COLUMN": {
      if (!state.table) return state;
      const { afterIndex } = action;
      const newVisitId = `visit-new-${Date.now()}`;
      const newVisit: SOAVisit = {
        id: newVisitId,
        displayName: "New Visit",
        originalText: "New Visit",
        columnIndex: afterIndex + 1,
        footnoteRefs: [],
        provenance: { pageNumber: 1 },
      };
      const newVisits = [...state.table.visits];
      newVisits.splice(afterIndex + 1, 0, newVisit);

      const newGrid = state.table.grid.map(row => {
        const newCells = [...row.cells];
        newCells.splice(afterIndex + 1, 0, {
          value: "",
          visitId: newVisitId,
          footnoteRefs: [],
          provenance: null,
        });
        return { ...row, cells: newCells };
      });

      const newTable = { ...state.table, grid: newGrid, visits: newVisits };
      const newHistory = [...state.history.slice(0, state.historyIndex + 1), newTable];
      return {
        ...state,
        table: newTable,
        history: newHistory.slice(-20),
        historyIndex: Math.min(newHistory.length - 1, 19),
      };
    }

    case "REMOVE_COLUMN": {
      if (!state.table || state.table.visits.length <= 1) return state;
      const { index } = action;
      const newVisits = state.table.visits.filter((_, i) => i !== index);
      const newGrid = state.table.grid.map(row => ({
        ...row,
        cells: row.cells.filter((_, i) => i !== index),
      }));
      const newTable = { ...state.table, grid: newGrid, visits: newVisits };
      const newHistory = [...state.history.slice(0, state.historyIndex + 1), newTable];
      return {
        ...state,
        table: newTable,
        history: newHistory.slice(-20),
        historyIndex: Math.min(newHistory.length - 1, 19),
        selection: { anchor: null, focus: null, cells: new Set() },
      };
    }

    case "UPDATE_CELL": {
      if (!state.table) return state;
      const { row, col, value } = action;
      const newGrid = state.table.grid.map((r, ri) => 
        ri === row ? {
          ...r,
          cells: r.cells.map((c, ci) => ci === col ? { ...c, value } : c),
        } : r
      );
      const newTable = { ...state.table, grid: newGrid };
      const newHistory = [...state.history.slice(0, state.historyIndex + 1), newTable];
      return {
        ...state,
        table: newTable,
        history: newHistory.slice(-20),
        historyIndex: Math.min(newHistory.length - 1, 19),
      };
    }

    case "UNDO": {
      if (state.historyIndex <= 0) return state;
      return {
        ...state,
        historyIndex: state.historyIndex - 1,
        table: state.history[state.historyIndex - 1],
      };
    }

    case "REDO": {
      if (state.historyIndex >= state.history.length - 1) return state;
      return {
        ...state,
        historyIndex: state.historyIndex + 1,
        table: state.history[state.historyIndex + 1],
      };
    }

    default:
      return state;
  }
}

const initialEditorState: TableEditorState = {
  table: null,
  selection: { anchor: null, focus: null, cells: new Set() },
  history: [],
  historyIndex: -1,
  isEditing: false,
};

interface ToolbarButtonProps {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: "default" | "destructive";
}

function ToolbarButton({ icon, label, onClick, disabled, variant = "default" }: ToolbarButtonProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClick}
            disabled={disabled}
            className={cn(
              "h-8 w-8 p-0",
              variant === "destructive" && "hover:bg-gray-100 hover:text-gray-700"
            )}
            data-testid={`toolbar-${label.toLowerCase().replace(/\s/g, "-")}`}
          >
            {icon}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{label}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

interface TableToolbarProps {
  selection: Selection;
  isEditing: boolean;
  canUndo: boolean;
  canRedo: boolean;
  onMerge: () => void;
  onSplit: () => void;
  onAddRow: () => void;
  onRemoveRow: () => void;
  onAddColumn: () => void;
  onRemoveColumn: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onToggleEdit: () => void;
  onClearSelection: () => void;
}

function TableToolbar({
  selection,
  isEditing,
  canUndo,
  canRedo,
  onMerge,
  onSplit,
  onAddRow,
  onRemoveRow,
  onAddColumn,
  onRemoveColumn,
  onUndo,
  onRedo,
  onToggleEdit,
  onClearSelection,
}: TableToolbarProps) {
  const hasSelection = selection.cells.size > 0;
  const canMerge = selection.cells.size >= 2 && isRectangularSelection(selection.cells);
  const bounds = getSelectionBounds(selection.cells);

  return (
    <div className="flex items-center gap-1 px-3 py-2 bg-gray-100 border-b rounded-t-lg">
      <Button
        variant={isEditing ? "default" : "outline"}
        size="sm"
        onClick={onToggleEdit}
        className="h-8 text-xs"
        data-testid="toggle-edit-mode"
      >
        {isEditing ? "Done Editing" : "Edit Table"}
      </Button>

      {isEditing && (
        <>
          <Separator orientation="vertical" className="h-6 mx-2" />
          
          <ToolbarButton
            icon={<Undo2 className="h-4 w-4" />}
            label="Undo"
            onClick={onUndo}
            disabled={!canUndo}
          />
          <ToolbarButton
            icon={<Redo2 className="h-4 w-4" />}
            label="Redo"
            onClick={onRedo}
            disabled={!canRedo}
          />

          <Separator orientation="vertical" className="h-6 mx-2" />

          <ToolbarButton
            icon={<Merge className="h-4 w-4" />}
            label="Merge Cells"
            onClick={onMerge}
            disabled={!canMerge}
          />
          <ToolbarButton
            icon={<Split className="h-4 w-4" />}
            label="Split Cells"
            onClick={onSplit}
            disabled={!hasSelection}
          />

          <Separator orientation="vertical" className="h-6 mx-2" />

          <ToolbarButton
            icon={<Plus className="h-4 w-4" />}
            label="Add Row"
            onClick={onAddRow}
          />
          <ToolbarButton
            icon={<Minus className="h-4 w-4" />}
            label="Remove Row"
            onClick={onRemoveRow}
            disabled={!hasSelection}
            variant="destructive"
          />

          <Separator orientation="vertical" className="h-6 mx-2" />

          <ToolbarButton
            icon={<Columns className="h-4 w-4" />}
            label="Add Column"
            onClick={onAddColumn}
          />
          <ToolbarButton
            icon={<Trash2 className="h-4 w-4" />}
            label="Remove Column"
            onClick={onRemoveColumn}
            disabled={!hasSelection}
            variant="destructive"
          />

          {hasSelection && (
            <>
              <Separator orientation="vertical" className="h-6 mx-2" />
              <Badge variant="secondary" className="text-xs">
                {selection.cells.size} cell{selection.cells.size !== 1 ? "s" : ""} selected
              </Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={onClearSelection}
                className="h-6 text-xs px-2"
                data-testid="clear-selection"
              >
                Clear
              </Button>
            </>
          )}
        </>
      )}
    </div>
  );
}

interface EditableSOATableGridProps {
  editorState: TableEditorState;
  dispatch: React.Dispatch<TableAction>;
  onCellClick?: (rowIndex: number, colIndex: number) => void;
  footnotes?: SOATable["footnotes"];
}

function EditableSOATableGrid({ editorState, dispatch, onCellClick, footnotes }: EditableSOATableGridProps) {
  const { table, selection, isEditing } = editorState;
  if (!table) return null;

  const footnoteMap = useMemo(() => {
    const map = new Map<string, { marker: string; text: string }>();
    footnotes?.forEach(fn => {
      map.set(fn.id, { marker: fn.marker, text: fn.text });
      map.set(fn.marker, { marker: fn.marker, text: fn.text });
    });
    return map;
  }, [footnotes]);

  const reverseLookup = useMemo(() => buildFootnoteReverseLookup(footnotes), [footnotes]);

  const handleCellClick = (rowIndex: number, colIndex: number, e: React.MouseEvent) => {
    if (isEditing) {
      dispatch({ type: "TOGGLE_CELL_SELECTION", row: rowIndex, col: colIndex, shiftKey: e.shiftKey });
    }
    onCellClick?.(rowIndex, colIndex);
  };

  return (
    <div className="overflow-x-auto max-w-full bg-white shadow-sm">
      <table className="w-max border-collapse text-sm">
        <thead>
          {/* Parent group row - only when visits have parentVisit (e.g., hours under days) */}
          {(() => {
            const groups = computeVisitGroups(table.visits);
            if (!groups) return null;
            return (
              <tr className="bg-gray-100">
                <th className="border border-gray-200 px-3 py-1 text-left font-semibold text-gray-700 sticky left-0 bg-gray-100 z-10 min-w-[200px]" />
                {groups.map((group, gIdx) => (
                  <th
                    key={gIdx}
                    colSpan={group.colSpan}
                    className="border border-gray-200 px-2 py-1.5 text-center font-semibold text-gray-700 text-xs"
                  >
                    {group.label}
                  </th>
                ))}
              </tr>
            );
          })()}
          {/* Individual visit columns */}
          <tr className="bg-gray-50">
            <th className="border border-gray-200 px-3 py-2 text-left font-semibold text-gray-700 sticky left-0 bg-gray-50 z-10 min-w-[200px]">
              Activity
            </th>
            {table.visits.map((visit, colIdx) => {
              const hasParentGroups = table.visits.some((v: any) => v.parentVisit);
              return (
                <th
                  key={visit.id}
                  className={cn(
                    "border border-gray-200 px-2 py-2 text-center font-medium text-gray-700 min-w-[80px] whitespace-nowrap",
                    isEditing && "cursor-pointer hover:bg-gray-100"
                  )}
                  onClick={() => isEditing && dispatch({ type: "ADD_COLUMN", afterIndex: colIdx })}
                >
                  {hasParentGroups && (visit as any).timingModifier ? (
                    <div className="text-xs">{(visit as any).timingModifier}</div>
                  ) : (
                    <>
                      <div className="text-xs">{visit.displayName}</div>
                      {visit.timing && (
                        <div className="text-[10px] text-muted-foreground mt-1">
                          {formatVisitTiming(visit.timing)}
                        </div>
                      )}
                    </>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {table.grid.map((row, rowIndex) => {
            const activity = table.activities.find((a) => a.id === row.activityId);
            return (
              <tr key={row.activityId} className="hover:bg-gray-50/50">
                <td className="border border-gray-200 px-3 py-2 font-medium text-gray-800 sticky left-0 bg-white z-10">
                  <div className="flex items-center gap-2">
                    <span>{activity?.displayName || row.activityName}</span>
                    {activity?.category && (
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                        {activity.category}
                      </Badge>
                    )}
                  </div>
                </td>
                {row.cells.map((cell, colIndex) => {
                  if (cell.merge?.isMergedChild) return null;

                  const isSelected = selection.cells.has(cellKey(rowIndex, colIndex));
                  const cellValue = cell.value.toUpperCase();
                  const hasValue = cellValue === "X" || cellValue === "O";
                  const rowSpan = cell.merge?.rowSpan || 1;
                  const colSpan = cell.merge?.colSpan || 1;

                  return (
                    <td
                      key={`${row.activityId}-${cell.visitId}`}
                      rowSpan={rowSpan}
                      colSpan={colSpan}
                      className={cn(
                        "border border-gray-200 px-2 py-2 text-center transition-colors",
                        isEditing && "cursor-pointer",
                        isSelected && "bg-primary/20 ring-2 ring-primary ring-inset",
                        !isSelected && hasValue && "bg-gray-50/50",
                        !isSelected && !hasValue && "hover:bg-gray-50",
                        cell.merge && !cell.merge.isMergedChild && "bg-gray-100/50"
                      )}
                      onClick={(e) => handleCellClick(rowIndex, colIndex, e)}
                      data-testid={`cell-${rowIndex}-${colIndex}`}
                    >
                      <span
                        className={cn(
                          "font-semibold",
                          cellValue === "X" && "text-gray-800",
                          cellValue === "O" && "text-gray-600"
                        )}
                      >
                        {cell.value}
                      </span>
                      {(() => {
                        const cellKey = `${row.activityId}@${cell.visitId}`;
                        const reverseMarkers = reverseLookup.get(cellKey) || [];
                        const effectiveMarkers = reverseMarkers.length > 0
                          ? reverseMarkers
                          : cell.footnoteRefs.map(ref => footnoteMap.get(ref)?.marker || ref);
                        return effectiveMarkers.length > 0 ? (
                          <TooltipProvider delayDuration={100}>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <sup className="text-[10px] text-primary ml-0.5 font-medium cursor-help hover:text-primary/70 transition-colors">
                                  {effectiveMarkers.join(",")}
                                </sup>
                              </TooltipTrigger>
                              <TooltipContent
                                side="top"
                                className="max-w-sm p-3 bg-gray-900 text-white border-0 shadow-xl rounded-lg"
                              >
                                <div className="space-y-2">
                                  {effectiveMarkers.map((marker, idx) => {
                                    const fn = footnoteMap.get(marker);
                                    return fn ? (
                                      <div key={marker} className={cn(idx > 0 && "pt-2 border-t border-gray-700")}>
                                        <span className="font-semibold text-primary-foreground">{fn.marker}:</span>{" "}
                                        <span className="text-gray-200 text-xs leading-relaxed">{fn.text}</span>
                                      </div>
                                    ) : null;
                                  })}
                                </div>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        ) : null;
                      })()}
                      {cell.merge && !cell.merge.isMergedChild && (
                        <div className="text-[9px] text-gray-600 mt-1">
                          merged {rowSpan}×{colSpan}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

interface SOATableGridProps {
  table: SOATable;
  onCellClick?: (rowIndex: number, colIndex: number) => void;
  selectedCell?: { row: number; col: number } | null;
  onFieldUpdate?: (path: string, value: string) => void;
  tableIndex?: number;
  highlights?: GridHighlights;
}

function SOATableGrid({ table, onCellClick, selectedCell, onFieldUpdate, tableIndex = 0, highlights }: SOATableGridProps) {
  const { visits: rawVisits, activities: rawActivities, matrix, footnotes } = table;

  // Debug logging
  console.log('[SOATableGrid] table:', table);
  console.log('[SOATableGrid] rawVisits:', rawVisits, 'length:', rawVisits?.length);
  console.log('[SOATableGrid] rawActivities:', rawActivities, 'length:', rawActivities?.length);
  console.log('[SOATableGrid] matrix:', matrix);
  console.log('[SOATableGrid] matrix.grid:', matrix?.grid, 'length:', matrix?.grid?.length);

  // Ensure arrays are actually arrays (USDM data may have different structures)
  const visits = Array.isArray(rawVisits) ? rawVisits : [];
  const activities = Array.isArray(rawActivities) ? rawActivities : [];

  console.log('[SOATableGrid] visits after check:', visits.length, 'first visit:', visits[0]);

  const footnoteMap = useMemo(() => {
    const map = new Map<string, { marker: string; text: string }>();
    const footnoteArray = Array.isArray(footnotes) ? footnotes : [];
    footnoteArray.forEach(fn => {
      map.set(fn.id, { marker: fn.marker, text: fn.text });
      map.set(fn.marker, { marker: fn.marker, text: fn.text });
    });
    return map;
  }, [footnotes]);

  const reverseLookup = useMemo(() => {
    const lookup = buildFootnoteReverseLookup(Array.isArray(footnotes) ? footnotes : []);
    if (lookup.size > 0) {
      console.log('[SOATableGrid] reverseLookup built:', lookup.size, 'entries',
        Object.fromEntries(Array.from(lookup.entries()).slice(0, 10)));
    }
    return lookup;
  }, [footnotes]);

  // Calculate minimum table width: 250px for activity + 100px per visit
  const minTableWidth = 250 + visits.length * 100;

  return (
    <div className="border rounded-lg bg-white shadow-sm" style={{ overflowX: 'auto' }}>
      <table className="border-collapse text-sm" style={{ minWidth: `${minTableWidth}px` }}>
        <thead>
          {/* Parent group row - only when visits have parentVisit (e.g., hours under days) */}
          {(() => {
            const groups = computeVisitGroups(visits);
            if (!groups) return null;
            return (
              <tr className="bg-gray-100">
                <th className="border border-gray-200 px-3 py-1 text-left font-semibold text-gray-700 bg-gray-100" style={{ minWidth: '200px', maxWidth: '300px' }} />
                {groups.map((group, gIdx) => (
                  <th
                    key={gIdx}
                    colSpan={group.colSpan}
                    className="border border-gray-200 px-2 py-1.5 text-center font-semibold text-gray-700 text-xs"
                  >
                    {group.label}
                  </th>
                ))}
              </tr>
            );
          })()}
          {/* Individual visit columns */}
          <tr className="bg-gray-50">
            <th className="border border-gray-200 px-3 py-2 text-left font-semibold text-gray-700 bg-gray-50" style={{ minWidth: '200px', maxWidth: '300px' }}>
              Activity
            </th>
            {visits.map((visit, visitIndex) => {
              const hasParentGroups = visits.some((v: any) => v.parentVisit);
              const reverseVisitMarkers = reverseLookup.get(visit.id) || [];
              const visitFootnoteMarkers = reverseVisitMarkers.length > 0
                ? reverseVisitMarkers
                : ((visit as any).footnoteRefs || []).map((ref: string) => footnoteMap.get(ref)?.marker || ref);
              return (
                <th
                  key={visit.id}
                  className={cn(
                    "border border-gray-200 px-2 py-3 text-center font-medium text-gray-700 bg-gray-50/80",
                    highlights?.newVisitIds.has(visit.id) && "bg-green-100 border-green-300"
                  )}
                  style={{ width: '120px', minWidth: '100px' }}
                >
                  <div className="flex flex-col items-center gap-1.5">
                    {hasParentGroups && (visit as any).timingModifier ? (
                      <div className="text-xs font-semibold text-gray-800 leading-tight">
                        {(visit as any).timingModifier}
                      </div>
                    ) : (
                      <>
                        {/* Visit Name */}
                        <div className="text-xs font-semibold text-gray-800 leading-tight">
                          <EditableText
                            value={visit.displayName || `Visit ${visitIndex + 1}`}
                            onSave={(newValue) => {
                              onFieldUpdate?.(`tables.${tableIndex}.visits.${visitIndex}.displayName`, newValue);
                            }}
                          />
                          {visitFootnoteMarkers.length > 0 && (
                            <sup className="text-[9px] text-blue-600 ml-0.5 font-medium">
                              {visitFootnoteMarkers.join(",")}
                            </sup>
                          )}
                        </div>
                        {/* Timing Badge - shows unit (Day/Hour/Week/Cycle) based on timing.unit */}
                        {visit.timing && (
                          <div className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-gray-100 rounded text-[10px] text-gray-600">
                            <span className="text-gray-400">{getTimingUnitLabel(visit.timing)}</span>
                            <EditableText
                              value={visit.timing.value !== null ? String(visit.timing.value) : ""}
                              placeholder=""
                              onSave={(newValue) => {
                                onFieldUpdate?.(`tables.${tableIndex}.visits.${visitIndex}.timing.value`, newValue);
                              }}
                              className="font-medium text-gray-700"
                            />
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {matrix.grid.map((row, rowIndex) => {
            const activity = activities.find((a) => a.id === row.activityId);
            const activityIndex = activities.findIndex((a) => a.id === row.activityId);
            const expansion = highlights?.expandedActivities.get(row.activityId);
            const isExpanded = !!expansion;
            return (
              <tr key={row.activityId} className={cn(
                "hover:bg-gray-50/50",
                highlights?.newActivityIds.has(row.activityId) && "bg-green-50",
                isExpanded && !highlights?.newActivityIds.has(row.activityId) && "bg-violet-50/40"
              )}>
                <td className={cn(
                  "border border-gray-200 px-3 py-2 font-medium text-gray-800 bg-white",
                  highlights?.newActivityIds.has(row.activityId) && "bg-green-50 border-l-2 border-l-green-400",
                  isExpanded && !highlights?.newActivityIds.has(row.activityId) && "bg-violet-50 border-l-2 border-l-violet-400"
                )} style={{ minWidth: '200px', maxWidth: '300px' }}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <EditableText
                      value={activity?.displayName || row.activityName}
                      onSave={(newValue) => {
                        if (activityIndex >= 0) {
                          onFieldUpdate?.(`tables.${tableIndex}.activities.${activityIndex}.displayName`, newValue);
                        }
                        // Also update the row's activityName
                        onFieldUpdate?.(`tables.${tableIndex}.matrix.grid.${rowIndex}.activityName`, newValue);
                      }}
                      className="break-words"
                    />
                    {/* Activity footnote markers - superscript (reverse lookup preferred) */}
                    {(() => {
                      const reverseActMarkers = reverseLookup.get(row.activityId) || [];
                      const actMarkers = reverseActMarkers.length > 0
                        ? reverseActMarkers
                        : (activity?.footnoteRefs || []).map((ref: string) => footnoteMap.get(ref)?.marker || ref);
                      return actMarkers.length > 0 ? (
                        <sup className="text-[9px] text-blue-600 font-medium -mt-1 ml-0.5">
                          {actMarkers.join(",")}
                        </sup>
                      ) : null;
                    })()}
                    {activity?.category && (
                      <EditableText
                        value={activity.category}
                        onSave={(newValue) => {
                          if (activityIndex >= 0) {
                            onFieldUpdate?.(`tables.${tableIndex}.activities.${activityIndex}.category`, newValue);
                          }
                        }}
                        className="text-[10px] px-1.5 py-0.5 border rounded-md bg-gray-100 text-gray-600 whitespace-nowrap"
                      />
                    )}
                    {/* Stage 2 expansion indicator with tooltip */}
                    {isExpanded && expansion && (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-violet-100 text-violet-700 border border-violet-200 text-[10px] font-medium cursor-help whitespace-nowrap">
                              <Split className="w-3 h-3" />
                              {expansion.componentCount}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent side="right" className="max-w-xs p-0 bg-white border border-gray-200 shadow-lg">
                            <div className="px-3 py-2">
                              <p className="text-xs font-semibold text-gray-800 mb-1.5">
                                Expanded into {expansion.componentCount} components
                              </p>
                              <ul className="space-y-0.5">
                                {expansion.components.map((comp, ci) => (
                                  <li key={ci} className="text-xs text-gray-600 flex items-center gap-1.5">
                                    <span className="w-1 h-1 rounded-full bg-violet-400 flex-shrink-0" />
                                    {comp.name}
                                  </li>
                                ))}
                              </ul>
                              {expansion.confidence > 0 && (
                                <p className="text-[10px] text-gray-400 mt-1.5 border-t pt-1">
                                  {Math.round(expansion.confidence * 100)}% confidence · {expansion.source}
                                </p>
                              )}
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    )}
                  </div>
                </td>
                {row.cells.map((cell, colIndex) => {
                  const isSelected = selectedCell?.row === rowIndex && selectedCell?.col === colIndex;
                  const cellValue = (cell.value || '').toUpperCase();
                  const hasValue = cellValue === "X" || cellValue === "O";
                  const isNewActivity = highlights?.newActivityIds.has(row.activityId);
                  const isNewVisit = highlights?.newVisitIds.has(cell.visitId);

                  return (
                    <td
                      key={`${row.activityId}-${cell.visitId}-${colIndex}`}
                      className={cn(
                        "border border-gray-200 px-2 py-2 text-center transition-colors",
                        isSelected && "bg-primary/20 ring-2 ring-primary ring-inset",
                        !isSelected && (isNewActivity || isNewVisit) && "bg-green-50/50",
                        !isSelected && !isNewActivity && !isNewVisit && hasValue && "bg-gray-50/50",
                        !isSelected && !isNewActivity && !isNewVisit && !hasValue && "hover:bg-gray-50"
                      )}
                      style={{ width: '100px' }}
                      onClick={() => onCellClick?.(rowIndex, colIndex)}
                    >
                      <span className="inline-flex items-start">
                        <EditableText
                          value={cell.value || ''}
                          placeholder=""
                          onSave={(newValue) => {
                            onFieldUpdate?.(`tables.${tableIndex}.matrix.grid.${rowIndex}.cells.${colIndex}.value`, newValue);
                          }}
                          className={cn(
                            "font-semibold",
                            cellValue === "X" && "text-gray-800",
                            cellValue === "O" && "text-gray-600"
                          )}
                        />
                        {/* Editable footnote refs - superscript immediately after X (reverse lookup preferred) */}
                        {(() => {
                          const cellEntityKey = `${row.activityId}@${cell.visitId}`;
                          const reverseCellMarkers = reverseLookup.get(cellEntityKey) || [];
                          const displayMarkers = reverseCellMarkers.length > 0
                            ? reverseCellMarkers.join(",")
                            : (cell.footnoteRefs?.map(ref => footnoteMap.get(ref)?.marker || ref).join(",") || '');
                          return (hasValue || displayMarkers) ? (
                            <sup className="text-[9px] text-blue-600 font-medium -mt-1 ml-0.5">
                              <EditableText
                                value={displayMarkers}
                                placeholder=""
                                onSave={(newValue) => {
                                  const markers = newValue.split(',').map(m => m.trim()).filter(Boolean);
                                  const footnoteIds = markers.map(marker => {
                                    for (const [key, fn] of Array.from(footnoteMap.entries())) {
                                      if (fn.marker === marker) return key;
                                    }
                                    return marker;
                                  });
                                  onFieldUpdate?.(`tables.${tableIndex}.matrix.grid.${rowIndex}.cells.${colIndex}.footnoteRefs`, JSON.stringify(footnoteIds));
                                }}
                                className="text-[9px] text-blue-600 font-medium"
                              />
                            </sup>
                          ) : null;
                        })()}
                      </span>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// Footnotes Panel with Category Grouping
function MarkerEditor({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [editValue, setEditValue] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); inputRef.current?.select(); }, []);

  const handleSave = () => { onSave(editValue); };
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSave();
  };

  return (
    <div className="space-y-2">
      <label className="text-xs font-medium text-gray-500">Marker</label>
      <input
        ref={inputRef}
        type="text"
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onKeyDown={handleKeyDown}
        className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 bg-white"
      />
      <div className="flex justify-end gap-2">
        <button onClick={handleSave} className="px-2 py-1 text-xs bg-gray-900 text-white rounded-md hover:bg-gray-800">
          Save
        </button>
      </div>
    </div>
  );
}

interface FootnotesPanelProps {
  footnotes: SOATable["footnotes"] | undefined;
  onViewSource: (pageNumber: number) => void;
  onFieldUpdate?: (path: string, value: string) => void;
  tableIndex?: number;
  onAddFootnote?: (footnote: FootnoteWithCategory) => void;
  onDeleteFootnote?: (footnoteId: string) => void;
  currentPage?: number;
}

// Marker dropdown options for add footnote form
const MARKER_OPTIONS = {
  letters: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j'],
  symbols: ['*', '†', '‡', '§', '¶', '#'],
  numbers: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'],
};

// Rule type options
const RULE_TYPE_OPTIONS = ['CONDITIONAL', 'TIMING', 'FREQUENCY', 'OPERATIONAL', 'PROCEDURAL', 'INFORMATIONAL'];

interface FootnoteWithCategory {
  id: string;
  marker: string;
  text: string;
  ruleType?: string;
  category?: string | string[];
  subcategory?: string;
  classificationReasoning?: string;
  edcImpact?: {
    affectsScheduling?: boolean;
    affectsBranching?: boolean;
    isInformational?: boolean;
  };
  provenance?: { pageNumber: number; tableId?: string };
}

const CATEGORY_CONFIG: Record<string, { label: string; color: string; bgColor: string; icon: string }> = {
  CONDITIONAL: { label: 'Conditional', color: 'text-gray-700', bgColor: 'bg-gray-100 border-gray-300', icon: '🔀' },
  SCHEDULING: { label: 'Scheduling', color: 'text-gray-700', bgColor: 'bg-gray-100 border-gray-300', icon: '📅' },
  OPERATIONAL: { label: 'Operational', color: 'text-gray-700', bgColor: 'bg-gray-100 border-gray-300', icon: '⚙️' },
  PROCEDURAL: { label: 'Procedural', color: 'text-gray-700', bgColor: 'bg-gray-100 border-gray-300', icon: '📋' },
  INFORMATIONAL: { label: 'Informational', color: 'text-gray-700', bgColor: 'bg-gray-50 border-gray-200', icon: 'ℹ️' },
  UNCATEGORIZED: { label: 'Other', color: 'text-gray-700', bgColor: 'bg-gray-50 border-gray-200', icon: '📝' },
};

function FootnotesPanel({ footnotes, onViewSource, onFieldUpdate, tableIndex = 0, onAddFootnote, onDeleteFootnote, currentPage = 1 }: FootnotesPanelProps) {
  // Ensure footnotes is an array (USDM data may have different structures)
  const footnoteArray = Array.isArray(footnotes) ? footnotes : [];

  // State for add footnote form
  const [showAddForm, setShowAddForm] = useState(false);
  const [markerType, setMarkerType] = useState<'letters' | 'symbols' | 'numbers' | 'custom'>('letters');
  const [formData, setFormData] = useState({
    marker: '',
    text: '',
    pageNumber: currentPage,
    ruleType: '',
    category: '',
    subcategory: '',
    textSnippet: '',
  });
  const [customMarker, setCustomMarker] = useState('');
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Reset form when currentPage changes
  useEffect(() => {
    setFormData(prev => ({ ...prev, pageNumber: currentPage }));
  }, [currentPage]);

  // Get effective marker value
  const getEffectiveMarker = () => {
    if (markerType === 'custom') {
      return customMarker;
    }
    return formData.marker;
  };

  // Validate form
  const validateForm = () => {
    const errors: Record<string, string> = {};
    const marker = getEffectiveMarker();

    if (!marker.trim()) {
      errors.marker = 'Marker is required';
    }
    if (!formData.text.trim()) {
      errors.text = 'Footnote text is required';
    }
    if (!formData.pageNumber || formData.pageNumber < 1) {
      errors.pageNumber = 'Valid page number is required';
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // Handle form submission
  const handleSubmitFootnote = () => {
    if (!validateForm()) return;
    if (!onAddFootnote) return;

    const marker = getEffectiveMarker();
    const newFootnote: FootnoteWithCategory = {
      id: `fn-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      marker: marker.trim(),
      text: formData.text.trim(),
      ruleType: formData.ruleType || undefined,
      category: formData.category || undefined,
      subcategory: formData.subcategory || undefined,
      provenance: {
        pageNumber: formData.pageNumber,
      },
    };

    onAddFootnote(newFootnote);

    // Reset form
    setShowAddForm(false);
    setFormData({
      marker: '',
      text: '',
      pageNumber: currentPage,
      ruleType: '',
      category: '',
      subcategory: '',
      textSnippet: '',
    });
    setCustomMarker('');
    setMarkerType('letters');
    setFormErrors({});
  };

  // Handle form cancel
  const handleCancelForm = () => {
    setShowAddForm(false);
    setFormData({
      marker: '',
      text: '',
      pageNumber: currentPage,
      ruleType: '',
      category: '',
      subcategory: '',
      textSnippet: '',
    });
    setCustomMarker('');
    setMarkerType('letters');
    setFormErrors({});
  };

  // Create a map of footnote id to its original index for field updates
  const footnoteIndexMap = useMemo(() => {
    const map = new Map<string, number>();
    footnoteArray.forEach((fn, idx) => map.set(fn.id, idx));
    return map;
  }, [footnoteArray]);

  const groupedFootnotes = useMemo(() => {
    const groups = new Map<string, FootnoteWithCategory[]>();
    if (footnoteArray.length === 0) return [];

    footnoteArray.forEach((fn) => {
      const fnWithCat = fn as FootnoteWithCategory;
      const categories = Array.isArray(fnWithCat.category) 
        ? fnWithCat.category 
        : fnWithCat.category 
          ? [fnWithCat.category] 
          : ['UNCATEGORIZED'];
      
      const primaryCategory = categories[0] || 'UNCATEGORIZED';
      if (!groups.has(primaryCategory)) {
        groups.set(primaryCategory, []);
      }
      groups.get(primaryCategory)!.push(fnWithCat);
    });
    
    const sortOrder = ['CONDITIONAL', 'SCHEDULING', 'OPERATIONAL', 'PROCEDURAL', 'INFORMATIONAL', 'UNCATEGORIZED'];
    return Array.from(groups.entries()).sort((a, b) => {
      return sortOrder.indexOf(a[0]) - sortOrder.indexOf(b[0]);
    });
  }, [footnoteArray]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    groupedFootnotes.forEach(([cat, fns]) => {
      counts[cat] = fns.length;
    });
    return counts;
  }, [groupedFootnotes]);

  // Inline Add Footnote Form JSX (not a component to prevent re-mount on state change)
  const addFootnoteFormJSX = showAddForm ? (
    <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 mb-4">
      <div className="flex items-center justify-between mb-4">
        <h4 className="font-medium text-gray-900">Add New Footnote</h4>
        <button
          onClick={handleCancelForm}
          className="text-gray-400 hover:text-gray-600"
          type="button"
        >
          <Plus className="w-4 h-4 rotate-45" />
        </button>
      </div>

      <div className="space-y-4">
        {/* Row 1: Marker and Page Number */}
        <div className="grid grid-cols-2 gap-4">
          {/* Marker Dropdown */}
          <div className="space-y-1.5">
            <Label className="text-sm font-medium text-gray-700">
              Marker <span className="text-red-500">*</span>
            </Label>
            <div className="flex gap-2">
              <Select
                value={markerType}
                onValueChange={(value: 'letters' | 'symbols' | 'numbers' | 'custom') => {
                  setMarkerType(value);
                  setFormData(prev => ({ ...prev, marker: '' }));
                  setFormErrors(prev => ({ ...prev, marker: '' }));
                }}
              >
                <SelectTrigger className="w-[100px]">
                  <SelectValue placeholder="Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="letters">Letters</SelectItem>
                  <SelectItem value="symbols">Symbols</SelectItem>
                  <SelectItem value="numbers">Numbers</SelectItem>
                  <SelectItem value="custom">Other</SelectItem>
                </SelectContent>
              </Select>

              {markerType === 'custom' ? (
                <Input
                  value={customMarker}
                  onChange={(e) => {
                    setCustomMarker(e.target.value);
                    setFormErrors(prev => ({ ...prev, marker: '' }));
                  }}
                  placeholder="Enter marker"
                  className={cn("flex-1", formErrors.marker && "border-red-500")}
                />
              ) : (
                <Select
                  value={formData.marker}
                  onValueChange={(value) => {
                    setFormData(prev => ({ ...prev, marker: value }));
                    setFormErrors(prev => ({ ...prev, marker: '' }));
                  }}
                >
                  <SelectTrigger className={cn("flex-1", formErrors.marker && "border-red-500")}>
                    <SelectValue placeholder="Select marker" />
                  </SelectTrigger>
                  <SelectContent>
                    {MARKER_OPTIONS[markerType].map((marker) => (
                      <SelectItem key={marker} value={marker}>
                        {marker}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            {formErrors.marker && (
              <p className="text-xs text-red-500">{formErrors.marker}</p>
            )}
          </div>

          {/* Page Number */}
          <div className="space-y-1.5">
            <Label className="text-sm font-medium text-gray-700">
              Page Number <span className="text-red-500">*</span>
            </Label>
            <Input
              type="number"
              min={1}
              value={formData.pageNumber}
              onChange={(e) => {
                setFormData(prev => ({ ...prev, pageNumber: parseInt(e.target.value) || 1 }));
                setFormErrors(prev => ({ ...prev, pageNumber: '' }));
              }}
              className={cn(formErrors.pageNumber && "border-red-500")}
            />
            {formErrors.pageNumber && (
              <p className="text-xs text-red-500">{formErrors.pageNumber}</p>
            )}
          </div>
        </div>

        {/* Row 2: Footnote Text */}
        <div className="space-y-1.5">
          <Label className="text-sm font-medium text-gray-700">
            Footnote Text <span className="text-red-500">*</span>
          </Label>
          <Textarea
            value={formData.text}
            onChange={(e) => {
              setFormData(prev => ({ ...prev, text: e.target.value }));
              setFormErrors(prev => ({ ...prev, text: '' }));
            }}
            placeholder="Enter footnote text or paste from PDF..."
            rows={3}
            className={cn(formErrors.text && "border-red-500")}
          />
          {formErrors.text && (
            <p className="text-xs text-red-500">{formErrors.text}</p>
          )}
        </div>

        {/* Row 3: Optional Fields */}
        <div className="grid grid-cols-3 gap-4">
          {/* Rule Type */}
          <div className="space-y-1.5">
            <Label className="text-sm font-medium text-gray-500">Rule Type</Label>
            <Select
              value={formData.ruleType}
              onValueChange={(value) => setFormData(prev => ({ ...prev, ruleType: value }))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Optional" />
              </SelectTrigger>
              <SelectContent>
                {RULE_TYPE_OPTIONS.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type.charAt(0) + type.slice(1).toLowerCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Category */}
          <div className="space-y-1.5">
            <Label className="text-sm font-medium text-gray-500">Category</Label>
            <Select
              value={formData.category}
              onValueChange={(value) => setFormData(prev => ({ ...prev, category: value }))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Optional" />
              </SelectTrigger>
              <SelectContent>
                {Object.keys(CATEGORY_CONFIG).map((cat) => (
                  <SelectItem key={cat} value={cat}>
                    {CATEGORY_CONFIG[cat].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Subcategory */}
          <div className="space-y-1.5">
            <Label className="text-sm font-medium text-gray-500">Subcategory</Label>
            <Input
              value={formData.subcategory}
              onChange={(e) => setFormData(prev => ({ ...prev, subcategory: e.target.value }))}
              placeholder="Optional"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={handleCancelForm} type="button">
            Cancel
          </Button>
          <Button size="sm" onClick={handleSubmitFootnote} type="button">
            <Plus className="w-4 h-4 mr-1" />
            Add Footnote
          </Button>
        </div>
      </div>
    </div>
  ) : null;

  if (footnoteArray.length === 0) {
    return (
      <div className="space-y-4">
        {/* Add Footnote Button for empty state */}
        {onAddFootnote && !showAddForm && (
          <div className="flex justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowAddForm(true)}
              className="gap-1.5"
              type="button"
            >
              <Plus className="w-4 h-4" />
              Add Footnote
            </Button>
          </div>
        )}

        {/* Add Footnote Form */}
        {addFootnoteFormJSX}

        {/* Empty state message */}
        {!showAddForm && (
          <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">No footnotes found in this table.</p>
            {onAddFootnote && (
              <p className="text-sm text-gray-400 mt-2">
                Click "Add Footnote" to add missing footnotes manually.
              </p>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Card - Apple-style light */}
      <div className="rounded-2xl bg-white border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-semibold tracking-tight text-gray-900">Table Footnotes</h3>
            <p className="text-gray-500 mt-1">
              {footnoteArray.length} footnotes classified by type
            </p>
          </div>
          <div className="flex items-center gap-2 ml-4">
            {/* Add Footnote Button */}
            {onAddFootnote && !showAddForm && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowAddForm(true)}
                className="gap-1 h-7 px-2.5 text-xs"
                type="button"
              >
                <Plus className="w-3 h-3" />
                Add Footnote
              </Button>
            )}
            <div className="flex items-center gap-1.5 flex-wrap">
              {Object.entries(categoryCounts).map(([cat, count]) => {
                const config = CATEGORY_CONFIG[cat] || CATEGORY_CONFIG.UNCATEGORIZED;
                return (
                  <div
                    key={cat}
                    className="px-2 py-0.5 rounded-full bg-gray-100 text-xs text-gray-600"
                  >
                    <span className="mr-0.5">{config.icon}</span>
                    {config.label}: {count}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Add Footnote Form (collapsible) */}
      {addFootnoteFormJSX}

      {/* Grouped Footnotes */}
      {groupedFootnotes.map(([category, categoryFootnotes]) => {
        const config = CATEGORY_CONFIG[category] || CATEGORY_CONFIG.UNCATEGORIZED;
        
        return (
          <div key={category} className="space-y-3">
            {/* Category Header */}
            <div className={cn(
              "flex items-center gap-3 px-4 py-3 rounded-xl border",
              config.bgColor
            )}>
              <span className="text-xl">{config.icon}</span>
              <div>
                <h4 className={cn("font-semibold", config.color)}>{config.label}</h4>
                <p className="text-xs text-gray-500">{categoryFootnotes.length} footnote{categoryFootnotes.length > 1 ? 's' : ''}</p>
              </div>
            </div>

            {/* Footnote Cards */}
            <div className="space-y-2 pl-4">
              {categoryFootnotes.map((footnote) => {
                const categories = Array.isArray(footnote.category)
                  ? footnote.category
                  : footnote.category
                    ? [footnote.category]
                    : [];
                const footnoteIdx = footnoteIndexMap.get(footnote.id) ?? -1;

                return (
                  <div
                    key={footnote.id}
                    className="group w-full text-left focus:outline-none focus:ring-2 focus:ring-blue-500/30 rounded-xl"
                    data-testid={`view-footnote-${footnote.id}`}
                  >
                    <div className="flex items-start gap-3">
                      {/* Marker Badge - Editable via Popover */}
                      <Popover>
                        <PopoverTrigger asChild>
                          <button className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-100 text-gray-600 flex items-center justify-center font-medium text-sm border border-gray-200 hover:bg-gray-200 hover:border-gray-300 transition-colors group relative">
                            {footnote.marker}
                            <Pencil className="w-2.5 h-2.5 absolute -bottom-0.5 -right-0.5 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </button>
                        </PopoverTrigger>
                        <PopoverContent className="w-48 p-3" side="right" align="start">
                          <MarkerEditor
                            value={footnote.marker}
                            onSave={(newValue) => {
                              if (footnoteIdx >= 0) {
                                onFieldUpdate?.(`tables.${tableIndex}.footnotes.${footnoteIdx}.marker`, newValue);
                              }
                            }}
                          />
                        </PopoverContent>
                      </Popover>

                      {/* Footnote Card */}
                      <div className={cn(
                        "flex-1 rounded-xl border border-gray-200/80 bg-white p-4 shadow-sm transition-all duration-200",
                        "hover:shadow-md hover:border-gray-300"
                      )}>
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            {/* Tags Row */}
                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              {footnote.ruleType && (
                                <EditableText
                                  value={footnote.ruleType.replace('_', ' ')}
                                  onSave={(newValue) => {
                                    if (footnoteIdx >= 0) {
                                      onFieldUpdate?.(`tables.${tableIndex}.footnotes.${footnoteIdx}.ruleType`, newValue.replace(' ', '_'));
                                    }
                                  }}
                                  className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-600"
                                />
                              )}
                              {categories.length > 1 && categories.slice(1).map((cat: string) => {
                                const catConfig = CATEGORY_CONFIG[cat] || CATEGORY_CONFIG.UNCATEGORIZED;
                                return (
                                  <span
                                    key={cat}
                                    className={cn(
                                      "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium",
                                      catConfig.bgColor, catConfig.color
                                    )}
                                  >
                                    {catConfig.label}
                                  </span>
                                );
                              })}
                              {footnote.edcImpact?.affectsBranching && (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-700 border border-gray-300">
                                  Affects EDC Branching
                                </span>
                              )}
                              {footnote.edcImpact?.affectsScheduling && (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-700 border border-gray-300">
                                  Affects Scheduling
                                </span>
                              )}
                            </div>

                            <EditableText
                              value={footnote.text}
                              onSave={(newValue) => {
                                if (footnoteIdx >= 0) {
                                  onFieldUpdate?.(`tables.${tableIndex}.footnotes.${footnoteIdx}.text`, newValue);
                                }
                              }}
                              multiline
                              className="text-sm text-gray-700 leading-relaxed"
                            />

                            {footnote.subcategory && (
                              <div className="text-xs text-gray-400 mt-2">
                                Subcategory:{" "}
                                <EditableText
                                  value={typeof footnote.subcategory === 'string'
                                    ? footnote.subcategory.replace('_', ' ')
                                    : String(footnote.subcategory)}
                                  onSave={(newValue) => {
                                    if (footnoteIdx >= 0) {
                                      onFieldUpdate?.(`tables.${tableIndex}.footnotes.${footnoteIdx}.subcategory`, newValue.replace(' ', '_'));
                                    }
                                  }}
                                  className="text-xs"
                                />
                              </div>
                            )}
                          </div>

                          {/* Actions - Navigate to PDF & Delete */}
                          <div className="flex-shrink-0 flex items-center gap-1">
                            <button
                              onClick={() => {
                                if (footnote.provenance?.pageNumber) {
                                  onViewSource(footnote.provenance.pageNumber);
                                }
                              }}
                              className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center text-gray-400 hover:bg-gray-200 hover:text-gray-700 transition-colors"
                              title="View in PDF"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </button>
                            {onDeleteFootnote && (
                              <button
                                onClick={() => onDeleteFootnote(footnote.id)}
                                className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center text-gray-400 hover:bg-red-100 hover:text-red-600 transition-colors opacity-0 group-hover:opacity-100"
                                title="Delete footnote"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Interpretation Expansion Panel - Shows 12-stage interpretation results from database
interface InterpretationExpansionPanelProps {
  jobId: string | null;
  protocolId: string | null;  // Protocol ID for insights link
  usdmData: any;
  extraction: any;  // Current extraction data with tables
  onViewSource: (pageNumber: number) => void;
  currentTableId?: string;  // Currently selected table ID for per-table filtering
  perTableStages?: Record<string, any>;  // Pre-fetched per-table interpretation stages
  section?: 'overview' | 'details' | 'all';  // Which section to render
  onViewInsights?: () => void;  // Callback to view detailed insights inline
}

function InterpretationExpansionPanel({ jobId, protocolId, usdmData, extraction, onViewSource, currentTableId, perTableStages, section = 'all', onViewInsights }: InterpretationExpansionPanelProps) {
  const [stagesData, setStagesData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);

  // Fetch interpretation stages from database
  useEffect(() => {
    if (!jobId) return;

    const fetchStages = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await api.soa.getInterpretationStages(jobId);
        setStagesData(response);
        // Auto-select current table's group if available, otherwise first group
        if (response.groups && response.groups.length > 0) {
          const matchingGroup = currentTableId
            ? response.groups.find((g: any) =>
                g.merge_group_id === currentTableId ||
                g.source_table_ids?.includes(currentTableId)
              )
            : null;
          setSelectedGroup(matchingGroup?.merge_group_id || response.groups[0].merge_group_id);
        }
      } catch (err: any) {
        console.log('[Interpretation] Could not fetch stages:', err.message);
        // Not an error - stages may not be available yet
        setStagesData(null);
      } finally {
        setLoading(false);
      }
    };

    fetchStages();
  }, [jobId]);

  // Auto-select the group matching the currently selected table when table changes
  useEffect(() => {
    if (!stagesData?.groups || !currentTableId) return;
    const matchingGroup = stagesData.groups.find((g: any) =>
      g.merge_group_id === currentTableId ||
      g.source_table_ids?.includes(currentTableId)
    );
    if (matchingGroup) {
      setSelectedGroup(matchingGroup.merge_group_id);
    }
  }, [currentTableId, stagesData]);

  // Get activities from extraction data (scoped to current table if available)
  const extractionActivities = useMemo(() => {
    if (!extraction?.tables) return [];
    // If we have a current table ID, scope to that table
    if (currentTableId) {
      const currentTable = extraction.tables.find((t: any) => t.tableId === currentTableId);
      if (currentTable?.activities) return currentTable.activities;
    }
    // Fallback: collect activities from all tables
    const allActivities: any[] = [];
    extraction.tables.forEach((table: any) => {
      if (table.activities && Array.isArray(table.activities)) {
        allActivities.push(...table.activities);
      }
    });
    return allActivities;
  }, [extraction, currentTableId]);

  // Stage status colors
  const getStageStatusColor = (status: string) => {
    switch (status) {
      case 'success': return 'bg-green-100 text-green-700 border-green-200';
      case 'failed': return 'bg-red-100 text-red-700 border-red-200';
      case 'skipped': return 'bg-gray-100 text-gray-500 border-gray-200';
      default: return 'bg-yellow-100 text-yellow-700 border-yellow-200';
    }
  };

  // Get selected group data
  const selectedGroupData = useMemo(() => {
    if (!stagesData?.groups || !selectedGroup) return null;
    return stagesData.groups.find((g: any) => g.merge_group_id === selectedGroup);
  }, [stagesData, selectedGroup]);

  // Loading state
  if (loading) {
    if (section !== 'all') return null;
    return (
      <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center">
        <Loader2 className="w-8 h-8 text-gray-400 mx-auto mb-3 animate-spin" />
        <p className="text-gray-500">Loading interpretation stages...</p>
      </div>
    );
  }

  // No job ID
  if (!jobId) {
    if (section !== 'all') return null;
    return (
      <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center">
        <Expand className="w-12 h-12 text-gray-300 mx-auto mb-3" />
        <p className="text-gray-500">No SOA job available.</p>
        <p className="text-xs text-gray-400 mt-2">Start an extraction to see interpretation results.</p>
      </div>
    );
  }

  // No stages data - show fallback with extraction activities
  if (!stagesData || !stagesData.groups || stagesData.groups.length === 0) {
    if (section !== 'all') return null;
    // Try extraction activities first, then fall back to usdmData
    const activities = extractionActivities.length > 0
      ? extractionActivities
      : (usdmData?.activities || []);

    if (activities.length === 0) {
      return (
        <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center">
          <Expand className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500">No interpretation data available.</p>
          <p className="text-xs text-gray-400 mt-2">
            Confirm the merge plan and run 12-stage interpretation to see results.
          </p>
        </div>
      );
    }

    // Show activities from current extraction with domain categorization preview
    return (
      <div className="space-y-4">
        {/* Status Banner */}
        <div className="rounded-2xl bg-amber-50 border border-amber-200 p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">Interpretation Not Yet Run</p>
              <p className="text-xs text-amber-700 mt-1">
                Click "Confirm &amp; Classify Tables" to start the classification and interpretation pipeline.
              </p>
            </div>
          </div>
        </div>

        {/* Header */}
        <div className="rounded-2xl bg-white border border-gray-200 p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xl font-semibold tracking-tight text-gray-900">Extracted Activities</h3>
              <p className="text-gray-500 mt-1">
                {activities.length} activities from SOA extraction
              </p>
            </div>
            <Badge variant="secondary">Pre-Interpretation</Badge>
          </div>
        </div>

        {/* Activities List */}
        <div className="space-y-2">
          {activities.map((activity: any, idx: number) => (
            <div
              key={activity.id || idx}
              className="rounded-lg border border-gray-200 bg-white p-4 hover:shadow-sm transition-shadow"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <p className="font-medium text-gray-900">
                    {activity.displayName || activity.name || activity.originalText || `Activity ${idx + 1}`}
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {activity.category && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-purple-50 text-purple-700 border border-purple-200">
                        {activity.category}
                      </span>
                    )}
                    {activity.domain && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-200">
                        {typeof activity.domain === 'object'
                          ? (activity.domain.decode || activity.domain.code)
                          : activity.domain}
                      </span>
                    )}
                    {activity.footnoteRefs && activity.footnoteRefs.length > 0 && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-600">
                        {activity.footnoteRefs.length} footnote{activity.footnoteRefs.length > 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                </div>
                {activity.provenance?.pageNumber && (
                  <button
                    onClick={() => onViewSource(activity.provenance.pageNumber)}
                    className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center text-gray-400 hover:bg-gray-200 hover:text-gray-700 transition-colors ml-3"
                    title="View in PDF"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Next Steps */}
        <div className="rounded-xl bg-blue-50 border border-blue-200 p-4">
          <h4 className="font-medium text-blue-900 mb-2">Next Steps for Full Interpretation</h4>
          <ol className="text-sm text-blue-800 space-y-1 list-decimal list-inside">
            <li>Complete review of SOA Grid, Visits & Activities, and Footnotes</li>
            <li>Click "Confirm & Classify Tables" to classify and interpret</li>
            <li>Review interpreted results, then proceed to merge analysis</li>
            <li>Confirm the suggested merge plan</li>
          </ol>
        </div>
      </div>
    );
  }

  // Render full interpretation stages view
  const stageMetadata = stagesData.stage_metadata || {};

  // Overview section: Header card + summary stats
  const renderOverview = () => (
    <div className="space-y-4">
      {/* Header Card */}
      <div className="rounded-2xl bg-white border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-semibold tracking-tight text-gray-900">12-Stage Interpretation</h3>
            <p className="text-gray-500 mt-1">
              {stagesData.total_groups} merge group{stagesData.total_groups !== 1 ? 's' : ''} processed
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant={stagesData.status === 'completed' ? 'default' : 'secondary'}>
              {stagesData.status}
            </Badge>
            {protocolId && onViewInsights && (
              <button
                onClick={onViewInsights}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                View Detailed Insights
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Summary Stats Card */}
      {selectedGroupData && (
        <div className="rounded-xl bg-gray-50 border border-gray-200 p-4">
          <div className="grid grid-cols-4 gap-4 text-center">
            <div>
              <p className="text-2xl font-bold text-green-600">
                {selectedGroupData.interpretation_summary?.stages_completed || 0}
              </p>
              <p className="text-xs text-gray-500">Completed</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-red-600">
                {selectedGroupData.interpretation_summary?.stages_failed || 0}
              </p>
              <p className="text-xs text-gray-500">Failed</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-400">
                {selectedGroupData.interpretation_summary?.stages_skipped || 0}
              </p>
              <p className="text-xs text-gray-500">Skipped</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-blue-600">
                {(selectedGroupData.interpretation_summary?.total_duration_seconds || 0).toFixed(1)}s
              </p>
              <p className="text-xs text-gray-500">Duration</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  // Details section: Stage-by-Stage Results + Counts Summary
  const renderDetails = () => (
    <div className="space-y-4">
      {selectedGroupData && (
        <>
          {/* Stage-by-Stage Results */}
          <div className="space-y-2">
            <h4 className="font-medium text-gray-700">Stage Results</h4>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((stageNum) => {
              const stageMeta = stageMetadata[stageNum] || { name: `Stage ${stageNum}`, description: '' };
              const stageStatus = selectedGroupData.interpretation_summary?.stage_statuses?.[stageNum] || 'pending';
              const stageDuration = selectedGroupData.interpretation_summary?.stage_durations?.[stageNum];
              const stageResult = selectedGroupData.stage_results?.[stageNum];

              return (
                <div
                  key={stageNum}
                  className="rounded-lg border border-gray-200 bg-white p-3 hover:shadow-sm transition-shadow"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs font-medium text-gray-600">
                        {stageNum}
                      </span>
                      <div>
                        <p className="font-medium text-gray-900 text-sm">{stageMeta.name}</p>
                        <p className="text-xs text-gray-500">{stageMeta.description}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {stageDuration !== undefined && (
                        <span className="text-xs text-gray-400">{stageDuration.toFixed(2)}s</span>
                      )}
                      <span className={cn(
                        "px-2 py-0.5 rounded-full text-[10px] font-medium border",
                        getStageStatusColor(stageStatus)
                      )}>
                        {stageStatus}
                      </span>
                    </div>
                  </div>

                  {/* Show stage result summary if available */}
                  {stageResult && typeof stageResult === 'object' && (
                    <div className="mt-2 pt-2 border-t border-gray-100">
                      {stageResult.summary && (
                        <p className="text-xs text-gray-600">{stageResult.summary}</p>
                      )}
                      {stageResult.changesApplied !== undefined && (
                        <p className="text-xs text-gray-500">Changes applied: {stageResult.changesApplied}</p>
                      )}
                      {stageResult.activitiesProcessed !== undefined && (
                        <p className="text-xs text-gray-500">Activities processed: {stageResult.activitiesProcessed}</p>
                      )}
                      {stageResult.expansionsCount !== undefined && (
                        <p className="text-xs text-gray-500">Expansions: {stageResult.expansionsCount}</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Counts Summary */}
          {selectedGroupData.counts && (
            <div className="rounded-xl bg-blue-50 border border-blue-200 p-4">
              <h4 className="font-medium text-blue-900 mb-2">Final Output Counts</h4>
              <div className="grid grid-cols-4 gap-4 text-center">
                <div>
                  <p className="text-xl font-bold text-blue-700">{selectedGroupData.counts.visits || 0}</p>
                  <p className="text-xs text-blue-600">Visits</p>
                </div>
                <div>
                  <p className="text-xl font-bold text-blue-700">{selectedGroupData.counts.activities || 0}</p>
                  <p className="text-xs text-blue-600">Activities</p>
                </div>
                <div>
                  <p className="text-xl font-bold text-blue-700">{selectedGroupData.counts.sais || 0}</p>
                  <p className="text-xs text-blue-600">SAIs</p>
                </div>
                <div>
                  <p className="text-xl font-bold text-blue-700">{selectedGroupData.counts.footnotes || 0}</p>
                  <p className="text-xs text-blue-600">Footnotes</p>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );

  if (section === 'overview') return renderOverview();
  if (section === 'details') return renderDetails();

  // section === 'all': render everything together
  return (
    <div className="space-y-6">
      {renderOverview()}
      {renderDetails()}
    </div>
  );
}

// Apple-Inspired Timeline Visualization for Visits & Activities Combined
interface VisitsTimelineProps {
  visits: SOAVisit[];
  activities: SOAActivity[];
  matrix: SOATable["matrix"];
  footnotes?: SOATable["footnotes"];
  onViewSource: (pageNumber: number) => void;
}

function VisitsTimeline({ visits: rawVisits, activities: rawActivities, matrix, footnotes, onViewSource }: VisitsTimelineProps) {
  // Ensure arrays are actually arrays (USDM data may have different structures)
  const visits = Array.isArray(rawVisits) ? rawVisits : [];
  const activities = Array.isArray(rawActivities) ? rawActivities : [];

  const footnoteMap = useMemo(() => {
    const map = new Map<string, { marker: string; text: string }>();
    const footnoteArray = Array.isArray(footnotes) ? footnotes : [];
    footnoteArray.forEach(fn => map.set(fn.marker, { marker: fn.marker, text: fn.text }));
    return map;
  }, [footnotes]);

  const reverseLookup = useMemo(() => buildFootnoteReverseLookup(
    Array.isArray(footnotes) ? footnotes : []
  ), [footnotes]);

  // Build a map of visitId -> activities scheduled for that visit
  const activitiesPerVisit = useMemo(() => {
    const visitActivitiesMap = new Map<string, Array<{ activity: SOAActivity; cellValue: string; footnoteRefs: string[] }>>();

    visits.forEach(visit => {
      visitActivitiesMap.set(visit.id, []);
    });

    if (!matrix?.grid) return visitActivitiesMap;

    matrix.grid.forEach(row => {
      const activity = activities.find(a => a.id === row.activityId);
      if (!activity) return;
      
      row.cells.forEach(cell => {
        const cellValue = cell.value.trim().toUpperCase();
        if (cellValue === 'X' || cellValue === 'O' || cellValue === '✓' || cellValue === '●') {
          const existing = visitActivitiesMap.get(cell.visitId) || [];
          existing.push({ 
            activity, 
            cellValue: cell.value, 
            footnoteRefs: cell.footnoteRefs 
          });
          visitActivitiesMap.set(cell.visitId, existing);
        }
      });
    });

    return visitActivitiesMap;
  }, [visits, activities, matrix]);

  const getVisitTypeColor = (visitType: string) => {
    switch (visitType) {
      case 'screening': return '#4B5563';
      case 'treatment': return '#6B7280';
      case 'end_of_treatment': return '#9CA3AF';
      case 'follow_up': return '#374151';
      default: return '#6B7280';
    }
  };

  const getVisitTypeBgColor = (visitType: string) => {
    switch (visitType) {
      case 'screening': return 'bg-gray-50';
      case 'treatment': return 'bg-gray-50';
      case 'end_of_treatment': return 'bg-gray-100';
      case 'follow_up': return 'bg-gray-50';
      default: return 'bg-gray-50';
    }
  };

  const getVisitTypeLabel = (visitType: string) => {
    switch (visitType) {
      case 'screening': return 'Screening';
      case 'treatment': return 'Treatment';
      case 'end_of_treatment': return 'End of Treatment';
      case 'follow_up': return 'Follow-up';
      default: return 'Visit';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Card - Apple-style light */}
      <div className="rounded-2xl bg-white border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-2xl font-semibold tracking-tight text-gray-900">
              Visits & Activities
            </h3>
            <p className="text-gray-500 mt-1">
              {visits.length} visits with {activities.length} activities mapped
            </p>
          </div>
          <div className="flex items-center gap-4">
            {[
              { color: '#1F2937', label: 'Screening' },
              { color: '#4B5563', label: 'Treatment' },
              { color: '#6B7280', label: 'End of Treatment' },
              { color: '#9CA3AF', label: 'Follow-up' },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-2">
                <div 
                  className="w-2.5 h-2.5 rounded-full" 
                  style={{ backgroundColor: item.color }} 
                />
                <span className="text-xs text-gray-600">{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Vertical Timeline */}
      <div className="relative">
        {/* Timeline Vertical Line */}
        <div className="absolute left-[39px] top-0 bottom-0 w-[2px] bg-gradient-to-b from-gray-200 via-gray-300 to-gray-200" />

        {/* Visit Cards */}
        <div className="space-y-4">
          {visits.map((visit, idx) => {
            const visitType = (visit as any).visitType || 'treatment';
            const color = getVisitTypeColor(visitType);
            const bgColorClass = getVisitTypeBgColor(visitType);
            const reverseVisitMarkers = reverseLookup.get(visit.id) || [];
            const effectiveVisitMarkers = reverseVisitMarkers.length > 0
              ? reverseVisitMarkers
              : (visit.footnoteRefs || []);
            const hasFootnotes = effectiveVisitMarkers.length > 0;

            return (
              <button
                key={visit.id}
                onClick={() => onViewSource(visit.provenance.pageNumber)}
                className="group w-full text-left focus:outline-none focus:ring-2 focus:ring-blue-500/30 rounded-2xl"
                data-testid={`timeline-visit-${visit.id}`}
              >
                <div className="flex items-start gap-6">
                  {/* Timeline Node */}
                  <div className="relative flex-shrink-0 w-20 pt-5">
                    {/* Day Badge */}
                    <div className="absolute right-8 top-4 z-10">
                      <div 
                        className="px-2.5 py-1 rounded-lg text-xs font-bold text-white shadow-lg"
                        style={{ backgroundColor: color }}
                      >
                        {visit.timing?.value !== null && visit.timing?.value !== undefined
                          ? formatVisitTiming(visit.timing)
                          : `#${idx + 1}`}
                      </div>
                    </div>
                    {/* Node Circle */}
                    <div className="absolute left-[31px] top-5 z-20">
                      <div 
                        className="w-4 h-4 rounded-full border-[3px] border-white shadow-md transition-transform duration-200 group-hover:scale-125"
                        style={{ backgroundColor: color }}
                      />
                    </div>
                  </div>

                  {/* Visit Card */}
                  <div 
                    className={cn(
                      "flex-1 rounded-2xl border border-gray-200/80 bg-white p-5 shadow-sm transition-all duration-200",
                      "hover:shadow-lg hover:border-gray-300 hover:-translate-y-0.5"
                    )}
                  >
                    <div className="flex items-start justify-between gap-4">
                      {/* Left Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-2">
                          <span 
                            className={cn(
                              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
                              bgColorClass
                            )}
                            style={{ color }}
                          >
                            <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
                            {getVisitTypeLabel(visitType)}
                          </span>
                          {hasFootnotes && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 text-xs font-medium">
                              <FileText className="w-3 h-3" />
                              {effectiveVisitMarkers.length} note{effectiveVisitMarkers.length > 1 ? 's' : ''}
                            </span>
                          )}
                        </div>
                        
                        <h4 className="text-lg font-semibold text-gray-900 mb-1">
                          {visit.displayName}
                        </h4>
                        
                        <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500">
                          {visit.timing?.relativeTo && (
                            <span className="flex items-center gap-1.5">
                              <Calendar className="w-3.5 h-3.5" />
                              Relative to {visit.timing.relativeTo.replace('_', ' ')}
                            </span>
                          )}
                          {visit.window && (visit.window.earlyBound > 0 || visit.window.lateBound > 0) && (
                            <span className="flex items-center gap-1.5">
                              <Clock className="w-3.5 h-3.5" />
                              Window: -{visit.window.earlyBound} to +{visit.window.lateBound} days
                            </span>
                          )}
                        </div>

                        {/* Activities for this visit */}
                        {(() => {
                          const visitActivities = activitiesPerVisit.get(visit.id) || [];
                          if (visitActivities.length === 0) return null;
                          
                          // Group by category
                          const byCategory = new Map<string, typeof visitActivities>();
                          visitActivities.forEach(item => {
                            const cat = item.activity.category || 'Other';
                            const existing = byCategory.get(cat) || [];
                            existing.push(item);
                            byCategory.set(cat, existing);
                          });
                          
                          return (
                            <div className="mt-4 pt-4 border-t border-gray-100">
                              <div className="flex items-center gap-2 mb-3">
                                <ClipboardCheck className="w-4 h-4 text-gray-500" />
                                <span className="text-sm font-medium text-gray-700">
                                  {visitActivities.length} Activities
                                </span>
                              </div>
                              <div className="grid grid-cols-2 gap-2">
                                {visitActivities.slice(0, 6).map((item, actIdx) => (
                                  <div 
                                    key={`${item.activity.id}-${actIdx}`}
                                    className="flex items-center gap-2 px-2.5 py-1.5 bg-gray-50 rounded-lg text-xs"
                                  >
                                    <span className="w-5 h-5 rounded bg-gray-200 text-gray-700 flex items-center justify-center font-medium text-[10px]">
                                      {item.cellValue}
                                    </span>
                                    <span className="text-gray-700 truncate flex-1">
                                      {item.activity.displayName}
                                    </span>
                                    {item.activity.category && (
                                      <span className="text-[10px] text-gray-500 truncate max-w-[60px]">
                                        {item.activity.category}
                                      </span>
                                    )}
                                  </div>
                                ))}
                              </div>
                              {visitActivities.length > 6 && (
                                <p className="text-xs text-gray-500 mt-2">
                                  +{visitActivities.length - 6} more activities
                                </p>
                              )}
                            </div>
                          );
                        })()}

                        {/* Footnotes inline */}
                        {hasFootnotes && (
                          <div className="mt-3 pt-3 border-t border-gray-100">
                            <div className="space-y-1.5">
                              {effectiveVisitMarkers.map((marker) => {
                                const fn = footnoteMap.get(marker);
                                return fn ? (
                                  <p key={marker} className="text-sm text-gray-600 leading-relaxed">
                                    <span className="font-semibold text-gray-700">{fn.marker}.</span>{" "}
                                    {fn.text}
                                  </p>
                                ) : null;
                              })}
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Right Arrow */}
                      <div className="flex-shrink-0 pt-1">
                        <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center text-gray-400 group-hover:bg-gray-200 group-hover:text-gray-700 transition-colors">
                          <ExternalLink className="w-4 h-4" />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

interface SummaryCardProps {
  title: string;
  value: number | string;
  icon: React.ReactNode;
  variant?: "default" | "success" | "warning";
}

// Table Selector Component - for switching between multiple SOA tables
interface TableSelectorProps {
  tables: SOATable[];
  selectedIndex: number;
  onSelect: (index: number) => void;
  onPageChange?: (page: number) => void;
  compact?: boolean;
}

function TableSelector({ tables, selectedIndex, onSelect, onPageChange, compact = false }: TableSelectorProps) {
  if (tables.length <= 1) return null;

  const categoryColors: Record<string, string> = {
    'MAIN_SOA': 'bg-blue-100 text-blue-800 border-blue-300',
    'PK_SOA': 'bg-purple-100 text-purple-800 border-purple-300',
    'PD_SOA': 'bg-green-100 text-green-800 border-green-300',
    'SAFETY_SOA': 'bg-red-100 text-red-800 border-red-300',
  };

  if (compact) {
    return (
      <div className="flex items-center gap-2 mb-4">
        <span className="text-sm text-muted-foreground">Table:</span>
        <div className="flex gap-1">
          {tables.map((t, idx) => {
            const isSelected = idx === selectedIndex;
            const categoryColor = categoryColors[t.category] || 'bg-gray-100 text-gray-800';
            return (
              <button
                key={t.tableId}
                onClick={() => {
                  onSelect(idx);
                  if (onPageChange && t.pageRange?.start) {
                    onPageChange(t.pageRange.start);
                  }
                }}
                className={cn(
                  "px-2 py-1 rounded text-xs font-medium transition-all",
                  isSelected
                    ? "bg-primary text-white"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                )}
              >
                {t.tableId}
                <span className={cn("ml-1 px-1 rounded text-[9px]", isSelected ? "bg-white/20" : categoryColor)}>
                  {t.category?.replace('_SOA', '')}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <Card className="border-primary/20 mb-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Columns className="w-4 h-4" />
          SOA Tables ({tables.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex flex-wrap gap-2">
          {tables.map((t, idx) => {
            const isSelected = idx === selectedIndex;
            const categoryColor = categoryColors[t.category] || 'bg-gray-100 text-gray-800 border-gray-300';

            return (
              <button
                key={t.tableId}
                onClick={() => {
                  onSelect(idx);
                  if (onPageChange && t.pageRange?.start) {
                    onPageChange(t.pageRange.start);
                  }
                }}
                className={cn(
                  "flex flex-col items-start p-3 rounded-lg border-2 transition-all min-w-[140px]",
                  isSelected
                    ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                    : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                )}
              >
                <div className="flex items-center gap-2 w-full">
                  <span className="font-semibold text-sm">{t.tableId}</span>
                  {isSelected && <Check className="w-3 h-3 text-primary ml-auto" />}
                </div>
                <Badge variant="outline" className={cn("text-[10px] mt-1", categoryColor)}>
                  {t.category?.replace('_SOA', '') || 'SOA'}
                </Badge>
                <div className="text-[10px] text-muted-foreground mt-1.5 flex gap-2">
                  <span>{t.visits?.length || 0} visits</span>
                  <span>•</span>
                  <span>{t.activities?.length || 0} activities</span>
                </div>
                <div className="text-[10px] text-muted-foreground">
                  Pages {t.pageRange?.start}-{t.pageRange?.end}
                </div>
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function SummaryCard({ title, value, icon, variant = "default" }: SummaryCardProps) {
  return (
    <Card className={cn(
      "bg-white",
      variant === "success" && "border-gray-300",
      variant === "warning" && "border-gray-300"
    )}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-1">{value}</p>
          </div>
          <div className={cn(
            "w-10 h-10 rounded-lg flex items-center justify-center",
            variant === "default" && "bg-primary/10 text-primary",
            variant === "success" && "bg-gray-100 text-gray-800",
            variant === "warning" && "bg-gray-100 text-gray-700"
          )}>
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}


// SOA Extraction State Type
type SOAExtractionState =
  | 'idle'
  | 'detecting_pages'
  | 'awaiting_page_confirmation'
  | 'extracting'
  | 'awaiting_extraction_review'
  | 'interpreting_tables'
  | 'awaiting_merge_review'
  | 'analyzing_merges'
  | 'awaiting_merge_confirmation'
  | 'classifying'
  | 'awaiting_classification_review'
  | 'interpreting'
  | 'validating'
  | 'completed'
  | 'failed';

export default function SOAAnalysisPage() {
  const searchString = useSearch();
  const [, navigate] = useLocation();
  const { toast } = useToast();

  // Get protocolId from URL params (preferred) or fall back to studyId
  const searchParams = new URLSearchParams(searchString);
  const protocolId = searchParams.get('protocolId');
  const studyIdParam = searchParams.get('studyId');
  const viewParam = searchParams.get('view');
  // Use protocolId (UUID) if available, otherwise use studyId - NO hardcoded default
  const studyId = protocolId || studyIdParam || null;

  // Determine PDF URL based on studyId
  const isM14359 = studyId?.includes('M14-359') || studyId?.includes('NCT02264990');
  const pdfUrl = studyId ? getPdfUrl(studyId) : '';

  // Fetch document for database persistence and audit trail
  const { data: document } = useDocument(studyId || '', { refetchInterval: false });

  // Field update mutation for persisting SOA changes with audit trail
  const fieldUpdate = useFieldUpdate(
    document?.id ?? 0,
    studyId || '',
    document?.studyTitle ?? '',
    'anonymous'
  );

  // Legacy static data URLs (fallback)
  const extractionDataUrl = isM14359 ? M14_359_EXTRACTION_URL : M14_031_EXTRACTION_URL;
  const usdmDataUrl = isM14359 ? M14_359_USDM_URL : M14_031_USDM_URL;

  // Wizard state
  const [currentStep, setCurrentStep] = useState(0);
  const [stepStatuses, setStepStatuses] = useState<Record<string, WizardStepStatus>>({
    table_structure: "current",
    visits_activities: "pending",
    footnotes: "pending",
  });

  // View mode for switching between extraction wizard, merge confirmation, and classification review
  type ViewMode = 'extraction' | 'merge_confirmation' | 'classification_review' | 'completion' | 'interpretation';
  const [viewMode, setViewMode] = useState<ViewMode>(
    viewParam === 'interpretation' ? 'interpretation' : 'extraction'
  );

  // Raw USDM data for interpretation panel
  const [rawUsdmData, setRawUsdmData] = useState<any>(null);
  const [selectedCell, setSelectedCell] = useState<{ row: number; col: number } | null>(null);
  const [pdfExpanded, setPdfExpanded] = useState(false);
  const [dataExpanded, setDataExpanded] = useState(false);
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(41);
  const [scale, setScale] = useState(1.0);

  // Data state
  const [loading, setLoading] = useState(true);
  const [extraction, setExtraction] = useState<SOAExtraction | null>(null);
  const [error, setError] = useState<string | null>(null);

  // SOA Extraction Job State
  const [soaState, setSoaState] = useState<SOAExtractionState>('idle');
  const [soaJobId, setSoaJobId] = useState<string | null>(null);
  const [detectedPages, setDetectedPages] = useState<SOAPageInfo[]>([]);
  const [editablePages, setEditablePages] = useState<SOAPageInfo[]>([]);
  const [showPageConfirmModal, setShowPageConfirmModal] = useState(false);
  const [phaseProgress, setPhaseProgress] = useState<{
    phase: string;
    progress: number;
    current_stage?: number;
    current_stage_name?: string;
    current_stage_status?: string;
    current_group?: string;
    groups_completed?: number;
    groups_total?: number;
    current_table?: string;
    tables_completed?: number;
    tables_total?: number;
  } | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Merge Plan State (Phase 3.5)
  const [mergePlan, setMergePlan] = useState<MergePlan | null>(null);
  const [showMergeConfirmation, setShowMergeConfirmation] = useState(false);

  // Classification Review State (Phase 3.6)
  const [classificationReview, setClassificationReview] = useState<ClassificationReviewData | null>(null);
  const [showClassificationReview, setShowClassificationReview] = useState(false);

  // Interpretation Results State - for grid highlighting and stage results below grid
  const [interpretationComplete, setInterpretationComplete] = useState(false);
  const [rawPerTableUsdm, setRawPerTableUsdm] = useState<Record<string, any>>({});
  const [interpretationStagesPerTable, setInterpretationStagesPerTable] = useState<Record<string, any>>({});
  const [mergedResults, setMergedResults] = useState<any>(null);

  const [editorState, dispatch] = useReducer(tableReducer, initialEditorState);

  // Table selection state - for displaying multiple SOA tables
  const [selectedTableIndex, setSelectedTableIndex] = useState(0);

  // Reset table selection when extraction data changes
  useEffect(() => {
    setSelectedTableIndex(0);
  }, [extraction?.protocolId]);

  // Start SOA extraction when page loads
  useEffect(() => {
    async function startSOAExtraction() {
      if (!studyId) return;

      console.log('[SOA] Starting extraction check for studyId:', studyId);
      setLoading(true);

      try {
        // Check if there's an existing SOA job
        const latestJob = await api.soa.getLatestJob(studyId);
        console.log('[SOA] Latest job response:', latestJob);

        if (latestJob.job_id && latestJob.status === 'completed' && latestJob.has_results) {
          // Load completed results with interpretation highlighting
          console.log('[SOA] Loading completed job results:', latestJob.job_id);
          setSoaJobId(latestJob.job_id);
          setSoaState('completed');
          const results = await api.soa.getResults(latestJob.job_id);
          console.log('[SOA] Got results:', { keys: Object.keys(results || {}) });
          await loadSOAResults(results);

          // Load merged USDM results if available
          if (results.usdm_data?.type === "merged_interpreted") {
            setMergedResults(results.usdm_data);
          }

          // Load merge plan if available
          if (latestJob.merge_plan) {
            setMergePlan(latestJob.merge_plan as MergePlan);
          }

          // Load raw USDM and interpretation stages for grid highlighting
          try {
            const perTableResults = await api.soa.getPerTableResults(latestJob.job_id);
            const rawMap: Record<string, any> = {};
            const stagesMap: Record<string, any> = {};
            let hasInterpretation = false;
            perTableResults.tables.forEach(t => {
              if (t.raw_usdm_data) { rawMap[t.table_id] = t.raw_usdm_data; hasInterpretation = true; }
              if (t.interpretation_stages) stagesMap[t.table_id] = t.interpretation_stages;
            });
            if (hasInterpretation) {
              setRawPerTableUsdm(rawMap);
              setInterpretationStagesPerTable(stagesMap);
              setInterpretationComplete(true);
            }
          } catch (err) {
            console.log('[SOA] No interpretation data on resume');
          }

          // Set wizard to last step with all steps completed
          setCurrentStep(wizardSteps.length - 1);
          setStepStatuses({
            table_structure: "completed",
            visits_activities: "completed",
            footnotes: "completed",
          });

          // Show completion summary if merge was confirmed
          if (latestJob.merge_plan?.status === 'confirmed') {
            setViewMode('completion');
          }
          return;
        }

        if (latestJob.job_id && latestJob.status === 'awaiting_page_confirmation') {
          // Resume from page confirmation
          setSoaJobId(latestJob.job_id);
          setSoaState('awaiting_page_confirmation');
          if (latestJob.detected_pages?.tables) {
            setDetectedPages(latestJob.detected_pages.tables);
            setEditablePages(latestJob.detected_pages.tables);
            // Navigate to first detected page
            const firstPage = latestJob.detected_pages.tables[0]?.pageStart;
            if (firstPage) setPageNumber(firstPage);
          }
          setShowPageConfirmModal(true);
          setLoading(false);
          return;
        }

        if (latestJob.job_id && latestJob.status === 'awaiting_extraction_review') {
          // Resume from extraction review - show results for user to confirm
          console.log('[SOA] Resuming awaiting_extraction_review job:', latestJob.job_id);
          setSoaJobId(latestJob.job_id);
          setSoaState('awaiting_extraction_review');

          try {
            const perTableResults = await api.soa.getPerTableResults(latestJob.job_id);
            const ext = convertPerTableResultsToExtraction(perTableResults, studyId || '');
            setExtraction(ext);

            // Load raw USDM data so "Extracted USDM" export is available
            const rawMap: Record<string, any> = {};
            perTableResults.tables.forEach(t => {
              if (t.raw_usdm_data) { rawMap[t.table_id] = t.raw_usdm_data; }
            });
            if (Object.keys(rawMap).length > 0) {
              setRawPerTableUsdm(rawMap);
            }
          } catch (err) {
            console.error('Failed to fetch extraction results for review:', err);
            setError('Failed to load extraction results');
            setSoaState('failed');
          }
          setLoading(false);
          return;
        }

        if (latestJob.job_id && latestJob.status === 'interpreting_tables') {
          // Resume interpreting_tables - show progress
          console.log('[SOA] Resuming interpreting_tables job:', latestJob.job_id);
          setSoaJobId(latestJob.job_id);
          setSoaState('interpreting_tables');
          subscribeToSOAEvents(latestJob.job_id);
          return;
        }

        if (latestJob.job_id && latestJob.status === 'awaiting_merge_review') {
          // Resume from awaiting_merge_review - interpretation done, show results before merge
          console.log('[SOA] Resuming awaiting_merge_review job:', latestJob.job_id);
          setSoaJobId(latestJob.job_id);
          setSoaState('awaiting_merge_review');

          try {
            const perTableResults = await api.soa.getPerTableResults(latestJob.job_id);
            const ext = convertPerTableResultsToExtraction(perTableResults, studyId || '');
            setExtraction(ext);

            const rawMap: Record<string, any> = {};
            const stagesMap: Record<string, any> = {};
            let hasInterpretation = false;
            perTableResults.tables.forEach(t => {
              if (t.raw_usdm_data) { rawMap[t.table_id] = t.raw_usdm_data; hasInterpretation = true; }
              if (t.interpretation_stages) stagesMap[t.table_id] = t.interpretation_stages;
            });
            if (hasInterpretation) {
              setRawPerTableUsdm(rawMap);
              setInterpretationStagesPerTable(stagesMap);
              setInterpretationComplete(true);
            }
          } catch (err) {
            console.error('Failed to load interpretation results for merge review:', err);
            setError('Failed to load interpretation results');
            setSoaState('failed');
          }
          setCurrentStep(wizardSteps.length - 1);
          setStepStatuses({
            table_structure: "completed",
            visits_activities: "completed",
            footnotes: "completed",
          });
          setViewMode('extraction');
          setLoading(false);
          return;
        }

        if (latestJob.job_id && latestJob.status === 'awaiting_merge_confirmation') {
          // Resume from merge confirmation (Phase 3.5)
          setSoaJobId(latestJob.job_id);
          setSoaState('awaiting_merge_confirmation');

          // Use merge_plan from response if available, otherwise fetch it
          let mergePlanData = latestJob.merge_plan;
          if (!mergePlanData) {
            try {
              mergePlanData = await api.soa.getMergePlan(latestJob.job_id);
            } catch (err) {
              console.error('Failed to fetch merge plan:', err);
              setError('Failed to load merge plan');
              setSoaState('failed');
              setLoading(false);
              return;
            }
          }

          if (mergePlanData) {
            setMergePlan(mergePlanData as MergePlan);
            setShowMergeConfirmation(true);
            setViewMode('merge_confirmation');  // Important: Set viewMode explicitly
          } else {
            setError('Merge plan not available');
            setSoaState('failed');
          }
          setLoading(false);
          return;
        }

        // Handle awaiting_classification_review status - show classification review UI
        if (latestJob.job_id && latestJob.status === 'awaiting_classification_review') {
          console.log('[SOA] Resuming awaiting_classification_review job:', latestJob.job_id);
          setSoaJobId(latestJob.job_id);
          setSoaState('awaiting_classification_review');

          let classificationData = latestJob.classification_review;
          if (!classificationData) {
            try {
              classificationData = await api.soa.getClassificationReview(latestJob.job_id);
            } catch (err) {
              console.error('Failed to fetch classification review:', err);
              setError('Failed to load classification review');
              setSoaState('failed');
              setLoading(false);
              return;
            }
          }

          if (classificationData) {
            setClassificationReview(classificationData as ClassificationReviewData);
            setShowClassificationReview(true);
          } else {
            setError('Classification review not available');
            setSoaState('failed');
          }
          setLoading(false);
          return;
        }

        // Handle classifying status - resume and show classification progress
        if (latestJob.job_id && latestJob.status === 'classifying') {
          console.log('[SOA] Resuming classifying job:', latestJob.job_id);
          setSoaJobId(latestJob.job_id);
          setSoaState('classifying');
          subscribeToSOAEvents(latestJob.job_id);
          // Keep loading=true to show progress UI
          return;
        }

        // Handle interpreting status - resume and show interpretation progress
        if (latestJob.job_id && latestJob.status === 'interpreting') {
          console.log('[SOA] Resuming interpreting job:', latestJob.job_id);
          setSoaJobId(latestJob.job_id);
          setSoaState('interpreting');
          subscribeToSOAEvents(latestJob.job_id);
          // Keep loading=true to show progress UI
          return;
        }

        // Handle extracting status - resume and show extraction progress
        if (latestJob.job_id && latestJob.status === 'extracting') {
          console.log('[SOA] Resuming extracting job:', latestJob.job_id);
          setSoaJobId(latestJob.job_id);
          setSoaState('extracting');
          subscribeToSOAEvents(latestJob.job_id);
          // Keep loading=true to show progress UI
          return;
        }

        // Handle detecting_pages status - resume and show detection progress
        if (latestJob.job_id && latestJob.status === 'detecting_pages') {
          console.log('[SOA] Resuming detecting_pages job:', latestJob.job_id);
          setSoaJobId(latestJob.job_id);
          setSoaState('detecting_pages');
          subscribeToSOAEvents(latestJob.job_id);
          // Keep loading=true to show progress UI
          return;
        }

        // Handle analyzing_merges status - resume and show merge analysis progress
        if (latestJob.job_id && latestJob.status === 'analyzing_merges') {
          console.log('[SOA] Resuming analyzing_merges job:', latestJob.job_id);
          setSoaJobId(latestJob.job_id);
          setSoaState('analyzing_merges');
          subscribeToSOAEvents(latestJob.job_id);
          // Keep loading=true to show progress UI
          return;
        }

        // Only start fresh extraction for terminal states (failed, cancelled) or no existing job
        // Start new SOA extraction
        console.log('[SOA] Starting new extraction (no resumable job found)');
        const response = await api.soa.startExtraction(studyId);
        setSoaJobId(response.job_id);
        setSoaState('detecting_pages');

        // Subscribe to SSE events for progress
        subscribeToSOAEvents(response.job_id);

      } catch (err) {
        console.error('Failed to start SOA extraction:', err);
        setError(err instanceof Error ? err.message : 'Failed to start SOA extraction');
        setSoaState('failed');
        setLoading(false);
      }
    }

    startSOAExtraction();

    // Cleanup SSE on unmount
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [studyId]);

  // Helper function to convert per-table database results to extraction format
  const convertPerTableResultsToExtraction = (perTableResults: SOAPerTableResults, protocolId: string): SOAExtraction => {
    const tables = perTableResults.tables.map((tableResult: SOATableResult) => {
      const usdm = tableResult.usdm_data || {};

      // Extract visits, activities, footnotes, and SAIs from per-table USDM
      // Backend stages (e.g., Stage 8 Cycle Expansion) may update encounters but not visits,
      // so use whichever array has more entries to capture expanded encounters
      const usdmVisits = Array.isArray(usdm.visits) ? usdm.visits : [];
      const usdmEncounters = Array.isArray(usdm.encounters) ? usdm.encounters : [];
      const rawVisits = usdmEncounters.length > usdmVisits.length ? usdmEncounters : (usdmVisits.length > 0 ? usdmVisits : usdmEncounters);
      const rawActivities = Array.isArray(usdm.activities) ? usdm.activities : [];
      const rawFootnotes = Array.isArray(usdm.footnotes) ? usdm.footnotes : [];
      const rawSais = Array.isArray(usdm.scheduledActivityInstances) ? usdm.scheduledActivityInstances : [];

      // Transform visits
      const visits = rawVisits.map((v: any, idx: number) => ({
        id: v.id || `V-${idx + 1}`,
        columnIndex: v.columnIndex ?? idx,
        displayName: v.displayName || v.name || v.originalName || `Visit ${idx + 1}`,
        originalText: v.originalText || v.originalName || v.name || '',
        timing: v.timing,
        window: v.window,
        footnoteRefs: v.footnoteMarkers || v.footnoteRefs || [],
        provenance: v.provenance || { pageNumber: tableResult.page_start, tableId: tableResult.table_id },
        timingModifier: v.timingModifier || null,
        parentVisit: v.parentVisit || null,
      }));

      // Transform activities (preserve _expansion metadata from Stage 2)
      const activities = rawActivities.map((a: any, idx: number) => ({
        id: a.id || `A-${idx + 1}`,
        rowIndex: a.rowIndex ?? idx,
        displayName: a.displayName || a.name || a.originalText || `Activity ${idx + 1}`,
        originalText: a.originalText || a.name || '',
        category: a.category || null,
        footnoteRefs: a.footnoteMarkers || a.footnoteRefs || [],
        provenance: a.provenance || { pageNumber: tableResult.page_start, tableId: tableResult.table_id },
        ...(a._expansion ? { _expansion: a._expansion } : {}),
      }));

      // Transform footnotes — preserve appliesTo and classification fields
      const footnotes = rawFootnotes.map((f: any, idx: number) => ({
        id: f.id || `F-${idx + 1}`,
        marker: f.marker || f.footnoteMarker || `${idx + 1}`,
        text: f.text || f.footnoteText || '',
        ruleType: f.ruleType,
        category: f.category,
        subcategory: f.subcategory,
        classificationReasoning: f.classificationReasoning,
        edcImpact: f.edcImpact,
        appliesTo: f.appliesTo,
        provenance: f.provenance || { pageNumber: tableResult.page_start, tableId: tableResult.table_id },
      }));

      // Build SAI lookup
      const saiLookup = new Map<string, any>();
      rawSais.forEach((sai: any) => {
        const key = `${sai.activityId || sai.activityRef}-${sai.visitId || sai.encounterId || sai.visitRef}`;
        saiLookup.set(key, sai);
      });

      // Build grid from activities and visits
      const grid = activities.map((activity: any) => ({
        activityId: activity.id,
        activityName: activity.displayName,
        cells: visits.map((visit: any) => {
          const sai = saiLookup.get(`${activity.id}-${visit.id}`);
          const cellValue = sai ? (sai.isRequired ? 'X' : 'O') : '';
          return {
            value: cellValue,
            visitId: visit.id,
            footnoteRefs: sai?.footnoteMarkers || [],
            rawContent: cellValue,
            provenance: sai?.provenance || null,
          };
        }),
      }));

      return {
        tableId: tableResult.table_id,
        tableName: `${tableResult.table_category} Table`,
        category: tableResult.table_category,
        pageRange: { start: tableResult.page_start, end: tableResult.page_end },
        visits,
        activities,
        footnotes,
        matrix: {
          description: `${tableResult.table_category} Schedule of Activities`,
          grid,
          legend: { symbols: { 'X': 'Required', 'O': 'Optional' } },
        },
      };
    });

    // Calculate totals
    const totalVisits = tables.reduce((sum, t) => sum + (t.visits?.length || 0), 0);
    const totalActivities = tables.reduce((sum, t) => sum + (t.activities?.length || 0), 0);
    const totalFootnotes = tables.reduce((sum, t) => sum + (t.footnotes?.length || 0), 0);
    const totalSais = perTableResults.tables.reduce((sum, t) => sum + (t.sais_count || 0), 0);

    return {
      schemaVersion: '1.0',
      reviewType: 'soa_extraction',
      protocolId,
      protocolTitle: protocolId,
      generatedAt: new Date().toISOString(),
      extractionSummary: {
        totalTables: perTableResults.total_tables,
        totalVisits,
        totalActivities,
        totalScheduledInstances: totalSais,
        totalFootnotes,
        confidence: 0.9,
        warnings: [],
      },
      tables,
    };
  };

  // Load SOA results and convert to extraction format
  const loadSOAResults = useCallback(async (results: any) => {
    try {
      console.log('[SOA] loadSOAResults called with:', {
        hasResults: !!results,
        keys: results ? Object.keys(results) : [],
        hasUsdmData: !!results?.usdm_data,
        hasExtractionReview: !!results?.extraction_review
      });

      // Try fetching per-table results from database first
      const jobId = results.job_id;
      if (jobId) {
        try {
          console.log('[SOA] Fetching per-table results for job:', jobId);
          const perTableResults = await api.soa.getPerTableResults(jobId);

          if (perTableResults.tables && perTableResults.tables.length > 0) {
            console.log('[SOA] Got per-table results:', {
              totalTables: perTableResults.total_tables,
              successfulTables: perTableResults.successful_tables,
              tables: perTableResults.tables.map(t => ({
                tableId: t.table_id,
                category: t.table_category,
                visits: t.visits_count,
                activities: t.activities_count,
              })),
            });

            // Convert per-table results to extraction format
            const extractionData = convertPerTableResultsToExtraction(perTableResults, studyId || '');
            setExtraction(extractionData);

            // Load raw USDM and interpretation stages for grid highlighting
            const rawMap: Record<string, any> = {};
            const stagesMap: Record<string, any> = {};
            let hasInterpretation = false;
            perTableResults.tables.forEach(t => {
              if (t.raw_usdm_data) { rawMap[t.table_id] = t.raw_usdm_data; hasInterpretation = true; }
              if (t.interpretation_stages) stagesMap[t.table_id] = t.interpretation_stages;
            });
            if (hasInterpretation) {
              setRawPerTableUsdm(rawMap);
              setInterpretationStagesPerTable(stagesMap);
              setInterpretationComplete(true);
            }

            setLoading(false);
            setSoaState('completed');
            return;
          }
        } catch (perTableErr) {
          console.log('[SOA] Per-table results not available, falling back to legacy format:', perTableErr);
        }
      }

      // Fallback to legacy format (extraction_review or usdm_data)
      const usdmData = results.usdm_data;
      const extractionReview = results.extraction_review;

      // Store raw USDM data for interpretation panel
      if (usdmData) {
        setRawUsdmData(usdmData);
      }

      if (extractionReview && extractionReview.tables?.length > 0) {
        // Use extraction_review as primary source (has grid/matrix structure)
        // Need to extract 'items' from nested structure {items: [], sectionDescription: ""}
        const extractItems = (data: any): any[] => {
          if (Array.isArray(data)) return data;
          if (data && typeof data === 'object' && 'items' in data) return data.items || [];
          if (data && typeof data === 'object') return Object.values(data);
          return [];
        };

        const transformedTables = extractionReview.tables.map((table: any) => {
          const rawVisits = extractItems(table.visits);
          const rawActivities = extractItems(table.activities);
          const rawFootnotes = extractItems(table.footnotes);

          // Transform visits to ensure displayName exists
          const visits = rawVisits.map((v: any, idx: number) => ({
            ...v,
            id: v.id || `V-${idx + 1}`,
            columnIndex: v.columnIndex ?? idx,
            displayName: v.displayName || v.name || v.originalName || v.originalText || `Visit ${idx + 1}`,
            originalText: v.originalText || v.originalName || v.name || '',
            footnoteRefs: v.footnoteRefs || v.footnoteMarkers || [],
            provenance: v.provenance || { pageNumber: 1, tableId: 'SOA-1' },
          }));

          // Transform activities to ensure displayName exists
          const activities = rawActivities.map((a: any, idx: number) => ({
            ...a,
            id: a.id || `A-${idx + 1}`,
            rowIndex: a.rowIndex ?? idx,
            displayName: a.displayName || a.name || a.originalText || `Activity ${idx + 1}`,
            originalText: a.originalText || a.name || '',
            category: a.category || null,
            footnoteRefs: a.footnoteRefs || a.footnoteMarkers || [],
            provenance: a.provenance || { pageNumber: 1, tableId: 'SOA-1' },
          }));

          // Calculate page range from visits/activities provenance
          const allPages = [
            ...visits.map((v: any) => v.provenance?.pageNumber).filter(Boolean),
            ...activities.map((a: any) => a.provenance?.pageNumber).filter(Boolean),
          ];
          const pageRange = table.pageRange || (allPages.length > 0
            ? { start: Math.min(...allPages), end: Math.max(...allPages) }
            : { start: 1, end: 1 });

          // Extract grid - could be at table.grid or table.matrix.grid
          const rawGrid = table.grid || table.matrix?.grid || [];
          const grid = Array.isArray(rawGrid) ? rawGrid : [];

          // Build SAI lookup from USDM data to get footnoteMarkers
          const saiLookup = new Map<string, any>();
          if (usdmData?.scheduledActivityInstances) {
            usdmData.scheduledActivityInstances.forEach((sai: any) => {
              const key = `${sai.activityId || sai.activityRef}-${sai.visitId || sai.encounterId || sai.visitRef}`;
              saiLookup.set(key, sai);
            });
          }

          // Build matrix structure expected by SOATableGrid
          const matrix = {
            grid: grid.map((row: any, rowIdx: number) => {
              const activityId = row.activityId || activities[rowIdx]?.id || `A-${rowIdx + 1}`;
              return {
                activityId,
                activityName: row.activityName || activities[rowIdx]?.displayName || `Activity ${rowIdx + 1}`,
                cells: Array.isArray(row.cells) ? row.cells.map((cell: any) => {
                  // Try to get footnoteMarkers from USDM SAI if not in cell
                  // Use nullish coalescing - only fall back to SAI when footnoteRefs is null/undefined,
                  // NOT when it's an empty array (which means user explicitly cleared it)
                  let footnoteRefs = cell.footnoteRefs ?? [];
                  if ((cell.footnoteRefs === null || cell.footnoteRefs === undefined) && saiLookup.size > 0) {
                    const sai = saiLookup.get(`${activityId}-${cell.visitId}`);
                    if (sai?.footnoteMarkers && sai.footnoteMarkers.length > 0) {
                      footnoteRefs = sai.footnoteMarkers;
                    }
                  }
                  return {
                    value: cell.value ?? cell.rawContent ?? '',
                    visitId: cell.visitId || '',
                    footnoteRefs,
                    rawContent: cell.rawContent || cell.value || '',
                    provenance: cell.provenance || null,
                  };
                }) : [],
              };
            }),
            legend: table.matrix?.legend || { symbols: { 'X': 'Required', 'O': 'Optional' } },
          };

          return {
            ...table,
            pageRange,
            visits,
            activities,
            footnotes: rawFootnotes,
            matrix,
          };
        });

        console.log('[SOA] Using extraction_review with transformed tables:', {
          visitsCount: transformedTables[0]?.visits?.length,
          activitiesCount: transformedTables[0]?.activities?.length,
          footnotesCount: transformedTables[0]?.footnotes?.length,
          gridRowsCount: transformedTables[0]?.matrix?.grid?.length,
          firstVisit: transformedTables[0]?.visits?.[0],
          firstActivity: transformedTables[0]?.activities?.[0],
          firstGridRow: transformedTables[0]?.matrix?.grid?.[0],
        });
        setExtraction({
          ...extractionReview,
          tables: transformedTables
        } as SOAExtraction);
      } else if (usdmData) {
        // Fallback to usdm_data if extraction_review is not available
        console.log('[SOA] Building from USDM data (fallback):', usdmData);

        const rawVisits = Array.isArray(usdmData.visits) ? usdmData.visits : [];
        const visits = rawVisits.map((v: any, idx: number) => ({
          id: v.id,
          columnIndex: idx,
          displayName: v.displayName || v.name || v.originalName || `Visit ${idx + 1}`,
          originalText: v.originalText || v.originalName || v.name || '',
          timing: v.timing,
          window: v.window,
          footnoteRefs: v.footnoteMarkers || v.footnoteRefs || [],
          provenance: v.provenance || { pageNumber: 1, tableId: 'SOA-1' },
        }));

        const rawActivities = Array.isArray(usdmData.activities) ? usdmData.activities : [];
        const activities = rawActivities.map((a: any, idx: number) => ({
          id: a.id,
          rowIndex: idx,
          displayName: a.displayName || a.name || `Activity ${idx + 1}`,
          originalText: a.originalText || a.name || '',
          category: a.category || null,
          footnoteRefs: a.footnoteMarkers || a.footnoteRefs || [],
          provenance: a.provenance || { pageNumber: 1, tableId: 'SOA-1' },
        }));

        const sais = Array.isArray(usdmData.scheduledActivityInstances) ? usdmData.scheduledActivityInstances : [];
        const footnotes = Array.isArray(usdmData.footnotes) ? usdmData.footnotes : [];

        const saiLookup = new Map<string, any>();
        sais.forEach((sai: any) => {
          const key = `${sai.activityId}-${sai.visitId}`;
          saiLookup.set(key, sai);
        });

        const grid = activities.map((activity: any) => ({
          activityId: activity.id,
          activityName: activity.displayName || activity.name,
          cells: visits.map((visit: any) => {
            const sai = saiLookup.get(`${activity.id}-${visit.id}`);
            const cellValue = sai ? (sai.isRequired ? 'X' : 'O') : '';
            return {
              value: cellValue,
              visitId: visit.id,
              footnoteRefs: sai?.footnoteMarkers || [],
              rawContent: cellValue,
              provenance: sai?.provenance || null,
            };
          }),
        }));

        const allPages = [
          ...visits.map((v: any) => v.provenance?.pageNumber).filter(Boolean),
          ...activities.map((a: any) => a.provenance?.pageNumber).filter(Boolean),
        ];
        const pageRange = allPages.length > 0
          ? { start: Math.min(...allPages), end: Math.max(...allPages) }
          : { start: 1, end: 1 };

        const extractionData: SOAExtraction = {
          schemaVersion: '1.0',
          reviewType: 'soa_extraction',
          protocolId: studyId || '',
          protocolTitle: usdmData.protocolTitle || studyId || '',
          generatedAt: new Date().toISOString(),
          extractionSummary: {
            totalTables: 1,
            totalVisits: visits.length,
            totalActivities: activities.length,
            totalScheduledInstances: sais.length,
            totalFootnotes: footnotes.length,
            confidence: usdmData.qualityMetrics?.matrixCoverage || 0.9,
            warnings: [],
          },
          tables: [{
            tableId: 'SOA-1',
            tableName: 'Main SOA',
            category: 'MAIN_SOA',
            pageRange,
            visits,
            activities,
            footnotes,
            matrix: { description: 'Schedule of Activities', grid, legend: { 'X': 'Required', 'O': 'Optional' } },
          }],
        };
        setExtraction(extractionData);
      } else {
        // Neither extraction_review nor usdm_data available - this is an error state
        console.error('[SOA] No extraction data available in results:', {
          hasExtractionReview: !!extractionReview,
          extractionReviewTablesLength: extractionReview?.tables?.length,
          hasUsdmData: !!usdmData
        });
        setError('SOA extraction completed but no data was returned. Please try again.');
        setSoaState('failed');
        setLoading(false);
        return;
      }

      setLoading(false);
      setSoaState('completed');
    } catch (err) {
      console.error('Error loading SOA results:', err);
      setError('Failed to load SOA results');
      setLoading(false);
    }
  }, [studyId]);

  // Poll job status as fallback
  const pollJobStatus = useCallback(async (jobId: string) => {
    try {
      const status = await api.soa.getJobStatus(jobId);
      setSoaState(status.status);
      setPhaseProgress(status.phase_progress || null);

      if (status.status === 'awaiting_page_confirmation' && status.detected_pages) {
        const tables = status.detected_pages.tables || [];
        setDetectedPages(tables);
        setEditablePages(tables);
        // Navigate to first detected page
        const firstPage = tables[0]?.pageStart;
        if (firstPage) setPageNumber(firstPage);
        setShowPageConfirmModal(true);
        setLoading(false);
      } else if (status.status === 'awaiting_merge_confirmation' && status.merge_plan) {
        // Phase 3.5: Merge confirmation needed
        setMergePlan(status.merge_plan);
        setShowMergeConfirmation(true);
        setLoading(false);
      } else if (status.status === 'completed') {
        console.log('[SOA] Poll detected completion, fetching results for jobId:', jobId);
        try {
          const results = await api.soa.getResults(jobId);
          console.log('[SOA] Poll received results from API:', {
            jobId: results.job_id,
            status: results.status,
            hasUsdmData: !!results.usdm_data,
            hasExtractionReview: !!results.extraction_review,
          });
          await loadSOAResults(results);

          // Check if interpretation ran - load raw USDM for grid highlighting
          try {
            const perTableResults = await api.soa.getPerTableResults(jobId);
            const rawMap: Record<string, any> = {};
            const stagesMap: Record<string, any> = {};
            let hasInterpretation = false;
            perTableResults.tables.forEach(t => {
              if (t.raw_usdm_data) { rawMap[t.table_id] = t.raw_usdm_data; hasInterpretation = true; }
              if (t.interpretation_stages) stagesMap[t.table_id] = t.interpretation_stages;
            });
            if (hasInterpretation) {
              console.log('[SOA] Interpretation complete, showing grid with highlights');
              setRawPerTableUsdm(rawMap);
              setInterpretationStagesPerTable(stagesMap);
              setInterpretationComplete(true);
            }
          } catch (stagesErr) {
            console.log('[SOA] No interpretation data available');
          }
        } catch (fetchErr) {
          console.error('[SOA] Poll failed to fetch results:', fetchErr);
          setError(fetchErr instanceof Error ? fetchErr.message : 'Failed to fetch SOA results');
          setSoaState('failed');
          setLoading(false);
        }
      } else if (status.status === 'failed') {
        setError(status.error_message || 'SOA extraction failed');
        setLoading(false);
      } else {
        // Still in progress, poll again
        setTimeout(() => pollJobStatus(jobId), 2000);
      }
    } catch (e) {
      console.error('Error polling job status:', e);
    }
  }, [loadSOAResults]);

  // Subscribe to SOA job events
  const subscribeToSOAEvents = useCallback((jobId: string) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const eventSource = api.soa.subscribeToEvents(jobId);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.status === 'stream_ended') {
          eventSource.close();
          return;
        }

        setSoaState(data.status as SOAExtractionState);
        setPhaseProgress(data.progress);

        if (data.status === 'awaiting_page_confirmation' && data.detected_pages) {
          const tables = data.detected_pages.tables || [];
          setDetectedPages(tables);
          setEditablePages(tables);
          // Navigate to first detected page
          const firstPage = tables[0]?.pageStart;
          if (firstPage) setPageNumber(firstPage);
          setShowPageConfirmModal(true);
          setLoading(false);
          eventSource.close();
        } else if (data.status === 'awaiting_extraction_review') {
          // Extraction complete — show results for user review before interpretation
          eventSource.close();
          console.log('[SOA] Extraction complete, loading results for review...');

          try {
            const perTableResults = await api.soa.getPerTableResults(jobId);
            const ext = convertPerTableResultsToExtraction(perTableResults, studyId || '');
            setExtraction(ext);
            setSoaState('awaiting_extraction_review');
            setLoading(false);
          } catch (fetchErr) {
            console.error('[SOA] Failed to fetch extraction results for review:', fetchErr);
            setError('Failed to load extraction results');
            setSoaState('failed');
            setLoading(false);
          }
        } else if (data.status === 'awaiting_merge_confirmation') {
          // Phase 3.5: Merge confirmation needed
          eventSource.close();

          // Fetch merge plan if not in SSE data (defensive fallback)
          let mergePlanData = data.merge_plan;
          if (!mergePlanData) {
            try {
              console.log('[SOA] Merge plan not in SSE event, fetching separately');
              mergePlanData = await api.soa.getMergePlan(jobId);
            } catch (fetchErr) {
              console.error('[SOA] Failed to fetch merge plan:', fetchErr);
              setError('Failed to load merge plan');
              setSoaState('failed');
              setLoading(false);
              return;
            }
          }

          if (mergePlanData) {
            setMergePlan(mergePlanData as MergePlan);
            setShowMergeConfirmation(true);
            setViewMode('merge_confirmation');
            setLoading(false);
          } else {
            setError('Merge plan not available');
            setSoaState('failed');
            setLoading(false);
          }
        } else if (data.status === 'awaiting_classification_review') {
          // Phase 3.6: Classification review needed
          eventSource.close();

          let classificationData = data.classification_review;
          if (!classificationData) {
            try {
              console.log('[SOA] Classification review not in SSE event, fetching separately');
              classificationData = await api.soa.getClassificationReview(jobId);
            } catch (fetchErr) {
              console.error('[SOA] Failed to fetch classification review:', fetchErr);
              setError('Failed to load classification review');
              setSoaState('failed');
              setLoading(false);
              return;
            }
          }

          if (classificationData) {
            setClassificationReview(classificationData as ClassificationReviewData);
            setShowClassificationReview(true);
            setSoaState('awaiting_classification_review');
            setLoading(false);
          } else {
            setError('Classification review not available');
            setSoaState('failed');
            setLoading(false);
          }
        } else if (data.status === 'awaiting_merge_review') {
          // Interpretation complete — show results before proceeding to merge
          eventSource.close();
          console.log('[SOA] Interpretation complete, loading results for review before merge...');
          try {
            const perTableResults = await api.soa.getPerTableResults(jobId);
            const ext = convertPerTableResultsToExtraction(perTableResults, studyId || '');
            setExtraction(ext);

            const rawMap: Record<string, any> = {};
            const stagesMap: Record<string, any> = {};
            let hasInterpretation = false;
            perTableResults.tables.forEach(t => {
              if (t.raw_usdm_data) { rawMap[t.table_id] = t.raw_usdm_data; hasInterpretation = true; }
              if (t.interpretation_stages) stagesMap[t.table_id] = t.interpretation_stages;
            });
            if (hasInterpretation) {
              setRawPerTableUsdm(rawMap);
              setInterpretationStagesPerTable(stagesMap);
              setInterpretationComplete(true);
            }

            setSoaState('awaiting_merge_review');
            setViewMode('extraction');
            setLoading(false);
          } catch (fetchErr) {
            console.error('[SOA] Failed to load interpretation results:', fetchErr);
            setError('Failed to load interpretation results');
            setSoaState('failed');
            setLoading(false);
          }
        } else if (data.status === 'completed') {
          eventSource.close();
          // Fetch final results
          console.log('[SOA] Job completed, fetching results for jobId:', jobId);
          try {
            const results = await api.soa.getResults(jobId);
            console.log('[SOA] Received results from API:', {
              jobId: results.job_id,
              status: results.status,
              hasUsdmData: !!results.usdm_data,
              hasExtractionReview: !!results.extraction_review,
              usdmDataKeys: results.usdm_data ? Object.keys(results.usdm_data) : [],
              extractionReviewKeys: results.extraction_review ? Object.keys(results.extraction_review) : [],
            });
            await loadSOAResults(results);

            // Check if interpretation ran - load raw USDM for grid highlighting
            try {
              const perTableResults = await api.soa.getPerTableResults(jobId);
              const rawMap: Record<string, any> = {};
              const stagesMap: Record<string, any> = {};
              let hasInterpretation = false;
              perTableResults.tables.forEach(t => {
                if (t.raw_usdm_data) { rawMap[t.table_id] = t.raw_usdm_data; hasInterpretation = true; }
                if (t.interpretation_stages) stagesMap[t.table_id] = t.interpretation_stages;
              });
              if (hasInterpretation) {
                console.log('[SOA] Interpretation complete, showing grid with highlights');
                setRawPerTableUsdm(rawMap);
                setInterpretationStagesPerTable(stagesMap);
                setInterpretationComplete(true);
              }
            } catch (stagesErr) {
              console.log('[SOA] No interpretation data available');
            }
          } catch (fetchErr) {
            console.error('[SOA] Failed to fetch results:', fetchErr);
            setError(fetchErr instanceof Error ? fetchErr.message : 'Failed to fetch SOA results');
            setSoaState('failed');
            setLoading(false);
          }
        } else if (data.status === 'failed') {
          setError(data.error || 'SOA extraction failed');
          setLoading(false);
          eventSource.close();
        }
      } catch (e) {
        console.error('Error parsing SSE event:', e);
      }
    };

    eventSource.onerror = () => {
      console.error('SSE connection error');
      // Try to poll status instead
      pollJobStatus(jobId);
    };
  }, [loadSOAResults, pollJobStatus]);

  // Handle page confirmation
  const handleConfirmPages = async (confirmed: boolean) => {
    if (!soaJobId) return;

    setShowPageConfirmModal(false);
    setLoading(true);
    setSoaState('extracting');

    try {
      await api.soa.confirmPages(soaJobId, confirmed, confirmed ? undefined : editablePages);
      // Subscribe to events for the rest of the extraction
      subscribeToSOAEvents(soaJobId);
    } catch (err) {
      console.error('Error confirming pages:', err);
      setError(err instanceof Error ? err.message : 'Failed to confirm pages');
      setSoaState('failed');
      setLoading(false);
    }
  };

  // Handle extraction review confirmation - triggers per-table classification
  const handleConfirmExtraction = async () => {
    if (!soaJobId) return;

    setSoaState('classifying');

    try {
      await api.soa.confirmExtraction(soaJobId);
      // Subscribe to events for classification progress
      subscribeToSOAEvents(soaJobId);
    } catch (err) {
      console.error('Error confirming extraction:', err);
      setError(err instanceof Error ? err.message : 'Failed to start classification');
      setSoaState('failed');
      setLoading(false);
    }
  };

  // Handle merge plan confirmation (final step - merge is after interpretation)
  const handleConfirmMergePlan = async (confirmation: MergePlanConfirmationType) => {
    if (!soaJobId) return;

    setShowMergeConfirmation(false);
    setLoading(true);

    try {
      await api.soa.confirmMergePlan(soaJobId, confirmation);

      // Load per-table interpreted results (interpretation ran before merge analysis)
      try {
        const perTableResults = await api.soa.getPerTableResults(soaJobId);
        const rawMap: Record<string, any> = {};
        const stagesMap: Record<string, any> = {};
        let hasInterpretation = false;
        perTableResults.tables.forEach(t => {
          if (t.raw_usdm_data) { rawMap[t.table_id] = t.raw_usdm_data; hasInterpretation = true; }
          if (t.interpretation_stages) stagesMap[t.table_id] = t.interpretation_stages;
        });
        if (hasInterpretation) {
          setRawPerTableUsdm(rawMap);
          setInterpretationStagesPerTable(stagesMap);
          setInterpretationComplete(true);
        }
      } catch (stagesErr) {
        console.log('[SOA] No interpretation data available after merge confirm');
      }

      // Fetch merged USDM results (populated by confirm endpoint)
      try {
        const results = await api.soa.getResults(soaJobId);
        if (results.usdm_data?.type === "merged_interpreted") {
          setMergedResults(results.usdm_data);
        }
      } catch {
        console.log('[SOA] Merged results not available yet');
      }

      setSoaState('completed');
      setViewMode('completion');
      setLoading(false);
    } catch (err) {
      console.error('Error confirming merge plan:', err);
      setError(err instanceof Error ? err.message : 'Failed to confirm merge plan');
      setSoaState('failed');
      setLoading(false);
    }
  };

  // Handle merge plan cancellation - go back to extraction review
  const handleCancelMergePlan = () => {
    setShowMergeConfirmation(false);
    setMergePlan(null);
    setViewMode('extraction');  // Go back to extraction wizard
    setSoaState('completed');   // Keep in completed state so user can review
  };

  // Handle classification confirmation (Phase 3.6)
  const handleConfirmClassification = async (confirmedProfiles: Record<string, ClassificationProfile>) => {
    if (!soaJobId) return;

    setShowClassificationReview(false);
    setLoading(true);
    setSoaState('interpreting_tables');

    try {
      await api.soa.confirmClassification(soaJobId, confirmedProfiles);
      // Subscribe to events for interpretation phase
      subscribeToSOAEvents(soaJobId);
    } catch (err) {
      console.error('Error confirming classification:', err);
      setError(err instanceof Error ? err.message : 'Failed to confirm classification');
      setSoaState('failed');
      setLoading(false);
    }
  };

  // Handle classification cancellation - just close modal, preserve data and state
  const handleCancelClassification = () => {
    setShowClassificationReview(false);
  };

  // Handle "Complete Review" - trigger merge analysis (Phase 3.5)
  const handleCompleteReview = async () => {
    if (!soaJobId) {
      toast({
        title: "Error",
        description: "No SOA job ID found",
        variant: "destructive",
      });
      return;
    }

    setLoading(true);
    setSoaState('analyzing_merges');
    setPhaseProgress({ phase: 'merge_analysis', progress: 0 });

    try {
      // Trigger merge analysis
      await api.soa.triggerMergeAnalysis(soaJobId);

      // Poll until merge analysis completes (avoids SSE race condition)
      const maxAttempts = 60; // 60 seconds max
      let attempts = 0;

      while (attempts < maxAttempts) {
        const status = await api.soa.getJobStatus(soaJobId);
        setSoaState(status.status as SOAExtractionState);
        setPhaseProgress(status.phase_progress || null);

        if (status.status === 'awaiting_merge_confirmation') {
          // Fetch merge plan explicitly
          let mergePlanData = status.merge_plan;
          if (!mergePlanData) {
            mergePlanData = await api.soa.getMergePlan(soaJobId);
          }

          if (mergePlanData) {
            setMergePlan(mergePlanData as MergePlan);
            setShowMergeConfirmation(true);
            setViewMode('merge_confirmation');
            setLoading(false);
            return;
          }
          throw new Error('Merge plan not available');
        } else if (status.status === 'failed') {
          throw new Error(status.error_message || 'Merge analysis failed');
        } else if (status.status === 'completed') {
          // Job completed without merge confirmation needed
          const results = await api.soa.getResults(soaJobId);
          await loadSOAResults(results);

          // Check if interpretation ran - load raw USDM for grid highlighting
          try {
            const perTableResults = await api.soa.getPerTableResults(soaJobId);
            const rawMap: Record<string, any> = {};
            const stagesMap: Record<string, any> = {};
            let hasInterpretation = false;
            perTableResults.tables.forEach(t => {
              if (t.raw_usdm_data) { rawMap[t.table_id] = t.raw_usdm_data; hasInterpretation = true; }
              if (t.interpretation_stages) stagesMap[t.table_id] = t.interpretation_stages;
            });
            if (hasInterpretation) {
              console.log('[SOA] Interpretation complete, showing grid with highlights');
              setRawPerTableUsdm(rawMap);
              setInterpretationStagesPerTable(stagesMap);
              setInterpretationComplete(true);
            }
          } catch (stagesErr) {
            console.log('[SOA] No interpretation data available');
          }

          // Navigate to completion page
          setSoaState('completed');
          setCurrentStep(wizardSteps.length - 1);
          setStepStatuses({
            table_structure: "completed",
            visits_activities: "completed",
            footnotes: "completed",
          });
          setViewMode('completion');
          setLoading(false);
          return;
        }

        // Still analyzing, wait and retry
        await new Promise(resolve => setTimeout(resolve, 1000));
        attempts++;
      }

      throw new Error('Merge analysis timed out');
    } catch (err) {
      console.error('Error during merge analysis:', err);
      setError(err instanceof Error ? err.message : 'Failed to complete merge analysis');
      setSoaState('failed');
      setLoading(false);
    }
  };

  // Handle page edit
  const handlePageEdit = (index: number, field: 'pageStart' | 'pageEnd', value: number) => {
    setEditablePages(prev => {
      const updated = [...prev];
      updated[index] = {
        ...updated[index],
        [field]: value,
        pages: Array.from(
          { length: (field === 'pageEnd' ? value : updated[index].pageEnd) - (field === 'pageStart' ? value : updated[index].pageStart) + 1 },
          (_, i) => (field === 'pageStart' ? value : updated[index].pageStart) + i
        ),
      };
      return updated;
    });
  };

  // Get the currently selected table (defaults to first table)
  const table = extraction?.tables[selectedTableIndex] || extraction?.tables[0];
  const totalTables = extraction?.tables?.length || 0;

  // Compute grid highlights for the selected table (comparing raw vs interpreted USDM)
  const gridHighlights = useMemo(() => {
    if (!interpretationComplete || !table) {
      console.log('[GridHighlights] Skipped: interpretationComplete=', interpretationComplete, 'table=', !!table);
      return undefined;
    }
    const tableId = (table as any).tableId;
    const rawUsdm = tableId ? rawPerTableUsdm[tableId] : null;
    if (!rawUsdm) {
      console.log('[GridHighlights] No rawUsdm for tableId=', tableId, 'rawPerTableUsdm keys=', Object.keys(rawPerTableUsdm));
      return undefined;
    }
    console.log('[GridHighlights] Computing for tableId=', tableId,
      'rawUsdm keys=', Object.keys(rawUsdm),
      'raw visits=', (rawUsdm.visits || rawUsdm.encounters || []).length,
      'raw activities=', (rawUsdm.activities || []).length,
      'raw SAIs=', (rawUsdm.scheduledActivityInstances || []).length,
      'interp visits=', table.visits?.length,
      'interp activities=', table.activities?.length
    );
    const result = computeGridHighlights(rawUsdm, table);
    console.log('[GridHighlights] Result:', {
      newActivities: result.newActivityIds.size,
      newVisits: result.newVisitIds.size,
      expandedActivities: result.expandedActivities.size,
    });
    return result;
  }, [interpretationComplete, table, rawPerTableUsdm]);

  // Debug: log table structure
  console.log('[SOAAnalysisPage] totalTables:', totalTables, 'selectedTableIndex:', selectedTableIndex);
  console.log('[SOAAnalysisPage] table?.tableId:', (table as any)?.tableId, 'visits:', table?.visits?.length, 'activities:', table?.activities?.length);

  useEffect(() => {
    if (table && !editorState.table) {
      dispatch({ type: "INIT_TABLE", table });
    }
  }, [table, editorState.table]);

  const handleStepClick = (index: number) => {
    const newStatuses = { ...stepStatuses };
    
    for (let i = 0; i < index; i++) {
      newStatuses[wizardSteps[i].id] = "completed";
    }
    newStatuses[wizardSteps[index].id] = "current";
    for (let i = index + 1; i < wizardSteps.length; i++) {
      if (newStatuses[wizardSteps[i].id] !== "completed") {
        newStatuses[wizardSteps[i].id] = "pending";
      }
    }
    
    setStepStatuses(newStatuses);
    setCurrentStep(index);
  };

  const handleNextStep = () => {
    if (currentStep < wizardSteps.length - 1) {
      const newStatuses = { ...stepStatuses };
      newStatuses[wizardSteps[currentStep].id] = "completed";
      newStatuses[wizardSteps[currentStep + 1].id] = "current";
      setStepStatuses(newStatuses);
      setCurrentStep(currentStep + 1);
    }
  };

  const handlePrevStep = () => {
    if (currentStep > 0) {
      handleStepClick(currentStep - 1);
    }
  };

  const handleCellClick = (rowIndex: number, colIndex: number) => {
    setSelectedCell({ row: rowIndex, col: colIndex });

    const cell = editorState.table?.grid[rowIndex]?.cells[colIndex] || table?.matrix.grid[rowIndex]?.cells[colIndex];

    // Use cell's own provenance if available, otherwise fall back to table's pageRange
    if (cell?.provenance?.pageNumber) {
      setPageNumber(cell.provenance.pageNumber);
    } else if (table?.pageRange?.start) {
      setPageNumber(table.pageRange.start);
    }
  };

  // Handle field updates in the SOA table
  const handleSOAFieldUpdate = useCallback((path: string, value: string) => {
    if (!extraction) return;

    // Deep clone the extraction data
    const updatedExtraction = JSON.parse(JSON.stringify(extraction)) as SOAExtraction;

    // Parse the path (e.g., "tables.0.visits.1.displayName")
    const pathParts = path.split(".");
    let current: any = updatedExtraction;

    for (let i = 0; i < pathParts.length - 1; i++) {
      const part = pathParts[i];
      const index = parseInt(part, 10);
      if (!isNaN(index)) {
        current = current[index];
      } else {
        current = current[part];
      }
      if (current === undefined) {
        console.error(`Invalid path: ${path}`);
        return;
      }
    }

    // Set the final value
    const finalKey = pathParts[pathParts.length - 1];
    const finalIndex = parseInt(finalKey, 10);
    let finalValue: string | number | string[] = value;

    if (!isNaN(finalIndex)) {
      current[finalIndex] = value;
    } else {
      // Handle timing.value which expects a number
      if (finalKey === "value" && pathParts.includes("timing")) {
        finalValue = parseInt(value, 10);
        current[finalKey] = finalValue;
      } else if (finalKey === "footnoteRefs") {
        // Handle footnoteRefs which is an array - parse JSON string
        try {
          finalValue = JSON.parse(value);
          current[finalKey] = finalValue;
        } catch {
          // If not valid JSON, treat as comma-separated string
          finalValue = value.split(',').map(s => s.trim()).filter(Boolean);
          current[finalKey] = finalValue;
        }
      } else {
        current[finalKey] = value;
      }
    }

    // Update local state immediately for responsive UI
    setExtraction(updatedExtraction);

    // Persist to backend soa_jobs table (usdm_data and extraction_review columns)
    if (soaJobId) {
      api.soa.updateField(soaJobId, path, finalValue, 'user')
        .then(() => {
          console.log(`[SOA] Persisted field update to backend: ${path} = ${finalValue}`);
          toast({
            title: "Field Updated",
            description: `Updated ${path.split('.').pop()}`,
            duration: 2000,
          });
        })
        .catch((error) => {
          console.error(`[SOA] Failed to persist field update to backend:`, error);
          toast({
            title: "Update Failed",
            description: "Failed to save changes to database",
            variant: "destructive",
            duration: 3000,
          });
        });
    } else if (document?.id) {
      // Fallback to frontend usdm_documents table if no soaJobId
      const dbPath = `soa.${path}`;
      fieldUpdate.mutate(
        { path: dbPath, value: finalValue },
        {
          onSuccess: () => {
            console.log(`[SOA] Persisted field update: ${dbPath} = ${finalValue}`);
            toast({
              title: "Field Updated",
              description: `Updated ${path.split('.').pop()}`,
              duration: 2000,
            });
          },
          onError: (error) => {
            console.error(`[SOA] Failed to persist field update:`, error);
            toast({
              title: "Update Failed",
              description: "Failed to save changes to database",
              variant: "destructive",
              duration: 3000,
            });
          },
        }
      );
    } else {
      console.log(`[SOA] Updated field locally (no soaJobId or document): ${path} = ${value}`);
    }
  }, [extraction, soaJobId, document?.id, fieldUpdate, toast]);

  // Handle adding a new footnote to the current table
  const handleAddFootnote = useCallback((newFootnote: any) => {
    if (!extraction) return;

    // Deep clone the extraction data
    const updatedExtraction = JSON.parse(JSON.stringify(extraction)) as SOAExtraction;
    const table = updatedExtraction.tables[selectedTableIndex];

    if (!table) {
      console.error(`[SOA] Table not found at index ${selectedTableIndex}`);
      return;
    }

    // Initialize footnotes array if not present
    if (!table.footnotes) {
      table.footnotes = [];
    }

    // Add the new footnote
    table.footnotes.push(newFootnote);

    // Update extraction summary if exists
    if (updatedExtraction.extractionSummary) {
      updatedExtraction.extractionSummary.totalFootnotes =
        (updatedExtraction.extractionSummary.totalFootnotes || 0) + 1;
    }

    // Update local state immediately for responsive UI
    setExtraction(updatedExtraction);

    // Persist to backend soa_jobs table
    if (soaJobId) {
      const path = `tables.${selectedTableIndex}.footnotes`;
      api.soa.updateField(soaJobId, path, table.footnotes, 'user')
        .then(() => {
          console.log(`[SOA] Persisted new footnote to backend`);
          toast({
            title: "Footnote Added",
            description: `Added footnote "${newFootnote.marker}"`,
            duration: 2000,
          });
        })
        .catch((error) => {
          console.error(`[SOA] Failed to persist new footnote to backend:`, error);
          toast({
            title: "Failed to Add Footnote",
            description: "Failed to save footnote to database",
            variant: "destructive",
            duration: 3000,
          });
        });
    } else {
      toast({
        title: "Footnote Added",
        description: `Added footnote "${newFootnote.marker}" (local only)`,
        duration: 2000,
      });
    }
  }, [extraction, selectedTableIndex, soaJobId, toast]);

  const handleDeleteFootnote = useCallback((footnoteId: string) => {
    if (!extraction) return;

    // Deep clone the extraction data
    const updatedExtraction = JSON.parse(JSON.stringify(extraction)) as SOAExtraction;
    const table = updatedExtraction.tables[selectedTableIndex];

    if (!table) {
      console.error(`[SOA] Table not found at index ${selectedTableIndex}`);
      return;
    }

    if (!table.footnotes) return;

    // Find and remove the footnote by ID
    const footnoteIndex = table.footnotes.findIndex((f: any) => f.id === footnoteId);
    if (footnoteIndex < 0) {
      console.error(`[SOA] Footnote not found: ${footnoteId}`);
      return;
    }

    const removedFootnote = table.footnotes[footnoteIndex];
    table.footnotes.splice(footnoteIndex, 1);

    // Update extraction summary if exists
    if (updatedExtraction.extractionSummary) {
      updatedExtraction.extractionSummary.totalFootnotes =
        Math.max(0, (updatedExtraction.extractionSummary.totalFootnotes || 0) - 1);
    }

    // Update local state immediately for responsive UI
    setExtraction(updatedExtraction);

    // Persist to backend soa_jobs table
    if (soaJobId) {
      const path = `tables.${selectedTableIndex}.footnotes`;
      api.soa.updateField(soaJobId, path, table.footnotes, 'user')
        .then(() => {
          console.log(`[SOA] Persisted footnote deletion to backend`);
          toast({
            title: "Footnote Deleted",
            description: `Removed footnote "${(removedFootnote as any).marker}"`,
            duration: 2000,
          });
        })
        .catch((error) => {
          console.error(`[SOA] Failed to persist footnote deletion to backend:`, error);
          toast({
            title: "Failed to Delete Footnote",
            description: "Failed to save change to database",
            variant: "destructive",
            duration: 3000,
          });
        });
    } else {
      toast({
        title: "Footnote Deleted",
        description: `Removed footnote "${(removedFootnote as any).marker}" (local only)`,
        duration: 2000,
      });
    }
  }, [extraction, selectedTableIndex, soaJobId, toast]);

  const toggleDataExpanded = () => {
    setDataExpanded(!dataExpanded);
    if (!dataExpanded) setPdfExpanded(false);
  };

  const togglePdfExpanded = () => {
    setPdfExpanded(!pdfExpanded);
    if (!pdfExpanded) setDataExpanded(false);
  };

  const downloadJsonBlob = (data: any, filename: string) => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = window.document.createElement("a");
    link.href = url;
    link.download = filename;
    window.document.body.appendChild(link);
    link.click();
    window.document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportExtractedUSDM = async () => {
    try {
      // Build combined raw USDM from per-table raw data
      let data: any = null;
      if (Object.keys(rawPerTableUsdm).length > 0) {
        data = {
          protocolId: studyId,
          type: "extracted",
          tables: Object.entries(rawPerTableUsdm).map(([tableId, usdm]) => ({
            tableId,
            usdm,
          })),
        };
      } else if (rawUsdmData) {
        data = rawUsdmData;
      }
      if (!data) throw new Error("No extracted USDM data available");

      downloadJsonBlob(data, `${studyId}_soa_extracted.json`);
      toast({ title: "Export Successful", description: `Downloaded ${studyId}_soa_extracted.json`, duration: 3000 });
    } catch (error) {
      console.error("Export failed:", error);
      toast({ title: "Export Failed", description: "No extracted USDM data available yet", variant: "destructive", duration: 3000 });
    }
  };

  const handleExportInterpretedUSDM = async () => {
    try {
      if (!soaJobId) throw new Error("No SOA job available");

      let data: any = null;

      // Try merged USDM first (populated after merge plan confirmation)
      try {
        const results = await api.soa.getResults(soaJobId);
        if (results.usdm_data && results.usdm_data.type === "merged_interpreted") {
          data = results.usdm_data;
        }
      } catch {
        // Job-level usdm_data not available, fall back to per-table
      }

      // Fallback: assemble from per-table interpreted USDMs
      if (!data) {
        const perTableResults = await api.soa.getPerTableResults(soaJobId);
        const interpretedTables = perTableResults.tables
          .filter(t => t.usdm_data)
          .map(t => ({ tableId: t.table_id, usdm: t.usdm_data }));

        if (interpretedTables.length === 0) throw new Error("No interpreted USDM data available");

        data = {
          protocolId: studyId,
          type: "interpreted",
          tables: interpretedTables,
        };
      }

      downloadJsonBlob(data, `${studyId}_soa_interpreted.json`);
      toast({ title: "Export Successful", description: `Downloaded ${studyId}_soa_interpreted.json`, duration: 3000 });
    } catch (error) {
      console.error("Export failed:", error);
      toast({ title: "Export Failed", description: "No interpreted USDM data available yet", variant: "destructive", duration: 3000 });
    }
  };

  // Phase-specific loading messages
  const getPhaseMessage = () => {
    switch (soaState) {
      case 'detecting_pages':
        return 'Detecting SOA pages in PDF...';
      case 'extracting':
        return 'Extracting table data from PDF...';
      case 'analyzing_merges':
        return 'Analyzing table merge candidates...';
      case 'awaiting_merge_confirmation':
        return 'Waiting for merge plan confirmation...';
      case 'classifying':
        return 'Running table classification...';
      case 'awaiting_classification_review':
        return 'Waiting for classification review...';
      case 'interpreting_tables':
        return 'Running 12-stage interpretation pipeline...';
      case 'interpreting':
        return 'Running 12-stage interpretation pipeline...';
      case 'validating':
        return 'Validating extraction results...';
      default:
        return 'Loading SOA data...';
    }
  };

  // Show error if no protocol is specified
  if (!studyId) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center max-w-md">
          <FileWarning className="w-12 h-12 text-amber-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-800 mb-2">No Protocol Selected</h2>
          <p className="text-muted-foreground mb-4">
            Please select a protocol from the main page to view SOA Analysis.
          </p>
          <Button onClick={() => navigate('/')}>
            Go to Protocol List
          </Button>
        </div>
      </div>
    );
  }

  // Show loading state with phase-specific message
  if (loading && !showPageConfirmModal && !showMergeConfirmation) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center max-w-md">
          <Loader2 className="w-10 h-10 animate-spin mx-auto text-primary mb-4" />
          <p className="text-lg font-medium text-gray-800 mb-2">{getPhaseMessage()}</p>
          {phaseProgress && (
            <div className="mt-4 space-y-3">
              {/* Stage indicator for interpretation phase */}
              {(phaseProgress.phase === 'interpretation' || phaseProgress.phase === 'interpreting_tables') && phaseProgress.current_stage && (
                <div className="text-sm">
                  <p className="font-medium text-gray-700">
                    Stage {phaseProgress.current_stage}/12: {phaseProgress.current_stage_name || `Stage ${phaseProgress.current_stage}`}
                  </p>
                  {phaseProgress.tables_total && phaseProgress.tables_total > 1 && (
                    <p className="text-xs text-gray-500 mt-1">
                      Table {(phaseProgress.tables_completed || 0) + 1} of {phaseProgress.tables_total}
                      {phaseProgress.current_table && ` (${phaseProgress.current_table})`}
                    </p>
                  )}
                  {phaseProgress.groups_total && phaseProgress.groups_total > 1 && (
                    <p className="text-xs text-gray-500 mt-1">
                      Group {(phaseProgress.groups_completed || 0) + 1} of {phaseProgress.groups_total}
                    </p>
                  )}
                </div>
              )}
              {/* Progress bar */}
              <div className="w-64 mx-auto bg-gray-200 rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all duration-300"
                  style={{ width: `${phaseProgress.progress}%` }}
                />
              </div>
              <p className="text-sm text-muted-foreground capitalize">
                {phaseProgress.phase}: {phaseProgress.progress}%
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Show loading state when awaiting merge confirmation but merge plan not yet loaded
  if (soaState === 'awaiting_merge_confirmation' && !mergePlan) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center max-w-md">
          <Loader2 className="w-10 h-10 animate-spin mx-auto text-primary mb-4" />
          <p className="text-lg font-medium text-gray-800 mb-2">Loading Merge Plan</p>
          <p className="text-sm text-muted-foreground">Please wait...</p>
        </div>
      </div>
    );
  }

  // Page confirmation view with PDF viewer - split layout
  if (showPageConfirmModal) {
    return (
      <div className="flex flex-col h-full bg-gray-50">
        {/* Header */}
        <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-6 h-6 text-green-500" />
            <div>
              <h1 className="text-lg font-semibold text-gray-800">SOA Pages Detected</h1>
              <p className="text-sm text-muted-foreground">
                Verify the detected pages and click on page numbers to preview in PDF
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => handleConfirmPages(false)}
              disabled={editablePages.length === 0}
            >
              <Edit2 className="w-4 h-4 mr-2" />
              Use Edited Pages
            </Button>
            <Button
              onClick={() => handleConfirmPages(true)}
              disabled={detectedPages.length === 0}
            >
              <Check className="w-4 h-4 mr-2" />
              Confirm & Continue
            </Button>
          </div>
        </div>

        {/* Split Panel Layout */}
        <PanelGroup direction="horizontal" className="flex-1">
          {/* Left Panel - Page Cards */}
          <Panel defaultSize={40} minSize={30}>
            <ScrollArea className="h-full">
              <div className="p-6 space-y-4">
                <div className="text-sm text-muted-foreground mb-4">
                  We detected <span className="font-semibold text-gray-800">{editablePages.length}</span> SOA table(s).
                  Click on page numbers to view in PDF.
                </div>

                {editablePages.map((pageInfo, index) => (
                  <Card key={pageInfo.id} className="overflow-hidden">
                    <CardHeader className="py-3 px-4 bg-gray-50 border-b">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base font-semibold">{pageInfo.id}</CardTitle>
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary" className="text-xs">{pageInfo.category}</Badge>
                          {editablePages.length > 1 && (
                            <button
                              onClick={() => {
                                setEditablePages(prev => prev.filter((_, i) => i !== index));
                              }}
                              className="p-1 rounded-full text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                              title="Remove this table"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="p-4">
                      <div className="grid grid-cols-2 gap-4 mb-3">
                        <div>
                          <Label htmlFor={`start-${index}`} className="text-sm text-gray-600">
                            Start Page
                          </Label>
                          <Input
                            id={`start-${index}`}
                            type="number"
                            value={pageInfo.pageStart}
                            onChange={(e) => handlePageEdit(index, 'pageStart', parseInt(e.target.value) || 1)}
                            className="mt-1"
                            min={1}
                          />
                        </div>
                        <div>
                          <Label htmlFor={`end-${index}`} className="text-sm text-gray-600">
                            End Page
                          </Label>
                          <Input
                            id={`end-${index}`}
                            type="number"
                            value={pageInfo.pageEnd}
                            onChange={(e) => handlePageEdit(index, 'pageEnd', parseInt(e.target.value) || 1)}
                            className="mt-1"
                            min={pageInfo.pageStart}
                          />
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        <span className="text-sm text-muted-foreground mr-1">Pages:</span>
                        {pageInfo.pages.map((page) => (
                          <Button
                            key={page}
                            variant={pageNumber === page ? "default" : "outline"}
                            size="sm"
                            className="h-7 px-2 text-xs"
                            onClick={() => setPageNumber(page)}
                          >
                            {page}
                          </Button>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                ))}

                {editablePages.length === 0 && (
                  <div className="text-center py-12 text-muted-foreground">
                    <AlertCircle className="w-10 h-10 mx-auto mb-3 text-gray-400" />
                    <p className="font-medium">No SOA pages detected</p>
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
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => pdfUrl && window.open(pdfUrl, '_blank')}
              >
                <ExternalLink className="w-4 h-4 text-muted-foreground" />
              </Button>
            </div>

            {/* PDF Document */}
            <div className="flex-1 w-full h-full bg-gray-100 overflow-hidden">
              <ScrollArea className="h-full w-full">
                <div className="flex justify-center p-8 min-h-full">
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
                      renderTextLayer={true}
                      renderAnnotationLayer={false}
                    />
                  </Document>
                </div>
              </ScrollArea>
            </div>
          </Panel>
        </PanelGroup>
      </div>
    );
  }

  // Interpretation insights view (embedded InsightsReviewShell)
  if (viewMode === 'interpretation') {
    return <InsightsReviewShell onBack={() => setViewMode('extraction')} initialGroupId={(table as any)?.tableId || null} />;
  }

  // Merge plan confirmation view (Phase 3.5)
  if (viewMode === 'merge_confirmation' && showMergeConfirmation && mergePlan) {
    return (
      <MergePlanConfirmation
        mergePlan={mergePlan}
        pdfUrl={pdfUrl}
        onConfirm={handleConfirmMergePlan}
        onCancel={handleCancelMergePlan}
      />
    );
  }

  // Completion summary view
  if (viewMode === 'completion' && soaState === 'completed') {
    return (
      <SOACompletionSummary
        studyId={studyId || ''}
        extraction={extraction}
        mergePlan={mergePlan}
        mergedResults={mergedResults}
        onExportExtracted={handleExportExtractedUSDM}
        onExportInterpreted={handleExportInterpretedUSDM}
        onViewDetails={() => {
          setCurrentStep(wizardSteps.length - 1);
          setViewMode('extraction');
        }}
      />
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center max-w-md">
          <AlertCircle className="w-10 h-10 text-red-500 mx-auto mb-4" />
          <p className="text-lg font-medium text-gray-800 mb-2">SOA Extraction Failed</p>
          <p className="text-muted-foreground mb-4">{error}</p>
          <Button onClick={() => window.location.reload()} variant="outline">
            Retry
          </Button>
        </div>
      </div>
    );
  }

  if (!extraction || !table) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <AlertCircle className="w-8 h-8 text-gray-500 mx-auto mb-4" />
          <p className="text-gray-700 font-semibold mb-2">No SOA data available</p>
          <p className="text-muted-foreground">Extraction may still be in progress.</p>
        </div>
      </div>
    );
  }

  const currentStepData = wizardSteps[currentStep];

  return (
    <>
    <div className="flex flex-col h-full bg-gray-50">
      <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold text-gray-800">SOA Analysis</h1>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="h-9 px-3 text-sm font-medium text-gray-700 hover:bg-gray-100 hover:text-gray-900 hover:border-gray-400 transition-colors"
            >
              <Download className="h-4 w-4 mr-2" />
              Export USDM
              <ChevronDown className="h-3.5 w-3.5 ml-1.5 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={handleExportExtractedUSDM}
              disabled={Object.keys(rawPerTableUsdm).length === 0 && !rawUsdmData}
            >
              <FileText className="h-4 w-4 mr-2" />
              Extracted USDM
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={handleExportInterpretedUSDM}
              disabled={!interpretationComplete}
            >
              <CheckCircle2 className="h-4 w-4 mr-2" />
              Interpreted USDM
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <WizardStepper
        steps={wizardSteps}
        currentStepIndex={currentStep}
        onStepClick={handleStepClick}
        stepStatuses={stepStatuses}
      />

      <PanelGroup direction="horizontal" className="flex-1">
        <Panel defaultSize={50} minSize={30} className={cn(pdfExpanded && "hidden")}>
          <div className="h-full flex flex-col min-w-0">
            <div className="flex-1 overflow-auto min-w-0">
            <div className="p-6 space-y-6 min-w-0">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-gray-800">{currentStepData.title}</h2>
                  <p className="text-sm text-muted-foreground mt-1">
                    {currentStepData.description}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={toggleDataExpanded}
                    className="h-9 w-9"
                    data-testid="toggle-data-expand"
                  >
                    {dataExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              {currentStep === 0 && extraction?.extractionSummary && (
                <div className="space-y-6">
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <SummaryCard
                      title="Total Tables"
                      value={totalTables}
                      icon={<Table2 className="w-5 h-5" />}
                    />
                    <SummaryCard
                      title="Total Visits"
                      value={extraction.extractionSummary.totalVisits}
                      icon={<Calendar className="w-5 h-5" />}
                    />
                    <SummaryCard
                      title="Total Activities"
                      value={extraction.extractionSummary.totalActivities}
                      icon={<ClipboardCheck className="w-5 h-5" />}
                    />
                    <SummaryCard
                      title="Confidence"
                      value={`${Math.round(extraction.extractionSummary.confidence * 100)}%`}
                      icon={<CheckCircle2 className="w-5 h-5" />}
                      variant="success"
                    />
                  </div>

                  {/* Table Selector Tabs - Show when multiple tables exist */}
                  <TableSelector
                    tables={extraction.tables}
                    selectedIndex={selectedTableIndex}
                    onSelect={setSelectedTableIndex}
                    onPageChange={setPageNumber}
                  />

                  {extraction.extractionSummary?.warnings?.length > 0 && (
                    <Card className="border-gray-300 bg-gray-50">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2 text-gray-800">
                          <AlertCircle className="w-4 h-4" />
                          Extraction Warnings
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="pt-0">
                        <ul className="space-y-1">
                          {extraction.extractionSummary.warnings.map((warning, i) => (
                            <li key={i} className="text-sm text-gray-700">
                              • {warning}
                            </li>
                          ))}
                        </ul>
                      </CardContent>
                    </Card>
                  )}

                  <Card>
                    <CardHeader
                      className="cursor-pointer hover:bg-gray-50 transition-colors"
                      onClick={() => {
                        if (table?.pageRange?.start) {
                          setPageNumber(table.pageRange.start);
                        }
                      }}
                    >
                      <CardTitle className="text-base flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span>{table?.tableId || 'SOA Table'}</span>
                          {table?.category && (
                            <Badge variant="outline" className="text-xs">
                              {table.category.replace('_SOA', '')}
                            </Badge>
                          )}
                          <span className="text-sm font-normal text-muted-foreground">
                            ({table?.visits?.length || 0} visits, {table?.activities?.length || 0} activities)
                          </span>
                        </div>
                        {table?.pageRange && (
                          <span className="text-sm font-normal text-muted-foreground">
                            Pages {table.pageRange.start}-{table.pageRange.end}
                          </span>
                        )}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0" style={{ overflowX: 'auto', maxWidth: '100%' }}>
                      <SOATableGrid
                        table={table}
                        onCellClick={handleCellClick}
                        onFieldUpdate={handleSOAFieldUpdate}
                        tableIndex={selectedTableIndex}
                        selectedCell={selectedCell}
                        highlights={gridHighlights}
                      />
                    </CardContent>
                  </Card>

                  {/* Interpretation Highlights Legend */}
                  {interpretationComplete && gridHighlights && (gridHighlights.newActivityIds.size > 0 || gridHighlights.newVisitIds.size > 0 || gridHighlights.expandedActivities.size > 0) && (
                    <div className="flex items-center gap-4 px-2 py-2 text-xs text-gray-600 bg-gray-50 rounded-lg border border-gray-200">
                      <span className="font-medium text-gray-700">Interpretation Changes:</span>
                      {gridHighlights.expandedActivities.size > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <span className="w-3 h-3 rounded-sm bg-violet-50 border-l-2 border-l-violet-400 border border-violet-200" />
                          {gridHighlights.expandedActivities.size} expanded activit{gridHighlights.expandedActivities.size === 1 ? 'y' : 'ies'}
                        </span>
                      )}
                      {gridHighlights.newActivityIds.size > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <span className="w-3 h-3 rounded-sm bg-green-50 border-l-2 border-l-green-400 border border-green-200" />
                          {gridHighlights.newActivityIds.size} new activit{gridHighlights.newActivityIds.size === 1 ? 'y' : 'ies'}
                        </span>
                      )}
                      {gridHighlights.newVisitIds.size > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <span className="w-3 h-3 rounded-sm bg-green-100 border border-green-300" />
                          {gridHighlights.newVisitIds.size} new visit{gridHighlights.newVisitIds.size === 1 ? '' : 's'}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Interpretation Results - shown below grid when interpretation is complete */}
                  {interpretationComplete && (
                    <InterpretationExpansionPanel
                      jobId={soaJobId}
                      protocolId={studyId}
                      usdmData={rawUsdmData}
                      extraction={extraction}
                      onViewSource={(pageNum: number) => setPageNumber(pageNum)}
                      currentTableId={(table as any)?.tableId}
                      perTableStages={interpretationStagesPerTable}
                      onViewInsights={() => setViewMode('interpretation')}
                    />
                  )}
                </div>
              )}

              {currentStep === 1 && table && (
                <div>
                  {/* Compact table selector for step 1 */}
                  {extraction && (
                    <TableSelector
                      tables={extraction.tables}
                      selectedIndex={selectedTableIndex}
                      onSelect={setSelectedTableIndex}
                      onPageChange={setPageNumber}
                      compact
                    />
                  )}
                  <VisitsTimeline
                    visits={table.visits}
                    activities={table.activities}
                    matrix={table.matrix}
                    footnotes={table.footnotes}
                    onViewSource={setPageNumber}
                  />
                </div>
              )}

              {currentStep === 2 && (
                <div>
                  {/* Compact table selector for step 2 */}
                  {extraction && (
                    <TableSelector
                      tables={extraction.tables}
                      selectedIndex={selectedTableIndex}
                      onSelect={setSelectedTableIndex}
                      onPageChange={setPageNumber}
                      compact
                    />
                  )}
                  <FootnotesPanel
                    footnotes={table?.footnotes || []}
                    onViewSource={setPageNumber}
                    onFieldUpdate={handleSOAFieldUpdate}
                    tableIndex={selectedTableIndex}
                    onAddFootnote={handleAddFootnote}
                    onDeleteFootnote={handleDeleteFootnote}
                    currentPage={pageNumber}
                  />
                </div>
              )}

              <div className="flex items-center justify-between pt-4 border-t">
                <Button
                  variant="outline"
                  onClick={handlePrevStep}
                  disabled={currentStep === 0}
                  data-testid="btn-prev-step"
                >
                  <ChevronLeft className="w-4 h-4 mr-2" />
                  Previous
                </Button>
                {currentStep < wizardSteps.length - 1 ? (
                  <Button onClick={handleNextStep} data-testid="btn-next-step">
                    Next
                    <ChevronRight className="w-4 h-4 ml-2" />
                  </Button>
                ) : soaState === 'awaiting_extraction_review' ? (
                  <Button
                    className="bg-blue-600 hover:bg-blue-700"
                    data-testid="btn-confirm-extraction"
                    onClick={handleConfirmExtraction}
                  >
                    <Check className="w-4 h-4 mr-2" />
                    Confirm &amp; Classify Tables
                  </Button>
                ) : soaState === 'classifying' ? (
                  <Button className="bg-blue-600 relative overflow-hidden" disabled>
                    <div
                      className="absolute inset-y-0 left-0 bg-blue-500 transition-all duration-300 ease-out"
                      style={{ width: `${phaseProgress?.progress ?? 0}%` }}
                    />
                    <span className="relative z-10 flex items-center">
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Classifying Tables...{phaseProgress?.progress != null ? ` ${Math.round(phaseProgress.progress)}%` : ''}
                    </span>
                  </Button>
                ) : soaState === 'awaiting_classification_review' ? (
                  <Button
                    className="bg-purple-600 hover:bg-purple-700"
                    onClick={() => setShowClassificationReview(true)}
                  >
                    <Check className="w-4 h-4 mr-2" />
                    Review Classification
                  </Button>
                ) : soaState === 'awaiting_merge_review' ? (
                  <Button
                    className="bg-blue-600 hover:bg-blue-700"
                    data-testid="btn-proceed-merge"
                    onClick={handleCompleteReview}
                  >
                    <Merge className="w-4 h-4 mr-2" />
                    Proceed to Merge Analysis
                  </Button>
                ) : (
                  <Button
                    className="bg-gray-800 hover:bg-gray-900"
                    data-testid="btn-complete"
                    onClick={handleCompleteReview}
                  >
                    <Check className="w-4 h-4 mr-2" />
                    Complete Review
                  </Button>
                )}
              </div>
            </div>
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
                  onClick={() => setPageNumber((p) => p + 1)}
                  className="h-8 w-8"
                  data-testid="btn-pdf-next"
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
                  onClick={() => setScale((s) => Math.min(2.0, s + 0.1))}
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
                data-testid="btn-pdf-external"
                onClick={() => pdfUrl && window.open(pdfUrl, '_blank')}
              >
                <ExternalLink className="w-4 h-4 text-muted-foreground" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={togglePdfExpanded}
                data-testid="btn-pdf-expand"
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
                    renderTextLayer={true}
                    renderAnnotationLayer={false}
                  />
                </Document>
              </div>
            </ScrollArea>
          </div>
        </Panel>
      </PanelGroup>
    </div>

    <Dialog open={showClassificationReview && !!classificationReview} onOpenChange={(open) => {
      if (!open) handleCancelClassification();
    }}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col p-6">
        <DialogTitle className="sr-only">Table Classification Review</DialogTitle>
        {classificationReview && (
          <ClassificationReview
            classificationData={classificationReview}
            onConfirm={handleConfirmClassification}
            onCancel={handleCancelClassification}
          />
        )}
      </DialogContent>
    </Dialog>
    </>
  );
}
