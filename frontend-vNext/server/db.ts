import dotenv from "dotenv";
import path from "path";
import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import * as schema from "@shared/schema";

dotenv.config({ path: path.resolve(process.cwd(), "../.env") });

const databaseUrl = process.env.DATABASE_URL || process.env.EXTERNAL_DATABASE_URL;

if (!databaseUrl) {
  throw new Error("DATABASE_URL or EXTERNAL_DATABASE_URL environment variable is required");
}

const pool = new Pool({
  connectionString: databaseUrl,
});

pool.on('connect', (client) => {
  client.query('SET search_path TO public');
});

export const db = drizzle(pool, { schema });

export async function repairSchema() {
  const client = await pool.connect();
  try {
    const tables = [
      { table: 'usdm_documents', timestamps: ['created_at', 'updated_at'] },
      { table: 'usdm_edit_audit', timestamps: ['updated_at'] },
      { table: 'soa_edit_audit', timestamps: [] },
    ];
    for (const { table, timestamps } of tables) {
      const seqName = `${table}_id_seq`;
      await client.query(`
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = '${seqName}') THEN
            CREATE SEQUENCE public.${seqName} OWNED BY public.${table}.id;
            PERFORM setval('public.${seqName}',
              COALESCE((SELECT MAX(id) FROM public.${table}), 0) + 1);
            ALTER TABLE public.${table}
              ALTER COLUMN id SET DEFAULT nextval('public.${seqName}');
          END IF;
        END $$;
      `);
      for (const col of timestamps) {
        await client.query(`
          ALTER TABLE public.${table} ALTER COLUMN ${col} SET DEFAULT now();
        `);
      }
    }
    await client.query(`
      CREATE UNIQUE INDEX IF NOT EXISTS usdm_documents_study_id_unique
        ON public.usdm_documents(study_id);
    `);
  } catch (e) {
  } finally {
    client.release();
  }
}
