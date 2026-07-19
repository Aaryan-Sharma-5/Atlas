"""Phase 7A.2a write: approved Markdown/Repository entities + MENTIONS relationships -> Neo4j.

Order: full JSON backup of the live graph, constraints, re-validation of the persisted extraction output against live entity ids (Rule 3, again, at the write boundary — same pattern as test_authored_by_write.py), MERGE-idempotent write, then verification. Never modifies existing :Entity/:Canonical nodes: Markdown/Repository nodes are new, everything else is MATCHed only.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.builders.neo4j_writer import Neo4jWriter
from graph.validators.validator import validate_graph, validate_mentions
from models.entity import Entity
from models.relationship import Relationship

ROOT = Path(__file__).parent.parent
INPUT_PATH = ROOT / "examples" / "expected_output" / "mentions_relationships.json"
BACKUP_PATH = ROOT / ".cache" / f"neo4j_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
CONSTRAINTS_PATH = ROOT / "graph" / "schema" / "constraints.cypher"

print("Phase 7A.2a write: Markdown/Repository + MENTIONS -> Neo4j")
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
    sources = [Entity(**row) for row in data["markdowns"] + data["repositories"]]
    relationships = [Relationship(**row) for row in data["relationships"]]

    live_entity_ids = {r["id"] for r in writer.run_read("MATCH (n:Entity) RETURN n.id AS id")}
    live_canonical_ids = {r["id"] for r in writer.run_read("MATCH (c:Canonical) RETURN c.id AS id")}

    source_result = validate_graph(sources)
    print(f"      source nodes: {len(source_result.entities)} valid, {len(source_result.errors)} errors")
    for err in source_result.errors[:10]:
        print(f"        REJECTED {err.item_id}: {err.reason}")

    # existing_edges intentionally left at its default (in-batch dedup only) — same reasoning as test_authored_by_write.py: MERGE is what makes a re-run of this same approved batch idempotent.
    new_source_ids = {e.id for e in source_result.entities}
    rel_result = validate_mentions(
        relationships,
        known_entity_ids=live_entity_ids | new_source_ids,
        known_canonical_ids=live_canonical_ids,
    )
    print(f"      relationships: {len(rel_result.relationships)} valid, {len(rel_result.errors)} errors")
    for err in rel_result.errors[:10]:
        print(f"        REJECTED {err.item_id}: {err.reason}")

    if source_result.errors or rel_result.errors:
        sys.exit("      aborting write: validation errors")

    print("\n[4/6] Writing (single transaction, MERGE-idempotent)...")
    entity_count_before = writer.run_read("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
    canonical_count_before = writer.run_read("MATCH (c:Canonical) RETURN count(c) AS c")[0]["c"]
    written = writer.write_mentions(source_result.entities, rel_result.relationships)
    print(f"      {written['source_nodes_written']} source nodes, "
          f"{written['mentions_edges_written']} MENTIONS edges")

    print("\n[5/6] Verifying...")
    source_node_count = writer.run_read(
        "MATCH (n) WHERE n:Markdown OR n:Repository RETURN count(n) AS c"
    )[0]["c"]
    edge_count = writer.run_read("MATCH ()-[r:MENTIONS]->() RETURN count(r) AS c")[0]["c"]
    entity_count_after = writer.run_read("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
    canonical_count_after = writer.run_read("MATCH (c:Canonical) RETURN count(c) AS c")[0]["c"]
    entity_delta = entity_count_after - entity_count_before

    checks = [
        ("Markdown/Repository nodes", source_node_count, len(source_result.entities)),
        ("MENTIONS edges", edge_count, len(rel_result.relationships)),
        (":Canonical nodes unmodified", canonical_count_after, canonical_count_before),
    ]
    ok = True
    for label, got, expected in checks:
        status = "OK " if got == expected else "FAIL"
        ok &= got == expected
        print(f"      [{status}] {label}: {got} (expected {expected})")
    print(f"      :Entity count {entity_count_before} -> {entity_count_after} (delta {entity_delta})")

print()
print("=" * 70)
print("[OK] PHASE 7A.2a WRITE COMPLETE" if ok else "[FAIL] VERIFICATION MISMATCH")
