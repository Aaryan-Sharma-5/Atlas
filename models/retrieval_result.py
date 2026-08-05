"""Internal RetrievalResult dataclass. The common shape every retriever (graph now; vector/keyword later, Step 10) must return."""

from dataclasses import dataclass, field
from typing import Any, Literal

RESULT_TYPES: frozenset[str] = frozenset({"Entity", "Canonical", "Chunk"})
# "fusion" added Step 10E: retrieval/fusion.py::reciprocal_rank_fusion produces results that no single retriever found on its own (they exist only after combining ranks across sources), so labeling one "graph"/"vector"/"keyword" would misattribute it. Per-source contribution (which retrievers found it, at what rank/score) is kept in metadata["fused_from"] rather than collapsed away.
SOURCES: frozenset[str] = frozenset({"graph", "vector", "keyword", "fusion"})
TargetResolution = Literal["canonical", "unresolved"]

# Added Step 13D: before this, "how was score derived" was only guessable from `source` (graph confidence vs. cosine similarity vs. Lucene relevance vs. RRF are four different scales — this session's own finding, retrieval/fusion.py's docstring), and even that guess was unreliable since metadata coverage was inconsistent across retrievers (graph attached extraction_source/extraction_method; vector attached extraction_source only for name-mode, nothing for chunk results; keyword attached neither). Every RetrievalResult now states its method explicitly, not left for a caller to infer from `source` plus whatever metadata happened to be attached.
CONFIDENCE_METHODS: frozenset[str] = frozenset(
    {
        "graph_exact_match",  # self-lookup by id — always 1.0, not a ranking signal
        "graph_edge_confidence",  # neighbor via a relationship — score is that edge's confidence
        "graph_evidence_chunk",  # chunk joined via evidence_chunk_id — exact link, always 1.0
        "cosine_similarity_name",  # vector_retriever.search_by_name() — short-name embedding match
        "cosine_similarity_passage",  # vector_retriever.search_by_passage() — passage embedding match
        "lucene_relevance",  # keyword_retriever fulltext search — Lucene's own relevance score
        "rrf_fused",  # fusion.reciprocal_rank_fusion() — rank-based combination, not comparable to any of the above
    }
)


@dataclass
class RetrievalResult:
    """One retrieved item.

    target_resolution is mandatory, not optional: it's what closes the docs/architecture.md §12.9/§13 MENTIONS coverage gap (89% of MENTIONS edges point at raw unresolved Entities) at the point results actually get shown as evidence, rather than only being noted in docs. Every result touching an Entity/Canonical states which it is.

    confidence_method is likewise mandatory, not optional, for the same reason applied to score instead of identity: a bare `score` float is meaningless (or actively misleading) without knowing which of graph/vector/keyword/fusion's incompatible scales produced it.
    """

    entity_id: str
    result_type: str
    score: float
    source: str
    matched_text: str
    target_resolution: TargetResolution
    confidence_method: str
    chunk_id: str | None = None
    path: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.result_type not in RESULT_TYPES:
            raise ValueError(
                f"Unknown result_type {self.result_type!r}. Valid types: {sorted(RESULT_TYPES)}"
            )
        if self.source not in SOURCES:
            raise ValueError(f"Unknown source {self.source!r}. Valid sources: {sorted(SOURCES)}")
        if self.target_resolution not in ("canonical", "unresolved"):
            raise ValueError(
                f"target_resolution must be 'canonical' or 'unresolved', got "
                f"{self.target_resolution!r}"
            )
        if self.confidence_method not in CONFIDENCE_METHODS:
            raise ValueError(
                f"Unknown confidence_method {self.confidence_method!r}. Valid methods: "
                f"{sorted(CONFIDENCE_METHODS)}"
            )
