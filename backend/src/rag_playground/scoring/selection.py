"""Selection gates (T08) and the paired bootstrap that decides whether a change is real (T09)."""

import random
from statistics import mean, quantiles

from rag_playground.settings import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, GATES


def failed_gates(scores: dict[str, float]) -> list[str]:
    """Names of the gates a run fails; an empty list means the run is eligible to be "best"."""
    return [name for name, minimum in GATES.items() if scores[name] < minimum]


def paired_bootstrap(before: dict[str, float], after: dict[str, float]) -> tuple[float, float]:
    """95% percentile interval of the mean per-question difference `after - before` (Efron & Tibshirani,
    1993). Both runs must score the same questions; resampling keeps each question's pair together."""
    if before.keys() != after.keys():
        raise ValueError("a paired bootstrap needs both runs on the same questions")
    diffs = [after[q] - before[q] for q in sorted(before)]
    rng = random.Random(BOOTSTRAP_SEED)
    means = [mean(rng.choices(diffs, k=len(diffs))) for _ in range(BOOTSTRAP_RESAMPLES)]
    cuts = quantiles(means, n=40, method="inclusive")
    return cuts[0], cuts[-1]


def is_real_improvement(before: dict[str, float], after: dict[str, float]) -> bool:
    """A change counts only if the whole interval is above 0."""
    return paired_bootstrap(before, after)[0] > 0
