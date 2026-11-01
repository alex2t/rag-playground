"""Step 6 checks of spend recording (T44), with fake OpenRouter replies (no network, no cost)."""

import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest
from openai.types.chat import ParsedChatCompletion
from pydantic import BaseModel

from rag_playground import store
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.datasets.schema import load_tests
from rag_playground.llm import openrouter
from rag_playground.llm.models import ModelInfo
from rag_playground.llm.openrouter import ChatResult, paid
from rag_playground.rag import estimate, pipeline, prompts, runs, spend
from rag_playground.rag.rerank import Reranked
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import settings
from rag_playground.stacks.hits import Hit

DEV = [t for t in load_tests() if t.split == "dev"][:3]
CHOICES = pipeline.Choices(stack="B", chunk_set_id="fixed__c1024__o200", top_k=2, hybrid=False,
                           openai_ranking=None, rerank=True, answer_model="openai/gpt-4.1-nano",
                           prompt_name="default")
VERDICT = Judgement(refused=False, accuracy=5, completeness=5, relevance=5, faithfulness=5, feedback="ok",
                    faithfulness_feedback="ok")


class Grade(BaseModel):
    score: int


def call(cost: float, model: str = "m", tokens: tuple[int, int, int] = (10, 2, 0)) -> ChatResult:
    return ChatResult(text="An answer.", model=model, canonical_slug=f"{model}-1", temperature_controlled=True,
                      prompt_tokens=tokens[0], completion_tokens=tokens[1], reasoning_tokens=tokens[2],
                      cost_usd=cost)


def info(model_id: str) -> ModelInfo:
    return ModelInfo(model_id, f"{model_id}-2026", frozenset({"temperature"}), 0.0, 0.0)


def reply(cost: float) -> ParsedChatCompletion:
    return ParsedChatCompletion[Grade].model_validate({
        "id": "gen-1", "object": "chat.completion", "created": 0, "model": "openai/gpt-4.1-nano",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": '{"score": 3}', "parsed": {"score": 3}}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 30, "total_tokens": 42, "cost": cost},
    })


@pytest.fixture
def conn(tmp_path):
    connection = store.connect(tmp_path / "test.db")
    prompts.ensure_default(connection)
    yield connection
    connection.close()


@pytest.fixture
def fake_openrouter(monkeypatch):
    """OpenRouter client whose create() and parse() return a reply costing $0.25."""
    completions = SimpleNamespace(create=lambda **kwargs: reply(0.25), parse=lambda **kwargs: reply(0.25))
    monkeypatch.setattr(openrouter, "client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    monkeypatch.setattr(openrouter, "model_info", info)


def test_chat_and_chat_structured_report_each_returned_call(fake_openrouter):
    seen = []
    token = openrouter.cost_listener.set(seen.append)
    try:
        openrouter.chat("openai/gpt-4.1-nano", [])
        openrouter.chat_structured("openai/gpt-4.1-nano", [], Grade)
    finally:
        openrouter.cost_listener.reset(token)
    assert [(r.cost_usd, r.prompt_tokens, r.completion_tokens) for r in seen] == [(0.25, 12, 30)] * 2


def test_calls_outside_a_recording_block_are_not_recorded(conn, fake_openrouter):
    with spend.recording(conn, None):
        openrouter.chat("openai/gpt-4.1-nano", [])
    openrouter.chat("openai/gpt-4.1-nano", [])
    assert conn.execute("SELECT count(*) FROM spend").fetchone()[0] == 1


def test_each_call_is_written_when_it_returns_with_its_tokens_and_cost(conn):
    with spend.recording(conn, None):
        paid(call(0.5, model="openai/gpt-4.1-mini", tokens=(100, 20, 7)))
        rows = conn.execute("SELECT run_id, model, prompt_tokens, completion_tokens, reasoning_tokens, cost_usd "
                            "FROM spend").fetchall()
    assert [tuple(row) for row in rows] == [(None, "openai/gpt-4.1-mini", 100, 20, 7, 0.5)]


def test_the_listener_is_removed_when_the_block_fails(conn):
    with pytest.raises(RuntimeError), spend.recording(conn, None):
        raise RuntimeError("boom")
    paid(call(0.5))
    assert spend.total(conn) == 0


@pytest.fixture
def offline_runs(monkeypatch):
    """Runs can start with no network: model versions and prices are fake (prices 0, so every estimate is $0),
    the chunk set is a single chunk, and the budget is $60."""
    monkeypatch.setattr(pipeline, "model_info", info)
    monkeypatch.setattr(estimate, "model_info", info)
    chunk = Chunk(chunk_id="d.md#0", source="d.md", doc_type="d", index=0, text="x", tokens=100, start=0, end=1)
    monkeypatch.setattr(pipeline, "load_chunk_set", lambda set_id: [chunk])
    monkeypatch.setattr(settings, "budget_usd", 60.0)


def test_total_sums_one_run_or_everything(conn, offline_runs):
    first, second = (pipeline.start_run(conn, CHOICES, DEV) for _ in range(2))
    spend.record(conn, first, call(0.25))
    spend.record(conn, first, call(0.5))
    spend.record(conn, second, call(1.0))
    spend.record(conn, None, call(2.0))
    assert spend.total(conn, first) == 0.75
    assert spend.total(conn, second) == 1.0
    assert spend.total(conn) == 3.75


def test_total_is_zero_with_no_spend(conn):
    assert spend.total(conn) == 0
    assert spend.total(conn, 1) == 0


@pytest.mark.parametrize("row", [{"cost_usd": -0.01}, {"run_id": 999}])
def test_the_table_refuses_a_negative_cost_or_an_unknown_run(conn, row):
    good = {"run_id": None, "model": "m", "prompt_tokens": 1, "completion_tokens": 1, "reasoning_tokens": 0,
            "cost_usd": 0.0}
    with pytest.raises(sqlite3.IntegrityError):
        runs.insert(conn, "spend", good | row)


@pytest.fixture
def paying_fakes(monkeypatch, offline_runs):
    """Reranker, answer model and judge that report their calls like the real ones; the judge's second call fails
    on the second question."""
    asked = []

    def rerank(question, hits, k):
        return Reranked(hits[:k], paid(call(0.001)), repaired=False)

    def answer(model, prompt, question, hits):
        asked.append(question)
        return paid(call(0.01))

    def judge(test, context, text):
        first = paid(call(0.002))
        if test.id == DEV[1].id:
            raise RuntimeError("judge reply could not be read")
        return VERDICT, [first, paid(call(0.003))]

    monkeypatch.setattr(pipeline, "rerank", rerank)
    monkeypatch.setattr(pipeline, "answer", answer)
    monkeypatch.setattr(pipeline, "judge", judge)


def retrieve(question, k):
    return [Hit(f"c{i}", f"doc{i}.md", 1.0, "text") for i in range(k)]


def test_a_run_records_the_calls_of_a_question_that_failed_halfway(conn, paying_fakes):
    """Questions 1 and 3 complete; question 2 pays for its rerank, answer and first judge call, then fails."""
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    with pytest.raises(RuntimeError):
        pipeline.execute(conn, run_id, retrieve)
    stored = sum(r.cost_usd for r in runs.get_results(conn, run_id))
    assert stored == pytest.approx(2 * 0.016)
    assert spend.total(conn, run_id) == pytest.approx(2 * 0.016 + 0.001 + 0.01 + 0.002)
    assert conn.execute("SELECT count(*) FROM spend WHERE run_id = ?", (run_id,)).fetchone()[0] == 2 * 4 + 3


def test_a_completed_run_records_the_same_spend_as_its_results(conn, paying_fakes, monkeypatch):
    monkeypatch.setattr(pipeline, "judge", lambda test, context, text: (VERDICT, [paid(call(0.002)),
                                                                               paid(call(0.003))]))
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    pipeline.execute(conn, run_id, retrieve)
    assert spend.total(conn, run_id) == pytest.approx(sum(r.cost_usd for r in runs.get_results(conn, run_id)))
    assert spend.total(conn, run_id) == pytest.approx(3 * 0.016)


STACK_A = runs.RunMeta(
    stack="A", split="dev", test_ids=[t.id for t in DEV], chunk_set_id="fixed__c1024__o200", top_k=2, hybrid=False,
    openai_ranking={"ranker": "auto"}, answer_model="m", answer_slug="m-1", judge_model="j", judge_slug="j-1",
    rerank_model=None, rerank_slug=None, rerank_candidates=None, temperature_controlled=True, prompt_name="default",
    prompt_sha256=prompts.sha256(prompts.DEFAULT_TEXT), dataset_sha256="d" * 64, app_version="test")
STACK_B = replace(STACK_A, stack="B", openai_ranking=None)


def stored(conn, meta, questions):
    run_id = runs.create_run(conn, meta)
    for test in DEV[:questions]:
        runs.add_result(conn, run_id, runs.Result(test_id=test.id, hits=[], rerank_repaired=None, answer="a",
                                                  judgement=VERDICT, cost_usd=0.001, latency_s=1.0))
    return run_id


def test_each_stored_stack_a_question_adds_one_search_fee(conn):
    """T53: the total is the paid calls plus $0.0025 per Stack A question; the stored result costs are not added."""
    run_id = stored(conn, STACK_A, 3)
    spend.record(conn, run_id, call(0.25))
    assert spend.total(conn, run_id) == pytest.approx(0.25 + 3 * 0.0025)
    assert spend.total(conn) == pytest.approx(0.25 + 3 * 0.0025)


def test_stack_b_pays_no_search_fee(conn):
    run_id = stored(conn, STACK_B, 3)
    assert spend.total(conn, run_id) == spend.total(conn) == 0


def test_a_runs_total_counts_only_its_own_searches(conn):
    first, second = stored(conn, STACK_A, 2), stored(conn, STACK_A, 1)
    stored(conn, STACK_B, 3)
    assert spend.total(conn, first) == pytest.approx(2 * 0.0025)
    assert spend.total(conn, second) == pytest.approx(0.0025)
    assert spend.total(conn) == pytest.approx(3 * 0.0025)


def test_the_fee_is_the_one_measured_on_the_bill():
    """20, 192 and 1,344 searches were billed $0.05, $0.48 and $3.36 (T53)."""
    for searches, billed in [(20, 0.05), (192, 0.48), (1344, 3.36)]:
        assert searches * spend.search_fee("A") == pytest.approx(billed)
    assert spend.search_fee("B") == 0
