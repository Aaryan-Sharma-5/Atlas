#!/usr/bin/env python3
"""Resolution Stage 1: string-similarity candidate pairs over the live
multi-source graph. NO merging — output is candidate_pairs.json plus a
top-20 sample for human review."""

import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.queries.entity_reader import fetch_all_entities
from resolution.string_matcher import DEFAULT_THRESHOLD, find_candidate_pairs

OUT_PATH = Path(__file__).parent.parent / "examples" / "expected_output" / "candidate_pairs.json"

print("Resolution Stage 1: string-similarity candidates")
print("=" * 70)

print("\n[1/3] Loading entities from Neo4j...")
entities = fetch_all_entities()
sources = Counter(e.extraction_source for e in entities)
print(f"      {len(entities)} entities across {len(sources)} sources")

print(f"\n[2/3] Finding candidate pairs (threshold {DEFAULT_THRESHOLD})...")
pairs = find_candidate_pairs(entities)
cross = [p for p in pairs if p.cross_source]
by_type = Counter(p.type for p in pairs)
print(f"      {len(pairs)} candidate pairs "
      f"({len(cross)} cross-source, {len(pairs) - len(cross)} within-source)")
for node_type, count in by_type.most_common():
    print(f"        {node_type:14s} {count:5d}")

print("\n[3/3] Writing candidate_pairs.json...")
OUT_PATH.write_text(
    json.dumps(
        {
            "stage": "string_similarity",
            "threshold": DEFAULT_THRESHOLD,
            "entity_count": len(entities),
            "pair_count": len(pairs),
            "cross_source_pairs": len(cross),
            "pairs": [asdict(p) for p in pairs],
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
print(f"      wrote {OUT_PATH.relative_to(OUT_PATH.parents[2])}")

print("\nTop 20 highest-confidence pairs for review:")
print(f"      {'score':>6s}  {'type':<13s} {'x-src':<6s} pair")
for p in pairs[:20]:
    marker = "YES" if p.cross_source else "no"
    print(f"      {p.score:6.3f}  {p.type:<13s} {marker:<6s} "
          f"{p.name_a!r}  <->  {p.name_b!r}")

print()
print("=" * 70)
print("[OK] STAGE 1 COMPLETE - candidates generated, nothing merged")
