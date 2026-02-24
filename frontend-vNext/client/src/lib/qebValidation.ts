export interface QebSummary {
  totalQEBs: number;
  inclusionQEBs: number;
  exclusionQEBs: number;
  fullyQueryable: number;
  partiallyQueryable: number;
  requiresManualReview: number;
  totalAtomicsConsolidated: number;
  uniqueOmopConcepts: number;
  deduplicationRate: number;
  killerCriteriaCount: number;
  funnelStagesCount: number;
  eligibilitySectionPages?: {
    start: number;
    end: number;
  };
}

export interface FunnelStage {
  stageId: string;
  stageName: string;
  stageOrder: number;
  qebIds: string[];
  combinedEliminationRate: number;
  stageDescription: string;
}

export interface OmopConcept {
  conceptId: number | null;
  conceptName: string;
  domain: string;
  vocabularyId: string | null;
  conceptCode: string | null;
}

export interface FhirResource {
  resourceType: string;
  searchParams: { query: string } | string;
  description: string | null;
}

export interface Provenance {
  pageNumber: number;
  sectionId: string | null;
  textSnippet: string;
  confidence?: number;
}

export interface QueryableBlock {
  qebId: string;
  originalCriterionId: string;
  criterionType: "inclusion" | "exclusion";
  clinicalName: string;
  clinicalDescription: string;
  clinicalCategory: string;
  funnelStage: string;
  funnelStageOrder: number;
  combinedSql: string;
  sqlLogicExplanation: string;
  queryableStatus: "fully_queryable" | "partially_queryable" | "requires_manual";
  nonQueryableReason: string | null;
  estimatedEliminationRate: number | null;
  isKillerCriterion: boolean;
  epidemiologicalEvidence: string | null;
  atomicIds: string[];
  atomicCount: number;
  internalLogic: "AND" | "OR" | "COMPLEX";
  omopConcepts: OmopConcept[];
  fhirResources: FhirResource[];
  protocolText: string;
  provenance: Provenance;
}

export interface FunnelImpact {
  eliminationRate: number;
  impactScore: number;
  isKillerCriterion: boolean;
}

export interface OmopQuery {
  tableName: string;
  conceptIds: (number | null)[];
  conceptNames: string[];
  vocabularyIds: (string | null)[];
  sqlTemplate: string;
  sqlExecutable: boolean;
  valueConstraint?: string;
}

export interface FhirCode {
  system: string;
  code: string;
  display: string;
}

export interface FhirQuery {
  resourceType: string;
  codes: FhirCode[];
  searchParams: string;
  queryExecutable: boolean;
  valueFilter: string | null;
  dateFilter: string | null;
}

export interface ExecutionContext {
  logicalGroup: string;
  groupLogic: string;
  combineWithPrevious: string;
  isExclusion: boolean;
  sequenceHint: number;
}

export interface QueryabilityClassification {
  category: "QUERYABLE" | "SCREENING_ONLY" | "NOT_APPLICABLE";
  confidence: number;
  reasoning: string;
  overridable: boolean;
}

export interface AtomicCriterion {
  atomicId: string;
  originalCriterionId: string;
  criterionType: "inclusion" | "exclusion";
  atomicText: string;
  normalizedText: string;
  category: string;
  funnelImpact: FunnelImpact;
  omopQuery: OmopQuery | null;
  fhirQuery: FhirQuery | null;
  executionContext: ExecutionContext;
  provenance: Provenance;
  queryableStatus: string;
  nonQueryableReason: string | null;
  queryabilityClassification: QueryabilityClassification;
}

export function isAtomicUnmapped(atomic: AtomicCriterion): boolean {
  if (!atomic.omopQuery) return true;
  if (!atomic.omopQuery.conceptIds || atomic.omopQuery.conceptIds.length === 0) return true;
  return atomic.omopQuery.conceptIds.some(id => id === null || id === 0);
}

export interface ExecutionOrder {
  recommendedSequence: string[];
  killerCriteria: string[];
  manualReviewRequired: string[];
  executionNotes: string;
}

export interface QebValidationData {
  protocolId: string;
  version: string;
  generatedAt: string;
  therapeuticArea: string;
  summary: QebSummary;
  funnelStages: FunnelStage[];
  queryableBlocks: QueryableBlock[];
  atomicCriteria: AtomicCriterion[];
  executionOrder: ExecutionOrder;
}

export interface ClassificationCounts {
  queryable: number;
  screeningOnly: number;
  notApplicable: number;
}

export interface EnrichedAtomic {
  atomic: AtomicCriterion;
  parentGroup: QueryableBlock | null;
  isUnmapped: boolean;
}

export interface ClassificationBuckets {
  queryable: EnrichedAtomic[];
  screeningOnly: EnrichedAtomic[];
  notApplicable: EnrichedAtomic[];
}

export interface DerivedQebData {
  classificationCounts: ClassificationCounts;
  classificationBuckets: ClassificationBuckets;
  unmappedAtomics: AtomicCriterion[];
  qebLookup: Map<string, QueryableBlock>;
  atomicLookup: Map<string, AtomicCriterion>;
  stageQebMap: Map<string, QueryableBlock[]>;
  killerQebs: QueryableBlock[];
}

export function deriveQebData(data: QebValidationData): DerivedQebData {
  // Guard against missing data
  if (!data?.queryableBlocks || !data?.atomicCriteria || !data?.funnelStages) {
    return {
      classificationCounts: { queryable: 0, screeningOnly: 0, notApplicable: 0 },
      classificationBuckets: { queryable: [], screeningOnly: [], notApplicable: [] },
      unmappedAtomics: [],
      qebLookup: new Map(),
      atomicLookup: new Map(),
      stageQebMap: new Map(),
      killerQebs: [],
    };
  }

  const classificationCounts: ClassificationCounts = {
    queryable: 0,
    screeningOnly: 0,
    notApplicable: 0,
  };

  const classificationBuckets: ClassificationBuckets = {
    queryable: [],
    screeningOnly: [],
    notApplicable: [],
  };

  const unmappedAtomics: AtomicCriterion[] = [];
  const qebLookup = new Map<string, QueryableBlock>();
  const atomicLookup = new Map<string, AtomicCriterion>();
  const stageQebMap = new Map<string, QueryableBlock[]>();
  const killerQebs: QueryableBlock[] = [];

  // First pass: build qebLookup
  data.queryableBlocks.forEach((qeb) => {
    qebLookup.set(qeb.qebId, qeb);
    if (qeb.isKillerCriterion) {
      killerQebs.push(qeb);
    }
  });

  // Build atomicId to parent group mapping
  const atomicToGroup = new Map<string, QueryableBlock>();
  data.queryableBlocks.forEach((qeb) => {
    qeb.atomicIds.forEach((atomicId) => {
      atomicToGroup.set(atomicId, qeb);
    });
  });

  // Second pass: process atomics with enriched data
  data.atomicCriteria.forEach((atomic) => {
    atomicLookup.set(atomic.atomicId, atomic);
    const isUnmapped = isAtomicUnmapped(atomic);
    const parentGroup = atomicToGroup.get(atomic.atomicId) || null;
    const enriched: EnrichedAtomic = { atomic, parentGroup, isUnmapped };
    
    switch (atomic.queryabilityClassification.category) {
      case "QUERYABLE":
        classificationCounts.queryable++;
        classificationBuckets.queryable.push(enriched);
        break;
      case "SCREENING_ONLY":
        classificationCounts.screeningOnly++;
        classificationBuckets.screeningOnly.push(enriched);
        break;
      case "NOT_APPLICABLE":
        classificationCounts.notApplicable++;
        classificationBuckets.notApplicable.push(enriched);
        break;
    }

    // Only include unmapped atomics that are QUERYABLE (part of executable queries)
    if (isUnmapped && atomic.queryabilityClassification.category === "QUERYABLE") {
      unmappedAtomics.push(atomic);
    }
  });

  data.funnelStages.forEach((stage) => {
    const qebs = stage.qebIds
      .map((id) => qebLookup.get(id))
      .filter((q): q is QueryableBlock => q !== undefined);
    stageQebMap.set(stage.stageId, qebs);
  });

  return {
    classificationCounts,
    classificationBuckets,
    unmappedAtomics,
    qebLookup,
    atomicLookup,
    stageQebMap,
    killerQebs,
  };
}

export type WizardStep = 
  | "overview"
  | "qeb-overview"
  | "funnel"
  | "assurance"
  | "execute";

export interface WizardState {
  currentStep: WizardStep;
  selectedQebId: string | null;
  overrides: Map<string, QueryabilityClassification["category"]>;
  conceptCorrections: Map<string, number[]>;
  stepsCompleted: Set<WizardStep>;
}

export const WIZARD_STEPS: { id: WizardStep; title: string; description: string }[] = [
  { id: "overview", title: "Criteria Overview", description: "Readiness at a glance" },
  { id: "qeb-overview", title: "Criteria Map", description: "Visualize criteria logic" },
  { id: "assurance", title: "Data Assurance", description: "Fix concepts & classifications" },
  { id: "funnel", title: "Funnel Studio", description: "Review & approve stages" },
  { id: "execute", title: "Execute", description: "Launch with confidence" },
];

export const MOCK_OMOP_SEARCH_RESULTS: Record<string, OmopConcept[]> = {
  "small cell": [
    { conceptId: 4115244, conceptName: "Small cell carcinoma of lung", domain: "Condition", vocabularyId: "SNOMED", conceptCode: "254632001" },
    { conceptId: 4116238, conceptName: "Small cell carcinoma", domain: "Condition", vocabularyId: "SNOMED", conceptCode: "128922002" },
    { conceptId: 46273477, conceptName: "Small cell lung cancer", domain: "Condition", vocabularyId: "ICDO3", conceptCode: "8041/3" },
  ],
  "nsclc": [
    { conceptId: 4115276, conceptName: "Non-small cell lung cancer", domain: "Condition", vocabularyId: "SNOMED", conceptCode: "254637007" },
    { conceptId: 4112738, conceptName: "Adenocarcinoma of lung", domain: "Condition", vocabularyId: "SNOMED", conceptCode: "254626006" },
    { conceptId: 4110589, conceptName: "Large cell carcinoma of lung", domain: "Condition", vocabularyId: "SNOMED", conceptCode: "254629004" },
  ],
  "ecog": [
    { conceptId: 4088397, conceptName: "ECOG performance status grade 0", domain: "Observation", vocabularyId: "SNOMED", conceptCode: "422512005" },
    { conceptId: 4088398, conceptName: "ECOG performance status grade 1", domain: "Observation", vocabularyId: "SNOMED", conceptCode: "422894000" },
    { conceptId: 4088399, conceptName: "ECOG performance status grade 2", domain: "Observation", vocabularyId: "SNOMED", conceptCode: "422512006" },
  ],
  "default": [
    { conceptId: 0, conceptName: "No matching concepts found", domain: "Unknown", vocabularyId: null, conceptCode: null },
  ],
};

export function searchMockOmop(term: string): OmopConcept[] {
  const lowerTerm = term.toLowerCase();
  for (const [key, results] of Object.entries(MOCK_OMOP_SEARCH_RESULTS)) {
    if (key !== "default" && lowerTerm.includes(key)) {
      return results;
    }
  }
  return MOCK_OMOP_SEARCH_RESULTS.default;
}
