"""Step 6 checks of the budget cap (D15, T44): a run over the remaining budget is refused, a running job stops
before a question that could pass it. Fake models and fixed estimates (no network, no cost).

Amounts are powers of two, so every sum is exact."""

import pytest

from rag_playground import store
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.datasets.schema import load_tests
from rag_playground.llm.models import ModelInfo
from rag_playground.llm.openrouter import ChatResult, paid
from rag_playground.rag import pipeline, prompts, runs, spend
from rag_playground.rag.rerank import Reranked
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import Settings, settings
from rag_playground.stacks.hits import Hit

DEV = [t for t in load_tests() if t.split == "dev"][:10]
CHOICES = pipeline.Choices(stack="B", chunk_set_id="fixed__c512__o0", top_k=3, hybrid=False, openai_ranking=None,
                           rerank=False, answer_model="openai/gpt-4.1-nano", prompt_name="default")
CHUNKS = [Chunk(chunk_id=f"d.md#{i}", source="d.md", doc_type="d", index=i, text="x", tokens=tokens, start=0, end=1)
          for i, tokens in enumerate([100, 200, 600])]
VERDICT = Judgement(refused=False, accuracy=5, completeness=5, relevance=5, faithfulness=5, feedback="ok",
                    faithfulness_feedback="ok")


def call(cost: float) -> ChatResult:
    return ChatResult(text="An answer.", model="m", canonical_slug="m-1", temperature_controlled=True,
                      prompt_tokens=1, completion_tokens=1, reasoning_tokens=0, cost_usd=cost)


@pytest.fixture
def conn(tmp_path):
    connection = store.connect(tmp_path / "test.db")
    prompts.ensure_default(connection)
    yield connection
    connection.close()


@pytest.fixture
def world(monkeypatch):
    """Budget $1; each question really costs `cost` (one paid answer call, the judge free); the estimates are
    fixed. Records what the estimate functions received and which questions were answered."""
    state = {"cost": 0.25, "guess": 0.125, "run_estimate": 0.0, "answered": [], "run_args": [], "guess_args": []}
    monkeypatch.setattr(settings, "budget_usd", 1.0)
    monkeypatch.setattr(pipeline, "model_info", lambda m: ModelInfo(m, f"{m}-1", frozenset(), 0.0, 0.0))
    monkeypatch.setattr(pipeline, "load_chunk_set", lambda set_id: CHUNKS if set_id == CHOICES.chunk_set_id else [])

    def run_cost(tests, prompt, answer_model, top_k, rerank, chunks):
        state["run_args"].append(([t.id for t in tests], prompt.name, answer_model, top_k, rerank, chunks))
        return state["run_estimate"]

    def question_cost(test, prompt, answer_model, top_k, rerank, chunk_tokens):
        state["guess_args"].append((test.id, prompt.name, answer_model, top_k, rerank, chunk_tokens))
        return state["guess"]

    def answer(model, prompt, question, hits):
        state["answered"].append(question)
        return paid(call(state["cost"]))

    monkeypatch.setattr(pipeline.estimate, "run_cost", run_cost)
    monkeypatch.setattr(pipeline.estimate, "question_cost", question_cost)
    monkeypatch.setattr(pipeline, "answer", answer)
    monkeypatch.setattr(pipeline, "judge", lambda test, context, text: (VERDICT, []))
    return state


def retrieve(question, k):
    return [Hit(f"c{i}", f"doc{i}.md", 1.0, "text") for i in range(k)]


def spent_elsewhere(conn, dollars):
    """Spend outside any run, such as an earlier sweep's failed call; it counts against the same budget (D15)."""
    spend.record(conn, None, call(dollars))


def run_ids(conn):
    return [row[0] for row in conn.execute("SELECT id FROM runs")]


def test_a_run_estimated_over_the_remaining_budget_is_refused_and_nothing_is_stored(conn, world):
    spent_elsewhere(conn, 0.5)
    world["run_estimate"] = 0.5 + 2 ** -10
    with pytest.raises(pipeline.BudgetExceeded, match=r"estimated at \$0\.5010, but only \$0\.5000 .* \$1\.00"):
        pipeline.start_run(conn, CHOICES, DEV)
    assert run_ids(conn) == []
    assert spend.total(conn) == 0.5


def test_a_run_estimated_at_exactly_the_remaining_budget_starts(conn, world):
    spent_elsewhere(conn, 0.5)
    world["run_estimate"] = 0.5
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    assert run_ids(conn) == [run_id]


def test_the_start_estimate_uses_the_run_settings_and_its_chunk_set(conn, world):
    choices = pipeline.Choices(stack="B", chunk_set_id=CHOICES.chunk_set_id, top_k=5, hybrid=False,
                               openai_ranking=None, rerank=True, answer_model="openai/gpt-4.1-mini",
                               prompt_name="default")
    pipeline.start_run(conn, choices, DEV[:2])
    assert world["run_args"] == [([t.id for t in DEV[:2]], "default", "openai/gpt-4.1-mini", 5, True, CHUNKS)]


def test_with_no_budget_set_any_paid_run_is_refused(conn, world, monkeypatch):
    """BUDGET_USD unset means $0: a machine without it cannot spend by mistake."""
    monkeypatch.delenv("BUDGET_USD", raising=False)
    monkeypatch.setattr(settings, "budget_usd", Settings(_env_file=None).budget_usd)
    world["run_estimate"] = 2 ** -20
    with pytest.raises(pipeline.BudgetExceeded):
        pipeline.start_run(conn, CHOICES, DEV)


def execute(conn, choices=CHOICES, tests=DEV):
    run_id = pipeline.start_run(conn, choices, tests)
    with pytest.raises(pipeline.BudgetExceeded):
        pipeline.execute(conn, run_id, retrieve)
    return run_id


def test_a_run_stops_before_the_question_that_could_pass_the_budget(conn, world):
    """$0.25 per question, guess $0.125: after 4 questions $1.00 is spent; a fifth could pass $1, so it is not
    asked. The run keeps its 4 results and is marked failed with the reason."""
    run_id = execute(conn)
    run = runs.get_run(conn, run_id)
    assert len(world["answered"]) == len(runs.get_results(conn, run_id)) == 4
    assert run.status == "failed"
    assert run.error == ("BudgetExceeded: Budget reached: $1.0000 spent of BUDGET_USD $1.00; "
                         "the next question could cost $0.2500")
    assert spend.total(conn) == 1.0


def test_the_next_question_is_assumed_as_costly_as_the_largest_so_far(conn, world, monkeypatch):
    """The estimate is low for reasoning models. With the estimate alone ($0.125) the 4th question would start at
    $0.75 spent and end at $1.00, past a $0.875 budget; the largest so far ($0.25) stops it."""
    monkeypatch.setattr(settings, "budget_usd", 0.875)
    run_id = execute(conn)
    assert len(runs.get_results(conn, run_id)) == 3
    assert spend.total(conn) == 0.75


def test_the_estimate_is_used_when_it_is_above_the_largest_so_far(conn, world):
    """Each question costs $0.125 but is estimated at $0.25: the run stops once $0.25 more could pass $1, at
    $0.875 spent, where the largest so far ($0.125) alone would allow one more."""
    world.update(cost=0.125, guess=0.25)
    run_id = execute(conn)
    assert len(runs.get_results(conn, run_id)) == 7
    assert spend.total(conn) == 0.875


def test_spend_outside_the_run_counts_while_it_runs(conn, world):
    """One budget for every run (D15): spend recorded before the run leaves room for no question."""
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    spent_elsewhere(conn, 0.875 + 2 ** -10)
    with pytest.raises(pipeline.BudgetExceeded):
        pipeline.execute(conn, run_id, retrieve)
    assert world["answered"] == []
    assert runs.get_run(conn, run_id).status == "failed"


def test_a_chunk_set_missing_at_execute_marks_the_run_failed(conn, world, monkeypatch):
    """Otherwise the run would stay "running" for ever."""
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    monkeypatch.setattr(pipeline, "load_chunk_set", lambda set_id: (_ for _ in ()).throw(FileNotFoundError(set_id)))
    with pytest.raises(FileNotFoundError):
        pipeline.execute(conn, run_id, retrieve)
    assert runs.get_run(conn, run_id).status == "failed"


def test_each_guess_uses_the_run_settings_and_the_mean_chunk_length(conn, world, monkeypatch):
    """Mean of 100, 200 and 600 tokens = 300."""
    world["cost"] = 0.0
    choices = pipeline.Choices(stack="B", chunk_set_id=CHOICES.chunk_set_id, top_k=4, hybrid=False,
                               openai_ranking=None, rerank=True, answer_model="openai/gpt-4.1-mini",
                               prompt_name="default")
    monkeypatch.setattr(pipeline, "rerank", lambda question, hits, k: Reranked(hits[:k], None, repaired=False))
    pipeline.execute(conn, pipeline.start_run(conn, choices, DEV[:2]), retrieve)
    assert world["guess_args"] == [(t.id, "default", "openai/gpt-4.1-mini", 4, True, 300.0) for t in DEV[:2]]
