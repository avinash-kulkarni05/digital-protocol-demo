import type { Express, Request, Response, NextFunction } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { insertUsdmDocumentSchema } from "@shared/schema";

declare module "express-session" {
  interface SessionData {
    user?: { email: string };
  }
}

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8080";

async function fetchWithRetry(url: string, options?: RequestInit, retries = 3, delayMs = 2000): Promise<globalThis.Response> {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      return await fetch(url, options);
    } catch (err: any) {
      const isConnRefused = err?.cause?.code === "ECONNREFUSED" || err?.message?.includes("ECONNREFUSED");
      if (isConnRefused && attempt < retries) {
        console.log(`Backend not ready (attempt ${attempt}/${retries}), retrying in ${delayMs}ms...`);
        await new Promise(r => setTimeout(r, delayMs));
        continue;
      }
      throw err;
    }
  }
  throw new Error("fetchWithRetry: should not reach here");
}

function requireAuth(req: Request, res: Response, next: NextFunction) {
  if (req.session?.user) {
    return next();
  }
  res.status(401).json({ error: "Not authenticated" });
}

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {

  app.post("/api/auth/login", (req, res) => {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: "Email and password are required" });
    }

    if (!email.toLowerCase().endsWith("@saama.com")) {
      return res.status(401).json({ error: "Only @saama.com email addresses are allowed" });
    }

    const appPassword = process.env.APP_PASSWORD;
    if (!appPassword) {
      return res.status(500).json({ error: "Server authentication not configured" });
    }

    if (password !== appPassword) {
      return res.status(401).json({ error: "Invalid password" });
    }

    req.session.user = { email: email.toLowerCase() };
    req.session.save((err) => {
      if (err) {
        return res.status(500).json({ error: "Failed to create session" });
      }
      res.json({ user: { email: email.toLowerCase() } });
    });
  });

  app.get("/api/auth/check", (req, res) => {
    if (req.session?.user) {
      return res.json({ authenticated: true, user: req.session.user });
    }
    res.json({ authenticated: false });
  });

  app.post("/api/auth/logout", (req, res) => {
    req.session.destroy((err) => {
      if (err) {
        return res.status(500).json({ error: "Failed to logout" });
      }
      res.clearCookie("connect.sid");
      res.json({ success: true });
    });
  });

  app.use("/api/protocols", requireAuth);
  app.use("/api/documents", requireAuth);
  app.use("/api/backend", requireAuth);

  app.get("/api/protocols/:studyId/pdf", async (req, res) => {
    try {
      const { studyId } = req.params;
      const backendUrl = `${BACKEND_URL}/api/v1/protocols/${encodeURIComponent(studyId)}/pdf`;
      const backendRes = await fetchWithRetry(backendUrl);
      if (backendRes.ok) {
        res.setHeader("Content-Type", "application/pdf");
        res.setHeader("Cache-Control", "no-cache");
        const buffer = Buffer.from(await backendRes.arrayBuffer());
        return res.send(buffer);
      }
      res.status(backendRes.status).json({ error: "PDF not available" });
    } catch (error) {
      console.error("Error serving PDF:", error);
      res.status(500).json({ error: "Failed to serve PDF" });
    }
  });

  app.get("/api/protocols/:studyId/pdf/annotated", async (req, res) => {
    try {
      const { studyId } = req.params;
      const backendUrl = `${BACKEND_URL}/api/v1/protocols/${encodeURIComponent(studyId)}/pdf/annotated`;
      const backendRes = await fetchWithRetry(backendUrl);
      if (backendRes.ok) {
        res.setHeader("Content-Type", "application/pdf");
        res.setHeader("Cache-Control", "no-cache");
        const buffer = Buffer.from(await backendRes.arrayBuffer());
        return res.send(buffer);
      }
      res.status(backendRes.status).json({ error: "Annotated PDF not available" });
    } catch (error) {
      console.error("Error serving annotated PDF:", error);
      res.status(500).json({ error: "Failed to serve annotated PDF" });
    }
  });

  app.use("/api/backend", async (req, res) => {
    try {
      const backendPath = req.url;
      const backendUrl = `${BACKEND_URL}/api/v1${backendPath}`;
      const reqContentType = req.headers["content-type"] || "";
      const fetchOptions: RequestInit = {
        method: req.method,
      };
      if (req.method !== "GET" && req.method !== "HEAD") {
        if (reqContentType.includes("multipart/form-data")) {
          const chunks: Buffer[] = [];
          await new Promise<void>((resolve, reject) => {
            req.on("data", (chunk: Buffer) => chunks.push(chunk));
            req.on("end", () => resolve());
            req.on("error", reject);
          });
          const rawBody = Buffer.concat(chunks);
          fetchOptions.body = rawBody;
          fetchOptions.headers = { "Content-Type": reqContentType };
        } else if (req.body) {
          fetchOptions.body = JSON.stringify(req.body);
          fetchOptions.headers = { "Content-Type": "application/json" };
        }
      }
      const backendRes = await fetchWithRetry(backendUrl, fetchOptions);
      const contentType = backendRes.headers.get("content-type") || "";

      if (contentType.includes("text/event-stream")) {
        res.setHeader("Content-Type", "text/event-stream");
        res.setHeader("Cache-Control", "no-cache");
        res.setHeader("Connection", "keep-alive");
        const reader = (backendRes.body as any)?.getReader?.();
        if (reader) {
          const pump = async () => {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              res.write(value);
            }
            res.end();
          };
          pump().catch(() => res.end());
        } else {
          res.end();
        }
        return;
      }

      if (contentType.includes("application/json")) {
        const data = await backendRes.json();
        return res.status(backendRes.status).json(data);
      }
      const buffer = Buffer.from(await backendRes.arrayBuffer());
      res.status(backendRes.status).send(buffer);
    } catch (error) {
      console.error("Backend proxy error:", error);
      res.status(502).json({ error: "Backend unavailable" });
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

      // First check if document exists in local table
      let localDoc = await storage.getDocument(studyId);

      // Try to get from backend protocols table (primary source of truth)
      const backendUrl = `${BACKEND_URL}/api/v1/protocols`;
      const backendResponse = await fetchWithRetry(backendUrl);

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
          const sourceDocumentUrl = `${BACKEND_URL}/api/v1/protocols/${encodeURIComponent(docStudyId)}/pdf/annotated`;

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
