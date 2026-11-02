"""One-setting sweeps (T15, T58): each value of one setting on the 192 dev questions, the other settings at the base
configuration. Exploratory: dev questions only, no winner picked; the ladder makes the decisions."""

import sqlite3

from rag_playground.chunking.chunk_sets import chunk_settings
from rag_playground.datasets.schema import TestCase, load_tests
from rag_playground.rag import builds, heldout, ladder_runs, pipeline, prompts
from rag_playground.rag.compare import verdict
from rag_playground.scoring.selection import Candidate, failed_gates, score_interval
from rag_playground.stacks import indexes
from rag_playground.sweep_requests import SweepRequest


def dev_tests() -> list[TestCase]:
    return [test for test in load_tests() if test.split == "dev"]


def change(base: Candidate, other: Candidate) -> dict:
    """The paired change of accuracy and MRR against the base value (T09), read both ways."""
    return {name: found | {"verdict": verdict(found)} for name, found in heldout.gain(base, other).items()}


def scored(candidate: Candidate, base: Candidate | None, is_base: bool) -> dict:
    """A value's stored run with its 95% intervals (T52), and its change against the base value when both have run."""
    return {"run_id": candidate.run_id, "accuracy": candidate.mean_accuracy, "accuracy_ci": score_interval(candidate.accuracy),
            "mrr": candidate.scores["mrr"], "mrr_ci": score_interval(candidate.mrr),
            "cost_per_question": candidate.cost_per_question, "failed_gates": failed_gates(candidate.scores),
            "change": None if is_base or base is None else change(base, candidate)}


def enrichment_cost(missing: list[pipeline.Choices]) -> float:
    """Enrichment still to pay for the missing values, once per chunk set: both stacks and runs share it (T47)."""
    sets = {(s["chunking_method"], s["chunk_size"], s["overlap"]) for s in map(chunk_settings, (c.chunk_set_id for c in missing))}
    return sum(builds.enrichment_cost(*chunk_set) for chunk_set in sets)


def plan(conn: sqlite3.Connection, request: SweepRequest) -> dict:
    """Each value with its stored run and scores, or what running it would cost; the total for the values still to run.
    A value with a full dev run of the same settings reuses it (oldest match), so nothing is paid twice. KeyError if
    the prompt version does not exist."""
    return assess(conn, request)[0]


def assess(conn: sqlite3.Connection, request: SweepRequest) -> tuple[dict, list[pipeline.Choices]]:
    """The plan, and the settings of the values still to run, in the sweep's order."""
    for _, config in request.items():
        prompts.get(conn, config.prompt_name)
    found = ladder_runs.stored_runs(conn, "dev")
    base_key = ladder_runs.key_of(request.base.choices())
    base = found(request.base.choices())
    tests = dev_tests()
    items, missing = [], []
    for value, config in request.items():
        choices = config.choices()
        candidate = found(choices)
        is_base = ladder_runs.key_of(choices) == base_key
        if candidate is None:
            missing.append(choices)
        items.append({"value": value, "base": is_base, "chunk_set_id": choices.chunk_set_id,
                      "built": indexes.lookup(conn, choices.stack, choices.chunk_set_id) is not None,
                      "run": candidate and scored(candidate, base, is_base),
                      "estimate_usd": None if candidate else builds.run_cost(conn, choices, tests)})
    runs_usd = sum(item["estimate_usd"] or 0.0 for item in items)
    return {"stack": request.base.stack, "variable": request.variable, "items": items, "runs_to_do": len(missing),
            "estimate_usd": runs_usd + enrichment_cost(missing), "budget_left_usd": pipeline.remaining(conn)}, missing
