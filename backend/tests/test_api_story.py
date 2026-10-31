"""POST /api/story and GET /api/story/{stack} (T50): the page starts one step and reads where the ladder stands. Same
fakes as test_ladder_step.py (no network, no cost)."""

import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_ladder_step import BASE, S1_NEW, at_s6, finish, run_ids, world  # noqa: F401  (world is a fixture)

from rag_playground import jobs, main
from rag_playground.rag import ladder_step, prompts, runs
from rag_playground.rag.ladder import options
from rag_playground.scoring.selection import Candidate
from rag_playground.settings import LADDER_SIZES, settings

client = TestClient(main.app)
GOOD = {"mrr": 1.0, "recall": 1.0, "faithfulness": 5.0, "correct_refusal_rate": 1.0}


def job_count(world) -> int:
    return world.conn.execute("SELECT count(*) FROM jobs").fetchone()[0]


def click(world, **body):
    response = client.post("/api/story", json={"stack": "B", **body})
    finish(world)
    return response


def versions(world, *names):
    prompts.ensure_default(world.conn)
    for name in names:
        prompts.save(world.conn, name, f"Text of {name}.")


def test_a_click_starts_the_next_step_and_returns_its_job(world):
    response = click(world)
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert (job["kind"], job["status"], job["run_id"]) == ("ladder_step", "done", run_ids(world)[0])


def test_the_state_of_a_new_ladder_shows_s0_and_its_estimate(world):
    state = client.get("/api/story/B").json()
    assert (state["stack"], state["steps"], state["next_step"], state["needs_prompts"], state["job_id"]) == (
        "B", [], "S0", False, None)
    assert state["missing"] == [{"chunk_size": 1024, "overlap": 200, "top_k": 2, "answer_model": BASE.answer_model,
                                 "prompt_name": "default", "method": "fixed", "rerank": False}]
    assert state["estimate_usd"] == pytest.approx(ladder_step.run_cost(world.conn, BASE)) and state["estimate_usd"] > 0
    assert (state["enrichment_usd"], state["budget_left_usd"]) == (0, 1.0)


def test_the_state_after_a_step_shows_its_scores_and_the_next_estimate(world):
    """The fake search always returns the first question's document: rank 1 there, not found on the second, MRR 0.5.
    It never refuses, so the unanswerable question fails that gate too. Each question costs the fake $0.0015."""
    click(world)
    state = client.get("/api/story/B").json()
    (step,) = state["steps"]
    (tried,) = step["tried"]
    assert (step["step"], step["kept"], tried["config"]["chunk_size"]) == ("S0", tried["config"], 1024)
    assert (tried["kept"], tried["run_id"], tried["accuracy"], tried["failed_gates"]) == (
        True, run_ids(world)[0], 5.0, ["mrr", "recall", "correct_refusal_rate"])
    assert tried["mrr"] == pytest.approx(0.5) and tried["cost_per_question"] == pytest.approx(0.0015)
    assert state["next_step"] == "S1" and len(state["missing"]) == len(LADDER_SIZES) - 1
    assert state["estimate_usd"] == pytest.approx(ladder_step.step_cost(world.conn, S1_NEW))
    assert state["budget_left_usd"] < 1.0


def test_a_stack_has_only_its_own_ladder(world):
    click(world)
    state = client.get("/api/story/A").json()
    assert (state["stack"], state["steps"], state["next_step"]) == ("A", [], "S0")


def test_every_tried_option_is_shown_and_only_the_winner_is_kept(world, monkeypatch):
    """At S1 a smaller size has the higher accuracy, with a real gap, so it alone is marked."""
    def result(config):
        accuracy = {f"q{i}": 5.0 if config.chunk_size == 400 else 2.0 + i % 2 for i in range(30)}
        if config.chunk_size not in LADDER_SIZES or config.overlap != round(config.chunk_size * 200 / 1024):
            return None
        return Candidate(config.chunk_size, GOOD, accuracy, 0.001, {"q": 1.0})

    monkeypatch.setattr(ladder_step.ladder_runs, "finder", lambda conn, stack: result)
    s1 = client.get("/api/story/B").json()["steps"][1]
    assert [o["run_id"] for o in s1["tried"] if o["kept"]] == [400] == [s1["kept"]["chunk_size"]]
    assert len(s1["tried"]) == len(LADDER_SIZES)


def test_each_score_shown_is_that_run_s_own(world, monkeypatch):
    run = Candidate(7, {**GOOD, "mrr": 0.8, "recall": 0.9}, {"a": 4.0, "b": 2.0}, 0.003, {"a": 0.8})
    monkeypatch.setattr(ladder_step.ladder_runs, "finder", lambda conn, stack: lambda config: run)
    tried = client.get("/api/story/B").json()["steps"][0]["tried"][0]
    assert (tried["run_id"], tried["accuracy"], tried["mrr"], tried["cost_per_question"]) == (7, 3.0, 0.8, 0.003)


def test_a_failed_gate_is_shown(world, monkeypatch):
    bad = Candidate(1, {**GOOD, "faithfulness": 1.0}, {"q": 5.0}, 0.001, {"q": 1.0})
    monkeypatch.setattr(ladder_step.ladder_runs, "finder", lambda conn, stack: lambda config: bad)
    assert client.get("/api/story/B").json()["steps"][0]["tried"][0]["failed_gates"] == ["faithfulness"]


def test_s4_reports_its_enrichment_within_the_estimate(world, monkeypatch):
    """T49: the page must show the paid enrichment before the user confirms it."""
    world.enrich_cost = 0.25
    def result(config):
        return None if config.method != "fixed" else Candidate(1, GOOD, {"q": 3.0}, 0.001, {"q": 1.0})

    monkeypatch.setattr(ladder_step.ladder_runs, "finder", lambda conn, stack: result)
    state = client.get("/api/story/B").json()
    assert (state["next_step"], state["enrichment_usd"]) == ("S4", 0.25)
    run = ladder_step.run_cost(world.conn, options("S3", BASE, ())[0])
    assert state["estimate_usd"] == pytest.approx(run + 0.25)


def test_a_second_click_while_a_step_runs_gets_409_and_the_state_names_the_job(world):
    world.gate = threading.Event()
    job_id = client.post("/api/story", json={"stack": "B"}).json()["job_id"]
    response = client.post("/api/story", json={"stack": "B"})
    assert (response.status_code, response.json()["detail"]) == (409, "A ladder step is already running on Stack B")
    assert client.get("/api/story/B").json()["job_id"] == job_id
    assert client.get("/api/story/A").json()["job_id"] is None
    world.gate.set()
    finish(world)
    assert client.get("/api/story/B").json()["job_id"] is None
    assert len(run_ids(world)) == 1


def test_a_second_click_says_a_step_is_running_even_when_the_budget_is_used_up(world, monkeypatch):
    """The running step is the reason to wait, so it is reported before any estimate is worked out."""
    world.gate = threading.Event()
    client.post("/api/story", json={"stack": "B"})
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    response = client.post("/api/story", json={"stack": "B"})
    world.gate.set()
    finish(world)
    assert response.json()["detail"] == "A ladder step is already running on Stack B"


def test_the_click_that_loses_a_race_gets_409_not_a_crash(world, monkeypatch):
    """The other click stores its job after this one has passed the first check."""
    real = ladder_step.next_step

    def rival_first(conn, stack, names):
        jobs.insert(conn, "jobs", {"kind": "ladder_step", "stack": stack, "step": "S0", "runs_total": 1})
        return real(conn, stack, names)

    monkeypatch.setattr(ladder_step, "next_step", rival_first)
    response = client.post("/api/story", json={"stack": "B"})
    assert (response.status_code, response.json()["detail"]) == (409, "A ladder step is already running on Stack B")
    assert job_count(world) == 1


def test_the_s6_click_that_loses_a_race_gets_409_and_keeps_the_winners_choice(world, monkeypatch):
    at_s6(world, monkeypatch)
    versions(world, "v2", "v3")
    real = jobs.ladder_step.chosen_prompts

    def rival_saves(conn, stack):
        found = real(conn, stack)
        monkeypatch.setattr(jobs.ladder_step, "chosen_prompts", real)
        jobs.insert(conn, "ladder_prompts", {"stack": stack, "names": '["v2"]'})
        return found

    monkeypatch.setattr(jobs.ladder_step, "chosen_prompts", rival_saves)
    assert client.post("/api/story", json={"stack": "B", "prompts": ["v3"]}).status_code == 409
    assert ladder_step.chosen_prompts(world.conn, "B") == ("v2",)


def test_over_the_budget_gets_409_with_nothing_stored(world, monkeypatch):
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    response = click(world)
    assert response.status_code == 409 and "The step is estimated" in response.json()["detail"]
    assert (job_count(world), run_ids(world)) == (0, [])


def test_s6_without_prompts_asks_for_them(world, monkeypatch):
    at_s6(world, monkeypatch)
    state = client.get("/api/story/B").json()
    assert (state["next_step"], state["needs_prompts"], state["missing"], state["estimate_usd"]) == ("S6", True, [], 0)
    response = click(world)
    assert response.status_code == 422 and "Choose the prompt versions" in response.json()["detail"]
    assert job_count(world) == 0


def test_s6_previews_the_estimate_of_proposed_versions_without_saving_them(world, monkeypatch):
    at_s6(world, monkeypatch)
    versions(world, "v2", "v3")
    state = client.get("/api/story/B", params={"prompts": ["v2", "v3"]}).json()
    assert (state["needs_prompts"], [c["prompt_name"] for c in state["missing"]]) == (False, ["v2", "v3"])
    assert state["estimate_usd"] > 0
    assert ladder_step.chosen_prompts(world.conn, "B") is None


def test_s6_runs_the_versions_sent_with_the_click(world, monkeypatch):
    at_s6(world, monkeypatch)
    versions(world, "v2")
    assert click(world, prompts=["v2"]).status_code == 202
    assert ladder_step.chosen_prompts(world.conn, "B") == ("v2",)
    assert runs.get_run(world.conn, run_ids(world)[0]).meta.prompt_name == "v2"


def test_an_empty_list_skips_s6(world, monkeypatch):
    at_s6(world, monkeypatch)
    click(world, prompts=[])
    assert ladder_step.chosen_prompts(world.conn, "B") == ()


def test_a_saved_choice_outranks_a_preview(world, monkeypatch):
    at_s6(world, monkeypatch)
    versions(world, "v2", "v3")
    jobs.insert(world.conn, "ladder_prompts", {"stack": "B", "names": '["v2"]'})
    state = client.get("/api/story/B", params={"prompts": ["v3"]}).json()
    assert [c["prompt_name"] for c in state["missing"]] == ["v2"]


def test_an_unknown_prompt_version_gets_404_from_both_routes(world, monkeypatch):
    at_s6(world, monkeypatch)
    assert client.get("/api/story/B", params={"prompts": ["nope"]}).status_code == 404
    response = click(world, prompts=["nope"])
    assert (response.status_code, response.json()["detail"]) == (404, "Not found: nope")
    assert ladder_step.chosen_prompts(world.conn, "B") is None


def test_more_than_four_versions_get_422_from_both_routes(world, monkeypatch):
    at_s6(world, monkeypatch)
    names = ["a", "b", "c", "d", "e"]
    assert client.get("/api/story/B", params={"prompts": names}).status_code == 422
    assert click(world, prompts=names).status_code == 422


def test_a_finished_ladder_gets_422_and_shows_no_next_step(world, monkeypatch):
    monkeypatch.setattr(ladder_step, "progress", lambda conn, stack: SimpleNamespace(next_step=None, missing=[]))
    response = click(world)
    assert response.status_code == 422 and "finished" in response.json()["detail"]
    good = Candidate(1, GOOD, {"q": 3.0}, 0.001, {"q": 1.0})
    monkeypatch.setattr(ladder_step.ladder_runs, "finder", lambda conn, stack: lambda config: good)
    versions(world)
    jobs.insert(world.conn, "ladder_prompts", {"stack": "B", "names": "[]"})
    state = client.get("/api/story/B").json()
    assert (state["next_step"], state["needs_prompts"], state["missing"], state["estimate_usd"]) == (None, False, [], 0)
    assert [s["step"] for s in state["steps"]] == ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7"]


@pytest.mark.parametrize("body", [{}, {"stack": "C"}, {"stack": "B", "extra": 1}, {"stack": "B", "prompts": "v2"},
                                  {"stack": "B", "prompts": [1]}])
def test_an_invalid_request_is_refused_with_nothing_stored(world, body):
    assert client.post("/api/story", json=body).status_code == 422
    assert job_count(world) == 0


def test_an_unknown_stack_is_refused_when_reading(world):
    assert client.get("/api/story/C").status_code == 422
