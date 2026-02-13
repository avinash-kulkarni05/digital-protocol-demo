import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { insertUsdmDocumentSchema } from "@shared/schema";

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  app.get("/api/documents", async (req, res) => {
    try {
      const documents = await storage.getAllDocumentsSummary();
      res.json(documents);
    } catch (error) {
      console.error("Error fetching documents:", error);
      res.status(500).json({ error: "Failed to fetch documents" });
    }
  });

  app.get("/api/documents/:studyId", async (req, res) => {
    try {
      const { studyId } = req.params;

      // First check if document exists in local table
      let localDoc = await storage.getDocument(studyId);

      // Try to get from backend protocols table (primary source of truth)
      const backendUrl = `http://localhost:8080/api/v1/protocols`;
      const backendResponse = await fetch(backendUrl);

      if (backendResponse.ok) {
        const protocols = await backendResponse.json();
        // Find protocol by studyId (which is filename without .pdf extension)
        const protocol = protocols.find((p: any) =>
          p.studyId === studyId ||
          p.filename === `${studyId}.pdf` ||
          p.filename?.replace('.pdf', '') === studyId
        );

        if (protocol) {
          // Transform backend protocol to frontend document format
          const docStudyId = protocol.studyId || protocol.filename?.replace('.pdf', '');
          const docStudyTitle = protocol.studyTitle || protocol.filename?.replace('.pdf', '').replace(/_/g, ' ');
          const backendUsdmData = protocol.usdmData || {};
          const sourceDocumentUrl = `http://localhost:8080/api/v1/protocols/${encodeURIComponent(docStudyId)}/pdf/annotated`;

          // If document doesn't exist locally, create it so field updates work
          if (!localDoc) {
            console.log(`[ROUTES] Creating local document for studyId: ${docStudyId}`);
            localDoc = await storage.createDocument({
              studyId: docStudyId,
              studyTitle: docStudyTitle,
              usdmData: backendUsdmData,
              sourceDocumentUrl: sourceDocumentUrl,
            });
          }

          // Use localDoc.usdmData if it has been edited (has local changes),
          // otherwise use the backend data as the source of truth.
          // This ensures field updates persist and are returned to the frontend.
          const usdmData = localDoc.usdmData || backendUsdmData;

          // Return document with local ID and local usdmData (so field updates persist)
          const document = {
            id: localDoc.id,
            studyId: docStudyId,
            studyTitle: docStudyTitle,
            usdmData: usdmData,
            sourceDocumentUrl: sourceDocumentUrl,
            createdAt: localDoc.createdAt || new Date().toISOString(),
            updatedAt: localDoc.updatedAt || new Date().toISOString(),
          };
          return res.json(document);
        }
      }

      // Fallback to local usdm_documents table only
      if (!localDoc) {
        return res.status(404).json({ error: "Document not found" });
      }

      res.json(localDoc);
    } catch (error) {
      console.error("Error fetching document:", error);
      res.status(500).json({ error: "Failed to fetch document" });
    }
  });

  app.post("/api/documents", async (req, res) => {
    try {
      const validatedData = insertUsdmDocumentSchema.parse(req.body);
      const document = await storage.createDocument(validatedData);
      res.status(201).json(document);
    } catch (error) {
      console.error("Error creating document:", error);
      res.status(400).json({ error: "Invalid document data" });
    }
  });

  // Update a field in the USDM document (with audit logging)
  app.patch("/api/documents/:id/field", async (req, res) => {
    try {
      const documentId = parseInt(req.params.id);
      console.log(`[FIELD UPDATE] Received request for document ${documentId}:`, req.body);

      if (isNaN(documentId)) {
        console.log("[FIELD UPDATE] Invalid document ID");
        return res.status(400).json({ error: "Invalid document ID" });
      }

      const { path, value, studyId, studyTitle, updatedBy } = req.body;

      if (!path || value === undefined || !updatedBy || !studyId) {
        console.log("[FIELD UPDATE] Missing required fields:", { path, value, updatedBy, studyId });
        return res.status(400).json({
          error: "Missing required fields: path, value, updatedBy, studyId"
        });
      }

      console.log(`[FIELD UPDATE] Updating field '${path}' to '${value}' for document ${documentId}`);
      await storage.updateDocumentField(
        documentId,
        path,
        value,
        updatedBy,
        studyId,
        studyTitle || ""
      );

      console.log("[FIELD UPDATE] Success");
      res.json({ success: true, message: "Field updated successfully" });
    } catch (error) {
      console.error("[FIELD UPDATE] Error:", error);
      res.status(500).json({ error: "Failed to update document field" });
    }
  });

  // Get edit history for a document
  app.get("/api/documents/:id/edit-history", async (req, res) => {
    try {
      const documentId = parseInt(req.params.id);

      if (isNaN(documentId)) {
        return res.status(400).json({ error: "Invalid document ID" });
      }

      const history = await storage.getDocumentEditHistory(documentId);
      res.json(history);
    } catch (error) {
      console.error("Error fetching edit history:", error);
      res.status(500).json({ error: "Failed to fetch edit history" });
    }
  });

  return httpServer;
}
