"""Stratified dev / held-out split with a fixed seed (T10, T18, T30)."""

import math
import random
from collections import defaultdict

SEED = 42
HELDOUT_TOTAL = 50


def heldout_quotas(counts: dict[str, int], total: int) -> dict[str, int]:
    """Share `total` held-out slots across categories in proportion to size, by largest remainder."""
    n = sum(counts.values())
    exact = {c: counts[c] * total / n for c in counts}
    quotas = {c: math.floor(v) for c, v in exact.items()}
    by_remainder = sorted(counts, key=lambda c: (-(exact[c] - quotas[c]), c))
    for c in by_remainder[: total - sum(quotas.values())]:
        quotas[c] += 1
    return quotas


def assign_splits(ids_by_category: dict[str, list[str]], total: int = HELDOUT_TOTAL, seed: int = SEED) -> dict[str, str]:
    """Map each test id to "dev" or "heldout"; the same input always gives the same split."""
    quotas = heldout_quotas({c: len(ids) for c, ids in ids_by_category.items()}, total)
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
