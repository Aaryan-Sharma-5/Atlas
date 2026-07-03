"""Internal Entity dataclass. The only Entity definition in Atlas, everything else imports from here."""

from dataclasses import dataclass, field
from typing import Any

# Node type -> base type, mirroring graph/schema/conceptual.md.
# Adding a type here requires updating conceptual.md and physical.md first.
NODE_HIERARCHY: dict[str, str] = {
    # Resource
    "Document": "Resource",
    "Paper": "Resource",
    "Markdown": "Resource",
    "Repository": "Resource",
    "Website": "Resource",
    # CodeEntity
    "Module": "CodeEntity",
    "Class": "CodeEntity",
    "Function": "CodeEntity",
    "Interface": "CodeEntity",
    "Variable": "CodeEntity",
    "Type": "CodeEntity",
    # KnowledgeEntity
    "Technology": "KnowledgeEntity",
    "Language": "KnowledgeEntity",
    "Framework": "KnowledgeEntity",
    "API": "KnowledgeEntity",
    "Dataset": "KnowledgeEntity",
    "Organization": "KnowledgeEntity",
    "Person": "KnowledgeEntity",
}


@dataclass
class Entity:
    """A node destined for the knowledge graph.

    Confidence and provenance fields are mandatory; range/content validation happens in graph/validators/, but the type constraint is structural and enforced here.
    """

    id: str
    type: str
    name: str
    confidence: float
    extraction_source: str
    extraction_method: str
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in NODE_HIERARCHY:
            raise ValueError(
                f"Unknown entity type {self.type!r}. Valid types: "
                f"{sorted(NODE_HIERARCHY)}. New types require a schema-doc "
                f"update first (CLAUDE.md rule 2)."
            )

    @property
    def base_type(self) -> str:
        """Resource, CodeEntity, or KnowledgeEntity."""
        return NODE_HIERARCHY[self.type]
