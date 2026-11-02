"""What the Sweep page sends (T58): a base configuration, the one setting to vary, and its values. Types are strict
(D27): "800" is not 800, and true is not 1."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from rag_playground.rag.ladder_runs import key_of
from rag_playground.run_requests import PanelSettings
from rag_playground.settings import SWEEP_MAX_VALUES

RANKING = ("ranker", "embedding_weight", "text_weight", "score_threshold")
VARIABLES = ("chunk_size", "overlap", "top_k", "chunking_method", "rerank", "answer_model", "prompt_name", "hybrid",
             *RANKING)
Value = bool | int | float | str  # strict like the whole model: each must match its setting's type exactly


class SweepRequest(BaseModel):
    """One sweep on one stack; a sweep on both stacks is two requests, like runs. The base configuration's own value
    of the setting is always part of the sweep: it is what every other value is compared with."""

    model_config = ConfigDict(extra="forbid", strict=True)
    base: PanelSettings
    variable: Literal[VARIABLES]
    values: list[Value] = Field(min_length=1, max_length=SWEEP_MAX_VALUES)

    @model_validator(mode="after")
    def check(self) -> "SweepRequest":
        if self.variable == "hybrid" and self.base.stack != "B":
            raise ValueError("hybrid is a Stack B setting")
        if self.variable in RANKING and self.base.stack != "A":
            raise ValueError(f"{self.variable} is a Stack A setting")
        configs = [config for _, config in self.items()]
        if len({key_of(config.choices()) for config in configs}) < len(configs):
            raise ValueError("Each value must appear once")
        if len(configs) > SWEEP_MAX_VALUES:
            raise ValueError(f"A sweep has at most {SWEEP_MAX_VALUES} values, the base value included")
        return self

    def base_value(self) -> Value:
        return self.base.openai_ranking.model_dump()[self.variable] if self.variable in RANKING else getattr(self.base, self.variable)

    def configured(self, value: Value) -> PanelSettings:
        """The base configuration with the setting at `value`, checked like any run request."""
        data = self.base.model_dump()
        if self.variable in RANKING:
            data["openai_ranking"][self.variable] = value
        else:
            data[self.variable] = value
        try:
            return PanelSettings.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"{self.variable} = {value!r} is not a valid setting: {exc.errors()[0]['msg']}") from exc

    def items(self) -> list[tuple[Value, PanelSettings]]:
        """Each value with its configuration, the base value first when it was not given."""
        given = [(value, self.configured(value)) for value in self.values]
        base_key = key_of(self.base.choices())
        if any(key_of(config.choices()) == base_key for _, config in given):
            return given
        return [(self.base_value(), self.base), *given]
