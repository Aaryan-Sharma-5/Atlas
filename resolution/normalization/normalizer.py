"""Raw entity name -> normalized string(s). Runs before ANY similarity scoring (normalization is mandatory before scoring).
Pure string -> string, no I/O, no Neo4j. Similarity thresholds are calibrated against this function's output; changing it requires recalibrating thresholds and deliberately regenerating examples/expected_output/candidate_pairs.json.
"""

import re
import unicodedata
from functools import lru_cache

# Trailing legal-suffix tokens stripped after punctuation removal, so "Inc." / "Inc" / ", Inc." all reduce to the same token.
_LEGAL_SUFFIXES = {"inc", "ltd", "llc", "co"}

# Leading articles are stripped BEFORE punctuation removal so an initial keeps its period marker: "A. Smola" is initial + surname, not article + surname, and stays intact. Known trade-off: a bare given name "An" ("An Nguyen") is indistinguishable from the article and gets stripped.
_ARTICLES = re.compile(r"^\s*(?:(?:the|an?)\s+)+")
_POSSESSIVE = re.compile(r"['’]s\b")
# Underscore is word-punctuation in code identifiers ("knowledge_graph"), so it splits tokens like any other punctuation.
_PUNCTUATION = re.compile(r"[^\w\s]|_")
_WHITESPACE = re.compile(r"\s+")


@lru_cache(maxsize=None)
def normalize(raw: str) -> str:
    # NFKD before lowercasing: math alphanumerics ("𝐸") only reach their ASCII base letter via NFKD, and .lower() alone leaves them untouched.
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = _POSSESSIVE.sub("", text)
    text = _ARTICLES.sub("", text)
    text = _PUNCTUATION.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()

    tokens = text.split(" ")
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


@lru_cache(maxsize=None)
def normalize_forms(raw: str) -> tuple[str, ...]:
    """Primary form plus, for names mixing initials with fuller tokens, a variant without the single-letter tokens ("christopher d manning" -> "christopher manning"). Both participate in blocking; scoring always uses the primary form. The variant needs >= 2 fuller tokens so pure initialisms ("A. Smola") don't degrade to a bare surname."""
    primary = normalize(raw)
    tokens = primary.split(" ")
    fuller = [t for t in tokens if len(t) > 1]
    if 2 <= len(fuller) < len(tokens):
        return (primary, " ".join(fuller))
    return (primary,)
