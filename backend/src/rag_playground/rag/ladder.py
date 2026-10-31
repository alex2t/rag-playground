"""The improvement ladder S0-S7 (plan.md 3.1) for one stack. Runs are permanent, so the ladder keeps no state of its
own: `walk` replays the steps over the stored results and stops at the first step with a run still missing (T50)."""

from collections.abc import Callable
from dataclasses import dataclass, replace

from rag_playground.chunking.chunk_sets import METHOD as FIXED_METHOD
from rag_playground.chunking.enrichment import METHOD as ENRICHED_METHOD
from rag_playground.scoring import selection
from rag_playground.scoring.selection import Candidate
from rag_playground.settings import (LADDER_MAX_PROMPTS, LADDER_OVERLAP_SHARES, LADDER_SIZES, LADDER_STRONG_MODEL,
                                     LADDER_TOP_KS, S0)

STEPS = ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7")


@dataclass(frozen=True)
class Config:
    """The settings the ladder changes. Each stack keeps its own default search throughout."""

    chunk_size: int
    overlap: int
    top_k: int
    answer_model: str
    prompt_name: str
    method: str = FIXED_METHOD
    rerank: bool = False


@dataclass(frozen=True)
class Decision:
    """One finished step: what it tried and what the later steps carry on with."""

    step: str
    tried: list[Config]
    kept: Config


@dataclass(frozen=True)
class Progress:
    """The finished steps and the next one. `next_step` is None when the ladder is finished. S6 with `missing` empty
    means the user has not yet chosen its prompt versions."""

    decisions: list[Decision]
    next_step: str | None
    missing: list[Config]


def baseline(prompt_name: str) -> Config:
    """S0's settings."""
    return Config(S0["chunk_size"], S0["overlap"], S0["top_k"], S0["answer_model"], prompt_name)


def options(step: str, current: Config, prompt_names: tuple[str, ...]) -> list[Config]:
    """The configurations a step tries, given the settings kept so far."""
    match step:
        case "S0":
            return [current]
        case "S1":
            share = S0["overlap"] / S0["chunk_size"]
            return [replace(current, chunk_size=size, overlap=round(size * share)) for size in LADDER_SIZES]
        case "S2":
            return [replace(current, overlap=round(current.chunk_size * s)) for s in LADDER_OVERLAP_SHARES]
        case "S3":
            return [replace(current, top_k=k) for k in LADDER_TOP_KS]
        case "S4":
            return [current, replace(current, method=ENRICHED_METHOD)]
        case "S5":
            return [current, replace(current, rerank=True)]
        case "S6":
            return list(dict.fromkeys([current] + [replace(current, prompt_name=p) for p in prompt_names]))
        case "S7":
            return [current, replace(current, answer_model=LADDER_STRONG_MODEL)]
    raise ValueError(f"unknown step {step}")


def real_gain(before: Candidate, after: Candidate) -> bool:
    """T49: the option is kept only if accuracy or MRR is really better. It must also pass the gates, since a run that
    fails one can never be the best (T08)."""
    return not selection.failed_gates(after.scores) and (
        selection.is_real_improvement(before.accuracy, after.accuracy)
        or selection.is_real_improvement(before.mrr, after.mrr))


def choose(step: str, current: Config, tried: list[Config], result: Callable[[Config], Candidate]) -> Config:
    """The configuration a finished step keeps, given the settings it started from. S7 is only reported; S4 and S5
    follow T49; the others follow T08 (T50), keeping `current` if no option passes the gates."""
    if step == "S7":
        return current
    if step in ("S4", "S5"):
        return tried[1] if real_gain(result(current), result(tried[1])) else current
    found = [result(config) for config in tried]
    best = selection.pick_best(found)
    return tried[found.index(best)] if best else current


def walk(result: Callable[[Config], Candidate | None], default_prompt: str,
         prompt_names: tuple[str, ...] | None = None) -> Progress:
    """Replay the ladder over the stored results. `result` returns a configuration's finished run or None;
    `prompt_names` are the versions chosen for S6, None until the user has chosen."""
    if prompt_names and len(prompt_names) > LADDER_MAX_PROMPTS:
        raise ValueError(f"at most {LADDER_MAX_PROMPTS} prompt versions at S6")
    current, decisions = baseline(default_prompt), []
    for step in STEPS:
        if step == "S6" and prompt_names is None:
            return Progress(decisions, step, [])
        tried = options(step, current, prompt_names or ())
        missing = [config for config in tried if result(config) is None]
        if missing:
            return Progress(decisions, step, missing)
        current = choose(step, current, tried, result)
        decisions.append(Decision(step, tried, current))
    return Progress(decisions, None, [])
