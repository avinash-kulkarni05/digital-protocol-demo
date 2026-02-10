import dotenv from "dotenv";
import path from "path";
import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import * as schema from "@shared/schema";

dotenv.config();

const databaseUrl = process.env.DATABASE_URL;

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
