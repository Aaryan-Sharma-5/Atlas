#!/usr/bin/env python3
"""Test connectivity to Neo4j and PostgreSQL after docker-compose is running."""

import sys
import time
from typing import Tuple

def test_neo4j_connectivity() -> Tuple[bool, str]:
    """Test Neo4j connectivity via Bolt protocol."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        return False, "neo4j package not installed (install with: pip install neo4j)"

    uri = "bolt://localhost:7687"
    auth = ("neo4j", "atlas_password_123")

    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            driver = GraphDatabase.driver(uri, auth=auth)
            with driver.session() as session:
                result = session.run("RETURN 1 as status")
                result.consume()
            driver.close()
            return True, f"✓ Neo4j (Bolt) is reachable at {uri}"
        except Exception as e:
            if attempt < max_retries:
                print(f"  Attempt {attempt}/{max_retries}: {str(e)[:80]}")
                time.sleep(2)
            else:
                return False, f"✗ Neo4j connection failed: {str(e)}"

    return False, "✗ Neo4j is not responding"

def test_postgres_connectivity() -> Tuple[bool, str]:
    """Test PostgreSQL connectivity."""
    try:
        import psycopg2
    except ImportError:
        return False, "psycopg2 package not installed (install with: pip install psycopg2-binary)"

    conn_params = {
        "host": "localhost",
        "port": 5432,
        "database": "atlas",
        "user": "atlas_user",
        "password": "atlas_password_123",
    }

    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(**conn_params)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True, f"✓ PostgreSQL is reachable at localhost:5432 (database: {conn_params['database']})"
        except Exception as e:
            if attempt < max_retries:
                print(f"  Attempt {attempt}/{max_retries}: {str(e)[:80]}")
                time.sleep(2)
            else:
                return False, f"✗ PostgreSQL connection failed: {str(e)}"

    return False, "✗ PostgreSQL is not responding"

def main():
    """Run all connectivity tests."""
    print("=" * 70)
    print("Atlas Infrastructure Connectivity Test")
    print("=" * 70)
    print()

    print("Testing services...")
    print()

    # Test Neo4j
    neo4j_ok, neo4j_msg = test_neo4j_connectivity()
    print(f"Neo4j:      {neo4j_msg}")

    # Test PostgreSQL
    postgres_ok, postgres_msg = test_postgres_connectivity()
    print(f"PostgreSQL: {postgres_msg}")

    print()
    print("=" * 70)

    if neo4j_ok and postgres_ok:
        print("✓ All services are reachable and operational!")
        print()
        print("Next steps:")
        print("  1. Neo4j Browser: http://localhost:7474")
        print("  2. Initialize database schema (Day 7)")
        print("  3. Install Python dependencies: pip install -r requirements.txt")
        print()
        return 0
    else:
        print("✗ Some services are not responding.")
        print()
        print("Troubleshooting:")
        if not neo4j_ok:
            print("  - Neo4j: Check logs with: docker-compose logs neo4j")
        if not postgres_ok:
            print("  - PostgreSQL: Check logs with: docker-compose logs postgres")
        print("  - Ensure Docker Desktop is running")
        print("  - Ensure services are started: docker-compose up -d")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(main())
