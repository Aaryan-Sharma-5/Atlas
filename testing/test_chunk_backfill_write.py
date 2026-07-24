#!/usr/bin/env python3
"""Step 9.5 write: approved Chunk nodes + HAS_CHUNK edges + evidence_chunk_id enrichment -> Neo4j.

Order: full JSON backup of the live graph, constraints, re-validation of the persisted preview output against live entity ids (Rule 3, again, at the write boundary - same pattern as every prior write), MERGE-idempotent write (Chunks + HAS_CHUNK) plus SET-based enrichment (existing AUTHORED_BY/ MENTIONS edges only), then verification. Never modifies existing :Entity/ :Canonical nodes beyond adding evidence_chunk_id to their outgoing edges.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.builders.neo4j_writer import Neo4jWriter
from graph.validators.validator import validate_graph, validate_has_chunk
from models.entity import Entity
from models.relationship import Relationship

ROOT = Path(__file__).parent.parent
INPUT_PATH = ROOT / "examples" / "expected_output" / "chunk_backfill.json"
BACKUP_PATH = ROOT / ".cache" / f"neo4j_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
CONSTRAINTS_PATH = ROOT / "graph" / "schema" / "constraints.cypher"

print("Step 9.5 write: Chunk + HAS_CHUNK + evidence enrichment -> Neo4j")
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
    chunks = [Entity(**row) for row in data["chunks"]]
    has_chunk_rels = [Relationship(**row) for row in data["has_chunk"]]
    evidence_enrichments = data["evidence_enrichments"]

    live_entity_ids = {r["id"] for r in writer.run_read("MATCH (n:Entity) RETURN n.id AS id")}
    live_canonical_ids = {r["id"] for r in writer.run_read("MATCH (c:Canonical) RETURN c.id AS id")}

    chunk_result = validate_graph(chunks)
    print(f"      chunks: {len(chunk_result.entities)} valid, {len(chunk_result.errors)} errors")
    for err in chunk_result.errors[:10]:
        print(f"        REJECTED {err.item_id}: {err.reason}")

    new_chunk_ids = {e.id for e in chunk_result.entities}
    has_chunk_result = validate_has_chunk(
        has_chunk_rels,
        known_entity_ids=live_entity_ids | new_chunk_ids,
        known_canonical_ids=live_canonical_ids,
    )
    print(f"      HAS_CHUNK: {len(has_chunk_result.relationships)} valid, {len(has_chunk_result.errors)} errors")
    for err in has_chunk_result.errors[:10]:
        print(f"        REJECTED {err.item_id}: {err.reason}")

    # Evidence enrichments target already-live AUTHORED_BY/MENTIONS edges, not new nodes/edges - re-validate that both endpoints are still live (defensive; the source/target ids haven't changed since the preview).
    valid_chunk_ids = new_chunk_ids
    enrichment_errors = [
        e for e in evidence_enrichments
        if e["source_id"] not in live_entity_ids
        or (e["target_id"] not in live_entity_ids and e["target_id"] not in live_canonical_ids)
        or e["chunk_id"] not in valid_chunk_ids
    ]
    print(f"      evidence enrichments: {len(evidence_enrichments) - len(enrichment_errors)} valid, {len(enrichment_errors)} errors")

    if chunk_result.errors or has_chunk_result.errors or enrichment_errors:
        sys.exit("      aborting write: validation errors")

    print("\n[4/6] Writing (single transaction, MERGE-idempotent + SET enrichment)...")
    entity_count_before = writer.run_read("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
    canonical_count_before = writer.run_read("MATCH (c:Canonical) RETURN count(c) AS c")[0]["c"]
    written = writer.write_chunk_backfill(chunk_result.entities, has_chunk_result.relationships, evidence_enrichments)
    print(f"      {written['chunk_nodes_written']} Chunk nodes, "
          f"{written['has_chunk_edges_written']} HAS_CHUNK edges, "
          f"{written['evidence_enrichments_written']} evidence enrichments")

    print("\n[5/6] Verifying...")
    chunk_count = writer.run_read("MATCH (n:Chunk) RETURN count(n) AS c")[0]["c"]
    has_chunk_count = writer.run_read("MATCH ()-[r:HAS_CHUNK]->() RETURN count(r) AS c")[0]["c"]
    evidence_count = writer.run_read(
        "MATCH ()-[r]->() WHERE r.evidence_chunk_id IS NOT NULL RETURN count(r) AS c"
    )[0]["c"]
    entity_count_after = writer.run_read("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
    canonical_count_after = writer.run_read("MATCH (c:Canonical) RETURN count(c) AS c")[0]["c"]
    entity_delta = entity_count_after - entity_count_before

    checks = [
        ("Chunk nodes", chunk_count, len(chunk_result.entities)),
        ("HAS_CHUNK edges", has_chunk_count, len(has_chunk_result.relationships)),
        ("edges with evidence_chunk_id", evidence_count, len(evidence_enrichments)),
        (":Canonical nodes unmodified", canonical_count_after, canonical_count_before),
    ]
    ok = True
    for label, got, expected in checks:
        status = "OK " if got == expected else "FAIL"
        ok &= got == expected
        print(f"      [{status}] {label}: {got} (expected {expected})")
    print(f"      :Entity count {entity_count_before} -> {entity_count_after} (delta {entity_delta}, expect {len(chunk_result.entities)} new Chunk nodes)")

    print("\n[6/6] Sample verification: a Chunk node + an enriched edge...")
    sample_chunk = writer.run_read(
        "MATCH (n:Chunk) RETURN n.id AS id, n.chunk_index AS idx, n.source_id AS source_id, "
        "size(n.content) AS content_len LIMIT 1"
    )
    print(f"      {sample_chunk}")
    sample_edge = writer.run_read(
        "MATCH (a)-[r]->(b) WHERE r.evidence_chunk_id IS NOT NULL "
        "RETURN a.id AS source, type(r) AS type, b.id AS target, r.evidence_chunk_id AS chunk_id LIMIT 1"
    )
    print(f"      {sample_edge}")

print()
print("=" * 70)
print("[OK] STEP 9.5 WRITE COMPLETE" if ok else "[FAIL] VERIFICATION MISMATCH")
