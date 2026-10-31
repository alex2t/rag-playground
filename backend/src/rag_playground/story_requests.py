"""The request that starts the ladder's next step (POST /api/story), as strict as run requests (D27)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Stack = Literal["A", "B"]


class StoryRequest(BaseModel):
    """`prompts` are the versions for S6, needed only at that step; an empty list skips S6 (T50)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    stack: Stack
    prompts: list[str] | None = None

    def prompt_names(self) -> tuple[str, ...] | None:
        return None if self.prompts is None else tuple(self.prompts)
