"""Stage 1 of the dataset (T29, T31): generate world.json in three calls, then compute derived facts."""

from pydantic import BaseModel

from rag_playground.datasets.world import ClientsPart, CorePart, RunbooksPart, World
from rag_playground.llm.openrouter import chat_structured
from rag_playground.settings import GENERATOR_MODEL

SYSTEM = """You design a realistic but entirely fictional world for evaluating a RAG system.
Questions with exact gold answers will be generated from it, so every fact must be consistent with every other fact.
The subject is a boutique Salesforce consulting firm of exactly 20 people.

Naming:
- Every company, client and person name is invented and must not be a real organisation or a famous person.
- Real Salesforce product names (Sales Cloud, Service Cloud, Data Cloud, Agentforce, MuleSoft, Tableau, Experience Cloud, Marketing Cloud, Revenue Cloud, Shield) are allowed.
- Ids use the formats emp-01, svc-01, cli-01, rb-01.

Values:
- Use specific, varied values: exact dates (YYYY-MM-DD), amounts in USD, counts, durations and percentages. Avoid round numbers where real data would not be round.
- Any percentage change must be arithmetically exact to one decimal place from the before and after values you state.
- Durations vary realistically around a service's typical duration (roughly -20% to +40%), not all by the same amount.

Free-text fields (milestones, notable_facts, outcome, metric) are the main risk:
- Each free-text fact describes only its own entity. Never compare it with, rank it against, or make claims about other entities.
- Never use these words in free text: first, second, third, only, most, least, largest, biggest, smallest, highest, lowest, fewest, total, record. Standard KPI names such as "first-contact resolution" are allowed.
- Never state counts or totals that span several entities (tickets across clients, projects completed by the firm, certified staff, employees).
- A project's metric must respect the limits of the service it uses (for example a ticket allowance per month).
- Milestones only record office openings (same year as the office), service launches (same year as the service launch_year) and partner-tier or policy changes. They contain no counts.

Structure:
- Make facts distinct enough to be asked about unambiguously: no two employees share a name, title and office.
- Include some entities that are similar on purpose (two clients in the same industry, two services with close prices), so comparative questions are meaningful."""

CORE_TASK = """Create the firm, its people and its services:
- company: founded between 2009 and 2014, 3 offices in different countries (headcount is computed later; put 0), 6-8 milestones, 4 policies (expenses, remote work, certification bonus, on-call) with 4-6 concrete rules each. Where two rules could both apply, state whether they combine. The certification bonus rules must name a tier for every kind of certification an employee holds (for example Associate, Specialist, Administrator, Consultant, Developer, Architect, Tableau and MuleSoft credentials), so the bonus for any held certification has exactly one answer.
- employees: exactly 20, spread across the offices, with a reporting line (one CEO with manager_id null), 0-4 Salesforce certifications each, and 2-4 notable facts each. Nobody starts before their office opened.
- services: exactly 10, each with a launch_year, a lead employee from the list above who was hired by that year, and 3-5 deliverables. Together the services must cover every product area that employee titles and skills refer to; each employee title refers only to a service area that exists."""

CLIENTS_TASK = """Here are the firm, employees and services already defined:
{core}

Create exactly 18 clients across at least 6 industries and 5 countries. Each client has:
- an account lead from the employees,
- 1-3 projects listing all work the firm has done for it; client_since_year is the year the earliest project started,
- for each project: a service whose summary matches the work described, a start date in or after that service's launch_year, a team of 2-4 employees all hired before the project starts, end date, outcome and one measurable metric,
- 2-4 notable facts about the client itself.
Use only the employee and service ids above."""

RUNBOOKS_TASK = """Here are the firm, employees and services already defined:
{core}

Create exactly 14 deployment runbooks the firm uses for Salesforce releases (for example sandbox refresh, metadata deployment with change sets or the Salesforce CLI, data migration, Agentforce agent rollout, permission set changes, rollback). Each has:
- an owner from the employees,
- a varied number of concrete steps between 5 and 12 (not the same count for every runbook), 2-5 rollback steps, and 1-3 known issues with specific error messages or limits,
- hands_on_minutes for the active work only, and monitoring_hours for any post-release monitoring window the steps mention (0 if none).
Use only the employee ids above."""


def ask[T: BaseModel](schema: type[T], task: str) -> tuple[T, float]:
    """One structured generation call; returns the part and its cost."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    part, result = chat_structured(GENERATOR_MODEL, messages, schema, max_tokens=32000)
    return part, result.cost_usd


def derive_facts(world: World) -> World:
    """Set facts that code computes instead of the LLM: office headcounts and project order."""
    for office in world.company.offices:
        office.headcount = sum(e.office_city == office.city for e in world.employees)
    for client in world.clients:
        client.projects.sort(key=lambda p: p.start_date)
    return world


def generate_world() -> tuple[World, float]:
    """Generate the full world and return it with the total cost in USD."""
    core, cost_core = ask(CorePart, CORE_TASK)
    core_json = core.model_dump_json(indent=1)
    clients, cost_clients = ask(ClientsPart, CLIENTS_TASK.format(core=core_json))
    runbooks, cost_runbooks = ask(RunbooksPart, RUNBOOKS_TASK.format(core=core_json))
    world = World(**core.model_dump(), clients=clients.clients, runbooks=runbooks.runbooks)
    return derive_facts(world), cost_core + cost_clients + cost_runbooks
