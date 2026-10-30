"""Judge calibration (T20, T48): which answers the user grades, and how far the judge agrees with the user. The equal
allocation per score and the fill rule are custom choices."""

import random
from dataclasses import dataclass
from math import sqrt
from statistics import mean

from rag_playground.settings import CALIBRATION_TARGET, PASS_ACCURACY

SCORES = (1, 2, 3, 4, 5)
Z_95 = 1.96


@dataclass(frozen=True)
class Agreement:
    """Agreement between judge and user over `graded` answers, as shares from 0 to 1, with the 95% interval of the
    pass/fail share."""

    pass_fail: float
    pass_fail_low: float
    pass_fail_high: float
    within_one: float
    graded: int

    @property
    def target_reached(self) -> bool:
        return self.pass_fail >= CALIBRATION_TARGET


def sample(scores: dict[str, int], per_score: int, seed: int) -> list[str]:
    """Answers to grade from one run's judge scores {test id: accuracy}, in shuffled order: `per_score` for each score,
    and any score short of answers is filled from the nearest scores, the lower one first on a tie."""
    if len(scores) < per_score * len(SCORES):
        raise ValueError(f"A run of {len(scores)} answers cannot give {per_score * len(SCORES)}")
    rng = random.Random(seed)
    pools = {score: sorted(t for t, s in scores.items() if s == score) for score in SCORES}
    for pool in pools.values():
        rng.shuffle(pool)
    chosen = {score: [pools[score].pop() for _ in range(min(per_score, len(pools[score])))] for score in SCORES}
    for score in SCORES:
        for nearest in sorted(SCORES, key=lambda other: (abs(other - score), other)):
            while len(chosen[score]) < per_score and pools[nearest]:
                chosen[score].append(pools[nearest].pop())
    picked = [test_id for group in chosen.values() for test_id in group]
    rng.shuffle(picked)
    return picked


def wilson(successes: int, total: int) -> tuple[float, float]:
    """The 95% Wilson score interval of a share, which stays sensible on small samples and near 0 or 1."""
    share, z2 = successes / total, Z_95 ** 2
    centre = (share + z2 / (2 * total)) / (1 + z2 / total)
    margin = Z_95 * sqrt(share * (1 - share) / total + z2 / (4 * total ** 2)) / (1 + z2 / total)
    return centre - margin, centre + margin


def agreement(pairs: list[tuple[int, int]]) -> Agreement:
    """Agreement over (judge score, user score) pairs: on pass or fail, and within 1 point on the 1-5 scale."""
    same_side = [(judge >= PASS_ACCURACY) == (human >= PASS_ACCURACY) for judge, human in pairs]
    low, high = wilson(sum(same_side), len(pairs))
    return Agreement(pass_fail=mean(same_side), pass_fail_low=low, pass_fail_high=high,
                     within_one=mean(abs(judge - human) <= 1 for judge, human in pairs), graded=len(pairs))
