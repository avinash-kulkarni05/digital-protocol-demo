"""
Migration script: Copies data from Replit dev DB to production DATABASE_URL.
Used during production build to seed the production database with data.

Uses DEV_DATABASE_URL to connect to the dev database and DATABASE_URL for production.
Falls back to a pickle dump file if DEV_DATABASE_URL is not available.
"""
import os
import sys

print("=" * 60)
print("DATA MIGRATION SCRIPT - START")
print("=" * 60)

TARGET_DB_URL = os.environ.get("DATABASE_URL")
DEV_DB_URL = os.environ.get("DEV_DATABASE_URL")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DUMP_FILE = os.path.join(SCRIPT_DIR, "dev_data_dump.pkl")
SCHEMA = "backend_vnext"

print(f"DATABASE_URL set: {'yes' if TARGET_DB_URL else 'NO'}")
print(f"DEV_DATABASE_URL set: {'yes' if DEV_DB_URL else 'NO'}")
if TARGET_DB_URL:
    print(f"Target (first 60): {TARGET_DB_URL[:60]}...")
if DEV_DB_URL:
    print(f"Source (first 60): {DEV_DB_URL[:60]}...")
print(f"Dump file exists: {os.path.exists(DUMP_FILE)}")

if not TARGET_DB_URL:
    print("WARNING: DATABASE_URL not set, skipping data migration")
    sys.exit(0)

try:
    import psycopg2
    import psycopg2.extras
    print("psycopg2 imported successfully")
except ImportError as e:
    print(f"ERROR: Cannot import psycopg2: {e}")
    sys.exit(1)

psycopg2.extensions.register_adapter(dict, psycopg2.extras.Json)
psycopg2.extensions.register_adapter(list, psycopg2.extras.Json)

from urllib.parse import urlparse

def same_db(url1, url2):
    """Check if two URLs point to the same database."""
    def parse(u):
        u = u.replace("postgres://", "postgresql://", 1)
        p = urlparse(u)
        return (p.hostname or '', str(p.port or 5432), p.path.lstrip('/').split('?')[0])
    try:
        return parse(url1) == parse(url2)
    except Exception:
        return url1 == url2

def migrate_from_db(source_url, target_url):
    """Copy all data from source DB to target DB."""
    print(f"\nDirect DB-to-DB migration...")

    src = psycopg2.connect(source_url)
    dst = psycopg2.connect(target_url)
    src.autocommit = False
    dst.autocommit = False
    src_cur = src.cursor()
    dst_cur = dst.cursor()

    dst_cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    dst.commit()
    print(f"Schema '{SCHEMA}' ensured on target.")

    src_cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """, (SCHEMA,))
    tables = [row[0] for row in src_cur.fetchall()]
    print(f"Found {len(tables)} tables: {', '.join(tables)}")

    if not tables:
        print("No tables in source, nothing to migrate.")
        src.close()
        dst.close()
        return

    fk_query = """
        SELECT tc.table_name, ccu.table_name AS referenced_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
          AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = %s
    """
    src_cur.execute(fk_query, (SCHEMA,))
    deps = src_cur.fetchall()
    dep_map = {}
    for child, parent in deps:
        dep_map.setdefault(child, set()).add(parent)

    ordered = []
    remaining = set(tables)
    max_iter = len(tables) + 1
    while remaining and max_iter > 0:
        max_iter -= 1
        for t in list(remaining):
            parents = dep_map.get(t, set()) - {t}
            if parents.issubset(set(ordered)):
                ordered.append(t)
                remaining.remove(t)
    ordered.extend(remaining)

    for table in ordered:
        src_cur.execute("""
            SELECT column_name, data_type, udt_name, character_maximum_length,
                   column_default, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """, (SCHEMA, table))
        columns_info = src_cur.fetchall()

        col_defs = []
        col_names = []
        type_map = {
            'uuid': 'UUID', 'jsonb': 'JSONB', 'json': 'JSON', 'text': 'TEXT',
            'bytea': 'BYTEA', 'int4': 'INTEGER', 'int8': 'BIGINT',
            'float8': 'DOUBLE PRECISION', 'float4': 'REAL', 'bool': 'BOOLEAN',
            'timestamp': 'TIMESTAMP', 'timestamptz': 'TIMESTAMPTZ',
        }
        for col_name, data_type, udt_name, max_len, col_default, is_nullable in columns_info:
            col_names.append(col_name)
            col_type = type_map.get(udt_name)
            if not col_type:
                if udt_name == 'varchar' and max_len:
                    col_type = f'VARCHAR({max_len})'
                elif udt_name == 'varchar':
                    col_type = 'VARCHAR'
                else:
                    col_type = data_type.upper()

            nullable = "" if is_nullable == 'YES' else " NOT NULL"
            default = ""
            if col_default and 'nextval' not in str(col_default):
                default = f" DEFAULT {col_default}"
            col_defs.append(f'"{col_name}" {col_type}{nullable}{default}')

        src_cur.execute("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = %s AND tc.table_name = %s
        """, (SCHEMA, table))
        pk_cols = [r[0] for r in src_cur.fetchall()]

        create_sql = f'CREATE TABLE IF NOT EXISTS {SCHEMA}."{table}" (\n  '
        create_sql += ',\n  '.join(col_defs)
        if pk_cols:
            pk_str = ', '.join(f'"{c}"' for c in pk_cols)
            create_sql += f',\n  PRIMARY KEY ({pk_str})'
        create_sql += '\n)'

        dst_cur.execute(f'DROP TABLE IF EXISTS {SCHEMA}."{table}" CASCADE')
        dst_cur.execute(create_sql)
        dst.commit()

        src_cur.execute(f'SELECT COUNT(*) FROM {SCHEMA}."{table}"')
        row_count = src_cur.fetchone()[0]

        if row_count == 0:
            print(f"  {table}: 0 rows (schema only)")
            continue

        quoted_cols = ', '.join(f'"{c}"' for c in col_names)
        src_cur2 = src.cursor(name=f'fetch_{table}', cursor_factory=psycopg2.extras.DictCursor)
        src_cur2.execute(f'SELECT {quoted_cols} FROM {SCHEMA}."{table}"')

        placeholders = ', '.join(['%s'] * len(col_names))
        insert_sql = f'INSERT INTO {SCHEMA}."{table}" ({quoted_cols}) VALUES ({placeholders})'

        total_inserted = 0
        while True:
            rows = src_cur2.fetchmany(500)
            if not rows:
                break
            values = [tuple(row) for row in rows]
            psycopg2.extras.execute_batch(dst_cur, insert_sql, values)
            total_inserted += len(rows)

        dst.commit()
        src_cur2.close()
        print(f"  {table}: {total_inserted} rows copied")

    print(f"\n--- Verification ---")
    total = 0
    for table in ordered:
        src_cur.execute(f'SELECT COUNT(*) FROM {SCHEMA}."{table}"')
        src_count = src_cur.fetchone()[0]
        dst_cur.execute(f'SELECT COUNT(*) FROM {SCHEMA}."{table}"')
        dst_count = dst_cur.fetchone()[0]
        status = "OK" if src_count == dst_count else f"MISMATCH (src={src_count})"
        total += dst_count
        print(f"  {table}: {dst_count} rows [{status}]")

    print(f"\nTotal: {total} rows")
    src.close()
    dst.close()


def migrate_from_pickle(dump_file, target_url):
    """Import data from pickle dump file."""
    import pickle
    print(f"\nImporting from pickle dump: {dump_file}")

    with open(dump_file, 'rb') as f:
        dump_data = pickle.load(f)

    schema = dump_data["schema"]
    table_order = dump_data["table_order"]
    tables_data = dump_data["tables"]
    total_in_dump = sum(len(t["rows"]) for t in tables_data.values())
    print(f"Loaded: {len(table_order)} tables, {total_in_dump} rows")

    conn = psycopg2.connect(target_url)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    conn.commit()

    for table in table_order:
        tdata = tables_data[table]
        col_defs = []
        for col in tdata["columns"]:
            nullable = "" if col["nullable"] else " NOT NULL"
            default = f" DEFAULT {col['default']}" if col["default"] else ""
            col_defs.append(f'"{col["name"]}" {col["type"]}{nullable}{default}')

        create_sql = f'CREATE TABLE IF NOT EXISTS {schema}."{table}" (\n  '
        create_sql += ',\n  '.join(col_defs)
        if tdata["pk_cols"]:
            pk_str = ', '.join(f'"{c}"' for c in tdata["pk_cols"])
            create_sql += f',\n  PRIMARY KEY ({pk_str})'
        create_sql += '\n)'

        cur.execute(f'DROP TABLE IF EXISTS {schema}."{table}" CASCADE')
        cur.execute(create_sql)
        conn.commit()

        rows = tdata["rows"]
        if not rows:
            print(f"  {table}: 0 rows (schema only)")
            continue

        col_names = tdata["col_names"]
        quoted_cols = ', '.join(f'"{c}"' for c in col_names)
        placeholders = ', '.join(['%s'] * len(col_names))
        insert_sql = f'INSERT INTO {schema}."{table}" ({quoted_cols}) VALUES ({placeholders})'

        for i in range(0, len(rows), 500):
            batch = rows[i:i + 500]
            psycopg2.extras.execute_batch(cur, insert_sql, [tuple(r) for r in batch])
        conn.commit()
        print(f"  {table}: {len(rows)} rows inserted")

    print(f"\n--- Verification ---")
    total = 0
    for table in table_order:
        cur.execute(f'SELECT COUNT(*) FROM {schema}."{table}"')
        count = cur.fetchone()[0]
        expected = len(tables_data[table]["rows"])
        status = "OK" if count == expected else f"MISMATCH (expected {expected})"
        total += count
        print(f"  {table}: {count} rows [{status}]")
    print(f"\nTotal: {total} rows")
    conn.close()


try:
    if DEV_DB_URL and not same_db(DEV_DB_URL, TARGET_DB_URL):
        try:
            test_conn = psycopg2.connect(DEV_DB_URL, connect_timeout=10)
            test_conn.close()
            print("Dev DB is reachable, using direct DB-to-DB migration")
            migrate_from_db(DEV_DB_URL, TARGET_DB_URL)
        except Exception as e:
            print(f"Cannot reach dev DB: {e}")
            if os.path.exists(DUMP_FILE):
                print("Falling back to pickle dump file...")
                migrate_from_pickle(DUMP_FILE, TARGET_DB_URL)
            else:
                print("ERROR: No dump file available either. Cannot migrate data.")
                sys.exit(1)
    elif DEV_DB_URL and same_db(DEV_DB_URL, TARGET_DB_URL):
        print("Source and target are the same database, skipping migration")
    elif os.path.exists(DUMP_FILE):
        print("No DEV_DATABASE_URL set, using pickle dump file...")
        migrate_from_pickle(DUMP_FILE, TARGET_DB_URL)
    else:
        print("WARNING: No data source available (no DEV_DATABASE_URL, no dump file)")
        print("Skipping migration.")
        sys.exit(0)

    print("\nData migration complete!")

except Exception as e:
    print(f"\nERROR during migration: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 60)
print("DATA MIGRATION SCRIPT - DONE")
print("=" * 60)
