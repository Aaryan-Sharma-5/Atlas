#!/usr/bin/env python3
"""Embedding write (Step 9.5 close-out): applies indexes.cypher for the first time, writes name_embedding (Entity/Canonical) + embedding (Chunk) from the reviewed .cache/embeddings_preview.json, UNWIND-batched. Then verifies index state, node counts, and two vector similarity queries: stored-vector-to-vector (chunk-to-chunk) and fresh-text-to-vector (the actual retrieval pattern Step 10 will use).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.builders.neo4j_writer import Neo4jWriter
from resolution.matchers.embedding_matcher import embed_names

ROOT = Path(__file__).parent.parent
INPUT_PATH = ROOT / ".cache" / "embeddings_preview.json"
BACKUP_PATH = ROOT / ".cache" / f"neo4j_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
CONSTRAINTS_PATH = ROOT / "graph" / "schema" / "constraints.cypher"
INDEXES_PATH = ROOT / "graph" / "schema" / "indexes.cypher"

print("Embedding write: name_embedding + embedding + indexes -> Neo4j")
print("=" * 70)

with Neo4jWriter() as writer:
    writer.verify_connectivity()

    print("\n[1/7] Backing up live graph to JSON...")
    nodes = writer.run_read("MATCH (n) RETURN labels(n) AS labels, properties(n) AS props")
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

    print("\n[2/7] Applying constraints.cypher + indexes.cypher (first real application)...")
    c_count = writer.apply_constraints(CONSTRAINTS_PATH)
    i_count = writer.apply_constraints(INDEXES_PATH)
    print(f"      {c_count} constraint statements, {i_count} index statements applied")

    print("\n[3/7] Loading reviewed embeddings...")
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    entity_rows = [{"id": r["id"], "embedding": r["name_embedding"]} for r in data["entities"]]
    canonical_rows = [{"id": r["id"], "embedding": r["name_embedding"]} for r in data["canonicals"]]
    chunk_rows = [{"id": r["id"], "embedding": r["embedding"]} for r in data["chunks"]]
    print(f"      entities: {len(entity_rows)}, canonicals: {len(canonical_rows)}, chunks: {len(chunk_rows)}")

    print("\n[4/7] Writing (single transaction, 3 UNWIND-batched SETs)...")
    written = writer.write_embeddings(entity_rows, canonical_rows, chunk_rows)
    print(f"      {written}")

    print("\n[5/7] Verifying index state...")
    indexes = writer.run_read(
        "SHOW INDEXES YIELD name, type, state RETURN name, type, state ORDER BY name"
    )
    all_online = all(i["state"] == "ONLINE" for i in indexes)
    vector_count = sum(1 for i in indexes if i["type"] == "VECTOR")
    for i in indexes:
        print(f"      {i['name']}: {i['type']} [{i['state']}]")
    print(f"      {'[OK ]' if all_online else '[FAIL]'} all {len(indexes)} indexes ONLINE "
          f"({vector_count} VECTOR, expected 3)")

    print("\n[6/7] Verifying node counts...")
    entity_emb_count = writer.run_read(
        "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN count(n) AS c"
    )[0]["c"]
    canonical_emb_count = writer.run_read(
        "MATCH (c:Canonical) WHERE c.name_embedding IS NOT NULL RETURN count(c) AS c"
    )[0]["c"]
    chunk_emb_count = writer.run_read(
        "MATCH (n:Chunk) WHERE n.embedding IS NOT NULL RETURN count(n) AS c"
    )[0]["c"]
    entity_total = writer.run_read("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
    canonical_total = writer.run_read("MATCH (c:Canonical) RETURN count(c) AS c")[0]["c"]

    checks = [
        ("Entity.name_embedding set", entity_emb_count, 4486),
        ("Canonical.name_embedding set", canonical_emb_count, 329),
        ("Chunk.embedding set", chunk_emb_count, 3056),
    ]
    ok = True
    for label, got, expected in checks:
        status = "OK " if got == expected else "FAIL"
        ok &= got == expected
        print(f"      [{status}] {label}: {got} (expected {expected})")
    print(f"      :Entity total: {entity_total} | :Canonical total: {canonical_total} (unchanged from before write)")

    print("\n[7/7] Vector similarity checks...")
    print("  -- stored-vector query: chunk-to-chunk --")
    seed = writer.run_read(
        "MATCH (n:Chunk {id: 'chunk_2003_02320v6_pdf_0'}) RETURN n.embedding AS v"
    )[0]["v"]
    neighbors = writer.run_read(
        "CALL db.index.vector.queryNodes('chunk_embedding', 5, $v) "
        "YIELD node, score RETURN node.id AS id, score",
        {"v": seed},
    )
    for row in neighbors:
        print(f"      {row['id']}: {row['score']:.4f}")

    print("\n  -- fresh-text query: NOT a stored node's vector (actual Step 10 retrieval pattern) --")
    query_text = "knowledge graph embeddings and representation learning"
    query_vector = embed_names([query_text])[0].tolist()
    fresh_neighbors = writer.run_read(
        "CALL db.index.vector.queryNodes('chunk_embedding', 5, $v) "
        "YIELD node, score RETURN node.id AS id, node.content AS content, score",
        {"v": query_vector},
    )
    print(f"      query: {query_text!r}")
    for row in fresh_neighbors:
        preview = row["content"][:100].replace("\n", " ")
        print(f"      {row['id']} ({row['score']:.4f}): {preview}...")

print()
print("=" * 70)
print("[OK] EMBEDDING WRITE COMPLETE" if ok else "[FAIL] VERIFICATION MISMATCH")
