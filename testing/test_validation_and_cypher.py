"""Validator rejection cases + parameterized Cypher generation. No Neo4j connection is opened."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from ingestion.pdf_parser import extract_pdf_metadata
from ingestion.chunker import chunk_text
from extraction.entity_extractor import extract_entities
from extraction.entity_converter import convert_raw_entities
from models.entity import Entity
from models.relationship import Relationship
from graph.validators.validator import validate_graph
from graph.builders.cypher_builder import (
    build_entity_batch_cypher,
    build_entity_cypher,
    build_relationship_cypher,
)

PROV = {"extraction_source": "test", "extraction_method": "manual"}

print("Day 6: validation + Cypher generation")
print("=" * 70)

# --- Part 1: validator must reject each category of bad input ---------
print("\nPart 1: Validator rejection cases (synthetic bad input)...")

good_a = Entity(id="person_ada", type="Person", name="Ada Lovelace", confidence=0.9, **PROV)
good_b = Entity(id="org_acm", type="Organization", name="ACM", confidence=0.8, **PROV)

bad_cases = [
    ("duplicate id", Entity(id="person_ada", type="Person", name="Ada Clone", confidence=0.9, **PROV)),
    ("confidence > 1", Entity(id="person_high", type="Person", name="X", confidence=1.5, **PROV)),
    ("negative confidence", Entity(id="person_neg", type="Person", name="Y", confidence=-0.1, **PROV)),
    ("missing provenance", Entity(id="person_noprov", type="Person", name="Z", confidence=0.5, extraction_source="", extraction_method="")),
    ("missing name", Entity(id="person_noname", type="Person", name="", confidence=0.5, **PROV)),
]

bad_rels = [
    ("invalid rel type", Relationship(source_id="person_ada", target_id="org_acm", type="TOTALLY_MADE_UP", confidence=0.9, **PROV)),
    ("orphan target", Relationship(source_id="person_ada", target_id="org_ghost",type="AFFILIATED_WITH", confidence=0.9, **PROV)),
    ("rel bad confidence", Relationship(source_id="person_ada", target_id="org_acm", type="AFFILIATED_WITH", confidence=2.0, **PROV)),
]
good_rel = Relationship(source_id="person_ada", target_id="org_acm", type="AFFILIATED_WITH", confidence=0.85, **PROV, properties={"role": "member"})

result = validate_graph(
    [good_a, good_b] + [e for _, e in bad_cases],
    [good_rel] + [r for _, r in bad_rels],
)

print(f"     Input:  {2 + len(bad_cases)} entities, {1 + len(bad_rels)} relationships")
print(f"     Passed: {len(result.entities)} entities, {len(result.relationships)} relationships")
print(f"     Errors: {len(result.errors)}")
for err in result.errors:
    print(f"       - {err.item_id}: {err.reason}")

assert len(result.entities) == 2, "expected exactly the 2 good entities"
assert len(result.relationships) == 1, "expected exactly the 1 good relationship"
assert len(result.errors) >= len(bad_cases) + len(bad_rels)
print("[OK] Every bad-input category rejected; good input passed")

# --- Part 2: validate the real corpus ---------------------------------
print("\nPart 2: Validating the real corpus (Knowledge Graphs paper)...")
pdf_path = Path(__file__).parent.parent / "examples" / "2003.02320v6.pdf"
metadata = extract_pdf_metadata(pdf_path)
chunks = chunk_text(metadata.text, source_file=pdf_path.name)
raw = extract_entities(chunks)
entities, _ = convert_raw_entities(raw, extraction_source=f"pdf:{pdf_path.name}")

corpus_result = validate_graph(entities)
print(f"     {len(entities)} entities in -> {len(corpus_result.entities)} valid, "
      f"{len(corpus_result.errors)} errors")
assert corpus_result.ok, f"corpus should validate cleanly: {corpus_result.errors[:5]}"
print("[OK] Full corpus passes validation")

# --- Part 3: Cypher generation ----------------------------------------
print("\nPart 3: Parameterized Cypher generation (no execution)...")

sample = next(e for e in corpus_result.entities if e.properties.get("aliases"))
cypher, params = build_entity_cypher(sample)
print("\nSingle entity statement:")
print(f"     {cypher}")
print("     params:")
print("     " + json.dumps(params, indent=2, ensure_ascii=False).replace("\n", "\n     "))

rel_cypher, rel_params = build_relationship_cypher(good_rel)
print("\nRelationship statement:")
print(f"     {rel_cypher}")
print(f"     params: {json.dumps(rel_params, ensure_ascii=False)}")

batch = build_entity_batch_cypher(corpus_result.entities)
print(f"\nBatch statements for full corpus: {len(batch)} (one per node type)")
for stmt, batch_params in batch:
    print(f"     {stmt}   <- {len(batch_params['rows'])} rows")

# Prove parameterization: no entity name may appear in any Cypher string.
for stmt, _ in [(cypher, params), (rel_cypher, rel_params)] + batch:
    assert sample.name not in stmt and "Ada" not in stmt
print("\n[OK] No values embedded in Cypher text - everything travels as $params")

print()
print("=" * 70)
print("[OK] Test PASSED (validator + builder ready, Neo4j untouched)")
