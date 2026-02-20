"""
Setup pgvector extension and omop_concepts table on production database.
Run this script on the deployed server where DATABASE_URL points to production.
"""
import os
import sys
import psycopg2

def setup_pgvector():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    print(f"Connecting to database...")
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    cur = conn.cursor()

    print("1. Enabling pgvector extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    print("   Done.")

    print("2. Creating omop_concepts table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS omop_concepts (
            id SERIAL PRIMARY KEY,
            concept_id INTEGER NOT NULL,
            concept_name TEXT NOT NULL,
            domain_id VARCHAR(50),
            vocabulary_id VARCHAR(50),
            concept_class_id VARCHAR(50),
            standard_concept VARCHAR(1),
            concept_code VARCHAR(100),
            valid_start_date DATE,
            valid_end_date DATE,
            invalid_reason VARCHAR(1),
            synonyms TEXT[],
            metadata JSONB,
            embedding vector(1536),
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    print("   Done.")

    print("3. Creating indexes...")
    indexes = [
        ("idx_omop_concepts_concept_id", "CREATE UNIQUE INDEX IF NOT EXISTS idx_omop_concepts_concept_id ON omop_concepts(concept_id)"),
        ("idx_omop_concepts_domain", "CREATE INDEX IF NOT EXISTS idx_omop_concepts_domain ON omop_concepts(domain_id)"),
        ("idx_omop_concepts_vocabulary", "CREATE INDEX IF NOT EXISTS idx_omop_concepts_vocabulary ON omop_concepts(vocabulary_id)"),
        ("idx_omop_concepts_standard", "CREATE INDEX IF NOT EXISTS idx_omop_concepts_standard ON omop_concepts(standard_concept)"),
        ("idx_omop_concepts_name_lower", "CREATE INDEX IF NOT EXISTS idx_omop_concepts_name_lower ON omop_concepts(lower(concept_name))"),
        ("idx_omop_concepts_embedding_hnsw", 'CREATE INDEX IF NOT EXISTS idx_omop_concepts_embedding_hnsw ON omop_concepts USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)'),
    ]
    for name, sql in indexes:
        print(f"   Creating {name}...")
        cur.execute(sql)
    print("   All indexes created.")

    print("4. Verifying setup...")
    cur.execute("SELECT count(*) FROM omop_concepts;")
    count = cur.fetchone()[0]
    print(f"   Table has {count} rows.")

    cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'omop_concepts';")
    idx_names = [r[0] for r in cur.fetchall()]
    print(f"   Indexes: {', '.join(idx_names)}")

    cur.close()
    conn.close()
    print("\npgvector setup complete!")

if __name__ == "__main__":
    setup_pgvector()
