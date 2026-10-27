"""Test candidates, document pairs for two-document questions, and code checks on tests (T34)."""

import random
import re
from itertools import combinations

from pydantic import BaseModel

from rag_playground.datasets.documents import entity_paths
from rag_playground.datasets.schema import Category
from rag_playground.datasets.splits import SEED
from rag_playground.datasets.world import Client, World

NOT_IN_KB = "Not in the knowledge base."
HANDBOOK = "company/employee-handbook.md"
TWO_DOC = {Category.MULTI_DOC, Category.COMPARATIVE}
INTERVAL = re.compile(r"\bhow (many|long)\b", re.IGNORECASE)
YEAR = re.compile(r"^\d{4}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
MONTHS_AND_DAYS = re.compile(r"\d+ months? and \d+ days?")


class Candidate(BaseModel):
    """A generated question before verification and selection."""

    question: str
    reference_answer: str
    category: Category
    source_docs: list[str]
    keywords: list[str]


class CandidateBatch(BaseModel):
    candidates: list[Candidate]


def unique_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop repeated pairs (in either order), keeping the first occurrence."""
    seen, kept = set(), []
    for a, b in pairs:
        if frozenset((a, b)) not in seen:
            seen.add(frozenset((a, b)))
            kept.append((a, b))
    return kept


def multi_doc_pairs(world: World, seed: int = SEED) -> list[tuple[str, str]]:
    """Document pairs linked by a relation: client, service and runbook with their lead's directory; client with
    the services of 2 random projects and with its project team's directories; the handbook with each directory."""
    path = entity_paths(world)
    rng = random.Random(seed)
    pairs = [(path[c.id], path[c.account_lead_id]) for c in world.clients]
    pairs += [(path[s.id], path[s.lead_employee_id]) for s in world.services]
    pairs += [(path[r.id], path[r.owner_id]) for r in world.runbooks]
    for c in world.clients:
        pairs += [(path[c.id], path[p.service_id]) for p in rng.sample(c.projects, min(2, len(c.projects)))]
    for c in world.clients:
        pairs += [(path[c.id], path[e]) for e in sorted({e for p in c.projects for e in p.team_employee_ids})]
    pairs += [(HANDBOOK, d) for d in sorted({path[e.id] for e in world.employees})]
    return unique_pairs(pairs)


def client_pairs(clients: list[Client], n: int, rng: random.Random) -> list[tuple[Client, Client]]:
    """Same-industry pairs first, then a ring over shuffled clients, so every client appears about equally."""
    same = [(a, b) for a, b in combinations(clients, 2) if a.industry == b.industry]
    order = rng.sample(clients, len(clients))
    ring = [(order[i], order[(i + k) % len(order)]) for k in range(1, len(order) // 2 + 1) for i in range(len(order))]
    by_id = {c.id: c for c in clients}
    ids = unique_pairs([(a.id, b.id) for a, b in same + ring])[:n]
    return [(by_id[a], by_id[b]) for a, b in ids]


def comparative_pairs(world: World, seed: int = SEED) -> list[tuple[str, str]]:
    """Pairs of comparable entities: 30 client pairs, 15 service pairs and 15 runbook pairs."""
    path = entity_paths(world)
    rng = random.Random(seed)
    picked = client_pairs(world.clients, 30, rng)
    picked += rng.sample(list(combinations(world.services, 2)), 15)
    picked += rng.sample(list(combinations(world.runbooks, 2)), 15)
    return [(path[a.id], path[b.id]) for a, b in picked]


def unique_keyword_problems(docs: list[str], keywords: list[str], kb: dict[str, str]) -> list[str]:
    """Each source document of a two-document test needs a keyword that the other source documents lack."""
    problems = []
    for d in docs:
        others = [kb[o].lower() for o in docs if o != d]
        if not any(k.lower() in kb[d].lower() and all(k.lower() not in o for o in others) for k in keywords):
            problems.append(f"no keyword unique to {d}")
    return problems


def interval_problems(c: Candidate) -> list[str]:
    """An interval between a bare year ("Client since: 2015") and a full date has no single correct answer,
    unless the question states that it counts calendar years."""
    years = [k for k in c.keywords if YEAR.match(k)]
    dates = [k for k in c.keywords if DATE.match(k)]
    calendar = "calendar year" in c.question.lower()
    if INTERVAL.search(c.question) and not calendar and years and dates:
        return [f"interval mixes a bare year and a full date: {', '.join(years + dates)}"]
    return []


def span_problems(c: Candidate) -> list[str]:
    """A span in months and days is ambiguous when the end's day of the month is before the start's:
    2020-01-13 to 2024-05-06 is 23 or 24 extra days depending on whether whole months or days are counted first."""
    dates = sorted(ISO_DATE.findall(c.reference_answer))
    if MONTHS_AND_DAYS.search(c.reference_answer) and len(dates) == 2 and dates[1][8:] < dates[0][8:]:
        return [f"months-and-days answer depends on the counting convention: {dates[0]} to {dates[1]}"]
    return []


def answerable_problems(c: Candidate, kb: dict[str, str]) -> list[str]:
    """Checks on an answerable candidate, using only its source docs that exist."""
    docs = [d for d in c.source_docs if d in kb]
    problems = []
    if c.category in TWO_DOC:
        if len(set(c.source_docs)) < 2:
            problems.append(f"{c.category} needs at least 2 source docs")
        else:
            problems += unique_keyword_problems(docs, c.keywords, kb)
    gold = "\n".join(kb[d] for d in docs).lower()
    problems += [f"keyword not in gold docs: {k}" for k in c.keywords if k.lower() not in gold]
    problems += [f"keyword not in reference answer: {k}" for k in c.keywords
                 if k.lower() not in c.reference_answer.lower()]
    return problems + interval_problems(c) + span_problems(c)


def unanswerable_problems(c: Candidate, kb: dict[str, str]) -> list[str]:
    problems = []
    if c.source_docs or c.reference_answer != NOT_IN_KB:
        problems.append("unanswerable must have no source docs and the fixed reference answer")
    corpus = "\n".join(kb.values()).lower()
    return problems + [f"unanswerable keyword in KB: {k}" for k in c.keywords if k.lower() in corpus]


def candidate_problems(c: Candidate, kb: dict[str, str]) -> list[str]:
    """Code checks on one candidate against the KB texts {path: markdown}."""
    problems = [f"unknown source doc {d}" for d in c.source_docs if d not in kb]
    if c.category == Category.UNANSWERABLE:
        problems += unanswerable_problems(c, kb)
    else:
        problems += answerable_problems(c, kb)
    if not c.keywords:
        problems.append("no keywords")
    return problems
