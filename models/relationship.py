"""Internal Relationship dataclass. The only Relationship definition in Atlas."""

from dataclasses import dataclass, field
from typing import Any

# Canonical relationship types from graph/schema/conceptual.md.
# graph/validators/ rejects Relationships whose type is not listed here.
RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        # Authorship and attribution
        "AUTHORED_BY",
        "PUBLISHED_BY",
        "AFFILIATED_WITH",
        # Citation and reference
        "CITES",
        "MENTIONS",
        "DESCRIBES",
        # Technology and dependency
        "BUILT_BY",
        "CREATED_IN",
        "EXTENDS",
        "DEPENDS_ON",
        # Code structure
        "DEFINED_IN",
        "CALLS",
        "IMPLEMENTS",
        "INHERITS_FROM",
        "USES_TECHNOLOGY",
        "USES_API",
        "REFERENCES",
        # Semantic
        "CONTAINED_IN",
        "SIMILAR_TO",
        "ALTERNATIVE_TO",
        # Dataset and experimentation
        "EVALUATED_ON",
        "USES_DATASET",
        "PRODUCED_BY",
        # Metadata and origin
        "EXTRACTED_FROM",
    }
)


@dataclass
class Relationship:
    """A directed edge between two entities, identified by their ids.

    Type membership in RELATIONSHIP_TYPES is checked by graph/validators/, not here, so invalid extractions can be collected and reported rather than crashing mid-pipeline.
    """

    source_id: str
    target_id: str
    type: str
    confidence: float
    extraction_source: str
    extraction_method: str
    properties: dict[str, Any] = field(default_factory=dict)
