"""Step 8 checks of the calibration sample and the agreement figures (T20, T48), with hand-built scores."""

from collections import Counter

import pytest

from rag_playground.scoring import calibration


def run(**counts: int) -> dict[str, int]:
    """Judge scores of a run, from counts such as s1=4 for four answers scored 1."""
    return {f"q{score}-{i}": int(score[1]) for score, count in counts.items() for i in range(count)}


FULL = run(s1=10, s2=10, s3=10, s4=10, s5=100)


def picked_scores(scores: dict[str, int], **kwargs) -> Counter:
    return Counter(scores[test_id] for test_id in calibration.sample(scores, 3, seed=7, **kwargs))


@pytest.mark.parametrize("successes, total, low, high", [
    (24, 30, 0.6269, 0.9050),  # centre 0.76595, margin 0.13900
    (30, 30, 0.8865, 1.0),  # all agree: n / (n + z^2)
    (0, 30, 0.0, 0.1135),
    (1, 2, 0.0945, 0.9055),
])
def test_wilson_interval_matches_hand_computed_values(successes, total, low, high):
    assert calibration.wilson(successes, total) == pytest.approx((low, high), abs=0.0001)


def test_every_score_gets_its_equal_share():
    assert picked_scores(FULL) == {1: 3, 2: 3, 3: 3, 4: 3, 5: 3}


def test_a_missing_score_is_filled_from_the_nearest_score():
    assert picked_scores(run(s2=10, s3=10, s4=10, s5=10)) == {2: 6, 3: 3, 4: 3, 5: 3}


def test_a_partly_filled_score_takes_only_what_it_lacks_from_the_nearest():
    assert picked_scores(run(s1=1, s2=10, s3=10, s4=10, s5=10)) == {1: 1, 2: 5, 3: 3, 4: 3, 5: 3}


def test_a_tie_between_two_nearest_scores_goes_to_the_lower_one():
    assert picked_scores(run(s1=10, s2=10, s4=10, s5=10)) == {1: 3, 2: 6, 4: 3, 5: 3}


def test_a_fill_reaches_further_when_the_nearest_score_runs_out():
    assert picked_scores(run(s2=4, s3=4, s5=20)) == {2: 4, 3: 4, 5: 7}


def test_the_sample_has_no_repeats_and_comes_only_from_the_run():
    chosen = calibration.sample(FULL, 3, seed=7)
    assert len(chosen) == len(set(chosen)) == 15 and set(chosen) <= set(FULL)


def test_a_run_with_too_few_answers_is_refused():
    with pytest.raises(ValueError):
        calibration.sample(run(s5=14), 3, seed=7)


def test_the_same_seed_gives_the_same_sample_in_any_input_order():
    shuffled = dict(reversed(FULL.items()))
    assert calibration.sample(FULL, 3, seed=7) == calibration.sample(shuffled, 3, seed=7)


def test_another_seed_gives_another_sample():
    """Other answers, not only the same answers in another order."""
    assert set(calibration.sample(FULL, 3, seed=7)) != set(calibration.sample(FULL, 3, seed=8))


def test_the_order_does_not_reveal_the_score():
    """The chosen answers come shuffled, not lowest score first."""
    chosen = calibration.sample(FULL, 3, seed=7)
    order = [FULL[test_id] for test_id in chosen]
    assert order != sorted(order)


@pytest.mark.parametrize("judge, human, expected", [
    (5, 5, 1.0), (5, 4, 1.0), (4, 5, 1.0), (3, 2, 1.0), (1, 2, 1.0),  # same side of the line
    (4, 3, 0.0), (3, 4, 0.0), (5, 1, 0.0), (1, 5, 0.0),  # opposite sides: 4 and above pass
])
def test_pass_fail_agreement_is_about_the_line_at_4(judge, human, expected):
    assert calibration.agreement([(judge, human)]).pass_fail == expected


@pytest.mark.parametrize("judge, human, expected", [(3, 3, 1.0), (3, 4, 1.0), (3, 2, 1.0), (3, 5, 0.0), (3, 1, 0.0)])
def test_within_one_allows_a_gap_of_one_and_no_more(judge, human, expected):
    assert calibration.agreement([(judge, human)]).within_one == expected


def test_agreement_is_the_share_over_all_grades():
    """Pass/fail differs only on (4, 3); within one fails only on (1, 3)."""
    result = calibration.agreement([(5, 5), (4, 3), (2, 1), (1, 3)])
    assert (result.pass_fail, result.within_one, result.graded) == (3 / 4, 3 / 4, 4)


@pytest.mark.parametrize("pairs, reached", [([(5, 5)] * 8 + [(5, 1)] * 2, True), ([(5, 5)] * 7 + [(4, 3)] * 3, False)])
def test_the_target_needs_at_least_80_percent_pass_fail_agreement(pairs, reached):
    """The second case is 100% within one point, so only pass/fail can fail it."""
    assert calibration.agreement(pairs).target_reached is reached
