#!/usr/bin/env python3
"""Combined Stage 1+2 candidate set: string-matcher pairs (threshold 0.85) plus embedding-matcher pairs (threshold 0.90) over the live multi-source graph. NO merging — this is the full candidate input to Stage 4 decisioning.

Owns examples/expected_output/candidate_pairs.json; the per-stage scripts (test_string_resolution.py, test_embedding_resolution.py) are diagnostic-only and write nothing there."""

import json
import logging
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.queries.entity_reader import fetch_all_entities
from resolution.matchers.embedding_matcher import (
    DEFAULT_THRESHOLD as EMBEDDING_THRESHOLD,
    DEFAULT_MODEL,
    find_embedding_candidates,
)
from resolution.matchers.string_matcher import (
    DEFAULT_THRESHOLD as STRING_THRESHOLD,
    find_candidate_pairs,
)

logging.basicConfig(level=logging.WARNING)

OUT_PATH = Path(__file__).parent.parent / "examples" / "expected_output" / "candidate_pairs.json"

print("Resolution Stage 1+2: combined candidate set")
print("=" * 70)

print("\n[1/3] Loading entities from Neo4j...")
entities = fetch_all_entities()
print(f"      {len(entities)} entities")

print(f"\n[2/3] Matching (string >= {STRING_THRESHOLD}, embedding >= {EMBEDDING_THRESHOLD})...")
string_pairs = find_candidate_pairs(entities)
exclude = {tuple(sorted((p.id_a, p.id_b))) for p in string_pairs}
embedding_pairs = find_embedding_candidates(entities, exclude=exclude)

overlap = exclude & {tuple(sorted((p.id_a, p.id_b))) for p in embedding_pairs}
assert not overlap, f"matchers overlap on {len(overlap)} pairs: {sorted(overlap)[:5]}"

combined = [
    {**asdict(p), "matcher": "string"} for p in string_pairs
] + [
    {**asdict(p), "matcher": "embedding"} for p in embedding_pairs
]
combined.sort(key=lambda p: (-p["score"], p["name_a"], p["id_a"], p["id_b"]))

cross = sum(1 for p in combined if p["cross_source"])
by_matcher = Counter(p["matcher"] for p in combined)
by_type = Counter(p["type"] for p in combined)
print(f"      {len(combined)} combined candidate pairs "
      f"({by_matcher['string']} string, {by_matcher['embedding']} embedding, "
      f"{cross} cross-source)")
for node_type, count in by_type.most_common():
    print(f"        {node_type:14s} {count:5d}")

print("\n[3/3] Writing candidate_pairs.json...")
OUT_PATH.write_text(
    json.dumps(
        {
            "stage": "combined_string_embedding",
            "string_threshold": STRING_THRESHOLD,
            "embedding_threshold": EMBEDDING_THRESHOLD,
            "embedding_model": DEFAULT_MODEL,
            # scores are NOT on one scale: string pairs carry RapidFuzz ratios, embedding pairs carry cosine similarity; "matcher" says which. Embedding threshold finalized at 0.90
            "entity_count": len(entities),
            "pair_count": len(combined),
            "string_pairs": by_matcher["string"],
            "embedding_pairs": by_matcher["embedding"],
            "cross_source_pairs": cross,
            "pairs": combined,
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
print(f"      wrote {OUT_PATH.relative_to(OUT_PATH.parents[2])}")

print("\nTop 10 embedding-sourced candidates:")
for p in [p for p in combined if p["matcher"] == "embedding"][:10]:
    marker = "YES" if p["cross_source"] else "no"
    print(f"      {p['score']:6.3f}  {p['type']:<13s} {marker:<6s} "
          f"{p['name_a']!r}  <->  {p['name_b']!r}")

print()
print("=" * 70)
print("[OK] STAGE 1+2 COMPLETE - combined candidates generated, nothing merged")
