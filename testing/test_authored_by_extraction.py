#!/usr/bin/env python3
"""Phase 7A.1: AUTHORED_BY (Paper -> Person) extraction, end to end, no Neo4j writes.

Order: build Paper entities from PDF metadata + validate them, extract author candidates (registry-driven), resolve targets via resolve_target(), validate the resolved relationships, then preview (not execute) the Cypher. Checkpoint discipline continues — this stops at the preview, same as Stage 4 decisioning did before its write was explicitly approved.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from extraction.entity_converter import convert_paper_entity
from graph.builders.cypher_builder import build_authored_by_cypher
from graph.builders.neo4j_writer import Neo4jWriter
from graph.validators.validator import validate_graph
from ingestion.pdf_parser import extract_pdf_metadata
from relationships.authored_by import resolve_candidates
from relationships.registry import RELATIONSHIP_REGISTRY

ROOT = Path(__file__).parent.parent
CORPUS = [ROOT / "examples" / "2002.00388v4.pdf", ROOT / "examples" / "2003.02320v6.pdf"]

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _source_slug(extraction_source: str) -> str:
    normalized = re.sub(r"\s+", " ", extraction_source.split(":", 1)[-1]).strip().lower()
    return _NON_ALNUM.sub("_", normalized).strip("_")


print("Phase 7A.1: AUTHORED_BY extraction (no Neo4j writes)")
print("=" * 70)

extractor = RELATIONSHIP_REGISTRY["AUTHORED_BY"]["extractor"]
validator = RELATIONSHIP_REGISTRY["AUTHORED_BY"]["validator"]

paper_entities = []
all_candidates = []
per_paper_candidate_count = {}

print("\n[1/5] Building Paper entities + candidates per source...")
for pdf_path in CORPUS:
    extraction_source = f"pdf:{pdf_path.name}"
    source_slug = _source_slug(extraction_source)
    paper_id = f"paper_{source_slug}"

    metadata = extract_pdf_metadata(str(pdf_path))
    paper_entities.append(convert_paper_entity(metadata, extraction_source))

    candidates = extractor(paper_id, str(pdf_path), extraction_source)
    all_candidates.extend(candidates)
    per_paper_candidate_count[pdf_path.name] = len(candidates)
    print(f"      {pdf_path.name}: paper_id={paper_id}, "
          f"metadata_authors={'yes' if metadata.authors else 'NO (fallback used)'}, "
          f"{len(candidates)} author candidates")

print("\n[2/5] Validating Paper entities...")
paper_result = validate_graph(paper_entities)
print(f"      {len(paper_result.entities)} valid, {len(paper_result.errors)} errors")
for err in paper_result.errors:
    print(f"        REJECTED {err.item_id}: {err.reason}")

print("\n[3/5] Resolving candidate targets via resolve_target()...")
all_relationships = []
all_dropped = []
for pdf_path in CORPUS:
    extraction_source = f"pdf:{pdf_path.name}"
    source_slug = _source_slug(extraction_source)
    paper_id = f"paper_{source_slug}"
    paper_candidates = [c for c in all_candidates if c.source_entity_id == paper_id]
    rels, dropped = resolve_candidates(paper_candidates, source_slug)
    all_relationships.extend(rels)
    all_dropped.extend(dropped)
print(f"      {len(all_relationships)} resolved, {len(all_dropped)} dropped (no target found)")

print("\n[4/5] Validating resolved AUTHORED_BY relationships...")
with Neo4jWriter() as writer:
    live_entity_ids = {r["id"] for r in writer.run_read("MATCH (n:Entity) RETURN n.id AS id")}
    live_canonical_ids = {r["id"] for r in writer.run_read("MATCH (c:Canonical) RETURN c.id AS id")}
    existing_edges = {
        (r["source"], "AUTHORED_BY", r["target"])
        for r in writer.run_read(
            "MATCH (a)-[r:AUTHORED_BY]->(b) RETURN a.id AS source, b.id AS target"
        )
    }
new_paper_ids = {p.id for p in paper_result.entities}
result = validator(
    all_relationships,
    known_entity_ids=live_entity_ids | new_paper_ids,
    known_canonical_ids=live_canonical_ids,
    existing_edges=existing_edges,
)
print(f"      {len(result.relationships)} valid, {len(result.errors)} errors")
for err in result.errors[:10]:
    print(f"        REJECTED {err.item_id}: {err.reason}")

print("\n[5/5] Cypher preview (NOT executed)...")
example = result.relationships[0]
cypher, params = build_authored_by_cypher(example)
print(f"  {cypher}")
print(f"  params: {params}")

by_kind = {"canonical": 0, "entity (unresolved)": 0}
for rel in result.relationships:
    kind = rel.properties["evidence"].rsplit("target=", 1)[-1]
    by_kind[kind] = by_kind.get(kind, 0) + 1

print()
print("=" * 70)
print(f"Total candidates: {len(all_candidates)}  |  "
      f"resolved: {len(result.relationships)}  |  "
      f"dropped (no target): {len(all_dropped)}  |  "
      f"validation-rejected: {len(result.errors)}")
print(f"Resolved-to-Canonical: {by_kind.get('canonical', 0)}  |  "
      f"Resolved-to-raw-Entity: {by_kind.get('entity (unresolved)', 0)}")
print("\nPapers with zero author candidates:")
zero = [name for name, count in per_paper_candidate_count.items() if count == 0]
print(f"  {zero if zero else 'none'}")

print("\nSample of 10 resolved candidates:")
for rel in result.relationships[:10]:
    print(f"  {rel.source_id} -[AUTHORED_BY]-> {rel.target_id}  "
          f"(conf {rel.confidence}, {rel.properties['evidence']})")

if all_dropped:
    print("\nSample of dropped candidates (no matching target):")
    for line in all_dropped[:10]:
        print(f"  {line}")

print()
print("[OK] STAGE 7A.1 EXTRACTION COMPLETE - nothing written to Neo4j")
