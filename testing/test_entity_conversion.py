#!/usr/bin/env python3
"""Convert raw spaCy output into models.Entity objects and verify they conform to graph/schema/physical.md (mandatory fields, types)."""

import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from ingestion.pdf_parser import extract_pdf_metadata
from ingestion.chunker import chunk_text
from extraction.entity_extractor import extract_entities
from extraction.entity_converter import convert_raw_entities
from models.entity import NODE_HIERARCHY

pdf_path = Path(__file__).parent.parent / "examples" / "2003.02320v6.pdf"

print(f"Testing raw -> Entity conversion: {pdf_path.name}")
print("=" * 70)

print("\nStep 1: Pipeline (parse -> chunk -> NER)...")
metadata = extract_pdf_metadata(pdf_path)
chunks = chunk_text(metadata.text, source_file=pdf_path.name)
raw = extract_entities(chunks)
print(f"[OK] {len(raw)} raw entities from {len(chunks)} chunks")

print("\nStep 2: Converting to models.Entity...")
entities, skipped = convert_raw_entities(
    raw, extraction_source=f"pdf:{pdf_path.name}"
)
print(f"[OK] {len(entities)} Entity objects created")
print(f"     Skipped (no schema type): "
      + ", ".join(f"{label}={n}" for label, n in sorted(skipped.items())))

print("\nEntities by type:")
for etype, count in Counter(e.type for e in entities).most_common():
    print(f"     {etype:14s} {count:5d}")

print("\nStep 3: Conformance checks against physical.md...")
errors: list[str] = []
seen_ids: set[str] = set()
for e in entities:
    if e.type not in NODE_HIERARCHY:
        errors.append(f"{e.id}: invalid type {e.type}")
    if not (0.0 <= e.confidence <= 1.0):
        errors.append(f"{e.id}: confidence {e.confidence} out of range")
    if not e.extraction_source or not e.extraction_method:
        errors.append(f"{e.id}: missing provenance")
    if not e.id or not e.name:
        errors.append(f"{e.id}: missing id/name")
    if e.id in seen_ids:
        errors.append(f"{e.id}: duplicate id")
    seen_ids.add(e.id)
    if e.type == "Person" and "full_name" not in e.properties:
        errors.append(f"{e.id}: Person missing full_name")

if errors:
    print(f"[FAIL] {len(errors)} conformance errors:")
    for err in errors[:10]:
        print(f"     {err}")
    sys.exit(1)
print(f"[OK] All {len(entities)} entities conform:")
print("     - id unique and present")
print("     - type in schema hierarchy")
print("     - confidence in [0.0, 1.0]")
print("     - extraction_source / extraction_method present")
print("     - Person entities carry full_name")

print("\nSample Entity objects (highest-confidence per type):")
by_type: dict[str, list] = {}
for e in sorted(entities, key=lambda x: -x.confidence):
    by_type.setdefault(e.type, []).append(e)
for etype, ents in sorted(by_type.items()):
    print(f"\n--- {etype} ({ents[0].base_type}) ---")
    print(json.dumps(asdict(ents[0]), indent=2, ensure_ascii=False))

print()
print("=" * 70)
print("[OK] Day 5 conversion test PASSED (no Neo4j touched)")
