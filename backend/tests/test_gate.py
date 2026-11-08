"""Offline tests of the evaluation gate (D36): real runs, scoring and gates on a fresh database and chunk-set folder,
with fake stacks, models and prices (no network, no cost)."""

import importlib.util

import pytest

from rag_playground import store
from rag_playground.datasets.schema import Category, load_tests
from rag_playground.datasets.splits import round_robin
from rag_playground.llm.models import ModelInfo
from rag_playground.llm.openrouter import ChatResult, paid
from rag_playground.rag import estimate, gate, pipeline, runs
from rag_playground.run_requests import RunRequest, smoke_tests
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import GATE_STACK_A_INDEXES, GATES, REPO_ROOT, settings
from rag_playground.stacks import indexes, openai_vector_store, qdrant_store
from rag_playground.stacks.hits import Hit

spec = importlib.util.spec_from_file_location("eval_gate", REPO_ROOT / "backend" / "scripts" / "eval_gate.py")
eval_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_gate)

S0_SET = "fixed__c1024__o200"
S0_CHUNKS = 51


def smoke_ids() -> list[str]:
    """The smoke set by its definition: the first 20 dev questions in round-robin order over the categories (T46)."""
    return [t.id for t in round_robin([t for t in load_tests() if t.split == "dev"], 20)]


def call() -> ChatResult:
    return ChatResult(text="An answer.", model="m", canonical_slug="m-1", temperature_controlled=True,
                      prompt_tokens=100, completion_tokens=10, reasoning_tokens=0, cost_usd=0.0001)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Fresh var/ folder, budget $1, fake prices, stacks that return each question's gold documents, a judge that
    refuses exactly the unanswerable questions (and any in "refuse_ids") and scores 5. Tests change `world` to break
    one part."""
    by_question = {t.question: t for t in load_tests()}
    seen = {"created": [], "searched": [], "faithfulness": 5, "refuses": True, "wrong_docs": set(), "completed": S0_CHUNKS,
            "accuracy": 5, "refuse_ids": set()}
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    monkeypatch.setattr(settings, "budget_usd", 1.0)
    info = lambda m: ModelInfo(m, f"{m}-1", frozenset({"temperature"}), 1e-6, 1e-6)
    monkeypatch.setattr(pipeline, "model_info", info)
    monkeypatch.setattr(estimate, "model_info", info)
    monkeypatch.setattr(openai_vector_store, "create_store", lambda name: seen["created"].append(("A", name)) or "vs_new")
    monkeypatch.setattr(openai_vector_store, "completed_files", lambda store_id: seen["completed"])
    monkeypatch.setattr(qdrant_store, "client", lambda: "qdrant")
    monkeypatch.setattr(qdrant_store, "index_chunks",
                        lambda q, name, chunks: seen["created"].append(("B", name)) or len(chunks))

    def hits(stack: str, question: str, k: int) -> list[Hit]:
        test = by_question[question]
        docs = ["other.md"] * k if stack in seen["wrong_docs"] or not test.source_docs else test.source_docs[:k]
        return [Hit(f"{doc}#0", doc, 1.0, "text") for doc in docs]

    monkeypatch.setattr(openai_vector_store, "search",
                        lambda sid, question, k, ranking: seen["searched"].append(("A", sid)) or hits("A", question, k))
    monkeypatch.setattr(qdrant_store, "search",
                        lambda q, name, question, k, hybrid: seen["searched"].append(("B", name)) or hits("B", question, k))
    monkeypatch.setattr(pipeline, "answer", lambda model, prompt, question, h: paid(call()))

    def judge(test, context, text):
        refused = (seen["refuses"] and test.category == Category.UNANSWERABLE) or test.id in seen["refuse_ids"]
        verdict = Judgement(refused=refused, accuracy=seen["accuracy"], completeness=5, relevance=5,
                            faithfulness=seen["faithfulness"], feedback="ok", faithfulness_feedback="ok")
        return verdict, [paid(call()), paid(call())]

    monkeypatch.setattr(pipeline, "judge", judge)
    return seen


def test_a_healthy_version_passes_on_both_stacks(world, capsys):
    assert eval_gate.main() == 0
    out = capsys.readouterr().out
    assert "Stack A: run 1, 20 questions: PASS" in out and "Stack B: run 2, 20 questions: PASS" in out


def test_stack_a_reuses_the_existing_index_and_stack_b_builds_its_own(world):
    """A new OpenAI index would be paid for on every gate run; Qdrant on the runner starts empty."""
    eval_gate.main()
    assert world["created"] == [("B", S0_SET)]
    assert {s for s in world["searched"] if s[0] == "A"} == {("A", GATE_STACK_A_INDEXES[S0_SET])}
    assert {s for s in world["searched"] if s[0] == "B"} == {("B", S0_SET)}


def test_a_second_gate_run_reuses_the_indexes_it_already_has(world, capsys):
    """On a database that already holds the indexes (a re-run, or a local database), nothing is built or
    registered again."""
    assert eval_gate.main() == 0
    assert eval_gate.main() == 0
    assert world["created"] == [("B", S0_SET)]
    assert "Stack A: run 3, 20 questions: PASS" in capsys.readouterr().out


def test_the_gate_asks_the_smoke_questions_at_s0(world):
    eval_gate.main()
    conn = store.connect()
    smoke = smoke_ids()
    for stack in ("A", "B"):
        meta = runs.get_run(conn, 1 if stack == "A" else 2).meta
        assert (meta.stack, meta.test_ids, meta.chunk_set_id, meta.top_k, meta.answer_model, meta.prompt_name) == (
            stack, smoke, S0_SET, 2, "openai/gpt-4.1-nano", "default")


def test_the_smoke_set_is_the_one_evaluate_uses():
    request = RunRequest.model_validate({"stack": "B", "chunking_method": "fixed", "chunk_size": 1024, "overlap": 200,
                                         "top_k": 2, "rerank": False, "answer_model": "openai/gpt-4.1-nano",
                                         "prompt_name": "default", "hybrid": False, "questions": "smoke"})
    assert [t.id for t in request.tests()] == [t.id for t in smoke_tests()] == smoke_ids()


def test_invented_facts_fail_the_faithfulness_gate(world, capsys):
    world["faithfulness"] = 2
    assert eval_gate.main() == 1
    out = capsys.readouterr().out
    assert "Stack A: run 1, 20 questions: FAIL (faithfulness)" in out
    assert "Stack B: run 2, 20 questions: FAIL (faithfulness)" in out


def test_wrong_documents_fail_the_retrieval_gates(world, capsys):
    world["wrong_docs"] = {"A", "B"}
    assert eval_gate.main() == 1
    assert "FAIL (mrr, recall)" in capsys.readouterr().out


def test_answering_unanswerable_questions_fails_the_refusal_gate(world, capsys):
    world["refuses"] = False
    assert eval_gate.main() == 1
    assert "FAIL (correct_refusal_rate)" in capsys.readouterr().out


def test_one_failing_stack_fails_the_gate(world, capsys):
    world["wrong_docs"] = {"A"}
    assert eval_gate.main() == 1
    out = capsys.readouterr().out
    assert "Stack A: run 1, 20 questions: FAIL (mrr, recall)" in out and "Stack B: run 2, 20 questions: PASS" in out


def test_an_incomplete_stack_a_index_is_refused_before_any_paid_call(world):
    world["completed"] = S0_CHUNKS - 1
    with pytest.raises(ValueError, match="holds 50 indexed files"):
        eval_gate.main()
    conn = store.connect()
    assert indexes.lookup(conn, "A", S0_SET) is None
    assert conn.execute("SELECT count(*) FROM spend").fetchone()[0] == 0


def test_no_budget_stops_the_gate_before_any_paid_call(world, monkeypatch):
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    with pytest.raises(pipeline.BudgetExceeded):
        eval_gate.main()
    assert store.connect().execute("SELECT count(*) FROM spend").fetchone()[0] == 0


def answerable_smoke_ids() -> list[str]:
    tests = {t.id: t for t in load_tests()}
    return [i for i in smoke_ids() if tests[i].category != Category.UNANSWERABLE]


def test_a_prompt_that_refuses_everything_fails_on_accuracy_and_false_refusals(world, capsys):
    """It passes every T08 gate (nothing invented, unanswerable questions refused): the gate's own limits catch it."""
    world["refuse_ids"] = set(answerable_smoke_ids())
    world["accuracy"] = 1
    assert eval_gate.main() == 1
    assert "Stack A: run 1, 20 questions: FAIL (accuracy, false_refusal_rate)" in capsys.readouterr().out


def test_wrong_answers_fail_on_accuracy(world, capsys):
    world["accuracy"] = 3
    assert eval_gate.main() == 1
    assert "Stack B: run 2, 20 questions: FAIL (accuracy)" in capsys.readouterr().out


@pytest.mark.parametrize(("refused", "expected"), [(4, 0), (5, 1)])
def test_four_false_refusals_of_18_pass_and_five_fail(world, capsys, refused, expected):
    world["refuse_ids"] = set(answerable_smoke_ids()[:refused])
    assert len(answerable_smoke_ids()) == 18
    assert eval_gate.main() == expected


def passing_scores() -> dict:
    return {name: minimum for name, minimum in GATES.items()} | {"accuracy": 3.5, "false_refusal_rate": 0.25}


def test_the_gate_s_own_limits_are_inclusive():
    """Accuracy 3.5 and false refusals 0.25 pass; just beyond either fails."""
    assert gate.failures({"failed_gates": [], "scores": passing_scores()}) == []
    assert gate.failures({"failed_gates": [], "scores": passing_scores() | {"accuracy": 3.49}}) == ["accuracy"]
    assert gate.failures({"failed_gates": [], "scores": passing_scores() | {"false_refusal_rate": 0.26}}) == [
        "false_refusal_rate"]


def test_t08_failures_come_first_then_the_gate_s_own():
    scores = passing_scores() | {"accuracy": 1.0, "false_refusal_rate": 1.0}
    assert gate.failures({"failed_gates": ["mrr"], "scores": scores}) == ["mrr", "accuracy", "false_refusal_rate"]

