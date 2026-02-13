import { pgTable, text, varchar, timestamp, jsonb, serial, integer } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const usdmDocuments = pgTable("usdm_documents", {
  id: serial("id").primaryKey(),
  studyId: varchar("study_id", { length: 255 }).notNull().unique(),
  studyTitle: text("study_title").notNull(),
  usdmData: jsonb("usdm_data").notNull(),
  sourceDocumentUrl: text("source_document_url").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

// Audit table to track all field edits with full USDM snapshots
export const usdmEditAudit = pgTable("usdm_edit_audit", {
  id: serial("id").primaryKey(),
  documentId: integer("document_id").notNull().references(() => usdmDocuments.id),
  studyId: varchar("study_id", { length: 255 }).notNull(), // For easy identification
  studyTitle: text("study_title"), // Protocol name for easy identification
  fieldPath: varchar("field_path", { length: 500 }).notNull(), // e.g., "study.name"
  originalValue: jsonb("original_value"), // Field value before edit
  newValue: jsonb("new_value"), // Field value after edit
  originalUsdm: jsonb("original_usdm"), // Complete USDM before edit
  updatedUsdm: jsonb("updated_usdm"), // Complete USDM after edit
  updatedBy: varchar("updated_by", { length: 255 }).notNull(), // Who made the change
  updatedAt: timestamp("updated_at").defaultNow().notNull(), // When the change was made
});

export const insertUsdmDocumentSchema = createInsertSchema(usdmDocuments).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export type InsertUsdmDocument = z.infer<typeof insertUsdmDocumentSchema>;
export type UsdmDocument = typeof usdmDocuments.$inferSelect;
export type UsdmEditAudit = typeof usdmEditAudit.$inferSelect;

export const soaProvenanceSchema = z.object({
  tableId: z.string().optional(),
  pageNumber: z.number(),
  cellCoords: z.array(z.number()).optional(),
  colIdx: z.number().optional(),
  textSnippet: z.string().optional(),
  source: z.string().optional(),
  jsonPath: z.string().optional(),
  rationale: z.string().optional(),
});

export const soaTimingSchema = z.object({
  value: z.number().nullable(),
  unit: z.string(),
  relativeTo: z.string(),
  provenance: soaProvenanceSchema.optional(),
});

export const soaWindowSchema = z.object({
  earlyBound: z.number(),
  lateBound: z.number(),
  type: z.string(),
  description: z.string(),
  provenance: soaProvenanceSchema.optional(),
}).nullable();

export const soaVisitSchema = z.object({
  id: z.string(),
  columnIndex: z.number(),
  displayName: z.string(),
  originalText: z.string(),
  timing: soaTimingSchema.optional(),
  window: soaWindowSchema.optional(),
  footnoteRefs: z.array(z.string()),
  provenance: soaProvenanceSchema,
  timingModifier: z.string().nullable().optional(),
  parentVisit: z.string().nullable().optional(),
});

export const soaActivitySchema = z.object({
  id: z.string(),
  rowIndex: z.number(),
  displayName: z.string(),
  originalText: z.string(),
  category: z.string().nullable(),
  footnoteRefs: z.array(z.string()),
  provenance: soaProvenanceSchema,
});

export const soaCellSchema = z.object({
  visitId: z.string(),
  value: z.string(),
  footnoteRefs: z.array(z.string()),
  rawContent: z.string(),
  provenance: soaProvenanceSchema,
});

export const soaMatrixRowSchema = z.object({
  activityId: z.string(),
  activityName: z.string(),
  cells: z.array(soaCellSchema),
});

export const soaEdcImpactSchema = z.object({
  affectsScheduling: z.boolean().optional(),
  affectsBranching: z.boolean().optional(),
  isInformational: z.boolean().optional(),
});

export const soaFootnoteSchema = z.object({
  id: z.string(),
  marker: z.string(),
  text: z.string(),
  ruleType: z.string().optional(),
  category: z.union([z.string(), z.array(z.string())]).optional(),
  subcategory: z.string().optional(),
  classificationReasoning: z.string().optional(),
  edcImpact: soaEdcImpactSchema.optional(),
  provenance: soaProvenanceSchema.optional(),
});

export const soaTableSchema = z.object({
  tableId: z.string(),
  tableName: z.string(),
  category: z.string(),
  pageRange: z.object({
    start: z.number(),
    end: z.number(),
  }),
  pdfImageUrls: z.array(z.string()).optional(),
  visits: z.array(soaVisitSchema),
  activities: z.array(soaActivitySchema),
  matrix: z.object({
    description: z.string(),
    legend: z.record(z.string()),
    grid: z.array(soaMatrixRowSchema),
  }),
  footnotes: z.array(soaFootnoteSchema).optional(),
});

export const soaExtractionSchema = z.object({
  schemaVersion: z.string(),
  reviewType: z.string(),
  protocolId: z.string(),
  protocolTitle: z.string(),
  generatedAt: z.string(),
  extractionSummary: z.object({
    totalTables: z.number(),
    totalVisits: z.number(),
    totalActivities: z.number(),
    totalScheduledInstances: z.number(),
    totalFootnotes: z.number(),
    confidence: z.number(),
    warnings: z.array(z.string()),
  }),
  tables: z.array(soaTableSchema),
});

export const interpretationProvenanceSchema = z.object({
  source: z.string().optional(),
  jsonPath: z.string().optional(),
  pageNumber: z.number().optional(),
  textSnippet: z.string().optional(),
  rationale: z.string().optional(),
});

export const interpretationComponentSchema = z.object({
  id: z.string(),
  name: z.string(),
  isRequired: z.boolean().optional(),
  order: z.number().optional(),
  confidence: z.number().optional(),
  cdashDomain: z.string().optional(),
  unit: z.string().optional(),
  instanceType: z.string().optional(),
  cdiscDomain: z.string().nullable().optional(),
  _alternativeResolution: z.object({
    originalActivityId: z.string().optional(),
    originalActivityName: z.string().optional(),
    alternativeType: z.string().optional(),
    alternativeIndex: z.number().optional(),
    alternativeCount: z.number().optional(),
    confidence: z.number().optional(),
    rationale: z.string().optional(),
    stage: z.string().optional(),
    model: z.string().optional(),
    timestamp: z.string().optional(),
    source: z.string().optional(),
    cacheHit: z.boolean().optional(),
    cacheKey: z.string().optional(),
  }).optional(),
  provenance: interpretationProvenanceSchema.optional(),
});

export const alternativeOptionSchema = z.object({
  resolution: z.string(),
  reasoning: z.string(),
});

export const interpretationItemSchema = z.object({
  itemId: z.string().optional(),
  activityId: z.string().optional(),
  activityName: z.string().optional(),
  type: z.string().optional(),
  confidence: z.number().optional(),
  status: z.enum(["PENDING", "APPROVED", "REJECTED", "FLAGGED", "AUTO_APPROVED"]).optional(),
  reasoning: z.string().optional(),
  source: z.string().optional(),
  isCritical: z.boolean().optional(),
  components: z.array(interpretationComponentSchema).optional(),
  alternatives: z.array(alternativeOptionSchema).optional(),
  specimen: z.object({
    specimenType: z.string().optional(),
    tubeType: z.string().optional(),
    volume: z.string().optional(),
    instructions: z.string().optional(),
  }).optional(),
  proposal: z.object({
    components: z.array(interpretationComponentSchema).optional(),
    specimenType: z.string().optional(),
    tubeType: z.string().optional(),
    volume: z.string().optional(),
    instructions: z.string().optional(),
    condition: z.string().optional(),
    conditionType: z.string().optional(),
    appliesTo: z.string().optional(),
    alternative1: z.string().optional(),
    alternative2: z.string().optional(),
    resolution: z.string().optional(),
    reasoning: z.string().optional(),
    expandedActivities: z.array(interpretationComponentSchema).optional(),
    structuredRule: z.object({
      appliesTo: z.array(z.string()).optional(),
    }).optional(),
    provenance: interpretationProvenanceSchema.optional(),
  }).optional(),
  context: z.object({
    originalText: z.string().optional(),
    sourceFootnote: z.record(z.any()).optional(),
  }).optional(),
  userDecision: z.any().nullable().optional(),
  provenance: interpretationProvenanceSchema.optional(),
});

export const soaWizardStepSchema = z.object({
  stepNumber: z.number(),
  stepId: z.string(),
  title: z.string(),
  description: z.string(),
  icon: z.string(),
  status: z.enum(["COMPLETED", "PENDING", "IN_PROGRESS", "AUTO_APPROVED"]),
  progress: z.object({
    reviewed: z.number(),
    total: z.number(),
  }),
  isCritical: z.boolean().optional(),
  autoApprovedItems: z.array(interpretationItemSchema).optional(),
  reviewItems: z.array(interpretationItemSchema).optional(),
});

export const wizardActionsSchema = z.object({
  allowedOperations: z.array(z.string()),
  completionRequired: z.object({
    criticalItems: z.boolean(),
    allItems: z.boolean(),
  }),
  nextStep: z.string(),
});

export const soaInterpretationSchema = z.object({
  schemaVersion: z.string(),
  reviewType: z.string(),
  protocolId: z.string(),
  protocolTitle: z.string(),
  generatedAt: z.string(),
  wizardConfig: z.object({
    totalSteps: z.number(),
    autoApproveThreshold: z.number(),
    allowBatchOperations: z.boolean(),
    allowSkipToEnd: z.boolean(),
  }),
  summary: z.object({
    totalItems: z.number(),
    autoApproved: z.number(),
    pendingReview: z.number(),
    byCategory: z.record(z.object({
      total: z.number(),
      autoApproved: z.number(),
      pending: z.number(),
    })),
  }),
  steps: z.array(soaWizardStepSchema),
  wizardActions: wizardActionsSchema.optional(),
});

export type SOAProvenance = z.infer<typeof soaProvenanceSchema>;
export type SOAVisit = z.infer<typeof soaVisitSchema>;
export type SOAActivity = z.infer<typeof soaActivitySchema>;
export type SOACell = z.infer<typeof soaCellSchema>;
export type SOAMatrixRow = z.infer<typeof soaMatrixRowSchema>;
export type SOAFootnote = z.infer<typeof soaFootnoteSchema>;
export type SOATable = z.infer<typeof soaTableSchema>;
export type SOAExtraction = z.infer<typeof soaExtractionSchema>;
export type SOAWizardStep = z.infer<typeof soaWizardStepSchema>;
export type SOAInterpretation = z.infer<typeof soaInterpretationSchema>;
export type InterpretationItem = z.infer<typeof interpretationItemSchema>;
export type InterpretationComponent = z.infer<typeof interpretationComponentSchema>;
export type InterpretationProvenance = z.infer<typeof interpretationProvenanceSchema>;
export type AlternativeOption = z.infer<typeof alternativeOptionSchema>;
export type WizardActions = z.infer<typeof wizardActionsSchema>;
