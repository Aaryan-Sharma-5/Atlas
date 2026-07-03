"""Pre-insertion validation. Every Entity/Relationship must pass through here before graph/builders/. Errors are collected and reported, never raised — a bad extraction must not kill a batch."""

from dataclasses import dataclass
from typing import Iterable

from models.entity import NODE_HIERARCHY, Entity
from models.relationship import RELATIONSHIP_TYPES, Relationship


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
