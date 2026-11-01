"""The request behind the Ask page (POST /api/ask): the settings panel plus one question (T54)."""

from typing import Annotated

from pydantic import StringConstraints, model_validator

from rag_playground.datasets.schema import TestCase, load_tests
from rag_playground.run_requests import PanelSettings


def dev_questions() -> list[TestCase]:
    """The test questions Ask may use. Held-out ones stay out: seeing them could steer choices (T18)."""
    return [test for test in load_tests() if test.split == "dev"]


class AskRequest(PanelSettings):
    """Either a typed `question` or the id of a dev test question, never both."""

    question: Annotated[str, StringConstraints(pattern=r"\S")] | None = None
    test_id: str | None = None

    @model_validator(mode="after")
    def one_question(self) -> "AskRequest":
        if (self.question is None) == (self.test_id is None):
            raise ValueError("Ask takes either a question or a test_id")
        return self

    def test(self) -> TestCase | None:
        """The chosen dev test question; KeyError if it is not one, so a held-out id reveals nothing."""
        if self.test_id is None:
            return None
        return {test.id: test for test in dev_questions()}[self.test_id]
