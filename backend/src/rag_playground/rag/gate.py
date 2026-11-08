"""The evaluation gate (D36): the 20 smoke questions at S0 on one stack, from an empty database, scored like any run
and judged by the T08 gates. Paid: answers and judge on OpenRouter, Stack A's searches on OpenAI."""

import sqlite3

from rag_playground.chunking.chunk_sets import load_or_build
from rag_playground.rag import evaluation, ladder, ladder_runs, pipeline, prompts, runs
from rag_playground.run_requests import smoke_tests
from rag_playground.settings import GATE_STACK_A_INDEXES, S0
from rag_playground.stacks import indexes


def choices(stack: str) -> pipeline.Choices:
    """S0 on a stack, with the default prompt and the stack's own default search."""
    return ladder_runs.choices(stack, ladder.baseline(prompts.DEFAULT_NAME))


def prepare(conn: sqlite3.Connection, stack: str, chunk_set_id: str) -> None:
    """Make the chunk set searchable on the stack: Stack B builds its index locally (free), Stack A registers the
    existing OpenAI index (a new one would be paid for on every gate run)."""
    load_or_build(S0["chunk_size"], S0["overlap"])
    if indexes.lookup(conn, stack, chunk_set_id) is not None:
        return
    if stack == "A":
        indexes.register_stack_a(conn, chunk_set_id, GATE_STACK_A_INDEXES[chunk_set_id])
    else:
        indexes.build(conn, "B", chunk_set_id)


def run(conn: sqlite3.Connection, stack: str) -> dict:
    """Run the gate on one stack and return its report; a run that fails raises, as pipeline.execute does."""
    gate = choices(stack)
    prepare(conn, stack, gate.chunk_set_id)
    run_id = pipeline.start_run(conn, gate, smoke_tests())
    pipeline.execute(conn, run_id, indexes.retriever(conn, runs.get_run(conn, run_id).meta))
    return evaluation.report(conn, run_id)


def passed(report: dict) -> bool:
    """A stack passes when it failed no gate (a report exists only for a finished run)."""
    return not report["failed_gates"]
