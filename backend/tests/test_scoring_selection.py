"""Step 5 checks for refusal rates, gates and the paired bootstrap, with hand-built inputs."""

import pytest

from rag_playground.datasets import schema
from rag_playground.scoring import selection, trust

PASSING = {"mrr": 0.75, "recall": 0.80, "faithfulness": 4.0, "correct_refusal_rate": 0.80}


def case(test_id: str, category: str) -> schema.TestCase:
    return schema.TestCase(id=test_id, question="q", reference_answer="a", category=category,
                           source_docs=[] if category == "unanswerable" else ["d.md"], keywords=["k"], split="dev")


TESTS = [case("u1", "unanswerable"), case("u2", "unanswerable"), case("u3", "unanswerable"), case("u4", "unanswerable"),
         case("a1", "direct_fact"), case("a2", "numerical"), case("a3", "temporal"), case("a4", "multi_doc"),
         case("a5", "comparative")]
REFUSED = {"u1": True, "u2": True, "u3": True, "u4": False,
           "a1": False, "a2": True, "a3": False, "a4": False, "a5": False}


def test_correct_refusal_rate_counts_refused_unanswerable_questions():
    assert trust.correct_refusal_rate(TESTS, REFUSED) == 3 / 4


def test_false_refusal_rate_counts_refused_answerable_questions():
    assert trust.false_refusal_rate(TESTS, REFUSED) == 1 / 5


def test_scores_exactly_at_every_minimum_pass_the_gates():
    assert selection.failed_gates(PASSING) == []


@pytest.mark.parametrize("name, value", [("faithfulness", 3.9), ("correct_refusal_rate", 0.7),
                                         ("mrr", 0.74), ("recall", 0.79)])
def test_a_score_below_its_minimum_fails_that_gate_only(name, value):
    assert selection.failed_gates({**PASSING, name: value}) == [name]


def scores(values: list[float]) -> dict[str, float]:
    return {f"q{i:03}": v for i, v in enumerate(values)}


BEFORE = scores([1, 2, 3, 4, 5] * 40)


def test_identical_runs_give_an_interval_containing_zero():
    low, high = selection.paired_bootstrap(BEFORE, BEFORE)
    assert low <= 0 <= high
    assert not selection.is_real_improvement(BEFORE, BEFORE)


def test_plus_one_on_every_question_gives_an_interval_above_zero():
    after = {q: v + 1 for q, v in BEFORE.items()}
    assert selection.paired_bootstrap(BEFORE, after) == (1.0, 1.0)
    assert selection.is_real_improvement(BEFORE, after)


def test_changes_that_cancel_out_are_not_a_real_improvement():
    """Half the questions gain 1 and half lose 1: mean change 0, so the interval straddles 0."""
    after = {q: v + (1 if i % 2 else -1) for i, (q, v) in enumerate(BEFORE.items())}
    low, high = selection.paired_bootstrap(BEFORE, after)
    assert low < 0 < high
    assert not selection.is_real_improvement(BEFORE, after)


def test_a_small_consistent_gain_is_real_and_its_interval_holds_the_mean_gain():
    """180 questions gain 1 and 20 lose 1: mean gain 0.8; the interval is narrow around it."""
    after = {q: v + (-1 if i < 20 else 1) for i, (q, v) in enumerate(BEFORE.items())}
    low, high = selection.paired_bootstrap(BEFORE, after)
    assert 0 < low < 0.8 < high
    assert selection.is_real_improvement(BEFORE, after)


def test_the_interval_is_reproducible_with_the_fixed_seed():
    after = {q: v + (1 if i % 3 else -1) for i, (q, v) in enumerate(BEFORE.items())}
    assert selection.paired_bootstrap(BEFORE, after) == selection.paired_bootstrap(BEFORE, after)


def test_runs_on_different_questions_are_rejected():
    with pytest.raises(ValueError):
        selection.paired_bootstrap(BEFORE, {**BEFORE, "extra": 1.0})


def candidate(run_id: int, accuracy: dict[str, float], cost: float, gate_scores: dict | None = None):
    return selection.Candidate(run_id, gate_scores or PASSING, accuracy, cost)


LOW = scores([3] * 200)
HIGH = scores([5] * 200)
SLIGHTLY_HIGHER = {q: v + (1 if i % 2 else -0.9) for i, (q, v) in enumerate(scores([3] * 200).items())}


def test_no_run_means_no_best_run():
    assert selection.pick_best([]) is None


def test_no_best_run_when_every_run_fails_a_gate():
    assert selection.pick_best([candidate(1, HIGH, 0.1, {**PASSING, "mrr": 0.1})]) is None


def test_the_highest_accuracy_wins_when_the_difference_is_real_even_if_it_costs_more():
    assert selection.pick_best([candidate(1, LOW, 0.01), candidate(2, HIGH, 0.09)]).run_id == 2


def test_a_run_failing_a_gate_cannot_win_however_accurate_it_is():
    failing = candidate(1, HIGH, 0.01, {**PASSING, "faithfulness": 3.9})
    assert selection.pick_best([failing, candidate(2, LOW, 0.09)]).run_id == 2


def test_the_cheaper_run_wins_when_the_accuracy_difference_is_not_real():
    """Run 2 leads by 0.05 on average, but half its questions got worse: the difference is not real."""
    assert selection.mean(SLIGHTLY_HIGHER.values()) > selection.mean(LOW.values())
    assert not selection.is_real_improvement(LOW, SLIGHTLY_HIGHER)
    assert selection.pick_best([candidate(1, LOW, 0.01), candidate(2, SLIGHTLY_HIGHER, 0.09)]).run_id == 1
    assert selection.pick_best([candidate(1, LOW, 0.09), candidate(2, SLIGHTLY_HIGHER, 0.01)]).run_id == 2


def test_a_cheap_run_really_worse_than_the_leader_does_not_win_on_price():
    """Run 3 ties the leader on nothing; only runs tied with the leader compete on cost."""
    picked = selection.pick_best([candidate(1, HIGH, 0.09), candidate(2, HIGH, 0.05), candidate(3, LOW, 0.01)])
    assert picked.run_id == 2


def test_tied_runs_at_the_same_cost_go_to_the_higher_accuracy():
    assert selection.pick_best([candidate(1, LOW, 0.05), candidate(2, SLIGHTLY_HIGHER, 0.05)]).run_id == 2


def test_same_accuracy_and_same_cost_pick_the_oldest_run_in_any_order():
    first, second = candidate(1, HIGH, 0.05), candidate(2, HIGH, 0.05)
    assert selection.pick_best([first, second]).run_id == 1
    assert selection.pick_best([second, first]).run_id == 1
