"""Executes builder-generated Cypher against Neo4j.

The only module in Atlas that opens a write connection. Writes accept a ValidationResult, not raw lists - code cannot reach Neo4j without passing graph/validators/ first.
"""

import os
from pathlib import Path
from types import TracebackType
from typing import Any

from neo4j import GraphDatabase

from graph.builders.cypher_builder import (
    build_authored_by_cypher,
    build_entity_batch_cypher,
    build_entity_merge_cypher,
    build_evidence_enrichment_cypher,
    build_has_chunk_cypher,
    build_mentions_cypher,
    build_relationship_cypher,
    build_resolution_cypher,
)
from graph.validators.validator import DecisionValidationResult, ValidationResult
from models.entity import Entity
from models.relationship import Relationship

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

    def write_resolution(
        self, validated: DecisionValidationResult, decided_at: int
    ) -> dict[str, int]:
        """Write validated ResolutionDecisions as Canonical nodes + SAME_AS edges in one transaction. Accepts a DecisionValidationResult only, same gate as write(): resolution output cannot reach Neo4j without graph/validators/.

        Non-destructive by construction (Rule 8): the generated Cypher only MERGEs :Canonical nodes and :SAME_AS edges and MATCHes existing :Entity nodes; no :Entity is modified or deleted.
        """
        statements = [
            stmt
            for decision in validated.decisions
            for stmt in build_resolution_cypher(decision, decided_at)
        ]
        with self._driver.session() as session:
            with session.begin_transaction() as tx:
                for cypher, params in statements:
                    tx.run(cypher, params).consume()
                tx.commit()
        written = [d for d in validated.decisions if d.action != "NONE"]
        return {
            "canonical_nodes_written": len(written),
            "same_as_edges_written": sum(len(d.source_ids) for d in written),
        }

    def write_authored_by(
        self, papers: list[Entity], relationships: list[Relationship]
    ) -> dict[str, int]:
        """Write Paper entities + AUTHORED_BY edges in one transaction (7A.1)."""
        counts = self._write_relationship_batch(papers, relationships, build_authored_by_cypher)
        return {
            "paper_nodes_written": counts["source_nodes_written"],
            "authored_by_edges_written": counts["edges_written"],
        }

    def write_mentions(
        self, sources: list[Entity], relationships: list[Relationship]
    ) -> dict[str, int]:
        """Write Markdown/Repository source entities + MENTIONS edges in one transaction (7A.2a)."""
        counts = self._write_relationship_batch(sources, relationships, build_mentions_cypher)
        return {
            "source_nodes_written": counts["source_nodes_written"],
            "mentions_edges_written": counts["edges_written"],
        }

    def write_chunk_backfill(
        self,
        chunks: list[Entity],
        has_chunk_relationships: list[Relationship],
        evidence_enrichments: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Write Chunk nodes + HAS_CHUNK edges + evidence_chunk_id enrichment on existing AUTHORED_BY/MENTIONS edges, all in one transaction (Step 9.5).

        Chunks and HAS_CHUNK are MERGE-based (idempotent, same as write_authored_by/write_mentions). The enrichment statements are SET on edges that already exist from a prior session (7A.1/7A.2a) - they MATCH, never MERGE-create, so a mismatch surfaces as 0 rows affected rather than silently creating a relationship that shouldn't exist.
        """
        chunk_statements = [build_entity_merge_cypher(c) for c in chunks]
        has_chunk_statements = [build_has_chunk_cypher(r) for r in has_chunk_relationships]
        enrichment_statements = [
            build_evidence_enrichment_cypher(
                e["source_id"], e["rel_type"], e["target_id"], e["chunk_id"]
            )
            for e in evidence_enrichments
        ]

        with self._driver.session() as session:
            with session.begin_transaction() as tx:
                for cypher, params in chunk_statements + has_chunk_statements + enrichment_statements:
                    tx.run(cypher, params).consume()
                tx.commit()

        return {
            "chunk_nodes_written": len(chunks),
            "has_chunk_edges_written": len(has_chunk_relationships),
            "evidence_enrichments_written": len(evidence_enrichments),
        }

    def _write_relationship_batch(
        self,
        source_entities: list[Entity],
        relationships: list[Relationship],
        build_edge_cypher,
    ) -> dict[str, int]:
        """Shared body for the per-relationship-type write methods above.

        Both sides MERGE-based (idempotent): re-running extraction over the same corpus must not duplicate source nodes or edges. Existing :Entity/:Canonical nodes are only ever MATCHed, never modified.
        """
        source_statements = [build_entity_merge_cypher(e) for e in source_entities]
        edge_statements = [build_edge_cypher(r) for r in relationships]

        with self._driver.session() as session:
            with session.begin_transaction() as tx:
                for cypher, params in source_statements + edge_statements:
                    tx.run(cypher, params).consume()
                tx.commit()

        return {
            "source_nodes_written": len(source_entities),
            "edges_written": len(relationships),
        }

    def run_read(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Read-only helper for verification. Retrieval-facing query templates belong in graph/queries/ (built in Phase 4)."""
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
