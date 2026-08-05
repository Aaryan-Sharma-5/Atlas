"""Vector retriever (Step 10C). Two modes, both against Neo4j's native vector indexes (graph/schema/indexes.cypher, populated in Step 9.5) via the fresh-text query pattern already proven in testing/test_embedding_write.py's close-out check: `db.index.vector.queryNodes(<index>, k, <query_vector>)`.

- search_by_name(): short-text mode, against entity_name_embedding + canonical_name_embedding (short name-similarity, same embedding space Stage 2 resolution already uses). 
- search_by_passage(): long-text mode, against chunk_embedding (passage-level semantic search).
Both embed the query with resolution.matchers.embedding_matcher.embed_names — same model
(all-MiniLM-L6-v2), same L2-normalization, so query vectors live in the same space the stored vectors were written in. No controlled-template constraint here (unlike graph_retriever / "no LLM-generated Cypher"): these are still fixed, parameterizedstatements, just against a vector index instead of a graph pattern.
"""

from typing import Any

from neo4j import GraphDatabase

from graph.builders.neo4j_writer import DEFAULT_PASSWORD, DEFAULT_URI, DEFAULT_USER
from models.retrieval_result import RetrievalResult
from resolution.matchers.embedding_matcher import embed_names

_STRUCTURAL_LABELS = {"Entity", "Canonical", "Resource", "CodeEntity", "KnowledgeEntity"}

_ENTITY_NAME_QUERY = (
    "CALL db.index.vector.queryNodes('entity_name_embedding', $k, $v) "
    "YIELD node, score "
    "RETURN properties(node) AS props, labels(node) AS labels, score"
)
_CANONICAL_NAME_QUERY = (
    "CALL db.index.vector.queryNodes('canonical_name_embedding', $k, $v) "
    "YIELD node, score "
    "RETURN properties(node) AS props, labels(node) AS labels, score"
)
_CHUNK_QUERY = (
    "CALL db.index.vector.queryNodes('chunk_embedding', $k, $v) "
    "YIELD node, score "
    "RETURN properties(node) AS props, score"
)


def search_by_name(
    query_text: str,
    top_k: int = 5,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> list[RetrievalResult]:
    """Short-text similarity against raw Entity names and Canonical names, merged and re-ranked by score. Queries both indexes (top_k each, disjoint label sets, so no dedup needed) rather than picking one, since a name query has no way to know in advance whether its best match is a resolved Canonical or an unresolved raw Entity.
    """
    query_vector = embed_names([query_text])[0].tolist()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            entity_rows = session.run(_ENTITY_NAME_QUERY, k=top_k, v=query_vector)
            results = [_name_result(r["props"], r["labels"], r["score"]) for r in entity_rows]
            canonical_rows = session.run(_CANONICAL_NAME_QUERY, k=top_k, v=query_vector)
            results += [_name_result(r["props"], r["labels"], r["score"]) for r in canonical_rows]
    finally:
        driver.close()
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]


def search_by_passage(
    query_text: str,
    top_k: int = 5,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> list[RetrievalResult]:
    """Passage-level similarity against Chunk.embedding. Chunks are never resolution targets (§12.5 — resolution operates on Entity/Canonical, not Chunk), so target_resolution is always "unresolved" here, same as graph_retriever's chunk results.
    """
    query_vector = embed_names([query_text])[0].tolist()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            rows = session.run(_CHUNK_QUERY, k=top_k, v=query_vector)
            return [_chunk_result(r["props"], r["score"]) for r in rows]
    finally:
        driver.close()


def _name_result(props: dict[str, Any], labels: list[str], score: float) -> RetrievalResult:
    is_canonical = "Canonical" in labels
    return RetrievalResult(
        entity_id=props["id"],
        result_type="Canonical" if is_canonical else "Entity",
        score=float(score),
        source="vector",
        matched_text=_display_name(props),
        target_resolution="canonical" if is_canonical else "unresolved",
        confidence_method="cosine_similarity_name",
        metadata={
            "node_type": _specific_type(labels),
            "confidence": props.get("confidence"),
            "extraction_source": props.get("extraction_source"),
        },
    )


def _chunk_result(props: dict[str, Any], score: float) -> RetrievalResult:
    content = props.get("content", "")
    return RetrievalResult(
        entity_id=props["id"],
        result_type="Chunk",
        score=float(score),
        source="vector",
        matched_text=content[:200],
        target_resolution="unresolved",
        confidence_method="cosine_similarity_passage",
        chunk_id=props["id"],
        metadata={"chunk_index": props.get("chunk_index"), "source_id": props.get("source_id")},
    )


def _specific_type(labels: list[str]) -> str:
    specific = [l for l in labels if l not in _STRUCTURAL_LABELS]
    return specific[0] if specific else "Unknown"


def _display_name(props: dict[str, Any]) -> str:
    return props.get("canonical_name") or props.get("name") or props.get("full_name") or ""
