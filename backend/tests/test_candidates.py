"""Exact tests for the code checks on test candidates and the document pairs (T34)."""

from collections import Counter

from rag_playground.datasets.candidates import (
    NOT_IN_KB, Candidate, candidate_problems, comparative_pairs, multi_doc_pairs,
)
from rag_playground.datasets.documents import entity_paths
from rag_playground.datasets.schema import WORLD_PATH
from rag_playground.datasets.world import World

KB = {
    "clients/nordwind.md": "# Nordwind\nAnnual contract value: USD 150,000. Account lead: Ana Ruiz.",
    "employees/lyon-staff-directory.md": "# Lyon\n## Ana Ruiz\nCertifications: Salesforce Certified Administrator",
}
TWO_DOCS = ["clients/nordwind.md", "employees/lyon-staff-directory.md"]
WORLD = World.model_validate_json(WORLD_PATH.read_text(encoding="utf-8"))


def candidate(**overrides) -> Candidate:
    base = dict(question="What is Nordwind's annual contract value?", reference_answer="USD 150,000",
                category="numerical", source_docs=["clients/nordwind.md"], keywords=["150,000"])
    return Candidate(**{**base, **overrides})


def test_valid_single_doc_candidate_has_no_problems():
    assert candidate_problems(candidate(), KB) == []


def test_unknown_source_doc_and_keyword_outside_gold_docs_are_reported():
    c = candidate(source_docs=["clients/nordwind.md", "clients/missing.md"], keywords=["150,000", "Administrator"])
    assert candidate_problems(c, KB) == [
        "unknown source doc clients/missing.md",
        "keyword not in gold docs: Administrator",
        "keyword not in reference answer: Administrator",
    ]


def test_keywords_match_case_insensitively():
    assert candidate_problems(candidate(keywords=["usd 150,000"]), KB) == []


def test_keyword_missing_from_the_reference_answer_is_reported():
    assert candidate_problems(candidate(keywords=["150,000", "Account lead"]), KB) == [
        "keyword not in reference answer: Account lead",
    ]


def test_two_doc_categories_need_two_distinct_source_docs():
    c = candidate(category="multi_doc", source_docs=["clients/nordwind.md", "clients/nordwind.md"])
    assert candidate_problems(c, KB) == ["multi_doc needs at least 2 source docs"]
    ok = candidate(category="multi_doc", keywords=["150,000", "Administrator"], source_docs=TWO_DOCS,
                   reference_answer="USD 150,000; its lead holds Salesforce Certified Administrator")
    assert candidate_problems(ok, KB) == []


def test_each_source_doc_of_a_two_doc_test_needs_a_keyword_the_other_lacks():
    shared_name_only = candidate(category="multi_doc", keywords=["Ana Ruiz", "Administrator"], source_docs=TWO_DOCS,
                                 reference_answer="Ana Ruiz holds Salesforce Certified Administrator")
    assert candidate_problems(shared_name_only, KB) == ["no keyword unique to clients/nordwind.md"]


def test_unanswerable_needs_no_sources_fixed_answer_and_absent_keywords():
    good = candidate(category="unanswerable", reference_answer=NOT_IN_KB, source_docs=[], keywords=["parking"])
    assert candidate_problems(good, KB) == []
    bad = candidate(category="unanswerable", reference_answer="Unknown", source_docs=[], keywords=["ana ruiz"])
    assert candidate_problems(bad, KB) == [
        "unanswerable must have no source docs and the fixed reference answer",
        "unanswerable keyword in KB: ana ruiz",
    ]


DATED_KB = {"clients/a.md": "Client since: 2015", "employees/e.md": "Joined: 2014-10-13", "clients/b.md": "2016-03-01"}


def dated(question: str, keywords: list[str], docs: list[str]) -> Candidate:
    return candidate(question=question, category="multi_doc", source_docs=docs, keywords=keywords,
                     reference_answer=" and ".join(keywords))


def test_interval_between_a_bare_year_and_a_full_date_is_reported():
    ambiguous = "interval mixes a bare year and a full date: 2015, 2014-10-13"
    for question in ["How many years after joining did Ashgrove become a client?", "How long before ..."]:
        c = dated(question, ["2014-10-13", "2015"], ["clients/a.md", "employees/e.md"])
        assert candidate_problems(c, DATED_KB) == [ambiguous]


def test_ordering_with_a_bare_year_and_intervals_between_full_dates_are_allowed():
    first = dated("Which came first: joining or Ashgrove becoming a client?", ["2014-10-13", "2015"],
                  ["clients/a.md", "employees/e.md"])
    days = dated("How many days after joining did the project start?", ["2014-10-13", "2016-03-01"],
                 ["clients/b.md", "employees/e.md"])
    assert candidate_problems(first, DATED_KB) == candidate_problems(days, DATED_KB) == []


def test_interval_wording_anywhere_in_the_question_is_checked_unless_calendar_years_are_stated():
    keywords, docs = ["2014-10-13", "2015"], ["clients/a.md", "employees/e.md"]
    exact = dated("Exactly how many years after joining did Ashgrove become a client?", keywords, docs)
    assert candidate_problems(exact, DATED_KB) == ["interval mixes a bare year and a full date: 2015, 2014-10-13"]
    calendar = dated("By how many calendar years did joining precede Ashgrove becoming a client?", keywords, docs)
    assert candidate_problems(calendar, DATED_KB) == []


SPAN_KB = {"employees/e.md": "Joined: 2020-01-13", "clients/b.md": "Ended: 2024-05-06. Started: 2024-05-20."}


def span(answer: str, end: str) -> Candidate:
    return candidate(question="How long had Naveen been at the firm when the project ended?", category="multi_doc",
                     source_docs=["employees/e.md", "clients/b.md"], keywords=["2020-01-13", end],
                     reference_answer=f"From 2020-01-13 to {end}: {answer}.")


def test_months_and_days_answer_across_a_shorter_month_day_is_reported():
    borrow = span("4 years, 3 months and 23 days", "2024-05-06")
    assert candidate_problems(borrow, SPAN_KB) == [
        "months-and-days answer depends on the counting convention: 2020-01-13 to 2024-05-06",
    ]


def test_months_and_days_without_a_borrow_and_answers_in_days_are_allowed():
    assert candidate_problems(span("4 years, 4 months and 7 days", "2024-05-20"), SPAN_KB) == []
    assert candidate_problems(span("1,575 days", "2024-05-06"), SPAN_KB) == []


def test_candidate_without_keywords_is_reported():
    assert candidate_problems(candidate(keywords=[]), KB) == ["no keywords"]


def test_comparative_pairs_spread_over_every_client_and_are_distinct():
    pairs = comparative_pairs(WORLD)
    client_docs = [d for pair in pairs for d in pair if d.startswith("clients/")]
    counts = Counter(client_docs)
    assert len(pairs) == 60 and len({frozenset(p) for p in pairs}) == 60
    assert len(client_docs) == 60 and len(counts) == len(WORLD.clients)
    assert min(counts.values()) >= 2 and max(counts.values()) <= 5


def test_multi_doc_pairs_use_projects_beyond_the_first():
    path = entity_paths(WORLD)
    pairs = set(multi_doc_pairs(WORLD))
    beyond_first = {(path[c.id], path[p.service_id]) for c in WORLD.clients for p in c.projects[1:]}
    first = {(path[c.id], path[c.projects[0].service_id]) for c in WORLD.clients}
    assert pairs & (beyond_first - first)
    assert len(pairs) == len(multi_doc_pairs(WORLD)) and multi_doc_pairs(WORLD) == multi_doc_pairs(WORLD)
