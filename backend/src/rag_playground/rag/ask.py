"""One question outside any run, for the Ask page (T54): nothing is stored but what it cost."""

import sqlite3
from dataclasses import asdict
from statistics import fmean

from rag_playground.chunking.chunk_sets import load as load_chunk_set
from rag_playground.datasets.schema import TestCase
from rag_playground.rag import estimate, pipeline, prompts, spend
from rag_playground.rag.pipeline import Choices, Retrieve
from rag_playground.scoring.judging import judge
from rag_playground.settings import RERANK_CANDIDATES
from rag_playground.stacks import indexes
from rag_playground.stacks.hits import Hit


def paid_search(conn: sqlite3.Connection, stack: str, retrieve: Retrieve) -> Retrieve:
    """The search, its fee recorded as soon as it returns: a later failure still leaves it paid."""
    def search(question: str, k: int) -> list[Hit]:
        hits = retrieve(question, k)
        spend.record_search(conn, stack)
        return hits

    return search


def assumed_cost(choices: Choices, prompt: prompts.PromptVersion, question: str, test: TestCase | None) -> float:
    """The estimate (T43), with the judge only for a test question."""
    chunk_tokens = fmean(chunk.tokens for chunk in load_chunk_set(choices.chunk_set_id))
    settings = (prompt, choices.answer_model, choices.top_k, choices.rerank, chunk_tokens, choices.stack)
    return estimate.question_cost(test, *settings) if test else estimate.answer_cost(question, *settings)


def ask(conn: sqlite3.Connection, choices: Choices, question: str, test: TestCase | None = None) -> dict:
    """Search and answer `question` with `choices`; a test question is also judged. KeyError if the chunk set is not
    indexed or the prompt is unknown; BudgetExceeded, with nothing paid, if it could pass BUDGET_USD."""
    retrieve = indexes.retriever(conn, choices)
    prompts.ensure_default(conn)
    prompt = prompts.get(conn, choices.prompt_name)
    pipeline.check_budget(conn, assumed_cost(choices, prompt, question, test))
    with spend.recording(conn, None):
        done = pipeline.search_and_answer(question, choices.top_k, RERANK_CANDIDATES if choices.rerank else None,
                                          choices.answer_model, prompt, paid_search(conn, choices.stack, retrieve))
        verdict, judge_calls = judge(test, [hit.text for hit in done.hits], done.reply.text) if test else (None, [])
    gold = set(test.source_docs) if test else set()
    return {"answer": done.reply.text, "stack": choices.stack, "latency_s": done.latency_s,
            "cost_usd": sum(call.cost_usd for call in [*done.calls, *judge_calls]) + spend.search_fee(choices.stack),
            "temperature_controlled": done.reply.temperature_controlled, "rerank_repaired": done.repaired,
            "chunks": [{"rank": rank, "source": hit.source, "score": hit.score, "text": hit.text,
                        "gold": hit.source in gold} for rank, hit in enumerate(done.hits, 1)],
            "reference_answer": test.reference_answer if test else None,
            "gold_sources": sorted(gold), "judgement": asdict(verdict) if verdict else None}
