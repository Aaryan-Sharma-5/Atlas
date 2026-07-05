"""Entity resolution: normalization -> blocking -> matching -> decisioning."""

from resolution.matchers.string_matcher import CandidatePair, find_candidate_pairs

__all__ = ["find_candidate_pairs", "CandidatePair"]
