"""T60 check of the question splitter itself (OpenRouter, gpt-4.1-mini, under $0.001): the structured reply with its
1 to 3 limit is accepted, a two-document question is split and a one-fact question is not.
Run with `uv run pytest -m live tests/test_live_decompose.py`."""

import pytest

from rag_playground.datasets.schema import load_tests
from rag_playground.rag.decompose import split_and_search

pytestmark = pytest.mark.live

BY_ID = {t.id: t for t in load_tests()}
SIMPLE = BY_ID["direct_fact-002"]  # Which languages does Keiko Lindqvist speak? One staff directory.
TWO_DOCS = BY_ID["multi_doc-006"]  # Dashiell Pruitt's start date (staff directory) against a client project's end.


def no_search(question, k):
    return []


def test_a_one_fact_question_is_not_split():
    split = split_and_search(SIMPLE.question, 2, no_search)
    assert len(split.sub_questions) == 1 and split.searches == 1
    assert split.result.temperature_controlled and split.result.cost_usd > 0


def test_a_two_document_question_is_split_into_two_parts():
    split = split_and_search(TWO_DOCS.question, 2, no_search)
    print(split.sub_questions)
    assert len(split.sub_questions) == 2 and split.searches == 2
