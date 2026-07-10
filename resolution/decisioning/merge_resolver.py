"""Stage 4 merge decisioning: CandidatePair -> ResolutionDecision.

Storage-agnostic per Rule 8: no Neo4j import, nothing is written, and no decision is ever a physical merge — MERGE and TENTATIVE both become a Canonical node + SAME_AS edges downstream, built exclusively by graph/builders/ after graph/validators/.

Decision rules (Stage 4 spec):
- every supporting string edge  > 0.92                      -> MERGE
- any string edge in [0.70, 0.92] OR any embedding edge     -> TENTATIVE
- pair below 0.70 (edge case; 0.85 string threshold already
  excludes these upstream)                                  -> NONE

Clusters, not pairs: A~B and B~C must yield ONE canonical, so pairs are grouped by union-find before deciding, and a cluster's action is gated by its weakest supporting edge. Union-find alone is single-linkage and chains (see _cohesion_partition), so clusters must additionally pass the cohesion floor.
"""

import re
from collections import Counter, defaultdict
from itertools import combinations

from models.resolution import ResolutionDecision
from resolution.matchers.string_matcher import CandidatePair, string_similarity
from resolution.normalization.normalizer import normalize

MERGE_THRESHOLD = 0.92
TENTATIVE_FLOOR = 0.70

# Cluster-level invariant, separate from and stricter than the pairwise thresholds: EVERY pair inside a cluster must reach this, not just the pairs that happened to be candidate edges. Rationale in docs §12.4.
COHESION_FLOOR = 0.85


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        parent = self._parent.setdefault(x, x)
        if parent != x:
            self._parent[x] = parent = self.find(parent)
        return parent

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


def _is_embedding(pair: CandidatePair) -> bool:
    return "embedding_similarity" in pair.matched_by


def _pair_action(pair: CandidatePair) -> str:
    if _is_embedding(pair):
        return "TENTATIVE"
    if pair.score > MERGE_THRESHOLD:
        return "MERGE"
    if pair.score >= TENTATIVE_FLOOR:
        return "TENTATIVE"
    return "NONE"


def resolve(pairs: list[CandidatePair]) -> list[ResolutionDecision]:
    graded = [(p, _pair_action(p)) for p in pairs]
    names: dict[str, str] = {}
    for p in pairs:
        names.setdefault(p.id_a, p.name_a)
        names.setdefault(p.id_b, p.name_b)

    # NONE pairs never join a cluster: they are recorded (auditable rejection) but must not transitively glue two otherwise-unrelated clusters together
    decisions = [
        ResolutionDecision(
            action="NONE",
            confidence=p.score,
            canonical_id="",
            canonical_name="",
            entity_type=p.type,
            source_ids=sorted((p.id_a, p.id_b)),
            reasoning=f"pair score {p.score} below tentative floor "
                      f"{TENTATIVE_FLOOR}: {p.name_a!r} / {p.name_b!r}",
        )
        for p, action in graded if action == "NONE"
    ]

    uf = _UnionFind()
    linking = [(p, action) for p, action in graded if action != "NONE"]
    for p, _ in linking:
        uf.union(p.id_a, p.id_b)

    cluster_edges: dict[str, list[tuple[CandidatePair, str]]] = defaultdict(list)
    for p, action in linking:
        cluster_edges[uf.find(p.id_a)].append((p, action))

    used_ids: set[str] = set()
    for root in sorted(cluster_edges):
        edges = cluster_edges[root]
        member_ids = sorted({i for p, _ in edges for i in (p.id_a, p.id_b)})
        for group in _cohesion_partition(member_ids, edges, names):
            if len(group) < 2:
                continue  # cohesion orphan: falls out of resolution entirely
            group_set = set(group)
            group_edges = [
                (p, a) for p, a in edges
                if p.id_a in group_set and p.id_b in group_set
            ]
            split_note = (
                "" if len(group) == len(member_ids)
                else f"; cohesion split of {len(member_ids)}-entity "
                     f"single-linkage cluster (floor {COHESION_FLOOR})"
            )
            decisions.append(
                _decide_cluster(
                    group, group_edges, names, used_ids, split_note,
                    entity_type=edges[0][0].type,
                )
            )

    decisions.sort(key=lambda d: (d.action, -d.confidence, d.canonical_id))
    return decisions


def _cohesion_partition(
    member_ids: list[str],
    edges: list[tuple[CandidatePair, str]],
    names: dict[str, str],
) -> list[list[str]]:
    """Guard against single-linkage chaining: union-find connects A-B-C-D on
    pairwise edges even when A and D share nothing ('Y. Zhang' ~ ... ~
    'T. Jiang'). Candidate edges all score >= the matcher thresholds
    (>= COHESION_FLOOR), so dropping sub-floor edges and re-running connected
    components can never disconnect anything — the split must instead enforce
    the cluster invariant directly: every INTERNAL PAIR of a surviving
    cluster >= COHESION_FLOOR (complete-linkage), not merely every edge.

    Check (spec): pairwise matrix over all members, direct candidate-edge
    scores where present, unknown (never directly compared) pairs count as 0.
    Clusters of 2 are their own edge and pass by construction. Failing
    clusters are greedily re-partitioned on max(edge score, string
    similarity) — embedding evidence keeps its edge score so a pair the
    embedding matcher joined is not torn apart by its lower string score.
    """
    if len(member_ids) < 3:
        return [member_ids]

    edge_score: dict[frozenset[str], float] = {}
    for p, _ in edges:
        key = frozenset((p.id_a, p.id_b))
        edge_score[key] = max(edge_score.get(key, 0.0), p.score)

    known = [
        edge_score.get(frozenset(pair), 0.0)
        for pair in combinations(member_ids, 2)
    ]
    if min(known) >= COHESION_FLOOR:
        return [member_ids]

    def sim(a: str, b: str) -> float:
        return max(
            edge_score.get(frozenset((a, b)), 0.0),
            string_similarity(names[a], names[b]),
        )

    groups: list[list[str]] = []
    for mid in member_ids:  # sorted -> deterministic partition
        for group in groups:
            if all(sim(mid, other) >= COHESION_FLOOR for other in group):
                group.append(mid)
                break
        else:
            groups.append([mid])
    return groups


def _decide_cluster(
    member_ids: list[str],
    edges: list[tuple[CandidatePair, str]],
    names: dict[str, str],
    used_ids: set[str],
    split_note: str,
    entity_type: str,
) -> ResolutionDecision:
    pairs = [p for p, _ in edges]

    if edges:
        # weakest supporting edge gates the whole cluster: one tentative link anywhere means the grouping as a whole is tentative
        action = "MERGE" if all(a == "MERGE" for _, a in edges) else "TENTATIVE"
        confidence = round(min(p.score for p in pairs), 4)
    else:
        # cohesion-only group: members landed together via pairwise string similarity, but no matcher edge survives inside the group - the evidence is indirect, so never stronger than TENTATIVE
        action = "TENTATIVE"
        confidence = round(
            min(
                string_similarity(names[a], names[b])
                for a, b in combinations(member_ids, 2)
            ),
            4,
        )

    member_names = Counter(names[mid] for mid in member_ids)
    canonical_name = max(
        member_names,
        key=lambda n: (member_names[n], not has_stutter(n), len(n), n),
    )

    string_edges = [p for p in pairs if not _is_embedding(p)]
    embedding_edges = [p for p in pairs if _is_embedding(p)]
    parts = []
    if string_edges:
        lo, hi = min(p.score for p in string_edges), max(p.score for p in string_edges)
        parts.append(f"{len(string_edges)} string edge(s) [{lo}..{hi}]")
    if embedding_edges:
        lo, hi = (min(p.score for p in embedding_edges),
                  max(p.score for p in embedding_edges))
        parts.append(f"{len(embedding_edges)} embedding edge(s) [{lo}..{hi}]")
    if not parts:
        parts.append("no direct matcher edge, cohesion-only grouping")
    reasoning = (
        f"{len(member_ids)} entities linked by {' + '.join(parts)}; "
        f"weakest link {confidence} -> {action}"
        + ("" if action == "MERGE"
           else f" (MERGE requires every edge to be a string match > {MERGE_THRESHOLD})")
        + split_note
    )

    return ResolutionDecision(
        action=action,
        confidence=confidence,
        canonical_id=_canonical_id(member_ids[0], canonical_name, used_ids),
        canonical_name=canonical_name,
        entity_type=entity_type,
        source_ids=member_ids,
        reasoning=reasoning,
    )


def has_stutter(name: str) -> bool:
    """NER stutter artifacts: adjacent repeated tokens ("Santiago Santiago de Chile") or a fully doubled sequence ("RDF Reading RDF Reading"). Deprioritized for display, never filtered (docs §12.1)."""
    tokens = normalize(name).split(" ")
    if any(a == b for a, b in zip(tokens, tokens[1:])):
        return True
    n = len(tokens)
    return n >= 2 and n % 2 == 0 and tokens[: n // 2] == tokens[n // 2 :]


def _canonical_id(sample_member_id: str, canonical_name: str, used: set[str]) -> str:
    """physical.md convention: {type_prefix}_{name_slug}, no source namespace. Prefix comes from the member ids so it always matches extraction's prefixes; numeric suffix on collision (collision does NOT imply same entity)."""
    prefix = sample_member_id.split("_", 1)[0]
    slug = re.sub(r"[^a-z0-9]+", "_", canonical_name.lower()).strip("_") or "unnamed"
    base = f"{prefix}_{slug}"
    candidate, n = base, 1
    while candidate in used:
        n += 1
        candidate = f"{base}_{n}"
    used.add(candidate)
    return candidate
