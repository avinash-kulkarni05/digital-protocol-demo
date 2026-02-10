"""
Export script: Dumps all data from the dev DB to a portable Python pickle file.
Run this before deploying to ensure production gets the latest data.

Uses psycopg2 (pure Python) so it works in any environment.
"""
import os
import sys
import pickle
import psycopg2
import psycopg2.extras

DB_URL = os.environ.get("DATABASE_URL")
SCHEMA = "backend_vnext"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DUMP_FILE = os.path.join(SCRIPT_DIR, "dev_data_dump.pkl")

if not DB_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

print(f"Exporting schema '{SCHEMA}' from dev database...")

conn = psycopg2.connect(DB_URL)
conn.autocommit = False
cur = conn.cursor()

cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = %s AND table_type = 'BASE TABLE'
    ORDER BY table_name
""", (SCHEMA,))
tables = [row[0] for row in cur.fetchall()]
print(f"Found {len(tables)} tables: {', '.join(tables)}")

if not tables:
    print("No tables found, nothing to export.")
    sys.exit(0)

fk_query = """
    SELECT tc.table_name, ccu.table_name AS referenced_table
    FROM information_schema.table_constraints tc
    JOIN information_schema.constraint_column_usage ccu
      ON tc.constraint_name = ccu.constraint_name
      AND tc.table_schema = ccu.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = %s
"""
cur.execute(fk_query, (SCHEMA,))
deps = cur.fetchall()
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

dump_data = {
    "schema": SCHEMA,
    "table_order": ordered,
    "tables": {},
}

for table in ordered:
    cur.execute("""
        SELECT column_name, data_type, udt_name, character_maximum_length,
               column_default, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """, (SCHEMA, table))
    columns_info = cur.fetchall()

    col_defs = []
    col_names = []
    for col_name, data_type, udt_name, max_len, col_default, is_nullable in columns_info:
        col_names.append(col_name)
        type_map = {
            'uuid': 'UUID', 'jsonb': 'JSONB', 'json': 'JSON', 'text': 'TEXT',
            'bytea': 'BYTEA', 'int4': 'INTEGER', 'int8': 'BIGINT',
            'float8': 'DOUBLE PRECISION', 'float4': 'REAL', 'bool': 'BOOLEAN',
            'timestamp': 'TIMESTAMP', 'timestamptz': 'TIMESTAMPTZ',
        }
        col_type = type_map.get(udt_name)
        if not col_type:
            if udt_name == 'varchar' and max_len:
                col_type = f'VARCHAR({max_len})'
            elif udt_name == 'varchar':
                col_type = 'VARCHAR'
            else:
                col_type = data_type.upper()

        col_defs.append({
            "name": col_name,
            "type": col_type,
            "nullable": is_nullable == 'YES',
            "default": col_default if col_default and 'nextval' not in str(col_default) else None,
        })

    cur.execute("""
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = %s AND tc.table_name = %s
    """, (SCHEMA, table))
    pk_cols = [r[0] for r in cur.fetchall()]

    cur2 = conn.cursor()
    quoted_cols = ', '.join(f'"{c}"' for c in col_names)
    cur2.execute(f'SELECT {quoted_cols} FROM {SCHEMA}."{table}"')
    raw_rows = cur2.fetchall()
    cur2.close()

    cleaned_rows = []
    for row in raw_rows:
        cleaned = []
        for val in row:
            if isinstance(val, memoryview):
                cleaned.append(bytes(val))
            else:
                cleaned.append(val)
        cleaned_rows.append(tuple(cleaned))

    dump_data["tables"][table] = {
        "columns": col_defs,
        "col_names": col_names,
        "pk_cols": pk_cols,
        "rows": cleaned_rows,
    }
    print(f"  {table}: {len(cleaned_rows)} rows, {len(col_names)} columns")

with open(DUMP_FILE, 'wb') as f:
    pickle.dump(dump_data, f, protocol=pickle.HIGHEST_PROTOCOL)

file_size = os.path.getsize(DUMP_FILE)
total_rows = sum(len(t["rows"]) for t in dump_data["tables"].values())
print(f"\nExport complete: {file_size / 1024:.1f} KB, {total_rows} total rows")
print(f"Output: {DUMP_FILE}")

conn.close()
