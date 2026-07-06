"""Stage 2 entity resolution: embedding-similarity candidate generation.

Scores ONLY blocked pairs that string matching did not already pair (build order 6.4) — it is a second signal for textually-distant duplicates, not a re-scoring of string candidates. Same contract as string_matcher: entities in, CandidatePair objects out, no Neo4j, no merging.

score is cosine similarity of normalized-name embeddings — a different scale than the string matcher's RapidFuzz score; matched_by distinguishes the two ("embedding_similarity" last).
"""

from collections import defaultdict

import numpy as np

from models.entity import Entity
from resolution.blocking.blocker import generate_blocks
from resolution.matchers.string_matcher import CandidatePair
from resolution.normalization.normalizer import normalize

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Calibrated 2026-07-17 against the 4,482-entity corpus (calibration report in
# testing/test_embedding_resolution.py). Every embedding match produces a
# TENTATIVE SAME_AS per the Stage 4 decisioning rules, never an auto-merge, so
# recall is weighted over precision here; 0.90 sits at the reported natural
# knee (79 of 40,829 scored pairs). Known accepted risk: short-name and
# initials-only pairs ("B. Zhou" vs "C. Zhou") can score above threshold and
# will surface as false-positive tentative pairs. This is intentional, not a
# bug — catch it in Stage 5 quality flagging, not here.
DEFAULT_THRESHOLD = 0.90

_model_cache: dict[str, object] = {}


def _model(name: str):
    if name not in _model_cache:
        # deferred: torch import is heavy and only needed when Stage 2 runs
        from sentence_transformers import SentenceTransformer

        _model_cache[name] = SentenceTransformer(name)
    return _model_cache[name]


def embed_names(names: list[str], model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """L2-normalized embeddings, so cosine similarity is a plain dot product."""
    return _model(model_name).encode(
        names, normalize_embeddings=True, show_progress_bar=False
    )


def find_embedding_candidates(
    entities: list[Entity],
    exclude: set[tuple[str, str]],
    threshold: float | None = DEFAULT_THRESHOLD,
    model_name: str = DEFAULT_MODEL,
) -> list[CandidatePair]:
    """Cosine-scored candidates for blocked pairs not in `exclude` (the string matcher's pairs, keyed as sorted id tuples). threshold=None returns every scored pair, for calibration."""
    by_id: dict[str, Entity] = {e.id: e for e in entities}
    pair_blocks: dict[tuple[str, str], set[str]] = defaultdict(set)
    for block_key, block in generate_blocks(entities).items():
        kind = block_key.split("|")[1]
        ids = sorted(e.id for e in block)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                key = (ids[i], ids[j])
                if key not in exclude:
                    pair_blocks[key].add(kind)

    names = sorted({normalize(by_id[i].name) for key in pair_blocks for i in key})
    index = {name: row for row, name in enumerate(names)}
    vectors = embed_names(names, model_name)

    pairs: list[CandidatePair] = []
    for (id_a, id_b), kinds in pair_blocks.items():
        a, b = by_id[id_a], by_id[id_b]
        score = float(
            vectors[index[normalize(a.name)]] @ vectors[index[normalize(b.name)]]
        )
        if threshold is not None and score < threshold:
            continue
        pairs.append(
            CandidatePair(
                id_a=a.id,
                id_b=b.id,
                name_a=a.name,
                name_b=b.name,
                type=a.type,
                score=round(score, 4),
                cross_source=a.extraction_source != b.extraction_source,
                matched_by=sorted(kinds) + ["embedding_similarity"],
            )
        )

    pairs.sort(key=lambda p: (-p.score, p.name_a, p.id_a, p.id_b))
    return pairs


def score_name_pairs(
    name_pairs: list[tuple[str, str]], model_name: str = DEFAULT_MODEL
) -> list[float]:
    """Diagnostic helper for calibration reports: cosine similarity for explicit name pairs (e.g. the string matcher's ambiguous band). Not part of candidate generation."""
    names = sorted({normalize(n) for pair in name_pairs for n in pair})
    index = {name: row for row, name in enumerate(names)}
    vectors = embed_names(names, model_name)
    return [
        float(vectors[index[normalize(a)]] @ vectors[index[normalize(b)]])
        for a, b in name_pairs
    ]
