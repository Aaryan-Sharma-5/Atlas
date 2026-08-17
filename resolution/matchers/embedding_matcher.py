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

# Calibrated 2026-07-17 against the 4,482-entity corpus. Every embedding match produces a TENTATIVE SAME_AS per the Stage 4 decisioning rules, never an auto-merge, so recall is weighted over precision here; 0.90 sits at the reported natural knee (79 of 40,829 scored pairs). Known accepted risk: short-name and initials-only pairs ("B. Zhou" vs "C. Zhou") can score above threshold and will surface as false-positive tentative pairs.
DEFAULT_THRESHOLD = 0.90

# torch-free inference: raw onnxruntime + tokenizers, not sentence-transformers (which imports torch unconditionally at package level even under backend="onnx" -- confirmed empirically, not assumed). fp32 model.onnx, not a quantized variant: measured equivalent to the original torch/sentence-transformers output (cosine 0.9999999-1.0000001 on a 5-string spot check), so no existing stored embedding needs regenerating. Cache holds (tokenizer, InferenceSession) pairs, same one-cache-entry-per-model-name shape the old _model() used.
_model_cache: dict[str, tuple] = {}


def _session(name: str) -> tuple:
    if name not in _model_cache:
        # deferred: even these lighter imports are only needed when Stage 2 runs
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(hf_hub_download(name, "tokenizer.json"))
        tokenizer.enable_padding()
        session = ort.InferenceSession(
            hf_hub_download(name, "onnx/model.onnx"), providers=["CPUExecutionProvider"]
        )
        _model_cache[name] = (tokenizer, session)
    return _model_cache[name]


def embed_names(names: list[str], model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """L2-normalized embeddings, so cosine similarity is a plain dot product.

    Mean-pools token embeddings (masked by attention_mask) then L2-normalizes -- replicates sentence-transformers' default pooling for this model, since that postprocessing isn't baked into the raw ONNX graph itself.
    """
    tokenizer, session = _session(model_name)
    encoded = tokenizer.encode_batch(names)
    input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids)

    outputs = session.run(
        None,
        {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        },
    )
    token_embeddings = outputs[0]

    mask = attention_mask[..., None].astype(np.float32)
    summed = (token_embeddings * mask).sum(axis=1)
    counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
    pooled = summed / counts
    return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)


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
