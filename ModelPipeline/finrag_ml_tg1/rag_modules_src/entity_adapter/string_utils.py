# ModelPipeline\finrag_ml_tg1\rag_modules_src\entity_adapter\string_utils.py

from __future__ import annotations

from typing import Iterable, Optional, Tuple


def simple_fuzzy_match(
    word: str,
    choices: Iterable[str],
    threshold: float = 0.8,
) -> Tuple[Optional[str], float]:
    """
    Simple fuzzy matching using Levenshtein distance (no external libs).

    Parameters
    ----------
    word:
        Input string to match.
    choices:
        Iterable of candidate strings.
    threshold:
        Similarity threshold in [0, 1]. If the best match has similarity
        below this threshold, (None, 0.0) is returned.

    Returns
    -------
    (best_match, score)
        best_match: the best matching string from choices, or None.
        score: similarity percentage in [0, 100].
    """

    def levenshtein_distance(s1: str, s2: str) -> int:
        # Standard DP Levenshtein distance
        if len(s1) < len(s2):
            return levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    def similarity(s1: str, s2: str) -> float:
        distance = levenshtein_distance(s1.lower(), s2.lower())
        max_len = max(len(s1), len(s2))
        return 1 - (distance / max_len) if max_len > 0 else 0.0

    best_match: Optional[str] = None
    best_score: float = 0.0

    for choice in choices:
        score = similarity(word, choice)
        if score > best_score:
            best_score = score
            best_match = choice

    if best_score >= threshold:
        # return similarity as percentage
        return best_match, best_score * 100.0

    return None, 0.0
