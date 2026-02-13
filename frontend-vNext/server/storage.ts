import { eq, desc, sql } from "drizzle-orm";
import { db } from "./db";
import {
  usdmDocuments,
  usdmEditAudit,
  type UsdmDocument,
  type InsertUsdmDocument,
  type UsdmEditAudit,
} from "@shared/schema";

export type DocumentSummary = Pick<UsdmDocument, 'id' | 'studyId' | 'studyTitle' | 'createdAt' | 'usdmData'>;

export interface IStorage {
  // USDM Documents
  getDocument(studyId: string): Promise<UsdmDocument | undefined>;
  getDocumentById(id: number): Promise<UsdmDocument | undefined>;
  getAllDocuments(): Promise<UsdmDocument[]>;
  getAllDocumentsSummary(): Promise<DocumentSummary[]>;
  createDocument(doc: InsertUsdmDocument): Promise<UsdmDocument>;

  // Field editing with audit trail
  updateDocumentField(
    documentId: number,
    fieldPath: string,
    newValue: any,
    updatedBy: string,
    studyId: string,
    studyTitle: string,
    changeReason?: string
  ): Promise<void>;
  getDocumentEditHistory(documentId: number): Promise<UsdmEditAudit[]>;
}

export class DatabaseStorage implements IStorage {
  async getDocument(studyId: string): Promise<UsdmDocument | undefined> {
    const docs = await db
      .select()
      .from(usdmDocuments)
      .where(eq(usdmDocuments.studyId, studyId))
      .limit(1);
    return docs[0];
  }

  async createDocument(doc: InsertUsdmDocument): Promise<UsdmDocument> {
    const [document] = await db.insert(usdmDocuments).values(doc).returning();
    return document;
  }

  async getAllDocuments(): Promise<UsdmDocument[]> {
    return db.select().from(usdmDocuments).orderBy(usdmDocuments.createdAt);
  }

  async getAllDocumentsSummary(): Promise<Pick<UsdmDocument, 'id' | 'studyId' | 'studyTitle' | 'createdAt' | 'usdmData'>[]> {
    return db.select({
      id: usdmDocuments.id,
      studyId: usdmDocuments.studyId,
      studyTitle: usdmDocuments.studyTitle,
      createdAt: usdmDocuments.createdAt,
      usdmData: usdmDocuments.usdmData,
    }).from(usdmDocuments).orderBy(usdmDocuments.createdAt);
  }

  async getDocumentById(id: number): Promise<UsdmDocument | undefined> {
    const docs = await db
      .select()
      .from(usdmDocuments)
      .where(eq(usdmDocuments.id, id))
      .limit(1);
    return docs[0];
  }

  /**
   * Update a field in the USDM document and create an audit record with full USDM snapshots.
   * Uses PostgreSQL jsonb_set() for efficient nested field updates.
   */
  async updateDocumentField(
    documentId: number,
    fieldPath: string,
    newValue: any,
    updatedBy: string,
    studyId: string,
    studyTitle: string
  ): Promise<void> {
    // Get the current document to capture original USDM
    const document = await this.getDocumentById(documentId);
    if (!document) {
      throw new Error(`Document with id ${documentId} not found`);
    }

    // Store full original USDM before update
    const originalUsdm = document.usdmData;

    // Extract original field value using the field path
    const pathParts = fieldPath.split('.');
    let originalValue: any = document.usdmData;
    for (const part of pathParts) {
      if (originalValue && typeof originalValue === 'object') {
        originalValue = (originalValue as Record<string, any>)[part];
      } else {
        originalValue = undefined;
        break;
      }
    }

    // Convert path to PostgreSQL array format: "study.name" -> '{study,name}'
    const pgPathArray = `{${pathParts.join(',')}}`;

    // Update the field using jsonb_set
    const serializedValue = JSON.stringify(newValue);

    console.log(`[STORAGE] Updating document ${documentId}, path: ${pgPathArray}, value: ${serializedValue}`);

    // Use sql.raw() for the path array since Drizzle's sql tag would escape it incorrectly
    // Use fully qualified table name to avoid search_path issues with pooled connections
    await db.execute(
      sql`UPDATE usdm_documents
          SET usdm_data = jsonb_set(usdm_data, ${sql.raw(`'${pgPathArray}'`)}::text[], ${serializedValue}::jsonb),
              updated_at = NOW()
          WHERE id = ${documentId}`
    );

    // Fetch the updated document to capture updated USDM
    const updatedDocument = await this.getDocumentById(documentId);
    const updatedUsdm = updatedDocument?.usdmData;

    console.log(`[STORAGE] Update complete, inserting audit record`);

    // Insert audit record with full USDM snapshots
    await db.insert(usdmEditAudit).values({
      documentId,
      studyId,
      studyTitle,
      fieldPath,
      originalValue,
      newValue,
      originalUsdm,
      updatedUsdm,
      updatedBy,
      updatedAt: new Date(),
    });
  }

  /**
   * Get the edit history for a document, ordered by most recent first.
   */
  async getDocumentEditHistory(documentId: number): Promise<UsdmEditAudit[]> {
    return db
      .select()
      .from(usdmEditAudit)
      .where(eq(usdmEditAudit.documentId, documentId))
      .orderBy(desc(usdmEditAudit.updatedAt));
  }
}

export const storage = new DatabaseStorage();
