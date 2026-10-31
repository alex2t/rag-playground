"""Running one ladder step (T50): a real worker thread and database, fake models, chunks and stacks (no network, no cost).
Questions are cut to 2 answerable and 1 unanswerable by faking the dev list, so each run stores 3 results."""

import sqlite3
import threading
from types import SimpleNamespace

import pytest

from rag_playground import jobs, store
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.datasets.schema import load_tests
from rag_playground.llm.models import ModelInfo
from rag_playground.llm.openrouter import ChatResult, paid
from rag_playground.rag import best_run, enrich_run, estimate, ladder, ladder_step, pipeline, prompts, runs
from rag_playground.rag.ladder import baseline, options
from rag_playground.rag.ladder_runs import choices
from rag_playground.scoring.judging import Judgement
from rag_playground.scoring.selection import Candidate
from rag_playground.settings import LADDER_SIZES, S0, settings
from rag_playground.stacks import indexes
from rag_playground.stacks.hits import Hit

ALL_DEV = [t for t in load_tests() if t.split == "dev"]
DEV = [t for t in ALL_DEV if t.source_docs][:2] + [t for t in ALL_DEV if not t.source_docs][:1]
IDS = sorted(t.id for t in DEV)
CHUNK = Chunk(chunk_id="d.md#0", source="d.md", doc_type="d", index=0, text="x", tokens=100, start=0, end=1)
VERDICT = Judgement(refused=False, accuracy=5, completeness=5, relevance=5, faithfulness=5, feedback="ok",
                    faithfulness_feedback="ok")
GOLD_CHUNKS = [CHUNK.model_copy(update={"source": source}) for t in DEV for source in t.source_docs]
BASE = baseline("default")
S1_NEW = [c for c in options("S1", BASE, ()) if c != BASE]


def call(cost: float) -> ChatResult:
    return ChatResult(text="An answer.", model="m", canonical_slug="m-1", temperature_controlled=True,
                      prompt_tokens=1, completion_tokens=1, reasoning_tokens=0, cost_usd=cost)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Fresh var/ folder, $1 budget, one worker thread. `state` records what the fakes were asked to do."""
    state = SimpleNamespace(built=[], enriched=[], gate=None, fail_at=None, questions=0, enrich_cost=0.0,
                            scores=None)
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    monkeypatch.setattr(settings, "budget_usd", 1.0)
    monkeypatch.setattr(jobs, "executor", jobs.new_executor())
    info = lambda m: ModelInfo(m, "judge-1" if m.startswith("google") else f"{m}-1", frozenset({"temperature"}),
                               1e-6, 1e-6)
    for module in (pipeline, estimate, best_run):
        monkeypatch.setattr(module, "model_info", info)
    monkeypatch.setattr(pipeline, "load_tests", lambda: DEV)
    monkeypatch.setattr(ladder_step, "dev_tests", lambda: DEV)
    monkeypatch.setattr(best_run, "load_tests", lambda: DEV)
    monkeypatch.setattr(best_run, "load_chunk_set", lambda set_id: GOLD_CHUNKS)
    monkeypatch.setattr(pipeline, "load_chunk_set", lambda set_id: [CHUNK])
    monkeypatch.setattr(ladder_step, "load_or_build", lambda size, overlap: [CHUNK])
    monkeypatch.setattr(indexes, "load_chunk_set", lambda set_id: [CHUNK])
    monkeypatch.setattr(indexes.enrichment, "load_complete", lambda set_id: [CHUNK])
    monkeypatch.setattr(enrich_run, "remaining_cost", lambda base_id: state.enrich_cost)
    monkeypatch.setattr(enrich_run, "enrich_set", lambda conn, base_id: state.enriched.append(base_id))

    def build_b(set_id, chunks):
        state.built.append(("B", set_id))
        return set_id

    def build_a(set_id, chunks):
        state.built.append(("A", set_id))
        return f"vs_{set_id}"

    monkeypatch.setattr(indexes, "build_stack_a", build_a)
    monkeypatch.setattr(indexes, "build_stack_b", build_b)
    monkeypatch.setattr(indexes.qdrant_store, "client", lambda: "qdrant")
    monkeypatch.setattr(indexes.qdrant_store, "search", lambda q, name, question, k, hybrid:
                        [Hit(f"c{i}", DEV[0].source_docs[0] if DEV[0].source_docs else "d.md", 1.0, "t")
                         for i in range(k)])

    def answer(model, prompt, question, hits):
        state.questions += 1
        if state.gate is not None:
            state.gate.wait(5)
        if state.fail_at == state.questions:
            raise RuntimeError("rate limited")
        return paid(call(0.001))

    monkeypatch.setattr(pipeline, "answer", answer)
    monkeypatch.setattr(pipeline, "judge", lambda test, context, text: (VERDICT, [paid(call(0.0005))]))
    state.conn = store.connect()
    yield state
    jobs.executor.shutdown(wait=True)
    state.conn.close()


def finish(world) -> None:
    """Wait for the queued jobs."""
    jobs.executor.submit(lambda: None).result(30)


def test_the_ladder_uses_every_dev_question_and_no_held_out_one():
    """On the real dataset, outside the `world` fixture, which cuts the list down."""
    tests = ladder_step.dev_tests()
    assert len(tests) == 192
    assert {t.split for t in tests} == {"dev"}


def run_ids(world) -> list[int]:
    return [row["id"] for row in world.conn.execute("SELECT id FROM runs ORDER BY id")]


def test_the_first_step_runs_s0_and_builds_its_index(world):
    job_id = jobs.submit_step(world.conn, "B")
    finish(world)
    job = jobs.get_job(world.conn, job_id)
    assert (job.kind, job.status, job.progress, job.error) == ("ladder_step", "done", 1.0, None)
    assert world.built == [("B", "fixed__c1024__o200")]
    run = runs.get_run(world.conn, run_ids(world)[0])
    assert (run.status, run.meta.stack, run.meta.split, sorted(run.meta.test_ids)) == ("done", "B", "dev", IDS)


def test_a_finished_step_moves_the_ladder_on(world):
    jobs.submit_step(world.conn, "B")
    finish(world)
    now = ladder_step.progress(world.conn, "B")
    assert now.next_step == "S1"
    assert len(now.missing) == len(LADDER_SIZES) - 1


def test_a_step_runs_each_missing_configuration_once_with_its_own_index(world):
    jobs.submit_step(world.conn, "B")
    finish(world)
    job_id = jobs.submit_step(world.conn, "B")
    finish(world)
    made = [runs.get_run(world.conn, i).meta for i in run_ids(world)[1:]]
    assert [m.chunk_set_id for m in made] == [choices("B", c).chunk_set_id for c in S1_NEW]
    assert world.built[1:] == [("B", m.chunk_set_id) for m in made]
    assert jobs.get_job(world.conn, job_id).run_id == run_ids(world)[-1]


def test_stack_a_runs_with_its_own_default_search(world, monkeypatch):
    monkeypatch.setattr(indexes.openai_vector_store, "search", lambda *a, **k: [Hit("c", "d.md", 1.0, "t")] * 2)
    jobs.submit_step(world.conn, "A")
    finish(world)
    run = runs.get_run(world.conn, run_ids(world)[0])
    assert (run.status, run.meta.openai_ranking) == ("done", S0["search"]["A"]["openai_ranking"])


def test_an_existing_index_is_not_built_again(world):
    indexes.insert(world.conn, "indexes", {"stack": "B", "chunk_set_id": "fixed__c1024__o200",
                                           "ref": "fixed__c1024__o200", "chunk_count": 1})
    jobs.submit_step(world.conn, "B")
    finish(world)
    assert world.built == []


def test_a_failure_after_the_run_starts_but_before_its_questions_closes_the_run(world, monkeypatch):
    """Nothing else would close it: recovery only looks at unfinished jobs."""
    def broken(conn, meta):
        raise FileNotFoundError("chunk set is gone")

    monkeypatch.setattr(indexes, "retriever", broken)
    job_id = jobs.submit_step(world.conn, "B")
    finish(world)
    assert jobs.get_job(world.conn, job_id).status == "failed"
    run = runs.get_run(world.conn, run_ids(world)[0])
    assert run.status == "failed" and "chunk set is gone" in run.error


def test_the_database_refuses_two_active_steps_on_one_stack(world):
    """Two clicks at the same moment can both pass the check in `submit_step`."""
    row = {"kind": "ladder_step", "stack": "B", "step": "S1", "runs_total": 1}
    jobs.insert(world.conn, "jobs", row)
    with pytest.raises(sqlite3.IntegrityError):
        jobs.insert(world.conn, "jobs", row)
    jobs.insert(world.conn, "jobs", {**row, "stack": "A"})


def test_a_finished_step_does_not_block_the_next_one(world):
    jobs.submit_step(world.conn, "B")
    finish(world)
    jobs.submit_step(world.conn, "B")
    finish(world)
    assert world.conn.execute("SELECT count(*) FROM jobs WHERE status = 'done'").fetchone()[0] == 2


def test_a_second_click_while_a_step_runs_is_refused(world):
    """A second click would pay for the same runs twice."""
    world.gate = threading.Event()
    jobs.submit_step(world.conn, "B")
    with pytest.raises(ValueError, match="already running"):
        jobs.submit_step(world.conn, "B")
    world.gate.set()
    finish(world)
    assert len(run_ids(world)) == 1


def test_a_failed_step_keeps_finished_runs_and_a_new_click_pays_only_for_the_rest(world):
    jobs.submit_step(world.conn, "B")
    finish(world)
    world.fail_at = world.questions + len(DEV) + 2  # second S1 run, second question
    failed_job = jobs.submit_step(world.conn, "B")
    finish(world)
    job = jobs.get_job(world.conn, failed_job)
    assert job.status == "failed" and "rate limited" in job.error
    assert [runs.get_run(world.conn, i).status for i in run_ids(world)] == ["done", "done", "failed"]
    missing = ladder_step.progress(world.conn, "B").missing
    assert missing == S1_NEW[1:]
    world.fail_at = None
    jobs.submit_step(world.conn, "B")
    finish(world)
    assert len(run_ids(world)) == 3 + len(missing)


def test_a_step_over_the_budget_is_refused_with_nothing_stored(world, monkeypatch):
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    with pytest.raises(pipeline.BudgetExceeded, match="The step is estimated"):
        jobs.submit_step(world.conn, "B")
    assert run_ids(world) == []
    assert world.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_the_estimate_adds_every_missing_run_and_the_enrichment(world):
    """Two runs at their own estimates, plus the enrichment once for the one enriched configuration."""
    world.enrich_cost = 0.25
    enriched = options("S4", BASE, ())[1]
    prompts.ensure_default(world.conn)
    single = ladder_step.run_cost(world.conn, BASE)
    assert single > 0
    assert ladder_step.step_cost(world.conn, [BASE, enriched]) == pytest.approx(2 * single + 0.25)


def test_a_step_over_the_budget_counts_the_enrichment(world, monkeypatch):
    prompts.ensure_default(world.conn)
    world.enrich_cost = 2.0
    with pytest.raises(pipeline.BudgetExceeded):
        ladder_step.check_budget(world.conn, [options("S4", BASE, ())[1]])


def test_an_enriched_configuration_is_enriched_before_it_is_indexed(world, monkeypatch):
    order = []
    monkeypatch.setattr(enrich_run, "enrich_set", lambda conn, base_id: order.append(("enrich", base_id)))
    monkeypatch.setattr(indexes, "build", lambda conn, stack, set_id: order.append(("index", set_id)))
    ladder_step.prepare(world.conn, "B", options("S4", BASE, ())[1])
    assert order == [("enrich", "fixed__c1024__o200"), ("index", "llm_enriched__c1024__o200")]


def test_a_fixed_configuration_is_never_enriched(world):
    ladder_step.prepare(world.conn, "B", BASE)
    assert world.enriched == []


def at_s6(world, monkeypatch, stack: str = "B"):
    """Make every configuration before S6 count as finished."""
    def result(config):
        if config.prompt_name != "default" or config.answer_model != BASE.answer_model:
            return None
        scores = {"mrr": 1.0, "recall": 1.0, "faithfulness": 5.0, "correct_refusal_rate": 1.0}
        return Candidate(hash(config), scores, {"q": 3.0}, 0.001, {"q": 1.0})

    monkeypatch.setattr(ladder_step.ladder_runs, "finder", lambda conn, s: result)
    assert ladder.walk(result, "default").next_step == "S6"


def test_s6_is_refused_until_the_prompts_are_chosen(world, monkeypatch):
    at_s6(world, monkeypatch)
    with pytest.raises(ValueError, match="Choose the prompt versions"):
        jobs.submit_step(world.conn, "B")


def test_s6_saves_the_choice_and_runs_those_versions(world, monkeypatch):
    at_s6(world, monkeypatch)
    prompts.ensure_default(world.conn)
    prompts.save(world.conn, "v2", "Other text.")
    jobs.submit_step(world.conn, "B", ("v2",))
    finish(world)
    assert ladder_step.chosen_prompts(world.conn, "B") == ("v2",)
    assert runs.get_run(world.conn, run_ids(world)[0]).meta.prompt_name == "v2"


def test_a_saved_s6_choice_resumes_without_being_given_again(world, monkeypatch):
    """After a failed S6 the next click sends no prompts: the saved ones are still the step's, and a new list is ignored."""
    at_s6(world, monkeypatch)
    prompts.ensure_default(world.conn)
    prompts.save(world.conn, "v2", "Other text.")
    prompts.save(world.conn, "v3", "Third text.")
    world.conn.execute("INSERT INTO ladder_prompts VALUES ('B', '[\"v2\"]')")
    for sent in (None, ("v3",)):
        now = ladder_step.next_step(world.conn, "B", sent)
        assert (now.next_step, [c.prompt_name for c in now.missing]) == ("S6", ["v2"])


def test_s6_with_no_extra_version_goes_on_to_s7(world, monkeypatch):
    at_s6(world, monkeypatch)
    assert ladder_step.next_step(world.conn, "B", ()).next_step == "S7"


def test_s6_refused_by_the_budget_stores_no_choice_so_the_user_can_choose_again(world, monkeypatch):
    at_s6(world, monkeypatch)
    prompts.ensure_default(world.conn)
    prompts.save(world.conn, "v2", "Other text.")
    budget = settings.budget_usd
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    with pytest.raises(pipeline.BudgetExceeded):
        jobs.submit_step(world.conn, "B", ("v2",))
    assert ladder_step.chosen_prompts(world.conn, "B") is None
    monkeypatch.setattr(settings, "budget_usd", budget)
    assert ladder_step.next_step(world.conn, "B", ()).next_step == "S7"
    assert ladder_step.chosen_prompts(world.conn, "B") == ()


def test_an_unknown_prompt_version_stores_no_choice(world, monkeypatch):
    at_s6(world, monkeypatch)
    with pytest.raises(KeyError):
        jobs.submit_step(world.conn, "B", ("missing",))
    assert ladder_step.chosen_prompts(world.conn, "B") is None


def test_more_than_four_versions_store_no_choice(world, monkeypatch):
    at_s6(world, monkeypatch)
    with pytest.raises(ValueError, match="at most 4"):
        jobs.submit_step(world.conn, "B", ("a", "b", "c", "d", "e"))
    assert ladder_step.chosen_prompts(world.conn, "B") is None


def test_the_choice_of_prompts_is_final_in_the_database(world):
    jobs.insert(world.conn, "ladder_prompts", {"stack": "B", "names": "[]"})
    for sql in ("INSERT INTO ladder_prompts VALUES ('B', '[]')", "INSERT OR REPLACE INTO ladder_prompts VALUES ('B', '[]')",
                "UPDATE ladder_prompts SET names = '[\"x\"]'", "DELETE FROM ladder_prompts"):
        with pytest.raises(sqlite3.IntegrityError):
            world.conn.execute(sql)


def test_a_finished_ladder_is_refused(world, monkeypatch):
    monkeypatch.setattr(ladder_step, "progress", lambda conn, stack: SimpleNamespace(next_step=None, missing=[]))
    with pytest.raises(ValueError, match="finished"):
        jobs.submit_step(world.conn, "B")


def step_row(done: int, total: int = 5) -> dict:
    return {"id": 1, "kind": "ladder_step", "status": "running", "run_id": 9, "stack": "B", "step": "S1",
            "runs_total": total, "runs_done": done, "error": None}


def test_progress_counts_finished_runs_and_the_current_questions():
    """2 of 5 runs finished and 1 of 3 questions of the third: (2 + 1/3) / 5."""
    job = jobs.step_job(step_row(2), {"status": "running", "done": 1, "test_ids": '["a", "b", "c"]'})
    assert job.progress == pytest.approx((2 + 1 / 3) / 5)
    assert job.message == "S1 on Stack B: run 3 of 5, 1 of 3 questions"


def test_a_run_just_finished_is_not_counted_twice():
    """The job has counted the run, and still points at it until the next one starts."""
    job = jobs.step_job(step_row(1), {"status": "done", "done": 3, "test_ids": '["a", "b", "c"]'})
    assert job.progress == pytest.approx(1 / 5)


def test_a_finished_step_reports_complete(world):
    job_id = jobs.submit_step(world.conn, "B")
    finish(world)
    assert jobs.get_job(world.conn, job_id).progress == 1.0


def test_a_step_job_before_its_first_run_says_it_is_preparing(world):
    job_id = jobs.insert(world.conn, "jobs", {"kind": "ladder_step", "stack": "B", "step": "S1", "runs_total": 5})
    job = jobs.get_job(world.conn, job_id)
    assert (job.run_id, job.progress, job.message) == (None, 0.0, "S1 on Stack B: preparing")


def test_an_interrupted_step_is_marked_failed_at_startup(world):
    """Also before its first run started, when it has no run to close."""
    prompts.ensure_default(world.conn)
    waiting = jobs.insert(world.conn, "jobs", {"kind": "ladder_step", "stack": "B", "step": "S1", "runs_total": 5})
    assert jobs.recover_interrupted(world.conn) == 1
    job = jobs.get_job(world.conn, waiting)
    assert (job.status, job.error) == ("failed", jobs.INTERRUPTED)


@pytest.mark.parametrize("row", [
    {"kind": "ladder_step", "stack": "B", "step": "S1"}, {"kind": "ladder_step", "step": "S1", "runs_total": 1},
    {"kind": "ladder_step", "stack": "B", "runs_total": 1}, {"kind": "evaluate"},
    {"kind": "ladder_step", "stack": "C", "step": "S1", "runs_total": 1},
    {"kind": "ladder_step", "stack": "B", "step": "S1", "runs_total": 0}])
def test_the_database_refuses_incomplete_jobs(world, row):
    with pytest.raises(sqlite3.IntegrityError):
        jobs.insert(world.conn, "jobs", row)
