"""The evaluation pipeline: for each question retrieve, optionally rerank, answer, judge, then store the result.

Retrieval is passed in as a function, so the pipeline is the same for both stacks."""

import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from contextvars import copy_context
from dataclasses import dataclass
from itertools import accumulate, takewhile
from statistics import fmean
from time import perf_counter

from rag_playground.chunking.chunk_sets import load as load_chunk_set
from rag_playground.datasets.schema import TestCase, dataset_sha256, load_tests
from rag_playground.llm.models import model_info
from rag_playground.llm.openrouter import ChatResult
from rag_playground.rag import estimate, prompts, runs, spend
from rag_playground.rag.answer import answer
from rag_playground.rag.rerank import rerank
from rag_playground.scoring.judging import judge
from rag_playground.settings import JUDGE_MODEL, PARALLEL_QUESTIONS, RERANK_CANDIDATES, RERANK_MODEL, settings
from rag_playground.stacks.hits import Hit

Retrieve = Callable[[str, int], list[Hit]]


class BudgetExceeded(Exception):
    """Spending more would take all recorded spend past BUDGET_USD (D15)."""


def remaining(conn: sqlite3.Connection) -> float:
    """Dollars left of BUDGET_USD, after every recorded paid call (T44) and Stack A's search fees (T53)."""
    return settings.budget_usd - spend.total(conn)


@dataclass(frozen=True)
class Choices:
    """The settings the user picks for a run (T35, T40)."""

    stack: str
    chunk_set_id: str
    top_k: int
    hybrid: bool
    openai_ranking: dict | None
    rerank: bool
    answer_model: str
    prompt_name: str


def build_meta(choices: Choices, prompt: prompts.PromptVersion, tests: list[TestCase]) -> runs.RunMeta:
    """The run's metadata, taken from the same values the pipeline uses: model versions are read once per run,
    the split and the question ids come from the tests."""
    test_ids = [test.id for test in tests]
    if len(set(test_ids)) != len(test_ids):
        raise ValueError("A run asks each question once")
    splits = {test.split.value for test in tests}
    if len(splits) != 1:
        raise ValueError(f"A run uses one split, got {sorted(splits)}")
    split = splits.pop()
    used = [choices.answer_model, JUDGE_MODEL] + ([RERANK_MODEL] if choices.rerank else [])
    return runs.RunMeta(
        stack=choices.stack, split=split, test_ids=test_ids, chunk_set_id=choices.chunk_set_id,
        top_k=choices.top_k, hybrid=choices.hybrid, openai_ranking=choices.openai_ranking,
        answer_model=choices.answer_model, answer_slug=model_info(choices.answer_model).canonical_slug,
        judge_model=JUDGE_MODEL, judge_slug=model_info(JUDGE_MODEL).canonical_slug,
        rerank_model=RERANK_MODEL if choices.rerank else None,
        rerank_slug=model_info(RERANK_MODEL).canonical_slug if choices.rerank else None,
        rerank_candidates=RERANK_CANDIDATES if choices.rerank else None,
        temperature_controlled=all(model_info(m).supports_temperature for m in used),
        prompt_name=prompt.name, prompt_sha256=prompt.sha256, dataset_sha256=dataset_sha256(),
        app_version=settings.app_version)


@dataclass(frozen=True)
class Answered:
    """A question searched and answered, not yet judged. `calls` are the paid calls so far; latency is what a user
    waits for."""

    hits: list[Hit]
    repaired: bool | None
    reply: ChatResult
    calls: list[ChatResult]
    latency_s: float


def search_and_answer(question: str, top_k: int, rerank_candidates: int | None, answer_model: str,
                      prompt: prompts.PromptVersion, retrieve: Retrieve) -> Answered:
    """Search, rerank if `rerank_candidates` is set, and answer: one path for runs and for the Ask page, so both read
    the same chunks."""
    start = perf_counter()
    calls, repaired = [], None
    if rerank_candidates:
        reranked = rerank(question, retrieve(question, rerank_candidates), top_k)
        hits, repaired = reranked.hits, reranked.repaired
        calls += [reranked.result] if reranked.result else []
    else:
        hits = retrieve(question, top_k)
    reply = answer(answer_model, prompt, question, hits)
    return Answered(hits, repaired, reply, [*calls, reply], perf_counter() - start)


def run_question(test: TestCase, meta: runs.RunMeta, prompt: prompts.PromptVersion, retrieve: Retrieve) -> runs.Result:
    """Answer and judge one question. Latency covers what a user waits for (retrieval, rerank, answer), not the
    judge; cost covers every call, the judge included."""
    done = search_and_answer(test.question, meta.top_k, meta.rerank_candidates if meta.rerank_model else None,
                             meta.answer_model, prompt, retrieve)
    verdict, judge_calls = judge(test, [hit.text for hit in done.hits], done.reply.text)
    cost = sum(call.cost_usd for call in [*done.calls, *judge_calls])
    return runs.Result(test_id=test.id, hits=done.hits, rerank_repaired=done.repaired, answer=done.reply.text,
                       judgement=verdict, cost_usd=cost, latency_s=done.latency_s)


def evaluated_on_dev(conn: sqlite3.Connection, prompt_name: str) -> bool:
    """Whether a prompt version has a finished run on dev questions."""
    return conn.execute("SELECT 1 FROM runs WHERE prompt_name = ? AND split = 'dev' AND status = 'done'",
                        (prompt_name,)).fetchone() is not None


def plan_run(conn: sqlite3.Connection, choices: Choices, tests: list[TestCase]) -> tuple[runs.RunMeta, float]:
    """A run's metadata and estimate (T43), storing nothing. A held-out run uses the default prompt or a version
    already evaluated on dev questions: held-out questions confirm a choice made on dev, never make one (T36
    revision)."""
    prompt = prompts.get(conn, choices.prompt_name)
    meta = build_meta(choices, prompt, tests)
    if meta.split == "heldout" and prompt.name != prompts.DEFAULT_NAME and not evaluated_on_dev(conn, prompt.name):
        raise ValueError(f"Held-out runs use the default prompt or a version evaluated on dev questions; "
                         f"{prompt.name!r} has no finished dev run")
    return meta, estimate.run_cost(tests, prompt, choices.answer_model, choices.top_k, choices.rerank,
                                   load_chunk_set(choices.chunk_set_id), choices.stack)


def start_run(conn: sqlite3.Connection, choices: Choices, tests: list[TestCase]) -> int:
    """Store a new run with its metadata and return its id, before any question is asked. A run `plan_run` refuses, or
    whose estimate exceeds what is left of BUDGET_USD, stores nothing."""
    meta, cost = plan_run(conn, choices, tests)
    if cost > remaining(conn):
        raise BudgetExceeded(f"The run is estimated at ${cost:.4f}, but only ${remaining(conn):.4f} of "
                             f"BUDGET_USD ${settings.budget_usd:.2f} is left")
    return runs.create_run(conn, meta)


def check_budget(conn: sqlite3.Connection, next_cost: float) -> None:
    """Raise BudgetExceeded if the next question could take spend past BUDGET_USD."""
    if next_cost > remaining(conn):
        raise BudgetExceeded(f"Budget reached: ${spend.total(conn):.4f} spent of BUDGET_USD "
                             f"${settings.budget_usd:.2f}; the next question could cost ${next_cost:.4f}")


def fitting(conn: sqlite3.Connection, assumed: list[float]) -> int:
    """How many of the next questions can run together: their assumed costs, all in flight at once, stay within
    what is left of BUDGET_USD."""
    left = remaining(conn)
    return len(list(takewhile(lambda total: total <= left, accumulate(assumed))))


def ask_together(conn: sqlite3.Connection, run_id: int, pool: ThreadPoolExecutor, tests: list[TestCase],
                 meta: runs.RunMeta, prompt: prompts.PromptVersion, retrieve: Retrieve) -> float:
    """Ask the questions at once and store their results in question order; return the most expensive one's cost. Each
    gets its own copy of the context, or its paid calls would not reach the spend listener. Every question ends before
    anything is stored, so no other thread is writing. A question that failed does not cost the others their paid
    results: those are stored first, then the first failure is raised."""
    asked = [pool.submit(copy_context().run, run_question, test, meta, prompt, retrieve) for test in tests]
    wait(asked)
    for future in asked:
        if not future.exception():
            runs.add_result(conn, run_id, future.result())
    return max(future.result().cost_usd for future in asked)


def execute(conn: sqlite3.Connection, run_id: int, retrieve: Retrieve) -> None:
    """Answer the run's own questions with its stored settings, up to PARALLEL_QUESTIONS at once, storing each batch
    as soon as it is judged so progress can be read meanwhile; every paid call is recorded as it returns (T44). The
    questions are read from the run, so they cannot differ from the ones it declared. The first question runs alone:
    it shows a dead service for one question's cost, loads the embedding model once, and gives the guard a real cost.
    Before each batch the guard keeps only the questions that fit in the budget together, each assumed to cost the
    larger of its estimate (T43) and the run's most expensive question so far, since the estimate is low for reasoning
    models; if not even one fits, the run stops. A failure, or that stop, marks the run failed with the error, which is
    raised again."""
    run = runs.get_run(conn, run_id)
    if run.status != "running":
        raise ValueError(f"Run {run_id} is {run.status}; a finished run is never run again")
    meta = run.meta
    prompt = prompts.get(conn, meta.prompt_name)
    by_id = {test.id: test for test in load_tests()}
    tests = [by_id[test_id] for test_id in meta.test_ids]
    largest, done = 0.0, 0
    try:
        chunk_tokens = fmean(chunk.tokens for chunk in load_chunk_set(meta.chunk_set_id))
        with spend.recording(conn, run_id), ThreadPoolExecutor(PARALLEL_QUESTIONS, "job-question") as pool:
            while done < len(tests):
                size = PARALLEL_QUESTIONS if done else 1
                assumed = [max(largest, estimate.question_cost(test, prompt, meta.answer_model, meta.top_k,
                                                               meta.rerank_model is not None, chunk_tokens, meta.stack))
                           for test in tests[done:done + size]]
                check_budget(conn, assumed[0])
                count = fitting(conn, assumed)
                cost = ask_together(conn, run_id, pool, tests[done:done + count], meta, prompt, retrieve)
                largest, done = max(largest, cost + spend.search_fee(meta.stack)), done + count
    except Exception as exc:
        runs.finish_run(conn, run_id, error=f"{type(exc).__name__}: {exc}")
        raise
    runs.finish_run(conn, run_id)
