"""The request that saves a system prompt version (POST /api/prompts), as strict as run requests (D27)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

VersionName = Annotated[str, StringConstraints(pattern=r"^\S([^\r\n]*\S)?$")]
VersionText = Annotated[str, StringConstraints(pattern=r"\S")]


class SavePrompt(BaseModel):
    """A one-line name with no space at either end, so two versions cannot look the same, and a text that is not blank."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: VersionName
    text: VersionText
