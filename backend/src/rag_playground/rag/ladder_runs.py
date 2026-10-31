"""Connect the ladder to stored runs: a ladder configuration on a stack becomes run settings, and a stored run."""

import json
import sqlite3
from collections.abc import Callable

from rag_playground.chunking.chunk_sets import METHOD as FIXED_METHOD
from rag_playground.chunking.chunk_sets import chunk_set_id
from rag_playground.chunking.enrichment import enriched_set_id
from rag_playground.rag import best_run, runs
from rag_playground.rag.ladder import Config
from rag_playground.rag.pipeline import Choices
from rag_playground.scoring.selection import Candidate
from rag_playground.settings import S0


def choices(stack: str, config: Config) -> Choices:
    """The run settings of a ladder configuration. Each stack keeps its own default search (T40 revision)."""
    search = S0["search"][stack]
    base = chunk_set_id(config.chunk_size, config.overlap)
    return Choices(stack=stack, chunk_set_id=base if config.method == FIXED_METHOD else enriched_set_id(base),
                   top_k=config.top_k, hybrid=search["hybrid"], openai_ranking=search["openai_ranking"],
                   rerank=config.rerank, answer_model=config.answer_model, prompt_name=config.prompt_name)


def settings_key(stack: str, set_id: str, top_k: int, hybrid: bool, ranking: dict | None, rerank: bool, model: str,
                 prompt_name: str) -> tuple:
    return stack, set_id, top_k, hybrid, json.dumps(ranking, sort_keys=True), rerank, model, prompt_name


def finder(conn: sqlite3.Connection, stack: str) -> Callable[[Config], Candidate | None]:
    """A lookup from configuration to its stored run, for `ladder.walk`. Only runs that may compete count (T08). The
    oldest match wins, so a later run with the same settings cannot change a past ladder decision."""
    stored = {}
    for candidate in best_run.candidates(conn):
        meta = runs.get_run(conn, candidate.run_id).meta
        stored.setdefault(settings_key(meta.stack, meta.chunk_set_id, meta.top_k, meta.hybrid, meta.openai_ranking,
                                       meta.rerank_model is not None, meta.answer_model, meta.prompt_name), candidate)

    def result(config: Config) -> Candidate | None:
        c = choices(stack, config)
        return stored.get(settings_key(c.stack, c.chunk_set_id, c.top_k, c.hybrid, c.openai_ranking, c.rerank,
                                       c.answer_model, c.prompt_name))

    return result
