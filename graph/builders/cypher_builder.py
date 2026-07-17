"""Validated Entity/Relationship objects -> parameterized Cypher.

This module RETURNS Cypher strings and parameter dicts; it never executes them (execution is neo4j_writer.py). All values travel as parameters. Labels and relationship types cannot be parameterized in Cypher, so they are embedded — but only after whitelisting against the schema (NODE_HIERARCHY / RELATIONSHIP_TYPES), which validation guarantees.
"""

from collections import defaultdict
from typing import Any

from models.entity import NODE_HIERARCHY, Entity
from models.relationship import RELATIONSHIP_TYPES, Relationship
from models.resolution import ResolutionDecision

CypherStatement = tuple[str, dict[str, Any]]

RESOLUTION_SOURCE = "resolution:candidate_pairs"
RESOLUTION_METHOD = "merge_resolver:union_find@v1"


def build_entity_cypher(entity: Entity) -> CypherStatement:
    """Single-entity CREATE.

    Three labels: :Entity (universal, carries the uniqueness constraint from constraints.cypher), base type, and specific type.
    """
    _assert_valid_labels(entity)
    cypher = f"CREATE (n:Entity:{entity.base_type}:{entity.type}) SET n = $props"
    return cypher, {"props": _flat_props(entity)}


def build_entity_merge_cypher(entity: Entity) -> CypherStatement:
    """Idempotent single-entity MERGE, vs. build_entity_cypher's CREATE.

    For entities that may legitimately be written more than once across extraction re-runs (e.g. Paper nodes backing relationship extraction, written once per corpus but re-validated/re-written on every 7A run) - CREATE would hit unique_entity_id on the second run instead of proving idempotency.
    """
    _assert_valid_labels(entity)
    cypher = f"MERGE (n:Entity:{entity.base_type}:{entity.type} {{id: $id}}) SET n = $props"
    return cypher, {"id": entity.id, "props": _flat_props(entity)}


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

    Labels are per-statement (Cypher can't parameterize them), so entities are grouped by type; 3k nodes become ~4 round-trips instead of 3k.
    """
    by_type: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        _assert_valid_labels(entity)
        by_type[entity.type].append(entity)

    statements: list[CypherStatement] = []
    for node_type, group in by_type.items():
        base = NODE_HIERARCHY[node_type]
        cypher = (
            f"UNWIND $rows AS row CREATE (n:Entity:{base}:{node_type}) SET n = row"
        )
        rows = [_flat_props(e) for e in group]
        statements.append((cypher, {"rows": rows}))
    return statements


def build_resolution_cypher(
    decision: ResolutionDecision, decided_at: int
) -> list[CypherStatement]:
    """Validated ResolutionDecision -> Canonical node + SAME_AS edges (Rule 8: source entities are matched, never modified or deleted).

    MERGE (not CREATE) on the canonical node and edges so a re-run of the same decision set is idempotent under the unique_canonical_id constraint. NONE decisions produce no statements.
    """
    if decision.action == "NONE":
        return []
    if decision.entity_type not in NODE_HIERARCHY:
        raise ValueError(f"unvalidated entity type: {decision.entity_type!r}")

    node = (
        f"MERGE (c:Canonical:{decision.entity_type} {{id: $id}}) SET c += $props",
        {
            "id": decision.canonical_id,
            "props": {
                "canonical_name": decision.canonical_name,
                "created_at": decided_at,
                "source_count": len(decision.source_ids),
                "confidence": decision.confidence,
                "extraction_source": RESOLUTION_SOURCE,
                "extraction_method": RESOLUTION_METHOD,
            },
        },
    )
    edges = (
        "MATCH (c:Canonical {id: $canonical_id}) "
        "UNWIND $source_ids AS sid "
        "MATCH (e:Entity {id: sid}) "
        "MERGE (c)-[r:SAME_AS]->(e) SET r = $props",
        {
            "canonical_id": decision.canonical_id,
            "source_ids": decision.source_ids,
            "props": {
                "confidence": decision.confidence,
                "decision_action": decision.action,
                "decided_at": decided_at,
                "extraction_source": RESOLUTION_SOURCE,
                "extraction_method": RESOLUTION_METHOD,
            },
        },
    )
    return [node, edges]


def build_authored_by_cypher(rel: Relationship) -> CypherStatement:
    """Validated AUTHORED_BY (Paper -> Person|Canonical) -> MERGE Cypher (7A.1).

    Same idempotent MERGE pattern as build_resolution_cypher: re-running extraction over the same corpus must not duplicate edges. Target may be either a :Canonical or a raw :Entity (resolve_target.py's fallback), so the match is unlabeled on the target side, same as build_relationship_cypher.
    """
    if rel.type != "AUTHORED_BY":
        raise ValueError(f"unvalidated relationship type: {rel.type!r}")
    cypher = (
        "MATCH (a {id: $source_id}) MATCH (b {id: $target_id}) "
        "MERGE (a)-[r:AUTHORED_BY]->(b) SET r = $props"
    )
    params = {
        "source_id": rel.source_id,
        "target_id": rel.target_id,
        "props": _rel_props(rel),
    }
    return cypher, params


def _flat_props(entity: Entity) -> dict[str, Any]:
    """Mandatory fields + custom properties as one flat dict.

    Neo4j properties must be primitives or lists of primitives; nested dicts fail loudly here instead of at write time.
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
    # Entity.__post_init__ enforces this, but the builder embeds labels in Cypher text, so re-check as the last line of injection defense.
    if entity.type not in NODE_HIERARCHY:
        raise ValueError(f"unvalidated entity type: {entity.type!r}")
