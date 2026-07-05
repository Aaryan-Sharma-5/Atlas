"""Stage 1 entity resolution: string-similarity candidate generation.

Produces candidate pairs ONLY — no merging happens here. Merge decisions are a later, explicit step once embedding similarity (Stage 2) adds a second signal. This module is pure: list[Entity] in, candidates out; it never touches Neo4j.

Pipeline: entities -> normalize each -> generate_blocks (union of keys) -> RapidFuzz within blocks only. A pair reachable through several blocks is emitted once, with every contributing block recorded in matched_by.
"""

from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from models.entity import Entity
from resolution.blocking.blocker import generate_blocks
from resolution.normalization.normalizer import normalize

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
    # contributing blocks (sorted) + winning scorer, e.g. ["first_token_block", "last_token_block", "token_sort_ratio"]. Stage 2 appends "embedding_similarity" when it adds signal.
    matched_by: list[str] = field(default_factory=list)


def find_candidate_pairs(
    entities: list[Entity],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[CandidatePair]:
    """Same-block entity pairs whose normalized-name similarity >= threshold.

    Blocking keys are scoped by node type, so Stage 1 never suggests merging a Person into an Organization, even for identical strings (those conflicts are Stage 5 quality material).
    """
    found: dict[tuple[str, str], CandidatePair] = {}
    for block_key, block in generate_blocks(entities).items():
        kind = block_key.split("|")[1]
        _score_block(block, kind, threshold, found)

    pairs = list(found.values())
    for pair in pairs:
        pair.matched_by = sorted(pair.matched_by[:-1]) + pair.matched_by[-1:]
    pairs.sort(key=lambda p: (-p.score, p.name_a, p.id_a, p.id_b))
    return pairs


def _score_block(
    block: list[Entity],
    kind: str,
    threshold: float,
    found: dict[tuple[str, str], CandidatePair],
) -> None:
    if len(block) < 2:
        return
    names = [normalize(e.name) for e in block]

    # One similarity matrix per scorer; final score is the max. ratio catches typos/case, token_sort_ratio catches reordering ("Hogan, Aidan" vs "Aidan Hogan").
    cutoff = threshold * 100
    ratio = process.cdist(names, names, scorer=fuzz.ratio, score_cutoff=cutoff)
    token_sort = process.cdist(
        names, names, scorer=fuzz.token_sort_ratio, score_cutoff=cutoff
    )

    n = len(block)
    for i in range(n):
        for j in range(i + 1, n):
            score = max(ratio[i][j], token_sort[i][j]) / 100.0
            if score < threshold:
                continue
            a, b = block[i], block[j]
            pair_key = (a.id, b.id) if a.id < b.id else (b.id, a.id)
            existing = found.get(pair_key)
            if existing is not None:
                if kind not in existing.matched_by:
                    existing.matched_by.insert(-1, kind)  # scorer stays last
                continue
            scorer = (
                "token_sort_ratio" if token_sort[i][j] > ratio[i][j] else "ratio"
            )
            found[pair_key] = CandidatePair(
                id_a=a.id,
                id_b=b.id,
                name_a=a.name,
                name_b=b.name,
                type=a.type,
                score=round(float(score), 4),
                cross_source=a.extraction_source != b.extraction_source,
                matched_by=[kind, scorer],
            )
