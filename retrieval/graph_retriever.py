"""Graph retriever (Step 10B). Controlled Cypher templates only — no LLM-generated Cypher, retrieval is planner-first and the Step 10 plan's explicit constraint.

Input: a Canonical or Entity id. Output: the node itself, its direct AUTHORED_BY/MENTIONS/ SAME_AS relationships in either direction, and the Chunk backing each relationship's evidence_chunk_id where the Step 9.5 enrichment set one. HAS_CHUNK itself is not traversed here: evidence_chunk_id already names the specific supporting chunk, and that id was only ever set on a chunk already reachable from its source via HAS_CHUNK (Step 9.5), so a direct id lookup is sufficient and avoids pulling in a source's entire chunk set.
"""

from typing import Any

from neo4j import GraphDatabase

from graph.builders.neo4j_writer import DEFAULT_PASSWORD, DEFAULT_URI, DEFAULT_USER
from models.retrieval_result import RetrievalResult

_DIRECT_RELATIONSHIP_TYPES = ("AUTHORED_BY", "MENTIONS", "SAME_AS")
_STRUCTURAL_LABELS = {"Entity", "Canonical", "Resource", "CodeEntity", "KnowledgeEntity"}

_SELF_QUERY = "MATCH (n {id: $id}) RETURN properties(n) AS props, labels(n) AS labels"

_NEIGHBORS_QUERY = (
    "MATCH (n {id: $id})-[r]-(m) WHERE type(r) IN $rel_types "
    "RETURN type(r) AS rel_type, properties(r) AS rel_props, "
    "properties(m) AS m_props, labels(m) AS m_labels, "
    "startNode(r).id = $id AS outgoing"
)

_CHUNKS_QUERY = "MATCH (c:Chunk) WHERE c.id IN $ids RETURN properties(c) AS props"


def get_entity_context(
    entity_id: str,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> list[RetrievalResult]:
    """The queried node, its direct relationship neighbors, and their supporting chunks.

    Returns [] if entity_id matches no node (caller's problem to handle, e.g. planner falling back to vector/keyword once those exist).
    """
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            self_record = session.run(_SELF_QUERY, id=entity_id).single()
            if self_record is None:
                return []

            results = [_self_result(entity_id, self_record["props"], self_record["labels"])]

            neighbor_rows = list(
                session.run(
                    _NEIGHBORS_QUERY, id=entity_id, rel_types=list(_DIRECT_RELATIONSHIP_TYPES)
                )
            )
            chunk_ids: set[str] = set()
            for row in neighbor_rows:
                results.append(_neighbor_result(entity_id, row))
                evidence_chunk_id = row["rel_props"].get("evidence_chunk_id")
                if evidence_chunk_id:
                    chunk_ids.add(evidence_chunk_id)

            if chunk_ids:
                chunk_rows = session.run(_CHUNKS_QUERY, ids=list(chunk_ids))
                results.extend(_chunk_result(r["props"]) for r in chunk_rows)

            return results
    finally:
        driver.close()


def _self_result(entity_id: str, props: dict[str, Any], labels: list[str]) -> RetrievalResult:
    return RetrievalResult(
        entity_id=entity_id,
        result_type=_node_result_type(labels),
        score=1.0,
        source="graph",
        matched_text=_display_name(props),
        target_resolution=_target_resolution(labels),
        path=[{"id": entity_id, "hop": 0}],
        metadata={"node_type": _specific_type(labels), "confidence": props.get("confidence")},
    )


def _neighbor_result(origin_id: str, row: dict[str, Any]) -> RetrievalResult:
    m_props = row["m_props"]
    m_labels = row["m_labels"]
    rel_props = row["rel_props"]
    direction = "outgoing" if row["outgoing"] else "incoming"
    neighbor_id = m_props["id"]

    return RetrievalResult(
        entity_id=neighbor_id,
        result_type=_node_result_type(m_labels),
        score=float(rel_props.get("confidence", 0.0)),
        source="graph",
        matched_text=_display_name(m_props),
        target_resolution=_target_resolution(m_labels),
        chunk_id=rel_props.get("evidence_chunk_id"),
        path=[
            {"id": origin_id, "hop": 0},
            {
                "relationship": row["rel_type"],
                "direction": direction,
                "id": neighbor_id,
                "hop": 1,
            },
        ],
        metadata={
            "node_type": _specific_type(m_labels),
            "relationship_type": row["rel_type"],
            "direction": direction,
            "extraction_source": rel_props.get("extraction_source"),
            "extraction_method": rel_props.get("extraction_method"),
            "decision_action": rel_props.get("decision_action"),
        },
    )


def _chunk_result(props: dict[str, Any]) -> RetrievalResult:
    content = props.get("content", "")
    return RetrievalResult(
        entity_id=props["id"],
        result_type="Chunk",
        score=1.0,
        source="graph",
        matched_text=content[:200],
        target_resolution="unresolved",
        chunk_id=props["id"],
        metadata={"chunk_index": props.get("chunk_index"), "source_id": props.get("source_id")},
    )


def _node_result_type(labels: list[str]) -> str:
    return "Canonical" if "Canonical" in labels else "Entity"


def _target_resolution(labels: list[str]) -> str:
    return "canonical" if "Canonical" in labels else "unresolved"


def _specific_type(labels: list[str]) -> str:
    specific = [l for l in labels if l not in _STRUCTURAL_LABELS]
    return specific[0] if specific else "Unknown"


def _display_name(props: dict[str, Any]) -> str:
    return props.get("canonical_name") or props.get("name") or props.get("full_name") or ""
