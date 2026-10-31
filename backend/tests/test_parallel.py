"""Questions of one run asked in parallel: spend still recorded, the budget still holds, results stay in order.
Fake models (no network, no cost). Amounts are powers of two, so every sum is exact."""

import threading
from contextvars import copy_context

import pytest

from rag_playground import store
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.datasets.schema import load_tests
from rag_playground.llm.models import ModelInfo
from rag_playground.llm.openrouter import ChatResult, paid
from rag_playground.rag import pipeline, prompts, runs, spend
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import PARALLEL_QUESTIONS, settings
from rag_playground.stacks import qdrant_store
from rag_playground.stacks.hits import Hit

DEV = [t for t in load_tests() if t.split == "dev"][:11]
CHOICES = pipeline.Choices(stack="B", chunk_set_id="fixed__c512__o0", top_k=3, hybrid=False, openai_ranking=None,
                           rerank=False, answer_model="openai/gpt-4.1-nano", prompt_name="default")
CHUNKS = [Chunk(chunk_id="d.md#0", source="d.md", doc_type="d", index=0, text="x", tokens=100, start=0, end=1)]
VERDICT = Judgement(refused=False, accuracy=5, completeness=5, relevance=5, faithfulness=5, feedback="ok",
                    faithfulness_feedback="ok")
WAIT_S = 10


def call(cost: float) -> ChatResult:
    return ChatResult(text="An answer.", model="m", canonical_slug="m-1", temperature_controlled=True,
                      prompt_tokens=1, completion_tokens=1, reasoning_tokens=0, cost_usd=cost)


def retrieve(question, k):
    return [Hit("c", "d.md", 1.0, "text")]


@pytest.fixture
def conn(tmp_path):
    connection = store.connect(tmp_path / "test.db")
    prompts.ensure_default(connection)
    yield connection
    connection.close()


@pytest.fixture
def world(monkeypatch):
    """Budget $64; each question costs `cost` (one paid answer call, the judge free) and is estimated at `guess`;
    `on_answer` runs in the question's thread."""
    state = {"cost": 0.25, "guess": 0.25, "on_answer": lambda question: None}
    monkeypatch.setattr(settings, "budget_usd", 64.0)
    monkeypatch.setattr(pipeline, "model_info", lambda m: ModelInfo(m, f"{m}-1", frozenset(), 0.0, 0.0))
    monkeypatch.setattr(pipeline, "load_chunk_set", lambda set_id: CHUNKS)
    monkeypatch.setattr(pipeline.estimate, "run_cost", lambda *args: 0.0)
    monkeypatch.setattr(pipeline.estimate, "question_cost", lambda *args: state["guess"])

    def answer(model, prompt, question, hits):
        state["on_answer"](question)
        return paid(call(state["cost"]))

    monkeypatch.setattr(pipeline, "answer", answer)
    monkeypatch.setattr(pipeline, "judge", lambda test, context, text: (VERDICT, []))
    return state


def test_after_the_first_question_a_full_batch_really_runs_at_the_same_time(conn, world):
    """The barrier opens only if PARALLEL_QUESTIONS threads are inside the answer call together; one at a time it
    would time out and fail the run. The first question and the last one run below a full batch."""
    together = threading.Barrier(PARALLEL_QUESTIONS, timeout=WAIT_S)
    tests = DEV[:1 + 2 * PARALLEL_QUESTIONS]
    first = tests[0].question
    world["on_answer"] = lambda question: None if question == first else together.wait()
    run_id = pipeline.start_run(conn, CHOICES, tests)
    pipeline.execute(conn, run_id, retrieve)
    assert runs.get_run(conn, run_id).status == "done"


def test_never_more_than_the_limit_at_once(conn, world):
    lock, inside, peak = threading.Lock(), [0], [0]
    gate = threading.Barrier(PARALLEL_QUESTIONS, timeout=WAIT_S)

    def on_answer(question):
        with lock:
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        if question != DEV[0].question:
            gate.wait()
        with lock:
            inside[0] -= 1

    world["on_answer"] = on_answer
    pipeline.execute(conn, pipeline.start_run(conn, CHOICES, DEV[:6]), retrieve)
    assert peak[0] == PARALLEL_QUESTIONS


def test_paid_calls_in_every_thread_are_recorded_under_the_run(conn, world):
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    pipeline.execute(conn, run_id, retrieve)
    rows = conn.execute("SELECT run_id FROM spend").fetchall()
    assert [row[0] for row in rows] == [run_id] * len(DEV)
    assert spend.total(conn, run_id) == 0.25 * len(DEV)


def test_spend_written_from_many_threads_at_once_all_arrives(conn):
    """Threads released together write through one connection, as parallel questions do; each row must arrive."""
    writers, writes = 8, 100
    start, errors = threading.Barrier(writers, timeout=WAIT_S), []

    def write():
        start.wait()
        try:
            for _ in range(writes):
                paid(call(0.25))
        except Exception as exc:
            errors.append(exc)

    with spend.recording(conn, None):
        threads = [threading.Thread(target=copy_context().run, args=(write,)) for _ in range(writers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
    assert errors == []
    assert conn.execute("SELECT count(*) FROM spend").fetchone()[0] == writers * writes


def test_results_are_stored_in_question_order_whatever_finishes_first(conn, world, monkeypatch):
    """The batch's first question waits until the second has finished."""
    second_done, batch = threading.Event(), DEV[1:3]

    def on_answer(question):
        if question == batch[0].question:
            assert second_done.wait(WAIT_S)

    def judge(test, context, text):
        if test.id == batch[1].id:
            second_done.set()
        return VERDICT, []

    world["on_answer"] = on_answer
    monkeypatch.setattr(pipeline, "judge", judge)
    run_id = pipeline.start_run(conn, CHOICES, DEV[:3])
    pipeline.execute(conn, run_id, retrieve)
    assert [r.test_id for r in runs.get_results(conn, run_id)] == [t.id for t in DEV[:3]]


def test_a_batch_shrinks_to_what_the_budget_can_pay_for_in_flight(conn, world, monkeypatch):
    """$1 budget, $0.25 per question exactly as guessed: 1 alone, then 3 together. A full batch of 5 would have
    ended at $1.50; it never starts."""
    monkeypatch.setattr(settings, "budget_usd", 1.0)
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    with pytest.raises(pipeline.BudgetExceeded):
        pipeline.execute(conn, run_id, retrieve)
    assert spend.total(conn) == 1.0
    assert len(runs.get_results(conn, run_id)) == 4
    assert runs.get_run(conn, run_id).status == "failed"


def test_the_batch_is_guarded_with_the_largest_cost_so_far(conn, world, monkeypatch):
    """Estimate $0.125 but real $0.25: judged by the estimate, 5 more would start at $0.25 spent ($0.875 in flight,
    within $1.25) and end at $1.50. The real first cost allows 4."""
    monkeypatch.setattr(settings, "budget_usd", 1.25)
    world["guess"] = 0.125
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    with pytest.raises(pipeline.BudgetExceeded):
        pipeline.execute(conn, run_id, retrieve)
    assert spend.total(conn) == 1.25


def test_a_failed_question_lets_the_others_finish_and_their_spend_stays(conn, world):
    """A question in the middle fails; the 4 others of its batch end, are paid and keep their results, and with the
    first question that is 5. The run is failed and no thread is left writing afterwards."""
    bad = DEV[3].question

    def on_answer(question):
        if question == bad:
            raise RuntimeError("the model is down")

    world["on_answer"] = on_answer
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    with pytest.raises(RuntimeError):
        pipeline.execute(conn, run_id, retrieve)
    run = runs.get_run(conn, run_id)
    assert run.status == "failed" and run.error == "RuntimeError: the model is down"
    assert spend.total(conn, run_id) == 0.25 * 5
    assert len(runs.get_results(conn, run_id)) == 5
    assert [t.name for t in threading.enumerate() if t.name.startswith("job-question")] == []


def test_a_first_question_that_fails_starts_no_other(conn, world):
    asked = []

    def on_answer(question):
        asked.append(question)
        raise RuntimeError("the model is down")

    world["on_answer"] = on_answer
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    with pytest.raises(RuntimeError):
        pipeline.execute(conn, run_id, retrieve)
    assert asked == [DEV[0].question]


@pytest.mark.parametrize("hybrid", [False, True])
def test_stack_b_embeds_one_question_at_a_time(monkeypatch, hybrid):
    """Five threads in `search`: the embedding work never overlaps, on an 8 GB PC."""
    lock, inside, peak = threading.Lock(), [0], [0]
    start = threading.Barrier(PARALLEL_QUESTIONS, timeout=WAIT_S)

    def embed_query(text):
        with lock:
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        threading.Event().wait(0.02)
        with lock:
            inside[0] -= 1
        return [0.0]

    class Points:
        points = []

    class Fake:
        def query_points(self, *args, **kwargs):
            return Points

    monkeypatch.setattr(qdrant_store.nomic, "embed_query", embed_query)
    monkeypatch.setattr(qdrant_store, "bm25", lambda: type("M", (), {"query_embed": lambda s, q: [type(
        "E", (), {"indices": type("A", (), {"tolist": lambda s: [1]})(),
                  "values": type("A", (), {"tolist": lambda s: [1.0]})()})()]})())

    def search():
        start.wait()
        qdrant_store.search(Fake(), "c", "q", 2, hybrid)

    threads = [threading.Thread(target=search) for _ in range(PARALLEL_QUESTIONS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT_S)
    assert peak[0] == 1
