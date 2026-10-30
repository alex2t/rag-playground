"""Real S0 runs: 10 dev questions (Step 6 check), or every dev question (Step 8, for the judge calibration), on one or
both stacks. Builds the S0 index on a stack if it is missing, runs the questions, and prints the estimate against the
recorded spend.

Paid: OpenRouter (answers and judge), and on Stack A the OpenAI index build and searches. Run by the user.
Usage: uv run python scripts/first_run.py A|B|both [batch|full]
Batch 1 (default) is the first 10 questions in round-robin order (T46), batch 2 the next 10, and so on, so a later
batch checks the estimate on questions it was not fitted to. "full" asks all 192 dev questions, and with "both" ends
by printing the command that grades them.
"""

import sys

from rag_playground import store
from rag_playground.chunking.chunk_sets import chunk_set_id, load_or_build
from rag_playground.datasets.schema import load_tests
from rag_playground.datasets.splits import round_robin
from rag_playground.rag import estimate, pipeline, prompts, runs, spend
from rag_playground.settings import S0, settings
from rag_playground.stacks import indexes

QUESTIONS = 10


def s0_choices(stack: str) -> pipeline.Choices:
    search = S0["search"][stack]
    return pipeline.Choices(stack=stack, chunk_set_id=chunk_set_id(S0["chunk_size"], S0["overlap"]),
                            top_k=S0["top_k"], hybrid=search["hybrid"], openai_ranking=search["openai_ranking"],
                            rerank=S0["rerank"], answer_model=S0["answer_model"], prompt_name=prompts.DEFAULT_NAME)


def batch_questions(batch: int) -> list:
    """Questions (batch - 1) * 10 + 1 to batch * 10 of the dev set in round-robin order."""
    return round_robin(all_dev_questions(), batch * QUESTIONS)[(batch - 1) * QUESTIONS:]


def all_dev_questions() -> list:
    return [t for t in load_tests() if t.split == "dev"]


def spend_by_model(conn, run_id: int) -> list[tuple]:
    return [tuple(row) for row in conn.execute(
        "SELECT model, count(*), sum(prompt_tokens), sum(completion_tokens), sum(reasoning_tokens), sum(cost_usd) "
        "FROM spend WHERE run_id = ? GROUP BY model ORDER BY model", (run_id,))]


def run_stack(conn, stack: str, tests: list) -> int:
    choices = s0_choices(stack)
    chunks = load_or_build(S0["chunk_size"], S0["overlap"])
    if indexes.lookup(conn, stack, choices.chunk_set_id) is None:
        print(f"Stack {stack}: indexing {choices.chunk_set_id} ...", flush=True)
        indexes.build(conn, stack, choices.chunk_set_id)
    guess = estimate.run_cost(tests, prompts.get(conn, choices.prompt_name), choices.answer_model, choices.top_k,
                              choices.rerank, chunks)
    run_id = pipeline.start_run(conn, choices, tests)
    print(f"Stack {stack}: run {run_id}, {len(tests)} questions, estimate ${guess:.4f}", flush=True)
    pipeline.execute(conn, run_id, indexes.retriever(conn, runs.get_run(conn, run_id).meta))
    actual = spend.total(conn, run_id)
    print(f"Stack {stack}: run {run_id} {runs.get_run(conn, run_id).status}; recorded spend ${actual:.4f}; "
          f"actual / estimate = {actual / guess:.2f}")
    for model, calls, prompt_tokens, completion_tokens, reasoning_tokens, cost in spend_by_model(conn, run_id):
        print(f"  {model}: {calls} calls, {prompt_tokens} in, {completion_tokens} out "
              f"({reasoning_tokens} reasoning), ${cost:.4f}")
    return run_id


def main(which: str, batch: str = "1") -> None:
    stacks = {"A": ["A"], "B": ["B"], "both": ["A", "B"]}[which]
    conn = store.connect()
    prompts.ensure_default(conn)
    tests = all_dev_questions() if batch == "full" else batch_questions(int(batch))
    print(f"BUDGET_USD ${settings.budget_usd:.2f}, ${pipeline.remaining(conn):.4f} left; questions: "
          f"{', '.join(t.id for t in tests)}")
    run_ids = [run_stack(conn, stack, tests) for stack in stacks]
    if batch == "full" and which == "both":
        print(f"Grade the sample with: uv run python scripts/grade.py {run_ids[0]} {run_ids[1]}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "1")
