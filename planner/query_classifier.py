"""Deterministic query classifier — Step 11 scoping (investigation only).

classify(question) -> one of "graph", "vector_name", "vector_passage", "keyword", "hybrid". Pattern/keyword matching only, no LLM call, no retriever call — this module does not import retrieval/graph_retriever.py, vector_retriever.py, keyword_retriever.py, or fusion.py at all. Wiring the output to an actual routing/execution layer is the next, separate step (explicitly out of scope here).

Design: each candidate category has a list of regex signals. A question is scored against every category's signals; a category "fires" if any of its signals match.
- Exactly one category fires -> that category.
- Zero or 2+ categories fire -> "hybrid" (deliberate default: no clear single-strategy signal, or genuinely multiple signals present, both mean "don't commit to one retriever" — same operating principle, own framing of hybrid as the fallback between graph-only and vector-only, extended here to include keyword).

This is intentionally blunt where the underlying question is genuinely ambiguous (see the module's test corpus in testing/test_query_classifier.py for the specific cases this trips on) — that ambiguity is the finding this scoping pass exists to surface, not something to regex away.
"""

import re

_FLAGS = re.IGNORECASE

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

# Content/explanation questions — asking what a source *says*, not what it's structurally connected to. "say about"/"discuss"/"explain"/"describe" are the signal; deliberately does NOT include "mention" (that's a _GRAPH_SIGNAL, since MENTIONS is a real edge type in this graph) even though "mention X" and "say about X" are close in everyday English — that's the Q3-shaped ambiguity this classifier is specifically tested against.
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


def classify(question: str) -> str:
    fired = {
        category
        for category, signals in _CATEGORY_SIGNALS.items()
        if any(re.search(pattern, question, _FLAGS) for pattern in signals)
    }
    if len(fired) == 1:
        return next(iter(fired))
    return "hybrid"


def classify_with_signals(question: str) -> tuple[str, set[str]]:
    """Same as classify(), but also returns which categories fired — for reporting/
    debugging why a question landed where it did, not for routing logic."""
    fired = {
        category
        for category, signals in _CATEGORY_SIGNALS.items()
        if any(re.search(pattern, question, _FLAGS) for pattern in signals)
    }
    if len(fired) == 1:
        return next(iter(fired)), fired
    return "hybrid", fired
