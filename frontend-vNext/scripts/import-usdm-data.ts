/**
 * Script to import USDM data from attached_assets into the database
 */
import { db } from "../server/db";
import { usdmDocuments } from "../shared/schema";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ASSETS_DIR = path.join(__dirname, "../attached_assets");

interface UsdmJson {
  id?: string;
  name?: string;
  sourceDocument?: {
    filename?: string;
  };
  study?: {
    id?: string;
    studyTitle?: { value?: string };
    studyIdentifiers?: Array<{ studyIdentifier?: { value?: string } }>;
  };
}

async function importUsdmData() {
  const files = fs.readdirSync(ASSETS_DIR);
  const usdmFiles = files.filter(f => f.includes("_usdm_4.0_") && f.endsWith(".json"));

  console.log(`Found ${usdmFiles.length} USDM files to import`);

  // Get unique protocols (take the latest version of each)
  const protocolMap = new Map<string, string>();
  for (const file of usdmFiles) {
    // Extract protocol ID from filename (e.g., NCT02264990_M14-359_usdm_4.0_1765326680361.json)
    const match = file.match(/^(.+?)_usdm_4\.0_\d+\.json$/);
    if (match) {
      const protocolId = match[1];
      // Keep the file with higher timestamp (later version)
      const existing = protocolMap.get(protocolId);
      if (!existing || file > existing) {
        protocolMap.set(protocolId, file);
      }
    }
  }

  console.log(`Unique protocols: ${protocolMap.size}`);

  for (const [protocolId, filename] of protocolMap) {
    const filePath = path.join(ASSETS_DIR, filename);
    console.log(`\nImporting: ${filename}`);

    try {
      const content = fs.readFileSync(filePath, "utf-8");
      const usdmData: UsdmJson = JSON.parse(content);

      // Extract study ID and title
      const studyId = usdmData.study?.studyIdentifiers?.[0]?.studyIdentifier?.value
        || usdmData.id
        || protocolId;

      const studyTitle = usdmData.study?.studyTitle?.value
        || usdmData.name
        || `Protocol ${protocolId}`;

      // Find corresponding PDF - prefer annotated version
      const pdfFiles = files.filter(f => f.startsWith(protocolId) && f.endsWith(".pdf"));
      // Prefer annotated PDFs
      const annotatedPdf = pdfFiles.find(f => f.includes("_annotated_"));
      const pdfFile = annotatedPdf || pdfFiles[0] || `${protocolId}.pdf`;
      const sourceDocumentUrl = `/attached_assets/${pdfFile}`;

      console.log(`  Study ID: ${studyId}`);
      console.log(`  Title: ${studyTitle.substring(0, 50)}...`);
      console.log(`  PDF: ${sourceDocumentUrl}`);

      // Insert into database (upsert based on studyId)
      await db
        .insert(usdmDocuments)
        .values({
          studyId,
          studyTitle,
          usdmData,
          sourceDocumentUrl,
        })
        .onConflictDoUpdate({
          target: usdmDocuments.studyId,
          set: {
            studyTitle,
            usdmData,
            sourceDocumentUrl,
            updatedAt: new Date(),
          },
        });

      console.log(`  ✓ Imported successfully`);
    } catch (error) {
      console.error(`  ✗ Error importing ${filename}:`, error);
    }
  }

  console.log("\n\nImport complete!");
  process.exit(0);
}

importUsdmData().catch(console.error);
