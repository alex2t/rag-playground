"""The request that starts an evaluation run from the dashboard (POST /api/runs). Every setting is required (T40);
each stack takes its own search settings (T40 revision 2026-10-29)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rag_playground.chunking.chunk_sets import check_params, chunk_set_id
from rag_playground.chunking.enrichment import enriched_set_id
from rag_playground.datasets.schema import TestCase, load_tests
from rag_playground.datasets.splits import round_robin
from rag_playground.rag.pipeline import Choices
from rag_playground.settings import ANSWER_MODELS, MAX_TOP_K

SMOKE_QUESTIONS = 20


class OpenAIRanking(BaseModel):
    """Stack A's search settings: OpenAI's own ranking options (T12)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    ranker: Literal["none", "auto"]
    embedding_weight: float = Field(ge=0)
    text_weight: float = Field(ge=0)
    score_threshold: float = Field(ge=0, le=1)


class RunRequest(BaseModel):
    """One evaluation run: the settings panel plus the question set. Stack A takes `openai_ranking`, Stack B
    `hybrid`; the other stack's field must be left out. Types are strict: "3" is not 3 (D27)."""

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
    questions: Literal["dev", "heldout", "smoke"]

    @model_validator(mode="after")
    def check(self) -> "RunRequest":
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
        base_id = chunk_set_id(self.chunk_size, self.overlap)
        set_id = enriched_set_id(base_id) if self.chunking_method == "llm_enriched" else base_id
        return Choices(stack=self.stack, chunk_set_id=set_id, top_k=self.top_k, hybrid=hybrid, openai_ranking=ranking, rerank=self.rerank, answer_model=self.answer_model,
                       prompt_name=self.prompt_name)

    def tests(self) -> list[TestCase]:
        """All 192 dev or 48 held-out questions, or the 20-question smoke test (round-robin over dev, T46)."""
        if self.questions == "smoke":
            return round_robin([t for t in load_tests() if t.split == "dev"], SMOKE_QUESTIONS)
        return [t for t in load_tests() if t.split == self.questions]
