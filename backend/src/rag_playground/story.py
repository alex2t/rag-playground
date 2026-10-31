"""What the Story page shows for one stack (T50): the finished steps with their scores, the next step and its estimate."""

import sqlite3
from dataclasses import asdict

from rag_playground import jobs
from rag_playground.rag import ladder_runs, ladder_step, pipeline
from rag_playground.rag.ladder import Decision
from rag_playground.scoring.selection import Candidate, failed_gates


def option(candidate: Candidate, config, kept: bool) -> dict:
    """One configuration a step tried, with the scores of its stored run."""
    return {"config": asdict(config), "kept": kept, "run_id": candidate.run_id, "accuracy": candidate.mean_accuracy,
            "mrr": candidate.scores["mrr"], "cost_per_question": candidate.cost_per_question,
            "failed_gates": failed_gates(candidate.scores)}


def finished_step(decision: Decision, result) -> dict:
    return {"step": decision.step, "kept": asdict(decision.kept),
            "tried": [option(result(c), c, c == decision.kept) for c in decision.tried]}


def state(conn: sqlite3.Connection, stack: str, proposed: tuple[str, ...] | None = None) -> dict:
    """A stack's ladder. `enrichment_usd` is the part of `estimate_usd` that pays for S4's enrichment, shown before the
    user confirms it (T49). At S6 nothing is missing until prompts are `proposed` or saved: `needs_prompts`."""
    result = ladder_runs.finder(conn, stack)
    now = ladder_step.replay(conn, stack, result, proposed)
    return {"stack": stack, "steps": [finished_step(d, result) for d in now.decisions], "next_step": now.next_step,
            "needs_prompts": now.next_step == "S6" and not now.missing, "missing": [asdict(c) for c in now.missing],
            "estimate_usd": ladder_step.step_cost(conn, now.missing),
            "enrichment_usd": sum(ladder_step.enrichment_cost(c) for c in now.missing),
            "budget_left_usd": pipeline.remaining(conn), "job_id": jobs.active_step(conn, stack)}
