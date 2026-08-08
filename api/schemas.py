"""API-facing Pydantic models (Step 14A). QueryResponse is derived from ExplainedAnswer (explainability/explained_answer.py), not a parallel model maintained by hand — every field here traces back to one ExplainedAnswer field, translated where the internal shape isn't already frontend-appropriate as-is. See QueryResponse.from_explained_answer for the mapping.
"""

from typing import Any

from pydantic import BaseModel

from explainability.explained_answer import ExplainedAnswer
from models.retrieval_result import RetrievalResult

# confidence_method (models/retrieval_result.py::CONFIDENCE_METHODS) is an internal scoring-provenance tag, not phrased for display — a frontend showing "cosine_similarity_name" verbatim would be showing implementation detail, not an explanation. The raw value is kept on the response too (frontend logic may still want to branch on it), this is additive.
_CONFIDENCE_METHOD_LABELS: dict[str, str] = {
    "graph_exact_match": "Exact ID lookup",
    "graph_edge_confidence": "Graph relationship confidence",
    "graph_evidence_chunk": "Linked source passage",
    "cosine_similarity_name": "Name similarity (embedding)",
    "cosine_similarity_passage": "Passage similarity (embedding)",
    "lucene_relevance": "Keyword search relevance",
    "rrf_fused": "Combined ranking across retrievers",
}


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5


class EvidenceOut(BaseModel):
    """Mirrors explainability/evidence.py::Evidence's flat/optional-field shape rather than splitting into three subtypes — that dataclass already made evidence's three possible shapes ("entity_with_chunk", "chunk_is_answer", "entity_only") consistently shaped via `shape` as a discriminant plus nullable fields, so no further translation is needed here beyond a 1:1 field mapping."""

    shape: str
    chunk_id: str | None = None
    chunk_content: str | None = None
    chunk_index: int | None = None
    source_document_id: str | None = None
    source_document_title: str | None = None


class CaveatOut(BaseModel):
    section: str
    label: str


class QueryResponse(BaseModel):
    question: str
    answer_entity_id: str
    answer_display_text: str
    answer_type: str
    target_resolution: str

    evidence: EvidenceOut

    routing_decision: str
    relationship_type_filtered: list[str] | None
    retrievers_invoked: list[str]
    single_strategy_vs_fused: bool
    per_source_contributions: list[dict] | None
    graph_traversal_path: list[dict]

    confidence_score: float
    confidence_method: str
    confidence_label: str

    known_limitations: list[CaveatOut]

    @classmethod
    def from_explained_answer(cls, answer: ExplainedAnswer) -> "QueryResponse":
        return cls(
            question=answer.question,
            answer_entity_id=answer.answer_entity_id,
            answer_display_text=answer.answer_display_text,
            answer_type=answer.answer_type,
            target_resolution=answer.target_resolution,
            evidence=EvidenceOut(
                shape=answer.evidence.shape,
                chunk_id=answer.evidence.chunk_id,
                chunk_content=answer.evidence.chunk_content,
                chunk_index=answer.evidence.chunk_index,
                source_document_id=answer.evidence.source_document_id,
                source_document_title=answer.evidence.source_document_title,
            ),
            routing_decision=answer.routing_decision,
            relationship_type_filtered=answer.relationship_type_filtered,
            retrievers_invoked=answer.retrievers_invoked,
            single_strategy_vs_fused=answer.single_strategy_vs_fused,
            per_source_contributions=answer.per_source_contributions,
            graph_traversal_path=answer.graph_traversal_path,
            confidence_score=answer.confidence_score,
            confidence_method=answer.confidence_method,
            confidence_label=_CONFIDENCE_METHOD_LABELS.get(
                answer.confidence_method, answer.confidence_method
            ),
            known_limitations=[
                CaveatOut(section=c.section, label=c.label) for c in answer.known_limitations
            ],
        )


class AliasOut(BaseModel):
    """One SAME_AS member behind a Canonical — graph/queries/entity_reader.py's fetch_entity_detail() aliases entry, mapped 1:1."""

    id: str
    name: str | None
    confidence: float | None
    decision_action: str | None


class EntityDetailResponse(BaseModel):
    """Maps graph/queries/entity_reader.py::fetch_entity_detail()'s return dict 1:1 — same discipline as QueryResponse: no fields invented beyond what the underlying Entity/Canonical node carries. `name` coalesces Entity.name/Canonical.canonical_name (see that function's docstring); `properties` is everything else on the node verbatim."""

    id: str
    node_type: str | None
    is_canonical: bool
    name: str | None
    confidence: float
    extraction_source: str
    extraction_method: str
    properties: dict[str, Any]
    aliases: list[AliasOut]

    @classmethod
    def from_detail(cls, detail: dict[str, Any]) -> "EntityDetailResponse":
        return cls(
            id=detail["id"],
            node_type=detail["node_type"],
            is_canonical=detail["is_canonical"],
            name=detail["name"],
            confidence=detail["confidence"],
            extraction_source=detail["extraction_source"],
            extraction_method=detail["extraction_method"],
            properties=detail["properties"],
            aliases=[AliasOut(**a) for a in detail["aliases"]],
        )


class GraphNodeOut(BaseModel):
    id: str
    label: str
    type: str | None
    target_resolution: str


class GraphEdgeOut(BaseModel):
    source: str
    target: str
    relationship_type: str
    direction: str


class EntityGraphResponse(BaseModel):
    """Cytoscape.js-shaped neighborhood for one entity — retrieval/graph_retriever.py's get_entity_context() results reshaped into distinct nodes/edges lists rather than dumped as RetrievalResult objects, since Cytoscape needs that specific split, not a flat scored-result list (that's what /query's evidence/graph_traversal_path are for). Chunk results (supporting-evidence hits get_entity_context() also returns via evidence_chunk_id) are excluded here — they aren't graph nodes with typed relationships, they're /query's evidence concern, not this endpoint's."""

    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    truncated: bool

    @classmethod
    def from_results(
        cls, seed_id: str, results: list[RetrievalResult], limit: int
    ) -> "EntityGraphResponse":
        entity_results = [r for r in results if r.result_type != "Chunk"]
        truncated = len(entity_results) > limit
        entity_results = entity_results[:limit]

        nodes = [
            GraphNodeOut(
                id=r.entity_id,
                label=r.matched_text,
                type=r.metadata.get("node_type"),
                target_resolution=r.target_resolution,
            )
            for r in entity_results
        ]

        edges = [
            GraphEdgeOut(
                source=seed_id if r.metadata.get("direction") == "outgoing" else r.entity_id,
                target=r.entity_id if r.metadata.get("direction") == "outgoing" else seed_id,
                relationship_type=r.metadata["relationship_type"],
                direction=r.metadata["direction"],
            )
            for r in entity_results
            if not r.metadata.get("is_seed")
        ]

        return cls(nodes=nodes, edges=edges, truncated=truncated)
