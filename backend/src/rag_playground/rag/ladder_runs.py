"""Connect the ladder to stored runs: a ladder configuration on a stack becomes run settings, and a stored run."""

import json
import sqlite3
from collections.abc import Callable

from rag_playground.chunking.enrichment import set_id_for
from rag_playground.rag import best_run, runs
from rag_playground.rag.ladder import Config
from rag_playground.rag.pipeline import Choices
from rag_playground.scoring.selection import Candidate
from rag_playground.settings import S0


def choices(stack: str, config: Config) -> Choices:
    """The run settings of a ladder configuration. Each stack keeps its own default search (T40 revision)."""
    search = S0["search"][stack]
    return Choices(stack=stack, chunk_set_id=set_id_for(config.method, config.chunk_size, config.overlap),
                   top_k=config.top_k, hybrid=search["hybrid"], openai_ranking=search["openai_ranking"],
                   rerank=config.rerank, answer_model=config.answer_model, prompt_name=config.prompt_name)


def settings_key(stack: str, set_id: str, top_k: int, hybrid: bool, ranking: dict | None, rerank: bool, model: str,
                 prompt_name: str) -> tuple:
    return stack, set_id, top_k, hybrid, json.dumps(ranking, sort_keys=True), rerank, model, prompt_name


def lookup(conn: sqlite3.Connection, stack: str, split: str) -> Callable[[Config], Candidate | None]:
    """From configuration to its stored run on a split. The oldest match wins, so a later run with the same settings
    cannot change a past result."""
    stored = {}
    for candidate in best_run.candidates(conn, split):
        meta = runs.get_run(conn, candidate.run_id).meta
        stored.setdefault(settings_key(meta.stack, meta.chunk_set_id, meta.top_k, meta.hybrid, meta.openai_ranking,
                                       meta.rerank_model is not None, meta.answer_model, meta.prompt_name), candidate)

    def result(config: Config) -> Candidate | None:
        c = choices(stack, config)
        return stored.get(settings_key(c.stack, c.chunk_set_id, c.top_k, c.hybrid, c.openai_ranking, c.rerank,
                                       c.answer_model, c.prompt_name))

    return result


def finder(conn: sqlite3.Connection, stack: str) -> Callable[[Config], Candidate | None]:
    """The dev runs, for `ladder.walk`. Only runs that may compete count (T08)."""
    return lookup(conn, stack, "dev")


def heldout_finder(conn: sqlite3.Connection, stack: str) -> Callable[[Config], Candidate | None]:
    """The held-out runs, which confirm a choice and never make one (T18)."""
    return lookup(conn, stack, "heldout")
