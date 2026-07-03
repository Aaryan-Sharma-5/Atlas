"""Internal data model. Everything imports Entity/Relationship from here."""

from models.entity import NODE_HIERARCHY, Entity
from models.relationship import RELATIONSHIP_TYPES, Relationship

__all__ = [
    "Entity",
    "Relationship",
    "NODE_HIERARCHY",
    "RELATIONSHIP_TYPES",
]
