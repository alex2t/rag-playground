"""Step 6 checks of the evaluation pipeline, with fake models and a fake retriever (no network, no cost)."""

from dataclasses import replace

import pytest

from rag_playground import store
from rag_playground.datasets.schema import dataset_sha256, load_tests
from rag_playground.llm.models import ModelInfo
from rag_playground.llm.openrouter import ChatResult
from rag_playground.rag import pipeline, prompts, runs
from rag_playground.rag.rerank import Reranked
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import JUDGE_MODEL, RERANK_CANDIDATES, RERANK_MODEL
from rag_playground.stacks.hits import Hit

DEV = [t for t in load_tests() if t.split == "dev"][:10]
HELDOUT = [t for t in load_tests() if t.split == "heldout"][:3]
NO_TEMPERATURE = "openai/gpt-6.1-sol"
MINI = "openai/gpt-4.1-mini"  # not the reranker model, so the two can be told apart
VERDICT = Judgement(refused=False, accuracy=5, completeness=5, relevance=5, faithfulness=5, feedback="ok",
                    faithfulness_feedback="ok")
CHOICES = pipeline.Choices(stack="B", chunk_set_id="fixed__c1024__o200", top_k=3, hybrid=False,
                           openai_ranking=None, rerank=False, answer_model="openai/gpt-4.1-nano",
                           prompt_name="default")


def call(cost: float, text: str = "An answer.") -> ChatResult:
    return ChatResult(text=text, model="m", canonical_slug="m-1", temperature_controlled=True, prompt_tokens=1,
                      completion_tokens=1, reasoning_tokens=0, cost_usd=cost)


def info(model_id: str, no_temperature: tuple[str, ...] = (NO_TEMPERATURE,)) -> ModelInfo:
    params = frozenset() if model_id in no_temperature else frozenset({"temperature"})
    return ModelInfo(model_id, f"{model_id}-2026", params, 0.0, 0.0)


def candidates(question: str, k: int) -> list[Hit]:
    return [Hit(f"c{i}", f"doc{i}.md", 1 / (i + 1), f"Chunk {i} for {question}") for i in range(k)]


@pytest.fixture
def fakes(monkeypatch):
    """Fake model metadata, reranker, answer model and judge; records what each received."""
    seen = {"retrieve": [], "rerank": [], "answer": [], "judge": []}
    monkeypatch.setattr(pipeline, "model_info", info)

    def rerank(question, hits, k):
        seen["rerank"].append((question, len(hits), k))
        return Reranked(list(reversed(hits))[:k], call(0.001), repaired=True)

    def answer(model, prompt, question, hits):
        seen["answer"].append((model, prompt.name, [h.chunk_id for h in hits]))
        return call(0.01)

    def judge(test, context, text):
        seen["judge"].append(context)
        return VERDICT, [call(0.002), call(0.003)]

    monkeypatch.setattr(pipeline, "rerank", rerank)
    monkeypatch.setattr(pipeline, "answer", answer)
    monkeypatch.setattr(pipeline, "judge", judge)
    return seen


def retriever(seen):
    def retrieve(question, k):
        seen["retrieve"].append(k)
        return candidates(question, k)
    return retrieve


@pytest.fixture
def conn(tmp_path):
    connection = store.connect(tmp_path / "test.db")
    prompts.ensure_default(connection)
    yield connection
    connection.close()


def test_a_10_question_run_stores_10_rows_with_full_metadata_and_progress_reaches_1(conn, fakes):
    """The plan's Step 6 check."""
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    assert runs.progress(conn, run_id) == 0.0
    pipeline.execute(conn, run_id, retriever(fakes))
    run = runs.get_run(conn, run_id)
    assert run.status == "done"
    assert run.meta == runs.RunMeta(
        stack="B", split="dev", test_ids=[t.id for t in DEV], chunk_set_id="fixed__c1024__o200", top_k=3, hybrid=False,
        openai_ranking=None, answer_model="openai/gpt-4.1-nano", answer_slug="openai/gpt-4.1-nano-2026",
        judge_model=JUDGE_MODEL, judge_slug=f"{JUDGE_MODEL}-2026", rerank_model=None, rerank_slug=None,
        rerank_candidates=None, temperature_controlled=True, prompt_name="default",
        prompt_sha256=prompts.sha256(prompts.DEFAULT_TEXT), dataset_sha256=dataset_sha256(), app_version="dev")
    assert [r.test_id for r in runs.get_results(conn, run_id)] == [t.id for t in DEV]
    assert runs.progress(conn, run_id) == 1.0


def test_without_rerank_k_chunks_go_to_the_answer_and_the_judge(conn, fakes):
    run_id = pipeline.start_run(conn, CHOICES, DEV[:2])
    pipeline.execute(conn, run_id, retriever(fakes))
    assert fakes["retrieve"] == [3, 3]
    assert fakes["rerank"] == []
    assert [ids for _, _, ids in fakes["answer"]] == [["c0", "c1", "c2"]] * 2
    result = runs.get_results(conn, run_id)[0]
    assert [h.chunk_id for h in result.hits] == ["c0", "c1", "c2"]
    assert fakes["judge"][0] == [h.text for h in result.hits]
    assert result.rerank_repaired is None
    assert result.cost_usd == pytest.approx(0.01 + 0.002 + 0.003)


def test_with_rerank_20_candidates_are_reranked_and_only_the_top_k_are_answered_and_judged(conn, fakes):
    run_id = pipeline.start_run(conn, replace(CHOICES, rerank=True), DEV[:1])
    pipeline.execute(conn, run_id, retriever(fakes))
    assert fakes["retrieve"] == [RERANK_CANDIDATES]
    assert fakes["rerank"] == [(DEV[0].question, RERANK_CANDIDATES, 3)]
    reranked = ["c19", "c18", "c17"]
    assert fakes["answer"] == [("openai/gpt-4.1-nano", "default", reranked)]
    result = runs.get_results(conn, run_id)[0]
    assert [h.chunk_id for h in result.hits] == reranked
    assert fakes["judge"] == [[h.text for h in result.hits]]
    assert result.rerank_repaired is True
    assert result.cost_usd == pytest.approx(0.001 + 0.01 + 0.002 + 0.003)
    meta = runs.get_run(conn, run_id).meta
    assert (meta.rerank_model, meta.rerank_slug, meta.rerank_candidates) == (
        RERANK_MODEL, f"{RERANK_MODEL}-2026", RERANK_CANDIDATES)


def test_a_rerank_without_a_model_call_adds_no_cost(conn, fakes, monkeypatch):
    """With 0 or 1 candidate the reranker makes no call and returns no usage."""
    monkeypatch.setattr(pipeline, "rerank", lambda question, hits, k: Reranked(hits[:k], None, repaired=False))
    run_id = pipeline.start_run(conn, replace(CHOICES, rerank=True), DEV[:1])
    pipeline.execute(conn, run_id, lambda question, k: [])
    result = runs.get_results(conn, run_id)[0]
    assert (result.hits, result.rerank_repaired) == ([], False)
    assert result.cost_usd == pytest.approx(0.01 + 0.002 + 0.003)


def test_latency_covers_retrieval_and_answer_but_not_the_judge(conn, fakes, monkeypatch):
    """A fake clock: retrieval takes 0.5 s, the answer 2 s and the judge 30 s."""
    clock = {"now": 100.0}

    def taking(seconds, reply):
        def step(*args):
            clock["now"] += seconds
            return reply
        return step

    monkeypatch.setattr(pipeline, "perf_counter", lambda: clock["now"])
    monkeypatch.setattr(pipeline, "answer", taking(2.0, call(0.01)))
    monkeypatch.setattr(pipeline, "judge", taking(30.0, (VERDICT, [])))
    run_id = pipeline.start_run(conn, CHOICES, DEV[:1])
    pipeline.execute(conn, run_id, taking(0.5, candidates("q", 3)))
    assert runs.get_results(conn, run_id)[0].latency_s == 2.5


def test_a_failure_marks_the_run_failed_keeps_earlier_results_and_is_raised(conn, fakes, monkeypatch):
    answered = []

    def answer(model, prompt, question, hits):
        if len(answered) == 3:
            raise RuntimeError("rate limited")
        answered.append(question)
        return call(0.01)

    monkeypatch.setattr(pipeline, "answer", answer)
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    with pytest.raises(RuntimeError, match="rate limited"):
        pipeline.execute(conn, run_id, retriever(fakes))
    run = runs.get_run(conn, run_id)
    assert (run.status, run.error) == ("failed", "RuntimeError: rate limited")
    assert len(runs.get_results(conn, run_id)) == 3
    assert runs.progress(conn, run_id) == 0.3


def test_the_run_uses_the_stored_prompt_version(conn, fakes):
    prompts.save(conn, "strict", "Only answer from the context.")
    run_id = pipeline.start_run(conn, replace(CHOICES, prompt_name="strict"), DEV[:1])
    pipeline.execute(conn, run_id, retriever(fakes))
    assert fakes["answer"][0][1] == "strict"
    assert runs.get_run(conn, run_id).meta.prompt_sha256 == prompts.sha256("Only answer from the context.")


@pytest.mark.parametrize("choices, no_temperature, controlled", [
    (CHOICES, (), True),
    (replace(CHOICES, rerank=True), (), True),
    (CHOICES, ("openai/gpt-4.1-nano",), False),  # the answer model
    (CHOICES, (JUDGE_MODEL,), False),
    (replace(CHOICES, answer_model=MINI, rerank=True), (RERANK_MODEL,), False),
    (replace(CHOICES, answer_model=MINI), (RERANK_MODEL,), True),  # a reranker that is not used does not count
], ids=["all-accept", "all-accept-rerank", "answer", "judge", "reranker", "unused-reranker"])
def test_a_run_is_temperature_controlled_only_if_every_model_it_uses_accepts_temperature(
        fakes, monkeypatch, choices, no_temperature, controlled):
    """The answer model, the judge and the reranker (when on) are all checked (T14)."""
    monkeypatch.setattr(pipeline, "model_info", lambda model_id: info(model_id, no_temperature))
    default = prompts.PromptVersion("default", "x", prompts.sha256("x"))
    assert pipeline.build_meta(choices, default, DEV).temperature_controlled is controlled


def test_a_run_asking_the_same_question_twice_is_refused(fakes):
    default = prompts.PromptVersion("default", "x", prompts.sha256("x"))
    with pytest.raises(ValueError, match="once"):
        pipeline.build_meta(CHOICES, default, DEV[:2] + DEV[:1])


def test_execute_asks_exactly_the_questions_the_run_declared_in_order(conn, fakes):
    """The questions are read back from the run, so they cannot differ from the declared ones."""
    chosen = [DEV[4], DEV[1], DEV[7]]
    run_id = pipeline.start_run(conn, CHOICES, chosen)
    pipeline.execute(conn, run_id, retriever(fakes))
    assert [r.test_id for r in runs.get_results(conn, run_id)] == [t.id for t in chosen]
    assert runs.progress(conn, run_id) == 1.0


def test_a_run_mixing_dev_and_heldout_questions_is_refused(fakes):
    default = prompts.PromptVersion("default", "x", prompts.sha256("x"))
    with pytest.raises(ValueError, match="one split"):
        pipeline.build_meta(CHOICES, default, DEV[:2] + HELDOUT[:1])


def test_heldout_runs_use_the_default_prompt_only(fakes):
    """Prompt tuning happens on dev questions; held-out questions confirm, they never tune (T36)."""
    default = prompts.PromptVersion("default", "x", prompts.sha256("x"))
    other = prompts.PromptVersion("strict", "y", prompts.sha256("y"))
    assert pipeline.build_meta(CHOICES, default, HELDOUT).split == "heldout"
    with pytest.raises(ValueError, match="default prompt"):
        pipeline.build_meta(replace(CHOICES, prompt_name="strict"), other, HELDOUT)


@pytest.mark.parametrize("fail", [False, True], ids=["done", "failed"])
def test_a_finished_run_is_never_run_again(conn, fakes, monkeypatch, fail):
    """A second execute would flip a complete run to failed; it is refused before any call."""
    if fail:
        monkeypatch.setattr(pipeline, "answer", lambda *a: (_ for _ in ()).throw(RuntimeError("down")))
    run_id = pipeline.start_run(conn, CHOICES, DEV[:2])
    if fail:
        with pytest.raises(RuntimeError):
            pipeline.execute(conn, run_id, retriever(fakes))
    else:
        pipeline.execute(conn, run_id, retriever(fakes))
    before = (runs.get_run(conn, run_id), runs.get_results(conn, run_id), len(fakes["retrieve"]))
    with pytest.raises(ValueError, match="finished run"):
        pipeline.execute(conn, run_id, retriever(fakes))
    assert (runs.get_run(conn, run_id), runs.get_results(conn, run_id), len(fakes["retrieve"])) == before
