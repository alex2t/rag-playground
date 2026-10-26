"""Exact tests for the document number and date check (T32)."""

from rag_playground.datasets.doc_checks import number_problems, tokens

FACTS = {
    "name": "Data Cloud Foundation",
    "price_usd": 86250,
    "typical_duration_weeks": 14,
    "launch_year": 2023,
    "deliverables": ["Identity resolution covering 3 source systems", "Go-live on 2024-03-18"],
}

FAITHFUL = """# Data Cloud Foundation

Launched in 2023, the service costs USD 86,250 and typically runs for 14 weeks.

1. Identity resolution covering 3 source systems.
2. Go-live on 2024-03-18.
"""


def test_tokens_normalise_thousands_separators_and_keep_decimals_and_dates():
    assert tokens("USD 86,250 and 97.6% on 2024-03-18, then 14.") == {"86250", "97.6", "2024-03-18", "14"}


def test_list_markers_are_not_numbers():
    assert tokens("1. First step\n2) Second step\n") == set()


def test_faithful_document_has_no_problems():
    assert number_problems(FAITHFUL, FACTS) == []


def test_changed_number_is_reported_as_added_and_missing():
    altered = FAITHFUL.replace("86,250", "86,520")
    assert number_problems(altered, FACTS) == ["added: 86520", "missing: 86250"]


def test_invented_number_and_non_iso_date_are_reported():
    # 2024 is the year of the fact date 2024-03-18, so it is allowed; the invented day 18 is not.
    doc = FAITHFUL + "\nIt went live on 18 March 2024 for 2 regions.\n"
    assert number_problems(doc, FACTS) == ["added: 18", "added: 2"]


def test_year_of_a_fact_date_is_allowed_but_not_required_and_other_years_are_not():
    assert number_problems(FAITHFUL + "\nIt went live in 2024.\n", FACTS) == []
    assert number_problems(FAITHFUL + "\nIt was planned in 2022.\n", FACTS) == ["added: 2022"]


def test_omitted_fact_date_is_reported():
    doc = FAITHFUL.replace("2. Go-live on 2024-03-18.\n", "")
    assert number_problems(doc, FACTS) == ["missing: 2024-03-18"]
