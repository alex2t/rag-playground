"""Select verified candidates per category quota, assign ids and splits (T30, T34)."""

import math
import random
import re
from collections import Counter

from rag_playground.datasets.candidates import Candidate
from rag_playground.datasets.schema import Category, TestCase
from rag_playground.datasets.splits import SEED, assign_splits

# T30: 25 unanswerable and 37 or 38 per answerable category; temporal and multi_doc reduced to what the
# verified pool fills under the distinct-fact rule and the 40% kind cap (T34 revision).
QUOTAS = {
    Category.DIRECT_FACT: 38, Category.MULTI_DOC: 30, Category.NUMERICAL: 38,
    Category.TEMPORAL: 35, Category.COMPARATIVE: 37, Category.EXACT_TERM: 37,
    Category.UNANSWERABLE: 25,
}
# T34, custom choice: no document kind (folder or folder pair) may fill more than this share of a category.
KIND_SHARE = 0.4


def paths_kind(paths: list[str] | tuple[str, ...]) -> str:
    """The KB folders of some document paths, such as "clients" or "deployment-runbooks+employees"."""
    return "+".join(sorted({d.split("/")[0] for d in paths}))


def doc_kind(c: Candidate) -> str:
    return paths_kind(c.source_docs)


def same_fact(a: Candidate, b: Candidate) -> bool:
    """T34, custom rule: two tests sharing a source doc test the same fact when every answer value (keyword)
    of one is also an answer value of the other, or when every source doc of one is also a source doc of the
    other and they share an answer value (the same fact reached from the same documents)."""
    ka, kb = {k.lower() for k in a.keywords}, {k.lower() for k in b.keywords}
    da, db = set(a.source_docs), set(b.source_docs)
    return bool(da & db) and (ka <= kb or kb <= ka or ((da <= db or db <= da) and shares_value(ka, kb)))


def contains_value(text: str, value: str) -> bool:
    """`value` appears in `text` as a whole value: "85.0%" is in "85.0% pass rate" but "5.0%" is not in "85.0%"."""
    return re.search(rf"(?<![\w.-]){re.escape(value)}(?![\w-])", text) is not None


def shares_value(ka: set[str], kb: set[str]) -> bool:
    """Two keyword sets share a value, even when one keyword adds words around it."""
    return any(contains_value(x, y) or contains_value(y, x) for x in ka for y in kb)


def distinct_facts(candidates: list[Candidate]) -> list[Candidate]:
    """Keep each candidate unless an earlier kept one tests the same fact."""
    kept = []
    for c in candidates:
        if not any(same_fact(c, k) for k in kept):
            kept.append(c)
    return kept


def kind_cap(category: Category, quota: int) -> int:
    if category == Category.UNANSWERABLE:
        return quota
    return math.floor(KIND_SHARE * quota)


def category_pools(candidates: list[Candidate]) -> dict[Category, list[Candidate]]:
    """Distinct questions per category, sorted, in scarcest-first order (pool size / quota, then QUOTAS order),
    so the categories with the fewest spare candidates claim a fact shared with another category."""
    pools = {}
    for category in QUOTAS:
        unique = {c.question.strip().lower(): c for c in candidates if c.category == category}
        pools[category] = sorted(unique.values(), key=lambda c: c.question)
    return dict(sorted(pools.items(), key=lambda item: len(item[1]) / QUOTAS[item[0]]))


def select(candidates: list[Candidate], seed: int = SEED) -> dict[Category, list[Candidate]]:
    """Per category, scarcest first: shuffle with the seed, then take candidates in order, skipping any whose
    document kind is at its cap or whose fact an earlier pick (any category) already tests."""
    rng = random.Random(seed)
    chosen, taken = {}, []
    for category, pool in category_pools(candidates).items():
        quota = QUOTAS[category]
        rng.shuffle(pool)
        picks, kinds = [], Counter()
        for c in pool:
            if len(picks) == quota:
                break
            if kinds[doc_kind(c)] < kind_cap(category, quota) and not any(same_fact(c, t) for t in taken):
                picks.append(c)
                taken.append(c)
                kinds[doc_kind(c)] += 1
        if len(picks) < quota:
            raise ValueError(f"{category}: {len(picks)} usable of {len(pool)} verified candidates, quota {quota}")
        chosen[category] = picks
    return {category: chosen[category] for category in QUOTAS}


def assemble(candidates: list[Candidate], seed: int = SEED) -> list[TestCase]:
    """Build the test cases with ids like "temporal-007" and the stratified split."""
    chosen = select(candidates, seed)
    ids = {cat: [f"{cat.value}-{i:03d}" for i in range(1, len(cs) + 1)] for cat, cs in chosen.items()}
    split = assign_splits({cat.value: v for cat, v in ids.items()}, seed=seed)
    return [
        TestCase(id=test_id, split=split[test_id], **c.model_dump())
        for cat, cs in chosen.items() for test_id, c in zip(ids[cat], cs)
    ]
