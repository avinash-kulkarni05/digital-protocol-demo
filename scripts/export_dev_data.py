"""
Export script: Uses pg_dump to create a proper dump of the backend_vnext schema.
Run this before deploying to ensure production gets the latest data.
"""
import os
import sys
import subprocess

DB_URL = os.environ.get("DATABASE_URL")
SCHEMA = "backend_vnext"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DUMP_FILE = os.path.join(SCRIPT_DIR, "dev_data_dump.sql")

if not DB_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

print(f"Exporting schema '{SCHEMA}' from dev database...")
print(f"Output: {DUMP_FILE}")

result = subprocess.run(
    [
        "pg_dump",
        DB_URL,
        "--schema=" + SCHEMA,
        "--no-owner",
        "--no-privileges",
        "--no-comments",
        "--clean",
        "--if-exists",
        "-f", DUMP_FILE,
    ],
    capture_output=True,
    text=True,
)

if result.returncode != 0:
    print(f"ERROR: pg_dump failed:\n{result.stderr}")
    sys.exit(1)

file_size = os.path.getsize(DUMP_FILE)
print(f"Export complete: {file_size / 1024:.1f} KB")

line_count = 0
copy_count = 0
with open(DUMP_FILE, 'r') as f:
    for line in f:
        line_count += 1
        if line.strip().startswith('COPY '):
            copy_count += 1

print(f"Lines: {line_count}, COPY statements: {copy_count}")
