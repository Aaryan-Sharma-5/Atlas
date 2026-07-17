#!/usr/bin/env python3
"""Regression check for the 7A.1 AUTHORED_BY milestone query.

Reruns the query live against Neo4j and diffs against the frozen snapshot in examples/expected_output/ — same pattern as the rest of the corpus. If AUTHORED_BY extraction legitimately changes, the snapshot must be regenerated deliberately, not silently overwritten here.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.builders.neo4j_writer import Neo4jWriter

ROOT = Path(__file__).parent.parent
SNAPSHOT_PATH = ROOT / "examples" / "expected_output" / "authored_by_milestone_query.json"

QUERY = (
    "MATCH (p:Paper)-[:AUTHORED_BY]->(a) "
    "WITH p, coalesce(a.canonical_name, a.name) AS author "
    "ORDER BY author "
    "RETURN p.name AS paper, collect(author) AS authors "
    "ORDER BY paper"
)

with Neo4jWriter() as writer:
    live = writer.run_read(QUERY)

snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

assert live == snapshot, f"AUTHORED_BY milestone query drifted from snapshot: live={live!r} != snapshot={snapshot!r}"

print(f"[OK] AUTHORED_BY milestone query matches snapshot ({len(live)} papers)")
