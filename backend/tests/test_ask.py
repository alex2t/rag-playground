"""POST /api/ask (T54): one question outside any run. It pays only what it uses, counts against the budget, stores no
run, and reads what a run reads. Same fakes as test_jobs.py (no network, no cost)."""

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIConnectionError
from qdrant_client.http.exceptions import ResponseHandlingException
from test_api_runs import A as RUN_A, B as RUN_B, client, stack_a  # noqa: F401  (stack_a is a fixture)
from test_jobs import CHUNK, VERDICT, call, world  # noqa: F401  (world is a fixture)

from rag_playground import main
from rag_playground.datasets.schema import load_tests
from rag_playground.llm.openrouter import paid
from rag_playground.rag import ask, estimate, pipeline, prompts, runs, spend
from rag_playground.rag.rerank import Reranked
from rag_playground.settings import RERANK_CANDIDATES, settings
from rag_playground.stacks import indexes, openai_vector_store, qdrant_store
from rag_playground.stacks.hits import Hit

B ={k: v for k, v in RUN_B.items() if k != "questions"}
A = {k: v for k, v in RUN_A.items() if k != "questions"}
TESTS = load_tests()
DEV_TEST = next(t for t in TESTS if t.split == "dev" and t.source_docs)
HELD_TEST = next(t for t in TESTS if t.split == "heldout")
FEE = 0.0025
ANSWER = 0.001
JUDGE = 0.0005


@pytest.fixture
def asking(world, monkeypatch):
    """`world` with the chunk set loadable by Ask and a judge that records what it reads."""
    world["judged"] = []
    monkeypatch.setattr(ask, "load_chunk_set", lambda set_id: [CHUNK])

    def judge(test, context, text):
        world["judged"].append((test.id, context, text))
        return VERDICT, [paid(call(JUDGE))]

    monkeypatch.setattr(ask, "judge", judge)
    return world


def post(body):
    return main_client().post("/api/ask", json=body)


def main_client():
    return TestClient(main.app, raise_server_exceptions=False)


def fee_rows(conn):
    return conn.execute("SELECT run_id, cost_usd FROM spend WHERE model = ?", (spend.SEARCH_ROW,)).fetchall()


def test_a_typed_question_is_answered_with_its_chunks_and_no_scores(asking):
    reply = post({**B, "question": "Who runs the cloud team?"}).json()
    assert reply["answer"] == "An answer."
    assert [(c["rank"], c["source"], c["score"], c["text"], c["gold"]) for c in reply["chunks"]] == [
        (1, "d.md", 1.0, "text", False), (2, "d.md", 1.0, "text", False)]
    assert (reply["judgement"], reply["reference_answer"], reply["gold_sources"]) == (None, None, [])
    assert asking["judged"] == []


def test_a_typed_question_on_stack_b_pays_only_its_answer_and_stores_no_run(asking):
    reply = post({**B, "question": "Who?"}).json()
    assert reply["cost_usd"] == pytest.approx(ANSWER)
    assert spend.total(asking["conn"]) == pytest.approx(ANSWER)
    assert fee_rows(asking["conn"]) == []
    assert asking["conn"].execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_a_typed_question_on_stack_a_pays_one_search_fee_recorded_outside_any_run(asking, stack_a):
    reply = post({**A, "question": "Who?"}).json()
    assert reply["cost_usd"] == pytest.approx(ANSWER + FEE)
    assert spend.total(asking["conn"]) == pytest.approx(ANSWER + FEE)
    assert [tuple(row) for row in fee_rows(asking["conn"])] == [(None, FEE)]


def test_the_ranking_of_the_request_reaches_stack_a(asking, stack_a):
    ranking = {**A["openai_ranking"], "text_weight": 0.0, "ranker": "none"}
    post({**A, "openai_ranking": ranking, "question": "Who?"})
    assert stack_a == [("vs_1", 2, openai_vector_store.Ranking(**ranking))]


def raises(error):
    def fail(*args):
        raise error

    return fail


OPENAI_DOWN = APIConnectionError(request=httpx.Request("POST", "https://example.test"))


def test_a_failed_search_pays_no_fee_and_says_why(asking, stack_a, monkeypatch):
    monkeypatch.setattr(openai_vector_store, "search", raises(OPENAI_DOWN))
    response = post({**A, "question": "Who?"})
    assert response.status_code == 502
    assert response.json()["detail"] == "The question failed: APIConnectionError: Connection error."
    assert spend.total(asking["conn"]) == 0


def test_a_qdrant_failure_is_a_service_failure(asking, monkeypatch):
    monkeypatch.setattr(qdrant_store, "search", raises(ResponseHandlingException(OSError("refused"))))
    response = post({**B, "question": "Who?"})
    assert response.status_code == 502 and "ResponseHandlingException" in response.json()["detail"]


def test_a_failed_answer_after_a_paid_search_still_counts_the_fee(asking, stack_a, monkeypatch):
    monkeypatch.setattr(pipeline, "answer", raises(OPENAI_DOWN))
    assert post({**A, "question": "Who?"}).status_code == 502
    assert spend.total(asking["conn"]) == pytest.approx(FEE)


@pytest.mark.parametrize("error", [AttributeError("a bug"), ValueError("a bad model reply")])
def test_a_bug_is_not_blamed_on_a_service_and_shows_no_text(asking, monkeypatch, error):
    monkeypatch.setattr(pipeline, "answer", raises(error))
    response = post({**B, "question": "Who?"})
    assert (response.status_code, response.text) == (500, "Internal Server Error")


def test_a_changed_default_prompt_is_a_conflict_with_its_reason(asking, monkeypatch):
    monkeypatch.setattr(prompts, "DEFAULT_TEXT", "Edited default.")
    response = post({**B, "question": "Who?"})
    assert response.status_code == 409 and "differs from DEFAULT_TEXT" in response.json()["detail"]
    assert spend.total(asking["conn"]) == 0


def test_the_reranker_pays_one_search_for_all_its_candidates_and_keeps_top_k(asking, stack_a, monkeypatch):
    def rerank(question, hits, k):
        return Reranked(hits[::-1][:k], paid(call(0.0001)), repaired=False)

    monkeypatch.setattr(pipeline, "rerank", rerank)
    reply = post({**A, "rerank": True, "question": "Who?"}).json()
    assert stack_a == [("vs_1", RERANK_CANDIDATES, stack_a[0][2])]
    assert [c["rank"] for c in reply["chunks"]] == [1, 2]
    assert reply["chunks"][0]["text"] == "text" and reply["rerank_repaired"] is False
    assert reply["cost_usd"] == pytest.approx(ANSWER + 0.0001 + FEE)
    assert len(fee_rows(asking["conn"])) == 1


def test_a_test_question_is_judged_and_marks_the_gold_chunks(asking, monkeypatch):
    gold = DEV_TEST.source_docs[0]
    monkeypatch.setattr(qdrant_store, "search", lambda q, name, question, k, hybrid: [
        Hit("c0", "other.md", 0.9, "first"), Hit("c1", gold, 0.8, "second")])
    reply = post({**B, "test_id": DEV_TEST.id}).json()
    assert [c["gold"] for c in reply["chunks"]] == [False, True]
    assert reply["gold_sources"] == sorted(DEV_TEST.source_docs)
    assert reply["reference_answer"] == DEV_TEST.reference_answer
    assert reply["judgement"]["accuracy"] == VERDICT.accuracy
    assert asking["judged"] == [(DEV_TEST.id, ["first", "second"], "An answer.")]
    assert reply["cost_usd"] == pytest.approx(ANSWER + JUDGE)


@pytest.mark.parametrize("test_id", [HELD_TEST.id, "no-such-question"])
def test_a_held_out_id_is_refused_like_an_unknown_one_and_nothing_is_paid(asking, test_id):
    response = post({**B, "test_id": test_id})
    assert (response.status_code, response.json()["detail"]) == (404, f"Not found: {test_id}")
    assert spend.total(asking["conn"]) == 0


def test_the_question_list_is_the_dev_questions_without_their_answers(asking):
    listed = client.get("/api/ask/questions").json()
    assert [item["id"] for item in listed] == [t.id for t in TESTS if t.split == "dev"]
    assert set(listed[0]) == {"id", "category", "question"}


def typed_estimate(world, stack="B"):
    prompt = pipeline.prompts.get(world["conn"], "default")
    return estimate.answer_cost("Who?", prompt, B["answer_model"], B["top_k"], False, CHUNK.tokens, stack)


def test_a_question_over_the_budget_is_refused_before_anything_is_paid(asking, monkeypatch):
    searched = []
    monkeypatch.setattr(qdrant_store, "search", lambda *args: searched.append(args) or [])
    monkeypatch.setattr(settings, "budget_usd", typed_estimate(asking) * 0.99)
    response = post({**B, "question": "Who?"})
    assert response.status_code == 409 and "Budget reached" in response.json()["detail"]
    assert searched == [] and spend.total(asking["conn"]) == 0


def test_a_question_at_exactly_the_budget_is_answered(asking, monkeypatch):
    monkeypatch.setattr(settings, "budget_usd", typed_estimate(asking))
    assert post({**B, "question": "Who?"}).status_code == 200


def test_the_budget_check_counts_stack_a_s_fee(asking, stack_a, monkeypatch):
    """A budget between the two estimates stops only Stack A."""
    monkeypatch.setattr(settings, "budget_usd", typed_estimate(asking, "B") + FEE / 2)
    assert post({**A, "question": "Who?"}).status_code == 409
    assert post({**B, "question": "Who?"}).status_code == 200


def test_the_budget_check_of_a_test_question_counts_the_judge(asking, monkeypatch):
    """A budget that covers answering but not judging refuses the test question only."""
    prompt = pipeline.prompts.get(asking["conn"], "default")
    answering = estimate.answer_cost(DEV_TEST.question, prompt, B["answer_model"], B["top_k"], False, CHUNK.tokens, "B")
    judged = estimate.question_cost(DEV_TEST, prompt, B["answer_model"], B["top_k"], False, CHUNK.tokens, "B")
    assert judged > answering
    monkeypatch.setattr(settings, "budget_usd", (answering + judged) / 2)
    assert post({**B, "test_id": DEV_TEST.id}).status_code == 409
    assert post({**B, "question": DEV_TEST.question}).status_code == 200


def test_ask_counts_against_what_a_run_may_spend(asking, stack_a, monkeypatch):
    """One budget (D15): an Ask fee leaves less for the next run."""
    post({**A, "question": "Who?"})
    assert pipeline.remaining(asking["conn"]) == pytest.approx(1.0 - ANSWER - FEE)


def test_a_chunk_set_not_indexed_or_an_unknown_prompt_is_refused_with_its_name(asking):
    missing = post({**B, "chunk_size": 512, "overlap": 0, "question": "Who?"})
    assert (missing.status_code, missing.json()["detail"]) == (404, "Not found: fixed__c512__o0 is not indexed on Stack B")
    unknown = post({**B, "prompt_name": "nope", "question": "Who?"})
    assert (unknown.status_code, unknown.json()["detail"]) == (404, "Not found: nope")


@pytest.mark.parametrize("extra", [{}, {"question": "Who?", "test_id": "x"}, {"question": ""}, {"question": " \n "},
                                   {"question": 1}, {"question": "Who?", "questions": "dev"}])
def test_exactly_one_real_question_is_required(asking, extra):
    assert post({**B, **extra}).status_code == 422
    assert spend.total(asking["conn"]) == 0


def test_the_panel_rules_of_a_run_hold_on_ask(asking):
    assert post({**A, "hybrid": False, "question": "Who?"}).status_code == 422
    assert post({**B, "top_k": 9, "question": "Who?"}).status_code == 422
    assert post({**B, "top_k": "2", "question": "Who?"}).status_code == 422


def test_ask_reads_the_chunks_a_run_read_for_the_same_question_and_settings(asking, monkeypatch):
    """plan.md Step 9: the search receives the same arguments, so the same index gives the same chunks."""
    searched = []
    monkeypatch.setattr(qdrant_store, "search", lambda q, name, question, k, hybrid: searched.append(
        (name, question, k, hybrid)) or [Hit(f"{question}-{i}", "d.md", 1.0, "text") for i in range(k)])
    choices = pipeline.Choices(stack="B", chunk_set_id="fixed__c1024__o200", top_k=2, hybrid=False,
                               openai_ranking=None, rerank=False, answer_model=B["answer_model"], prompt_name="default")
    conn = asking["conn"]
    run_id = pipeline.start_run(conn, choices, [DEV_TEST])
    pipeline.execute(conn, run_id, indexes.retriever(conn, runs.get_run(conn, run_id).meta))
    reply = post({**B, "test_id": DEV_TEST.id}).json()
    stored = runs.get_results(conn, run_id)[0].hits
    assert searched[0] == searched[1]
    assert [c["text"] for c in reply["chunks"]] == [hit.text for hit in stored]
