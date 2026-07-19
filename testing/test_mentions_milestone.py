"""Regression check for 7A.2a MENTIONS: aggregates + a fixed sample, not a full diff.

4,224 edges is too many to enumerate and exact-match every run (any resolution re-run could legitimately shift a handful of raw-Entity targets to a new Canonical without anything being "wrong"), so this checks the totals/breakdowns plus one fixed, deterministically-ordered sample of 20 (source, target, frequency) triples — same spirit as the AUTHORED_BY milestone check, scaled for a collection this size. If MENTIONS extraction legitimately changes, the snapshot must be regenerated deliberately, not silently overwritten here.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.builders.neo4j_writer import Neo4jWriter

ROOT = Path(__file__).parent.parent
SNAPSHOT_PATH = ROOT / "examples" / "expected_output" / "mentions_milestone_query.json"

TOTAL_Q = "MATCH ()-[r:MENTIONS]->() RETURN count(r) AS c"
TARGET_TYPE_Q = (
    "MATCH ()-[r:MENTIONS]->(t) "
    "RETURN [l IN labels(t) WHERE l IN ['Person','Organization','Technology','Language']][0] AS type, count(r) AS c "
    "ORDER BY type"
)
SOURCE_TYPE_Q = (
    "MATCH (s)-[r:MENTIONS]->() "
    "RETURN [l IN labels(s) WHERE l IN ['Paper','Markdown','Repository']][0] AS type, count(r) AS c "
    "ORDER BY type"
)
SAMPLE_Q = (
    "MATCH (s)-[r:MENTIONS]->(t) "
    "RETURN s.id AS source, t.id AS target, r.frequency AS frequency "
    "ORDER BY source, target "
    "LIMIT 20"
)

with Neo4jWriter() as writer:
    live = {
        "total_mentions": writer.run_read(TOTAL_Q)[0]["c"],
        "by_target_type": {r["type"]: r["c"] for r in writer.run_read(TARGET_TYPE_Q)},
        "by_source_type": {r["type"]: r["c"] for r in writer.run_read(SOURCE_TYPE_Q)},
        "fixed_sample": writer.run_read(SAMPLE_Q),
    }

snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

assert live["total_mentions"] == snapshot["total_mentions"], (
    f"total drifted: live={live['total_mentions']} snapshot={snapshot['total_mentions']}"
)
assert live["by_target_type"] == snapshot["by_target_type"], (
    f"target-type breakdown drifted: live={live['by_target_type']!r} snapshot={snapshot['by_target_type']!r}"
)
assert live["by_source_type"] == snapshot["by_source_type"], (
    f"source-type breakdown drifted: live={live['by_source_type']!r} snapshot={snapshot['by_source_type']!r}"
)
assert live["fixed_sample"] == snapshot["fixed_sample"], (
    f"fixed sample drifted: live={live['fixed_sample']!r} snapshot={snapshot['fixed_sample']!r}"
)

print(f"[OK] MENTIONS aggregates + fixed sample match snapshot "
      f"({live['total_mentions']} total edges, {len(live['fixed_sample'])}-row sample)")
