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
      pathRewrite: { "^/": "/api/v1/" },
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

      // Also register with Python backend for extraction support
      try {
        const FormData = (await import("form-data")).default;
        const backendForm = new FormData();
        backendForm.append("file", file.buffer, { filename: savedFilename, contentType: "application/pdf" });

        const backendResponse = await fetch(`${BACKEND_URL}/api/v1/protocols/upload`, {
          method: "POST",
          body: backendForm as any,
          headers: backendForm.getHeaders(),
        });
        if (backendResponse.ok) {
          const backendData = await backendResponse.json() as any;
          console.log(`[UPLOAD] Registered with Python backend: protocol_id=${backendData.id}`);
        } else {
          console.warn(`[UPLOAD] Python backend registration failed (${backendResponse.status}), extraction may not work`);
        }
      } catch (err: any) {
        console.warn(`[UPLOAD] Could not register with Python backend: ${err.message}`);
      }

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

  app.get("/api/protocols/:studyId/pdf", async (req, res) => {
    try {
      const { studyId } = req.params;
      const sanitized = studyId.replace(/[^a-zA-Z0-9._-]/g, "_");
      const filename = `${sanitized}.pdf`;
      const filePath = path.join(UPLOADS_DIR, filename);

      if (fs.existsSync(filePath)) {
        res.setHeader("Content-Type", "application/pdf");
        res.setHeader("Cache-Control", "no-cache");
        return res.sendFile(filePath);
      }

      const directPath = path.join(UPLOADS_DIR, `${studyId}.pdf`);
      if (fs.existsSync(directPath)) {
        res.setHeader("Content-Type", "application/pdf");
        res.setHeader("Cache-Control", "no-cache");
        return res.sendFile(directPath);
      }

      const files = fs.readdirSync(UPLOADS_DIR).filter(f => f.endsWith('.pdf'));
      const match = files.find(f => f.toLowerCase() === `${sanitized}.pdf`.toLowerCase());
      if (match) {
        res.setHeader("Content-Type", "application/pdf");
        res.setHeader("Cache-Control", "no-cache");
        return res.sendFile(path.join(UPLOADS_DIR, match));
      }

      try {
        const backendUrl = `${BACKEND_URL}/api/v1/protocols/${encodeURIComponent(studyId)}/pdf`;
        const backendRes = await fetch(backendUrl);
        if (backendRes.ok) {
          const pdfBuffer = Buffer.from(await backendRes.arrayBuffer());
          res.setHeader("Content-Type", "application/pdf");
          res.setHeader("Cache-Control", "no-cache");
          if (backendRes.headers.get("Content-Disposition")) {
            res.setHeader("Content-Disposition", backendRes.headers.get("Content-Disposition")!);
          }
          return res.send(pdfBuffer);
        }
      } catch (backendErr) {
        console.error("Backend PDF fetch failed:", backendErr);
      }

      res.status(404).json({ error: "PDF not found" });
    } catch (error) {
      console.error("Error serving PDF:", error);
      res.status(500).json({ error: "Failed to serve PDF" });
    }
  });

  app.get("/api/protocols/:studyId/pdf/annotated", async (req, res) => {
    try {
      const { studyId } = req.params;
      const backendUrl = `${BACKEND_URL}/api/v1/protocols/${encodeURIComponent(studyId)}/pdf/annotated`;
      const backendRes = await fetch(backendUrl);
      if (backendRes.ok) {
        const pdfBuffer = Buffer.from(await backendRes.arrayBuffer());
        res.setHeader("Content-Type", "application/pdf");
        res.setHeader("Cache-Control", "no-cache");
        if (backendRes.headers.get("Content-Disposition")) {
          res.setHeader("Content-Disposition", backendRes.headers.get("Content-Disposition")!);
        }
        return res.send(pdfBuffer);
      }
      res.status(backendRes.status).json({ error: "Annotated PDF not available" });
    } catch (error) {
      console.error("Error serving annotated PDF:", error);
      res.status(500).json({ error: "Failed to serve annotated PDF" });
    }
  });

  app.get("/api/documents", async (req, res) => {
    try {
      const documents = await storage.getAllDocumentsSummary();

      const enriched = await Promise.all(documents.map(async (doc) => {
        let extractionStatus = 'pending';
        const hasData = doc.usdmData && typeof doc.usdmData === 'object' && Object.keys(doc.usdmData).length > 0 && (doc.usdmData as any).study;
        if (hasData) {
          extractionStatus = 'completed';
        } else {
          try {
            const jobRes = await fetch(`${BACKEND_URL}/api/v1/jobs/protocol/${encodeURIComponent(doc.studyId)}/latest`);
            if (jobRes.ok) {
              const jobData = await jobRes.json() as any;
              if (jobData.status === 'running' || jobData.status === 'pending') {
                extractionStatus = 'processing';
              } else if (jobData.status === 'completed' || jobData.status === 'completed_with_errors') {
                extractionStatus = jobData.status;
              } else if (jobData.status === 'failed') {
                extractionStatus = 'failed';
              }
            }
          } catch {
          }
        }
        return { ...doc, extractionStatus };
      }));

      res.json(enriched);
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

  app.put("/api/documents/:studyId/usdm", async (req, res) => {
    try {
      const { studyId } = req.params;
      const { usdmData } = req.body;

      if (!usdmData) {
        return res.status(400).json({ error: "usdmData is required" });
      }

      const doc = await storage.getDocument(studyId);
      if (!doc) {
        return res.status(404).json({ error: "Document not found" });
      }

      await storage.updateDocumentUsdm(studyId, usdmData);
      console.log(`[USDM SYNC] Updated USDM data for ${studyId}`);
      res.json({ success: true });
    } catch (error) {
      console.error("Error updating USDM data:", error);
      res.status(500).json({ error: "Failed to update USDM data" });
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
