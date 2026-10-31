"""The ladder's steps and decisions (plan.md 3.1, T49, T50), with hand-built results and no database."""

import pytest

from rag_playground.rag.ladder import STEPS, Config, baseline, options, walk
from rag_playground.scoring.selection import Candidate
from rag_playground.settings import LADDER_OVERLAP_SHARES, LADDER_SIZES, LADDER_STRONG_MODEL, S0

QUESTIONS = [f"q{i}" for i in range(20)]
PASSING = {"mrr": 0.9, "recall": 0.9, "faithfulness": 4.5, "correct_refusal_rate": 0.9}
FAILING = {**PASSING, "faithfulness": 3.0}
BASE = baseline("default")


def scores(value: float) -> dict[str, float]:
    return {q: value for q in QUESTIONS}


def noise(value: float, flip: bool = False) -> dict[str, float]:
    """A mean of `value`, 2 above or below it per question. `flip` swaps which questions are above, so two runs differ
    by about 4 either way on every question and a gap of 0.1 between their means is not real."""
    return {q: value + (2 if (i % 2 == 0) == flip else -2) for i, q in enumerate(QUESTIONS)}


class Results:
    """Stored results: every configuration is finished at accuracy 3 and MRR 0.9 unless `special` says otherwise."""

    def __init__(self, special: dict | None = None, absent=lambda config: False):
        self.special, self.absent, self.ids = special or {}, absent, {}

    def __call__(self, config: Config) -> Candidate | None:
        if self.absent(config):
            return None
        run_id = self.ids.setdefault(config, len(self.ids) + 1)
        overrides = self.special.get(config, {})
        return Candidate(run_id, overrides.get("gates", PASSING), overrides.get("accuracy", scores(3.0)),
                         overrides.get("cost", 0.001), overrides.get("mrr", scores(0.9)))


def kept(progress, step: str) -> Config:
    return next(d.kept for d in progress.decisions if d.step == step)


def test_walk_stops_at_s0_without_a_baseline_run():
    progress = walk(Results(absent=lambda c: True), "default")
    assert (progress.decisions, progress.next_step, progress.missing) == ([], "S0", [BASE])


def test_walk_lists_only_the_missing_options_of_the_next_step():
    """A stored run is reused: S1's 1,024-token option is S0's own run, so it is not listed."""
    progress = walk(Results(absent=lambda c: c != BASE), "default")
    assert progress.next_step == "S1"
    assert [c.chunk_size for c in progress.missing] == [s for s in LADDER_SIZES if s != S0["chunk_size"]]


def test_size_sweep_keeps_the_s0_overlap_share():
    """plan.md section 3: 200/1024 of each size; the 1,024 option is S0 itself."""
    assert [(c.chunk_size, c.overlap) for c in options("S1", BASE, ())] == [
        (100, 20), (200, 39), (400, 78), (800, 156), (1024, 200), (1600, 312)]


@pytest.mark.parametrize("size", LADDER_SIZES)
def test_overlap_options_are_distinct_at_every_size(size):
    tried = options("S2", Config(size, 0, 2, "m", "p"), ())
    assert len({c.overlap for c in tried}) == len(LADDER_OVERLAP_SHARES)


def test_overlap_options_are_at_the_kept_size():
    assert [c.overlap for c in options("S2", Config(400, 78, 2, "m", "p"), ())] == [0, 78, 100]


@pytest.mark.parametrize("kept_size", options("S1", BASE, ()))
def test_overlap_step_reuses_the_size_sweep_run(kept_size):
    """plan.md 3.4: S2's about-20% option is the run S1 already has, so it must be the same configuration."""
    assert kept_size in options("S2", kept_size, ())


def test_s4_option_is_the_enriched_method_on_the_same_chunk_set():
    """The literal the API and `RunRequest` accept, not this module's own constant."""
    assert options("S4", BASE, ())[1] == Config(1024, 200, 2, BASE.answer_model, "default", method="llm_enriched")


def test_s5_option_turns_reranking_on_and_changes_nothing_else():
    assert options("S5", BASE, ())[1] == Config(1024, 200, 2, BASE.answer_model, "default", rerank=True)


def test_top_k_options_are_at_the_kept_chunk_set():
    tried = options("S3", Config(400, 100, 2, "m", "p"), ())
    assert [(c.chunk_size, c.overlap, c.top_k) for c in tried] == [(400, 100, 2), (400, 100, 4), (400, 100, 6),
                                                                  (400, 100, 8)]


def test_s6_tries_the_kept_prompt_and_the_chosen_versions_once_each():
    assert [c.prompt_name for c in options("S6", BASE, ("default", "v2"))] == ["default", "v2"]


def test_s1_keeps_a_really_better_size_and_later_steps_build_on_it():
    better = options("S1", BASE, ())[2]
    progress = walk(Results({better: {"accuracy": scores(4.0)}}, absent=lambda c: c.top_k == 4), "default")
    assert kept(progress, "S1") == better
    assert progress.next_step == "S3"
    assert {(c.chunk_size, c.top_k) for c in progress.missing} == {(400, 4)}


def test_s1_a_tie_goes_to_the_cheaper_size():
    """T50 uses T08: a gap that is not real is a tie, and the cheapest tied run wins."""
    leader, cheap = options("S1", BASE, ())[4], options("S1", BASE, ())[1]
    special = {c: {"accuracy": noise(3.0), "cost": 0.002} for c in options("S1", BASE, ())}
    special[leader] = {"accuracy": noise(3.1, flip=True), "cost": 0.002}
    special[cheap] = {"accuracy": noise(3.0), "cost": 0.001}
    assert kept(walk(Results(special), "default"), "S1") == cheap


def test_s1_ignores_the_best_score_if_it_fails_a_gate():
    trap = options("S1", BASE, ())[0]
    assert kept(walk(Results({trap: {"accuracy": scores(5.0), "gates": FAILING}}), "default"), "S1") == BASE


def test_s1_keeps_the_starting_setting_if_no_option_passes_the_gates():
    special = {c: {"gates": FAILING} for c in options("S1", BASE, ())}
    assert kept(walk(Results(special), "default"), "S1") == BASE


@pytest.mark.parametrize("step", ["S4", "S5"])
@pytest.mark.parametrize("gain", ["accuracy", "mrr"])
def test_one_option_step_keeps_a_real_gain_in_accuracy_or_mrr(step, gain):
    """T49. The gain on MRR alone counts as well as the gain on accuracy."""
    option = options(step, BASE, ())[1]
    better = {"accuracy": scores(4.0)} if gain == "accuracy" else {"mrr": scores(1.0)}
    assert kept(walk(Results({option: better}), "default"), step) == option


@pytest.mark.parametrize("step", ["S4", "S5"])
def test_one_option_step_without_a_real_gain_continues_from_the_step_before(step):
    option = options(step, BASE, ())[1]
    assert kept(walk(Results({option: {"accuracy": noise(3.1, flip=True)}, BASE: {"accuracy": noise(3.0)}}), "default"),
                step) == BASE


def test_one_option_step_refuses_a_gain_that_fails_a_gate():
    option = options("S5", BASE, ())[1]
    assert kept(walk(Results({option: {"accuracy": scores(4.0), "gates": FAILING}}), "default"), "S5") == BASE


def test_s4_is_kept_for_the_later_steps():
    enriched = options("S4", BASE, ())[1]
    progress = walk(Results({enriched: {"accuracy": scores(4.0)}}, absent=lambda c: c.rerank), "default")
    assert progress.next_step == "S5"
    assert progress.missing == [Config(**{**enriched.__dict__, "rerank": True})]


def test_walk_stops_at_s6_until_the_prompts_are_chosen():
    progress = walk(Results(), "default")
    assert (progress.next_step, progress.missing) == ("S6", [])
    assert [d.step for d in progress.decisions] == list(STEPS[:6])


def test_s6_with_no_extra_prompt_moves_on():
    progress = walk(Results(absent=lambda c: c.answer_model == LADDER_STRONG_MODEL), "default", ())
    assert progress.next_step == "S7"


def test_s6_keeps_the_better_prompt():
    version = options("S6", BASE, ("v2",))[1]
    assert kept(walk(Results({version: {"accuracy": scores(4.0)}}), "default", ("v2",)), "S6") == version


def test_s7_is_reported_but_never_kept_even_when_better():
    strong = options("S7", BASE, ())[1]
    progress = walk(Results({strong: {"accuracy": scores(5.0)}}), "default", ())
    assert kept(progress, "S7") == BASE
    assert progress.decisions[-1].tried == [BASE, strong]
    assert progress.next_step is None


def test_exactly_four_prompt_versions_are_accepted():
    progress = walk(Results(), "default", ("a", "b", "c", "d"))
    assert [c.prompt_name for c in progress.decisions[6].tried] == ["default", "a", "b", "c", "d"]


def test_more_than_four_prompt_versions_are_refused():
    with pytest.raises(ValueError, match="at most 4"):
        walk(Results(), "default", ("a", "b", "c", "d", "e"))
