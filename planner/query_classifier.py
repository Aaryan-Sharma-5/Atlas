"""Deterministic query classifier — Step 11 scoping (investigation only).

classify(question) -> one of "graph", "vector_name", "vector_passage", "keyword", "hybrid". Pattern/keyword matching only, no LLM call, no retriever call — this module does not import retrieval/graph_retriever.py, vector_retriever.py, keyword_retriever.py, or fusion.py at all. Wiring the output to an actual routing/execution layer is the next, separate step (explicitly out of scope here).

Design: each candidate category has a list of regex signals. A question is scored against every category's signals; a category "fires" if any of its signals match. Escalates to "hybrid" (does not commit to a single retriever) when:
  (a) zero categories fire — no clear single-strategy signal, or
  (b) two or more categories fire — genuinely multiple signals present, or
  (c) exactly one category fires, but the matched text itself is a known graph-technical/conversational-English overload (AMBIGUOUS_TERMS below) — an otherwise-clean single-signal match is still not trustworthy on its own, or
  (d) the question is structurally compound — a comma followed by "and how/is/are/does/do/what/which" (COMPOUND_QUESTION_SIGNALS below) — regardless of what a single category matched elsewhere in the sentence.

Rule (c) exists because of a specific, reproducible probe found during scoping: "What does the rdflib repository mention about RDF?" classifies as a clean single- signal "graph" match (fires only on "mention"), but the asker plausibly meant "what does rdflib's text/docs discuss about RDF" (vector_passage, content-level), not "does a MENTIONS edge exist" (graph, structural). "mention"/"mentions" is simultaneously this graph's literal edge-type name and an everyday English verb for "discuss/reference in passing" — a regex can match the word, it cannot tell which sense the asker meant. Escalating on this term specifically, even without a second category firing, is the fix; broadening or narrowing the pattern itself would not be (it would just move which exact phrasings get misread, not resolve the ambiguity).

Rule (d) exists because of a real routing failure, not just a lower rank: "Which technology/organization names appear across more than one corpus source, and how does resolution treat them?" (eval question 13) matched only _VECTOR_PASSAGE_SIGNALS ("how does"), so it routed to vector_passage alone — which only ever returns Chunk results, guaranteeing a miss for a question whose real answer is an Entity/Canonical (org_dbpedia/org_complex). Widening _VECTOR_PASSAGE_SIGNALS' "how does" pattern itself was considered and rejected: that pattern is also what correctly catches eval question 8 ("How does entity resolution merge duplicate entities?", a genuine single-clause vector_passage question with no second clause). The two differ structurally, not lexically: Q13 is two questions stitched together with ", and how does" — a second WH-clause after a comma; Q8 is one question, "How does" at the very start of the sentence. Detecting the comma-plus-second-clause shape instead of touching the "how does" pattern fixes Q13 without narrowing or broadening what "how does" itself matches, so Q8 is unaffected (verified: still fires vector_passage only, no compound-clause comma present).
"""

import re

_FLAGS = re.IGNORECASE

# Terms that carry both a precise graph-technical meaning (a real relationship type in this corpus's schema) and a vague conversational meaning, such that matching the word alone is not sufficient evidence of intent. Extend this set if further scoping turns up more (checked "depend"/"dependency" and "same" while building this list — neither showed the same ambiguity in practice: "depends on" reliably signals the DEPENDS_ON/USES relationship shape with no common conversational rival meaning in this corpus's question style, and "same as"/"same entity" likewise has no competing everyday sense). Only "mention"/"mentions" showed a real collision.
AMBIGUOUS_TERMS = {"mention", "mentions"}
_AMBIGUOUS_TERMS_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in AMBIGUOUS_TERMS) + r")\b", _FLAGS
)

# Structural compound-question marker: a comma directly followed by a second WH-question or auxiliary-led clause ("...X, and how does Y", "...X, and is Y"). Deliberately keyed on sentence structure (comma + "and " + question-starter), not on any specific verb, so it doesn't compete with or narrow _VECTOR_PASSAGE_SIGNALS' "how does" — see module docstring, rule (d), for the eval question 13 vs. 8 case this distinguishes.
_COMPOUND_QUESTION_SIGNALS = [
    r",\s*and (how|is|are|does|do|what|which)\b",
]

# Specific relationship-type language — the literal edge types this corpus's graph actually has (AUTHORED_BY, MENTIONS, SAME_AS) or structural graph concepts (aggregation across SAME_AS, distinct-entity counting). Deliberately NOT triggered by the bare word "canonical" alone — Q6/Q7 in this corpus's eval set both say "canonical" while describing a vector-search *result type*, not asking a structural graph question; a bare keyword match there would misclassify two real vector questions as graph. Requires the more specific aggregation/count/relationship phrasing.
_GRAPH_SIGNALS = [
    r"\bwho authored\b",
    r"\bauthored by\b",
    r"\bwho wrote\b",
    r"\bwhat does .{1,60}\bmentions?\b",
    r"\bmentions? (the )?most\b",
    r"\bmost (frequently )?mentions?\b",
    r"\bdepends? on\b",
    r"\bdependenc(y|ies)\b",
    r"\bsame entity\b",
    r"\bsame as\b",
    r"\bis .{1,60}\bthe same\b",
    r"\baggregat\w*\b",
    r"\braw (name )?variants?\b",
    r"\bhow many distinct\b",
    r"\brelationship(s)? between\b",
    r"\bconnected to\b",
]

# Explicit exact-string / identifier lookups — quoted literals or id-shaped tokens.
_KEYWORD_SIGNALS = [
    r'"[^"]{1,80}"',
    r"\bliteral string\b",
    r"\bexact(ly)? match(es)?\b",
    r"\bcontains? the (literal )?string\b",
    r"\barxiv id\b",
    r"\b\d{4}\.\d{4,5}\b",
]

# Short-text name-similarity — "find X similar/matching to <name>", not a relationship question and not a full-sentence content question.
_VECTOR_NAME_SIGNALS = [
    r"\bsimilar to\b",
    r"\bclosest match\b",
    r"\bclosest to\b",
    r"\bbest matching\b",
    r"\bname.{0,20}\bmatching\b",
]

# Content/explanation questions — asking what a source *says*, not what it's structurally connected to. Deliberately does NOT include "mention" (that's a _GRAPH_SIGNAL, since MENTIONS is a real edge type in this graph) even though "mention X" and "say about X" are close in everyday English — see AMBIGUOUS_TERMS and the module docstring for how that specific collision is handled instead.
_VECTOR_PASSAGE_SIGNALS = [
    r"\bhow do i\b",
    r"\bhow does\b",
    r"\bsay about\b",
    r"\btalks? about\b",
    r"\bdiscuss(es)?\b",
    r"\bexplain(s)?\b",
    r"\bdescribe(s)?\b",
    r"\bwhat does .{1,60}\bsay\b",
]

_CATEGORY_SIGNALS = {
    "graph": _GRAPH_SIGNALS,
    "keyword": _KEYWORD_SIGNALS,
    "vector_name": _VECTOR_NAME_SIGNALS,
    "vector_passage": _VECTOR_PASSAGE_SIGNALS,
}


def _matches_by_category(question: str) -> dict[str, list[str]]:
    """category -> list of matched substrings (not just whether it fired) - needed for escalation rule (c), which inspects the matched text itself, not just the category name."""
    matches: dict[str, list[str]] = {}
    for category, signals in _CATEGORY_SIGNALS.items():
        found = [
            m.group(0)
            for pattern in signals
            for m in re.finditer(pattern, question, _FLAGS)
        ]
        if found:
            matches[category] = found
    return matches


def classify(question: str) -> str:
    return classify_with_signals(question)[0]


def classify_with_signals(question: str) -> tuple[str, set[str]]:
    """Returns (category, fired_categories) — fired_categories is for reporting/ debugging why a question landed where it did, not for routing logic. category is "hybrid" whenever escalation rule (a), (b), (c), or (d) applies (see module docstring).
    """
    matches = _matches_by_category(question)
    fired = set(matches)

    if len(fired) != 1:
        return "hybrid", fired

    if any(re.search(pattern, question, _FLAGS) for pattern in _COMPOUND_QUESTION_SIGNALS):
        return "hybrid", fired

    only_category = next(iter(fired))
    if any(_AMBIGUOUS_TERMS_PATTERN.search(text) for text in matches[only_category]):
        return "hybrid", fired

    return only_category, fired
