"""First real run (Step 6 check): 10 dev questions with the S0 set-up, on one or both stacks. Builds the S0 index
on a stack if it is missing, runs the questions, and prints the estimate against the recorded spend.

Paid: OpenRouter (answers and judge), and on Stack A the OpenAI index build and searches. Run by the user.
Usage: uv run python scripts/first_run.py A|B|both
"""

import sys
from dataclasses import asdict

from rag_playground import store
from rag_playground.chunking.chunk_sets import chunk_set_id, load_or_build
from rag_playground.datasets.schema import load_tests
from rag_playground.datasets.splits import round_robin
from rag_playground.rag import estimate, pipeline, prompts, runs, spend
from rag_playground.settings import S0, settings
from rag_playground.stacks import indexes
from rag_playground.stacks.openai_vector_store import hybrid_ranking

QUESTIONS = 10


def s0_choices(stack: str) -> pipeline.Choices:
    ranking = asdict(hybrid_ranking(S0["hybrid"])) if stack == "A" else None
    return pipeline.Choices(stack=stack, chunk_set_id=chunk_set_id(S0["chunk_size"], S0["overlap"]),
                            top_k=S0["top_k"], hybrid=S0["hybrid"], openai_ranking=ranking, rerank=S0["rerank"],
                            answer_model=S0["answer_model"], prompt_name=prompts.DEFAULT_NAME)


def spend_by_model(conn, run_id: int) -> list[tuple]:
    return [tuple(row) for row in conn.execute(
        "SELECT model, count(*), sum(prompt_tokens), sum(completion_tokens), sum(reasoning_tokens), sum(cost_usd) "
        "FROM spend WHERE run_id = ? GROUP BY model ORDER BY model", (run_id,))]


def run_stack(conn, stack: str, tests: list) -> None:
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


def main(which: str) -> None:
    stacks = {"A": ["A"], "B": ["B"], "both": ["A", "B"]}[which]
    conn = store.connect()
    prompts.ensure_default(conn)
    tests = round_robin([t for t in load_tests() if t.split == "dev"], QUESTIONS)
    print(f"BUDGET_USD ${settings.budget_usd:.2f}, ${pipeline.remaining(conn):.4f} left; questions: "
          f"{', '.join(t.id for t in tests)}")
    for stack in stacks:
        run_stack(conn, stack, tests)


if __name__ == "__main__":
    main(sys.argv[1])
