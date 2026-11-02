"""T58: planning a one-setting sweep. Stored runs and prices are faked, so each test sets exactly what has run and
what a run costs (no network, no cost). The lookup of stored runs itself is the ladder's, tested in test_ladder_step."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rag_playground import main, store
from dataclasses import replace

from rag_playground.rag import best_run, builds, ladder_runs, prompts, runs, sweeps
from rag_playground.rag.runs import insert
from rag_playground.scoring.selection import Candidate
from rag_playground.settings import settings
from rag_playground.sweep_requests import SweepRequest
from test_runs import STACK_A

BASE_B = {"stack": "B", "chunking_method": "fixed", "chunk_size": 400, "overlap": 78, "top_k": 2, "hybrid": False,
          "rerank": False, "answer_model": "openai/gpt-4.1-nano", "prompt_name": "default"}
RANKING = {"ranker": "auto", "embedding_weight": 1.0, "text_weight": 1.0, "score_threshold": 0.0}
BASE_A = {**{k: v for k, v in BASE_B.items() if k != "hybrid"}, "stack": "A", "openai_ranking": RANKING}
QUESTIONS = [f"q{i}" for i in range(40)]


def candidate(run_id: int, accuracy: float, mrr: float = 0.9) -> Candidate:
    return Candidate(run_id, {"mrr": mrr, "recall": 0.9, "faithfulness": 4.5, "correct_refusal_rate": 0.9},
                     {q: accuracy for q in QUESTIONS}, 0.001, {q: mrr for q in QUESTIONS})


def request(variable: str, values: list, base: dict = BASE_B) -> SweepRequest:
    return SweepRequest.model_validate({"base": base, "variable": variable, "values": values})


@pytest.fixture
def world(tmp_path, monkeypatch):
    """`world.stored` maps a value of the swept setting to its stored run; each missing run is priced at $0.25 and each
    enrichment at $0.05, so the totals are exact."""
    class World:
        stored: dict = {}
        priced: list = []
        enriched: list = []
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    monkeypatch.setattr(settings, "budget_usd", 1.0)
    w = World()
    w.stored, w.priced, w.enriched = {}, [], []
    w.variable = "top_k"

    def stored_runs(conn, split):
        assert split == "dev"
        def found(choices):
            value = {"top_k": choices.top_k, "overlap": choices.chunk_set_id, "chunking_method": choices.chunk_set_id}[w.variable]
            return w.stored.get(value)
        return found

    monkeypatch.setattr(ladder_runs, "stored_runs", stored_runs)
    monkeypatch.setattr(builds, "run_cost", lambda conn, choices, tests: w.priced.append((choices.chunk_set_id, choices.top_k, len(tests))) or 0.25)
    monkeypatch.setattr(builds, "enrichment_cost", lambda method, size, overlap: w.enriched.append((method, size, overlap)) or (0.05 if method == "llm_enriched" else 0.0))
    w.conn = store.connect()
    prompts.ensure_default(w.conn)
    w.client = TestClient(main.app)
    yield w
    w.conn.close()


def test_the_base_value_comes_first_when_not_given_and_stays_in_place_when_given():
    assert [value for value, _ in request("top_k", [4, 6]).items()] == [2, 4, 6]
    assert [value for value, _ in request("top_k", [4, 2, 6]).items()] == [4, 2, 6]


def test_each_value_changes_only_the_swept_setting():
    configs = [config for _, config in request("overlap", [0, 100]).items()]
    assert [(c.overlap, c.chunk_size, c.top_k) for c in configs] == [(78, 400, 2), (0, 400, 2), (100, 400, 2)]
    a = [config for _, config in request("text_weight", [0.0, 2.0], BASE_A).items()]
    assert [c.openai_ranking.text_weight for c in a] == [1.0, 0.0, 2.0]
    assert all(c.openai_ranking.ranker == "auto" and c.openai_ranking.embedding_weight == 1.0 for c in a)


def test_the_chunking_method_value_gives_the_enriched_chunk_set():
    configs = [config.choices().chunk_set_id for _, config in request("chunking_method", ["llm_enriched"]).items()]
    assert configs == ["fixed__c400__o78", "llm_enriched__c400__o78"]


@pytest.mark.parametrize("variable, values, base, reason", [
    ("hybrid", [True], BASE_A, "hybrid is a Stack B setting"),
    ("ranker", ["none"], BASE_B, "ranker is a Stack A setting"),
    ("score_threshold", [0.5], BASE_B, "score_threshold is a Stack A setting"),
    ("top_k", [4, 4], BASE_B, "Each value must appear once"),
    ("top_k", [2, 2], BASE_B, "Each value must appear once"),
    ("embedding_weight", [1, 1.0], BASE_A, "Each value must appear once"),
    ("top_k", [1, 3, 4, 5, 6, 7], BASE_B, "at most 6 values, the base value included"),
    ("overlap", [201], BASE_B, "overlap = 201 is not a valid setting"),
    ("top_k", [9], BASE_B, "top_k = 9 is not a valid setting"),
    ("top_k", [True], BASE_B, "top_k = True is not a valid setting"),
    ("top_k", ["4"], BASE_B, "top_k = '4' is not a valid setting"),
    ("top_k", [4.0], BASE_B, "top_k = 4.0 is not a valid setting"),
    ("rerank", [1], BASE_B, "rerank = 1 is not a valid setting"),
    ("answer_model", ["openai/unknown"], BASE_B, "answer_model = 'openai/unknown' is not a valid setting"),
    ("score_threshold", [1.5], BASE_A, "score_threshold = 1.5 is not a valid setting"),
    ("chunking_method", ["semantic"], BASE_B, "chunking_method = 'semantic' is not a valid setting"),
])
def test_a_sweep_that_could_not_run_is_refused_with_its_reason(variable, values, base, reason):
    with pytest.raises(ValidationError, match=reason):
        request(variable, values, base)


def test_six_values_with_the_base_among_them_are_accepted():
    assert len(request("top_k", [1, 2, 3, 4, 5, 6]).items()) == 6
    assert len(request("top_k", [1, 3, 4, 5, 6]).items()) == 6


@pytest.mark.parametrize("body", [
    {"base": BASE_B, "variable": "top_k", "values": []},
    {"base": BASE_B, "variable": "temperature", "values": [0.5]},
    {"base": BASE_B, "variable": "top_k", "values": [4], "extra": 1},
    {"base": {**BASE_B, "overlap": 300}, "variable": "top_k", "values": [4]},
    {"variable": "top_k", "values": [4]},
])
def test_the_route_refuses_an_invalid_sweep(world, body):
    assert world.client.post("/api/sweeps/plan", json=body).status_code == 422


def test_values_with_a_stored_run_reuse_it_and_only_the_others_are_priced(world):
    world.stored = {2: candidate(15, 4.0), 6: candidate(30, 4.0)}
    plan = sweeps.plan(world.conn, request("top_k", [4, 6, 8]))
    assert [(i["value"], i["base"], i["run"] and i["run"]["run_id"], i["estimate_usd"]) for i in plan["items"]] == [
        (2, True, 15, None), (4, False, None, 0.25), (6, False, 30, None), (8, False, None, 0.25)]
    assert world.priced == [("fixed__c400__o78", 4, 192), ("fixed__c400__o78", 8, 192)]
    assert (plan["runs_to_do"], plan["estimate_usd"], plan["budget_left_usd"]) == (2, 0.5, 1.0)


def test_a_finished_value_shows_its_scores_intervals_and_change_against_the_base(world):
    world.stored = {2: candidate(15, 4.0, mrr=0.8), 4: candidate(16, 4.5, mrr=0.6), 6: candidate(17, 4.0, mrr=0.8)}
    items = sweeps.plan(world.conn, request("top_k", [4, 6]))["items"]
    base, better, same = (item["run"] for item in items)
    assert base["change"] is None
    assert (better["accuracy"], better["mrr"], better["run_id"]) == (4.5, 0.6, 16)
    assert (better["accuracy_ci"], better["mrr_ci"]) == ((4.5, 4.5), (0.6, 0.6))
    assert better["change"]["accuracy"]["verdict"] == "better" and better["change"]["accuracy"]["low"] > 0
    assert better["change"]["mrr"]["verdict"] == "worse" and better["change"]["mrr"]["high"] < 0
    assert same["change"]["accuracy"]["verdict"] == "no real difference"


def test_without_a_base_run_no_change_is_shown_but_scores_are(world):
    world.stored = {4: candidate(16, 4.5)}
    items = sweeps.plan(world.conn, request("top_k", [4]))["items"]
    assert items[0]["run"] is None and items[0]["estimate_usd"] == 0.25
    assert items[1]["run"]["accuracy"] == 4.5 and items[1]["run"]["change"] is None


def test_enrichment_is_added_once_per_chunk_set_and_only_for_values_still_to_run(world):
    world.variable = "chunking_method"
    plan = sweeps.plan(world.conn, request("chunking_method", ["llm_enriched"]))
    assert plan["estimate_usd"] == pytest.approx(0.25 * 2 + 0.05)
    assert sorted(world.enriched) == [("fixed", 400, 78), ("llm_enriched", 400, 78)]
    world.enriched.clear()
    world.stored = {"llm_enriched__c400__o78": candidate(40, 4.0)}
    plan = sweeps.plan(world.conn, request("chunking_method", ["llm_enriched"]))
    assert (plan["runs_to_do"], plan["estimate_usd"], world.enriched) == (1, 0.25, [("fixed", 400, 78)])


def test_each_value_says_whether_its_chunks_are_built_on_the_stack(world):
    world.variable = "overlap"
    insert(world.conn, "indexes", {"stack": "B", "chunk_set_id": "fixed__c400__o0", "ref": "r", "chunk_count": 1})
    insert(world.conn, "indexes", {"stack": "A", "chunk_set_id": "fixed__c400__o78", "ref": "r", "chunk_count": 1})
    items = sweeps.plan(world.conn, request("overlap", [0]))["items"]
    assert [(i["chunk_set_id"], i["built"]) for i in items] == [("fixed__c400__o78", False), ("fixed__c400__o0", True)]


def test_an_unknown_prompt_version_is_a_404(world):
    reply = world.client.post("/api/sweeps/plan", json={"base": {**BASE_B, "prompt_name": "nope"}, "variable": "top_k", "values": [4]})
    assert reply.status_code == 404


def test_an_unknown_prompt_version_among_the_values_is_a_404_even_if_others_have_run(world):
    world.stored = {2: candidate(15, 4.0)}
    reply = world.client.post("/api/sweeps/plan", json={"base": BASE_B, "variable": "prompt_name", "values": ["nope"]})
    assert (reply.status_code, reply.json()["detail"]) == (404, "Not found: nope")


def test_the_route_returns_the_plan(world):
    world.stored = {2: candidate(15, 4.0)}
    reply = world.client.post("/api/sweeps/plan", json={"base": BASE_B, "variable": "top_k", "values": [4]})
    assert reply.status_code == 200
    body = reply.json()
    assert (body["stack"], body["variable"], body["runs_to_do"], [i["value"] for i in body["items"]]) == ("B", "top_k", 1, [2, 4])


@pytest.fixture
def stored_a(tmp_path, monkeypatch):
    """Real Stack A runs in a fresh database, read by the real lookup. Only the scoring is faked: `best_run.candidates`
    returns the given runs, oldest first, each with a recognisable accuracy."""
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    monkeypatch.setattr(builds, "run_cost", lambda conn, choices, tests: 0.25)
    monkeypatch.setattr(builds, "enrichment_cost", lambda method, size, overlap: 0.0)
    conn = store.connect()
    prompts.ensure_default(conn)
    made = []

    def run(**ranking) -> int:
        full = {**RANKING, **ranking}
        meta = replace(STACK_A, chunk_set_id="fixed__c400__o78", top_k=2, openai_ranking=full, hybrid=full["text_weight"] > 0,
                       rerank_model=None, rerank_slug=None, rerank_candidates=None, answer_model="openai/gpt-4.1-nano")
        made.append(runs.create_run(conn, meta))
        return made[-1]

    monkeypatch.setattr(best_run, "candidates", lambda c, split: [candidate(run_id, float(run_id)) for run_id in made])
    yield conn, run
    conn.close()


def plan_json(conn, body: str) -> list:
    """Plan a sweep sent as the browser sends it: whole numbers stay whole numbers in JSON."""
    return [(i["value"], i["run"] and i["run"]["run_id"]) for i in sweeps.plan(conn, SweepRequest.model_validate_json(body))["items"]]


BASE_A_JSON = ('{"stack":"A","chunking_method":"fixed","chunk_size":400,"overlap":78,"top_k":2,"rerank":false,'
               '"answer_model":"openai/gpt-4.1-nano","prompt_name":"default",'
               '"openai_ranking":{"ranker":"auto","embedding_weight":1,"text_weight":1,"score_threshold":0}}')


def test_the_real_lookup_matches_stack_a_rankings_exactly_even_sent_as_whole_numbers(stored_a):
    conn, run = stored_a
    base, keyword_off = run(), run(text_weight=0.0)
    assert plan_json(conn, f'{{"base":{BASE_A_JSON},"variable":"text_weight","values":[0,2]}}') == [(1, base), (0, keyword_off), (2, None)]


def test_the_real_lookup_tells_the_ranker_and_the_threshold_apart(stored_a):
    conn, run = stored_a
    base, no_ranker, threshold = run(), run(ranker="none"), run(score_threshold=0.5)
    assert plan_json(conn, f'{{"base":{BASE_A_JSON},"variable":"ranker","values":["none"]}}') == [("auto", base), ("none", no_ranker)]
    assert plan_json(conn, f'{{"base":{BASE_A_JSON},"variable":"score_threshold","values":[0.5,0.25]}}') == [(0, base), (0.5, threshold), (0.25, None)]


def test_the_real_lookup_keeps_the_oldest_of_two_runs_with_the_same_settings(stored_a):
    conn, run = stored_a
    first, _later = run(), run()
    assert plan_json(conn, f'{{"base":{BASE_A_JSON},"variable":"top_k","values":[4]}}') == [(2, first), (4, None)]
