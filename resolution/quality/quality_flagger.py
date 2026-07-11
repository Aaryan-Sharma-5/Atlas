"""Stage 5 quality flagging: ResolutionDecision + CandidatePair evidence -> QualityFlag.

Implements the review obligations recorded in docs/architecture.md §12.1/§12.4 and the Stage 1 deferral of cross-type name collisions. Flags SURFACE risk for human review — they never suppress, filter, or downgrade a decision, and this module writes nothing (same storage-agnostic contract as the rest of resolution/).

Flag types:
- short_name_embedding    §12.1: embedding-supported TENTATIVE where either
                          endpoint of an embedding edge has <= 3 tokens or is
                          initials-only ("B. Zhou" / "C. Zhou")
- ner_stutter             §12.1: a member name shows adjacent token repetition
                          ("Santiago Santiago de Chile", "RDF Reading RDF")
- large_tentative_cluster §12.4 residual: TENTATIVE with >= 5 members
                          (initial-swap ambiguity survives the cohesion floor)
- cross_type_collision    deferred from Stage 1: same canonical name resolved
                          under different node types ("Cypher" as Person AND
                          Organization) — a Stage 1 blocking guarantee kept
                          them apart; one of them is likely a NER mislabel
"""

from dataclasses import dataclass, field
from collections import defaultdict

from models.resolution import ResolutionDecision
from resolution.decisioning.merge_resolver import has_stutter
from resolution.matchers.string_matcher import CandidatePair
from resolution.normalization.normalizer import normalize

SHORT_NAME_MAX_TOKENS = 3
LARGE_CLUSTER_MIN = 5


@dataclass
class QualityFlag:
    flag_type: str
    canonical_id: str
    canonical_name: str
    entity_type: str
    reason: str
    evidence: list[str] = field(default_factory=list)


def flag_decisions(
    decisions: list[ResolutionDecision], pairs: list[CandidatePair]
) -> list[QualityFlag]:
    clusters = [d for d in decisions if d.action != "NONE"]
    names: dict[str, str] = {}
    for p in pairs:
        names.setdefault(p.id_a, p.name_a)
        names.setdefault(p.id_b, p.name_b)
    embedding_pairs = [p for p in pairs if "embedding_similarity" in p.matched_by]

    flags: list[QualityFlag] = []
    for d in clusters:
        flags.extend(_short_name_embedding(d, embedding_pairs))
        flags.extend(_ner_stutter(d, names))
        flags.extend(_large_tentative(d))
    flags.extend(_cross_type_collisions(clusters))

    flags.sort(key=lambda f: (f.flag_type, f.canonical_id))
    return flags


def _is_risky_name(name: str) -> bool:
    tokens = normalize(name).split(" ")
    return (
        len(tokens) <= SHORT_NAME_MAX_TOKENS
        or all(len(t) == 1 for t in tokens)
    )


def _short_name_embedding(
    d: ResolutionDecision, embedding_pairs: list[CandidatePair]
) -> list[QualityFlag]:
    if d.action != "TENTATIVE":
        return []
    members = set(d.source_ids)
    risky = [
        p for p in embedding_pairs
        if p.id_a in members and p.id_b in members
        and (_is_risky_name(p.name_a) or _is_risky_name(p.name_b))
    ]
    if not risky:
        return []
    return [QualityFlag(
        flag_type="short_name_embedding",
        canonical_id=d.canonical_id,
        canonical_name=d.canonical_name,
        entity_type=d.entity_type,
        reason=f"{len(risky)} embedding edge(s) between short/initials-only "
               f"names (<= {SHORT_NAME_MAX_TOKENS} tokens) — highest-risk "
               f"false-positive class of the 0.90 threshold (docs §12.1)",
        evidence=[f"{p.name_a!r} ~ {p.name_b!r} (cos {p.score})" for p in risky],
    )]


def _ner_stutter(
    d: ResolutionDecision, names: dict[str, str]
) -> list[QualityFlag]:
    stuttered = sorted({
        names[sid] for sid in d.source_ids
        if sid in names and has_stutter(names[sid])
    })
    if not stuttered:
        return []
    return [QualityFlag(
        flag_type="ner_stutter",
        canonical_id=d.canonical_id,
        canonical_name=d.canonical_name,
        entity_type=d.entity_type,
        reason="member name(s) show NER stutter — legitimate same-entity "
               "grouping, but the underlying extraction is noisy (docs §12.1)",
        evidence=stuttered,
    )]


def _large_tentative(d: ResolutionDecision) -> list[QualityFlag]:
    if not (d.action == "TENTATIVE" and d.cluster_size >= LARGE_CLUSTER_MIN):
        return []
    return [QualityFlag(
        flag_type="large_tentative_cluster",
        canonical_id=d.canonical_id,
        canonical_name=d.canonical_name,
        entity_type=d.entity_type,
        reason=f"{d.cluster_size} members held together at the cohesion floor "
               f"— likely several real-world entities (docs §12.4 residual)",
        evidence=d.source_ids,
    )]


def _cross_type_collisions(
    clusters: list[ResolutionDecision],
) -> list[QualityFlag]:
    by_name: dict[str, list[ResolutionDecision]] = defaultdict(list)
    for d in clusters:
        by_name[normalize(d.canonical_name)].append(d)

    flags: list[QualityFlag] = []
    for group in by_name.values():
        types = {d.entity_type for d in group}
        if len(types) < 2:
            continue
        for d in group:
            others = sorted(
                f"{o.canonical_id} ({o.entity_type})" for o in group if o is not d
            )
            flags.append(QualityFlag(
                flag_type="cross_type_collision",
                canonical_id=d.canonical_id,
                canonical_name=d.canonical_name,
                entity_type=d.entity_type,
                reason="same canonical name resolved under multiple node types; "
                       "type-scoped blocking kept them apart by design — at "
                       "least one is likely a NER type mislabel",
                evidence=others,
            ))
    return flags
