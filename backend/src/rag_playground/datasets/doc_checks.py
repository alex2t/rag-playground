"""Deterministic fidelity check (T32): numbers and dates in a document must match its source facts exactly."""

import re

DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


def tokens(text: str) -> set[str]:
    """Dates and numbers in a text, normalised: thousands separators removed."""
    dates = set(DATE.findall(text))
    rest = LIST_MARKER.sub("", DATE.sub(" ", text))
    return dates | {n.replace(",", "") for n in NUMBER.findall(rest)}


def fact_tokens(value) -> set[str]:
    """Dates and numbers anywhere in a facts structure."""
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, int | float):
        return {str(value)}
    if isinstance(value, str):
        return tokens(value)
    if isinstance(value, dict):
        return set().union(*(fact_tokens(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(fact_tokens(v) for v in value)) if value else set()
    raise TypeError(f"unexpected fact value: {value!r}")


def number_problems(markdown: str, facts: dict) -> list[str]:
    """Report numbers or dates added to the document and those from the facts that it omits.

    The year of a fact date may also appear on its own ("joined in 2016"), but is not required.
    """
    in_doc, required = tokens(markdown), fact_tokens(facts)
    allowed = required | {t[:4] for t in required if DATE.fullmatch(t)}
    return ([f"added: {t}" for t in sorted(in_doc - allowed)]
            + [f"missing: {t}" for t in sorted(required - in_doc)])
