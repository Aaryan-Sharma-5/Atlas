"""spaCy-based NER over text chunks. Produces raw extraction results only.

Raw results are NOT internal Entity objects (models/) — that conversion happens downstream. This module knows nothing about Neo4j or the graph schema; it reports exactly what spaCy found and where.
"""

from dataclasses import dataclass

import spacy
from spacy.language import Language

from ingestion.chunker import TextChunk

# spaCy NER labels worth keeping for Atlas. Labels like CARDINAL, DATE, PERCENT are noise for a knowledge graph and are dropped at the source.
RELEVANT_LABELS: frozenset[str] = frozenset(
    {"PERSON", "ORG", "GPE", "PRODUCT", "LANGUAGE", "WORK_OF_ART", "NORP", "FAC", "EVENT", "LAW"}
)

DEFAULT_MODEL = "en_core_web_sm"

# Minimum alphabetic characters for a span to count as a real entity. Filters symbol junk the NER model mislabels ("=>", ">=", bullets).
_MIN_ALPHA_CHARS = 2


def _is_noise(text: str) -> bool:
    stripped = text.strip()
    # ASCII-only alpha count: Unicode math symbols report isalpha()=True but are formula fragments, not entity names.
    if sum(c.isalpha() and c.isascii() for c in stripped) < _MIN_ALPHA_CHARS:
        return True
    # Bare URL fragments are artifacts of reference sections, not entities.
    if stripped.lower().startswith(("http", "www.")):
        return True
    return False


@dataclass
class RawEntity:
    """A single NER hit, exactly as spaCy reported it."""
    text: str
    label: str
    start_char: int      # offset within the chunk, not the document
    end_char: int
    chunk_index: int
    source_file: str


def load_model(model_name: str = DEFAULT_MODEL) -> Language:
    """Load a spaCy pipeline with components NER doesn't need disabled."""
    return spacy.load(model_name, disable=["lemmatizer", "textcat"])


def extract_entities_from_chunk(
    nlp: Language,
    chunk: TextChunk,
    relevant_labels: frozenset[str] = RELEVANT_LABELS,
) -> list[RawEntity]:
    """Run NER on a single chunk and return raw hits.

    Args:
        nlp: Loaded spaCy pipeline.
        chunk: Text chunk from ingestion.
        relevant_labels: NER labels to keep; others are discarded.

    Returns:
        Raw entities with chunk-relative character positions.
    """
    doc = nlp(chunk.content)
    return [
        RawEntity(
            text=ent.text,
            label=ent.label_,
            start_char=ent.start_char,
            end_char=ent.end_char,
            chunk_index=chunk.chunk_index,
            source_file=chunk.source_file,
        )
        for ent in doc.ents
        if ent.label_ in relevant_labels and not _is_noise(ent.text)
    ]


def extract_entities(
    chunks: list[TextChunk],
    model_name: str = DEFAULT_MODEL,
    relevant_labels: frozenset[str] = RELEVANT_LABELS,
) -> list[RawEntity]:
    """Run NER across all chunks using nlp.pipe for batch efficiency.

    Args:
        chunks: Chunks from ingestion/chunker.py.
        model_name: spaCy model to use.
        relevant_labels: NER labels to keep.

    Returns:
        All raw entities across chunks, in chunk order.
    """
    if not chunks:
        return []

    nlp = load_model(model_name)

    results: list[RawEntity] = []
    texts = [chunk.content for chunk in chunks]
    for chunk, doc in zip(chunks, nlp.pipe(texts, batch_size=16)):
        results.extend(
            RawEntity(
                text=ent.text,
                label=ent.label_,
                start_char=ent.start_char,
                end_char=ent.end_char,
                chunk_index=chunk.chunk_index,
                source_file=chunk.source_file,
            )
            for ent in doc.ents
            if ent.label_ in relevant_labels and not _is_noise(ent.text)
        )
    return results
