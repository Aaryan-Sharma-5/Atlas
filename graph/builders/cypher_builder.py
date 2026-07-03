"""Validated Entity/Relationship objects -> parameterized Cypher.

This module RETURNS Cypher strings and parameter dicts; it never executes
them (execution is neo4j_writer.py, Day 7). All values travel as
parameters. Labels and relationship types cannot be parameterized in
Cypher, so they are embedded — but only after whitelisting against the
schema (NODE_HIERARCHY / RELATIONSHIP_TYPES), which validation guarantees.
"""

from collections import defaultdict
from typing import Any

from models.entity import NODE_HIERARCHY, Entity
from models.relationship import RELATIONSHIP_TYPES, Relationship

CypherStatement = tuple[str, dict[str, Any]]


def build_entity_cypher(entity: Entity) -> CypherStatement:
    """Single-entity CREATE with base label + specific label."""
    _assert_valid_labels(entity)
    cypher = f"CREATE (n:{entity.base_type}:{entity.type}) SET n = $props"
    return cypher, {"props": _flat_props(entity)}


def build_relationship_cypher(rel: Relationship) -> CypherStatement:
    """Edge CREATE, matching endpoints by id."""
    if rel.type not in RELATIONSHIP_TYPES:
        raise ValueError(f"unvalidated relationship type: {rel.type!r}")
    cypher = (
        "MATCH (a {id: $source_id}), (b {id: $target_id}) "
        f"CREATE (a)-[r:{rel.type}]->(b) SET r = $props"
    )
    params = {
        "source_id": rel.source_id,
        "target_id": rel.target_id,
        "props": _rel_props(rel),
    }
    return cypher, params


def build_entity_batch_cypher(entities: list[Entity]) -> list[CypherStatement]:
    """Batch CREATE via UNWIND, one statement per node type.

    Labels are per-statement (Cypher can't parameterize them), so entities
    are grouped by type; 3k nodes become ~4 round-trips instead of 3k.
    """
    by_type: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        _assert_valid_labels(entity)
        by_type[entity.type].append(entity)

    statements: list[CypherStatement] = []
    for node_type, group in by_type.items():
        base = NODE_HIERARCHY[node_type]
        cypher = f"UNWIND $rows AS row CREATE (n:{base}:{node_type}) SET n = row"
        rows = [_flat_props(e) for e in group]
        statements.append((cypher, {"rows": rows}))
    return statements


def _flat_props(entity: Entity) -> dict[str, Any]:
    """Mandatory fields + custom properties as one flat dict.

    Neo4j properties must be primitives or lists of primitives; nested
    dicts fail loudly here instead of at write time.
    """
    props: dict[str, Any] = {
        "id": entity.id,
        "name": entity.name,
        "confidence": entity.confidence,
        "extraction_source": entity.extraction_source,
        "extraction_method": entity.extraction_method,
    }
    for key, value in entity.properties.items():
        if isinstance(value, dict):
            raise ValueError(
                f"{entity.id}: nested dict property {key!r} cannot be stored in Neo4j"
            )
        props[key] = value
    return props


def _rel_props(rel: Relationship) -> dict[str, Any]:
    props: dict[str, Any] = {
        "confidence": rel.confidence,
        "extraction_source": rel.extraction_source,
        "extraction_method": rel.extraction_method,
    }
    for key, value in rel.properties.items():
        if isinstance(value, dict):
            raise ValueError(
                f"relationship {rel.type}: nested dict property {key!r} "
                "cannot be stored in Neo4j"
            )
        props[key] = value
    return props


def _assert_valid_labels(entity: Entity) -> None:
    # Entity.__post_init__ enforces this, but the builder embeds labels in
    # Cypher text, so re-check as the last line of injection defense.
    if entity.type not in NODE_HIERARCHY:
        raise ValueError(f"unvalidated entity type: {entity.type!r}")
