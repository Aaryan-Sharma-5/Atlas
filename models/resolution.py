"""Internal ResolutionDecision dataclass. The only ResolutionDecision definition in Atlas — resolution/decisioning/ produces them, graph/validators/ checks them, graph/builders/ turns them into Canonical + SAME_AS Cypher (Rule 8: nothing else writes, nothing is ever physically merged)."""

from dataclasses import dataclass, field

DECISION_ACTIONS: frozenset[str] = frozenset({"MERGE", "TENTATIVE", "NONE"})


@dataclass
class ResolutionDecision:
    """One decision per duplicate cluster (or per rejected pair for NONE).

    confidence is the weakest supporting candidate-pair score in the cluster — the decision is only as strong as its weakest link. canonical_id/canonical_name are empty for NONE (no Canonical node is created).
    """

    action: str
    confidence: float
    canonical_id: str
    canonical_name: str
    entity_type: str
    source_ids: list[str] = field(default_factory=list)
    reasoning: str = ""

    def __post_init__(self) -> None:
        if self.action not in DECISION_ACTIONS:
            raise ValueError(
                f"Unknown decision action {self.action!r}. "
                f"Valid actions: {sorted(DECISION_ACTIONS)}."
            )

    @property
    def cluster_size(self) -> int:
        return len(self.source_ids)

    @property
    def priority_review(self) -> bool:
        """Stage 5 review ordering: large TENTATIVE clusters (initial-swap ambiguity, stutter chains) surface before the long tail of pairs."""
        return self.action == "TENTATIVE" and self.cluster_size >= 5
