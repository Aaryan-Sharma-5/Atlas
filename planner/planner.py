"""Query planner routing/execution layer — Step 11 core deliverable.

plan_and_retrieve(question, ...) classifies a question (planner/query_classifier.py) and calls the retriever(s) that classification implies:
- Clean single-strategy categories (graph, vector_name, vector_passage, keyword) call exactly one retriever. Fusion is deliberately NOT invoked for a single source — the Step 10E/10F baseline found RRF fusion actively hurt pure-graph questions (Q1/Q3: cross-agreeing vector/keyword noise buried the correct graph-only answer), so fusing a single source's own ranked list against nothing would only add fusion's overhead for zero benefit.
- "hybrid" (the escalation category — 0 signals, 2+ signals, or a single signal built from an AMBIGUOUS_TERMS match) calls every retriever that can plausibly answer and fuses via retrieval/fusion.py, exactly as built in Step 10E.

Known scoping gap, not papered over: graph routing needs a seed entity id (retrieval/graph_retriever.py's get_entity_context() takes an id, not free text), and nothing in Atlas yet resolves free text ("the Ji et al. survey") to an entity id — that's an entity-linking problem, unbuilt. graph_seed_id must be supplied by the caller when routing touches graph; this function does not guess one.

Found and fixed while end-to-end testing all 16 eval questions: eval question 13 ("technology/organization names...") crashed db.index.fulltext.queryNodes with a Lucene lexer error on the unescaped "/" — retrieval/keyword_retriever.py's search_by_keyword() docstring is explicit that query_text is raw Lucene syntax (by design, e.g. eval question 10's deliberate '"SAME_AS"' exact-phrase search), so escaping belongs here, at the boundary where free-text natural-language questions first meet that Lucene-syntax contract — not in keyword_retriever.py itself, which would break the intentional raw-syntax use case.
"""

import re
from dataclasses import dataclass, field

from models.retrieval_result import RetrievalResult
from planner.query_classifier import classify_with_signals
from retrieval.fusion import reciprocal_rank_fusion
from retrieval.graph_retriever import get_entity_context
from retrieval.keyword_retriever import search_by_keyword
from retrieval.vector_retriever import search_by_name, search_by_passage

_FLAGS = re.IGNORECASE


@dataclass
class RoutingResult:
    """plan_and_retrieve()'s return shape. Step 13A: relationship_types_filtered and retrievers_invoked used to be computed internally and then discarded — a caller had no way to know which relationship type filtered a graph query, or (for hybrid) which retrievers were actually invoked vs. which contributed a surviving result, without re-deriving both themselves. Fixed by carrying them through instead of throwing them away; this is a bug fix, not new design — the values were already being computed either way.
    """

    category: str
    relationship_types_filtered: list[str] | None
    retrievers_invoked: list[str]
    results: list[RetrievalResult] = field(default_factory=list)

_LUCENE_SPECIAL_CHARS = set('+-&|!(){}[]^"~*?:\\/')


def _escape_lucene(text: str) -> str:
    """Free-text question -> safe Lucene query text. Only used on the planner's own calls into search_by_keyword() with a raw natural-language question; direct callers of search_by_keyword() are still expected to hand it real Lucene syntax (unescaped), per that function's own contract."""
    return "".join(f"\\{ch}" if ch in _LUCENE_SPECIAL_CHARS else ch for ch in text)

# Question language -> relationship_types filter for graph-routed queries (Step 10E/10F/12.12a's finding: unfiltered graph queries bury the answer on high-fan-out nodes). Checked in order, first match wins. None means "no implemented relationship type maps cleanly, run unfiltered" — this is not a placeholder to fill in later for every case: "depends on"/"dependency" language has NO implemented type to request. physical.md documents a resource-level "USES" (Repository -> Technology) relationship in prose, but it was never added to models.relationship.RELATIONSHIP_TYPES (confirmed empirically this session — 7A.3 is deferred to Phase 3, architecture.md §12.6). Requesting relationship_types=["USES"] would raise ValueError in get_entity_context(), not just return an empty result, so this mapping deliberately omits it rather than routing toward a call that would crash.
_RELATIONSHIP_TYPE_SIGNALS: list[tuple[str, list[str]]] = [
    (r"\bwho authored\b", ["AUTHORED_BY"]),
    (r"\bauthored by\b", ["AUTHORED_BY"]),
    (r"\bwho wrote\b", ["AUTHORED_BY"]),
    (r"\bwhat does .{1,60}\bmentions?\b", ["MENTIONS"]),
    (r"\bmentions? (the )?most\b", ["MENTIONS"]),
    (r"\bmost (frequently )?mentions?\b", ["MENTIONS"]),
    (r"\bsame entity\b", ["SAME_AS"]),
    (r"\bsame as\b", ["SAME_AS"]),
    (r"\bis .{1,60}\bthe same\b", ["SAME_AS"]),
    (r"\baggregat\w*\b", ["SAME_AS"]),
    (r"\braw (name )?variants?\b", ["SAME_AS"]),
]


def infer_relationship_types(question: str) -> list[str] | None:
    for pattern, rel_types in _RELATIONSHIP_TYPE_SIGNALS:
        if re.search(pattern, question, _FLAGS):
            return rel_types
    return None


# Relationship types under which the seed node itself is never a valid answer to the implied question — "who authored X" / "what does X mention" ask about a relationship TARGET, not X's own identity, unlike "what does X aggregate" (SAME_AS) or an unfiltered "tell me about X" call, where the seed genuinely can be (and per eval questions 2/5/12/13, is) the correct top answer.
_SEED_EXCLUDED_RELATIONSHIP_TYPES = {"AUTHORED_BY", "MENTIONS"}


def _include_seed(relationship_types: list[str] | None) -> bool:
    if not relationship_types:
        return True
    return not _SEED_EXCLUDED_RELATIONSHIP_TYPES.intersection(relationship_types)


# search_by_name() embeds whatever text it's given against entity_name_embedding/ canonical_name_embedding — short-name embeddings, calibrated for a few words, not a full sentence (architecture.md §12.14, found during Step 11 end-to-end testing: question 6 dropped rank 1 -> 6, question 4's vector leg similarly diluted). Two-step extraction below, proportionate to that specific gap — not a new NLP subsystem:
# 1. If the question matches one of query_classifier.py's own _VECTOR_NAME_SIGNALS trigger phrases with a term following it (e.g. "best matching 'knowledge graph'"), capture that term directly — reusing the same trigger vocabulary the classifier already uses to decide "this is a vector_name question" to now also answer "what's the name it's asking about."
# 2. Otherwise: cut off a second clause at the same compound-question comma boundary query_classifier.py's escalation rule (d) detects (", and how/is/are/does/do/what/which..." — e.g. question 12's "...Gayo, and is his name affected..." -> drop everything from the comma on), then strip a leading question-word/instruction prefix ("What is", "Who is", "Find...", "Search for") and surrounding punctuation.
# Falls back to the original question text unchanged if neither step reduces anything — this never makes a query longer than doing nothing would.
_VECTOR_NAME_TERM_PATTERNS = [
    r"\bsimilar to\b\s*['\"]?([^'\".!?]+)['\"]?",
    r"\bclosest match(?:es)? to\b\s*['\"]?([^'\".!?]+)['\"]?",
    r"\bclosest to\b\s*['\"]?([^'\".!?]+)['\"]?",
    r"\bbest matching\b\s*['\"]?([^'\".!?]+)['\"]?",
    r"\bname.{0,20}\bmatching\b\s*['\"]?([^'\".!?]+)['\"]?",
]

# Same shape as query_classifier.py's _COMPOUND_QUESTION_SIGNALS — duplicated rather than imported, since that module's patterns are private and classification vs. term-extraction are different concerns even when they share a trigger shape.
_COMPOUND_CLAUSE_BOUNDARY = re.compile(r",\s*and (how|is|are|does|do|what|which)\b.*$", _FLAGS)

_LEADING_SCAFFOLDING = [
    r"^\s*what is\b\s*",
    r"^\s*who is\b\s*",
    r"^\s*find (information about|entities?(?:\s*/\s*canonicals?)?(?:\s*whose name is)?)?\s*",
    r"^\s*search for\b\s*",
    r"^\s*tell me about\b\s*",
]


def extract_vector_name_term(question: str) -> str:
    for pattern in _VECTOR_NAME_TERM_PATTERNS:
        m = re.search(pattern, question, _FLAGS)
        if m and m.group(1).strip():
            return m.group(1).strip().strip("'\"")

    stripped = _COMPOUND_CLAUSE_BOUNDARY.sub("", question).strip()
    for prefix in _LEADING_SCAFFOLDING:
        replaced = re.sub(prefix, "", stripped, flags=_FLAGS)
        if replaced != stripped:
            stripped = replaced
            break
    stripped = stripped.strip().strip("'\"").rstrip("?.! ").strip()

    return stripped if stripped else question


def plan_and_retrieve(
    question: str,
    graph_seed_id: str | None = None,
    top_k: int = 8,
) -> RoutingResult:
    category, fired = classify_with_signals(question)

    if category == "graph":
        if graph_seed_id is None:
            raise ValueError(
                "graph routing requires graph_seed_id — entity linking from free text is not implemented in Atlas yet (see module docstring)"
            )
        rel_types = infer_relationship_types(question)
        results = get_entity_context(
            graph_seed_id, relationship_types=rel_types, include_seed=_include_seed(rel_types)
        )[:top_k]
        return RoutingResult(category, rel_types, ["graph"], results)

    if category == "vector_name":
        results = search_by_name(extract_vector_name_term(question), top_k=top_k)
        return RoutingResult(category, None, ["vector"], results)

    if category == "vector_passage":
        results = search_by_passage(question, top_k=top_k)
        return RoutingResult(category, None, ["vector"], results)

    if category == "keyword":
        results = search_by_keyword(_escape_lucene(question), top_k=top_k)
        return RoutingResult(category, None, ["keyword"], results)

    # hybrid
    per_source: dict[str, list[RetrievalResult]] = {}
    graph_rel_types: list[str] | None = None
    if graph_seed_id is not None:
        graph_rel_types = infer_relationship_types(question)
        per_source["graph"] = get_entity_context(
            graph_seed_id,
            relationship_types=graph_rel_types,
            include_seed=_include_seed(graph_rel_types),
        )[:top_k]

    # Which vector mode for a hybrid call? The classifier's category alone doesn't say (that's exactly why it escalated). Use whichever vector signal actually fired if one did; if the escalation was specifically an AMBIGUOUS_TERMS match on an otherwise-clean "graph" signal (e.g. "mention" — see query_classifier.py), call vector in passage mode, since content-level "discusses X" is the competing interpretation graph's "mention" reading was hedged against. Any other 0-signal or 2+-signal hybrid case (Q12/Q13/Q15-shaped: identity/lookup questions with no single dominant signal) defaults to name mode.
    if "vector_passage" in fired:
        vector_mode = "passage"
    elif "vector_name" in fired:
        vector_mode = "name"
    elif fired == {"graph"}:
        vector_mode = "passage"
    else:
        vector_mode = "name"
    per_source["vector"] = (
        search_by_passage(question, top_k=top_k)
        if vector_mode == "passage"
        else search_by_name(extract_vector_name_term(question), top_k=top_k)
    )

    per_source["keyword"] = search_by_keyword(_escape_lucene(question), top_k=top_k)

    fused = reciprocal_rank_fusion(per_source)[:top_k]
    return RoutingResult("hybrid", graph_rel_types, list(per_source.keys()), fused)
