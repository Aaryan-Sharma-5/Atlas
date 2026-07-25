#!/usr/bin/env python3
"""Embedding generation (Step 9.5 follow-up): name_embedding for Entity/ Canonical, embedding for Chunk. Preview only - computes and times the real batches, previews the Cypher, does NOT write to Neo4j and does NOT apply indexes.cypher yet (both pending review, same checkpoint discipline as every prior write).

Reuses resolution/matchers/embedding_matcher.py's embed_names() (same all-MiniLM-L6-v2 dependency, same L2-normalized-for-cosine convention Stage 2 already established) rather than writing a second encoder path.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from graph.builders.cypher_builder import build_embedding_cypher
from graph.builders.neo4j_writer import Neo4jWriter
from resolution.matchers.embedding_matcher import embed_names

ROOT = Path(__file__).parent.parent
OUTPUT_PATH = ROOT / ".cache" / "embeddings_preview.json"

print("Embedding generation preview (no Neo4j writes)")
print("=" * 70)

print("\n[1/5] Checking index definitions...")
with Neo4jWriter() as writer:
    indexes = writer.run_read(
        "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, state RETURN *"
    )
vector_indexes = [i for i in indexes if i["type"] == "VECTOR"]
print(f"      {len(vector_indexes)} VECTOR indexes currently exist (expect 0 - "
      f"indexes.cypher was written but never applied, confirmed this session)")
for i in indexes:
    print(f"        {i['name']}: {i['type']} on {i['labelsOrTypes']}.{i['properties']} [{i['state']}]")

print("\n[2/5] Fetching text to embed from live Neo4j (read-only)...")
with Neo4jWriter() as writer:
    entity_rows = writer.run_read(
        "MATCH (n:Entity) WHERE NOT n:Chunk RETURN n.id AS id, n.name AS name"
    )
    canonical_rows = writer.run_read(
        "MATCH (c:Canonical) RETURN c.id AS id, c.canonical_name AS name"
    )
    chunk_rows = writer.run_read(
        "MATCH (n:Chunk) RETURN n.id AS id, n.content AS content"
    )
print(f"      Entity (excl. Chunk): {len(entity_rows)}")
print(f"      Canonical: {len(canonical_rows)}")
print(f"      Chunk: {len(chunk_rows)}")
print(f"      Total texts to embed: {len(entity_rows) + len(canonical_rows) + len(chunk_rows)}")

print("\n[3/5] Computing embeddings (timed, real wall-clock)...")
t0 = time.perf_counter()
entity_vectors = embed_names([r["name"] for r in entity_rows])
t1 = time.perf_counter()
print(f"      Entity name_embedding:    {len(entity_rows):5d} texts in {t1 - t0:6.1f}s "
      f"({(t1 - t0) / len(entity_rows) * 1000:.1f} ms/text)")

canonical_vectors = embed_names([r["name"] for r in canonical_rows])
t2 = time.perf_counter()
print(f"      Canonical name_embedding: {len(canonical_rows):5d} texts in {t2 - t1:6.1f}s "
      f"({(t2 - t1) / len(canonical_rows) * 1000:.1f} ms/text)")

chunk_vectors = embed_names([r["content"] for r in chunk_rows])
t3 = time.perf_counter()
print(f"      Chunk embedding:          {len(chunk_rows):5d} texts in {t3 - t2:6.1f}s "
      f"({(t3 - t2) / len(chunk_rows) * 1000:.1f} ms/text)")

total_texts = len(entity_rows) + len(canonical_rows) + len(chunk_rows)
print(f"\n      TOTAL: {total_texts} texts in {t3 - t0:.1f}s wall-clock "
      f"({(t3 - t0) / total_texts * 1000:.1f} ms/text average)")

print("\n[4/5] Cypher preview (NOT executed)...")
ex_id, ex_vec = entity_rows[0]["id"], entity_vectors[0]
cypher, params = build_embedding_cypher(ex_id, "name_embedding", ex_vec.tolist())
print("  -- Entity name_embedding --")
print(f"  {cypher}")
print(f"  params: {{'id': {params['id']!r}, 'embedding': <{len(params['embedding'])} floats, "
      f"e.g. {[round(x, 4) for x in params['embedding'][:4]]}...>}}")

ex_id, ex_vec = canonical_rows[0]["id"], canonical_vectors[0]
cypher, params = build_embedding_cypher(ex_id, "name_embedding", ex_vec.tolist())
print("\n  -- Canonical name_embedding --")
print(f"  {cypher}")
print(f"  params: {{'id': {params['id']!r}, 'embedding': <{len(params['embedding'])} floats>}}")

ex_id, ex_vec = chunk_rows[0]["id"], chunk_vectors[0]
cypher, params = build_embedding_cypher(ex_id, "embedding", ex_vec.tolist())
print("\n  -- Chunk embedding --")
print(f"  {cypher}")
print(f"  params: {{'id': {params['id']!r}, 'embedding': <{len(params['embedding'])} floats>}}")

print("\n[5/5] Writing embeddings_preview.json to .cache/ (gitignored - large numeric "
      "data, not a corpus fixture, not committed)...")
payload = {
    "entities": [
        {"id": r["id"], "name_embedding": [round(float(x), 6) for x in vec]}
        for r, vec in zip(entity_rows, entity_vectors)
    ],
    "canonicals": [
        {"id": r["id"], "name_embedding": [round(float(x), 6) for x in vec]}
        for r, vec in zip(canonical_rows, canonical_vectors)
    ],
    "chunks": [
        {"id": r["id"], "embedding": [round(float(x), 6) for x in vec]}
        for r, vec in zip(chunk_rows, chunk_vectors)
    ],
}
OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
print(f"      wrote {OUTPUT_PATH.relative_to(ROOT)} ({OUTPUT_PATH.stat().st_size / 1e6:.1f} MB)")

print()
print("=" * 70)
print(f"[OK] EMBEDDING GENERATION PREVIEW COMPLETE - {total_texts} texts embedded in {t3 - t0:.1f}s, "
      "nothing written to Neo4j, indexes.cypher not yet applied")
