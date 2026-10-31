"""GET /api/runs/{id}/answers: what a run answered, question by question. Stored rows only (no network, no cost)."""

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from rag_playground import main, store
from rag_playground.datasets.schema import load_tests
from rag_playground.rag import prompts, runs
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import settings
from rag_playground.stacks.hits import Hit

client = TestClient(main.app)
TESTS = load_tests()
DEV = [t for t in TESTS if t.split == "dev"][:3]
HELDOUT = [t for t in TESTS if t.split == "heldout"][:1]
META = runs.RunMeta(
    stack="B", split="dev", test_ids=[t.id for t in DEV], chunk_set_id="fixed__c512__o0", top_k=2, hybrid=False,
    openai_ranking=None, answer_model="m", answer_slug="m-1", judge_model="j", judge_slug="j-1", rerank_model=None,
    rerank_slug=None, rerank_candidates=None, temperature_controlled=True, prompt_name="default", prompt_sha256="p",
    dataset_sha256="d", app_version="dev")


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    connection = store.connect()
    prompts.ensure_default(connection)
    yield connection
    connection.close()


def meta(conn, **changes):
    default = prompts.get(conn, "default")
    return replace(META, prompt_sha256=default.sha256, **changes)


def result(test, accuracy, refused=False):
    verdict = Judgement(refused=refused, accuracy=accuracy, completeness=4, relevance=3, faithfulness=2,
                        feedback=f"about {test.id}", faithfulness_feedback=f"grounding of {test.id}")
    return runs.Result(test_id=test.id, hits=[Hit("c1", "doc.md", 0.5, "the chunk text")], rerank_repaired=None,
                       answer=f"answer to {test.id}", judgement=verdict, cost_usd=0.001, latency_s=1.0)


def answers(run_id):
    return client.get(f"/api/runs/{run_id}/answers")


def stored_run(conn, *accuracies):
    run_id = runs.create_run(conn, meta(conn))
    for test, accuracy in zip(DEV, accuracies):
        runs.add_result(conn, run_id, result(test, accuracy))
    return run_id


def test_each_answer_comes_with_its_question_reference_verdict_and_chunks(conn):
    run_id = stored_run(conn, 5, 5, 5)
    first, test = answers(run_id).json()[0], DEV[0]
    assert first == {
        "test_id": test.id, "category": test.category, "question": test.question,
        "reference_answer": test.reference_answer, "answer": f"answer to {test.id}", "refused": False, "accuracy": 5,
        "completeness": 4, "relevance": 3, "faithfulness": 2, "feedback": f"about {test.id}",
        "faithfulness_feedback": f"grounding of {test.id}", "chunks": [{"source": "doc.md", "text": "the chunk text"}]}


def test_the_lowest_accuracy_comes_first_and_ties_keep_question_order(conn):
    run_id = stored_run(conn, 5, 1, 5)
    assert [a["test_id"] for a in answers(run_id).json()] == [DEV[1].id, DEV[0].id, DEV[2].id]


def test_a_run_stopped_partway_shows_what_it_answered(conn):
    run_id = stored_run(conn, 3)
    runs.finish_run(conn, run_id, error="stopped")
    assert [a["test_id"] for a in answers(run_id).json()] == [DEV[0].id]


def test_a_run_with_no_answer_yet_is_an_empty_list(conn):
    response = answers(stored_run(conn))
    assert (response.status_code, response.json()) == (200, [])


def test_held_out_answers_are_refused(conn):
    run_id = runs.create_run(conn, meta(conn, split="heldout", test_ids=[t.id for t in HELDOUT]))
    runs.add_result(conn, run_id, result(HELDOUT[0], 5))
    response = answers(run_id)
    assert response.status_code == 422
    assert HELDOUT[0].question not in json.dumps(response.json())
    assert "Held-out" in response.json()["detail"]


def test_an_unknown_run_is_404(conn):
    response = answers(999)
    assert (response.status_code, response.json()["detail"]) == (404, "No run 999")


def test_a_bad_run_id_is_refused(conn):
    assert answers("abc").status_code == 422
