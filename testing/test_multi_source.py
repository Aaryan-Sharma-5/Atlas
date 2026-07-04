#!/usr/bin/env python3
"""Multi-source ingestion: two KG surveys + an architecture markdown doc into one graph, each under its own extraction_source, then report entities appearing in multiple sources — the duplicate surface resolution/ merges.

(The rdflib code-domain source is ingested by test_github_ingestion.py.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from ingestion.pdf_parser import extract_pdf_metadata
from ingestion.markdown_parser import parse_markdown
from ingestion.chunker import chunk_text
from extraction.entity_extractor import extract_entities
from extraction.entity_converter import convert_raw_entities
from graph.validators.validator import validate_graph
from graph.builders.neo4j_writer import Neo4jWriter

ROOT = Path(__file__).parent.parent
CONSTRAINTS_PATH = ROOT / "graph" / "schema" / "constraints.cypher"

PDF_SOURCES = [
    ROOT / "examples" / "2003.02320v6.pdf",   # Hogan et al., Knowledge Graphs
    ROOT / "examples" / "2002.00388v4.pdf",   # Ji et al., KG survey
]
MARKDOWN_SOURCES = [
    ROOT / "docs" / "architecture.md",        # Atlas's own architecture doc
]

print("Multi-source ingestion -> one graph")
print("=" * 70)

with Neo4jWriter() as writer:
    writer.verify_connectivity()
    writer.apply_constraints(CONSTRAINTS_PATH)

    def run_source(source: str, text: str, label: str) -> None:
        chunks = chunk_text(text, source_file=label)
        raw = extract_entities(chunks)
        entities, _ = convert_raw_entities(raw, extraction_source=source)
        validated = validate_graph(entities)
        if not validated.ok:
            print(f"[FAIL] {source}: {len(validated.errors)} validation errors")
            sys.exit(1)
        deleted = writer.clear_source(source)
        note = f" (cleared {deleted} on re-run)" if deleted else ""
        counts = writer.write(validated)
        print(f"      {len(chunks)} chunks -> {len(raw)} mentions -> "
              f"{counts['entities_written']} nodes{note}")

    for pdf_path in PDF_SOURCES:
        print(f"\nProcessing {pdf_path.name} (pdf)...")
        metadata = extract_pdf_metadata(pdf_path)
        run_source(f"pdf:{pdf_path.name}", metadata.text, pdf_path.name)

    for md_path in MARKDOWN_SOURCES:
        rel = md_path.relative_to(ROOT).as_posix()
        print(f"\nProcessing {rel} (markdown)...")
        doc = parse_markdown(md_path)
        run_source(f"md:{rel}", doc.text, rel)

    print("\n" + "=" * 70)
    print("Graph state by source:")
    for row in writer.run_read(
        "MATCH (n:Entity) RETURN n.extraction_source AS source, "
        "count(*) AS nodes ORDER BY source"
    ):
        print(f"      {row['source']:30s} {row['nodes']:5d} nodes")

    print("\nEntities appearing in 2+ sources (any type):")
    multi = writer.run_read(
        "MATCH (n:Entity) "
        "WITH toLower(n.name) AS name, "
        "     collect(DISTINCT n.extraction_source) AS sources, "
        "     max(n.confidence) AS conf "
        "WHERE size(sources) >= 2 "
        "RETURN name, size(sources) AS n_sources, conf "
        "ORDER BY n_sources DESC, conf DESC"
    )
    print(f"      {len(multi)} distinct names span multiple sources")
    print("\n      Top 15 by source count + confidence:")
    for row in multi[:15]:
        print(f"        {row['n_sources']} sources  {row['name']}")

print()
print("=" * 70)
print("[OK] MULTI-SOURCE GRAPH BUILT - resolution now has real cross-source "
      "duplicates to merge")
