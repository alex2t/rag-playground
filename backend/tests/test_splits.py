"""Exact tests for the stratified dev / held-out split (T18, T30)."""

from rag_playground.datasets.splits import assign_splits, heldout_quotas

COUNTS = {
    "unanswerable": 25,
    "direct_fact": 38, "multi_doc": 38, "numerical": 38,
    "temporal": 37, "comparative": 37, "exact_term": 37,
}


def make_ids(counts: dict[str, int]) -> dict[str, list[str]]:
    return {c: [f"{c}-{i:03d}" for i in range(n)] for c, n in counts.items()}


def test_quotas_sum_to_50_with_largest_remainder():
    # 50/250 = 1/5 of each category: 25 -> 5.0, 38 -> 7.6, 37 -> 7.4.
    # Floors give 47; the 3 spare slots go to the 0.6 remainders.
    assert heldout_quotas(COUNTS, 50) == {
        "unanswerable": 5,
        "direct_fact": 8, "multi_doc": 8, "numerical": 8,
        "temporal": 7, "comparative": 7, "exact_term": 7,
    }


def test_quota_ties_are_broken_by_category_name():
    assert heldout_quotas({"b": 1, "a": 1}, 1) == {"a": 1, "b": 0}


def test_split_gives_200_dev_and_50_heldout_stratified():
    split = assign_splits(make_ids(COUNTS))
    assert len(split) == 250
    assert list(split.values()).count("heldout") == 50
    heldout_unanswerable = [i for i, s in split.items() if s == "heldout" and i.startswith("unanswerable")]
    assert len(heldout_unanswerable) == 5


def test_heldout_is_a_fifth_of_any_total_rounded():
    smaller = {**COUNTS, "temporal": 35, "multi_doc": 30}
    assert list(assign_splits(make_ids(smaller)).values()).count("heldout") == 48
    assert list(assign_splits(make_ids({**smaller, "multi_doc": 36})).values()).count("heldout") == 49


def test_split_is_identical_on_every_call_and_ignores_input_order():
    ids = make_ids(COUNTS)
    reversed_ids = {c: list(reversed(v)) for c, v in reversed(list(ids.items()))}
    assert assign_splits(ids) == assign_splits(ids) == assign_splits(reversed_ids)


def test_split_depends_on_the_seed():
    ids = make_ids(COUNTS)
    assert assign_splits(ids, seed=42) != assign_splits(ids, seed=43)
