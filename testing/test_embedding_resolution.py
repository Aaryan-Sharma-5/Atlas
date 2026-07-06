#!/usr/bin/env python3
"""Resolution Stage 2 calibration: embedding similarity over blocked pairs the string matcher did NOT pair. NO threshold is applied and NO expected_output is written — this run produces the report the embedding threshold gets calibrated against, manually."""

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
    find_embedding_candidates,
    score_name_pairs,
)
from resolution.matchers.string_matcher import find_candidate_pairs

logging.basicConfig(level=logging.INFO, format="      %(message)s")

SCRATCH_OUT = Path(__file__).parent.parent / ".cache" / "embedding_calibration.json"

print("Resolution Stage 2 calibration: embedding similarity (no threshold)")
print("=" * 70)

print("\n[1/4] Loading entities and string-matcher pairs...")
entities = fetch_all_entities()
string_pairs = find_candidate_pairs(entities)
exclude = {tuple(sorted((p.id_a, p.id_b))) for p in string_pairs}
print(f"      {len(entities)} entities; excluding {len(exclude)} string-paired")

print("\n[2/4] Scoring blocked-but-unpaired candidates...")
scored = find_embedding_candidates(entities, exclude=exclude, threshold=None)
print(f"      {len(scored)} pairs scored")

print("\n      cosine distribution:")
buckets = Counter(min(int(p.score * 20), 19) for p in scored)
for b in sorted(buckets, reverse=True):
    lo = b / 20
    if lo < 0.60:
        below = sum(v for k, v in buckets.items() if k / 20 < 0.60)
        print(f"        < 0.60      {below:6d}")
        break
    print(f"        {lo:.2f}-{lo + 0.05:.2f}   {buckets[b]:6d}")

print("\n[3/4] Top 30 embedding-only candidates (string matcher missed these):")
print(f"      {'cos':>6s}  {'type':<13s} {'x-src':<6s} pair")
for p in scored[:30]:
    marker = "YES" if p.cross_source else "no"
    print(f"      {p.score:6.3f}  {p.type:<13s} {marker:<6s} "
          f"{p.name_a!r}  <->  {p.name_b!r}")

print("\n[4/4] Diagnostic: ambiguous string band (0.85-0.87) under embeddings...")
band = [p for p in string_pairs if p.score <= 0.87]
cos = score_name_pairs([(p.name_a, p.name_b) for p in band])
ranked = sorted(zip(band, cos), key=lambda t: -t[1])
print(f"      {len(band)} string pairs in band; embedding spread "
      f"{min(cos):.3f} .. {max(cos):.3f}")
for p, c in ranked[:8]:
    print(f"      {c:6.3f}  (str {p.score:.3f})  {p.name_a!r}  <->  {p.name_b!r}")
print("      ...")
for p, c in ranked[-8:]:
    print(f"      {c:6.3f}  (str {p.score:.3f})  {p.name_a!r}  <->  {p.name_b!r}")

SCRATCH_OUT.write_text(
    json.dumps(
        {
            "stage": "embedding_calibration",
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "threshold": None,
            "scored_pair_count": len(scored),
            "pairs": [asdict(p) for p in scored],
            "string_band_diagnostic": [
                {"name_a": p.name_a, "name_b": p.name_b,
                 "string_score": p.score, "cosine": round(c, 4)}
                for p, c in ranked
            ],
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
print(f"\n      full scored list -> {SCRATCH_OUT} (threshold experiments without re-embedding)")

print()
print("=" * 70)
print("[OK] STAGE 2 CALIBRATION RUN COMPLETE - no threshold set, nothing merged")
