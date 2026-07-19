"""MENTIONS (Paper/Markdown/Repository -> KnowledgeEntity) extraction (Phase 7A.2a).

Unlike AUTHORED_BY, target resolution needs no name reconstruction: the target IS the already-known Entity being converted (every Entity already carries extraction_source, i.e. which source node it belongs to), so resolve_mentions() resolves entity.id directly through resolve_target() rather than rebuilding a guessed id from a raw string. extract_mentions() still produces RelationshipCandidate objects (target_name = entity.name) to keep the same extractor/validator registry shape as every other relationship type, but the "no matching target" drop class AUTHORED_BY has structurally does not exist here — nothing to confirm by reconstruction, since we already hold the real id.
"""

import re

from graph.queries.resolve_target import resolve_target
from models.entity import Entity
from models.relationship import Relationship
from models.relationship_candidate import RelationshipCandidate

# extraction_source prefix -> the source node type's id prefix (must match extraction/entity_converter.py's convert_paper_entity / convert_markdown_entity / convert_repository_entity).
_SOURCE_TYPE_PREFIX: dict[str, str] = {"pdf": "paper", "md": "markdown", "github": "repo"}

_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

_EXTRACTION_METHOD = "mentions:extraction_source_link@v1"


def source_slug(identifier: str) -> str:
    """Must exactly match extraction/entity_converter.py's source_slug convention."""
    normalized = _WHITESPACE.sub(" ", identifier).strip().lower()
    return _NON_ALNUM.sub("_", normalized).strip("_")


def source_node_id(extraction_source: str) -> str:
    """"pdf:X" / "md:X" / "github:X" -> the Paper/Markdown/Repository node id that owns it."""
    kind, _, rest = extraction_source.partition(":")
    return f"{_SOURCE_TYPE_PREFIX[kind]}_{source_slug(rest)}"


def extract_mentions(entities: list[Entity]) -> list[RelationshipCandidate]:
    """One candidate per entity, carrying the mention_count entity_converter.py now exposes as evidence."""
    return [
        RelationshipCandidate(
            source_entity_id=source_node_id(entity.extraction_source),
            target_name=entity.name,
            relationship_type="MENTIONS",
            evidence=f"entity_extraction_source; mention_count={entity.properties.get('mention_count', 1)}",
            confidence=entity.confidence,
            extraction_source=entity.extraction_source,
            extraction_method=_EXTRACTION_METHOD,
        )
        for entity in entities
    ]


def resolve_mentions(entities: list[Entity]) -> list[Relationship]:
    """entity.id -> resolve_target() directly. No drop class: unlike AUTHORED_BY's reconstructed candidate ids, the target here is the entity already being iterated, so there is nothing to fail to match.
    """
    relationships: list[Relationship] = []
    for entity in entities:
        target_id = resolve_target(entity.id)
        target_kind = "canonical" if target_id != entity.id else "entity (unresolved)"
        relationships.append(
            Relationship(
                source_id=source_node_id(entity.extraction_source),
                target_id=target_id,
                type="MENTIONS",
                confidence=entity.confidence,
                extraction_source=entity.extraction_source,
                extraction_method=_EXTRACTION_METHOD,
                properties={
                    "frequency": entity.properties.get("mention_count", 1),
                    "evidence": f"entity_extraction_source; target={target_kind}",
                },
            )
        )
    return relationships
