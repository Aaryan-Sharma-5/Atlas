"""Graph retriever (Step 10B). Controlled Cypher templates only — no LLM-generated Cypher, retrieval is planner-first and the Step 10 plan's explicit constraint.

Input: a Canonical or Entity id. Output: the node itself, its direct AUTHORED_BY/MENTIONS/ SAME_AS relationships in either direction, and the Chunk backing each relationship's evidence_chunk_id where the Step 9.5 enrichment set one. HAS_CHUNK itself is not traversed here: evidence_chunk_id already names the specific supporting chunk, and that id was only ever set on a chunk already reachable from its source via HAS_CHUNK (Step 9.5), so a direct id lookup is sufficient and avoids pulling in a source's entire chunk set.
"""

from typing import Any

from neo4j import GraphDatabase

from graph.builders.neo4j_writer import DEFAULT_PASSWORD, DEFAULT_URI, DEFAULT_USER
from models.relationship import RELATIONSHIP_TYPES
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
    relationship_types: list[str] | None = None,
    include_seed: bool = True,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> list[RetrievalResult]:
    """The queried node, its direct relationship neighbors, and their supporting chunks.

    relationship_types=None (default): all three direct types (AUTHORED_BY/MENTIONS/ SAME_AS), the original Step 10B behavior. Pass a subset (e.g. ["AUTHORED_BY"]) to filter the traversal itself — the WHERE type(r) IN $rel_types clause in _NEIGHBORS_QUERY runs inside Neo4j before scoring/sorting, not as a Python post-filter over the full result set. Added Step 10E+ baseline testing: for a high-fan-out node (a Paper with thousands of MENTIONS edges, or a Repository with hundreds), the answer to a type-specific question ("who authored X") existed in the unfiltered result set but was buried past any usable rank (e.g. rank 884 of 3806) because every relationship type's confidence clusters near 1.0 alike — confidence sorting alone can't recover type-specific relevance, only filtering can. This function still doesn't decide which type to request for a given question — that's Step 11 planner territory — it just makes a filtered query possible at all.

    include_seed=True (default): the queried node itself is included as a tier-1 result (metadata["is_seed"]=True), same as always. Pass False to omit it entirely — added Step 13 closeout (§13 row 10): for "who authored X"/"what does X mention" style questions, the seed is never a valid answer (it's the *subject*, not a relationship target), yet it always outranked the real answer at tier 1 (score 1.0, same tier as the answer itself). This function still doesn't decide *when* to pass False for a given question — same non-decision as relationship_types above, and for the same reason: that's intent, planner territory (planner/planner.py decides based on which relationship_types were requested). Blanket-excluding the seed unconditionally here would be wrong: eval questions 2/5/12/13 all correctly expect the seed itself as the top answer (e.g. "what does person_erik_cambria aggregate" — the canonical's own identity, with its SAME_AS aliases as supporting evidence, not a relationship target to find instead of it) — checked against examples/expected_output/retrieval_eval_questions.json's own expected evidence before choosing a caller-controlled flag over unconditional exclusion.

    Returns [] if entity_id matches no node (caller's problem to handle, e.g. planner falling back to vector/keyword once those exist).
    """
    if relationship_types is not None:
        unknown = set(relationship_types) - RELATIONSHIP_TYPES
        if unknown:
            raise ValueError(f"unknown relationship type(s): {sorted(unknown)}")
    rel_types = relationship_types if relationship_types is not None else list(_DIRECT_RELATIONSHIP_TYPES)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            self_record = session.run(_SELF_QUERY, id=entity_id).single()
            if self_record is None:
                return []

            results = (
                [_self_result(entity_id, self_record["props"], self_record["labels"])]
                if include_seed
                else []
            )

            neighbor_rows = list(
                session.run(_NEIGHBORS_QUERY, id=entity_id, rel_types=rel_types)
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

            # Two-tier sort, found necessary during Step 10E/10F baseline testing (§13 row 9). Tier 1 ("answer"): self + neighbor Entity/Canonical results — these are what a question is actually asking about. Tier 2 ("supporting evidence"): Chunk results pulled in via evidence_chunk_id — these back up an answer, they aren't the answer. Chunks were previously flatly scored 1.0, identical to the queried node itself, so on a high-fan-out node they numerically outnumbered and outranked the actual answer-entity by sheer count (verified: paper_2003_02320v6_pdf filtered to AUTHORED_BY still buried its target author at rank 14, behind ~12 same-scored chunks). result_type == "Chunk" is reused as the tier discriminator rather than adding a new field to RetrievalResult — it already distinguishes exactly this ("Chunk" vs "Entity"/"Canonical"), so a second field would be redundant. Within each tier, still sorted by score descending (original reasoning below still applies per tier).
            
            # Original note (Step 10E, still true within a tier): neighbor_rows comes back in Neo4j's traversal order (arbitrary, no ORDER BY), not by relevance — unlike vector_retriever (index-native score order) and keyword_retriever (explicit sort). retrieval/fusion.py's RRF only uses each source's RANK, not its score, so an unsorted list silently made "rank" random for graph results and would have corrupted every fused ranking that included a graph contribution.
            results.sort(key=lambda r: (r.result_type == "Chunk", -r.score))
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
        confidence_method="graph_exact_match",
        path=[{"id": entity_id, "hop": 0}],
        metadata={
            "node_type": _specific_type(labels),
            "confidence": props.get("confidence"),
            "is_seed": True,
        },
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
        confidence_method="graph_edge_confidence",
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
        confidence_method="graph_evidence_chunk",
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
