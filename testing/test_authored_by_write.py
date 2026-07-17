#!/usr/bin/env python3
"""Phase 7A.1 write: approved Paper entities + AUTHORED_BY relationships -> Neo4j.

Order: full JSON backup of the live graph, constraints, re-validation of the persisted extraction output against live entity ids (Rule 3, again, at the write boundary - same pattern as test_resolution_write.py), MERGE-idempotent write, then verification. Never modifies existing :Entity/:Canonical nodes (Rule 8 principle extended to relationships): Paper nodes are new, everything else is MATCHed only.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.builders.neo4j_writer import Neo4jWriter
from graph.validators.validator import validate_authored_by, validate_graph
from models.entity import Entity
from models.relationship import Relationship

ROOT = Path(__file__).parent.parent
INPUT_PATH = ROOT / "examples" / "expected_output" / "authored_by_relationships.json"
BACKUP_PATH = ROOT / ".cache" / f"neo4j_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
CONSTRAINTS_PATH = ROOT / "graph" / "schema" / "constraints.cypher"

print("Phase 7A.1 write: Paper + AUTHORED_BY -> Neo4j")
print("=" * 70)

with Neo4jWriter() as writer:
    writer.verify_connectivity()

    print("\n[1/6] Backing up live graph to JSON...")
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

    print("\n[2/6] Applying constraints...")
    count = writer.apply_constraints(CONSTRAINTS_PATH)
    print(f"      {count} constraint statements applied")

    print("\n[3/6] Loading + re-validating against live entity ids...")
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    papers = [Entity(**row) for row in data["papers"]]
    relationships = [Relationship(**row) for row in data["relationships"]]

    live_entity_ids = {r["id"] for r in writer.run_read("MATCH (n:Entity) RETURN n.id AS id")}
    live_canonical_ids = {r["id"] for r in writer.run_read("MATCH (c:Canonical) RETURN c.id AS id")}

    paper_result = validate_graph(papers)
    print(f"      papers: {len(paper_result.entities)} valid, {len(paper_result.errors)} errors")
    for err in paper_result.errors[:10]:
        print(f"        REJECTED {err.item_id}: {err.reason}")

    # existing_edges is intentionally left at its default (in-batch dedup only): the live graph's own AUTHORED_BY edges are NOT fed in here. MERGE at the Cypher layer is what makes re-running this same approved batch idempotent; validation rejecting "already exists" would defeat that and turn every idempotency re-run into a hard failure.
    new_paper_ids = {p.id for p in paper_result.entities}
    rel_result = validate_authored_by(
        relationships,
        known_entity_ids=live_entity_ids | new_paper_ids,
        known_canonical_ids=live_canonical_ids,
    )
    print(f"      relationships: {len(rel_result.relationships)} valid, {len(rel_result.errors)} errors")
    for err in rel_result.errors[:10]:
        print(f"        REJECTED {err.item_id}: {err.reason}")

    if paper_result.errors or rel_result.errors:
        sys.exit("      aborting write: validation errors")

    print("\n[4/6] Writing (single transaction, MERGE-idempotent)...")
    entity_count_before = writer.run_read("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
    canonical_count_before = writer.run_read("MATCH (c:Canonical) RETURN count(c) AS c")[0]["c"]
    written = writer.write_authored_by(paper_result.entities, rel_result.relationships)
    print(f"      {written['paper_nodes_written']} Paper nodes, "
          f"{written['authored_by_edges_written']} AUTHORED_BY edges")

    print("\n[5/6] Verifying...")
    paper_count = writer.run_read("MATCH (n:Paper) RETURN count(n) AS c")[0]["c"]
    edge_count = writer.run_read("MATCH ()-[r:AUTHORED_BY]->() RETURN count(r) AS c")[0]["c"]
    entity_count_after = writer.run_read("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
    canonical_count_after = writer.run_read("MATCH (c:Canonical) RETURN count(c) AS c")[0]["c"]
    entity_delta = entity_count_after - entity_count_before

    checks = [
        ("Paper nodes", paper_count, len(paper_result.entities)),
        ("AUTHORED_BY edges", edge_count, len(rel_result.relationships)),
        (":Canonical nodes unmodified", canonical_count_after, canonical_count_before),
    ]
    ok = True
    for label, got, expected in checks:
        status = "OK " if got == expected else "FAIL"
        ok &= got == expected
        print(f"      [{status}] {label}: {got} (expected {expected})")
    # Informational, not pass/fail: 0 on an idempotent re-run (Papers already exist, MERGE doesn't grow :Entity), == paper_count on the first run.
    print(f"      :Entity count {entity_count_before} -> {entity_count_after} (delta {entity_delta})")

    print("\n[6/6] Milestone query: MATCH (p:Paper)-[:AUTHORED_BY]->(a) "
          "RETURN p.name, collect(author name)")
    rows = writer.run_read(
        "MATCH (p:Paper)-[:AUTHORED_BY]->(a) "
        "RETURN p.name AS paper, collect(coalesce(a.canonical_name, a.name)) AS authors "
        "ORDER BY p.name"
    )
    for row in rows:
        print(f"      {row['paper']!r}")
        print(f"        authors: {row['authors']}")

print()
print("=" * 70)
print("[OK] PHASE 7A.1 WRITE COMPLETE" if ok else "[FAIL] VERIFICATION MISMATCH")
