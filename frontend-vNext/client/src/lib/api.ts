import type { InsertUsdmDocument, UsdmDocument, UsdmEditAudit } from "@shared/schema";

export interface FieldUpdateParams {
  path: string;
  value: any;
  studyId: string;
  studyTitle: string;
  updatedBy: string;
}

export type DocumentSummary = Pick<UsdmDocument, 'id' | 'studyId' | 'studyTitle' | 'createdAt' | 'usdmData'>;

const API_BASE = "";
const BACKEND_API_BASE = `${API_BASE}/api/backend`;

export const getPdfUrl = (studyId: string): string => {
  return `/api/protocols/${encodeURIComponent(studyId)}/pdf`;
};

export const api = {
  documents: {
    getAll: async (): Promise<DocumentSummary[]> => {
      const response = await fetch(`${API_BASE}/api/documents`);
      if (!response.ok) {
        throw new Error(`Failed to fetch documents: ${response.statusText}`);
      }
      return response.json();
    },

    getByStudyId: async (studyId: string): Promise<UsdmDocument> => {
      const response = await fetch(`${API_BASE}/api/documents/${studyId}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch document: ${response.statusText}`);
      }
      return response.json();
    },

    create: async (document: InsertUsdmDocument): Promise<UsdmDocument> => {
      const response = await fetch(`${API_BASE}/api/documents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(document),
      });
      if (!response.ok) {
        throw new Error(`Failed to create document: ${response.statusText}`);
      }
      return response.json();
    },

    // Update a field in the document with audit logging
    updateField: async (documentId: number, params: FieldUpdateParams): Promise<{ success: boolean; message: string }> => {
      const response = await fetch(`${API_BASE}/api/documents/${documentId}/field`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!response.ok) {
        throw new Error(`Failed to update field: ${response.statusText}`);
      }
      return response.json();
    },

    // Get edit history for a document
    getEditHistory: async (documentId: number): Promise<UsdmEditAudit[]> => {
      const response = await fetch(`${API_BASE}/api/documents/${documentId}/edit-history`);
      if (!response.ok) {
        throw new Error(`Failed to fetch edit history: ${response.statusText}`);
      }
      return response.json();
    },
  },

  extraction: {
    startExtraction: async (protocolId: string): Promise<{ job_id: string; protocol_id: string; status: string; message: string }> => {
      const response = await fetch(`${BACKEND_API_BASE}/protocols/${encodeURIComponent(protocolId)}/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume: true }),
      });
      if (!response.ok) {
        throw new Error(`Failed to start extraction: ${response.statusText}`);
      }
      return response.json();
    },

    getJobStatus: async (jobId: string): Promise<any> => {
      const response = await fetch(`${BACKEND_API_BASE}/jobs/${jobId}`);
      if (!response.ok) {
        throw new Error(`Failed to get job status: ${response.statusText}`);
      }
      return response.json();
    },

    getLatestJob: async (protocolId: string): Promise<any> => {
      const response = await fetch(`${BACKEND_API_BASE}/jobs/protocol/${protocolId}/latest`);
      if (!response.ok) {
        throw new Error(`Failed to get latest job: ${response.statusText}`);
      }
      return response.json();
    },
  },

  soa: {
    // Start SOA page detection (Stage 1)
    startExtraction: async (protocolId: string): Promise<SOAStartResponse> => {
      const response = await fetch(`${BACKEND_API_BASE}/protocols/${encodeURIComponent(protocolId)}/soa/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        throw new Error(`Failed to start SOA extraction: ${response.statusText}`);
      }
      return response.json();
    },

    // Get SOA job status
    getJobStatus: async (jobId: string): Promise<SOAJobStatus> => {
      const response = await fetch(`${BACKEND_API_BASE}/soa/jobs/${jobId}/status`);
      if (!response.ok) {
        throw new Error(`Failed to get SOA job status: ${response.statusText}`);
      }
      return response.json();
    },

    // Confirm or correct detected pages (triggers Stage 2)
    confirmPages: async (jobId: string, confirmed: boolean, pages?: SOAPageInfo[]): Promise<{ job_id: string; status: string; message: string }> => {
      const response = await fetch(`${BACKEND_API_BASE}/soa/jobs/${jobId}/confirm-pages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed, pages }),
      });
      if (!response.ok) {
        throw new Error(`Failed to confirm SOA pages: ${response.statusText}`);
      }
      return response.json();
    },

    // Get final SOA results
    getResults: async (jobId: string): Promise<SOAResults> => {
      const response = await fetch(`${BACKEND_API_BASE}/soa/jobs/${jobId}/results`);
      if (!response.ok) {
        throw new Error(`Failed to get SOA results: ${response.statusText}`);
      }
      return response.json();
    },

    // Get latest SOA job for a protocol
    getLatestJob: async (protocolId: string): Promise<SOALatestJob> => {
      const response = await fetch(`${BACKEND_API_BASE}/protocols/${encodeURIComponent(protocolId)}/soa/latest`);
      if (!response.ok) {
        throw new Error(`Failed to get latest SOA job: ${response.statusText}`);
      }
      return response.json();
    },

    // Subscribe to SSE events for real-time progress
    subscribeToEvents: (jobId: string): EventSource => {
      return new EventSource(`${BACKEND_API_BASE}/soa/jobs/${jobId}/events`);
    },

    // Update a specific field in SOA data
    updateField: async (jobId: string, path: string, value: any, updatedBy?: string): Promise<SOAFieldUpdateResponse> => {
      const response = await fetch(`${BACKEND_API_BASE}/soa/jobs/${jobId}/field`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, value, updated_by: updatedBy }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to update SOA field: ${response.statusText}`);
      }
      return response.json();
    },

    // Get per-table results for granular review
    getPerTableResults: async (jobId: string, includeUsdm: boolean = true): Promise<SOAPerTableResults> => {
      const response = await fetch(`${BACKEND_API_BASE}/soa/jobs/${jobId}/tables?include_usdm=${includeUsdm}`);
      if (!response.ok) {
        throw new Error(`Failed to get per-table results: ${response.statusText}`);
      }
      return response.json();
    },

    // Get USDM data for a specific table
    getTableUsdm: async (jobId: string, tableId: string): Promise<SOATableUsdm> => {
      const response = await fetch(`${BACKEND_API_BASE}/soa/jobs/${jobId}/tables/${encodeURIComponent(tableId)}`);
      if (!response.ok) {
        throw new Error(`Failed to get table USDM: ${response.statusText}`);
      }
      return response.json();
    },

    // Trigger merge analysis (Phase 3.5) - call after "Complete Review"
    triggerMergeAnalysis: async (jobId: string): Promise<{ job_id: string; status: string; message: string }> => {
      const response = await fetch(`${BACKEND_API_BASE}/soa/jobs/${jobId}/analyze-merges`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to trigger merge analysis: ${response.statusText}`);
      }
      return response.json();
    },

    // Get merge plan for review (Phase 3.5)
    getMergePlan: async (jobId: string): Promise<MergePlan> => {
      const response = await fetch(`${BACKEND_API_BASE}/soa/jobs/${jobId}/merge-plan`);
      if (!response.ok) {
        throw new Error(`Failed to get merge plan: ${response.statusText}`);
      }
      return response.json();
    },

    // Confirm merge plan and trigger interpretation
    confirmMergePlan: async (jobId: string, confirmation: MergePlanConfirmation): Promise<{ success: boolean; message: string }> => {
      // Transform to snake_case for backend
      const payload = {
        confirmed_groups: confirmation.confirmedGroups.map(g => ({
          id: g.id,
          table_ids: g.tableIds,
          confirmed: g.confirmed,
          user_override: g.userOverride,
        })),
        confirmed_by: 'user',
      };

      const response = await fetch(`${BACKEND_API_BASE}/soa/jobs/${jobId}/merge-plan/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to confirm merge plan: ${response.statusText}`);
      }
      return response.json();
    },

    // Get merge group results after interpretation
    getMergeGroupResults: async (jobId: string): Promise<MergeGroupResult[]> => {
      const response = await fetch(`${BACKEND_API_BASE}/soa/jobs/${jobId}/merge-results`);
      if (!response.ok) {
        throw new Error(`Failed to get merge group results: ${response.statusText}`);
      }
      return response.json();
    },

    // Get interpretation stages for all merge groups
    getInterpretationStages: async (jobId: string, groupId?: string): Promise<InterpretationStagesResponse> => {
      const url = groupId
        ? `${BACKEND_API_BASE}/soa/jobs/${jobId}/interpretation-stages?group_id=${encodeURIComponent(groupId)}`
        : `${BACKEND_API_BASE}/soa/jobs/${jobId}/interpretation-stages`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to get interpretation stages: ${response.statusText}`);
      }
      return response.json();
    },
  },

  eligibility: {
    // Start eligibility section detection (Stage 1 - human-in-the-loop)
    startExtraction: async (protocolId: string): Promise<EligibilityStartResponse> => {
      const response = await fetch(`${BACKEND_API_BASE}/protocols/${encodeURIComponent(protocolId)}/eligibility/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        throw new Error(`Failed to start eligibility extraction: ${response.statusText}`);
      }
      return response.json();
    },

    // Get eligibility job status
    getJobStatus: async (jobId: string): Promise<EligibilityJobStatus> => {
      const response = await fetch(`${BACKEND_API_BASE}/eligibility/jobs/${jobId}`);
      if (!response.ok) {
        throw new Error(`Failed to get eligibility job status: ${response.statusText}`);
      }
      return response.json();
    },

    // Confirm or correct detected sections (triggers full extraction)
    confirmSections: async (
      jobId: string,
      sections: EligibilitySectionInfo[],
      options?: { skipFeasibility?: boolean; useCache?: boolean }
    ): Promise<{ job_id: string; status: string; message: string }> => {
      const response = await fetch(`${BACKEND_API_BASE}/eligibility/jobs/${jobId}/confirm-sections`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          confirmed: true,
          sections: sections,
          skip_feasibility: options?.skipFeasibility ?? false,
          use_cache: options?.useCache ?? true
        }),
      });
      if (!response.ok) {
        throw new Error(`Failed to confirm eligibility sections: ${response.statusText}`);
      }
      return response.json();
    },

    // Get final eligibility results
    getResults: async (jobId: string): Promise<EligibilityResults> => {
      const response = await fetch(`${BACKEND_API_BASE}/eligibility/jobs/${jobId}/results`);
      if (!response.ok) {
        throw new Error(`Failed to get eligibility results: ${response.statusText}`);
      }
      return response.json();
    },

    // Get latest eligibility job for a protocol
    getLatestJob: async (protocolId: string): Promise<EligibilityLatestJob> => {
      const response = await fetch(`${BACKEND_API_BASE}/protocols/${encodeURIComponent(protocolId)}/eligibility/latest`);
      if (!response.ok) {
        throw new Error(`Failed to get latest eligibility job: ${response.statusText}`);
      }
      return response.json();
    },

    // Subscribe to SSE events for real-time progress
    subscribeToEvents: (jobId: string): EventSource => {
      return new EventSource(`${BACKEND_API_BASE}/eligibility/jobs/${jobId}/events`);
    },
  },
};

// SOA Types
export interface SOAPageInfo {
  id: string;
  pageStart: number;
  pageEnd: number;
  category: string;
  pages: number[];
}

export interface SOAStartResponse {
  job_id: string;
  protocol_id: string;
  status: string;
  message: string;
}

export interface SOAJobStatus {
  job_id: string;
  protocol_id: string;
  status: 'detecting_pages' | 'awaiting_page_confirmation' | 'extracting' | 'analyzing_merges' | 'awaiting_merge_confirmation' | 'interpreting' | 'validating' | 'completed' | 'failed';
  current_phase?: string;
  phase_progress?: { phase: string; progress: number };
  detected_pages?: {
    totalSOAs: number;
    tables: SOAPageInfo[];
  };
  merge_plan?: MergePlan;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface SOAResults {
  job_id: string;
  status: string;
  usdm_data?: any;
  quality_report?: any;
  extraction_review?: any;
  interpretation_review?: any;
}

export interface SOALatestJob {
  job_id: string | null;
  status: string;
  detected_pages?: any;
  has_results?: boolean;
  message?: string;
}

export interface SOAFieldUpdateResponse {
  success: boolean;
  message: string;
  job_id: string;
  path: string;
  updated_value: any;
}

export interface SOATableResult {
  id: string;
  table_id: string;
  table_category: string;
  page_start: number;
  page_end: number;
  status: string;
  error_message?: string;
  visits_count: number;
  activities_count: number;
  sais_count: number;
  footnotes_count: number;
  usdm_data?: any;
}

export interface SOAPerTableResults {
  job_id: string;
  status: string;
  total_tables: number;
  successful_tables: number;
  tables: SOATableResult[];
}

export interface SOATableUsdm {
  id: string;
  table_id: string;
  table_category: string;
  page_start: number;
  page_end: number;
  status: string;
  error_message?: string;
  counts: {
    visits: number;
    activities: number;
    sais: number;
    footnotes: number;
  };
  usdm_data?: any;
}

// Eligibility Types

// Section info matching backend Pydantic model (camelCase)
export interface EligibilitySectionInfo {
  id: string;
  type: 'inclusion' | 'exclusion';
  pageStart: number;
  pageEnd: number;
  pages: number[];
  title: string;
  confidence: number;
}

// Wrapper for detected sections response from backend
export interface EligibilityDetectedSections {
  totalSections: number;
  sections: EligibilitySectionInfo[];
  crossReferences?: Array<{
    id: string;
    type: string;
    pages: number[];
  }>;
  geminiFileUri?: string;
}

export interface EligibilityStartResponse {
  job_id: string;
  protocol_id: string;
  status: string;
  message: string;
}

export interface EligibilityJobStatus {
  job_id: string;
  protocol_id: string;
  status: 'detecting_sections' | 'awaiting_section_confirmation' | 'extracting' | 'interpreting' | 'validating' | 'completed' | 'failed';
  current_phase?: string;
  current_stage?: number;
  phase_progress?: { phase: string; progress: number; stage?: number };
  detected_sections?: EligibilityDetectedSections;
  confirmed_sections?: EligibilityDetectedSections;
  counts?: { inclusion: number; exclusion: number; atomic: number; total: number };
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface EligibilityResults {
  job_id: string;
  status: string;
  usdm_data?: {
    criteria?: Array<{
      criterionId: string;
      originalText: string;
      type: 'Inclusion' | 'Exclusion';
      expression?: any;
      atomicCriteria?: any[];
    }>;
  };
  quality_report?: any;
  interpretation_result?: any;
  feasibility_result?: any;
  qeb_result?: {
    qeb_output?: {
      queryableBlocks?: any[];
      atomicCriteria?: any[];
      funnelStages?: any[];
    };
    summary?: any;
  };
  counts?: {
    inclusion: number;
    exclusion: number;
    atomic: number;
    total: number;
  };
}

export interface EligibilityLatestJob {
  protocol_id: string;
  has_job: boolean;
  job_id?: string;
  status?: string;
  current_phase?: string;
  counts?: {
    inclusion: number;
    exclusion: number;
    atomic: number;
    total: number;
  };
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
  message?: string;
}

// Merge Plan Types for Phase 3.5
export interface MergeGroup {
  id: string;                    // "MG-001"
  tableIds: string[];            // ["SOA-1", "SOA-2"]
  mergeType: string;             // "physical_continuation", "standalone", "same_schedule", etc.
  decisionLevel: number;         // 1-8
  confidence: number;            // 0.0-1.0
  reasoning: string;
  confirmed: boolean | null;
  userOverride: UserOverride | null;
  // Additional metadata for display
  pageRanges?: { [tableId: string]: { start: number; end: number } };
  tableCategories?: { [tableId: string]: string };
}

export interface UserOverride {
  action: 'split' | 'merge' | 'remove_table' | 'add_table';
  newGroups?: { tableIds: string[] }[];
  reason?: string;
}

export interface MergePlan {
  protocolId: string;
  analysisTimestamp: string;
  status: 'pending_confirmation' | 'confirmed';
  totalTablesInput: number;
  suggestedMergeGroups: number;
  mergeGroups: MergeGroup[];
  analysisDetails?: {
    pairwiseComparisons: any[];
    levelStatistics: Record<string, number>;
  };
}

export interface ConfirmedGroup {
  id: string;
  tableIds: string[];
  confirmed: boolean;
  userOverride?: UserOverride;
}

export interface MergePlanConfirmation {
  confirmedGroups: ConfirmedGroup[];
}

export interface MergeGroupResult {
  id: string;
  merge_group_id: string;
  source_table_ids: string[];
  merged_usdm?: any;
  interpretation_result?: any;
  status: string;
}

// Interpretation stages response types
export interface StageMetadata {
  name: string;
  description: string;
}

export interface InterpretationSummary {
  success: boolean;
  stages_completed: number;
  stages_failed: number;
  stages_skipped: number;
  total_duration_seconds: number;
  stage_durations: Record<string, number>;
  stage_statuses: Record<string, string>;
}

export interface InterpretationGroupStages {
  merge_group_id: string;
  source_table_ids: string[];
  status: string;
  stage_results: Record<string, any>;
  interpretation_summary: InterpretationSummary;
  counts: {
    visits: number;
    activities: number;
    sais: number;
    footnotes: number;
  };
}

export interface InterpretationStagesResponse {
  job_id: string;
  status: string;
  total_groups?: number;
  merge_group_id?: string;
  stage_metadata: Record<string, StageMetadata>;
  stage_results?: Record<string, any>;
  interpretation_summary?: InterpretationSummary;
  groups?: InterpretationGroupStages[];
}
