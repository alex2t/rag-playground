"""Selection gates and best run (T08), and the paired bootstrap that decides whether a change is real (T09)."""

import random
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Candidate:
    """What choosing between runs needs from one run: gate scores, accuracy per question, mean cost per question,
    and MRR per answerable question."""

    run_id: int
    scores: dict[str, float]
    accuracy: dict[str, float]
    cost_per_question: float
    mrr: dict[str, float]

    @property
    def mean_accuracy(self) -> float:
        return mean(self.accuracy.values())


def pick_best(candidates: list[Candidate]) -> Candidate | None:
    """T08: among runs passing every gate, the highest mean accuracy; runs whose gap to it is not real (T09) are tied
    with it, and the cheapest of those wins. Higher accuracy, then the older run, settle an exact cost tie. None if
    no run passes."""
    eligible = [c for c in candidates if not failed_gates(c.scores)]
    if not eligible:
        return None
    leader = max(eligible, key=lambda c: c.mean_accuracy)
    tied = [c for c in eligible if not is_real_improvement(c.accuracy, leader.accuracy)]
    return min(tied, key=lambda c: (c.cost_per_question, -c.mean_accuracy, c.run_id))
