"""Step 2 checks on the committed synthetic dataset (plan.md section 6, T30, T34)."""

import json
from collections import Counter
from itertools import combinations

from rag_playground.datasets.assemble import QUOTAS, doc_kind, kind_cap, same_fact
from rag_playground.datasets.candidates import NOT_IN_KB, Candidate, candidate_problems
from rag_playground.datasets.schema import KB_DIR, VERIFICATION_PATH, load_tests
from rag_playground.datasets.splits import assign_splits, group_by_category

TESTS = load_tests()
KB = {p.relative_to(KB_DIR).as_posix(): p.read_text(encoding="utf-8").lower() for p in KB_DIR.rglob("*.md")}
CANDIDATES = [Candidate.model_validate(t.model_dump()) for t in TESTS]


def test_every_source_doc_path_exists():
    missing = [(t.id, d) for t in TESTS for d in t.source_docs if d not in KB]
    assert missing == []


def test_answerable_keywords_appear_in_their_gold_documents():
    misses = [(t.id, k) for t in TESTS if t.category != "unanswerable"
              for k in t.keywords if k.lower() not in "\n".join(KB[d] for d in t.source_docs)]
    assert misses == []


def test_unanswerable_tests_have_no_sources_and_keywords_appear_nowhere_in_the_kb():
    corpus = "\n".join(KB.values())
    unanswerable = [t for t in TESTS if t.category == "unanswerable"]
    assert all(t.source_docs == [] and t.reference_answer == NOT_IN_KB for t in unanswerable)
    assert [(t.id, k) for t in unanswerable for k in t.keywords if k.lower() in corpus] == []


def test_category_counts_per_split_match_t30():
    counts = Counter((t.category.value, t.split.value) for t in TESTS)
    print("\ncategory counts per split:", dict(sorted(counts.items())))
    assert Counter(t.category for t in TESTS) == QUOTAS
    assert Counter(t.split for t in TESTS) == {"dev": 200, "heldout": 50}
    assert counts[("unanswerable", "dev")] == 20 and counts[("unanswerable", "heldout")] == 5


def test_ids_and_questions_are_unique():
    assert len({t.id for t in TESTS}) == len(TESTS) == 250
    assert len({t.question.strip().lower() for t in TESTS}) == 250


def test_split_is_identical_on_every_load_and_reproducible_from_the_seed():
    assert load_tests() == TESTS
    recomputed = assign_splits(group_by_category([(t.id, t.category.value) for t in TESTS]))
    assert {t.id: t.split.value for t in TESTS} == recomputed


def test_every_test_was_accepted_by_the_full_kb_verification():
    rows = [json.loads(line) for line in VERIFICATION_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    accepted = {r["candidate"]["question"] for r in rows if r["accepted"]}
    assert [t.id for t in TESTS if t.question not in accepted] == []


def test_every_test_passes_the_candidate_code_checks():
    assert [(t.id, p) for t, c in zip(TESTS, CANDIDATES) if (p := candidate_problems(c, KB))] == []


def test_no_two_tests_test_the_same_fact():
    assert [(a.id, b.id) for (a, ca), (b, cb) in combinations(zip(TESTS, CANDIDATES), 2) if same_fact(ca, cb)] == []


def test_no_document_kind_fills_more_than_its_share_of_a_category():
    kinds = Counter((t.category, doc_kind(c)) for t, c in zip(TESTS, CANDIDATES))
    print("\ndocument kinds per category:", dict(sorted(kinds.items())))
    assert [(cat, kind, n) for (cat, kind), n in kinds.items() if n > kind_cap(cat, QUOTAS[cat])] == []
