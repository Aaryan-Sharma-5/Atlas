"""Caveat rules (Step 13E) — a pointer system into docs/architecture.md's §12/§13 findings, deliberately NOT a restatement of their content. Each rule names a section and a short label; the actual explanation of *why* stays in architecture.md, in one place, so it doesn't drift out of sync with this file the next time that section is revised. If a rule's label starts sounding like a paragraph, that's a sign the explanation belongs in architecture.md instead, with this file trimmed back to a pointer.
"""

from collections.abc import Callable
from dataclasses import dataclass

from models.retrieval_result import RetrievalResult
from planner.planner import RoutingResult


@dataclass(frozen=True)
class Caveat:
    section: str
    label: str


CaveatRule = Callable[[RetrievalResult, RoutingResult], bool]

# (predicate, section, short pointer label) — checked independently, not first-match; a single answer can carry more than one applicable caveat.
_RULES: list[tuple[CaveatRule, str, str]] = [
    (
        lambda r, routing: r.target_resolution == "unresolved",
        "architecture.md §12.5",
        "unresolved entity — may have unmerged duplicate aliases",
    ),
    (
        lambda r, routing: r.target_resolution == "unresolved"
        and r.metadata.get("relationship_type") == "MENTIONS",
        "architecture.md §12.9",
        "unresolved MENTIONS target — outside Stage 5 quality-flag coverage",
    ),
    (
        lambda r, routing: "graph" in routing.retrievers_invoked,
        "architecture.md §12.10",
        "graph retrieval is 1-hop only",
    ),
    (
        lambda r, routing: r.metadata.get("decision_action") == "TENTATIVE",
        "architecture.md §12.4",
        "identity merge was TENTATIVE, not MERGE — weaker resolution confidence",
    ),
    (
        lambda r, routing: r.metadata.get("node_type") == "Person"
        and str(r.metadata.get("extraction_source") or "").startswith("pdf:"),
        "architecture.md §12.7",
        "PDF-sourced person name — possible encoding corruption",
    ),
    (
        lambda r, routing: r.metadata.get("node_type") in {"Technology", "Language"},
        "architecture.md §12.3",
        "Technology/Language entities are under-extracted relative to Person/Organization in this corpus",
    ),
]


def applicable_caveats(result: RetrievalResult, routing: RoutingResult) -> list[Caveat]:
    return [Caveat(section, label) for predicate, section, label in _RULES if predicate(result, routing)]
