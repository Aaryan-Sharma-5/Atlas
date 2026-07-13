"""Read-only Cypher query templates."""

from graph.queries.entity_reader import fetch_all_entities
from graph.queries.resolve_target import resolve_target

__all__ = ["fetch_all_entities", "resolve_target"]
