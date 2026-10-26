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
