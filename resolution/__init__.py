"""Entity resolution: string similarity, embedding similarity, merge logic."""

from resolution.string_matcher import CandidatePair, find_candidate_pairs

__all__ = ["find_candidate_pairs", "CandidatePair"]
