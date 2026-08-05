"""Step 13F: assembles ExplainedAnswer for a handful of the 16 eval questions, spanning each routing category and both evidence shapes graph_retriever vector_retriever can produce (entity_with_chunk, chunk_is_answer), plus entity_only.

None of the 16 questions cleanly exercise "keyword" as a clean single-strategy category with real (non-empty) results — questions 10/11 are both documented retrieval gaps (architecture.md §12's keyword-coverage findings). A supplementary direct keyword query is included to demonstrate that shape; noted explicitly, not substituted silently for an eval question.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from explainability.explained_answer import assemble_explained_answer
from planner.planner import plan_and_retrieve
from retrieval.keyword_retriever import search_by_keyword
from planner.planner import RoutingResult

CASES = [
    ("Q1 (graph)", "Who authored the 'Knowledge Graphs' survey (2003.02320v6.pdf)?", "paper_2003_02320v6_pdf"),
    ("Q8 (vector_passage)", "How does entity resolution merge duplicate entities?", None),
    ("Q7 (vector_name)", "Find the entity or canonical best matching 'knowledge graph'.", None),
    ("Q12 (hybrid)", "Who is José Emilio Labra Gayo, and is his name affected by the known PDF-encoding issue (architecture.md §12.7)?", "person_jos_emilio_labra_gayo"),
]

for label, question, graph_seed in CASES:
    print(f"=== {label} ===")
    routing = plan_and_retrieve(question, graph_seed_id=graph_seed)
    print(f"routing_decision={routing.category} relationship_type_filtered={routing.relationship_types_filtered} retrievers_invoked={routing.retrievers_invoked}")
    explained = assemble_explained_answer(question, routing)
    if explained is None:
        print("  (no results)")
        print()
        continue
    print(f"  answer: {explained.answer_display_text!r} ({explained.answer_type}, {explained.target_resolution})")
    print(f"  evidence shape: {explained.evidence.shape}")
    if explained.evidence.shape != "entity_only":
        print(f"    chunk_id={explained.evidence.chunk_id} source_title={explained.evidence.source_document_title!r}")
        print(f"    chunk_content_preview={(explained.evidence.chunk_content or '')[:80]!r}")
    print(f"  single_strategy_vs_fused={explained.single_strategy_vs_fused}")
    if explained.per_source_contributions:
        print(f"  per_source_contributions: {len(explained.per_source_contributions)} entries")
    print(f"  confidence: {explained.confidence_score:.4f} via {explained.confidence_method}")
    print(f"  known_limitations: {[(c.section, c.label) for c in explained.known_limitations]}")
    print()

print("=== Supplementary (keyword) ===")
question = "DistMult knowledge graph embedding model"
results = search_by_keyword("DistMult", top_k=8)
routing = RoutingResult("keyword", None, ["keyword"], results)
explained = assemble_explained_answer(question, routing)
if explained is None:
    print("  (no results)")
else:
    print(f"  answer: {explained.answer_display_text!r} ({explained.answer_type}, {explained.target_resolution})")
    print(f"  evidence shape: {explained.evidence.shape}")
    print(f"  confidence: {explained.confidence_score:.4f} via {explained.confidence_method}")
    print(f"  known_limitations: {[(c.section, c.label) for c in explained.known_limitations]}")
