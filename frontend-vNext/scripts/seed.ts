import { db } from "../server/db.js";
import usdmData from "../client/src/lib/usdm-data.json" assert { type: "json" };
import { usdmDocuments } from "../shared/schema.js";

async function seed() {
  try {
    console.log("Seeding database with USDM document...");

    const studyId = usdmData.study?.id || "M14-359";
    const studyTitle = usdmData.study?.officialTitle || "M14-359 Study";

    await db.insert(usdmDocuments).values({
      studyId,
      studyTitle,
      usdmData: usdmData as any,
      sourceDocumentUrl: "/protocol.pdf",
    }).onConflictDoUpdate({
      target: usdmDocuments.studyId,
      set: {
        studyTitle,
        usdmData: usdmData as any,
        sourceDocumentUrl: "/protocol.pdf",
        updatedAt: new Date(),
      },
    });

    console.log("✓ Successfully seeded USDM document:", studyId);
    process.exit(0);
  } catch (error) {
    console.error("Error seeding database:", error);
    process.exit(1);
  }
}

seed();
