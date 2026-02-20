"""
Copy 500 random rows from production omop_concepts to dev omop_concepts.
Reads from production read replica via execute_sql production access,
then inserts into dev via local DATABASE_URL.
"""
import os
import sys
import json
import psycopg2

DEV_DB_URL = os.environ.get("DATABASE_URL")

def main(prod_rows_json_path: str):
    if not DEV_DB_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    with open(prod_rows_json_path, 'r') as f:
        rows = json.load(f)

    print(f"Loaded {len(rows)} rows from export file")

    conn = psycopg2.connect(DEV_DB_URL)
    cur = conn.cursor()

    cur.execute("DELETE FROM omop_concepts;")
    conn.commit()
    print("Cleared existing dev data")

    insert_sql = """
        INSERT INTO omop_concepts (concept_id, concept_name, domain_id, vocabulary_id, 
            concept_class_id, standard_concept, concept_code, synonyms, metadata, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (concept_id) DO NOTHING
    """

    inserted = 0
    for row in rows:
        try:
            cur.execute(insert_sql, (
                row['concept_id'],
                row['concept_name'],
                row.get('domain_id'),
                row.get('vocabulary_id'),
                row.get('concept_class_id'),
                row.get('standard_concept'),
                row.get('concept_code'),
                row.get('synonyms'),
                json.dumps(row['metadata']) if row.get('metadata') else None,
                row.get('embedding'),
            ))
            inserted += 1
        except Exception as e:
            print(f"Error inserting concept_id={row.get('concept_id')}: {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.execute("SELECT count(*) FROM omop_concepts;")
    final_count = cur.fetchone()[0]

    cur.close()
    conn.close()
    print(f"Inserted {inserted} rows. Dev table now has {final_count} rows.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python copy_omop_sample.py <prod_rows.json>")
        sys.exit(1)
    main(sys.argv[1])
