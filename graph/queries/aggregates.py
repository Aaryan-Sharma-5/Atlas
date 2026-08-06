"""Whole-graph aggregate read queries — no anchor entity, unlike graph_retriever.py's get_entity_context() (Step 10B) which always starts from one seed id. Added Step 12 closeout: the investigation (docs/architecture.md, Step 12 section) found the graph questions get_entity_context() genuinely can't express are a narrow, enumerable class — "top-N by some count" / "count-threshold filter" / "aggregate stat over a relationship type" — not evidence of open-ended query diversity. Three fixed, parameterized functions close that class. No query-text parsing, no LLM, no new validation pipeline: same pattern as every other graph/queries/ file (resolve_target.py, document_reader.py, entity_reader.py) — fixed Cypher, parameters only.
"""

from typing import Any

from neo4j import GraphDatabase

from graph.builders.neo4j_writer import DEFAULT_PASSWORD, DEFAULT_URI, DEFAULT_USER
from models.relationship import RELATIONSHIP_TYPES

_MOST_MENTIONED_QUERY = (
    "MATCH (s)-[:MENTIONS]->(c:Canonical) "
    "WITH c, count(DISTINCT s) AS source_count "
    "RETURN c.id AS id, c.canonical_name AS canonical_name, source_count "
    "ORDER BY source_count DESC LIMIT $limit"
)

_ALIAS_COUNT_QUERY = (
    "MATCH (c:Canonical)-[:SAME_AS]->(e) "
    "WITH c, count(e) AS alias_count "
    "WHERE alias_count >= $min_aliases "
    "RETURN c.id AS id, c.canonical_name AS canonical_name, alias_count "
    "ORDER BY alias_count DESC LIMIT $limit"
)


def most_mentioned_canonicals(
    limit: int = 10,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> list[dict[str, Any]]:
    """Canonicals ranked by distinct MENTIONS source count — "which identity is referenced most broadly across sources" (Step 12 investigation question 4). Rows: {id, canonical_name, source_count}."""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            return [r.data() for r in session.run(_MOST_MENTIONED_QUERY, limit=limit)]
    finally:
        driver.close()


def canonicals_by_alias_count(
    min_aliases: int = 3,
    limit: int = 10,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> list[dict[str, Any]]:
    """Canonicals with at least min_aliases raw SAME_AS members — "which identities aggregate the most duplicate mentions" (Step 12 investigation question 5). Rows: {id, canonical_name, alias_count}."""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            return [
                r.data()
                for r in session.run(
                    _ALIAS_COUNT_QUERY, min_aliases=min_aliases, limit=limit
                )
            ]
    finally:
        driver.close()


def relationship_type_stats(
    relationship_type: str,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> dict[str, Any]:
    """Aggregate confidence stats (count, avg/min/max confidence) for one relationship type across the whole graph — "how confident is Atlas about its AUTHORED_BY edges overall" (Step 12 investigation question 8's class, generalized to any relationship type rather than hardcoding one). relationship_type is validated against models.relationship.RELATIONSHIP_TYPES before being embedded — Cypher can't parameterize a relationship type name, same whitelist-before-embed discipline graph/builders/cypher_builder.py already uses for the same reason.
    """
    if relationship_type not in RELATIONSHIP_TYPES:
        raise ValueError(f"unknown relationship type: {relationship_type!r}")

    query = (
        f"MATCH ()-[r:{relationship_type}]->() "
        "RETURN count(r) AS edge_count, avg(r.confidence) AS avg_confidence, "
        "min(r.confidence) AS min_confidence, max(r.confidence) AS max_confidence"
    )
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            record = session.run(query).single()
            return record.data() if record else {
                "edge_count": 0,
                "avg_confidence": None,
                "min_confidence": None,
                "max_confidence": None,
            }
    finally:
        driver.close()
