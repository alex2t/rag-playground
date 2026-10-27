"""The search result type shared by both stacks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Hit:
    """One retrieved chunk, in rank order. Scores are on each stack's own scale and are not comparable."""

    chunk_id: str
    source: str
    score: float
    text: str
