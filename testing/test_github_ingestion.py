#!/usr/bin/env python3
"""GitHub ingestion: rdflib repo docs -> NER -> Neo4j as a third source,
then cross-source overlap across papers + code."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from ingestion.github_parser import ingest_repository
from ingestion.chunker import chunk_text
from extraction.entity_extractor import extract_entities
from extraction.entity_converter import convert_raw_entities
from graph.validators.validator import validate_graph
from graph.builders.neo4j_writer import Neo4jWriter

ROOT = Path(__file__).parent.parent
REPO_URL = "https://github.com/rdflib/rdflib"
CACHE = ROOT / ".cache" / "repos"

print("GitHub ingestion: rdflib/rdflib")
print("=" * 70)

print("\n[1/4] Cloning / reading repository docs...")
repo = ingest_repository(REPO_URL, CACHE)
source = f"github:rdflib/{repo.name}"
total_chars = sum(len(d.text) for d in repo.documents)
print(f"      {repo.name} @ {repo.commit[:12]}")
print(f"      {len(repo.documents)} doc files (.md/.rst), {total_chars:,} chars of prose")

print("\n[2/4] Chunking + NER per document...")
all_chunks = []
for doc in repo.documents:
    try:
        all_chunks.extend(
            chunk_text(doc.text, source_file=f"{repo.name}/{doc.path}")
        )
    except ValueError:
        continue  # doc too small/empty after cleanup
raw = extract_entities(all_chunks)
print(f"      {len(all_chunks)} chunks -> {len(raw)} raw mentions")

print("\n[3/4] Convert -> validate -> write...")
entities, _ = convert_raw_entities(raw, extraction_source=source)
validated = validate_graph(entities)
if not validated.ok:
    print(f"[FAIL] {len(validated.errors)} validation errors")
    sys.exit(1)

with Neo4jWriter() as writer:
    deleted = writer.clear_source(source)
    if deleted:
        print(f"      cleared {deleted} existing nodes (re-run)")
    counts = writer.write(validated)
    print(f"      wrote {counts['entities_written']} entities under {source!r}")

    print("\n[4/4] Cross-source overlap (papers + code)...")
    for row in writer.run_read(
        "MATCH (n:Entity) RETURN n.extraction_source AS source, "
        "count(*) AS nodes ORDER BY source"
    ):
        print(f"      {row['source']:28s} {row['nodes']:5d} nodes")

    overlaps = writer.run_read(
        "MATCH (a:Entity), (b:Entity) "
        "WHERE a.extraction_source STARTS WITH 'pdf:' "
        "  AND b.extraction_source STARTS WITH 'github:' "
        "  AND toLower(a.name) = toLower(b.name) "
        "RETURN DISTINCT toLower(a.name) AS name, "
        "[l IN labels(b) WHERE NOT l IN ['Entity','KnowledgeEntity']][0] AS type "
        "ORDER BY name"
    )
    print(f"\n      {len(overlaps)} distinct names appear in BOTH papers and code:")
    for row in overlaps[:20]:
        print(f"        {row['type']:14s} {row['name']}")
    if len(overlaps) > 20:
        print(f"        ... and {len(overlaps) - 20} more")

print()
print("=" * 70)
print("[OK] Papers + code repository now share one graph - "
      "cross-domain entity resolution has real material")
