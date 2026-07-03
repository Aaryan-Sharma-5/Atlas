#!/usr/bin/env python3
"""Full pipeline end to end.

PDF -> chunks -> spaCy NER -> Entity objects -> validation -> Cypher -> Neo4j.
Requires the docker-compose Neo4j instance to be running.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from ingestion.pdf_parser import extract_pdf_metadata
from ingestion.chunker import chunk_text
from extraction.entity_extractor import extract_entities
from extraction.entity_converter import convert_raw_entities
from graph.validators.validator import validate_graph
from graph.builders.cypher_builder import build_entity_cypher
from graph.builders.neo4j_writer import Neo4jWriter

ROOT = Path(__file__).parent.parent
PDF_PATH = ROOT / "examples" / "2003.02320v6.pdf"
CONSTRAINTS_PATH = ROOT / "graph" / "schema" / "constraints.cypher"
SOURCE = f"pdf:{PDF_PATH.name}"

print("Full pipeline -> Neo4j")
print("=" * 70)

print("\n[1/6] Ingestion: parsing and chunking PDF...")
metadata = extract_pdf_metadata(PDF_PATH)
chunks = chunk_text(metadata.text, source_file=PDF_PATH.name)
print(f"      {metadata.page_count} pages -> {len(chunks)} chunks")

print("\n[2/6] Extraction: spaCy NER...")
raw = extract_entities(chunks)
print(f"      {len(raw)} raw entity mentions")

print("\n[3/6] Conversion: raw -> models.Entity...")
entities, skipped = convert_raw_entities(raw, extraction_source=SOURCE)
print(f"      {len(entities)} Entity objects ({sum(skipped.values())} unmappable mentions skipped)")

print("\n[4/6] Validation...")
validated = validate_graph(entities)
if not validated.ok:
    print(f"[FAIL] {len(validated.errors)} validation errors")
    sys.exit(1)
print(f"      {len(validated.entities)} entities passed, 0 errors")

print("\n[5/6] Neo4j: constraints + write...")
with Neo4jWriter() as writer:
    writer.verify_connectivity()
    print("      connected to Neo4j")

    applied = writer.apply_constraints(CONSTRAINTS_PATH)
    print(f"      {applied} constraint statement(s) applied")

    deleted = writer.clear_source(SOURCE)
    if deleted:
        print(f"      cleared {deleted} existing nodes from {SOURCE} (re-run)")

    counts = writer.write(validated)
    print(f"      wrote {counts['entities_written']} entities, "
          f"{counts['relationships_written']} relationships")

    print("\n[6/6] Verification queries...")
    label_counts = writer.run_read(
        "MATCH (n:Entity) RETURN labels(n) AS labels, count(*) AS count "
        "ORDER BY count DESC"
    )
    total = sum(r["count"] for r in label_counts)
    print(f"      total :Entity nodes: {total}")
    for row in label_counts:
        print(f"        {':'.join(row['labels']):45s} {row['count']:5d}")

    constraints = writer.run_read("SHOW CONSTRAINTS YIELD name, type RETURN name, type")
    print(f"      constraints active: "
          + ", ".join(f"{c['name']} ({c['type']})" for c in constraints))

    print("\n      Sample Person node from Neo4j:")
    person = writer.run_read(
        "MATCH (n:Person) WHERE n.confidence >= 0.9 "
        "RETURN n ORDER BY n.name LIMIT 1"
    )[0]["n"]
    print("      " + json.dumps(person, indent=2, ensure_ascii=False).replace("\n", "\n      "))

    print("\n      Sample Technology node from Neo4j:")
    tech = writer.run_read(
        "MATCH (n:Technology) RETURN n ORDER BY n.confidence DESC LIMIT 1"
    )[0]["n"]
    print("      " + json.dumps(tech, indent=2, ensure_ascii=False).replace("\n", "\n      "))

    assert total == len(validated.entities), "node count must match written entities"

# Show the exact Cypher the sample entity was built from
sample_entity = next(e for e in validated.entities if e.id == person["id"])
cypher, params = build_entity_cypher(sample_entity)
print("\nCypher that created the sample entity (single-node form):")
print(f"      {cypher}")
print("      params: " + json.dumps(params, ensure_ascii=False))

print()
print("=" * 70)
print("[OK] FULL PIPELINE PASSED: PDF -> chunks -> NER -> Entity -> "
      "validation -> Cypher -> Neo4j")
print()
print("Verify manually in Neo4j Browser (http://localhost:7474):")
print("  MATCH (n:Person)      RETURN n LIMIT 25;")
print("  MATCH (n:Technology)  RETURN n LIMIT 25;")
print("  MATCH (n:Entity)      RETURN count(n);")
