"""One ladder step on one stack (T50): what it needs, what it should cost, and getting its chunks and index ready."""

import json
import sqlite3
from collections.abc import Callable

from rag_playground.chunking.chunk_sets import METHOD as FIXED_METHOD
from rag_playground.chunking.chunk_sets import chunk_set_id, load_or_build
from rag_playground.datasets.schema import TestCase, load_tests
from rag_playground.rag import enrich_run, estimate, ladder, ladder_runs, pipeline, prompts
from rag_playground.rag.ladder import Config, Progress
from rag_playground.rag.runs import insert
from rag_playground.scoring.selection import Candidate
from rag_playground.settings import settings
from rag_playground.stacks import indexes


def dev_tests() -> list[TestCase]:
    """The ladder runs on every dev question, never on held-out ones."""
    return [t for t in load_tests() if t.split == "dev"]


def chosen_prompts(conn: sqlite3.Connection, stack: str) -> tuple[str, ...] | None:
    """The versions chosen for S6 on a stack, None until the user has chosen."""
    row = conn.execute("SELECT names FROM ladder_prompts WHERE stack = ?", (stack,)).fetchone()
    return tuple(json.loads(row["names"])) if row else None


def replay(conn: sqlite3.Connection, stack: str, result: Callable[[Config], Candidate | None],
           proposed: tuple[str, ...] | None) -> Progress:
    """Walk the ladder over `result`; a choice already saved for S6 outranks a `proposed` one."""
    prompts.ensure_default(conn)
    chosen = chosen_prompts(conn, stack)
    return ladder.walk(result, prompts.DEFAULT_NAME, proposed if chosen is None else chosen)


def progress(conn: sqlite3.Connection, stack: str, proposed: tuple[str, ...] | None = None) -> Progress:
    """Where the ladder stands on a stack."""
    return replay(conn, stack, ladder_runs.finder(conn, stack), proposed)


def next_step(conn: sqlite3.Connection, stack: str, prompt_names: tuple[str, ...] | None) -> Progress:
    """The step to run now, refused if its estimate is over the budget. An S6 choice is final, so it is saved only
    once it has passed every check: at most 4 versions, all known, within the budget. An empty choice skips S6."""
    now = progress(conn, stack)
    choosing = now.next_step == "S6" and not now.missing
    if choosing:
        if prompt_names is None:
            raise ValueError("Choose the prompt versions for S6 first")
        now = progress(conn, stack, prompt_names)
    if now.next_step is None:
        raise ValueError(f"The ladder is finished on Stack {stack}")
    check_budget(conn, now.missing)
    if choosing:
        insert(conn, "ladder_prompts", {"stack": stack, "names": json.dumps(prompt_names)})
    return now


def run_cost(conn: sqlite3.Connection, config: Config) -> float:
    """A configuration's estimated run (T43). Answers read the original chunks, enriched or not (T47)."""
    return estimate.run_cost(dev_tests(), prompts.get(conn, config.prompt_name), config.answer_model, config.top_k,
                             config.rerank, load_or_build(config.chunk_size, config.overlap))


def enrichment_cost(config: Config) -> float:
    """What is left to pay to enrich a configuration's chunk set; both stacks share the enriched set."""
    if config.method == FIXED_METHOD:
        return 0.0
    load_or_build(config.chunk_size, config.overlap)
    return enrich_run.remaining_cost(chunk_set_id(config.chunk_size, config.overlap))


def step_cost(conn: sqlite3.Connection, missing: list[Config]) -> float:
    """Estimated OpenRouter dollars for a step. Stack A's index builds and searches are OpenAI's, not counted (T44)."""
    return sum(run_cost(conn, config) + enrichment_cost(config) for config in missing)


def check_budget(conn: sqlite3.Connection, missing: list[Config]) -> None:
    """Refuse a step whose estimate is over what is left of BUDGET_USD, before anything is paid."""
    cost, left = step_cost(conn, missing), pipeline.remaining(conn)
    if cost > left:
        raise pipeline.BudgetExceeded(f"The step is estimated at ${cost:.4f}, but only ${left:.4f} of BUDGET_USD "
                                      f"${settings.budget_usd:.2f} is left")


def prepare(conn: sqlite3.Connection, stack: str, config: Config) -> None:
    """Build what a run needs and does not have yet: the chunk set, its paid enrichment, the stack's index."""
    load_or_build(config.chunk_size, config.overlap)
    if config.method != FIXED_METHOD:
        enrich_run.enrich_set(conn, chunk_set_id(config.chunk_size, config.overlap))
    set_id = ladder_runs.choices(stack, config).chunk_set_id
    if indexes.lookup(conn, stack, set_id) is None:
        indexes.build(conn, stack, set_id)
