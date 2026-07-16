"""AUTHORED_BY (Paper -> Person) extraction (Phase 7A.1).

extract_authors() produces RelationshipCandidates from PDF metadata, falling back to the page-1 byline when metadata coverage is missing or unreliable (observed on this corpus: 2002.00388v4.pdf has no metadata title/authors at all). resolve_candidates() resolves each candidate's raw target_name to a live graph id via graph/queries/resolve_target.py, producing models. Relationship objects (Rule 1) — candidates with no matching Person entity are dropped, never attached to a name that doesn't exist in the graph.
"""

import re

from graph.queries.entity_reader import fetch_all_entities
from graph.queries.resolve_target import resolve_target
from ingestion.pdf_parser import extract_pdf_metadata
from models.relationship import Relationship
from models.relationship_candidate import RelationshipCandidate

# Byline role/affiliation tokens that ride along with comma-split names in both metadata Author fields and page-1 bylines (e.g. IEEE membership grade).
_ROLE_TOKENS = {
    "ieee",
    "member",
    "senior member",
    "life fellow",
    "fellow",
    "student member",
    "life member",
    "senior fellow",
}
_LEADING_AND = re.compile(r"^\s*and\s+", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

_METADATA_CONFIDENCE = 0.98
_FALLBACK_CONFIDENCE = 0.96


def extract_authors(
    paper_id: str, pdf_path: str, extraction_source: str
) -> list[RelationshipCandidate]:
    """Primary: PDF metadata's Author field. Fallback: page-1 byline text, only when metadata is absent (checked against this corpus before building this path — see docs/architecture.md Phase 7A notes)."""
    metadata = extract_pdf_metadata(pdf_path)

    if metadata.authors:
        names = _split_names(metadata.authors[0])
        evidence, method, confidence = (
            "metadata:author_list",
            "pdf_metadata_authors",
            _METADATA_CONFIDENCE,
        )
    else:
        names = _extract_byline(metadata.text)
        evidence, method, confidence = (
            "page1:author_section",
            "page1_byline_heuristic",
            _FALLBACK_CONFIDENCE,
        )

    return [
        RelationshipCandidate(
            source_entity_id=paper_id,
            target_name=name,
            relationship_type="AUTHORED_BY",
            evidence=evidence,
            confidence=confidence,
            extraction_source=extraction_source,
            extraction_method=method,
        )
        for name in names
    ]


def resolve_candidates(
    candidates: list[RelationshipCandidate], source_slug: str
) -> tuple[list[Relationship], list[str]]:
    """target_name -> live graph id. The candidate Person id is constructed with the exact same convention as extraction/entity_converter.py (so it matches real NER-extracted entities from the same source), then resolved through resolve_target() to its Canonical if one exists.

    Returns (relationships, dropped_log) — dropped candidates never become a relationship (no attaching to a name absent from the graph).
    """
    live_ids = {e.id for e in fetch_all_entities()}
    relationships: list[Relationship] = []
    dropped: list[str] = []

    for c in candidates:
        entity_id = f"person_{_entity_slug(c.target_name)}__{source_slug}"
        if entity_id not in live_ids:
            dropped.append(f"{c.target_name!r}: no matching Entity ({entity_id})")
            continue
        target_id = resolve_target(entity_id)
        target_kind = "canonical" if target_id != entity_id else "entity (unresolved)"
        relationships.append(
            Relationship(
                source_id=c.source_entity_id,
                target_id=target_id,
                type=c.relationship_type,
                confidence=c.confidence,
                extraction_source=c.extraction_source,
                extraction_method=c.extraction_method,
                properties={"evidence": f"{c.evidence}; target={target_kind}"},
            )
        )
    return relationships, dropped


def _split_names(raw: str) -> list[str]:
    tokens = (_LEADING_AND.sub("", t.strip()) for t in raw.split(","))
    return [t for t in tokens if t and t.lower() not in _ROLE_TOKENS]


def _extract_byline(text: str) -> list[str]:
    page1 = text.split("--- Page 2 ---")[0]
    lines = [
        line.strip()
        for line in page1.splitlines()
        if line.strip() and not line.strip().startswith("---")
    ]
    # First real line is the running journal header (e.g. "IEEE TRANSACTIONS ON ..., 2021 1"); skip it. Everything else up to "Abstract" is title + byline — title fragments ride along but safely fail resolution below rather than being silently included as authors.
    body: list[str] = []
    for line in lines[1:]:
        if line.lower().startswith("abstract"):
            break
        body.append(line)
    # Join with a comma, not a space: a line break can fall between two names with no trailing comma of its own (title -> byline, or a wrapped byline), and a bare space-join would silently fuse the last title word into the first author's name.
    return _split_names(", ".join(body))


def _entity_slug(name: str) -> str:
    """Must exactly match extraction/entity_converter.py's Person id slug (lowercase + collapse whitespace, non-alnum runs -> single underscore) - NOT unicode-folded, so mangled/accented names slug identically to however NER actually extracted them, or safely fail to match at all."""
    normalized = _WHITESPACE.sub(" ", name).strip().lower()
    return _NON_ALNUM.sub("_", normalized).strip("_") or "unnamed"
