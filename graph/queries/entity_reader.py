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
