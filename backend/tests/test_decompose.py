"""Split the question (decision.md T60): the turn-taking merge, the one-part rule, the shared search path, the stored
parts and searches, Stack A's fee per search, the estimate, the request, the database and its upgrade."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_api_runs import A as RUN_A, B as RUN_B, client, stack_a, start  # noqa: F401  (stack_a is a fixture)
from test_ask import A, asking, fee_rows, post  # noqa: F401  (asking is a fixture)
from test_best_run import META, conn, result, store_run  # noqa: F401  (conn is a fixture)
from test_estimate import PROMPT, TEST, TESTS, prices, real_count, tokens  # noqa: F401  (prices is a fixture)
from test_jobs import CHUNK, call, world  # noqa: F401  (world is a fixture)
from test_evaluation import every_document_has_a_chunk  # noqa: F401  (autouse: reports can score any document)
from test_per_document import make_old_database

from rag_playground import store
from rag_playground.llm.openrouter import paid
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.rag import best_run, decompose, estimate, evaluation, grading, pipeline, prompts, runs, spend
from rag_playground.rag.decompose import SubQuestions, in_turns, split_and_search, split_messages
from rag_playground.rag.ladder import baseline
from rag_playground.rag.ladder_runs import finder
from rag_playground.run_requests import RunRequest
from rag_playground.settings import DECOMPOSE_MODEL, MAX_SUB_QUESTIONS, STACK_A_SEARCH_USD
from rag_playground.stacks.hits import Hit

SPLIT_COST = 0.0001


def hit(chunk_id: str) -> Hit:
    return Hit(chunk_id, f"{chunk_id[0]}.md", 1.0, chunk_id)


def ids(hits: list[Hit]) -> list[str]:
    return [h.chunk_id for h in hits]


def test_in_turns_takes_the_best_of_each_part_then_the_next():
    assert ids(in_turns([[hit("a1"), hit("a2")], [hit("b1"), hit("b2")]], 3)) == ["a1", "b1", "a2"]


def test_in_turns_skips_a_chunk_already_kept():
    assert ids(in_turns([[hit("a1"), hit("a2")], [hit("a1"), hit("b2")]], 3)) == ["a1", "a2", "b2"]


def test_in_turns_continues_with_a_longer_list_when_a_shorter_one_ends():
    assert ids(in_turns([[hit("a1")], [hit("b1"), hit("b2"), hit("b3")]], 4)) == ["a1", "b1", "b2", "b3"]


def test_in_turns_keeps_fewer_than_k_when_the_parts_hold_fewer_chunks():
    assert ids(in_turns([[hit("a1")], [hit("a1")]], 2)) == ["a1"]


def test_three_parts_take_turns_in_order():
    parts = [[hit("a1"), hit("a2")], [hit("b1"), hit("b2")], [hit("c1"), hit("c2")]]
    assert ids(in_turns(parts, 4)) == ["a1", "b1", "c1", "a2"]


@pytest.fixture
def splitter(monkeypatch):
    """The split model returns state["parts"] for every question; state["asked"] holds the messages it got."""
    state = {"parts": ["Q?"], "asked": []}

    def chat_structured(model, messages, schema):
        state["asked"].append((model, messages, schema))
        return SubQuestions(sub_questions=state["parts"]), paid(call(SPLIT_COST))

    monkeypatch.setattr(decompose, "chat_structured", chat_structured)
    return state


def searching():
    asked = []

    def retrieve(question, k):
        asked.append((question, k))
        return [hit(f"{question[0].lower()}{rank}") for rank in range(1, k + 1)]

    return asked, retrieve


def test_one_part_searches_the_original_question_once(splitter):
    splitter["parts"] = ["A rewording of it?"]
    asked, retrieve = searching()
    split = split_and_search("Original?", 2, retrieve)
    assert asked == [("Original?", 2)]
    assert (ids(split.hits), split.searches, split.sub_questions) == (["o1", "o2"], 1, ["A rewording of it?"])


def test_two_parts_search_each_for_k_and_take_turns(splitter):
    splitter["parts"] = ["Alpha?", "Beta?"]
    asked, retrieve = searching()
    split = split_and_search("Original?", 2, retrieve)
    assert asked == [("Alpha?", 2), ("Beta?", 2)]
    assert (ids(split.hits), split.searches) == (["a1", "b1"], 2)


def test_the_split_model_gets_the_question_and_returns_its_structured_parts(splitter):
    split_and_search("Original?", 2, searching()[1])
    assert splitter["asked"] == [(DECOMPOSE_MODEL, split_messages("Original?"), SubQuestions)]


@pytest.mark.parametrize("parts", [[], ["a"] * (MAX_SUB_QUESTIONS + 1)])
def test_a_reply_with_no_part_or_too_many_is_refused(parts):
    with pytest.raises(ValidationError):
        SubQuestions(sub_questions=parts)


@pytest.fixture
def answering(monkeypatch):
    questions = []
    monkeypatch.setattr(pipeline, "answer", lambda model, prompt, question, hits: questions.append(question) or call(0.001))
    return questions


def test_the_answer_model_reads_the_original_question_and_the_split_call_is_paid(splitter, answering):
    splitter["parts"] = ["Alpha?", "Beta?"]
    done = pipeline.search_and_answer("Original?", 2, None, "m", None, searching()[1], decompose=True)
    assert answering == ["Original?"]
    assert [c.cost_usd for c in done.calls] == [SPLIT_COST, 0.001]
    assert (done.sub_questions, done.searches) == (["Alpha?", "Beta?"], 2)


def test_without_the_setting_nothing_is_split(splitter, answering):
    done = pipeline.search_and_answer("Original?", 2, None, "m", None, searching()[1])
    assert splitter["asked"] == [] and (done.sub_questions, done.searches) == (None, 1)


def test_a_stack_a_run_stores_parts_and_searches_and_pays_a_fee_per_search(world, stack_a, splitter):
    splitter["parts"] = ["Alpha?", "Beta?", "Gamma?"]
    job = client.get(f"/api/jobs/{start({**RUN_A, 'split_question': True}).json()['job_id']}").json()
    assert job["status"] == "done"
    meta = runs.get_run(world["conn"], job["run_id"]).meta
    assert (meta.decompose_model, meta.decompose_slug) == (DECOMPOSE_MODEL, f"{DECOMPOSE_MODEL}-1")
    results = runs.get_results(world["conn"], job["run_id"])
    assert {(tuple(r.sub_questions), r.searches) for r in results} == {(("Alpha?", "Beta?", "Gamma?"), 3)}
    assert len(stack_a) == 3 * len(results)
    calls = sum(r.cost_usd for r in results)
    assert spend.total(world["conn"], job["run_id"]) == pytest.approx(calls + 3 * len(results) * STACK_A_SEARCH_USD)
    report = evaluation.report(world["conn"], job["run_id"])
    assert report["cost_per_question"] == pytest.approx(calls / len(results) + 3 * STACK_A_SEARCH_USD)
    assert report["settings"]["split_question"] is True


def test_the_budget_guard_counts_every_search_of_the_costliest_question(world, stack_a, splitter):
    """ask_together returns what the guard assumes for the next question: the costliest one with all its fees."""
    splitter["parts"] = ["Alpha?", "Beta?"]
    request = RunRequest.model_validate({**RUN_A, "split_question": True})
    tests = request.tests()[:2]
    run_id = pipeline.start_run(world["conn"], request.choices(), tests)
    meta = runs.get_run(world["conn"], run_id).meta
    with ThreadPoolExecutor(2) as pool:
        largest = pipeline.ask_together(world["conn"], run_id, pool, tests, meta, prompts.get(world["conn"], "default"),
                                        lambda question, k: [hit(f"x{i}") for i in range(k)])
    costs = [r.cost_usd for r in runs.get_results(world["conn"], run_id)]
    assert largest == pytest.approx(max(costs) + 2 * STACK_A_SEARCH_USD)


def test_ask_records_a_fee_for_each_search_and_shows_the_parts(asking, stack_a, splitter):
    splitter["parts"] = ["Alpha?", "Beta?"]
    reply = post({**A, "split_question": True, "question": "Who?"}).json()
    assert reply["sub_questions"] == ["Alpha?", "Beta?"]
    assert len(fee_rows(asking["conn"])) == 2
    assert reply["cost_usd"] == pytest.approx(0.001 + SPLIT_COST + 2 * STACK_A_SEARCH_USD)


def test_the_estimate_adds_the_split_call_with_the_question_echoed_as_its_reply(prices):
    def cost(decompose):
        return estimate.question_cost(TEST, PROMPT, "openai/gpt-4.1-nano", 2, False, 200, "B", decompose)

    prices[DECOMPOSE_MODEL, "in"] = 1.0
    assert cost(True) - cost(False) == real_count(split_messages(TEST.question))
    prices[DECOMPOSE_MODEL, "in"], prices[DECOMPOSE_MODEL, "out"] = 0.0, 1.0
    assert cost(True) - cost(False) == tokens(json.dumps({"sub_questions": [TEST.question]}))


@pytest.mark.parametrize("change, problem", [
    ({"rerank": True}, "cannot be split"), ({"per_doc_limit": 1}, "cannot be split"),
    ({"split_question": "true"}, "split_question"), ({"split_question": 1}, "split_question")])
def test_a_request_that_cannot_split_is_refused(change, problem):
    with pytest.raises(ValidationError, match=problem):
        RunRequest.model_validate({**RUN_B, "split_question": True, **change})


def test_the_setting_must_be_stated():
    with pytest.raises(ValidationError, match="split_question"):
        RunRequest.model_validate({k: v for k, v in RUN_B.items() if k != "split_question"})


SPLIT = replace(META, decompose_model=DECOMPOSE_MODEL, decompose_slug="mini-1")


def test_the_database_refuses_splitting_with_the_reranker_or_the_limit_or_without_a_slug(conn):
    for meta in (replace(SPLIT, rerank_model="m", rerank_slug="s", rerank_candidates=20),
                 replace(SPLIT, per_doc_limit=1), replace(SPLIT, decompose_slug=None)):
        with pytest.raises(sqlite3.IntegrityError, match="decompose"):
            runs.create_run(conn, meta)


def test_the_database_refuses_a_search_count_outside_1_to_the_cap(conn):
    run_id = runs.create_run(conn, SPLIT)
    result = runs.get_results(conn, store_run(conn, meta=SPLIT))[0]
    for searches in (0, MAX_SUB_QUESTIONS + 1):
        with pytest.raises(sqlite3.IntegrityError, match="searches"):
            runs.add_result(conn, run_id, replace(result, searches=searches))


def test_stored_parts_and_searches_read_back_and_never_change(conn):
    run_id = runs.create_run(conn, SPLIT)
    base = runs.get_results(conn, store_run(conn))[0]
    runs.add_result(conn, run_id, replace(base, sub_questions=["Alpha?", "Beta?"], searches=2))
    back = runs.get_results(conn, run_id)[0]
    assert (back.sub_questions, back.searches) == (["Alpha?", "Beta?"], 2)
    with pytest.raises(sqlite3.IntegrityError), conn:
        conn.execute("UPDATE results SET searches = 1 WHERE run_id = ?", (run_id,))


def test_the_split_model_never_changes_on_a_stored_run(conn):
    """Finishing the run is allowed, so only the settings trigger can refuse this update."""
    run_id = runs.create_run(conn, META)
    with pytest.raises(sqlite3.IntegrityError, match="run settings are permanent"), conn:
        conn.execute("UPDATE runs SET status = 'failed', error = 'x', decompose_model = 'm', decompose_slug = 's' "
                     "WHERE id = ?", (run_id,))


def test_a_split_run_is_not_a_ladder_run_nor_an_s0_calibration_run(conn, monkeypatch):
    monkeypatch.setattr(grading, "model_info", lambda model: SimpleNamespace(canonical_slug=META.judge_slug))
    run_id = store_run(conn, meta=SPLIT)
    assert finder(conn, "B")(baseline(prompts.DEFAULT_NAME)) is None
    assert "split question" in grading.problems(runs.get_run(conn, run_id), "B", sorted(META.test_ids))


@pytest.mark.parametrize("with_per_doc_limit", [False, True], ids=["before-T59", "live-site-T59"])
def test_an_older_database_gains_the_columns_with_earlier_rows_as_not_split(tmp_path, with_per_doc_limit):
    make_old_database(tmp_path / "old.db", with_per_doc_limit)
    raw = sqlite3.connect(tmp_path / "old.db")
    old = {k: v for k, v in runs.asdict(result(META.test_ids[0])).items() if k not in ("sub_questions", "searches")}
    verdict = old.pop("judgement")
    runs.insert(raw, "results", {"run_id": 1, **old, **verdict, "hits": json.dumps(old["hits"])})
    raw.close()
    conn = store.connect(tmp_path / "old.db")
    back = runs.get_results(conn, 1)[0]
    assert (back.sub_questions, back.searches) == (None, 1)
    meta = runs.get_run(conn, 1).meta
    assert (meta.per_doc_limit, meta.decompose_model, meta.decompose_slug) == (None, None, None)
    with pytest.raises(sqlite3.IntegrityError, match="run settings are permanent"), conn:
        conn.execute("UPDATE runs SET status = 'failed', error = 'x', decompose_model = 'm', decompose_slug = 's' "
                     "WHERE id = 1")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(results)")}
    assert {"sub_questions", "searches"} <= columns


def test_a_run_estimate_adds_one_split_call_per_question(prices):
    chunks = [Chunk(chunk_id="d.md#0", source="d.md", doc_type="d", index=0, text="x", tokens=200, start=0, end=1)]

    def cost(decompose):
        return estimate.run_cost(TESTS, PROMPT, "openai/gpt-4.1-nano", 2, False, chunks, "B", decompose)

    prices[DECOMPOSE_MODEL, "in"] = 1.0
    assert cost(True) - cost(False) == sum(real_count(split_messages(t.question)) for t in TESTS)


def test_the_best_run_choice_counts_every_search_in_a_stack_a_runs_cost(conn):
    meta = replace(SPLIT, stack="A", hybrid=True, openai_ranking={"ranker": "auto", "embedding_weight": 1.0,
                                                                  "text_weight": 1.0, "score_threshold": 0.0})
    run_id = runs.create_run(conn, meta)
    for test_id in meta.test_ids:
        runs.add_result(conn, run_id, replace(result(test_id, refused=test_id.startswith("u")), searches=2))
    runs.finish_run(conn, run_id)
    chosen = next(c for c in best_run.candidates(conn) if c.run_id == run_id)
    assert chosen.cost_per_question == pytest.approx(0.01 + 2 * STACK_A_SEARCH_USD)
