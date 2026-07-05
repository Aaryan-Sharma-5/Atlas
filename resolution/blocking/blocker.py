"""Candidate generation via blocking: reduces O(n²) pairwise comparison to within-block comparisons before any matcher runs (CLAUDE.md: blocking is mandatory before matching, regardless of corpus size).

Union blocking: each entity lands in one block per (key kind, normalized form), and a pair is a candidate if it shares ANY block. Complementary keys keep recall-critical variants comparable — last_token survives middle initials and leading articles, sorted_initials survives token reordering — while comparisons stay far below full pairwise. Node types never share a block, so a Person is never a candidate for an Organization even on an identical string. Pure, no Neo4j.
"""

import logging
from collections import defaultdict

from models.entity import Entity
from resolution.normalization.normalizer import normalize_forms

logger = logging.getLogger(__name__)


def _keys_for(form: str) -> dict[str, str]:
    tokens = form.split(" ")
    return {
        "first_token_block": tokens[0],
        "last_token_block": tokens[-1],
        "sorted_initials_block": "".join(sorted(t[0] for t in tokens)),
    }


def generate_blocks(entities: list[Entity]) -> dict[str, list[Entity]]:
    # id-keyed dedupe: an entity's two forms often share a key (same last token), and it must appear in that block once
    members: dict[str, dict[str, Entity]] = defaultdict(dict)
    for entity in entities:
        for form in normalize_forms(entity.name):
            if not form:
                continue
            for kind, value in _keys_for(form).items():
                members[f"{entity.type}|{kind}|{value}"].setdefault(entity.id, entity)

    blocks = {key: list(m.values()) for key, m in members.items()}
    stats = block_stats(blocks)
    logger.info(
        "blocking: %(blocks)d blocks (largest %(largest)d, avg %(average).1f, "
        "singletons %(singletons)d); %(unique_pairs)d unique candidate pairs "
        "across %(comparison_slots)d within-block slots",
        stats,
    )
    return blocks


def block_stats(blocks: dict[str, list[Entity]]) -> dict[str, float | int]:
    sizes = [len(members) for members in blocks.values()]
    unique_pairs: set[tuple[str, str]] = set()
    for members in blocks.values():
        ids = sorted(e.id for e in members)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                unique_pairs.add((ids[i], ids[j]))
    return {
        "blocks": len(blocks),
        "largest": max(sizes, default=0),
        "average": round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
        "singletons": sum(1 for s in sizes if s == 1),
        # slots = RapidFuzz comparisons actually run (a pair sharing k blocks is scored k times); unique_pairs = distinct pairs ever compared, the number to hold against the O(n²) baseline
        "comparison_slots": sum(s * (s - 1) // 2 for s in sizes),
        "unique_pairs": len(unique_pairs),
    }
