"""Relationship type -> extractor + validator. Thin orchestration map, not a graph write (Rule 1 boundary stays in graph/builders/).

AUTHORED_BY (7A.1) and MENTIONS (7A.2a) are populated. USES (7A.3) lands here when that stage is built, not stubbed ahead of time. MENTIONS Repository->API (7A.2b) is blocked on new API-entity extraction and deliberately not represented as a separate registry entry yet.
"""

from graph.validators.validator import validate_authored_by, validate_mentions
from relationships.authored_by import extract_authors
from relationships.mentions import extract_mentions

RELATIONSHIP_REGISTRY: dict[str, dict[str, object]] = {
    "AUTHORED_BY": {
        "source_type": "Paper",
        "target_type": "Person",
        "extractor": extract_authors,
        "validator": validate_authored_by,
    },
    "MENTIONS": {
        "source_type": "Paper|Markdown|Repository",
        "target_type": "KnowledgeEntity",
        "extractor": extract_mentions,
        "validator": validate_mentions,
    },
}
