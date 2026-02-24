"""
Configuration Check for OMOP RAG Vector Store Builder

Validates that all required environment variables and dependencies are properly
configured before running the vector store build process.

Usage:
    python config_check.py
"""

import os
import sys
from pathlib import Path


def check_environment_variables() -> dict:
    """Check all required environment variables."""
    results = {
        "passed": [],
        "failed": [],
        "warnings": [],
    }

    # Load .env file if exists
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
        print(f"[OK] Loaded .env from: {env_path}")
    else:
        results["warnings"].append(f".env file not found at {env_path}")

    # Required: PostgreSQL database URL
    pg_url = os.environ.get("POSTGRE_DATABASE_URL")
    if pg_url:
        masked = pg_url[:30] + "..." if len(pg_url) > 30 else pg_url
        results["passed"].append(f"POSTGRE_DATABASE_URL: {masked}")
    else:
        results["failed"].append("POSTGRE_DATABASE_URL: Not set")

    # Required: Azure OpenAI Embedding credentials
    azure_vars = {
        "AZURE_OPENAI_EMBEDDING_ENDPOINT": "Azure endpoint URL",
        "AZURE_OPENAI_EMBEDDING_API_KEY": "Azure API key",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "Deployment name",
    }

    for var, description in azure_vars.items():
        value = os.environ.get(var)
        if value:
            # Mask sensitive values
            if "KEY" in var:
                display_value = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            else:
                display_value = value
            results["passed"].append(f"{var}: {display_value}")
        else:
            results["failed"].append(f"{var}: Not set ({description})")

    # Optional but recommended
    optional_vars = {
        "AZURE_OPENAI_EMBEDDING_MODEL_NAME": "Model name (optional)",
        "AZURE_OPENAI_EMBEDDING_API_VERSION": "API version (defaults to 2024-02-01)",
    }

    for var, description in optional_vars.items():
        value = os.environ.get(var)
        if value:
            results["passed"].append(f"{var}: {value}")
        else:
            results["warnings"].append(f"{var}: Not set ({description})")

    return results


def check_dependencies() -> dict:
    """Check required Python packages."""
    results = {
        "passed": [],
        "failed": [],
    }

    packages = {
        "chromadb": "Vector store",
        "openai": "Azure OpenAI client",
        "dotenv": "Environment loading (python-dotenv)",
    }

    for package, description in packages.items():
        try:
            if package == "dotenv":
                import dotenv
                version = getattr(dotenv, "__version__", "unknown")
            else:
                module = __import__(package)
                version = getattr(module, "__version__", "unknown")
            results["passed"].append(f"{package} ({version}): {description}")
        except ImportError:
            results["failed"].append(f"{package}: Not installed ({description})")

    return results


def check_omop_schema() -> dict:
    """Validate PostgreSQL omop_concepts table schema."""
    results = {
        "passed": [],
        "failed": [],
        "info": [],
    }

    pg_url = os.environ.get("POSTGRE_DATABASE_URL")
    if not pg_url:
        results["failed"].append("Cannot check schema: POSTGRE_DATABASE_URL not set")
        return results

    try:
        import psycopg2

        conn = psycopg2.connect(pg_url)
        conn.autocommit = True
        cursor = conn.cursor()

        # Check omop_concepts table exists
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'omop_concepts';"
        )
        if cursor.fetchone()[0] > 0:
            results["passed"].append("Table 'omop_concepts' exists")
        else:
            results["failed"].append("Table 'omop_concepts' not found")
            conn.close()
            return results

        # Check required columns
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'omop_concepts';"
        )
        columns = {row[0] for row in cursor.fetchall()}
        required_columns = ["concept_id", "concept_name", "domain_id", "vocabulary_id",
                            "standard_concept", "concept_code", "embedding"]
        for col in required_columns:
            if col in columns:
                results["passed"].append(f"Column 'omop_concepts.{col}' exists")
            else:
                results["failed"].append(f"Column 'omop_concepts.{col}' not found")

        # Get concept counts
        cursor.execute("SELECT COUNT(*) FROM omop_concepts;")
        total_count = cursor.fetchone()[0]
        results["info"].append(f"Total concepts: {total_count:,}")

        # Check embeddings
        cursor.execute("SELECT COUNT(*) FROM omop_concepts WHERE embedding IS NOT NULL;")
        emb_count = cursor.fetchone()[0]
        results["info"].append(f"Concepts with embeddings: {emb_count:,}")

        # Get domain distribution
        cursor.execute("""
            SELECT domain_id, COUNT(*) as cnt
            FROM omop_concepts
            GROUP BY domain_id
            ORDER BY cnt DESC
            LIMIT 10;
        """)
        domains = cursor.fetchall()
        results["info"].append("Top domains:")
        for domain, count in domains:
            results["info"].append(f"  - {domain}: {count:,}")

        conn.close()

    except Exception as e:
        results["failed"].append(f"Database error: {e}")

    return results


def test_azure_embedding() -> dict:
    """Test Azure OpenAI embedding connection."""
    results = {
        "passed": [],
        "failed": [],
        "info": [],
    }

    try:
        from openai import AzureOpenAI

        endpoint = os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT")
        api_key = os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY")
        deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        api_version = os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01")

        if not all([endpoint, api_key, deployment]):
            results["failed"].append("Missing Azure credentials, skipping connection test")
            return results

        # Check SSL verification setting
        ssl_verify = os.environ.get("AZURE_OPENAI_SSL_VERIFY", "true").lower() != "false"

        if not ssl_verify:
            import httpx
            http_client = httpx.Client(verify=False)
            client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version,
                http_client=http_client,
            )
            results["info"].append("SSL verification: DISABLED (corporate proxy mode)")
        else:
            client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version,
            )

        # Test with a simple embedding
        test_text = "Diabetes mellitus type 2"
        response = client.embeddings.create(
            input=[test_text],
            model=deployment,
        )

        embedding = response.data[0].embedding
        results["passed"].append(f"Azure OpenAI connection successful")
        results["info"].append(f"Test embedding dimension: {len(embedding)}")
        results["info"].append(f"Test text: '{test_text}'")

    except Exception as e:
        results["failed"].append(f"Azure OpenAI connection failed: {e}")

    return results


def print_section(title: str, results: dict) -> bool:
    """Print a section of results. Returns True if all passed."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print("=" * 60)

    all_passed = True

    if results.get("passed"):
        for item in results["passed"]:
            print(f"  [OK] {item}")

    if results.get("warnings"):
        for item in results["warnings"]:
            print(f"  [!!] {item}")

    if results.get("info"):
        for item in results["info"]:
            print(f"  [..] {item}")

    if results.get("failed"):
        all_passed = False
        for item in results["failed"]:
            print(f"  [XX] {item}")

    return all_passed


def main():
    """Run all configuration checks."""
    print("\n" + "=" * 60)
    print(" OMOP RAG Vector Store - Configuration Check")
    print("=" * 60)

    all_passed = True

    # Check dependencies first
    dep_results = check_dependencies()
    if not print_section("Python Dependencies", dep_results):
        all_passed = False
        if dep_results["failed"]:
            print("\n  >> Install missing packages:")
            print("     pip install chromadb openai python-dotenv")

    # Check environment variables
    env_results = check_environment_variables()
    if not print_section("Environment Variables", env_results):
        all_passed = False

    # Check PostgreSQL omop_concepts schema (only if env vars passed)
    if "POSTGRE_DATABASE_URL" not in str(env_results.get("failed", [])):
        schema_results = check_omop_schema()
        if not print_section("PostgreSQL omop_concepts Schema", schema_results):
            all_passed = False

    # Test Azure connection (only if env vars passed)
    azure_failed = [f for f in env_results.get("failed", []) if "AZURE" in f]
    if not azure_failed:
        azure_results = test_azure_embedding()
        if not print_section("Azure OpenAI Connection Test", azure_results):
            all_passed = False

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print(" STATUS: All checks passed - Ready to build vector store")
        print("=" * 60)
        print("\n  Next step: python vector_store_builder.py --limit 100")
        return 0
    else:
        print(" STATUS: Some checks failed - Please fix issues above")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
