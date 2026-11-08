"""The request that starts an evaluation run from the dashboard (POST /api/runs). Every setting is required (T40);
each stack takes its own search settings (T40 revision 2026-10-29)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rag_playground.chunking.chunk_sets import MAX_OVERLAP_SHARE, MAX_SIZE, MIN_SIZE, check_params
from rag_playground.chunking.enrichment import set_id_for
from rag_playground.datasets.schema import TestCase, load_tests
from rag_playground.datasets.splits import round_robin
from rag_playground.rag.pipeline import Choices
from rag_playground.settings import ANSWER_MODELS, MAX_TOP_K, S0

SMOKE_QUESTIONS = 20


def smoke_tests() -> list[TestCase]:
    """The 20-question smoke test: dev questions in round-robin order over the categories (T46). The evaluation gate
    uses the same set (D36)."""
    return round_robin([t for t in load_tests() if t.split == "dev"], SMOKE_QUESTIONS)


def panel_options() -> dict:
    """What the settings panel offers (T35): the ranges and models it may choose from, and S0's values to start from.
    They live in the backend so the page cannot drift from what the requests below accept."""
    search = S0["search"]
    return {"min_chunk_size": MIN_SIZE, "max_chunk_size": MAX_SIZE, "max_overlap_share": MAX_OVERLAP_SHARE,
            "max_top_k": MAX_TOP_K, "answer_models": ANSWER_MODELS,
            "start": {"chunking_method": "fixed", "chunk_size": S0["chunk_size"], "overlap": S0["overlap"],
                      "top_k": S0["top_k"], "rerank": S0["rerank"], "answer_model": S0["answer_model"],
                      "openai_ranking": search["A"]["openai_ranking"], "hybrid": search["B"]["hybrid"]}}


class OpenAIRanking(BaseModel):
    """Stack A's search settings: OpenAI's own ranking options (T12)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    ranker: Literal["none", "auto"]
    embedding_weight: float = Field(ge=0)
    text_weight: float = Field(ge=0)
    score_threshold: float = Field(ge=0, le=1)


class PanelSettings(BaseModel):
    """The settings panel (T35), shared by Evaluate and Ask. Stack A takes `openai_ranking`, Stack B `hybrid`; the
    other stack's field must be left out. Types are strict: "3" is not 3 (D27)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    stack: Literal["A", "B"]
    chunking_method: Literal["fixed", "llm_enriched"]
    chunk_size: int
    overlap: int
    top_k: int = Field(ge=1, le=MAX_TOP_K)
    openai_ranking: OpenAIRanking | None = None
    hybrid: bool | None = None
    rerank: bool
    answer_model: Literal[tuple(ANSWER_MODELS)]
    prompt_name: str

    @model_validator(mode="after")
    def check(self) -> "PanelSettings":
        check_params(self.chunk_size, self.overlap)
        if self.stack == "A" and (self.openai_ranking is None or self.hybrid is not None):
            raise ValueError("Stack A takes openai_ranking, not hybrid")
        if self.stack == "B" and (self.hybrid is None or self.openai_ranking is not None):
            raise ValueError("Stack B takes hybrid, not openai_ranking")
        return self

    def choices(self) -> Choices:
        """The pipeline's settings. On Stack A, `hybrid` records whether OpenAI's keyword list takes part."""
        ranking = self.openai_ranking.model_dump() if self.openai_ranking else None
        hybrid = ranking["text_weight"] > 0 if ranking else self.hybrid
        return Choices(stack=self.stack, chunk_set_id=set_id_for(self.chunking_method, self.chunk_size, self.overlap), top_k=self.top_k, hybrid=hybrid, openai_ranking=ranking, rerank=self.rerank, answer_model=self.answer_model,
                       prompt_name=self.prompt_name)


class RunRequest(PanelSettings):
    """One evaluation run: the settings panel plus the question set."""

    questions: Literal["dev", "heldout", "smoke"]

    def tests(self) -> list[TestCase]:
        """All 192 dev or 48 held-out questions, or the 20-question smoke test (round-robin over dev, T46)."""
        if self.questions == "smoke":
            return smoke_tests()
        return [t for t in load_tests() if t.split == self.questions]
