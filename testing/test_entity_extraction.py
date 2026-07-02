#!/usr/bin/env python3
"""Test spaCy entity extraction against the Knowledge Graphs paper."""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from ingestion.pdf_parser import extract_pdf_metadata
from ingestion.chunker import chunk_text
from extraction.entity_extractor import extract_entities

pdf_path = Path(__file__).parent.parent / "examples" / "2003.02320v6.pdf"

print(f"Testing entity extraction: {pdf_path.name}")
print("=" * 70)

print("\nStep 1: Ingesting PDF (parser + chunker)...")
metadata = extract_pdf_metadata(pdf_path)
chunks = chunk_text(metadata.text, source_file=pdf_path.name)
print(f"[OK] {len(chunks)} chunks from {metadata.page_count} pages")

print("\nStep 2: Running spaCy NER over all chunks...")
entities = extract_entities(chunks)
print(f"[OK] {len(entities)} raw entities extracted")

print("\nLabel distribution:")
label_counts = Counter(e.label for e in entities)
for label, count in label_counts.most_common():
    print(f"     {label:12s} {count:5d}")

print("\nMost frequent entities per label (top 5 labels):")
for label, _ in label_counts.most_common(5):
    texts = Counter(e.text for e in entities if e.label == label)
    top = ", ".join(f"{t} ({n})" for t, n in texts.most_common(5))
    print(f"     {label:12s} {top}")

print("\nSample raw results (first 10):")
for e in entities[:10]:
    print(f"     chunk {e.chunk_index:2d} [{e.start_char:4d}:{e.end_char:4d}] {e.label:10s} {e.text!r}")

print()
print("=" * 70)
print("[OK] Entity extraction test PASSED")
print("Next: Day 5 converts these raw results into models.Entity objects")
