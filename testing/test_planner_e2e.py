"""Step 11 core deliverable: end-to-end test of planner/planner.py's plan_and_retrieve() against all 16 questions in the retrieval eval corpus.

graph_seed_id is supplied per question from the eval corpus's own verified evidence (Step 10F) — entity linking from free text is not implemented anywhere in Atlas yet (see planner/planner.py's module docstring), so this script plays that role manually, the same way Step 10E/10F's baseline-vs-fusion comparison did. That is a real, documented scoping boundary, not simulated end-to-end entity resolution.

Q16 is excluded from the per-question loop: it's a structural aggregate question (count of distinct authors across two Papers, comparing a naive vs canonical-aware count) rather than a single get_entity_context() call against one seed id — same treatment as every prior baseline run this session.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from planner.planner import plan_and_retrieve

ROOT = Path(__file__).parent.parent
EVAL_PATH = ROOT / "examples" / "expected_output" / "retrieval_eval_questions.json"

# qid -> (graph_seed_id or None, expected entity ids that count as a correct hit)
GROUND_TRUTH: dict[int, tuple[str | None, list[str]]] = {
    1: ("paper_2003_02320v6_pdf", ["person_claudio_guti_rrez", "person_aidan_hogan__2003_02320v6_pdf"]),
    2: ("person_erik_cambria", ["person_erik_cambria", "person_erik_cambria__2002_00388v4_pdf", "person_e_cambria__2002_00388v4_pdf", "person_erik_cambria__2003_02320v6_pdf"]),
    3: ("paper_2002_00388v4_pdf", ["person_shaoxiong_ji__2002_00388v4_pdf", "person_shirui_pan", "person_erik_cambria", "person_pekka_marttinen", "person_philip_s_yu"]),
    4: ("repo_rdflib_rdflib", ["org_rdf", "org_api"]),
    5: ("org_dbpedia", ["org_dbpedia", "org_dbpedia__2003_02320v6_pdf", "org_dbpedia__2002_00388v4_pdf", "org_dbpedia__rdflib_rdflib"]),
    6: (None, ["org_rdf_data__2003_02320v6_pdf", "org_rdf_reading_rdf", "org_rdf_reading_rdf__rdflib_rdflib"]),
    7: (None, ["person_knowledge_graph__2003_02320v6_pdf", "person_knowledge_graphs"]),
    8: (None, ["chunk_2003_02320v6_pdf_236"]),
    9: (None, ["chunk_rdflib_rdflib_101", "chunk_rdflib_rdflib_386"]),
    10: (None, []),
    11: (None, ["paper_2003_02320v6_pdf"]),
    12: ("person_jos_emilio_labra_gayo", ["person_jos_emilio_labra_gayo"]),
    13: ("org_dbpedia", ["org_dbpedia", "org_complex"]),
    14: ("repo_rdflib_rdflib", []),
    15: (None, ["org_acl", "org_acl__rdflib_rdflib", "org_acl__2003_02320v6_pdf", "org_acl__2002_00388v4_pdf"]),
}


def rank_of(results, expected_ids):
    for i, r in enumerate(results, start=1):
        if r.entity_id in expected_ids:
            return i, r.entity_id
    return None, None


data = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
by_id = {q["id"]: q for q in data["questions"]}

print(f"{'Q':<3} {'routing':<10} {'rank':<6} {'hit_id':<45} question")
print("-" * 130)
for qid, (graph_seed, expected) in GROUND_TRUTH.items():
    question = by_id[qid]["question"]
    routing, results = plan_and_retrieve(question, graph_seed_id=graph_seed)
    rank, hit = rank_of(results, expected)
    print(f"{qid:<3} {routing:<10} {str(rank):<6} {str(hit):<45} {question[:70]}")

print("\nQ16 excluded — structural aggregate question, not a single get_entity_context() call.")
