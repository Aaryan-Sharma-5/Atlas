#!/usr/bin/env python3
"""Resolution Stage 1 diagnostic: string-similarity candidate pairs over the live multi-source graph. NO merging, and since Stage 2 this script writes nothing — examples/expected_output/candidate_pairs.json is owned by test_combined_resolution.py (string + embedding).

Names are normalized (accent folding, leading articles, dual forms for middle initials) and union-blocked (first_token | last_token | sorted_initials) before RapidFuzz runs; scoring itself is unchanged. Threshold 0.85 stays put — recalibration is a manual step, not done here."""

import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.queries.entity_reader import fetch_all_entities
from resolution.blocking.blocker import block_stats, generate_blocks
from resolution.matchers.string_matcher import DEFAULT_THRESHOLD, find_candidate_pairs

logging.basicConfig(level=logging.INFO, format="      %(message)s")

print("Resolution Stage 1: string-similarity candidates (normalized + blocked)")
print("=" * 70)

print("\n[1/3] Loading entities from Neo4j...")
entities = fetch_all_entities()
sources = Counter(e.extraction_source for e in entities)
print(f"      {len(entities)} entities across {len(sources)} sources")

print("\n[2/3] Blocking (union: first_token | last_token | sorted_initials)...")
stats = block_stats(generate_blocks(entities))
full_pairwise = sum(
    n * (n - 1) // 2 for n in Counter(e.type for e in entities).values()
)
print(f"      {stats['blocks']} blocks, largest {stats['largest']}, "
      f"avg {stats['average']}, singletons {stats['singletons']}")
print(f"      unique candidate pairs: {stats['unique_pairs']} "
      f"vs {full_pairwise} full per-type pairwise "
      f"({100 * stats['unique_pairs'] / full_pairwise:.2f}%); "
      f"{stats['comparison_slots']} within-block slots")

print(f"\n[3/3] Finding candidate pairs (threshold {DEFAULT_THRESHOLD})...")
pairs = find_candidate_pairs(entities)
cross = [p for p in pairs if p.cross_source]
by_type = Counter(p.type for p in pairs)
print(f"      {len(pairs)} candidate pairs "
      f"({len(cross)} cross-source, {len(pairs) - len(cross)} within-source)")
for node_type, count in by_type.most_common():
    print(f"        {node_type:14s} {count:5d}")

print("\nTop 20 highest-confidence pairs for review:")
print(f"      {'score':>6s}  {'type':<13s} {'x-src':<6s} pair")
for p in pairs[:20]:
    marker = "YES" if p.cross_source else "no"
    print(f"      {p.score:6.3f}  {p.type:<13s} {marker:<6s} "
          f"{p.name_a!r}  <->  {p.name_b!r}")

print()
print("=" * 70)
print("[OK] STAGE 1 COMPLETE - candidates generated, nothing merged")
