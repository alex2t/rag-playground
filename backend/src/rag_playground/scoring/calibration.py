"""Judge calibration (T20, T48): which answers the user grades, and how far the judge agrees with the user. The equal
allocation per score and the fill rule are custom choices."""

import random
from dataclasses import dataclass
from math import sqrt
from statistics import mean

from rag_playground.settings import CALIBRATION_TARGET, PASS_ACCURACY

Z_95 = 1.96


@dataclass(frozen=True)
class Agreement:
    """Agreement between judge and user over `graded` answers, as shares from 0 to 1, with the 95% interval of the
    pass/fail share, and how many of the judge's passes and fails the user confirmed."""

    pass_fail: float
    pass_fail_low: float
    pass_fail_high: float
    within_one: float
    graded: int
    judge_passed: int
    passes_confirmed: int
    judge_failed: int
    fails_confirmed: int

    @property
    def target_reached(self) -> bool:
        return self.pass_fail >= CALIBRATION_TARGET


def shares(used: list[int], total: int) -> dict[int, int]:
    """`total` answers split equally over the scores the judge used, any remainder going to the lowest scores."""
    share, extra = divmod(total, len(used))
    return {score: share + (position < extra) for position, score in enumerate(used)}


def sample(scores: dict[str, int], total: int, seed: int) -> list[str]:
    """`total` answers to grade from one run's judge scores {test id: accuracy}, in shuffled order: an equal share for
    each score the judge used, and any score short of answers is filled from the nearest scores, the lower one first on
    a tie."""
    if len(scores) < total:
        raise ValueError(f"A run of {len(scores)} answers cannot give {total}")
    rng = random.Random(seed)
    used = sorted(set(scores.values()))
    wanted = shares(used, total)
    pools = {score: sorted(t for t, s in scores.items() if s == score) for score in used}
    for pool in pools.values():
        rng.shuffle(pool)
    chosen = {score: [pools[score].pop() for _ in range(min(wanted[score], len(pools[score])))] for score in used}
    for score in used:
        for nearest in sorted(used, key=lambda other: (abs(other - score), other)):
            while len(chosen[score]) < wanted[score] and pools[nearest]:
                chosen[score].append(pools[nearest].pop())
    picked = [test_id for group in chosen.values() for test_id in group]
    rng.shuffle(picked)
    return picked


def wilson(successes: int, total: int) -> tuple[float, float]:
    """The 95% Wilson score interval of a share, which stays sensible on small samples and near 0 or 1. Rounding can put
    the exact bound of 0 just below it, so the bounds are held within 0 and 1."""
    share, z2 = successes / total, Z_95 ** 2
    centre = (share + z2 / (2 * total)) / (1 + z2 / total)
    margin = Z_95 * sqrt(share * (1 - share) / total + z2 / (4 * total ** 2)) / (1 + z2 / total)
    return max(0.0, centre - margin), min(1.0, centre + margin)


def agreement(pairs: list[tuple[int, int]]) -> Agreement:
    """Agreement over (judge score, user score) pairs: on pass or fail overall and for each side of the judge's verdict,
    and within 1 point on the 1-5 scale."""
    same_side = [(judge >= PASS_ACCURACY) == (human >= PASS_ACCURACY) for judge, human in pairs]
    low, high = wilson(sum(same_side), len(pairs))
    passed = [human >= PASS_ACCURACY for judge, human in pairs if judge >= PASS_ACCURACY]
    failed = [human < PASS_ACCURACY for judge, human in pairs if judge < PASS_ACCURACY]
    return Agreement(pass_fail=mean(same_side), pass_fail_low=low, pass_fail_high=high,
                     within_one=mean(abs(judge - human) <= 1 for judge, human in pairs), graded=len(pairs),
                     judge_passed=len(passed), passes_confirmed=sum(passed),
                     judge_failed=len(failed), fails_confirmed=sum(failed))
