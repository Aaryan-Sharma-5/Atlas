"""Internal RelationshipCandidate dataclass — the relationship-extraction analogue of Entity (ingestion) and ResolutionDecision (resolution): same shape, new stage.

Extractors (relationships/) produce these with a raw, pre-resolution target_name. graph/queries/resolve_target.py resolves that name to a live graph id; the result becomes a models.Relationship (Rule 1: extraction output is always an Entity or Relationship object), which graph/validators/ and graph/builders/ then handle the same way they handle any other relationship.
"""

from dataclasses import dataclass

from models.relationship import RELATIONSHIP_TYPES


@dataclass
class RelationshipCandidate:
    """One proposed relationship before its target has been resolved to a live graph id."""

    source_entity_id: str
    target_name: str
    relationship_type: str
    evidence: str
    confidence: float
    extraction_source: str
    extraction_method: str

    def __post_init__(self) -> None:
        if self.relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError(
                f"Unknown relationship type {self.relationship_type!r}. Valid "
                f"types: {sorted(RELATIONSHIP_TYPES)}. New types require a "
                f"schema-doc update first (CLAUDE.md rule 2)."
            )
