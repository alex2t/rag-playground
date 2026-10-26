"""Test-case schema and the paths of the committed synthetic dataset (D20)."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "synthetic"
KB_DIR = DATA_DIR / "kb"
WORLD_PATH = DATA_DIR / "world.json"
AUDIT_PATH = DATA_DIR / "world_audit.json"
DOCS_AUDIT_PATH = DATA_DIR / "docs_audit.json"
CLAIM_ALLOWLIST_PATH = DATA_DIR / "claim_allowlist.json"
CANDIDATES_PATH = DATA_DIR / "candidates.jsonl"
VERIFICATION_PATH = DATA_DIR / "verification.jsonl"
TESTS_PATH = DATA_DIR / "tests.jsonl"


class Category(StrEnum):
    DIRECT_FACT = "direct_fact"
    MULTI_DOC = "multi_doc"
    NUMERICAL = "numerical"
    TEMPORAL = "temporal"
    COMPARATIVE = "comparative"
    EXACT_TERM = "exact_term"
    UNANSWERABLE = "unanswerable"


class Split(StrEnum):
    DEV = "dev"
    HELDOUT = "heldout"


class TestCase(BaseModel):
    """One evaluation question with its gold sources (T17) and split (T18)."""

    id: str
    question: str
    reference_answer: str
    category: Category
    source_docs: list[str]
    keywords: list[str]
    split: Split


def load_tests() -> list[TestCase]:
    """Read every test case from tests.jsonl."""
    lines = TESTS_PATH.read_text(encoding="utf-8").splitlines()
    return [TestCase.model_validate_json(line) for line in lines if line.strip()]
