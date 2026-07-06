"""Merge decisioning (Stage 4): CandidatePair -> ResolutionDecision.

Intentionally empty — blocked on review of the combined Stage 1+2 candidate output. merge_resolver.py lands here once approved.

TODO(Stage 5 quality flagging, docs/architecture.md §12.1): specifically flag embedding-sourced TENTATIVE pairs where either entity name has <= 3 tokens or consists only of initials ("B. Zhou" / "C. Zhou") — the accepted false-positive risk of the 0.90 embedding threshold, weighted for recall because nothing auto-merges.
"""
