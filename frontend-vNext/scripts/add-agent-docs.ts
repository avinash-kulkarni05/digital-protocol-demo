import { db } from "../server/db.js";
import { usdmDocuments } from "../shared/schema.js";
import { eq } from "drizzle-orm";
import usdmData from "../client/src/lib/usdm-data.json" assert { type: "json" };

async function addAgentDocs() {
  try {
    const docs = await db.select().from(usdmDocuments).where(eq(usdmDocuments.studyId, "NCT02264990"));
    if (!docs.length) {
      console.log("Document NCT02264990 not found");
      process.exit(1);
    }
    const doc = docs[0];
    const currentData = doc.usdmData as any;
    if (!currentData.agentDocumentation) {
      currentData.agentDocumentation = (usdmData as any).agentDocumentation;
      await db.update(usdmDocuments)
        .set({ usdmData: currentData, updatedAt: new Date() })
        .where(eq(usdmDocuments.studyId, "NCT02264990"));
      console.log("✓ Successfully added agentDocumentation to M14-359");
    } else {
      console.log("agentDocumentation already exists");
    }
    process.exit(0);
  } catch (error) {
    console.error("Error:", error);
    process.exit(1);
  }
}
addAgentDocs();
