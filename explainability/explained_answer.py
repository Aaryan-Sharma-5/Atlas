"""ExplainedAnswer assembly (Step 13F) — combines a RoutingResult's chosen answer
with its evidence (13B), source-document title (13C), confidence provenance (13D),
and applicable caveats (13E) into one self-contained record.

Schema fields map directly onto the five questions Step 13's scoping report set out
to answer: what's the answer (answer_*), what's it based on (evidence), how did you
find it (routing_decision/relationship_type_filtered/retrievers_invoked/
single_strategy_vs_fused/per_source_contributions/graph_traversal_path), how sure
are you (confidence_score/confidence_method — a label, not a bare number, per
Step 13D), and what should I be wary of (known_limitations).
"""

from dataclasses import dataclass, field

from explainability.caveats import Caveat, applicable_caveats
from explainability.evidence import Evidence, build_evidence
from graph.queries.document_reader import fetch_source_titles
from planner.planner import RoutingResult


@dataclass
class ExplainedAnswer:
    question: str
    answer_entity_id: str
    answer_display_text: str
    answer_type: str
    target_resolution: str

    evidence: Evidence

    routing_decision: str
    relationship_type_filtered: list[str] | None
    retrievers_invoked: list[str]
    single_strategy_vs_fused: bool
    per_source_contributions: list[dict] | None
    graph_traversal_path: list[dict] = field(default_factory=list)

    confidence_score: float = 0.0
    confidence_method: str = ""

    known_limitations: list[Caveat] = field(default_factory=list)


def assemble_explained_answer(
    question: str, routing: RoutingResult, rank: int = 0
) -> ExplainedAnswer | None:
    """rank=0 explains the top result; pass a higher rank to explain a lower-ranked
    candidate from the same RoutingResult instead of re-querying. Returns None if
    routing.results is empty (nothing to explain — e.g. a documented retrieval gap
    like eval questions 10/11/14) rather than raising, since an empty result set is
    an expected, valid outcome, not an error condition."""
    if not routing.results or rank >= len(routing.results):
        return None

    answer = routing.results[rank]

    source_ids = {
        r.metadata.get("source_id") for r in routing.results if r.metadata.get("source_id")
    }
    source_titles = fetch_source_titles(list(source_ids)) if source_ids else {}

    evidence = build_evidence(answer, routing.results, source_titles)

    return ExplainedAnswer(
        question=question,
        answer_entity_id=answer.entity_id,
        answer_display_text=answer.matched_text,
        answer_type=answer.result_type,
        target_resolution=answer.target_resolution,
        evidence=evidence,
        routing_decision=routing.category,
        relationship_type_filtered=routing.relationship_types_filtered,
        retrievers_invoked=routing.retrievers_invoked,
        single_strategy_vs_fused=(answer.source == "fusion"),
        per_source_contributions=answer.metadata.get("fused_from"),
        graph_traversal_path=answer.path,
        confidence_score=answer.score,
        confidence_method=answer.confidence_method,
        known_limitations=applicable_caveats(answer, routing),
    )
