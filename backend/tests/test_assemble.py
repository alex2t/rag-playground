"""Exact tests for verification acceptance and test-set assembly (T30, T34)."""

from collections import Counter

import pytest

from rag_playground.datasets.assemble import QUOTAS, assemble, doc_kind, kind_cap, same_fact, select
from rag_playground.datasets.candidates import NOT_IN_KB, Candidate
from rag_playground.datasets.schema import Category
from rag_playground.datasets.verify_tests import Verdict, accepted

FOLDERS = ["clients", "services", "employees"]


def candidate(category: str = "numerical", i: int = 0, docs: list[str] | None = None,
              keyword: str | None = None) -> Candidate:
    """A candidate with its own document (folders in turn) and its own keyword, unless given."""
    unanswerable = category == "unanswerable"
    keyword = keyword or f"{category}-value-{i}"
    return Candidate(question=f"{category} question {i}?", reference_answer=NOT_IN_KB if unanswerable else keyword,
                     category=category, keywords=[keyword],
                     source_docs=[] if unanswerable else (docs or [f"{FOLDERS[i % 3]}/{category}-{i}.md"]))


def verdict(**overrides) -> Verdict:
    base = dict(index=0, answerable=True, unambiguous=True, reference_correct=True, reference_complete=True,
                docs_with_answer=["a.md"], fewer_docs_suffice=False, explanation="ok")
    return Verdict(**{**base, **overrides})


def test_answerable_candidate_is_kept_only_when_every_check_passes():
    c = candidate(docs=["a.md"])
    assert accepted(c, verdict())
    for failing in [dict(answerable=False), dict(unambiguous=False), dict(reference_correct=False),
                    dict(reference_complete=False), dict(fewer_docs_suffice=True)]:
        assert not accepted(c, verdict(**failing))


def test_answer_found_in_other_documents_too_is_rejected():
    assert not accepted(candidate(docs=["a.md"]), verdict(docs_with_answer=["a.md", "b.md"]))
    assert not accepted(candidate(docs=["a.md", "b.md"]), verdict(docs_with_answer=["a.md"]))
    assert accepted(candidate(docs=["a.md", "b.md"]), verdict(docs_with_answer=["b.md", "a.md"]))


def test_two_doc_question_answerable_from_one_doc_is_rejected():
    c = candidate("multi_doc", docs=["a.md", "b.md"])
    assert not accepted(c, verdict(docs_with_answer=["a.md", "b.md"], fewer_docs_suffice=True))


def test_unanswerable_candidate_is_kept_only_when_judged_not_answerable():
    assert accepted(candidate("unanswerable"), verdict(answerable=False, docs_with_answer=[]))
    assert not accepted(candidate("unanswerable"), verdict(answerable=True))


def full_pool(extra: int = 3) -> list[Candidate]:
    return [candidate(cat.value, i) for cat, quota in QUOTAS.items() for i in range(quota + extra)]


def test_assemble_gives_250_tests_with_quota_counts_and_200_50_split():
    tests = assemble(full_pool())
    assert len(tests) == 250
    assert Counter(t.category for t in tests) == QUOTAS
    assert Counter(t.split for t in tests) == {"dev": 200, "heldout": 50}
    assert sum(t.split == "heldout" and t.category == "unanswerable" for t in tests) == 5
    assert len({t.id for t in tests}) == 250
    assert tests[0].id == "direct_fact-001"


def test_assemble_is_deterministic_and_independent_of_input_order():
    pool = full_pool()
    assert assemble(pool) == assemble(list(reversed(pool)))


def test_duplicate_questions_count_once_and_shortfall_is_an_error():
    pool = [c for c in full_pool(extra=0) if c.category != "temporal"]
    pool += [candidate("temporal", i % 20) for i in range(40)]
    with pytest.raises(ValueError, match="temporal: 20 usable of 20 verified candidates, quota 37"):
        select(pool)


def test_doc_kind_is_the_sorted_folder_set():
    assert doc_kind(candidate(docs=["services/x.md", "employees/y.md"])) == "employees+services"
    assert doc_kind(candidate(docs=["clients/a.md", "clients/b.md"])) == "clients"
    assert doc_kind(candidate("unanswerable")) == ""


def test_no_document_kind_fills_more_than_40_percent_of_a_category():
    pool = [c for c in full_pool() if c.category != "numerical"]
    pool += [candidate("numerical", i, docs=[f"clients/n-{i}.md"]) for i in range(40)]
    pool += [candidate("numerical", 100 + i, docs=[f"services/n-{i}.md"]) for i in range(22)]
    with pytest.raises(ValueError, match="numerical: 30 usable of 62 verified candidates, quota 38"):
        select(pool)
    pool += [candidate("numerical", 200 + i, docs=[f"employees/n-{i}.md"]) for i in range(8)]
    kinds = Counter(doc_kind(c) for c in select(pool)["numerical"])
    assert kinds == {"clients": 15, "services": 15, "employees": 8}


def two_values(docs: list[str], keywords: list[str]) -> Candidate:
    return Candidate(question="q?", reference_answer=" ".join(keywords), category="multi_doc",
                     source_docs=docs, keywords=keywords)


def test_same_fact_when_a_shared_doc_and_one_tests_answer_values_cover_the_others():
    owner = candidate(docs=["deployment-runbooks/r.md"], keyword="Ana Ruiz")
    bridge = two_values(["deployment-runbooks/r.md", "employees/e.md"], ["ana ruiz", "2019-03-04"])
    assert same_fact(owner, bridge) and same_fact(bridge, owner)
    assert same_fact(bridge, two_values(["employees/e.md", "clients/c.md"], ["2019-03-04", "Ana Ruiz"]))
    assert not same_fact(owner, candidate(docs=["deployment-runbooks/r.md"], keyword="2019-03-04"))
    assert not same_fact(owner, candidate(docs=["clients/b.md"], keyword="Ana Ruiz"))


def test_tests_sharing_one_value_but_adding_different_ones_are_different_facts():
    saltmarsh = two_values(["clients/saltmarsh.md", "employees/e.md"], ["2020-01-13", "2023-05-08"])
    maplecrest = two_values(["clients/maplecrest.md", "employees/e.md"], ["2020-01-13", "2022-09-19"])
    assert not same_fact(saltmarsh, maplecrest)


def test_a_fact_already_tested_in_an_earlier_category_is_not_tested_again():
    owner = candidate("direct_fact", 0, docs=["deployment-runbooks/r.md"], keyword="Dashiell Pruitt")
    repeat = candidate("multi_doc", 999, docs=["deployment-runbooks/r.md", "employees/e.md"], keyword="Dashiell Pruitt")
    pool = [c for c in full_pool() if c.category != "direct_fact"] + [repeat]
    pool += [owner] + [candidate("direct_fact", i) for i in range(1, QUOTAS["direct_fact"])]
    chosen = select(pool)
    assert owner in chosen["direct_fact"]
    assert repeat not in chosen["multi_doc"] and len(chosen["multi_doc"]) == QUOTAS["multi_doc"]


def test_kind_cap_is_40_percent_and_none_for_unanswerable():
    assert kind_cap(Category.NUMERICAL, 38) == 15
    assert kind_cap(Category.TEMPORAL, 37) == 14
    assert kind_cap(Category.MULTI_DOC, 38) == 15
    assert kind_cap(Category.UNANSWERABLE, 25) == 25
