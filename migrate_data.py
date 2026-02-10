import os
import sys
import json
import psycopg2
import psycopg2.extras
from psycopg2.extensions import register_adapter, adapt

psycopg2.extensions.register_adapter(dict, psycopg2.extras.Json)
psycopg2.extensions.register_adapter(list, psycopg2.extras.Json)

EXTERNAL_DB_URL = os.environ.get("EXTERNAL_DATABASE_URL")
REPLIT_DB_URL = os.environ.get("DATABASE_URL")
SCHEMA = "backend_vnext"

if not EXTERNAL_DB_URL:
    print("ERROR: EXTERNAL_DATABASE_URL not set")
    sys.exit(1)
if not REPLIT_DB_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

print(f"Source (Neon): {EXTERNAL_DB_URL[:50]}...")
print(f"Target (Replit): {REPLIT_DB_URL[:50]}...")
print()

src = psycopg2.connect(EXTERNAL_DB_URL)
dst = psycopg2.connect(REPLIT_DB_URL)
src.autocommit = False
dst.autocommit = False

try:
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
    print(f"Found {len(tables)} tables: {', '.join(tables)}\n")

    src_cur.execute(f"SET search_path TO {SCHEMA}")

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

    ordered = []
    remaining = set(tables)
    dep_map = {}
    for child, parent in deps:
        dep_map.setdefault(child, set()).add(parent)

    max_iter = len(tables) + 1
    while remaining and max_iter > 0:
        max_iter -= 1
        for t in list(remaining):
            parents = dep_map.get(t, set()) - {t}
            if parents.issubset(set(ordered)):
                ordered.append(t)
                remaining.remove(t)
    ordered.extend(remaining)

    print(f"Import order: {', '.join(ordered)}\n")

    for table in ordered:
        src_cur.execute(f"""
            SELECT column_name, data_type, udt_name, character_maximum_length,
                   column_default, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """, (SCHEMA, table))
        columns_info = src_cur.fetchall()

        col_defs = []
        col_names = []
        for col_name, data_type, udt_name, max_len, col_default, is_nullable in columns_info:
            col_names.append(col_name)
            if udt_name == 'uuid':
                col_type = 'UUID'
            elif udt_name == 'jsonb':
                col_type = 'JSONB'
            elif udt_name == 'json':
                col_type = 'JSON'
            elif udt_name == 'text':
                col_type = 'TEXT'
            elif udt_name == 'bytea':
                col_type = 'BYTEA'
            elif udt_name == 'int4':
                col_type = 'INTEGER'
            elif udt_name == 'int8':
                col_type = 'BIGINT'
            elif udt_name == 'float8':
                col_type = 'DOUBLE PRECISION'
            elif udt_name == 'float4':
                col_type = 'REAL'
            elif udt_name == 'bool':
                col_type = 'BOOLEAN'
            elif udt_name == 'timestamp':
                col_type = 'TIMESTAMP'
            elif udt_name == 'timestamptz':
                col_type = 'TIMESTAMPTZ'
            elif udt_name == 'varchar':
                col_type = f'VARCHAR({max_len})' if max_len else 'VARCHAR'
            elif udt_name == 'serial' or udt_name == 'int4' and col_default and 'nextval' in str(col_default):
                col_type = 'SERIAL'
            else:
                col_type = data_type.upper()

            nullable = "" if is_nullable == 'YES' else " NOT NULL"
            default = ""
            if col_default and 'nextval' not in str(col_default):
                default = f" DEFAULT {col_default}"

            col_defs.append(f'"{col_name}" {col_type}{nullable}{default}')

        src_cur.execute(f"""
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
            print(f"  {table}: 0 rows (empty table, schema created)")
            continue

        quoted_cols = ', '.join(f'"{c}"' for c in col_names)
        src_cur2 = src.cursor(name=f'fetch_{table}', cursor_factory=psycopg2.extras.DictCursor)
        src_cur2.execute(f'SELECT {quoted_cols} FROM {SCHEMA}."{table}"')

        placeholders = ', '.join(['%s'] * len(col_names))
        insert_sql = f'INSERT INTO {SCHEMA}."{table}" ({quoted_cols}) VALUES ({placeholders})'

        batch_size = 500
        total_inserted = 0
        while True:
            rows = src_cur2.fetchmany(batch_size)
            if not rows:
                break
            values = [tuple(row) for row in rows]
            psycopg2.extras.execute_batch(dst_cur, insert_sql, values)
            total_inserted += len(rows)

        dst.commit()
        src_cur2.close()
        print(f"  {table}: {total_inserted} rows copied")

    print("\n--- Verification ---")
    for table in ordered:
        src_cur.execute(f'SELECT COUNT(*) FROM {SCHEMA}."{table}"')
        src_count = src_cur.fetchone()[0]
        dst_cur.execute(f'SELECT COUNT(*) FROM {SCHEMA}."{table}"')
        dst_count = dst_cur.fetchone()[0]
        status = "OK" if src_count == dst_count else "MISMATCH"
        print(f"  {table}: source={src_count}, target={dst_count} [{status}]")

    print("\nDone! Data migration complete.")

except Exception as e:
    print(f"\nERROR: {e}")
    dst.rollback()
    raise
finally:
    src.close()
    dst.close()
