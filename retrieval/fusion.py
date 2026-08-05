"""RRF (Reciprocal Rank Fusion) — Step 10E. Combines per-source result lists from graph_retriever/vector_retriever/keyword_retriever into one ranked list.

Rank-based, deliberately not score-based. This session found (Step 10D/10F, evaluation question 11) that Lucene scores are not comparable even across the three fulltext indexes within keyword search alone — a 0.7 document_fulltext score and a 4.9 person_fulltext score for the same query are not on the same scale, so a strong document hit got buried under weaker-but-numerically-larger person hits. That already rules out blending raw scores within one retrieval method; it rules out blending across graph confidence, cosine similarity, and Lucene relevance even more decisively — none of the three share a scale or a distribution. RRF sidesteps the whole problem by using only each result's RANK within its own source's list: rrf_score(d) = sum over sources s containing d of  1 / (k + rank_s(d))

k=60 is the standard RRF default (Cormack et al. 2009) — it flattens the influence of rank 1 vs rank 2 so one source's top pick doesn't dominate purely by being first.

Canonical-aware collapsing (added after baseline testing, questions 12/13): fusing naively by entity_id treats a Canonical and its raw SAME_AS aliases as unrelated rows competing independently. In practice a Canonical often ranks #1 in graph (it's the deduplicated identity) while vector/keyword — which have no resolution awareness — rank its raw aliases individually, each a little lower; RRF's cross-source-agreement bonus then rewards the *aliases* (which multiple sources "agree" on separately) over the canonical itself, splitting one real-world entity's relevance across several rows instead of consolidating it. This is the same failure mode evaluation question 16 was built to name (a naive count that treats aliases as distinct overcounts). Fixed here by crediting every raw Entity result's rank contribution to its owning Canonical (graph.queries.resolve_target.resolve_target) before scoring, so the same real-world entity is exactly one fused row, however many aliases and sources found it.
"""

from collections import defaultdict

from graph.builders.neo4j_writer import DEFAULT_PASSWORD, DEFAULT_URI, DEFAULT_USER
from graph.queries.resolve_target import resolve_target
from models.retrieval_result import RetrievalResult

DEFAULT_K = 60

_CANONICAL_DISPLAY_QUERY = (
    "MATCH (c:Canonical {id: $id}) RETURN properties(c) AS props, labels(c) AS labels"
)


def reciprocal_rank_fusion(
    results_by_source: dict[str, list[RetrievalResult]],
    k: int = DEFAULT_K,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> list[RetrievalResult]:
    """results_by_source: e.g. {"graph": [...], "vector": [...], "keyword": [...]}, each list already ranked best-first by its own retriever.

    Collapsing: a raw Entity result (target_resolution == "unresolved") is credited to its owning Canonical's row via resolve_target(), not counted as its own row, if one exists. A Canonical result, or a raw Entity with no Canonical, is credited to itself unchanged. uri/user/password are only needed for that resolve_target lookup and the canonical-display fetch below (same defaults every other retriever uses).

    result_type/target_resolution/matched_text are node-intrinsic, so for a row that collapsed to a Canonical never directly returned by any source, its display fields are fetched once rather than approximated from a raw alias's name, which can be a lower-quality variant (e.g. "Jose" vs the canonical's proper "José").

    Per-source provenance is preserved in metadata["fused_from"], not collapsed: each entry there records which source found this result, at what rank, with what (non-comparable, source-native) original score, and which raw alias id actually produced that entry — so a caller can still see "graph rank 1 (canonical itself) + vector rank 3 (via alias X) + keyword rank 1 (via alias Y)" rather than one opaque combined number.
    """
    contributions: dict[str, list[dict]] = defaultdict(list)
    representative: dict[str, RetrievalResult] = {}
    resolved_cache: dict[str, str] = {}

    def fusion_key_for(result: RetrievalResult) -> str:
        if result.target_resolution == "canonical":
            return result.entity_id
        if result.entity_id not in resolved_cache:
            resolved_cache[result.entity_id] = resolve_target(
                result.entity_id, uri=uri, user=user, password=password
            )
        return resolved_cache[result.entity_id]

    for source, results in results_by_source.items():
        for rank, result in enumerate(results, start=1):
            fusion_key = fusion_key_for(result)
            contributions[fusion_key].append(
                {
                    "source": source,
                    "rank": rank,
                    "score": result.score,
                    "raw_entity_id": result.entity_id,
                }
            )
            if fusion_key == result.entity_id:
                representative.setdefault(fusion_key, result)

    fused = []
    for fusion_key, contribs in contributions.items():
        rep = representative.get(fusion_key) or _fetch_canonical_representative(
            fusion_key, uri, user, password
        )
        fused.append(
            RetrievalResult(
                entity_id=fusion_key,
                result_type=rep.result_type,
                score=sum(1.0 / (k + c["rank"]) for c in contribs),
                source="fusion",
                matched_text=rep.matched_text,
                target_resolution=rep.target_resolution,
                confidence_method="rrf_fused",
                chunk_id=rep.chunk_id,
                path=rep.path,
                metadata={**rep.metadata, "fused_from": contribs, "source_count": len(contribs)},
            )
        )
    fused.sort(key=lambda r: r.score, reverse=True)
    return fused


def _fetch_canonical_representative(
    canonical_id: str, uri: str, user: str, password: str
) -> RetrievalResult:
    """Only called when a Canonical collapsed several raw aliases but was never itself directly returned by any source — so there's no RetrievalResult to reuse for its display fields. One-off read, deferred import to keep the neo4j dependency local to the (uncommon) path that actually needs it.
    """
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            record = session.run(_CANONICAL_DISPLAY_QUERY, id=canonical_id).single()
    finally:
        driver.close()

    props = record["props"] if record else {}
    labels = record["labels"] if record else []
    return RetrievalResult(
        entity_id=canonical_id,
        result_type="Canonical",
        score=0.0,
        source="fusion",
        matched_text=props.get("canonical_name", ""),
        target_resolution="canonical",
        confidence_method="rrf_fused",
        metadata={"node_type": next((l for l in labels if l != "Canonical"), "Unknown")},
    )
