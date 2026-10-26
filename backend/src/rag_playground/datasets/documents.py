"""Which facts go into which KB document (T32): each fact in exactly one document, ids resolved to names."""

import re
import unicodedata
from dataclasses import dataclass

from rag_playground.datasets.world import Employee, World


@dataclass(frozen=True)
class DocSpec:
    """One document to write: its KB path, kind, title and facts."""

    path: str
    kind: str
    title: str
    facts: dict


def slug(text: str) -> str:
    """File-name slug: accents removed, lower case ASCII letters, digits and hyphens."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def directory_path(city: str) -> str:
    return f"employees/{slug(city)}-staff-directory.md"


def service_path(name: str) -> str:
    return f"services/{slug(name)}.md"


def client_path(name: str) -> str:
    return f"clients/{slug(name)}.md"


def runbook_path(title: str) -> str:
    return f"deployment-runbooks/{slug(title)}.md"


def entity_paths(world: World) -> dict[str, str]:
    """Map every employee, service, client and runbook id to the document that holds its facts."""
    paths = {e.id: directory_path(e.office_city) for e in world.employees}
    paths |= {s.id: service_path(s.name) for s in world.services}
    paths |= {c.id: client_path(c.name) for c in world.clients}
    return paths | {r.id: runbook_path(r.title) for r in world.runbooks}


def company_specs(world: World) -> list[DocSpec]:
    c = world.company
    overview = {
        "business": "Salesforce consulting firm", "founded_year": c.founded_year, "founders": c.founders, "headquarters_city": c.headquarters_city,
        "mission": c.mission, "offices": [o.model_dump() for o in c.offices],
        "service_names": [s.name for s in world.services],
    }
    return [
        DocSpec("company/overview.md", "company overview", f"About {c.name}", overview),
        DocSpec("company/history.md", "company history", f"{c.name} history",
                {"milestones": [m.model_dump() for m in c.milestones]}),
        DocSpec("company/employee-handbook.md", "employee handbook (policies)", f"{c.name} employee handbook",
                {"policies": [p.model_dump() for p in c.policies]}),
    ]


def profile(e: Employee, people: dict[str, Employee]) -> dict:
    """One employee's facts, with the manager resolved to name and title."""
    manager = people.get(e.manager_id)
    facts = e.model_dump(exclude={"id", "manager_id", "office_city"})
    facts["manager"] = f"{manager.name} ({manager.title})" if manager else None
    return facts


def directory_specs(world: World) -> list[DocSpec]:
    """One staff directory per office; short profiles are grouped as real firms do."""
    people = {e.id: e for e in world.employees}
    return [
        DocSpec(directory_path(o.city), "office staff directory",
                f"{o.city} office staff directory",
                {"office": o.city,
                 "profiles": [profile(e, people) for e in world.employees if e.office_city == o.city]})
        for o in world.company.offices
    ]


def service_specs(world: World) -> list[DocSpec]:
    names = {e.id: e.name for e in world.employees}
    specs = []
    for s in world.services:
        facts = s.model_dump(exclude={"id", "lead_employee_id"})
        facts["lead"] = names[s.lead_employee_id]
        specs.append(DocSpec(service_path(s.name), "service description", s.name, facts))
    return specs


def client_specs(world: World) -> list[DocSpec]:
    people = {e.id: e.name for e in world.employees}
    services = {s.id: s.name for s in world.services}
    specs = []
    for c in world.clients:
        facts = c.model_dump(exclude={"id", "account_lead_id", "projects"})
        facts["account_lead"] = people[c.account_lead_id]
        facts["projects"] = [
            {**p.model_dump(exclude={"service_id", "team_employee_ids"}),
             "service": services[p.service_id], "team": [people[m] for m in p.team_employee_ids]}
            for p in c.projects
        ]
        specs.append(DocSpec(client_path(c.name), "client account summary", c.name, facts))
    return specs


def runbook_specs(world: World) -> list[DocSpec]:
    people = {e.id: e.name for e in world.employees}
    specs = []
    for r in world.runbooks:
        facts = r.model_dump(exclude={"id", "owner_id"})
        facts["owner"] = people[r.owner_id]
        specs.append(DocSpec(runbook_path(r.title), "deployment runbook", r.title, facts))
    return specs


def doc_specs(world: World) -> list[DocSpec]:
    """Every document of the KB, in a fixed order; each document's facts include the firm's name."""
    specs = (company_specs(world) + directory_specs(world) + service_specs(world)
             + client_specs(world) + runbook_specs(world))
    return [DocSpec(s.path, s.kind, s.title, {"firm": world.company.name, **s.facts}) for s in specs]
