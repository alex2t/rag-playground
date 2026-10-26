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

Free-text fields (milestones, bio, notable_facts, service summary and scope, project summary, objectives, outcome, metrics, runbook purpose) are the main risk:
- Each free-text fact describes only its own entity. Never compare it with, rank it against, or make claims about other entities.
- Never use these words in free text: first, second, third, only, most, least, largest, biggest, smallest, highest, lowest, fewest, total, record. Standard KPI names such as "first-contact resolution" are allowed.
- Never state counts or totals that span several entities (tickets across clients, projects completed by the firm, certified staff, employees).
- A project's metric must respect the limits of the service it uses (for example a ticket allowance per month).
- Milestones only record office openings (same year as the office), service launches (same year as the service launch_year) and partner-tier or policy changes. They contain no counts.

Structure:
- Make facts distinct enough to be asked about unambiguously: no two employees share a name, title and office.
- Include some entities that are similar on purpose (two clients in the same industry, two services with close prices), so comparative questions are meaningful."""

CORE_TASK = """Create the firm, its people and its services:
- company: founded between 2009 and 2014, 3 offices in different countries (headcount is computed later; put 0), 6-8 milestones, 6 policies (expenses, travel, remote work, certification bonus, on-call, data security) with 5-8 concrete rules each. Where two rules could both apply, state whether they combine. The certification bonus rules must name a tier for every kind of certification an employee holds (for example Associate, Specialist, Administrator, Consultant, Developer, Architect, Tableau and MuleSoft credentials), so the bonus for any held certification has exactly one answer.
- employees: exactly 20, spread across the offices, with a reporting line (one CEO with manager_id null), 0-4 Salesforce certifications each, a bio of 2-3 sentences about their own background and expertise, and 3-5 notable facts each. Nobody starts before their office opened.
- services: exactly 10, each with a launch_year, a lead employee from the list above who was hired by that year, 4-7 deliverables, 4-6 scope_includes items, 2-4 scope_excludes items and 2-4 client_prerequisites. Together the services must cover every product area that employee titles and skills refer to; each employee title refers only to a service area that exists."""

CLIENTS_TASK = """Here are the firm, employees and services already defined:
{core}

Create exactly 9 clients with ids {first_id} to {last_id}.{avoid}
Across all 18 clients the firm has, there are at least 6 industries and 5 countries, so vary them. Each client has:
- an account lead from the employees,
- 2-3 client-side stakeholders (invented names, different from every employee name) with their role at the client,
- 3-5 projects listing all work the firm has done for it; client_since_year is the year the earliest project started,
- for each project: a service whose summary matches the work described, a start date in or after that service's launch_year, a team of 2-4 employees all hired before the project starts, an end date, a summary of 2-3 sentences, 2-3 objectives, an outcome and 2-3 measurable metrics,
- 3-5 notable facts about the client itself.
Use only the employee and service ids above."""

RUNBOOKS_TASK = """Here are the firm, employees and services already defined:
{core}

Create exactly 14 deployment runbooks the firm uses for Salesforce releases (for example sandbox refresh, metadata deployment with change sets or the Salesforce CLI, data migration, Agentforce agent rollout, permission set changes, rollback). Each has:
- an owner from the employees and a purpose of 2-3 sentences,
- 3-6 prerequisites,
- a varied number of concrete steps between 6 and 14 (not the same count for every runbook); each step has an action and a verification that confirms it worked,
- 3-6 rollback steps, and 2-4 known issues, each with a symptom (a specific error message or limit) and its resolution,
- hands_on_minutes for the active work only, and monitoring_hours for any post-release monitoring window the steps mention (0 if none).
Use only the employee ids above."""


def ask[T: BaseModel](schema: type[T], task: str) -> tuple[T, float]:
    """One structured generation call; returns the part and its cost."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    # Sonnet reasons before answering; a 9-client batch used 26k reasoning tokens, so 32k was too small.
    part, result = chat_structured(GENERATOR_MODEL, messages, schema, max_tokens=64000)
    return part, result.cost_usd


def derive_facts(world: World) -> World:
    """Set facts that code computes instead of the LLM: office headcounts and project order."""
    for office in world.company.offices:
        office.headcount = sum(e.office_city == office.city for e in world.employees)
    for client in world.clients:
        client.projects.sort(key=lambda p: p.start_date)
    return world


def generate_clients(core_json: str) -> tuple[list, float]:
    """Generate 18 clients in two calls of 9, so each response stays well within the output limit."""
    first, cost_first = ask(ClientsPart, CLIENTS_TASK.format(core=core_json, first_id="cli-01", last_id="cli-09", avoid=""))
    taken = ", ".join(c.name for c in first.clients)
    avoid = f" Do not reuse these client names or their stakeholder names: {taken}; " + ", ".join(
        s.name for c in first.clients for s in c.stakeholders) + "."
    second, cost_second = ask(ClientsPart, CLIENTS_TASK.format(core=core_json, first_id="cli-10", last_id="cli-18", avoid=avoid))
    return first.clients + second.clients, cost_first + cost_second


def generate_world() -> tuple[World, float]:
    """Generate the full world and return it with the total cost in USD."""
    core, cost_core = ask(CorePart, CORE_TASK)
    core_json = core.model_dump_json(indent=1)
    clients, cost_clients = generate_clients(core_json)
    runbooks, cost_runbooks = ask(RunbooksPart, RUNBOOKS_TASK.format(core=core_json))
    world = World(**core.model_dump(), clients=clients, runbooks=runbooks.runbooks)
    return derive_facts(world), cost_core + cost_clients + cost_runbooks
