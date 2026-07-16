"""Relationship type -> extractor + validator. Thin orchestration map, not a graph write (Rule 1 boundary stays in graph/builders/).

Only AUTHORED_BY is populated (7A.1). MENTIONS/USES entries land here when those stages are built, not stubbed ahead of time.
"""

from graph.validators.validator import validate_authored_by
from relationships.authored_by import extract_authors

RELATIONSHIP_REGISTRY: dict[str, dict[str, object]] = {
    "AUTHORED_BY": {
        "source_type": "Paper",
        "target_type": "Person",
        "extractor": extract_authors,
        "validator": validate_authored_by,
    },
}
