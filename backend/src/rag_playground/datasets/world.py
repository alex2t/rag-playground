"""Structured world model: the single source of truth for the synthetic KB (T29)."""

import re
from collections import Counter

from pydantic import BaseModel

# Words that make a free-text fact a claim about other entities (rank, uniqueness, totals) (T31).
CLAIM_WORDS = re.compile(
    r"\b(first|second|third|only|most|least|largest|biggest|smallest|highest|lowest|fewest|total"
    r"|record[- ](high|low|breaking|year|number))\b",
    re.IGNORECASE,
)
# Standard KPI names that contain a claim word but make no claim.
KPI_NAMES = re.compile(r"\bfirst[- ](contact|call) resolution\b|\bfirst response time\b", re.IGNORECASE)


class Office(BaseModel):
    city: str
    country: str
    opened_year: int
    headcount: int


class Milestone(BaseModel):
    year: int
    event: str


class Policy(BaseModel):
    title: str
    rules: list[str]


class Company(BaseModel):
    name: str
    founded_year: int
    founders: list[str]
    headquarters_city: str
    mission: str
    offices: list[Office]
    milestones: list[Milestone]
    policies: list[Policy]


class Employee(BaseModel):
    id: str
    name: str
    title: str
    office_city: str
    start_date: str
    manager_id: str | None
    certifications: list[str]
    skills: list[str]
    bio: str
    notable_facts: list[str]


class Service(BaseModel):
    id: str
    name: str
    summary: str
    salesforce_products: list[str]
    pricing_model: str
    price_usd: int
    typical_duration_weeks: int
    launch_year: int
    lead_employee_id: str
    deliverables: list[str]
    scope_includes: list[str]
    scope_excludes: list[str]
    client_prerequisites: list[str]


class Project(BaseModel):
    name: str
    service_id: str
    start_date: str
    end_date: str
    team_employee_ids: list[str]
    summary: str
    objectives: list[str]
    outcome: str
    metrics: list[str]


class Stakeholder(BaseModel):
    name: str
    role: str


class Client(BaseModel):
    id: str
    name: str
    industry: str
    country: str
    client_since_year: int
    annual_contract_value_usd: int
    account_lead_id: str
    stakeholders: list[Stakeholder]
    projects: list[Project]
    notable_facts: list[str]


class RunbookStep(BaseModel):
    action: str
    verification: str


class KnownIssue(BaseModel):
    symptom: str
    resolution: str


class Runbook(BaseModel):
    id: str
    title: str
    salesforce_area: str
    owner_id: str
    last_reviewed: str
    hands_on_minutes: int
    monitoring_hours: int
    purpose: str
    prerequisites: list[str]
    steps: list[RunbookStep]
    rollback_steps: list[str]
    known_issues: list[KnownIssue]


class CorePart(BaseModel):
    """First generation call: the firm, its people and its services."""

    company: Company
    employees: list[Employee]
    services: list[Service]


class ClientsPart(BaseModel):
    clients: list[Client]


class RunbooksPart(BaseModel):
    runbooks: list[Runbook]


class World(BaseModel):
    company: Company
    employees: list[Employee]
    services: list[Service]
    clients: list[Client]
    runbooks: list[Runbook]


def duplicates(values: list[str]) -> list[str]:
    return sorted(v for v, n in Counter(values).items() if n > 1)


def world_problems(world: World, allowed_claims: frozenset[str] = frozenset()) -> list[str]:
    """Return every broken reference, duplicate, timeline error, claim word or artifact; empty means consistent.

    `allowed_claims` holds exact texts a human reviewed and accepted despite a claim word.
    """
    employee_ids = {e.id for e in world.employees}
    service_ids = {s.id for s in world.services}
    cities = {o.city for o in world.company.offices}
    problems = []
    for kind, ids in [
        ("employee", [e.id for e in world.employees]),
        ("service", [s.id for s in world.services]),
        ("client", [c.id for c in world.clients]),
        ("runbook", [r.id for r in world.runbooks]),
        ("name", [e.name for e in world.employees] + [c.name for c in world.clients]
                  + [s.name for c in world.clients for s in c.stakeholders]),
    ]:
        problems += [f"duplicate {kind}: {d}" for d in duplicates(ids)]
    for e in world.employees:
        if e.manager_id is not None and e.manager_id not in employee_ids:
            problems.append(f"{e.id}: unknown manager {e.manager_id}")
        if e.office_city not in cities:
            problems.append(f"{e.id}: unknown office {e.office_city}")
    for s in world.services:
        if s.lead_employee_id not in employee_ids:
            problems.append(f"{s.id}: unknown lead {s.lead_employee_id}")
    for c in world.clients:
        if c.account_lead_id not in employee_ids:
            problems.append(f"{c.id}: unknown account lead {c.account_lead_id}")
        for p in c.projects:
            if p.service_id not in service_ids:
                problems.append(f"{c.id}/{p.name}: unknown service {p.service_id}")
            problems += [f"{c.id}/{p.name}: unknown team member {m}" for m in p.team_employee_ids if m not in employee_ids]
    for r in world.runbooks:
        if r.owner_id not in employee_ids:
            problems.append(f"{r.id}: unknown owner {r.owner_id}")
    return problems + date_problems(world) + claim_word_problems(world, allowed_claims) + artifact_problems(world)


def all_texts(value, where: str = "world") -> list[tuple[str, str]]:
    """Every string in the world, as (path, text)."""
    if isinstance(value, str):
        return [(where, value)]
    if isinstance(value, dict):
        return [t for k, v in value.items() for t in all_texts(v, f"{where}.{k}")]
    if isinstance(value, list):
        return [t for i, v in enumerate(value) for t in all_texts(v, f"{where}[{i}]")]
    return []


def artifact_problems(world: World) -> list[str]:
    """Flag ellipses, which mark truncated or self-corrected generator text."""
    return [f"{where}: ellipsis in: {text}" for where, text in all_texts(world.model_dump())
            if "..." in text or "…" in text]


def claim_texts(world: World) -> list[tuple[str, str]]:
    """Free-text fields where cross-entity claims can appear, as (location, text)."""
    texts = [(f"company milestone {m.year}", m.event) for m in world.company.milestones]
    texts += [(e.id, t) for e in world.employees for t in [e.bio, *e.notable_facts]]
    texts += [(s.id, t) for s in world.services for t in [s.summary, *s.scope_includes, *s.scope_excludes]]
    texts += [(c.id, f) for c in world.clients for f in c.notable_facts]
    for c in world.clients:
        texts += [(f"{c.id}/{p.name}", t) for p in c.projects
                  for t in [p.summary, *p.objectives, p.outcome, *p.metrics]]
    texts += [(r.id, r.purpose) for r in world.runbooks]
    return texts


def claim_word_problems(world: World, allowed: frozenset[str] = frozenset()) -> list[str]:
    """Flag ordinals, superlatives and totals in claim fields; they must be computed, not written by the LLM."""
    return [
        f"{where}: claim word '{match.group(0)}' in: {text}"
        for where, text in claim_texts(world)
        if text not in allowed and (match := CLAIM_WORDS.search(KPI_NAMES.sub("", text)))
    ]


def date_problems(world: World) -> list[str]:
    """Return timeline contradictions: hires before an office opened, projects out of order or staffed too early."""
    opened = {o.city: o.opened_year for o in world.company.offices}
    hired = {e.id: e.start_date for e in world.employees}
    problems = [
        f"{e.id}: starts {e.start_date} before the {e.office_city} office opened in {opened[e.office_city]}"
        for e in world.employees
        if e.office_city in opened and int(e.start_date[:4]) < opened[e.office_city]
    ]
    launched = {s.id: s.launch_year for s in world.services}
    for o in world.company.offices:
        staff = sum(e.office_city == o.city for e in world.employees)
        if o.headcount != staff:
            problems.append(f"office {o.city}: headcount {o.headcount} but {staff} employees")
    for c in world.clients:
        if c.projects and c.client_since_year != min(int(p.start_date[:4]) for p in c.projects):
            problems.append(f"{c.id}: client since {c.client_since_year} but earliest project starts "
                            f"{min(p.start_date for p in c.projects)}")
        if [p.start_date for p in c.projects] != sorted(p.start_date for p in c.projects):
            problems.append(f"{c.id}: projects not in date order")
        for p in c.projects:
            if p.service_id in launched and int(p.start_date[:4]) < launched[p.service_id]:
                problems.append(f"{c.id}/{p.name}: starts {p.start_date} before {p.service_id} launched "
                                f"in {launched[p.service_id]}")
            if p.end_date <= p.start_date:
                problems.append(f"{c.id}/{p.name}: ends {p.end_date} before it starts {p.start_date}")
            problems += [
                f"{c.id}/{p.name}: {m} hired {hired[m]} after project start {p.start_date}"
                for m in p.team_employee_ids
                if m in hired and hired[m] > p.start_date
            ]
    return problems
