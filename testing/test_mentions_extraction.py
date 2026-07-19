"""Phase 7A.2a: MENTIONS (Paper/Markdown/Repository -> KnowledgeEntity) extraction, end to end, no Neo4j writes.

Order: backfill Markdown + Repository source entities (same shape as 7A.1's Paper backfill) + validate them, re-run extraction over all 4 corpus sources in-memory (needed to get entity.properties['mention_count'], which only exists on freshly-converted entities, not on the already-written live graph nodes), generate MENTIONS candidates (registry-driven), resolve targets directly via entity.id (no name reconstruction needed, unlike AUTHORED_BY), validate the resolved relationships, then preview (not execute) the Cypher. Checkpoint discipline continues — stops at the preview.
"""

import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from extraction.entity_converter import (
    convert_markdown_entity,
    convert_paper_entity,
    convert_raw_entities,
    convert_repository_entity,
)
from extraction.entity_extractor import extract_entities
from graph.builders.cypher_builder import build_mentions_cypher
from graph.builders.neo4j_writer import Neo4jWriter
from graph.validators.validator import validate_graph
from ingestion.chunker import chunk_text
from ingestion.github_parser import ingest_repository
from ingestion.markdown_parser import parse_markdown
from ingestion.pdf_parser import extract_pdf_metadata
from models.entity import Entity
from relationships.mentions import resolve_mentions
from relationships.registry import RELATIONSHIP_REGISTRY

ROOT = Path(__file__).parent.parent
PDF_SOURCES = [ROOT / "examples" / "2003.02320v6.pdf", ROOT / "examples" / "2002.00388v4.pdf"]
MARKDOWN_SOURCES = [ROOT / "docs" / "architecture.md"]
REPO_URL = "https://github.com/rdflib/rdflib"
REPO_CACHE = ROOT / ".cache" / "repos"
OUTPUT_PATH = ROOT / "examples" / "expected_output" / "mentions_relationships.json"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _source_slug(extraction_source: str) -> str:
    normalized = re.sub(r"\s+", " ", extraction_source.split(":", 1)[-1]).strip().lower()
    return _NON_ALNUM.sub("_", normalized).strip("_")


print("Phase 7A.2a: MENTIONS extraction (no Neo4j writes)")
print("=" * 70)

extractor = RELATIONSHIP_REGISTRY["MENTIONS"]["extractor"]
validator = RELATIONSHIP_REGISTRY["MENTIONS"]["validator"]

print("\n[1/6] Backfilling source entities (Paper re-derived, Markdown + Repository new)...")
source_entities: list[Entity] = []
all_entities: list[Entity] = []

for pdf_path in PDF_SOURCES:
    extraction_source = f"pdf:{pdf_path.name}"
    metadata = extract_pdf_metadata(str(pdf_path))
    source_entities.append(convert_paper_entity(metadata, extraction_source))
    chunks = chunk_text(metadata.text, source_file=pdf_path.name)
    raw = extract_entities(chunks)
    entities, _ = convert_raw_entities(raw, extraction_source=extraction_source)
    all_entities.extend(entities)
    print(f"      {pdf_path.name}: {len(entities)} entities")

for md_path in MARKDOWN_SOURCES:
    rel = md_path.relative_to(ROOT).as_posix()
    extraction_source = f"md:{rel}"
    doc = parse_markdown(md_path)
    source_entities.append(convert_markdown_entity(doc, extraction_source))
    chunks = chunk_text(doc.text, source_file=rel)
    raw = extract_entities(chunks)
    entities, _ = convert_raw_entities(raw, extraction_source=extraction_source)
    all_entities.extend(entities)
    print(f"      {rel}: {len(entities)} entities")

repo = ingest_repository(REPO_URL, REPO_CACHE)
extraction_source = f"github:rdflib/{repo.name}"
source_entities.append(convert_repository_entity(repo, extraction_source))
repo_chunks = []
for doc in repo.documents:
    try:
        repo_chunks.extend(chunk_text(doc.text, source_file=f"{repo.name}/{doc.path}"))
    except ValueError:
        continue
raw = extract_entities(repo_chunks)
entities, _ = convert_raw_entities(raw, extraction_source=extraction_source)
all_entities.extend(entities)
print(f"      {repo.name}: {len(entities)} entities")

print("\n[2/6] Validating new source entities (Markdown + Repository)...")
new_sources = [e for e in source_entities if e.type in ("Markdown", "Repository")]
source_result = validate_graph(new_sources)
print(f"      {len(source_result.entities)} valid, {len(source_result.errors)} errors")
for err in source_result.errors:
    print(f"        REJECTED {err.item_id}: {err.reason}")

print(f"\n[3/6] Generating MENTIONS candidates ({len(all_entities)} entities total)...")
candidates = extractor(all_entities)
print(f"      {len(candidates)} candidates")

print("\n[4/6] Resolving targets via resolve_target()...")
relationships = resolve_mentions(all_entities)
# resolve_mentions is one-to-one/order-preserving with all_entities (no drop path exists for MENTIONS); zip for the target-type breakdown before validation may filter some out below.
rel_source_entity_type = {id(rel): entity.type for entity, rel in zip(all_entities, relationships)}
print(f"      {len(relationships)} resolved, "
      f"{len(all_entities) - len(relationships)} dropped (expect 0 — no name reconstruction here)")

print("\n[5/6] Validating resolved MENTIONS relationships...")
with Neo4jWriter() as writer:
    live_entity_ids = {r["id"] for r in writer.run_read("MATCH (n:Entity) RETURN n.id AS id")}
    live_canonical_ids = {r["id"] for r in writer.run_read("MATCH (c:Canonical) RETURN c.id AS id")}
new_source_ids = {e.id for e in source_result.entities}
result = validator(
    relationships,
    known_entity_ids=live_entity_ids | new_source_ids,
    known_canonical_ids=live_canonical_ids,
)
print(f"      {len(result.relationships)} valid, {len(result.errors)} errors")
for err in result.errors[:10]:
    print(f"        REJECTED {err.item_id}: {err.reason}")

print("\n[6/6] Cypher preview (NOT executed)...")
example = result.relationships[0]
cypher, params = build_mentions_cypher(example)
print(f"  {cypher}")
print(f"  params: {params}")

by_target_type: Counter[str] = Counter()
by_source_type: Counter[str] = Counter()
for rel in result.relationships:
    source_prefix = rel.source_id.split("_", 1)[0]
    by_source_type[{"paper": "Paper", "markdown": "Markdown", "repo": "Repository"}.get(source_prefix, source_prefix)] += 1
    by_target_type[rel_source_entity_type[id(rel)]] += 1

print()
print("=" * 70)
print(f"Total candidates: {len(candidates)}  |  resolved: {len(relationships)}  |  "
      f"dropped: {len(all_entities) - len(relationships)}  |  "
      f"validation-rejected: {len(result.errors)}")
print(f"\nBy source type: {dict(by_source_type)}")
print(f"By target type: {dict(by_target_type)}")

print("\nSample of 10 resolved candidates:")
for rel in result.relationships[:10]:
    print(f"  {rel.source_id} -[MENTIONS]-> {rel.target_id}  "
          f"(freq {rel.properties['frequency']}, conf {rel.confidence}, {rel.properties['evidence']})")

print("\nWriting mentions_relationships.json (extraction output, no graph write)...")
OUTPUT_PATH.write_text(
    json.dumps(
        {
            "markdowns": [asdict(e) for e in source_result.entities if e.type == "Markdown"],
            "repositories": [asdict(e) for e in source_result.entities if e.type == "Repository"],
            "relationships": [asdict(r) for r in result.relationships],
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print(f"  wrote {OUTPUT_PATH.relative_to(ROOT)}")

print()
print("[OK] STAGE 7A.2a EXTRACTION COMPLETE - nothing written to Neo4j")
