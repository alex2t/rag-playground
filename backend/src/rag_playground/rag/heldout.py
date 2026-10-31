"""Held-out confirmation (plan.md 3.3, T18): after the ladder, S0 and the stack's final configuration run on the 48
held-out questions. These are the numbers quoted as the result; they confirm the choice and never make one."""

import sqlite3

from rag_playground.datasets.schema import TestCase, load_tests
from rag_playground.rag import ladder_runs, ladder_step
from rag_playground.rag.ladder import Config, Progress
from rag_playground.scoring.selection import Candidate, paired_bootstrap

STEP = "held-out"


def tests() -> list[TestCase]:
    return [t for t in load_tests() if t.split == "heldout"]


def configurations(now: Progress) -> list[Config]:
    """S0 and the final configuration, or S0 alone if the ladder kept its settings. S7 is reported only, so the last
    decision keeps S6's configuration (T50)."""
    return list(dict.fromkeys([now.decisions[0].kept, now.decisions[-1].kept]))


def next_runs(conn: sqlite3.Connection, stack: str) -> list[Config]:
    """The confirmation runs still to do, refused if the ladder is not finished, if none is left, or if their estimate
    is over the budget. Runs are permanent and the oldest match wins, so a configuration is confirmed once."""
    now = ladder_step.progress(conn, stack)
    if now.next_step is not None:
        raise ValueError(f"Finish the ladder on Stack {stack} first; its next step is {now.next_step}")
    result = ladder_runs.heldout_finder(conn, stack)
    left = [config for config in configurations(now) if result(config) is None]
    if not left:
        raise ValueError(f"Stack {stack} is already confirmed on the held-out questions")
    ladder_step.check_budget(conn, left, tests())
    return left


def change(before: dict[str, float], after: dict[str, float]) -> dict:
    """A score's paired change (T09): real only if the whole interval is above 0."""
    low, high = paired_bootstrap(before, after)
    return {"low": low, "high": high, "real": low > 0}


def gain(s0: Candidate, final: Candidate) -> dict:
    """The final configuration against S0 on the same held-out questions."""
    return {"accuracy": change(s0.accuracy, final.accuracy), "mrr": change(s0.mrr, final.mrr)}
