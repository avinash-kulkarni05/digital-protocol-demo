#!/usr/bin/env python3
import os
import sys
import psycopg2

def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("[seed] No DATABASE_URL found, skipping")
        return

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("CREATE SCHEMA IF NOT EXISTS backend_vnext")

        cur.execute("""
            SELECT count(*) FROM information_schema.tables 
            WHERE table_schema = 'backend_vnext'
        """)
        table_count = cur.fetchone()[0]

        if table_count == 0:
            print("[seed] No tables found in backend_vnext schema - tables will be created by app startup")
            cur.close()
            conn.close()
            return

        cur.execute("SELECT count(*) FROM backend_vnext.protocols")
        row_count = cur.fetchone()[0]

        if row_count > 0:
            print(f"[seed] Production database already has {row_count} protocols - skipping seed")
            cur.close()
            conn.close()
            return

        print("[seed] Production database is empty - seeding data...")

        seed_file = os.path.join(os.path.dirname(__file__), "seed_data.sql")
        if not os.path.exists(seed_file):
            print(f"[seed] ERROR: Seed file not found: {seed_file}")
            cur.close()
            conn.close()
            return

        with open(seed_file, "r") as f:
            sql = f.read()

        statements = [s.strip() for s in sql.split(";\n") if s.strip() and not s.strip().startswith("--")]
        success = 0
        errors = 0
        for stmt in statements:
            stmt = stmt.rstrip(";")
            if not stmt or stmt.startswith("--"):
                continue
            try:
                cur.execute(stmt)
                success += 1
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"[seed] Warning: {str(e)[:200]}")

        print(f"[seed] Seeding complete: {success} statements executed, {errors} errors")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"[seed] Error connecting to database: {e}")

if __name__ == "__main__":
    main()
