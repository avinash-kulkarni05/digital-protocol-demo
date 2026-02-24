import { db } from "../server/db";
import { usdmDocuments } from "../shared/schema";
import fs from "fs";
import path from "path";

async function insertAbbvieProtocol() {
  const jsonPath = path.join(process.cwd(), "attached_assets/NCT02264990_M14-359_usdm_4.0_1765247245942.json");
  const jsonContent = fs.readFileSync(jsonPath, "utf-8");
  const usdmData = JSON.parse(jsonContent);

  const studyId = "NCT02264990";
  const studyTitle = "A Randomized, Open-Label, Multicenter, Phase 3 Trial Comparing Veliparib Plus Carboplatin and Paclitaxel Versus Investigator's Choice of Standard Chemotherapy in Subjects Receiving First Cytotoxic Chemotherapy for Metastatic or Advanced Non-Squamous Non-Small Cell Lung Cancer (NSCLC) and Who Are Current or Former Smokers";
  const sourceDocumentUrl = "/abbvie_m14359_protocol.pdf";

  try {
    const result = await db.insert(usdmDocuments).values({
      studyId,
      studyTitle,
      usdmData,
      sourceDocumentUrl,
    }).returning();

    console.log("Successfully inserted Abbvie protocol:", result[0].id);
  } catch (error: any) {
    if (error.code === "23505") {
      console.log("Protocol already exists, updating...");
      const { eq } = await import("drizzle-orm");
      await db.update(usdmDocuments)
        .set({ usdmData, studyTitle, sourceDocumentUrl, updatedAt: new Date() })
        .where(eq(usdmDocuments.studyId, studyId));
      console.log("Successfully updated Abbvie protocol");
    } else {
      throw error;
    }
  }

  process.exit(0);
}

insertAbbvieProtocol().catch((err) => {
  console.error("Error inserting protocol:", err);
  process.exit(1);
});
