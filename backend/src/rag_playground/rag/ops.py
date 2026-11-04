"""What the Ops page shows (D14, D30): spend against the budget, how often background jobs fail, and answer times.
Read from stored jobs, runs, results and spend; request logs come with Step 12."""

import sqlite3
from statistics import quantiles

from rag_playground.jobs import INTERRUPTED
from rag_playground.rag import pipeline, spend
from rag_playground.settings import OPS_WINDOW_DAYS, settings

SINCE = f"datetime('now', '-{OPS_WINDOW_DAYS} days')"


def budget(conn: sqlite3.Connection) -> dict:
    """All spend so far against BUDGET_USD, as the budget guard counts it, split into runs and calls outside runs (Ask,
    enrichment)."""
    outside = conn.execute("SELECT coalesce(sum(cost_usd), 0) FROM spend WHERE run_id IS NULL").fetchone()[0]
    total = spend.total(conn)
    return {"budget_usd": settings.budget_usd, "spent_usd": total, "left_usd": pipeline.remaining(conn),
            "in_runs_usd": total - outside, "outside_runs_usd": outside}


def cause(error: str) -> str:
    """Why a job failed: the budget cap and an app restart stop work on purpose; anything else is a fault."""
    if error.startswith("BudgetExceeded:"):
        return "budget"
    return "restart" if error == INTERRUPTED else "fault"


def failures(conn: sqlite3.Connection) -> dict:
    """Jobs finished in the window, the faults among them, and every failure newest first with its cause. The error
    rate is faults over finished jobs; budget stops and restarts are counted apart."""
    rows = conn.execute(f"SELECT id, created_at, kind, stack, status, error FROM jobs "
                        f"WHERE finished_at >= {SINCE} OR finished_at IS NULL ORDER BY id DESC").fetchall()
    finished = [row for row in rows if row["status"] in ("done", "failed")]
    failed = [dict(row) | {"cause": cause(row["error"])} for row in finished if row["status"] == "failed"]
    faults = sum(job["cause"] == "fault" for job in failed)
    return {"finished": len(finished), "active": len(rows) - len(finished), "faults": faults,
            "budget_stops": sum(job["cause"] == "budget" for job in failed),
            "restarts": sum(job["cause"] == "restart" for job in failed),
            "error_rate": faults / len(finished) if finished else None, "failed": failed}


def percentiles(seconds: list[float]) -> tuple[float, float]:
    """p50 and p95, interpolated between the stored times (the "inclusive" method, numpy's default)."""
    if len(seconds) == 1:
        return seconds[0], seconds[0]
    cuts = quantiles(seconds, n=100, method="inclusive")
    return cuts[49], cuts[94]


def latency(conn: sqlite3.Connection) -> list[dict]:
    """Per stack, p50 and p95 of the time to search and answer one question, over questions of runs started in the
    window. A stack with no such question is left out."""
    rows = conn.execute(f"SELECT stack, latency_s FROM results JOIN runs ON runs.id = run_id WHERE runs.created_at >= {SINCE}").fetchall()
    found = []
    for stack in ("A", "B"):
        seconds = sorted(row["latency_s"] for row in rows if row["stack"] == stack)
        if seconds:
            p50, p95 = percentiles(seconds)
            found.append({"stack": stack, "questions": len(seconds), "p50_s": p50, "p95_s": p95})
    return found


def summary(conn: sqlite3.Connection) -> dict:
    return {"window_days": OPS_WINDOW_DAYS, "budget": budget(conn), "jobs": failures(conn), "latency": latency(conn)}
