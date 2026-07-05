"""Unit tests for normalize() / normalize_forms(). Runs standalone
(python test_normalizer.py) or under pytest. Cases cover the duplicate
patterns observed in the live multi-source corpus."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from resolution.normalization.normalizer import normalize, normalize_forms

CASES: list[tuple[str, str]] = [
    # case folding (corpus: all-caps header extractions)
    ("AIDAN HOGAN", "aidan hogan"),
    ("Aidan Hogan", "aidan hogan"),
    # legal suffixes
    ("OpenAI Inc.", "openai"),
    ("Google LLC", "google"),
    ("Acme Co., Ltd.", "acme"),
    # suffix token only stripped at the end, never emptied to nothing
    ("Co", "co"),
    ("Ltd Industries", "ltd industries"),
    # casing variants of the same technology name (corpus: DBPedia/DBpedia)
    ("DBPedia", "dbpedia"),
    ("DBpedia", "dbpedia"),
    # possessives, both apostrophe styles
    ("Wikidata's", "wikidata"),
    ("OpenAI’s", "openai"),
    # punctuation -> space, then collapse
    ("Hogan, Aidan", "hogan aidan"),
    ("RDF-star", "rdf star"),
    ("knowledge_graph", "knowledge graph"),
    # whitespace collapse
    ("  Aidan \t Hogan  ", "aidan hogan"),
    # accent folding (corpus: Óscar Corcho appears both ways)
    ("Óscar Corcho", "oscar corcho"),
    ("José Pérez", "jose perez"),
    # NFKD also rescues math-alphanumeric PDF artifacts
    ("𝐸. Negative", "e negative"),
    # leading articles (corpus: 'the RDF4J Client' vs 'RDF4J Client')
    ("The RDF4J Client", "rdf4j client"),
    ("a World Heritage Site", "world heritage site"),
    ("The Acme Co.", "acme"),
    # an initial is NOT an article: the period protects it
    ("A. Smola", "a smola"),
    # article alone never strips to empty
    ("The", "the"),
]

FORMS_CASES: list[tuple[str, tuple[str, ...]]] = [
    # middle initial -> second form without it, both used for blocking
    ("Christopher D. Manning", ("christopher d manning", "christopher manning")),
    ("Fabian M. Suchanek", ("fabian m suchanek", "fabian suchanek")),
    # no initials -> single form
    ("Aidan Hogan", ("aidan hogan",)),
    # initial + surname must NOT degrade to a bare surname form
    ("A. Smola", ("a smola",)),
    ("T. M. Hospedales", ("t m hospedales",)),
]


def test_normalize_cases() -> None:
    for raw, expected in CASES:
        got = normalize(raw)
        assert got == expected, f"normalize({raw!r}) = {got!r}, expected {expected!r}"


def test_normalize_forms_cases() -> None:
    for raw, expected in FORMS_CASES:
        got = normalize_forms(raw)
        assert got == expected, (
            f"normalize_forms({raw!r}) = {got!r}, expected {expected!r}"
        )


def test_corpus_variants_converge() -> None:
    assert normalize("DBPedia") == normalize("DBpedia")
    assert normalize("AIDAN HOGAN") == normalize("Aidan Hogan")
    assert normalize("OpenAI Inc.") == normalize("OpenAI")
    assert normalize("Óscar Corcho") == normalize("Oscar Corcho")
    assert normalize("the RDF4J Client") == normalize("RDF4J Client")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    test_normalize_cases()
    test_normalize_forms_cases()
    test_corpus_variants_converge()
    print(f"[OK] {len(CASES)} normalize + {len(FORMS_CASES)} forms cases "
          f"+ convergence checks passed")
