#!/usr/bin/env python3
"""Resolution Stage 5: quality flagging over the approved decision set. Flags surface risk for human review — nothing is suppressed, nothing is written to Neo4j."""

import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from models.resolution import ResolutionDecision
from resolution.matchers.string_matcher import CandidatePair
from resolution.quality.quality_flagger import flag_decisions

ROOT = Path(__file__).parent.parent
PAIRS_PATH = ROOT / "examples" / "expected_output" / "candidate_pairs.json"
DECISIONS_PATH = ROOT / "examples" / "expected_output" / "resolution_decisions.json"
OUT_PATH = ROOT / "examples" / "expected_output" / "quality_flags.json"

print("Resolution Stage 5: quality flagging (no writes, nothing suppressed)")
print("=" * 70)

print("\n[1/3] Loading decisions and candidate evidence...")
pairs = [
    CandidatePair(**{k: v for k, v in row.items() if k != "matcher"})
    for row in json.loads(PAIRS_PATH.read_text(encoding="utf-8"))["pairs"]
]
decisions = [
    ResolutionDecision(**{
        k: v for k, v in row.items() if k not in ("cluster_size", "priority_review")
    })
    for row in json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))["decisions"]
]
clusters = [d for d in decisions if d.action != "NONE"]
print(f"      {len(decisions)} decisions, {len(pairs)} pairs")

print("\n[2/3] Flagging...")
flags = flag_decisions(decisions, pairs)
by_type = Counter(f.flag_type for f in flags)
flagged_ids = {f.canonical_id for f in flags}
multi = Counter(f.canonical_id for f in flags)
print(f"      {len(flags)} flags on {len(flagged_ids)} of {len(clusters)} canonicals "
      f"({sum(1 for c in multi.values() if c > 1)} carry multiple flags)")
for flag_type, count in by_type.most_common():
    print(f"        {flag_type:24s} {count:4d}")
tentative_unflagged = sum(
    1 for d in clusters
    if d.action == "TENTATIVE" and d.canonical_id not in flagged_ids
)
print(f"      TENTATIVE decisions with no flag: {tentative_unflagged} of "
      f"{sum(1 for d in clusters if d.action == 'TENTATIVE')}")

print("\n[3/3] Writing quality_flags.json...")
OUT_PATH.write_text(
    json.dumps(
        {
            "stage": "quality_flagging",
            "flag_count": len(flags),
            "by_type": dict(by_type),
            "flagged_canonicals": len(flagged_ids),
            "canonical_count": len(clusters),
            "flags": [asdict(f) for f in flags],
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
print(f"      wrote {OUT_PATH.relative_to(ROOT.parent)}")

print("\nSamples per flag type:")
for flag_type in by_type:
    sample = [f for f in flags if f.flag_type == flag_type][:3]
    print(f"\n  {flag_type}:")
    for f in sample:
        print(f"    {f.canonical_id} {f.canonical_name!r} [{f.entity_type}]")
        print(f"      {f.reason}")
        for ev in f.evidence[:3]:
            print(f"      evidence: {ev}")

print()
print("=" * 70)
print("[OK] STAGE 5 FLAGGING COMPLETE - flags recorded, decisions untouched")
