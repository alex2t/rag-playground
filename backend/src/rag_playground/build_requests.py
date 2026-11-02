"""What the Build page sends (D29): a chunk set to estimate, or to build on one stack. Types are strict (D27)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from rag_playground.chunking.chunk_sets import check_params


class BuildSettings(BaseModel):
    """The chunk set: chunking method, size and overlap in tokens (T35 ranges)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    chunking_method: Literal["fixed", "llm_enriched"]
    chunk_size: int
    overlap: int

    @model_validator(mode="after")
    def check(self) -> "BuildSettings":
        check_params(self.chunk_size, self.overlap)
        return self


class BuildRequest(BuildSettings):
    """One build: the chunk set on one stack. Building on both stacks is two requests, like runs."""

    stack: Literal["A", "B"]
