import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { insertUsdmDocumentSchema } from "@shared/schema";
import multer from "multer";
import fs from "fs";
import path from "path";
import { createProxyMiddleware } from "http-proxy-middleware";

const UPLOADS_DIR = path.resolve(process.cwd(), "attached_assets");
const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8080";

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 100 * 1024 * 1024 } });

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  if (!fs.existsSync(UPLOADS_DIR)) {
    fs.mkdirSync(UPLOADS_DIR, { recursive: true });
  }

  app.use(
    "/api/backend",
    createProxyMiddleware({
      target: BACKEND_URL,
      changeOrigin: true,
      pathRewrite: { "^/api/backend": "/api/v1" },
      on: {
        error: (err, req, res) => {
          console.error("[PROXY] Backend proxy error:", err.message);
          if ('status' in res && typeof res.status === 'function') {
            (res as any).status(502).json({
              error: "Backend service unavailable",
              message: "The extraction backend is not running. Please ensure the Python backend is started.",
            });
          }
        },
      },
    })
  );

  app.post("/api/protocols/upload", upload.single("file"), async (req, res) => {
    try {
      if (!req.file) {
        return res.status(400).json({ error: "No file uploaded" });
      }

      const file = req.file;
      const baseName = file.originalname.replace(/\.pdf$/i, "").replace(/[^a-zA-Z0-9._-]/g, "_");
      const studyId = baseName;
      const savedFilename = `${baseName}.pdf`;
      const studyTitle = baseName.replace(/_/g, " ");

      const filePath = path.join(UPLOADS_DIR, savedFilename);
      fs.writeFileSync(filePath, file.buffer);

      const existing = await storage.getDocument(studyId);
      if (existing) {
        return res.json({
          id: existing.id,
          studyId: existing.studyId,
          studyTitle: existing.studyTitle,
          message: "Protocol already exists (file updated)",
        });
      }

      const document = await storage.createDocument({
        studyId,
        studyTitle,
        usdmData: {},
        sourceDocumentUrl: `/attached_assets/${savedFilename}`,
      });

      console.log(`[UPLOAD] Protocol uploaded: ${savedFilename} -> document ${document.id}, saved to ${filePath}`);

      res.status(201).json({
        id: document.id,
        studyId: document.studyId,
        studyTitle: document.studyTitle,
        message: "Protocol uploaded successfully",
      });
    } catch (error) {
      console.error("Error uploading protocol:", error);
      res.status(500).json({ error: "Failed to upload protocol" });
    }
  });

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

      const localDoc = await storage.getDocument(studyId);

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
