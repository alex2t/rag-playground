"""What the Story page shows for one stack (T50): the finished steps with their scores, the next step and its estimate."""

import sqlite3
from dataclasses import asdict

from rag_playground import jobs
from rag_playground.datasets.schema import load_tests
from rag_playground.rag import heldout, ladder_runs, ladder_step, pipeline, runs
from rag_playground.rag.ladder import Decision, Progress
from rag_playground.scoring.selection import Candidate, failed_gates, score_interval


def option(candidate: Candidate, config, kept: bool) -> dict:
    """One configuration a step tried, with the scores of its stored run and their 95% intervals (T52)."""
    return {"config": asdict(config), "kept": kept, "run_id": candidate.run_id, "accuracy": candidate.mean_accuracy,
            "mrr": candidate.scores["mrr"], "accuracy_ci": score_interval(candidate.accuracy),
            "mrr_ci": score_interval(candidate.mrr), "cost_per_question": candidate.cost_per_question,
            "failed_gates": failed_gates(candidate.scores)}


def answers(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    """A dev run's questions with their answers, verdicts and chunks, lowest accuracy first. Held-out runs are refused:
    reading their answers could steer later choices, and those questions are never used to tune (T18). KeyError if the
    run does not exist."""
    if runs.get_run(conn, run_id).meta.split != "dev":
        raise ValueError("Held-out answers are not shown: those questions stay out of tuning")
    tests = {test.id: test for test in load_tests()}
    return [{"test_id": result.test_id, "category": tests[result.test_id].category,
             "question": tests[result.test_id].question, "reference_answer": tests[result.test_id].reference_answer,
             "answer": result.answer, **asdict(result.judgement),
             "chunks": [{"source": hit.source, "text": hit.text} for hit in result.hits]}
            for result in sorted(runs.get_results(conn, run_id), key=lambda r: r.judgement.accuracy)]


def finished_step(decision: Decision, before: Decision | None, result) -> dict:
    """One step. `change` is its kept configuration against the step before's, the paired test of T09 on the same
    questions (T52); None at S0."""
    return {"step": decision.step, "kept": asdict(decision.kept),
            "change": heldout.gain(result(before.kept), result(decision.kept)) if before else None,
            "tried": [option(result(c), c, c == decision.kept) for c in decision.tried]}


def confirmation(conn: sqlite3.Connection, stack: str, now: Progress) -> dict | None:
    """The held-out panel, None until the ladder is finished. `gain` is the final configuration against S0, the number
    quoted as the result; it exists once both runs do, and not when the ladder kept S0's settings."""
    if now.next_step is not None:
        return None
    result = ladder_runs.heldout_finder(conn, stack)
    configs = heldout.configurations(now)
    found = [(config, result(config)) for config in configs]
    left = [config for config, run in found if run is None]
    done = [run for _, run in found if run]
    return {"runs": [option(run, config, config == configs[-1]) for config, run in found if run],
            "missing": [asdict(config) for config in left],
            "estimate_usd": ladder_step.step_cost(conn, stack, left, heldout.tests()),
            "gain": heldout.gain(*done) if len(done) == 2 else None}


def state(conn: sqlite3.Connection, stack: str, proposed: tuple[str, ...] | None = None) -> dict:
    """A stack's ladder. `enrichment_usd` is the part of `estimate_usd` that pays for S4's enrichment, shown before the
    user confirms it (T49). At S6 nothing is missing until prompts are `proposed` or saved: `needs_prompts`.
    `saved_prompts` is the final S6 choice, None until made. `last_error` survives a page refresh."""
    result = ladder_runs.finder(conn, stack)
    now = ladder_step.replay(conn, stack, result, proposed)
    steps = [finished_step(d, before, result) for d, before in zip(now.decisions, [None, *now.decisions])]
    return {"stack": stack, "steps": steps, "next_step": now.next_step,
            "needs_prompts": now.next_step == "S6" and not now.missing, "missing": [asdict(c) for c in now.missing],
            "estimate_usd": ladder_step.step_cost(conn, stack, now.missing),
            "enrichment_usd": sum(ladder_step.enrichment_cost(c) for c in now.missing),
            "budget_left_usd": pipeline.remaining(conn), "job_id": jobs.active_step(conn, stack),
            "last_error": jobs.last_failure(conn, stack), "saved_prompts": ladder_step.chosen_prompts(conn, stack),
            "heldout": confirmation(conn, stack, now)}
