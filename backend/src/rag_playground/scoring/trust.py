"""Refusal rates from the judge's `refused` flag (T19)."""

from statistics import mean

from rag_playground.datasets.schema import Category, TestCase


def correct_refusal_rate(tests: list[TestCase], refused: dict[str, bool]) -> float:
    """Unanswerable questions that were refused / unanswerable questions. Higher is better."""
    return mean(refused[t.id] for t in tests if t.category == Category.UNANSWERABLE)


def false_refusal_rate(tests: list[TestCase], refused: dict[str, bool]) -> float:
    """Answerable questions that were refused / answerable questions. Lower is better."""
    return mean(refused[t.id] for t in tests if t.category != Category.UNANSWERABLE)
