"""Held-out confirmation (plan.md 3.3, T18). Same fakes as test_ladder_step.py (no network, no cost); the ladder is made
to look finished, and the confirmation's runs are real rows, through the real worker thread."""

import threading

import pytest
from fastapi.testclient import TestClient
from test_ladder_step import ALL_DEV, BASE, CHUNK, DEV, GOLD_CHUNKS, finish, run_ids, world  # noqa: F401

from rag_playground import jobs, main
from rag_playground.datasets.schema import load_tests
from rag_playground.rag import best_run, heldout, ladder_runs, ladder_step, pipeline, prompts, runs
from rag_playground.rag.ladder import Decision, Progress
from rag_playground.scoring.selection import Candidate
from rag_playground.settings import settings

client = TestClient(main.app)
GOOD = {"mrr": 1.0, "recall": 1.0, "faithfulness": 5.0, "correct_refusal_rate": 1.0}
ALL_HELD = [t for t in load_tests() if t.split == "heldout"]
HELD = [t for t in ALL_HELD if t.source_docs][:2] + [t for t in ALL_HELD if not t.source_docs][:1]
URL = "/api/story/B/heldout"


@pytest.fixture
def held(world, monkeypatch):
    """The held-out list cut to 3 questions, and their documents known to the scoring."""
    monkeypatch.setattr(heldout, "tests", lambda: HELD)
    for module in (pipeline, best_run):
        monkeypatch.setattr(module, "load_tests", lambda: DEV + HELD)
    gold = [CHUNK.model_copy(update={"source": s}) for t in HELD for s in t.source_docs]
    monkeypatch.setattr(best_run, "load_chunk_set", lambda set_id: GOLD_CHUNKS + gold)
    return world


def finished(world, monkeypatch, winner: int | None = 400) -> None:
    """Every dev run exists and the ladder is finished; S1 really prefers `winner`, or nothing beats S0 if None."""
    def result(config):
        best = config == BASE if winner is None else config.chunk_size == winner
        accuracy = {f"q{i}": 5.0 if best else 2.0 + i % 2 for i in range(30)}
        return Candidate(config.chunk_size, GOOD, accuracy, 0.001, {"q": 1.0})

    monkeypatch.setattr(ladder_step.ladder_runs, "finder", lambda conn, stack: result)
    prompts.ensure_default(world.conn)
    jobs.insert(world.conn, "ladder_prompts", {"stack": "B", "names": "[]"})


def click(world):
    response = client.post(URL)
    finish(world)
    return response


def final(world):
    return ladder_step.progress(world.conn, "B").decisions[-1].kept


def metas(world):
    return [runs.get_run(world.conn, i).meta for i in run_ids(world)]


def statuses(world):
    return [runs.get_run(world.conn, i).status for i in run_ids(world)]


def test_the_real_held_out_list_has_all_48_questions_and_no_dev_one():
    assert len(heldout.tests()) == 48 and {t.split for t in heldout.tests()} == {"heldout"}
    assert not {t.id for t in heldout.tests()} & {t.id for t in ALL_DEV}


def test_confirmation_runs_s0_and_the_final_configuration_on_the_held_out_questions(held, monkeypatch):
    finished(held, monkeypatch)
    assert final(held).chunk_size == 400
    response = click(held)
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert (job["status"], job["error"]) == ("done", None)
    made = metas(held)
    assert [m.chunk_set_id for m in made] == ["fixed__c1024__o200", ladder_runs.choices("B", final(held)).chunk_set_id]
    assert all(m.split == "heldout" and sorted(m.test_ids) == sorted(t.id for t in HELD) for m in made)


def test_the_job_says_it_is_the_confirmation(held, monkeypatch):
    finished(held, monkeypatch)
    held.gate = threading.Event()
    job_id = client.post(URL).json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}").json()["message"].startswith("held-out on Stack B")
    held.gate.set()
    finish(held)


def test_a_ladder_that_kept_s0_runs_it_once(held, monkeypatch):
    finished(held, monkeypatch, winner=None)
    click(held)
    assert [m.chunk_set_id for m in metas(held)] == ["fixed__c1024__o200"]
    panel = client.get("/api/story/B").json()["heldout"]
    assert (len(panel["runs"]), panel["missing"], panel["gain"]) == (1, [], None)


def test_the_ladder_must_be_finished_first(held):
    response = click(held)
    assert response.status_code == 422 and "Finish the ladder on Stack B first" in response.json()["detail"]
    assert run_ids(held) == []
    assert client.get("/api/story/B").json()["heldout"] is None


def test_a_ladder_part_way_through_cannot_be_confirmed(held):
    """S0 is done and the ladder is at S1: no final configuration exists yet."""
    client.post("/api/story", json={"stack": "B"})
    finish(held)
    assert client.get("/api/story/B").json()["heldout"] is None
    response = click(held)
    assert response.status_code == 422 and "its next step is S1" in response.json()["detail"]


def test_a_confirmed_stack_is_not_run_again(held, monkeypatch):
    """Held-out questions must not be re-rolled until a number looks better, and a repeat would pay again."""
    finished(held, monkeypatch)
    click(held)
    before = run_ids(held)
    response = click(held)
    assert response.status_code == 422 and "already confirmed" in response.json()["detail"]
    assert run_ids(held) == before


def test_after_a_failure_a_click_pays_only_for_what_is_left(held, monkeypatch):
    finished(held, monkeypatch)
    held.fail_at = len(HELD) + 1
    job_id = click(held).json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "failed"
    panel = client.get("/api/story/B").json()["heldout"]
    assert [r["config"]["chunk_size"] for r in panel["runs"]] == [1024]
    assert [c["chunk_size"] for c in panel["missing"]] == [400]
    held.fail_at = None
    click(held)
    assert statuses(held) == ["done", "failed", "done"]


def test_a_held_out_run_never_competes_with_dev_runs(held, monkeypatch):
    finished(held, monkeypatch)
    click(held)
    assert len(best_run.candidates(held.conn, "heldout")) == 2
    assert best_run.candidates(held.conn) == [] and best_run.best_run(held.conn) is None


def test_each_lookup_reads_only_its_own_split(held):
    jobs.submit_step(held.conn, "B")
    finish(held)
    assert ladder_runs.heldout_finder(held.conn, "B")(BASE) is None
    assert ladder_runs.lookup(held.conn, "B", "dev")(BASE).run_id == run_ids(held)[0]


def test_over_the_budget_is_refused_with_nothing_stored(held, monkeypatch):
    finished(held, monkeypatch)
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    response = click(held)
    assert response.status_code == 409 and "The step is estimated" in response.json()["detail"]
    assert run_ids(held) == [] and held.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_the_estimate_counts_the_held_out_questions_not_the_dev_ones(held, monkeypatch):
    finished(held, monkeypatch)
    monkeypatch.setattr(heldout, "tests", lambda: HELD[:1])
    panel = client.get("/api/story/B").json()["heldout"]
    configs = heldout.configurations(ladder_step.progress(held.conn, "B"))
    expected = sum(ladder_step.run_cost(held.conn, "B", c, HELD[:1]) for c in configs)
    assert panel["estimate_usd"] == pytest.approx(expected)
    assert expected < sum(ladder_step.run_cost(held.conn, "B", c) for c in configs)


def test_the_budget_check_also_counts_the_held_out_questions(held, monkeypatch):
    """Dev's 3 questions would be over this budget, the single held-out one is not."""
    finished(held, monkeypatch)
    monkeypatch.setattr(heldout, "tests", lambda: HELD[:1])
    configs = heldout.configurations(ladder_step.progress(held.conn, "B"))
    cheap = sum(ladder_step.run_cost(held.conn, "B", c, HELD[:1]) for c in configs)
    monkeypatch.setattr(settings, "budget_usd", cheap * 1.5)
    assert [c.chunk_size for c in heldout.next_runs(held.conn, "B")] == [1024, 400]


def test_a_running_confirmation_blocks_a_second_click_and_a_ladder_step(held, monkeypatch):
    finished(held, monkeypatch)
    held.gate = threading.Event()
    client.post(URL)
    assert client.post(URL).status_code == 409
    assert client.post("/api/story", json={"stack": "B"}).status_code == 409
    assert client.get("/api/story/B").json()["job_id"] is not None
    held.gate.set()
    finish(held)


def test_the_panel_shows_both_runs_and_marks_the_final_one(held, monkeypatch):
    finished(held, monkeypatch)
    click(held)
    panel = client.get("/api/story/B").json()["heldout"]
    assert [(r["config"]["chunk_size"], r["kept"], r["run_id"]) for r in panel["runs"]] == [
        (1024, False, run_ids(held)[0]), (400, True, run_ids(held)[1])]
    assert (panel["missing"], panel["estimate_usd"]) == ([], 0)
    assert panel["gain"]["accuracy"] == {"low": 0, "high": 0, "real": False}


def test_the_panel_gain_is_the_final_configuration_minus_s0_for_each_score(held, monkeypatch):
    """Accuracy up by 1 and MRR down by 0.25 on every question: a swap of the runs or of the scores shows."""
    finished(held, monkeypatch)
    stored = {1024: run([3.0, 4.0], [1.0, 0.75]), 400: run([4.0, 5.0], [0.75, 0.5])}
    monkeypatch.setattr(ladder_runs, "heldout_finder", lambda conn, stack: lambda c: stored[c.chunk_size])
    gain = client.get("/api/story/B").json()["heldout"]["gain"]
    assert gain == {"accuracy": {"low": 1.0, "high": 1.0, "real": True},
                    "mrr": {"low": -0.25, "high": -0.25, "real": False}}


def test_no_questions_estimate_nothing(held, monkeypatch):
    finished(held, monkeypatch)
    assert ladder_step.run_cost(held.conn, "B", BASE, []) == 0


def test_a_finished_ladder_shows_the_estimate_before_any_held_out_run(held, monkeypatch):
    finished(held, monkeypatch)
    panel = client.get("/api/story/B").json()["heldout"]
    assert (panel["runs"], panel["gain"]) == ([], None)
    assert [c["chunk_size"] for c in panel["missing"]] == [1024, 400] and panel["estimate_usd"] > 0


def test_an_invalid_stack_is_refused(held):
    assert client.post("/api/story/C/heldout").status_code == 422


def run(accuracy: list[float], mrr: list[float]) -> Candidate:
    return Candidate(1, GOOD, {f"q{i}": a for i, a in enumerate(accuracy)}, 0.001,
                     {f"q{i}": m for i, m in enumerate(mrr)})


def test_a_constant_gain_is_real_and_exact():
    gain = heldout.gain(run([3.0, 4.0], [0.5, 0.5]), run([4.0, 5.0], [0.5, 0.5]))
    assert gain["accuracy"] == {"low": 1.0, "high": 1.0, "real": True}
    assert gain["mrr"] == {"low": 0, "high": 0, "real": False}


def test_a_gain_whose_interval_crosses_zero_is_not_real():
    """Half the questions better, half worse: the honest report is that nothing was shown."""
    change = heldout.change({f"q{i}": 3.0 for i in range(20)}, {f"q{i}": 4.0 if i % 2 else 2.0 for i in range(20)})
    assert change["low"] < 0 < change["high"] and change["real"] is False


def test_a_ladder_that_changed_nothing_has_one_configuration():
    decision = Decision("S0", [BASE], BASE)
    assert heldout.configurations(Progress([decision, decision], None, [])) == [BASE]


def test_a_stack_a_confirmation_counts_the_search_fee(held, monkeypatch):
    """T53: every held-out run pays it; a budget between the two estimates stops only Stack A."""
    finished(held, monkeypatch)
    configs = heldout.configurations(ladder_step.progress(held.conn, "B"))
    jobs.insert(held.conn, "ladder_prompts", {"stack": "A", "names": "[]"})
    estimate_a = client.get("/api/story/A").json()["heldout"]["estimate_usd"]
    estimate_b = client.get("/api/story/B").json()["heldout"]["estimate_usd"]
    assert estimate_a - estimate_b == pytest.approx(len(configs) * len(HELD) * 0.0025)
    monkeypatch.setattr(settings, "budget_usd", (estimate_a + estimate_b) / 2)
    refused = client.post("/api/story/A/heldout")
    assert refused.status_code == 409 and "The step is estimated" in refused.json()["detail"]
    assert click(held).status_code == 202
