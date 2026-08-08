"""Read-only entity queries.

graph/queries/ is, with graph/builders/. Returns models.Entity objects so downstream consumers (resolution/) never see Neo4j records.
"""

from typing import Any

from neo4j import GraphDatabase

from graph.builders.neo4j_writer import DEFAULT_PASSWORD, DEFAULT_URI, DEFAULT_USER
from models.entity import NODE_HIERARCHY, Entity

_MANDATORY = {"id", "name", "confidence", "extraction_source", "extraction_method"}
_STRUCTURAL_LABELS = {"Entity", "Resource", "CodeEntity", "KnowledgeEntity"}


def fetch_all_entities(
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> list[Entity]:
    """Load every :Entity node back into a models.Entity object."""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            records = session.run(
                "MATCH (n:Entity) RETURN properties(n) AS props, labels(n) AS labels"
            )
            return [_to_entity(r["props"], r["labels"]) for r in records]
    finally:
        driver.close()


def _to_entity(props: dict[str, Any], labels: list[str]) -> Entity:
    node_type = next(l for l in labels if l not in _STRUCTURAL_LABELS)
    if node_type not in NODE_HIERARCHY:
        raise ValueError(f"node {props.get('id')!r} has unknown type label {node_type!r}")
    return Entity(
        id=props["id"],
        type=node_type,
        name=props["name"],
        confidence=props["confidence"],
        extraction_source=props["extraction_source"],
        extraction_method=props["extraction_method"],
        properties={k: v for k, v in props.items() if k not in _MANDATORY},
    )


# Canonical nodes carry :Canonical:{SpecificType} only (no :Entity/:Resource/:CodeEntity/:KnowledgeEntity — physical.md's Canonical section), so the type-label lookup below needs "Canonical" excluded too, on top of the structural labels _to_entity already skips.
_NON_TYPE_LABELS = _STRUCTURAL_LABELS | {"Canonical"}

# Single node lookup, either :Entity or :Canonical, plus its SAME_AS members if it's a Canonical — one round trip rather than a conditional second query, since the caller (api/routes/entities.py) doesn't know in advance which kind of node entity_id names.
_ENTITY_DETAIL_QUERY = (
    "MATCH (n {id: $id}) WHERE n:Entity OR n:Canonical "
    "OPTIONAL MATCH (n)-[r:SAME_AS]->(e:Entity) "
    "RETURN properties(n) AS props, labels(n) AS labels, "
    "collect(CASE WHEN e IS NOT NULL THEN "
    "{id: e.id, name: e.name, confidence: r.confidence, decision_action: r.decision_action} "
    "END) AS aliases"
)


def fetch_entity_detail(
    entity_id: str,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> dict[str, Any] | None:
    """Full detail for one node by id, Entity or Canonical alike. None if no such node.

    Returns {id, node_type, is_canonical, name, confidence, extraction_source, extraction_method, properties, aliases}. `name` coalesces Entity.name and Canonical.canonical_name into one display field — same coalescing precedent as document_reader.py's `title` (Paper.title vs Repository.name). `properties` carries every remaining node property verbatim except name_embedding/embedding, dropped here (not upstream — the vectors stay in Neo4j untouched) since a 384-float vector has no API-consumer use and would bloat every response; `aliases` is only non-empty when is_canonical is True.
    """
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            record = session.run(_ENTITY_DETAIL_QUERY, id=entity_id).single()
            if record is None:
                return None

            props = dict(record["props"])
            labels = record["labels"]
            is_canonical = "Canonical" in labels
            node_type = next((l for l in labels if l not in _NON_TYPE_LABELS), None)

            name = props.pop("canonical_name", None) if is_canonical else props.pop("name", None)
            confidence = props.pop("confidence")
            extraction_source = props.pop("extraction_source")
            extraction_method = props.pop("extraction_method")
            props.pop("name_embedding", None)
            props.pop("embedding", None)

            return {
                "id": props.pop("id", entity_id),
                "node_type": node_type,
                "is_canonical": is_canonical,
                "name": name,
                "confidence": confidence,
                "extraction_source": extraction_source,
                "extraction_method": extraction_method,
                "properties": props,
                "aliases": [a for a in record["aliases"] if a is not None] if is_canonical else [],
            }
    finally:
        driver.close()
