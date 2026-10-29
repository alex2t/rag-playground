"""Stratified dev / held-out split with a fixed seed (T10, T18, T30)."""

import math
import random
from collections import defaultdict
from itertools import zip_longest

from rag_playground.datasets.schema import TestCase

SEED = 42
HELDOUT_SHARE = 0.2


def heldout_quotas(counts: dict[str, int], total: int) -> dict[str, int]:
    """Share `total` held-out slots across categories in proportion to size, by largest remainder."""
    n = sum(counts.values())
    exact = {c: counts[c] * total / n for c in counts}
    quotas = {c: math.floor(v) for c, v in exact.items()}
    by_remainder = sorted(counts, key=lambda c: (-(exact[c] - quotas[c]), c))
    for c in by_remainder[: total - sum(quotas.values())]:
        quotas[c] += 1
    return quotas


def assign_splits(ids_by_category: dict[str, list[str]], seed: int = SEED) -> dict[str, str]:
    """Map each test id to "dev" or "heldout" (a fifth, rounded); the same input always gives the same split."""
    counts = {c: len(ids) for c, ids in ids_by_category.items()}
    quotas = heldout_quotas(counts, round(HELDOUT_SHARE * sum(counts.values())))
    rng = random.Random(seed)
    split = {}
    for category in sorted(ids_by_category):
        ids = sorted(ids_by_category[category])
        rng.shuffle(ids)
        for i, test_id in enumerate(ids):
            split[test_id] = "heldout" if i < quotas[category] else "dev"
    return split


def group_by_category(tests: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Group (id, category) pairs into {category: [ids]}."""
    groups = defaultdict(list)
    for test_id, category in tests:
        groups[category].append(test_id)
    return dict(groups)


def round_robin(tests: list[TestCase], n: int) -> list[TestCase]:
    """The first test of each category in turn, then the second of each, until `n` (custom choice for small
    runs, decision.md T46): every category is covered once n reaches the number of categories."""
    by_category = defaultdict(list)
    for test in tests:
        by_category[test.category].append(test)
    rounds = zip_longest(*by_category.values())
    return [test for row in rounds for test in row if test is not None][:n]
