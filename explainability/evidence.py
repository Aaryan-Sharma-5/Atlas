"""Evidence assembly (Step 13B). A RetrievalResult that serves as an answer can back itself with a Chunk in one of two structurally different ways, and forcing both into one flat shape would hide which one actually happened:

- "entity_with_chunk" (graph-routed): the answer is an Entity/Canonical, and a separate Chunk RetrievalResult exists elsewhere in the same result list, joined by chunk_id (retrieval/graph_retriever.py sets chunk_id from a relationship's evidence_chunk_id, then appends the matching Chunk as its own list entry).
- "chunk_is_answer" (vector_passage-routed): the answer *is* the Chunk — retrieval/vector_retriever.py's search_by_passage() and graph_retriever.py's own Chunk entries return the chunk directly as the top-level result, not as separate evidence for something else.
- "entity_only": the answer is an Entity/Canonical with no linked chunk at all — vector_name and keyword hits never set chunk_id (Step 10C/10D never populate it), and graph SAME_AS/AUTHORED_BY neighbors only carry one when the Step 9.5 evidence_chunk_id enrichment happened to reach that specific edge.
"""

from dataclasses import dataclass

from graph.queries.document_reader import fetch_source_titles
from models.retrieval_result import RetrievalResult

EVIDENCE_SHAPES = frozenset({"entity_with_chunk", "chunk_is_answer", "entity_only"})


@dataclass
class Evidence:
    shape: str
    chunk_id: str | None = None
    chunk_content: str | None = None
    chunk_index: int | None = None
    source_document_id: str | None = None
    source_document_title: str | None = None

    def __post_init__(self) -> None:
        if self.shape not in EVIDENCE_SHAPES:
            raise ValueError(f"Unknown evidence shape {self.shape!r}. Valid: {sorted(EVIDENCE_SHAPES)}")


def build_evidence(
    answer: RetrievalResult,
    all_results: list[RetrievalResult],
    source_titles: dict[str, str],
) -> Evidence:
    """all_results is the full RoutingResult.results list the answer came from — needed to find the separately-listed Chunk entry in the entity_with_chunk case. source_titles is a pre-fetched id->title map (see assemble_explained_answer; fetched once per call, not once per evidence item, to avoid a Neo4j round trip per result)."""
    if answer.result_type == "Chunk":
        source_id = answer.metadata.get("source_id")
        return Evidence(
            shape="chunk_is_answer",
            chunk_id=answer.chunk_id or answer.entity_id,
            chunk_content=answer.matched_text,
            chunk_index=answer.metadata.get("chunk_index"),
            source_document_id=source_id,
            source_document_title=source_titles.get(source_id) if source_id else None,
        )

    if answer.chunk_id:
        chunk = next(
            (r for r in all_results if r.result_type == "Chunk" and r.entity_id == answer.chunk_id),
            None,
        )
        if chunk is not None:
            source_id = chunk.metadata.get("source_id")
            return Evidence(
                shape="entity_with_chunk",
                chunk_id=chunk.entity_id,
                chunk_content=chunk.matched_text,
                chunk_index=chunk.metadata.get("chunk_index"),
                source_document_id=source_id,
                source_document_title=source_titles.get(source_id) if source_id else None,
            )
        # chunk_id points somewhere outside this result list (e.g. top_k truncated the chunk entry out) — still the entity_with_chunk shape, but content isn't available from what we already fetched; not silently downgraded to entity_only, since a chunk genuinely was linked, just not resolvable here.
        return Evidence(shape="entity_with_chunk", chunk_id=answer.chunk_id)

    return Evidence(shape="entity_only")
