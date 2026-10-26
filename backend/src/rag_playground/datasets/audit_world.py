"""Consistency audit of world.json by an independent model (T31)."""

from enum import StrEnum

from pydantic import BaseModel

from rag_playground.datasets.world import World
from rag_playground.llm.openrouter import chat_structured
from rag_playground.settings import AUDIT_MODEL

INSTRUCTIONS = """You audit a fictional world model that will become the knowledge base of a RAG evaluation.
Questions with gold answers will be generated from it, so every fact must be consistent.

Read the whole JSON and report every issue of these two kinds:
- contradiction: two statements (structured fields or free text) that cannot both be true. Check across entities: dates and timelines, counts and totals, ordinals and superlatives ("first", "second", "only", "most"), caps and limits (for example a service allowance versus a project metric), which service or product a project uses, and claims one entity makes about another.
- ambiguity: a statement that would give a reasonable question two defensible answers (for example a total in free text that the structured data contradicts or cannot support).

Do not report style issues, missing detail, or things that are merely unusual but possible.
For each issue give the ids involved, quote the exact conflicting text, and explain the conflict in one or two sentences.
Return an empty list only if you find no issue.

In this pass, focus only on: {focus}
Go through every entity for this focus, one by one."""

# One narrow pass per kind of check; a single broad pass missed half of the known issues (T31).
FOCUSES = [
    "timelines: every date and year in structured fields and free text (hires, office openings, "
    "practice and service launches, client start years, project dates, milestones) and every claim "
    "about what happened before or after something else.",
    "numbers: every count, total, cap, allowance, price, duration, percentage and calculation, in "
    "structured fields and free text; check arithmetic and that metrics respect the limits of the "
    "service a project uses.",
    "cross-references: every claim one entity makes about another (people, clients, services, "
    "products, offices, runbooks), every ordinal or superlative, and whether each project's service "
    "matches the work described.",
]


class IssueKind(StrEnum):
    CONTRADICTION = "contradiction"
    AMBIGUITY = "ambiguity"


class Issue(BaseModel):
    kind: IssueKind
    entity_ids: list[str]
    evidence: list[str]
    explanation: str


class AuditReport(BaseModel):
    issues: list[Issue]


def audit_pass(world_json: str, focus: str) -> tuple[AuditReport, float]:
    """One focused audit call; returns its issues and cost in USD."""
    messages = [
        {"role": "system", "content": INSTRUCTIONS.format(focus=focus)},
        {"role": "user", "content": world_json},
    ]
    report, result = chat_structured(AUDIT_MODEL, messages, AuditReport, max_tokens=64000)
    return report, result.cost_usd


def audit_world(world: World) -> tuple[AuditReport, float]:
    """Run every focused pass and return all issues found with the total cost in USD."""
    world_json = world.model_dump_json(indent=1)
    passes = [audit_pass(world_json, focus) for focus in FOCUSES]
    issues = [issue for report, _ in passes for issue in report.issues]
    return AuditReport(issues=issues), sum(cost for _, cost in passes)
