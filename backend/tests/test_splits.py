"""Exact tests for the stratified dev / held-out split (T18, T30)."""

from rag_playground.datasets.schema import load_tests
from rag_playground.datasets.splits import assign_splits, heldout_quotas, round_robin

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


DEV = [t for t in load_tests() if t.split == "dev"]


def test_round_robin_takes_each_category_in_turn_in_file_order():
    """The file is grouped by category, so the first 10 dev questions are all one category (T46)."""
    picked = round_robin(DEV, 10)
    order = list(dict.fromkeys(t.category for t in DEV))
    assert len(order) == 7
    assert [t.category for t in picked] == order + order[:3]
    firsts = [next(t for t in DEV if t.category == c) for c in order]
    seconds = [[t for t in DEV if t.category == c][1] for c in order[:3]]
    assert picked == firsts + seconds


def test_round_robin_with_fewer_than_one_per_category_and_more_than_all():
    assert [t.category for t in round_robin(DEV, 3)] == list(dict.fromkeys(t.category for t in DEV))[:3]
    picked = round_robin(DEV, 1000)
    assert sorted(t.id for t in picked) == sorted(t.id for t in DEV)


def test_round_robin_keeps_going_after_a_category_runs_out():
    a, b = DEV[0], next(t for t in DEV if t.category != DEV[0].category)
    others = [t for t in DEV if t.category == b.category][:3]
    assert round_robin([a] + others, 4) == [a, others[0], others[1], others[2]]
