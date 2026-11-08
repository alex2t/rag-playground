"""The evaluation gate (D36): the 20 smoke questions at S0 on both stacks; exit code 0 if both pass every T08 gate,
1 otherwise. Meant for an empty database (GitHub's runner), with Qdrant reachable at QDRANT_URL.

Paid: about $0.08 a run (answers and judge on OpenRouter, Stack A's searches on OpenAI), capped by BUDGET_USD.
Usage: uv run python scripts/eval_gate.py
"""

import sys

from rag_playground import store
from rag_playground.rag import gate, pipeline, prompts, spend
from rag_playground.settings import GATES, settings

STACKS = ("A", "B")


def lines(report: dict) -> list[str]:
    """One stack's verdict, then each gate's score against its minimum."""
    verdict = "PASS" if gate.passed(report) else f"FAIL ({', '.join(report['failed_gates'])})"
    head = f"Stack {report['stack']}: run {report['id']}, {report['questions']} questions: {verdict}"
    scores = report["scores"]
    return [head] + [f"  {name}: {scores[name]:.3f} (minimum {minimum})" for name, minimum in GATES.items()] + [
        f"  accuracy: {scores['accuracy']:.3f}"]


def main() -> int:
    conn = store.connect()
    prompts.ensure_default(conn)
    print(f"Evaluation gate, version {settings.app_version}; BUDGET_USD ${settings.budget_usd:.2f}, "
          f"${pipeline.remaining(conn):.4f} left", flush=True)
    reports = [gate.run(conn, stack) for stack in STACKS]
    for report in reports:
        print("\n".join(lines(report)))
    print(f"Spent ${spend.total(conn):.4f}")
    return 0 if all(gate.passed(report) for report in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
