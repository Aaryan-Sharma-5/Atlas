"""Step 11 scoping: scores the deterministic query classifier (planner/query_classifier.py) against the 16-question retrieval eval corpus, plus a handful of Q3-shaped ambiguity probes not in that corpus. Investigation only — no routing/execution, no retriever calls. 

Not a pass/fail regression gate: classifier accuracy against this corpus is the deliverable itself (see docs/architecture.md's Step 11 scoping notes for the resulting recommendation), so this prints a report rather than asserting a fixed score.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from planner.query_classifier import classify_with_signals

ROOT = Path(__file__).parent.parent
EVAL_PATH = ROOT / "examples" / "expected_output" / "retrieval_eval_questions.json"

# retrieval_eval_questions.json's retrieval_type values -> the classifier's output vocabulary. keyword_vs_vector_name (Q15) and graph_target_resolution_dependent (Q16) are the two eval-corpus-specific labels from Step 10F that don't literally match a classifier category name.
TYPE_MAP = {
    "graph": "graph",
    "vector_name": "vector_name",
    "vector_passage": "vector_passage",
    "keyword": "keyword",
    "hybrid": "hybrid",
    "keyword_vs_vector_name": "hybrid",
    "graph_target_resolution_dependent": "graph",
}

AMBIGUITY_PROBES = [
    ("Who authored the Ji et al. 2020 survey?", "graph"),
    ("What does the Ji et al. survey say about knowledge graph embeddings?", "vector_passage"),
    ("What does the rdflib repository mention about RDF?", None),  # genuinely ambiguous, no fixed expectation
    ("What does the rdflib repository say about installation?", "vector_passage"),
    ("Does the Ji et al. survey discuss ComplEx?", "vector_passage"),
]

data = json.loads(EVAL_PATH.read_text(encoding="utf-8"))

print(f"{'Q':<3} {'expected':<16} {'predicted':<16} {'ok':<4} question")
print("-" * 120)
correct = 0
for q in data["questions"]:
    expected = TYPE_MAP[q["retrieval_type"]]
    predicted, _fired = classify_with_signals(q["question"])
    ok = predicted == expected
    correct += ok
    print(f"{q['id']:<3} {expected:<16} {predicted:<16} {'YES' if ok else 'NO':<4} {q['question'][:70]}")

total = len(data["questions"])
print(f"\nAccuracy: {correct}/{total} = {correct / total:.1%}")

print("\n=== Ambiguity probes (not in eval corpus) ===")
for question, expected in AMBIGUITY_PROBES:
    predicted, fired = classify_with_signals(question)
    note = "" if expected is None else (" OK" if predicted == expected else " MISMATCH")
    print(f"  {predicted:<16}{note:<10} (fired: {sorted(fired) or 'none'}) <- {question}")
