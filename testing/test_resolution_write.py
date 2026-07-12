#!/usr/bin/env python3
"""Resolution write milestone: approved ResolutionDecisions -> Neo4j.

Order: full JSON backup of the live graph, constraints, re-validation of the decisions against live entity ids (Rule 3, again, at the write boundary), MERGE-idempotent write of :Canonical + :SAME_AS, then verification. Never touches :Entity nodes (Rule 8)."""

import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.builders.neo4j_writer import Neo4jWriter
from graph.validators.validator import validate_decisions
from models.resolution import ResolutionDecision

ROOT = Path(__file__).parent.parent
DECISIONS_PATH = ROOT / "examples" / "expected_output" / "resolution_decisions.json"
CONSTRAINTS_PATH = ROOT / "graph" / "schema" / "constraints.cypher"
BACKUP_PATH = ROOT / ".cache" / f"neo4j_backup_{datetime.now():%Y%m%d_%H%M%S}.json"

print("Resolution write: Canonical + SAME_AS -> Neo4j")
print("=" * 70)

with Neo4jWriter() as writer:
    writer.verify_connectivity()

    print("\n[1/5] Backing up live graph to JSON...")
    nodes = writer.run_read(
        "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props"
    )
    rels = writer.run_read(
        "MATCH (a)-[r]->(b) RETURN a.id AS source, b.id AS target, "
        "type(r) AS type, properties(r) AS props"
    )
    BACKUP_PATH.write_text(
        json.dumps({"nodes": nodes, "relationships": rels}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"      {len(nodes)} nodes, {len(rels)} relationships "
          f"-> {BACKUP_PATH.relative_to(ROOT)} "
          f"({BACKUP_PATH.stat().st_size / 1e6:.1f} MB)")

    print("\n[2/5] Applying constraints (incl. unique_canonical_id)...")
    count = writer.apply_constraints(CONSTRAINTS_PATH)
    print(f"      {count} constraint statements applied")

    print("\n[3/5] Loading + re-validating decisions against live entity ids...")
    data = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    decisions = [
        ResolutionDecision(**{
            k: v for k, v in row.items()
            if k not in ("cluster_size", "priority_review")
        })
        for row in data["decisions"]
    ]
    live_ids = {
        r["id"] for r in writer.run_read("MATCH (n:Entity) RETURN n.id AS id")
    }
    result = validate_decisions(decisions, known_entity_ids=live_ids)
    print(f"      {len(result.decisions)} valid, {len(result.errors)} errors")
    for err in result.errors[:10]:
        print(f"        REJECTED {err.item_id}: {err.reason}")
    if result.errors:
        sys.exit("      aborting write: validation errors")

    print("\n[4/5] Writing (single transaction, MERGE-idempotent)...")
    entity_count_before = writer.run_read(
        "MATCH (n:Entity) RETURN count(n) AS c"
    )[0]["c"]
    decided_at = int(time.time())
    written = writer.write_resolution(result, decided_at=decided_at)
    print(f"      {written['canonical_nodes_written']} canonical nodes, "
          f"{written['same_as_edges_written']} SAME_AS edges")

    print("\n[5/5] Verifying...")
    canonical_count = writer.run_read(
        "MATCH (c:Canonical) RETURN count(c) AS c"
    )[0]["c"]
    edge_count = writer.run_read(
        "MATCH (:Canonical)-[r:SAME_AS]->(:Entity) RETURN count(r) AS c"
    )[0]["c"]
    entity_count_after = writer.run_read(
        "MATCH (n:Entity) RETURN count(n) AS c"
    )[0]["c"]
    by_action = Counter(d.action for d in result.decisions if d.action != "NONE")
    expected_edges = sum(
        len(d.source_ids) for d in result.decisions if d.action != "NONE"
    )
    checks = [
        ("canonical nodes", canonical_count, len(result.decisions)),
        ("SAME_AS edges", edge_count, expected_edges),
        (":Entity nodes untouched", entity_count_after, entity_count_before),
    ]
    ok = True
    for label, got, expected in checks:
        status = "OK " if got == expected else "FAIL"
        ok &= got == expected
        print(f"      [{status}] {label}: {got} (expected {expected})")

    for cid in ("lang_english", "person_z_zhang", "org_santiago_de_chile"):
        rows = writer.run_read(
            "MATCH (c:Canonical {id: $id})-[r:SAME_AS]->(e:Entity) "
            "RETURN c.canonical_name AS name, c.source_count AS sc, "
            "c.confidence AS conf, r.decision_action AS action, "
            "e.name AS member ORDER BY e.id",
            {"id": cid},
        )
        header = rows[0]
        members = [r["member"] for r in rows]
        print(f"\n      {cid}: {header['name']!r} "
              f"[{header['action']}, conf {header['conf']}, "
              f"source_count {header['sc']}, edges {len(rows)}]")
        print(f"        members: {members}")

print()
print("=" * 70)
print(("[OK] RESOLUTION WRITE COMPLETE" if ok else "[FAIL] VERIFICATION MISMATCH")
      + f" - {by_action['MERGE']} MERGE + {by_action['TENTATIVE']} TENTATIVE clusters in graph")
