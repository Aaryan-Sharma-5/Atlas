"""Pre-insertion validation. Every Entity/Relationship must pass through here before graph/builders/. Errors are collected and reported, never raised — a bad extraction must not kill a batch."""

from dataclasses import dataclass
from typing import Iterable

from models.entity import NODE_HIERARCHY, Entity
from models.relationship import RELATIONSHIP_TYPES, Relationship
from models.resolution import DECISION_ACTIONS, ResolutionDecision


@dataclass
class ValidationError:
    item_id: str
    reason: str


@dataclass
class ValidationResult:
    entities: list[Entity]
    relationships: list[Relationship]
    errors: list[ValidationError]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_graph(
    entities: Iterable[Entity],
    relationships: Iterable[Relationship] = (),
) -> ValidationResult:
    """Validate entities and relationships together.

    Relationships are checked against the set of VALID entity ids, so an edge pointing at a rejected entity is itself rejected (orphan).
    """
    errors: list[ValidationError] = []

    valid_entities: list[Entity] = []
    seen_ids: set[str] = set()
    for entity in entities:
        reasons = _entity_errors(entity, seen_ids)
        if reasons:
            errors.extend(ValidationError(entity.id, r) for r in reasons)
        else:
            valid_entities.append(entity)
            seen_ids.add(entity.id)

    valid_relationships: list[Relationship] = []
    for rel in relationships:
        rel_id = f"{rel.source_id}-[{rel.type}]->{rel.target_id}"
        reasons = _relationship_errors(rel, seen_ids)
        if reasons:
            errors.extend(ValidationError(rel_id, r) for r in reasons)
        else:
            valid_relationships.append(rel)

    return ValidationResult(valid_entities, valid_relationships, errors)


def _entity_errors(entity: Entity, seen_ids: set[str]) -> list[str]:
    reasons: list[str] = []
    if not entity.id:
        reasons.append("missing id")
    elif entity.id in seen_ids:
        reasons.append("duplicate id")
    if not entity.name:
        reasons.append("missing name")
    if entity.type not in NODE_HIERARCHY:
        reasons.append(f"invalid type {entity.type!r}")
    reasons.extend(_common_errors(entity))
    return reasons


def _relationship_errors(rel: Relationship, valid_ids: set[str]) -> list[str]:
    reasons: list[str] = []
    if rel.type not in RELATIONSHIP_TYPES:
        reasons.append(f"invalid relationship type {rel.type!r}")
    if rel.source_id not in valid_ids:
        reasons.append(f"orphan: source {rel.source_id!r} not a valid entity")
    if rel.target_id not in valid_ids:
        reasons.append(f"orphan: target {rel.target_id!r} not a valid entity")
    reasons.extend(_common_errors(rel))
    return reasons


@dataclass
class DecisionValidationResult:
    decisions: list[ResolutionDecision]
    errors: list[ValidationError]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_decisions(
    decisions: Iterable[ResolutionDecision],
    known_entity_ids: set[str] | None = None,
) -> DecisionValidationResult:
    """ResolutionDecision objects must pass here before graph/builders/ turns them into Canonical + SAME_AS writes (Rule 3 applies to resolution writes like any other).

    Batch-level invariants: an entity may belong to at most one cluster, and canonical ids are unique. known_entity_ids (from graph/queries/) enables the orphan check; None skips it.
    """
    errors: list[ValidationError] = []
    valid: list[ResolutionDecision] = []
    claimed_entities: dict[str, str] = {}  # entity id -> canonical id that claimed it
    seen_canonical_ids: set[str] = set()

    for decision in decisions:
        label = decision.canonical_id or f"NONE:{'|'.join(decision.source_ids)}"
        reasons = _decision_errors(decision, known_entity_ids)

        if decision.action in ("MERGE", "TENTATIVE"):
            if decision.canonical_id in seen_canonical_ids:
                reasons.append(f"duplicate canonical id {decision.canonical_id!r}")
            for sid in decision.source_ids:
                if sid in claimed_entities:
                    reasons.append(
                        f"entity {sid!r} already claimed by "
                        f"{claimed_entities[sid]!r} (overlapping clusters)"
                    )

        if reasons:
            errors.extend(ValidationError(label, r) for r in reasons)
        else:
            valid.append(decision)
            if decision.action in ("MERGE", "TENTATIVE"):
                seen_canonical_ids.add(decision.canonical_id)
                for sid in decision.source_ids:
                    claimed_entities[sid] = decision.canonical_id

    return DecisionValidationResult(valid, errors)


def _decision_errors(
    decision: ResolutionDecision, known_entity_ids: set[str] | None
) -> list[str]:
    reasons: list[str] = []
    if decision.action not in DECISION_ACTIONS:
        reasons.append(f"invalid action {decision.action!r}")
    if not isinstance(decision.confidence, (int, float)) or not (
        0.0 <= decision.confidence <= 1.0
    ):
        reasons.append(f"confidence {decision.confidence!r} outside [0.0, 1.0]")
    if decision.entity_type not in NODE_HIERARCHY:
        reasons.append(f"invalid entity type {decision.entity_type!r}")
    if len(set(decision.source_ids)) != len(decision.source_ids):
        reasons.append("duplicate source ids within decision")
    if known_entity_ids is not None:
        for sid in decision.source_ids:
            if sid not in known_entity_ids:
                reasons.append(f"orphan: source entity {sid!r} not in graph")

    if decision.action in ("MERGE", "TENTATIVE"):
        if not decision.canonical_id:
            reasons.append("missing canonical_id")
        elif "__" in decision.canonical_id:
            reasons.append(
                f"canonical id {decision.canonical_id!r} carries a source "
                "namespace ('__'); canonical ids must drop it (physical.md)"
            )
        if not decision.canonical_name:
            reasons.append("missing canonical_name")
        if len(decision.source_ids) < 2:
            reasons.append(
                f"{decision.action} needs >= 2 source entities, "
                f"got {len(decision.source_ids)}"
            )
    return reasons


def validate_authored_by(
    relationships: Iterable[Relationship],
    known_entity_ids: set[str],
    known_canonical_ids: set[str],
    existing_edges: set[tuple[str, str, str]] = frozenset(),
) -> ValidationResult:
    """AUTHORED_BY (Paper -> Person|Canonical) relationships, post target-resolution, before graph/builders/ (7A.1). Reuses ValidationResult/ValidationError (Rule 3 applies to relationships the same as entities and resolution decisions); `entities` is always empty here since this validates edges only.

    known_entity_ids/known_canonical_ids cover both the live graph and any new nodes validated in the same batch (e.g. Paper nodes not yet written). existing_edges seeds the duplicate-edge check for genuinely distinct candidate sets run back-to-back; deliberately do NOT pass the live graph's own AUTHORED_BY edges here for a re-run of the SAME already-written batch — build_authored_by_cypher's MERGE is what makes that idempotent, and this check would otherwise reject every one of it.
    """
    errors: list[ValidationError] = []
    valid: list[Relationship] = []
    seen_edges: set[tuple[str, str, str]] = set(existing_edges)

    for rel in relationships:
        rel_id = f"{rel.source_id}-[{rel.type}]->{rel.target_id}"
        reasons: list[str] = []
        if rel.type != "AUTHORED_BY":
            reasons.append(f"not an AUTHORED_BY relationship: {rel.type!r}")
        if rel.source_id not in known_entity_ids:
            reasons.append(f"orphan: source {rel.source_id!r} not a known Paper entity")
        if rel.target_id not in known_entity_ids and rel.target_id not in known_canonical_ids:
            reasons.append(f"orphan: target {rel.target_id!r} not a known Entity or Canonical")
        if rel.source_id == rel.target_id:
            reasons.append("self-loop: source and target are the same id")
        edge_key = (rel.source_id, rel.type, rel.target_id)
        if edge_key in seen_edges:
            reasons.append("duplicate edge (already exists or repeated in this batch)")
        reasons.extend(_common_errors(rel))

        if reasons:
            errors.extend(ValidationError(rel_id, r) for r in reasons)
        else:
            valid.append(rel)
            seen_edges.add(edge_key)

    return ValidationResult(entities=[], relationships=valid, errors=errors)


def _common_errors(item: Entity | Relationship) -> list[str]:
    """Mandatory confidence/provenance checks shared by nodes and edges."""
    reasons: list[str] = []
    if not isinstance(item.confidence, (int, float)) or not (
        0.0 <= item.confidence <= 1.0
    ):
        reasons.append(f"confidence {item.confidence!r} outside [0.0, 1.0]")
    if not item.extraction_source:
        reasons.append("missing extraction_source")
    if not item.extraction_method:
        reasons.append("missing extraction_method")
    return reasons
