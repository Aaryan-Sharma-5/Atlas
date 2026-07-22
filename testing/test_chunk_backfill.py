"""Step 9.5: Chunk nodes + HAS_CHUNK edges + chunk-evidence enrichment for existing AUTHORED_BY/MENTIONS relationships. Preview only - no Neo4j writes, no embeddings generated, no new Entity/Canonical/relationship nodes.

Order per source: NER-mode chunking (500 tokens, UNCHANGED - reproduces the exact live entity ids, verified this matters: 60-token chunking produces a DIFFERENT entity set) for entity doc-positions, and embedding-mode chunking (60 tokens) separately for the actual Chunk nodes. Chunk + HAS_CHUNK are validated and previewed as new writes (MERGE-idempotent). For every LIVE AUTHORED_BY/MENTIONS edge, find which of this source's entities resolves to that edge's target, map its doc position to a containing embedding-mode Chunk, and preview a SET enrichment (not a new edge - the edge already exists from a prior session).
"""

import dataclasses
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from extraction.entity_converter import (
    convert_chunk_entity,
    convert_raw_entities,
)
from extraction.entity_extractor import extract_entities
from graph.builders.cypher_builder import (
    build_evidence_enrichment_cypher,
    build_has_chunk_cypher,
)
from graph.builders.neo4j_writer import Neo4jWriter
from graph.queries.resolve_target import resolve_target
from graph.validators.validator import validate_graph, validate_has_chunk
from ingestion.chunker import chunk_text, chunk_text_for_embedding
from ingestion.github_parser import ingest_repository
from ingestion.markdown_parser import parse_markdown
from ingestion.pdf_parser import extract_pdf_metadata
from models.relationship import Relationship

ROOT = Path(__file__).parent.parent
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _source_slug(identifier: str) -> str:
    normalized = re.sub(r"\s+", " ", identifier).strip().lower()
    return _NON_ALNUM.sub("_", normalized).strip("_")


def _find_chunk(chunks_sorted, source_file, doc_pos):
    # char_start/char_end are relative to source_file's own text, not globally offset across a multi-file source (e.g. Repository) - must filter to the same file before comparing positions, or a position in one file can spuriously match a same-numbered range in another file.
    for c in chunks_sorted:
        if c.source_file == source_file and c.char_start <= doc_pos < c.char_end:
            return c
    return None


print("Step 9.5: Chunk nodes + HAS_CHUNK + evidence enrichment (no writes)")
print("=" * 70)

print("\n[1/7] Building per-source text + source_id manifest...")
manifest = []  # each: {extraction_source, source_id, texts: [(source_file, text), ...]}

pdf_meta_1 = extract_pdf_metadata(str(ROOT / "examples" / "2003.02320v6.pdf"))
manifest.append({
    "extraction_source": "pdf:2003.02320v6.pdf",
    "source_id": "paper_" + _source_slug("2003.02320v6.pdf"),
    "texts": [("2003.02320v6.pdf", pdf_meta_1.text)],
})
pdf_meta_2 = extract_pdf_metadata(str(ROOT / "examples" / "2002.00388v4.pdf"))
manifest.append({
    "extraction_source": "pdf:2002.00388v4.pdf",
    "source_id": "paper_" + _source_slug("2002.00388v4.pdf"),
    "texts": [("2002.00388v4.pdf", pdf_meta_2.text)],
})
md_doc = parse_markdown(ROOT / "examples" / "corpus" / "architecture_pinned.md")
manifest.append({
    "extraction_source": "md:docs/architecture.md",
    "source_id": "markdown_" + _source_slug("docs/architecture.md"),
    "texts": [("docs/architecture.md", md_doc.text)],
})
repo = ingest_repository("https://github.com/rdflib/rdflib", ROOT / ".cache" / "repos")
manifest.append({
    "extraction_source": f"github:rdflib/{repo.name}",
    "source_id": "repo_" + _source_slug(f"rdflib/{repo.name}"),
    "texts": [(f"{repo.name}/{d.path}", d.text) for d in repo.documents],
})
for m in manifest:
    print(f"      {m['source_id']} <- {m['extraction_source']} ({len(m['texts'])} file(s))")

print("\n[2/7] NER-mode extraction (500 tokens, unchanged) for entity doc-positions...")
entities_by_source: dict[str, list] = {}
for m in manifest:
    # Batch ALL files' chunks into one extract_entities()/convert_raw_entities() call per source - matches the original ingestion pattern exactly (spaCy loaded once per source, not once per file; convert_raw_entities groups by (type, slug) across the whole source, so calling it per-file would produce duplicate-id entities for names appearing in multiple files).
    ner_chunks = []
    for source_file, text in m["texts"]:
        ner_chunks.extend(chunk_text(text, source_file=source_file))
    raw = extract_entities(ner_chunks)
    entities, _ = convert_raw_entities(raw, extraction_source=m["extraction_source"])
    entities_by_source[m["source_id"]] = entities
    print(f"      {m['source_id']}: {len(entities)} entities (with doc_char_start/end)")

print("\n[3/7] Embedding-mode chunking (60 tokens) -> Chunk entities + HAS_CHUNK...")
chunk_entities = []
embedding_chunks_by_source: dict[str, list] = {}
for m in manifest:
    global_idx = 0
    flat_chunks = []
    for source_file, text in m["texts"]:
        for c in chunk_text_for_embedding(text, source_file=source_file):
            flat_chunks.append(dataclasses.replace(c, chunk_index=global_idx))
            global_idx += 1
    embedding_chunks_by_source[m["source_id"]] = flat_chunks
    for c in flat_chunks:
        chunk_entities.append(convert_chunk_entity(c, m["source_id"], m["extraction_source"]))
    print(f"      {m['source_id']}: {len(flat_chunks)} embedding-mode chunks")

print(f"\n      Total Chunk entities: {len(chunk_entities)}")

print("\n[4/7] Validating Chunk entities + building HAS_CHUNK relationships...")
chunk_result = validate_graph(chunk_entities)
print(f"      Chunks: {len(chunk_result.entities)} valid, {len(chunk_result.errors)} errors")
for err in chunk_result.errors[:10]:
    print(f"        REJECTED {err.item_id}: {err.reason}")

has_chunk_rels = [
    Relationship(
        source_id=e.properties["source_id"],
        target_id=e.id,
        type="HAS_CHUNK",
        confidence=1.0,
        extraction_source=e.extraction_source,
        extraction_method="chunker:embedding_mode@v1",
        properties={},
    )
    for e in chunk_result.entities
]

with Neo4jWriter() as writer:
    live_entity_ids = {r["id"] for r in writer.run_read("MATCH (n:Entity) RETURN n.id AS id")}
    live_canonical_ids = {r["id"] for r in writer.run_read("MATCH (c:Canonical) RETURN c.id AS id")}
    live_authored_by = writer.run_read(
        "MATCH (a)-[r:AUTHORED_BY]->(b) RETURN a.id AS source, b.id AS target"
    )
    live_mentions = writer.run_read(
        "MATCH (a)-[r:MENTIONS]->(b) RETURN a.id AS source, b.id AS target"
    )

new_chunk_ids = {e.id for e in chunk_result.entities}
has_chunk_result = validate_has_chunk(
    has_chunk_rels,
    known_entity_ids=live_entity_ids | new_chunk_ids,
    known_canonical_ids=live_canonical_ids,
)
print(f"      HAS_CHUNK: {len(has_chunk_result.relationships)} valid, {len(has_chunk_result.errors)} errors")
for err in has_chunk_result.errors[:10]:
    print(f"        REJECTED {err.item_id}: {err.reason}")

print("\n[5/7] Evidence enrichment: matching live AUTHORED_BY/MENTIONS edges to a Chunk...")
source_id_to_extraction_source = {m["source_id"]: m["extraction_source"] for m in manifest}
enrichments = []
not_found = []

for rel_type, live_rels in [("AUTHORED_BY", live_authored_by), ("MENTIONS", live_mentions)]:
    for row in live_rels:
        source_id, target_id = row["source"], row["target"]
        candidates = entities_by_source.get(source_id, [])
        match = next((e for e in candidates if resolve_target(e.id) == target_id), None)
        if match is None:
            not_found.append((rel_type, source_id, target_id, "no source entity resolves to this target"))
            continue
        emb_chunks = embedding_chunks_by_source.get(source_id, [])
        chunk = _find_chunk(emb_chunks, match.properties["source_file"], match.properties["doc_char_start"])
        if chunk is None:
            not_found.append((rel_type, source_id, target_id, "doc position outside all embedding-mode chunks"))
            continue
        chunk_id = f"chunk_{_source_slug(source_id_to_extraction_source[source_id].split(':', 1)[-1])}_{chunk.chunk_index}"
        enrichments.append((rel_type, source_id, target_id, chunk_id))

print(f"      {len(enrichments)} enriched, {len(not_found)} could not be matched")
if not_found:
    reasons = {}
    for rel_type, s, t, reason in not_found:
        reasons[reason] = reasons.get(reason, 0) + 1
    for reason, count in reasons.items():
        print(f"        {count}x: {reason}")

print("\n[6/7] Cypher preview (NOT executed)...")
example_chunk = chunk_result.entities[0]
from graph.builders.cypher_builder import build_entity_merge_cypher
chunk_cypher, chunk_params = build_entity_merge_cypher(example_chunk)
print("  -- Chunk node --")
print(f"  {chunk_cypher}")
print(f"  params: {{'id': {chunk_params['props']['id']!r}, 'content': <{len(chunk_params['props']['content'])} chars>, "
      f"'chunk_index': {chunk_params['props']['chunk_index']}, 'char_start': {chunk_params['props']['char_start']}, "
      f"'char_end': {chunk_params['props']['char_end']}, 'source_id': {chunk_params['props']['source_id']!r}}}")

example_has_chunk = has_chunk_result.relationships[0]
hc_cypher, hc_params = build_has_chunk_cypher(example_has_chunk)
print("\n  -- HAS_CHUNK edge --")
print(f"  {hc_cypher}")
print(f"  params: {hc_params}")

if enrichments:
    rel_type, source_id, target_id, chunk_id = enrichments[0]
    ev_cypher, ev_params = build_evidence_enrichment_cypher(source_id, rel_type, target_id, chunk_id)
    print("\n  -- Evidence enrichment --")
    print(f"  {ev_cypher}")
    print(f"  params: {ev_params}")

print("\n[7/7] Writing chunk_backfill.json (preview output, no graph write)...")
from dataclasses import asdict
OUTPUT_PATH = ROOT / "examples" / "expected_output" / "chunk_backfill.json"
OUTPUT_PATH.write_text(
    json.dumps(
        {
            "chunks": [asdict(e) for e in chunk_result.entities],
            "has_chunk": [asdict(r) for r in has_chunk_result.relationships],
            "evidence_enrichments": [
                {"rel_type": rt, "source_id": s, "target_id": t, "chunk_id": c}
                for rt, s, t, c in enrichments
            ],
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print(f"  wrote {OUTPUT_PATH.relative_to(ROOT)}")

print()
print("=" * 70)
print(f"Chunk nodes: {len(chunk_result.entities)}  |  HAS_CHUNK edges: {len(has_chunk_result.relationships)}")
print(f"AUTHORED_BY total: {len(live_authored_by)}  |  MENTIONS total: {len(live_mentions)}")
print(f"Evidence enrichments: {len(enrichments)}  |  not matched: {len(not_found)}")
print("[OK] STEP 9.5 PREVIEW COMPLETE - nothing written to Neo4j")
