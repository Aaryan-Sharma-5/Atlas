"""Convert raw spaCy NER results into internal models.Entity objects.

Exact-duplicate mentions (same type + normalized surface form) collapse into one Entity here; fuzzy merging ("OpenAI" vs "OpenAI Inc.") is resolution/'s job and deliberately NOT done at this stage.
"""

import re
from collections import Counter, defaultdict

from extraction.entity_extractor import RawEntity
from models.entity import Entity

# spaCy label -> Atlas node type. Labels absent here (GPE, NORP, FAC, EVENT, LAW, WORK_OF_ART) have no home in the schema hierarchy yet and are skipped; adding them requires a schema-doc update first.
SPACY_LABEL_TO_TYPE: dict[str, str] = {
    "PERSON": "Person",
    "ORG": "Organization",
    "PRODUCT": "Technology",
    "LANGUAGE": "Language",
}

_ID_PREFIX: dict[str, str] = {
    "Person": "person",
    "Organization": "org",
    "Technology": "tech",
    "Language": "lang",
}

# spaCy NER exposes no per-entity probability, so confidence is a documented heuristic: base score for the small model, boosted per repeat mention (repeats are strong evidence the span is a real entity).
_BASE_CONFIDENCE = 0.6
_REPEAT_BONUS = 0.05
_MAX_CONFIDENCE = 0.95


def convert_raw_entities(
    raw_entities: list[RawEntity],
    extraction_source: str,
    extraction_method: str = "spacy:en_core_web_sm",
) -> tuple[list[Entity], dict[str, int]]:
    """Convert raw NER hits into Entity objects.

    Args:
        raw_entities: Output of extraction.entity_extractor.
        extraction_source: Provenance identifier, e.g. "pdf:2003.02320v6.pdf".
        extraction_method: Provenance identifier for the extractor.

    Returns:
        (entities, skipped) where skipped maps unmappable spaCy labels to
        how many mentions were dropped.
    """
    # Ids are namespaced by source, so the same name in two documents yields two distinct nodes. Collapsing them into one canonical entity is resolution/'s job — done explicitly, never implicitly at id-collision time.
    source_slug = _slugify(_normalize(extraction_source.split(":", 1)[-1]))

    groups: dict[tuple[str, str], list[RawEntity]] = defaultdict(list)
    skipped: Counter[str] = Counter()

    for raw in raw_entities:
        node_type = SPACY_LABEL_TO_TYPE.get(raw.label)
        if node_type is None:
            skipped[raw.label] += 1
            continue
        # Group by slug (not normalized text) so punctuation variants like "Prud'hommeaux"/"Prud hommeaux" can't collide into duplicate ids.
        groups[(node_type, _slugify(_normalize(raw.text)))].append(raw)

    entities: list[Entity] = []
    for (node_type, slug), mentions in groups.items():
        # Most frequent surface form becomes the canonical name.
        surface_forms = Counter(_collapse_ws(m.text) for m in mentions)
        name = surface_forms.most_common(1)[0][0]
        aliases = sorted(set(surface_forms) - {name})

        properties: dict[str, object] = {}
        if aliases:
            properties["aliases"] = aliases
        if node_type == "Person":
            properties["full_name"] = name  

        confidence = min(
            _MAX_CONFIDENCE,
            _BASE_CONFIDENCE + _REPEAT_BONUS * (len(mentions) - 1),
        )

        entities.append(
            Entity(
                id=f"{_ID_PREFIX[node_type]}_{slug}__{source_slug}",
                type=node_type,
                name=name,
                confidence=confidence,
                extraction_source=extraction_source,
                extraction_method=extraction_method,
                properties=properties,
            )
        )

    return entities, dict(skipped)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize(text: str) -> str:
    return _collapse_ws(text).lower()


def _slugify(normalized: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return slug or "unnamed"
