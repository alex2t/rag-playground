"""Finding a ladder configuration's stored run (T50). Uses the small stored world of test_best_run.py."""

from dataclasses import replace

import pytest
from test_best_run import META, conn, store_run  # noqa: F401

from rag_playground.rag import prompts
from rag_playground.rag.ladder import baseline, walk
from rag_playground.rag.ladder_runs import choices, finder
from rag_playground.settings import LADDER_SIZES, S0

BASE = baseline(prompts.DEFAULT_NAME)
STACK_A = replace(META, stack="A", hybrid=True, openai_ranking=S0["search"]["A"]["openai_ranking"])


def test_a_stored_s0_run_is_found_on_its_own_stack(conn):
    run_id = store_run(conn)
    assert finder(conn, "B")(BASE).run_id == run_id
    assert finder(conn, "A")(BASE) is None


def test_stack_a_is_found_with_its_own_default_search(conn):
    run_id = store_run(conn, meta=STACK_A)
    assert finder(conn, "A")(BASE).run_id == run_id


@pytest.mark.parametrize("change", [
    {"chunk_set_id": "fixed__c400__o78"}, {"top_k": 4}, {"hybrid": True}, {"answer_model": "openai/gpt-4.1-mini"},
    {"prompt_name": "v2"}, {"rerank_model": "m", "rerank_slug": "s", "rerank_candidates": 20}],
    ids=["chunk-set", "top-k", "hybrid", "model", "prompt", "rerank"])
def test_a_run_with_any_other_setting_is_not_the_configuration(conn, change):
    if "prompt_name" in change:
        prompts.save(conn, "v2", "Other text.")
        change = {**change, "prompt_sha256": prompts.get(conn, "v2").sha256}
    store_run(conn, meta=replace(META, **change))
    assert finder(conn, "B")(BASE) is None


def test_stack_a_with_other_ranking_is_not_the_default_search(conn):
    ranking = {**STACK_A.openai_ranking, "ranker": "none"}
    store_run(conn, meta=replace(STACK_A, openai_ranking=ranking))
    assert finder(conn, "A")(BASE) is None


def test_the_oldest_of_two_matching_runs_is_used(conn):
    """A later Evaluate run with the same settings must not change a past ladder decision."""
    oldest = store_run(conn, cost=0.09)
    store_run(conn, cost=0.01)
    assert finder(conn, "B")(BASE).run_id == oldest


def test_a_smoke_run_does_not_count_as_a_ladder_run(conn):
    store_run(conn, meta=replace(META, test_ids=META.test_ids[:8]))
    assert finder(conn, "B")(BASE) is None


def test_an_enriched_configuration_uses_the_enriched_chunk_set():
    assert choices("B", replace(BASE, method="llm_enriched")).chunk_set_id == "llm_enriched__c1024__o200"


def test_choices_carry_every_ladder_setting():
    config = replace(BASE, chunk_size=400, overlap=78, top_k=6, rerank=True, answer_model="m", prompt_name="p")
    made = choices("B", config)
    assert (made.chunk_set_id, made.top_k, made.rerank, made.answer_model, made.prompt_name) == (
        "fixed__c400__o78", 6, True, "m", "p")


def test_the_ladder_walks_from_a_stored_baseline_to_the_size_sweep(conn):
    store_run(conn)
    progress = walk(finder(conn, "B"), prompts.DEFAULT_NAME)
    assert [d.step for d in progress.decisions] == ["S0"]
    assert progress.next_step == "S1"
    assert [c.chunk_size for c in progress.missing] == [s for s in LADDER_SIZES if s != 1024]
