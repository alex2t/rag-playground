"""Step 6 checks of best-run selection from stored runs: which runs may compete, and the scores they are judged on.
Every value comes from a small hand-built world, so each expected score can be checked by hand."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from rag_playground import store
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.datasets import schema
from rag_playground.rag import best_run, prompts, runs
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import JUDGE_MODEL
from rag_playground.stacks.hits import Hit

JUDGE_SLUG = "judge-v1"
DATASET = "d" * 64


def case(test_id: str, category: str, split: str = "dev") -> schema.TestCase:
    gold = {"unanswerable": [], "multi_doc": ["gold.md", "second.md"]}.get(category, ["gold.md"])
    return schema.TestCase(id=test_id, question="q", reference_answer="a", category=category, source_docs=gold,
                           keywords=["gold"], split=split)


DEV = [case("a1", "direct_fact"), case("a2", "numerical"), case("a3", "temporal"), case("a4", "multi_doc"),
       case("u1", "unanswerable"), case("u2", "unanswerable"), case("u3", "unanswerable"), case("u4", "unanswerable"),
       case("u5", "unanswerable")]
HELDOUT = [case("h1", "direct_fact", "heldout"), case("h2", "unanswerable", "heldout")]
DEV_IDS = [t.id for t in DEV]
UNANSWERABLE = DEV_IDS[4:]
META = runs.RunMeta(
    stack="B", split="dev", test_ids=DEV_IDS, chunk_set_id="fixed__c1024__o200", top_k=2, hybrid=False,
    openai_ranking=None, answer_model="openai/gpt-4.1-nano", answer_slug="nano-v1", judge_model=JUDGE_MODEL,
    judge_slug=JUDGE_SLUG, rerank_model=None, rerank_slug=None, rerank_candidates=None, temperature_controlled=True,
    prompt_name="default", prompt_sha256=prompts.sha256(prompts.DEFAULT_TEXT), dataset_sha256=DATASET,
    app_version="test")


@pytest.fixture
def conn(tmp_path, monkeypatch):
    connection = store.connect(tmp_path / "test.db")
    prompts.ensure_default(connection)
    monkeypatch.setattr(best_run, "load_tests", lambda: DEV + HELDOUT)
    monkeypatch.setattr(best_run, "dataset_sha256", lambda: DATASET)
    monkeypatch.setattr(best_run, "model_info", lambda model: SimpleNamespace(canonical_slug=JUDGE_SLUG))
    monkeypatch.setattr(best_run, "load_chunk_set", lambda set_id: [
        Chunk(chunk_id="c", source="gold.md", doc_type="d", index=0, text="gold", tokens=1, start=0, end=4)])
    yield connection
    connection.close()


def result(test_id: str, source: str = "gold.md", accuracy: int = 5, faithfulness: int = 5, refused: bool = False,
           cost: float = 0.01) -> runs.Result:
    verdict = Judgement(refused=refused, accuracy=accuracy, completeness=5, relevance=5, faithfulness=faithfulness,
                        feedback="f", faithfulness_feedback="f")
    return runs.Result(test_id=test_id, hits=[Hit("c", source, 1.0, "gold")], rerank_repaired=None, answer="a",
                       judgement=verdict, cost_usd=cost, latency_s=1.0)


def store_run(conn, results: dict[str, runs.Result] | None = None, meta: runs.RunMeta = META, **common) -> int:
    """A finished run; every declared question gets a passing result unless `results` overrides it."""
    run_id = runs.create_run(conn, meta)
    for test_id in meta.test_ids:
        default = result(test_id, refused=test_id in UNANSWERABLE or test_id == "h2", **common)
        runs.add_result(conn, run_id, (results or {}).get(test_id, default))
    runs.finish_run(conn, run_id)
    return run_id


def test_no_stored_run_means_no_best_run(conn):
    assert best_run.best_run(conn) is None


def test_a_candidate_holds_the_exact_scores_of_its_run(conn):
    """a1 misses gold (MRR 3/4); a4 finds 1 of its 2 gold documents (recall (0 + 1 + 1 + 1/2)/4); u1 is answered
    instead of refused (refusal 4/5). Faithfulness (1 + 8*5)/9. Cost (0.05 + 8*0.01)/9."""
    run_id = store_run(conn, {"a1": result("a1", source="other.md", accuracy=2, faithfulness=1, cost=0.05),
                              "u1": result("u1")})
    candidate = best_run.candidates(conn)[0]
    assert candidate.run_id == run_id
    assert candidate.scores == pytest.approx(
        {"mrr": 3 / 4, "recall": 5 / 8, "faithfulness": 41 / 9, "correct_refusal_rate": 4 / 5})
    assert candidate.accuracy == {"a1": 2, **{test_id: 5 for test_id in DEV_IDS[1:]}}
    assert candidate.cost_per_question == pytest.approx(0.13 / 9)


def test_the_best_run_is_chosen_from_stored_scores(conn):
    """Equal accuracy, so not a real difference: the cheaper run wins."""
    store_run(conn, cost=0.02)
    cheaper = store_run(conn, cost=0.01)
    assert best_run.best_run(conn).run_id == cheaper


def test_a_stored_run_failing_a_gate_is_not_chosen(conn):
    """Only 3 of 5 unanswerable questions refused: correct refusal rate 0.6, below 0.80."""
    store_run(conn, {"u1": result("u1"), "u2": result("u2")}, cost=0.001)
    passing = store_run(conn, cost=0.09)
    assert best_run.best_run(conn).run_id == passing


@pytest.mark.parametrize("meta", [
    replace(META, test_ids=DEV_IDS[:8]), replace(META, split="heldout", test_ids=["h1", "h2"]),
    replace(META, split="heldout"), replace(META, dataset_sha256="e" * 64), replace(META, judge_slug="judge-v2")],
    ids=["smoke", "heldout", "marked-heldout", "old-dataset", "other-judge"])
def test_runs_that_cannot_be_compared_never_compete(conn, meta):
    """The other run is cheaper, so it would win if it were allowed to compete."""
    comparable = store_run(conn, cost=0.09)
    store_run(conn, meta=meta, cost=0.01)
    assert [c.run_id for c in best_run.candidates(conn)] == [comparable]


def test_a_failed_run_and_a_running_run_never_compete(conn):
    comparable = store_run(conn)
    runs.create_run(conn, META)
    failed = runs.create_run(conn, META)
    for test_id in DEV_IDS:
        runs.add_result(conn, failed, result(test_id, refused=test_id in UNANSWERABLE))
    runs.finish_run(conn, failed, error="Budget reached")
    assert [c.run_id for c in best_run.candidates(conn)] == [comparable]


def test_the_order_of_a_runs_questions_does_not_stop_it_competing(conn):
    run_id = store_run(conn, meta=replace(META, test_ids=DEV_IDS[::-1]))
    assert [c.run_id for c in best_run.candidates(conn)] == [run_id]
