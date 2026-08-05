"""Keyword retriever (Step 10D). Queries the FULLTEXT indexes defined in graph/schema/indexes.cypher: document_fulltext (Paper|Markdown, on title+description), person_fulltext (Person, on full_name), technology_fulltext (Technology, on name+description+aliases), organization_fulltext (Organization, on name+description+aliases, added post-Q15 — Organization was missing from the original three, a real coverage gap, not a scoping choice) — via Neo4j's db.index.fulltext.queryNodes, same fixed-template approach as graph_retriever/ vector_retriever.

Canonical:{Person|Technology|Organization} nodes carry the same specific-type label these indexes are scoped to (physical.md: Canonical labels are :Canonical:{SpecificType}, no :Entity), so they are structurally in scope — but Canonical uses `canonical_name`, not `name`/`full_name`, and rarely populates `description`/`aliases` (verified: org_acl's Canonical has name=None, description=None, aliases=None), so none of the indexed properties are ever set on a Canonical in practice and none has ever appeared as a hit. A future Canonical-name backfill into these same properties would change this silently, which is why _keyword_result still checks the label explicitly rather than hardcoding target_resolution="unresolved". Chunk body text is not covered at all (document_fulltext only reaches title/description, not content) — see the Step 10D report for what that means for full-text coverage.
"""

from typing import Any

from neo4j import GraphDatabase

from graph.builders.neo4j_writer import DEFAULT_PASSWORD, DEFAULT_URI, DEFAULT_USER
from models.retrieval_result import RetrievalResult

_INDEX_NAMES = (
    "document_fulltext",
    "person_fulltext",
    "technology_fulltext",
    "organization_fulltext",
)
_STRUCTURAL_LABELS = {"Entity", "Canonical", "Resource", "CodeEntity", "KnowledgeEntity"}

_FULLTEXT_QUERY = (
    "CALL db.index.fulltext.queryNodes($index, $query_text) YIELD node, score "
    "RETURN properties(node) AS props, labels(node) AS labels, score "
    "LIMIT $k"
)


def search_by_keyword(
    query_text: str,
    top_k: int = 5,
    indexes: tuple[str, ...] = _INDEX_NAMES,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> list[RetrievalResult]:
    """Runs query_text (Lucene syntax — quote for an exact phrase) against each index in `indexes`, merges, and re-ranks by Lucene score. top_k applies per-index before merging (so a strong match in one index isn't crowded out by another) and again to the merged, sorted result.
    """
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            results: list[RetrievalResult] = []
            for index in indexes:
                rows = session.run(_FULLTEXT_QUERY, index=index, query_text=query_text, k=top_k)
                results += [_keyword_result(r["props"], r["labels"], r["score"]) for r in rows]
    finally:
        driver.close()
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]


def _keyword_result(props: dict[str, Any], labels: list[str], score: float) -> RetrievalResult:
    is_canonical = "Canonical" in labels
    return RetrievalResult(
        entity_id=props["id"],
        result_type="Canonical" if is_canonical else "Entity",
        score=float(score),
        source="keyword",
        matched_text=_display_name(props),
        target_resolution="canonical" if is_canonical else "unresolved",
        confidence_method="lucene_relevance",
        metadata={"node_type": _specific_type(labels)},
    )


def _specific_type(labels: list[str]) -> str:
    specific = [l for l in labels if l not in _STRUCTURAL_LABELS]
    return specific[0] if specific else "Unknown"


def _display_name(props: dict[str, Any]) -> str:
    return (
        props.get("full_name")
        or props.get("title")
        or props.get("name")
        or props.get("canonical_name")
        or ""
    )
