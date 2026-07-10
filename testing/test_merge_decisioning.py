#!/usr/bin/env python3
"""Resolution Stage 4 (decisioning): combined candidate pairs -> ResolutionDecision objects -> validation -> Canonical/SAME_AS Cypher preview.

Reads the approved candidate set from examples/expected_output/ (no Neo4j, no embeddings needed). Generates and validates decisions and SHOWS the Cypher — it never executes it; the write is a separate, explicitly approved step."""

import json
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.builders.cypher_builder import build_resolution_cypher
from graph.validators.validator import validate_decisions
from resolution.decisioning.merge_resolver import resolve
from resolution.matchers.string_matcher import CandidatePair

IN_PATH = Path(__file__).parent.parent / "examples" / "expected_output" / "candidate_pairs.json"
OUT_PATH = Path(__file__).parent.parent / "examples" / "expected_output" / "resolution_decisions.json"

print("Resolution Stage 4: merge decisioning (no Neo4j writes)")
print("=" * 70)

print("\n[1/5] Loading combined candidate pairs...")
data = json.loads(IN_PATH.read_text(encoding="utf-8"))
pairs = [
    CandidatePair(**{k: v for k, v in row.items() if k != "matcher"})
    for row in data["pairs"]
]
print(f"      {len(pairs)} pairs over {data['entity_count']} entities")

print("\n[2/5] Resolving clusters (union-find) and deciding...")
decisions = resolve(pairs)
by_action = Counter(d.action for d in decisions)
print(f"      {len(decisions)} decisions: "
      f"{by_action['MERGE']} MERGE, {by_action['TENTATIVE']} TENTATIVE, "
      f"{by_action['NONE']} NONE")

clusters = [d for d in decisions if d.action != "NONE"]
sizes = Counter(len(d.source_ids) for d in clusters)
print("\n      cluster size distribution:")
for size in sorted(sizes):
    print(f"        {size:3d} entities  x {sizes[size]:4d} clusters")
print(f"        largest cluster: {max(sizes)} entities")

split = [d for d in clusters if "cohesion split" in d.reasoning]
clustered_ids = {sid for d in clusters for sid in d.source_ids}
candidate_ids = {i for p in pairs for i in (p.id_a, p.id_b)}
orphans = candidate_ids - clustered_ids
print(f"      cohesion: {len(split)} decisions from split chains, "
      f"{len(orphans)} orphaned entities (fell out of resolution)")

print("\n[3/5] Validating decisions (Rule 3)...")
known_ids = {i for p in pairs for i in (p.id_a, p.id_b)}
result = validate_decisions(decisions, known_entity_ids=known_ids)
print(f"      {len(result.decisions)} valid, {len(result.errors)} errors")
for err in result.errors[:10]:
    print(f"        REJECTED {err.item_id}: {err.reason}")

print("\n[4/5] Resolution metrics (CLAUDE.md deliverable):")
raw = data["entity_count"]
resolved_members = sum(len(d.source_ids) for d in clusters)
canonical_count = raw - resolved_members + len(clusters)
aliases = resolved_members / len(clusters) if clusters else 0
cross = sum(
    1 for d in clusters
    if len({sid.rsplit("__", 1)[-1] for sid in d.source_ids}) > 1
)
print(f"      raw entities:                {raw}")
print(f"      entities in clusters:        {resolved_members} "
      f"({len(clusters)} clusters)")
print(f"      canonical entity count:      {canonical_count} "
      f"({100 * (raw - canonical_count) / raw:.1f}% reduction)")
print(f"      avg aliases per canonical:   {aliases:.2f}")
print(f"      cross-source canonicals:     {cross}")
print(f"      cohesion orphans:            {len(orphans)} "
      f"(chained into a candidate cluster but did not survive "
      f"cohesion partitioning; remain unresolved)")

print("\n[5/5] Writing resolution_decisions.json (decisions only, no graph write)...")
rows = [
    {**asdict(d), "cluster_size": d.cluster_size, "priority_review": d.priority_review}
    for d in result.decisions
]
# priority-review rows first (largest cluster first) so Stage 5 reviewers
# hit the Z. Zhang-style clusters before the long tail of clean pairs
rows.sort(key=lambda r: (
    not r["priority_review"], -r["cluster_size"] if r["priority_review"] else 0,
    r["action"], -r["confidence"], r["canonical_id"],
))
OUT_PATH.write_text(
    json.dumps(
        {
            "stage": "merge_decisioning",
            "rules": "string>0.92 MERGE; string 0.70-0.92 or embedding TENTATIVE; else NONE; cluster gated by weakest edge; cluster cohesion floor 0.85 all-pairs (complete-linkage split of single-linkage chains)",
            "decision_count": len(decisions),
            "by_action": dict(by_action),
            "canonical_entity_count": canonical_count,
            "cohesion_orphans": len(orphans),
            "priority_review_count": sum(1 for r in rows if r["priority_review"]),
            "decisions": rows,
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
print(f"      wrote {OUT_PATH.relative_to(OUT_PATH.parents[2])}")

def show(title: str, ds, n=10):
    print(f"\n{title}")
    for d in ds[:n]:
        srcs = ", ".join(d.source_ids[:3]) + (" ..." if len(d.source_ids) > 3 else "")
        print(f"      {d.confidence:5.3f}  {d.entity_type:<13s} "
              f"{d.canonical_name!r:<40s} <- {len(d.source_ids)} entities [{srcs}]")
        print(f"             {d.reasoning}")

merges = [d for d in result.decisions if d.action == "MERGE"]
tentatives = [d for d in result.decisions if d.action == "TENTATIVE"]
show("Sample: 10 MERGE decisions", merges)
show("Sample: 10 TENTATIVE decisions", tentatives)

mixed = [
    d for d in tentatives
    if {"string", "embedding"} <= {
        "embedding" if "embedding_similarity" in p.matched_by else "string"
        for p in pairs
        if p.id_a in set(d.source_ids) and p.id_b in set(d.source_ids)
    }
]
print(f"\nMixed-matcher clusters (string + embedding evidence): {len(mixed)}")
for d in mixed:
    print(f"      {d.confidence:5.3f}  {d.entity_type:<13s} {d.canonical_name!r} "
          f"<- {len(d.source_ids)} entities")
    print(f"             {d.reasoning}")

now = int(time.time())
print("\n" + "=" * 70)
print("Cypher preview (NOT executed):")
for label, sample in (("MERGE", merges[0]), ("TENTATIVE", tentatives[0])):
    print(f"\n--- {label} example: {sample.canonical_name!r} ---")
    for cypher, params in build_resolution_cypher(sample, decided_at=now):
        print(f"  {cypher}")
        print(f"  params: {json.dumps(params, ensure_ascii=False)}")

print()
print("=" * 70)
print("[OK] STAGE 4 DECISIONING COMPLETE - nothing written to Neo4j")
