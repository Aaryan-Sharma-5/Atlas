"""Stage 1 entity resolution: string-similarity candidate generation.

Produces candidate pairs ONLY — no merging happens here. Merge decisions are a later, explicit step once embedding similarity (Stage 2) adds a second signal. This module is pure: list[Entity] in, candidates out; it never touches Neo4j.
"""

import re
from dataclasses import dataclass
from collections import defaultdict

from rapidfuzz import fuzz, process

from models.entity import Entity

DEFAULT_THRESHOLD = 0.85


@dataclass
class CandidatePair:
    id_a: str
    id_b: str
    name_a: str
    name_b: str
    type: str
    score: float          # [0, 1], max of ratio and token_sort_ratio
    cross_source: bool    # duplicates across documents, resolution's main target


def find_candidate_pairs(
    entities: list[Entity],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[CandidatePair]:
    """All same-type entity pairs whose name similarity >= threshold.

    Blocking: pairs are only proposed within one node type — Stage 1 never suggests merging a Person into an Organization, even for identical strings (those conflicts are Stage 5 quality material).
    """
    by_type: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        by_type[entity.type].append(entity)

    pairs: list[CandidatePair] = []
    for node_type, group in by_type.items():
        pairs.extend(_pairs_within_type(node_type, group, threshold))

    pairs.sort(key=lambda p: (-p.score, p.name_a))
    return pairs


def _pairs_within_type(
    node_type: str, group: list[Entity], threshold: float
) -> list[CandidatePair]:
    names = [_normalize(e.name) for e in group]

    # One similarity matrix per scorer; final score is the max. ratio catches typos/case, token_sort_ratio catches reordering ("Hogan, Aidan" vs "Aidan Hogan").
    cutoff = threshold * 100
    ratio = process.cdist(names, names, scorer=fuzz.ratio, score_cutoff=cutoff)
    token_sort = process.cdist(
        names, names, scorer=fuzz.token_sort_ratio, score_cutoff=cutoff
    )

    pairs: list[CandidatePair] = []
    n = len(group)
    for i in range(n):
        for j in range(i + 1, n):
            score = max(ratio[i][j], token_sort[i][j]) / 100.0
            if score >= threshold:
                a, b = group[i], group[j]
                pairs.append(
                    CandidatePair(
                        id_a=a.id,
                        id_b=b.id,
                        name_a=a.name,
                        name_b=b.name,
                        type=node_type,
                        score=round(float(score), 4),
                        cross_source=a.extraction_source != b.extraction_source,
                    )
                )
    return pairs


def _normalize(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    return re.sub(r"\s+", " ", cleaned).strip()
