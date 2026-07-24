"""Convert raw spaCy NER results into internal models.Entity objects.

Exact-duplicate mentions (same type + normalized surface form) collapse into one Entity here; fuzzy merging ("OpenAI" vs "OpenAI Inc.") is resolution/'s job and deliberately NOT done at this stage.
"""

import re
import time
from collections import Counter, defaultdict

from extraction.entity_extractor import RawEntity
from ingestion.chunker import TextChunk
from ingestion.github_parser import RepoContent
from ingestion.markdown_parser import MarkdownDoc
from ingestion.pdf_parser import PDFMetadata
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

        # mention_count backs MENTIONS' frequency property (relationships/mentions.py); it was already computed for the confidence heuristic below, just not previously kept.
        # doc_char_start/doc_char_end/source_file are ALWAYS mentions[0]'s (first occurrence in scan order, which follows chunk order = document order) - a deliberate, deterministic choice for chunk-evidence linkage (Step 9.5): for entities with mention_count > 1, evidence_chunk_id always points at the chunk containing the FIRST mention, never the last or an arbitrary one. Reproducible across re-runs since chunk_text()/extract_entities() are deterministic over the same input. Single-chunk evidence for a multi-mention entity is an accepted simplification, not a bug.
        properties: dict[str, object] = {
            "mention_count": len(mentions),
            "doc_char_start": mentions[0].doc_char_start,
            "doc_char_end": mentions[0].doc_char_end,
            "source_file": mentions[0].source_file,  # offsets above are relative to this file's own text
        }
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


def convert_paper_entity(metadata: PDFMetadata, extraction_source: str) -> Entity:
    """PDF ingestion metadata -> a Paper Entity node.

    Id uses the same source_slug namespace as every entity extracted from this PDF (see convert_raw_entities), so `paper_{source_slug}` is the natural, deterministic anchor id for relationships (AUTHORED_BY, MENTIONS) that attach to this paper. Falls back to the source_slug as the name/title when PDF metadata carries no title (observed on this corpus: 2002.00388v4.pdf).
    """
    source_slug = _slugify(_normalize(extraction_source.split(":", 1)[-1]))
    title = metadata.title or source_slug

    properties: dict[str, object] = {
        "title": title,
        "ingestion_timestamp": int(time.time()),
        "file_hash": metadata.file_hash,
        "content_type": "application/pdf",
        "page_count": metadata.page_count,
        "language": metadata.language,
    }
    if metadata.authors:
        properties["authors"] = metadata.authors

    return Entity(
        id=f"paper_{source_slug}",
        type="Paper",
        name=title,
        confidence=1.0,
        extraction_source=extraction_source,
        extraction_method="pdfplumber",
        properties=properties,
    )


def convert_markdown_entity(doc: MarkdownDoc, extraction_source: str) -> Entity:
    """Markdown ingestion output -> a Markdown Entity node (7A.2a source backfill, same shape as convert_paper_entity).

    Falls back to the source_slug as the name/title when no top-level heading was found.
    """
    source_slug = _slugify(_normalize(extraction_source.split(":", 1)[-1]))
    title = doc.title or source_slug

    return Entity(
        id=f"markdown_{source_slug}",
        type="Markdown",
        name=title,
        confidence=1.0,
        extraction_source=extraction_source,
        extraction_method="markdown_parser",
        properties={
            "title": title,
            "ingestion_timestamp": int(time.time()),
            "file_hash": doc.file_hash,
            "content_type": "text/markdown",
        },
    )


def convert_repository_entity(repo: RepoContent, extraction_source: str) -> Entity:
    """GitHub repository metadata -> a Repository Entity node (7A.2a source backfill, same shape as convert_paper_entity).

    `commit` is a git SHA, not the Unix-timestamp physical.md's `last_commit` expects, so it's stored under its own `commit_sha` property rather than force-fit into a field with a different type.
    """
    source_slug = _slugify(_normalize(extraction_source.split(":", 1)[-1]))

    return Entity(
        id=f"repo_{source_slug}",
        type="Repository",
        name=repo.name,
        confidence=1.0,
        extraction_source=extraction_source,
        extraction_method="github_parser",
        properties={
            "url": repo.url,
            "ingestion_timestamp": int(time.time()),
            "commit_sha": repo.commit,
        },
    )


def convert_chunk_entity(
    chunk: TextChunk, source_id: str, extraction_source: str
) -> Entity:
    """Embedding-mode TextChunk -> a Chunk Entity node (Step 9.5).

    Id is scoped by source + chunk_index (embedding-mode indices, not the NER-mode chunker's), so re-running ingestion over the same source reproduces the same Chunk ids (MERGE-idempotent, same principle as Paper/Markdown/Repository).
    """
    source_slug = _slugify(_normalize(extraction_source.split(":", 1)[-1]))

    return Entity(
        id=f"chunk_{source_slug}_{chunk.chunk_index}",
        type="Chunk",
        name=f"{source_id} chunk {chunk.chunk_index}",
        confidence=1.0,
        extraction_source=extraction_source,
        extraction_method="chunker:embedding_mode@v1",
        properties={
            "content": chunk.content,
            "chunk_index": chunk.chunk_index,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "source_id": source_id,
            "created_at": int(time.time()),
        },
    )


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize(text: str) -> str:
    return _collapse_ws(text).lower()


def _slugify(normalized: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return slug or "unnamed"
