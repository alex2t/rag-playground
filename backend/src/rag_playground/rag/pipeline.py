"""The evaluation pipeline: for each question retrieve, optionally rerank, answer, judge, then store the result.

Retrieval is passed in as a function, so the pipeline is the same for both stacks."""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from statistics import fmean
from time import perf_counter

from rag_playground.chunking.chunk_sets import load as load_chunk_set
from rag_playground.datasets.schema import TestCase, dataset_sha256, load_tests
from rag_playground.llm.models import model_info
from rag_playground.rag import estimate, prompts, runs, spend
from rag_playground.rag.answer import answer
from rag_playground.rag.rerank import rerank
from rag_playground.scoring.judging import judge
from rag_playground.settings import JUDGE_MODEL, RERANK_CANDIDATES, RERANK_MODEL, settings
from rag_playground.stacks.hits import Hit

Retrieve = Callable[[str, int], list[Hit]]


class BudgetExceeded(Exception):
    """Spending more would take all recorded spend past BUDGET_USD (D15)."""


def remaining(conn: sqlite3.Connection) -> float:
    """Dollars left of BUDGET_USD, after every recorded paid call (T44)."""
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
    the split and the question ids come from the tests. Held-out runs use the default prompt only (T36)."""
    test_ids = [test.id for test in tests]
    if len(set(test_ids)) != len(test_ids):
        raise ValueError("A run asks each question once")
    splits = {test.split.value for test in tests}
    if len(splits) != 1:
        raise ValueError(f"A run uses one split, got {sorted(splits)}")
    split = splits.pop()
    if split == "heldout" and prompt.name != prompts.DEFAULT_NAME:
        raise ValueError("Held-out runs use the default prompt version only")
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


def run_question(test: TestCase, meta: runs.RunMeta, prompt: prompts.PromptVersion, retrieve: Retrieve) -> runs.Result:
    """Answer and judge one question. Latency covers what a user waits for (retrieval, rerank, answer), not the
    judge; cost covers every call, the judge included."""
    start = perf_counter()
    calls, repaired = [], None
    if meta.rerank_model:
        reranked = rerank(test.question, retrieve(test.question, meta.rerank_candidates), meta.top_k)
        hits, repaired = reranked.hits, reranked.repaired
        calls += [reranked.result] if reranked.result else []
    else:
        hits = retrieve(test.question, meta.top_k)
    reply = answer(meta.answer_model, prompt, test.question, hits)
    latency = perf_counter() - start
    verdict, judge_calls = judge(test, [hit.text for hit in hits], reply.text)
    cost = sum(call.cost_usd for call in [*calls, reply, *judge_calls])
    return runs.Result(test_id=test.id, hits=hits, rerank_repaired=repaired, answer=reply.text,
                       judgement=verdict, cost_usd=cost, latency_s=latency)


def start_run(conn: sqlite3.Connection, choices: Choices, tests: list[TestCase]) -> int:
    """Store a new run with its metadata and return its id, before any question is asked. A run whose
    estimate (T43) exceeds what is left of BUDGET_USD is refused, and nothing is stored."""
    prompt = prompts.get(conn, choices.prompt_name)
    meta = build_meta(choices, prompt, tests)
    cost = estimate.run_cost(tests, prompt, choices.answer_model, choices.top_k, choices.rerank,
                             load_chunk_set(choices.chunk_set_id))
    if cost > remaining(conn):
        raise BudgetExceeded(f"The run is estimated at ${cost:.4f}, but only ${remaining(conn):.4f} of "
                             f"BUDGET_USD ${settings.budget_usd:.2f} is left")
    return runs.create_run(conn, meta)


def check_budget(conn: sqlite3.Connection, next_cost: float) -> None:
    """Raise BudgetExceeded if the next question could take spend past BUDGET_USD."""
    if next_cost > remaining(conn):
        raise BudgetExceeded(f"Budget reached: ${spend.total(conn):.4f} spent of BUDGET_USD "
                             f"${settings.budget_usd:.2f}; the next question could cost ${next_cost:.4f}")


def execute(conn: sqlite3.Connection, run_id: int, retrieve: Retrieve) -> None:
    """Answer the run's own questions with its stored settings, storing each result as soon as it is judged so
    progress can be read meanwhile; every paid call is recorded as it returns (T44). The questions are read from
    the run, so they cannot differ from the ones it declared. Before each question the run stops if it could
    take spend past BUDGET_USD; the next question is assumed to cost the larger of its estimate (T43) and the
    run's most expensive question so far, since the estimate is low for reasoning models. A failure, or that
    stop, marks the run failed with the error, which is raised again."""
    run = runs.get_run(conn, run_id)
    if run.status != "running":
        raise ValueError(f"Run {run_id} is {run.status}; a finished run is never run again")
    meta = run.meta
    prompt = prompts.get(conn, meta.prompt_name)
    by_id = {test.id: test for test in load_tests()}
    largest = 0.0
    try:
        chunk_tokens = fmean(chunk.tokens for chunk in load_chunk_set(meta.chunk_set_id))
        with spend.recording(conn, run_id):
            for test in (by_id[test_id] for test_id in meta.test_ids):
                guess = estimate.question_cost(test, prompt, meta.answer_model, meta.top_k,
                                               meta.rerank_model is not None, chunk_tokens)
                check_budget(conn, max(guess, largest))
                result = run_question(test, meta, prompt, retrieve)
                runs.add_result(conn, run_id, result)
                largest = max(largest, result.cost_usd)
    except Exception as exc:
        runs.finish_run(conn, run_id, error=f"{type(exc).__name__}: {exc}")
        raise
    runs.finish_run(conn, run_id)
