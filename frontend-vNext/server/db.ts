import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";
import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import * as schema from "@shared/schema";

// Load .env from root directory
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.resolve(__dirname, "../../.env") });

const databaseUrl = process.env.DATABASE_URL || process.env.EXTERNAL_DATABASE_URL;

if (!databaseUrl) {
  throw new Error("DATABASE_URL or EXTERNAL_DATABASE_URL environment variable is required");
}

const pool = new Pool({
  connectionString: databaseUrl,
});

pool.on('connect', (client) => {
  client.query('SET search_path TO backend_vnext');
});

export const db = drizzle(pool, { schema });
