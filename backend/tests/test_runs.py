"""Step 6 checks of run storage: every run keeps its reproducibility metadata and its per-question results."""

import sqlite3
from dataclasses import replace
from datetime import datetime

import pytest

from rag_playground import store
from rag_playground.datasets import schema
from rag_playground.rag import prompts, runs
from rag_playground.scoring.judging import Judgement
from rag_playground.stacks.hits import Hit

STACK_A = runs.RunMeta(
    stack="A", split="dev", test_ids=[f"q{i}" for i in range(10)], chunk_set_id="fixed__c1024__o200", top_k=5,
    hybrid=True,
    openai_ranking={"ranker": "none", "embedding_weight": 1.0, "text_weight": 1.0, "score_threshold": 0.0},
    answer_model="openai/gpt-6.1-sol", answer_slug="openai/gpt-6.1-sol-20260801",
    judge_model="google/gemini-3.5-flash-lite", judge_slug="google/gemini-3.5-flash-lite-001",
    rerank_model="openai/gpt-4.1-nano", rerank_slug="openai/gpt-4.1-nano-2025-04-14", rerank_candidates=20,
    temperature_controlled=False, prompt_name="default", prompt_sha256=prompts.sha256(prompts.DEFAULT_TEXT),
    dataset_sha256="d" * 64, app_version="52eb6d0")
STACK_B = replace(STACK_A, stack="B", hybrid=False, openai_ranking=None, rerank_model=None, rerank_slug=None,
                  rerank_candidates=None, answer_model="openai/gpt-4.1-nano",
                  answer_slug="openai/gpt-4.1-nano-2025-04-14", temperature_controlled=True)
VERDICT = Judgement(refused=False, accuracy=5, completeness=4, relevance=5, faithfulness=3,
                    feedback="Correct price.", faithfulness_feedback="The discount is not in the context.")


def result(test_id: str, repaired: bool | None = None) -> runs.Result:
    hits = [Hit("services/a.md#0", "services/a.md", 0.91, "It costs 46,250 USD."),
            Hit("company/b.md#2", "company/b.md", 0.42, "Founded in 2011.")]
    return runs.Result(test_id=test_id, hits=hits, rerank_repaired=repaired, answer="It costs 46,250 USD.",
                       judgement=VERDICT, cost_usd=0.00042, latency_s=1.7)


@pytest.fixture
def conn(tmp_path):
    connection = store.connect(tmp_path / "test.db")
    prompts.ensure_default(connection)
    yield connection
    connection.close()


NO_RERANK = {"rerank_model": None, "rerank_slug": None, "rerank_candidates": None}
WITH_RERANK = {"rerank_model": "openai/gpt-4.1-nano", "rerank_slug": "openai/gpt-4.1-nano-2025-04-14",
               "rerank_candidates": 20}


@pytest.mark.parametrize("meta", [STACK_A, replace(STACK_A, **NO_RERANK), STACK_B, replace(STACK_B, **WITH_RERANK)],
                         ids=["A+rerank", "A", "B", "B+rerank"])
def test_a_run_keeps_every_metadata_field_exactly(conn, meta):
    run_id = runs.create_run(conn, meta)
    run = runs.get_run(conn, run_id)
    assert (run.id, run.status, run.error, run.meta) == (run_id, "running", None, meta)
    assert datetime.strptime(run.created_at, "%Y-%m-%d %H:%M:%S")


def test_a_run_must_name_a_saved_prompt_version(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        runs.create_run(conn, replace(STACK_A, prompt_name="never-saved"))


def test_a_run_prompt_hash_must_match_the_saved_version(conn):
    """The name and hash are checked together, so a run cannot claim a prompt text it did not use."""
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        runs.create_run(conn, replace(STACK_A, prompt_sha256="0" * 64))


@pytest.mark.parametrize("changes", [
    {"stack": "C"}, {"split": "test"}, {"test_ids": []}, {"top_k": 0},
    {"openai_ranking": None},  # Stack A always records its OpenAI ranking (T40)
    {"rerank_slug": None}, {"rerank_candidates": None},  # reranker settings come together
    {"rerank_candidates": 4},  # fewer candidates than the K kept
])
def test_invalid_or_incomplete_settings_are_refused(conn, changes):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        runs.create_run(conn, replace(STACK_A, **changes))


@pytest.mark.parametrize("changes", [{"openai_ranking": STACK_A.openai_ranking}, {"rerank_model": "openai/gpt-4.1-nano"}])
def test_stack_b_refuses_openai_ranking_and_a_partial_reranker(conn, changes):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        runs.create_run(conn, replace(STACK_B, **changes))


@pytest.mark.parametrize("changes", [{"accuracy": 0}, {"completeness": 6}, {"relevance": 0}, {"faithfulness": 6}])
def test_judge_scores_outside_1_to_5_are_refused(conn, changes):
    run_id = runs.create_run(conn, STACK_A)
    bad = replace(result("q0"), judgement=replace(VERDICT, **changes))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        runs.add_result(conn, run_id, bad)
    assert runs.get_results(conn, run_id) == []


@pytest.mark.parametrize("repaired", [None, False, True])
def test_a_result_keeps_the_chunks_verdict_cost_and_time_exactly(conn, repaired):
    run_id = runs.create_run(conn, STACK_A)
    runs.add_result(conn, run_id, result("q0", repaired))
    assert runs.get_results(conn, run_id) == [result("q0", repaired)]


def test_a_refusal_comes_back_as_true(conn):
    run_id = runs.create_run(conn, STACK_A)
    refusal = replace(result("q1"), judgement=replace(VERDICT, refused=True))
    runs.add_result(conn, run_id, refusal)
    assert runs.get_results(conn, run_id)[0].judgement.refused is True


def test_progress_counts_stored_questions_and_reaches_1(conn):
    run_id = runs.create_run(conn, STACK_A)
    assert runs.progress(conn, run_id) == 0.0
    for i in range(3):
        runs.add_result(conn, run_id, result(f"q{i}"))
    assert runs.progress(conn, run_id) == 0.3
    for i in range(3, 10):
        runs.add_result(conn, run_id, result(f"q{i}"))
    assert runs.progress(conn, run_id) == 1.0
    assert [r.test_id for r in runs.get_results(conn, run_id)] == [f"q{i}" for i in range(10)]


def test_a_question_is_stored_once_per_run_but_again_in_another_run(conn):
    first, second = runs.create_run(conn, STACK_A), runs.create_run(conn, STACK_B)
    runs.add_result(conn, first, result("q0"))
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        runs.add_result(conn, first, result("q0"))
    runs.add_result(conn, second, result("q0"))
    assert len(runs.get_results(conn, first)) == len(runs.get_results(conn, second)) == 1


def test_a_result_must_belong_to_an_existing_run(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        runs.add_result(conn, 999, result("q0"))


def test_a_result_for_a_question_the_run_did_not_declare_is_refused(conn):
    """Runs are compared question by question, so a run must hold results for its own questions only."""
    run_id = runs.create_run(conn, replace(STACK_A, test_ids=["q0", "q1"]))
    with pytest.raises(sqlite3.IntegrityError, match="not part of this run"):
        runs.add_result(conn, run_id, result("q2"))
    assert runs.get_results(conn, run_id) == []


def test_results_of_one_run_do_not_mix_with_another(conn):
    first, second = runs.create_run(conn, STACK_A), runs.create_run(conn, STACK_B)
    runs.add_result(conn, first, result("q0"))
    runs.add_result(conn, second, result("q1"))
    assert [r.test_id for r in runs.get_results(conn, first)] == ["q0"]
    assert runs.progress(conn, second) == 0.1


def test_finishing_marks_done_or_failed_with_the_error(conn):
    done, failed = runs.create_run(conn, STACK_A), runs.create_run(conn, STACK_A)
    runs.finish_run(conn, done)
    runs.finish_run(conn, failed, error="RateLimitError: 429")
    assert (runs.get_run(conn, done).status, runs.get_run(conn, done).error) == ("done", None)
    assert (runs.get_run(conn, failed).status, runs.get_run(conn, failed).error) == ("failed", "RateLimitError: 429")


def test_unknown_run_raises_key_error(conn):
    with pytest.raises(KeyError):
        runs.get_run(conn, 999)
    with pytest.raises(KeyError):
        runs.progress(conn, 999)


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    """A tiny dataset in place of the committed one."""
    (tmp_path / "kb" / "company").mkdir(parents=True)
    (tmp_path / "tests.jsonl").write_bytes(b'{"id": "q1"}\n')
    (tmp_path / "kb" / "company" / "a.md").write_bytes(b"Founded in 2011.\nAustin.\n")
    monkeypatch.setattr(schema, "DATA_DIR", tmp_path)
    monkeypatch.setattr(schema, "KB_DIR", tmp_path / "kb")
    monkeypatch.setattr(schema, "TESTS_PATH", tmp_path / "tests.jsonl")
    return tmp_path


def test_the_dataset_hash_is_stable_and_changes_with_any_test_or_document(dataset):
    original = schema.dataset_sha256()
    assert schema.dataset_sha256() == original
    (dataset / "kb" / "company" / "a.md").write_bytes(b"Founded in 2012.\nAustin.\n")
    edited_doc = schema.dataset_sha256()
    (dataset / "tests.jsonl").write_bytes(b'{"id": "q2"}\n')
    assert len({original, edited_doc, schema.dataset_sha256()}) == 3


def test_the_dataset_hash_changes_when_a_document_is_renamed_added_or_removed(dataset):
    original = schema.dataset_sha256()
    (dataset / "kb" / "company" / "a.md").rename(dataset / "kb" / "company" / "b.md")
    renamed = schema.dataset_sha256()
    (dataset / "kb" / "company" / "c.md").write_bytes(b"New.\n")
    added = schema.dataset_sha256()
    (dataset / "kb" / "company" / "b.md").unlink()
    assert len({original, renamed, added, schema.dataset_sha256()}) == 4


def test_the_dataset_hash_ignores_line_endings(dataset):
    original = schema.dataset_sha256()
    (dataset / "kb" / "company" / "a.md").write_bytes(b"Founded in 2011.\r\nAustin.\r\n")
    assert schema.dataset_sha256() == original
