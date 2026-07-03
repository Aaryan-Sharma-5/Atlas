"""Executes builder-generated Cypher against Neo4j.

The only module in Atlas that opens a write connection. Writes accept a ValidationResult, not raw lists - code cannot reach Neo4j without passing graph/validators/ first.
"""

import os
from pathlib import Path
from types import TracebackType
from typing import Any

from neo4j import GraphDatabase

from graph.builders.cypher_builder import (
    build_entity_batch_cypher,
    build_relationship_cypher,
)
from graph.validators.validator import ValidationResult

DEFAULT_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_USER = os.environ.get("NEO4J_USER", "neo4j")
DEFAULT_PASSWORD = os.environ.get("NEO4J_PASSWORD", "atlas_password_123")


class Neo4jWriter:
    def __init__(
        self,
        uri: str = DEFAULT_URI,
        user: str = DEFAULT_USER,
        password: str = DEFAULT_PASSWORD,
    ) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def apply_constraints(self, constraints_path: Path) -> int:
        """Run every statement in a .cypher schema file. Returns count."""
        statements = _parse_cypher_file(constraints_path)
        with self._driver.session() as session:
            for statement in statements:
                session.run(statement).consume()
        return len(statements)

    def clear_source(self, extraction_source: str) -> int:
        """Delete all nodes from one extraction source (idempotent re-runs).

        Deliberately scoped: only data whose provenance matches is touched, never the whole graph.
        """
        with self._driver.session() as session:
            result = session.run(
                "MATCH (n:Entity {extraction_source: $source}) "
                "DETACH DELETE n RETURN count(n) AS deleted",
                source=extraction_source,
            )
            return result.single()["deleted"]

    def write(self, validated: ValidationResult) -> dict[str, int]:
        """Write validated entities and relationships in one transaction.

        All-or-nothing: a constraint violation mid-batch rolls back everything rather than leaving a partial graph.
        """
        entity_statements = build_entity_batch_cypher(validated.entities)
        rel_statements = [
            build_relationship_cypher(rel) for rel in validated.relationships
        ]

        with self._driver.session() as session:
            with session.begin_transaction() as tx:
                for cypher, params in entity_statements + rel_statements:
                    tx.run(cypher, params).consume()
                tx.commit()

        return {
            "entities_written": len(validated.entities),
            "relationships_written": len(validated.relationships),
        }

    def run_read(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Read-only helper for verification. Retrieval-facing query
        templates belong in graph/queries/ (built in Phase 4)."""
        with self._driver.session() as session:
            return [record.data() for record in session.run(cypher, params or {})]


def _parse_cypher_file(path: Path) -> list[str]:
    """Split a .cypher file into statements, dropping // comments."""
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("//")
    ]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
