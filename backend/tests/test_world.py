"""Exact tests for the world-model consistency check."""

from rag_playground.datasets.generate_world import derive_facts
from rag_playground.datasets.world import (
    Client, Company, Employee, Office, Project, Runbook, RunbookStep, Service, Stakeholder, World, world_problems,
)


def employee(id: str, name: str, manager_id: str | None = None, city: str = "Lyon") -> Employee:
    return Employee(id=id, name=name, title="Consultant", office_city=city, start_date="2020-01-06",
                    manager_id=manager_id, certifications=[], skills=[], bio="b", notable_facts=[])


def make_world(**overrides) -> World:
    parts = dict(
        company=Company(name="Acme", founded_year=2012, founders=["A"], headquarters_city="Lyon", mission="m",
                        offices=[Office(city="Lyon", country="France", opened_year=2012, headcount=2)],
                        milestones=[], policies=[]),
        employees=[employee("emp-01", "Ana Ruiz"), employee("emp-02", "Bo Chen", manager_id="emp-01")],
        services=[Service(id="svc-01", name="Audit", summary="s", salesforce_products=["Sales Cloud"],
                          pricing_model="fixed", price_usd=20000, typical_duration_weeks=4, launch_year=2015,
                          lead_employee_id="emp-01", deliverables=[], scope_includes=[], scope_excludes=[],
                          client_prerequisites=[])],
        clients=[Client(id="cli-01", name="Nordwind", industry="Retail", country="Germany", client_since_year=2021,
                        annual_contract_value_usd=150000, account_lead_id="emp-02", notable_facts=[],
                        stakeholders=[Stakeholder(name="Kai Berg", role="CIO")],
                        projects=[Project(name="P1", service_id="svc-01", start_date="2021-03-01",
                                          end_date="2021-05-01", team_employee_ids=["emp-01", "emp-02"], summary="s",
                                          objectives=[], outcome="o", metrics=["m"])])],
        runbooks=[Runbook(id="rb-01", title="t", salesforce_area="Data Cloud", owner_id="emp-02",
                          last_reviewed="2026-01-10", hands_on_minutes=30, monitoring_hours=2, purpose="p", prerequisites=[],
                          steps=[RunbookStep(action="a", verification="v")], rollback_steps=[], known_issues=[])],
    )
    return World(**{**parts, **overrides})


def test_consistent_world_has_no_problems():
    assert world_problems(make_world()) == []


def test_broken_references_are_all_reported():
    world = make_world()
    world.employees[1].manager_id = "emp-99"
    world.employees[1].office_city = "Paris"
    world.services[0].lead_employee_id = "emp-98"
    world.clients[0].account_lead_id = "emp-97"
    world.clients[0].projects[0].service_id = "svc-99"
    world.clients[0].projects[0].team_employee_ids = ["emp-01", "emp-96"]
    world.runbooks[0].owner_id = "emp-95"
    assert world_problems(world) == [
        "emp-02: unknown manager emp-99",
        "emp-02: unknown office Paris",
        "svc-01: unknown lead emp-98",
        "cli-01: unknown account lead emp-97",
        "cli-01/P1: unknown service svc-99",
        "cli-01/P1: unknown team member emp-96",
        "rb-01: unknown owner emp-95",
        "office Lyon: headcount 2 but 1 employees",
    ]


def test_timeline_contradictions_are_all_reported():
    world = make_world()
    world.employees[1].start_date = "2011-05-02"
    project = world.clients[0].projects[0]
    project.start_date, project.end_date = "2018-04-01", "2018-03-01"
    assert world_problems(world) == [
        "emp-02: starts 2011-05-02 before the Lyon office opened in 2012",
        "cli-01: client since 2021 but earliest project starts 2018-04-01",
        "cli-01/P1: ends 2018-03-01 before it starts 2018-04-01",
        "cli-01/P1: emp-01 hired 2020-01-06 after project start 2018-04-01",
    ]


def test_project_member_hired_after_project_start_is_reported():
    world = make_world()
    world.employees[1].start_date = "2021-04-12"
    assert world_problems(world) == ["cli-01/P1: emp-02 hired 2021-04-12 after project start 2021-03-01"]


def test_claim_words_in_claim_fields_are_reported():
    world = make_world()
    world.employees[0].notable_facts = ["Delivered the firm's first Data Cloud project.", "Speaks Portuguese."]
    world.clients[0].notable_facts = ["Most projects of any client."]
    world.clients[0].projects[0].metrics = ["Handled 3,912 tickets in total"]
    assert world_problems(world) == [
        "emp-01: claim word 'first' in: Delivered the firm's first Data Cloud project.",
        "cli-01: claim word 'Most' in: Most projects of any client.",
        "cli-01/P1: claim word 'total' in: Handled 3,912 tickets in total",
    ]


def test_claim_words_match_whole_words_only_and_skip_steps_and_policies():
    world = make_world()
    world.employees[0].notable_facts = ["Holds a firstclass honours degree.", "Mostly works on Sales Cloud."]
    world.runbooks[0].steps = [RunbookStep(action="First, back up the org.", verification="Backup listed.")]
    assert world_problems(world) == []


def test_kpi_names_are_allowed_but_other_claim_words_in_the_same_text_are_not():
    world = make_world()
    world.clients[0].projects[0].metrics = ["First-contact resolution up from 61% to 74%; first response time 4 hours"]
    world.clients[0].projects[0].outcome = "First call resolution rose to the highest level"
    assert world_problems(world) == [
        "cli-01/P1: claim word 'highest' in: First call resolution rose to the highest level",
    ]


def test_duplicate_ids_and_names_are_reported():
    staff = [employee("emp-01", "Ana Ruiz"), employee("emp-01", "Ana Ruiz"), employee("emp-02", "Bo Chen")]
    world = make_world(employees=staff)
    assert world_problems(world) == [
        "duplicate employee: emp-01",
        "duplicate name: Ana Ruiz",
        "office Lyon: headcount 2 but 3 employees",
    ]


def test_computed_facts_must_match_the_structured_data():
    world = make_world()
    world.company.offices[0].headcount = 40
    world.services[0].launch_year = 2022
    world.clients[0].projects.insert(0, world.clients[0].projects[0].model_copy(
        update={"name": "P0", "start_date": "2022-06-01", "end_date": "2022-09-01"}))
    assert world_problems(world) == [
        "office Lyon: headcount 40 but 2 employees",
        "cli-01: projects not in date order",
        "cli-01/P1: starts 2021-03-01 before svc-01 launched in 2022",
    ]


def test_derive_facts_sets_headcount_and_sorts_projects():
    world = make_world()
    world.company.offices[0].headcount = 40
    world.clients[0].projects.insert(0, world.clients[0].projects[0].model_copy(
        update={"name": "P2", "start_date": "2023-01-09", "end_date": "2023-04-03"}))
    derived = derive_facts(world)
    assert derived.company.offices[0].headcount == 2
    assert [p.name for p in derived.clients[0].projects] == ["P1", "P2"]
    assert world_problems(derived) == []


def test_ellipses_are_reported_in_any_text_field():
    world = make_world()
    world.runbooks[0].steps = [RunbookStep(action="Confirm accuracy of 90%... meeting the threshold of 90%.",
                                            verification="v")]
    world.company.mission = "Help clients… succeed"
    assert world_problems(world) == [
        "world.company.mission: ellipsis in: Help clients… succeed",
        "world.runbooks[0].steps[0].action: ellipsis in: Confirm accuracy of 90%... meeting the threshold of 90%.",
    ]


def test_client_since_year_must_equal_earliest_project_year():
    world = make_world()
    world.clients[0].client_since_year = 2019
    assert world_problems(world) == ["cli-01: client since 2019 but earliest project starts 2021-03-01"]


def test_stakeholder_names_must_not_repeat_employee_or_client_names():
    world = make_world()
    world.clients[0].stakeholders.append(Stakeholder(name="Ana Ruiz", role="COO"))
    assert world_problems(world) == ["duplicate name: Ana Ruiz"]


def test_claim_words_are_checked_in_the_new_free_text_fields():
    world = make_world()
    world.employees[0].bio = "The firm's most senior architect."
    world.services[0].scope_includes = ["Our only fixed-fee audit."]
    world.clients[0].projects[0].summary = "The largest rollout to date."
    world.runbooks[0].purpose = "Used for every first deployment."
    assert world_problems(world) == [
        "emp-01: claim word 'most' in: The firm's most senior architect.",
        "svc-01: claim word 'only' in: Our only fixed-fee audit.",
        "cli-01/P1: claim word 'largest' in: The largest rollout to date.",
        "rb-01: claim word 'first' in: Used for every first deployment.",
    ]


def test_record_is_a_claim_word_only_in_superlative_phrases():
    world = make_world()
    world.services[0].scope_includes = ["Sales process variants by record type", "Secure record sharing"]
    world.clients[0].projects[0].metrics = ["Bookings reached a record high of 1,204"]
    assert world_problems(world) == [
        "cli-01/P1: claim word 'record high' in: Bookings reached a record high of 1,204",
    ]


def test_reviewed_texts_are_allowed_exactly_and_nowhere_else():
    world = make_world()
    world.employees[0].notable_facts = ["Cycles to the office most days.", "Cycles to the office most weeks."]
    allowed = frozenset({"Cycles to the office most days."})
    assert world_problems(world, allowed) == [
        "emp-01: claim word 'most' in: Cycles to the office most weeks.",
    ]
