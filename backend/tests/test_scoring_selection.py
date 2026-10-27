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
