"""System prompt versions for the answer model (decision.md T36): named, immutable, identified by a hash."""

import hashlib
import sqlite3
from dataclasses import dataclass

DEFAULT_NAME = "default"
DEFAULT_TEXT = """You are the internal knowledge assistant of Larkspur Cloud Partners, a consulting firm that delivers \
cloud CRM projects for its clients.
Staff ask you questions about the company and its policies, its employees, its services, its clients and its \
deployment runbooks.
Each question comes with context documents retrieved from the company knowledge base.
Answer using only these context documents. Do not use outside knowledge and do not guess.
If the context does not contain the answer, say that the information is not in the knowledge base.
When the answer needs a calculation, such as a duration or a total, compute it from the facts in the context.
Answer concisely, in a few sentences at most."""


@dataclass(frozen=True)
class PromptVersion:
    name: str
    text: str
    sha256: str


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save(conn: sqlite3.Connection, name: str, text: str) -> PromptVersion:
    """Save a new version; raises sqlite3.IntegrityError if the name is taken."""
    version = PromptVersion(name, text, sha256(text))
    with conn:
        conn.execute("INSERT INTO prompt_versions (name, text, sha256) VALUES (?, ?, ?)",
                     (version.name, version.text, version.sha256))
    return version


def get(conn: sqlite3.Connection, name: str) -> PromptVersion:
    """Return a saved version; raises KeyError if it does not exist."""
    row = conn.execute("SELECT name, text, sha256 FROM prompt_versions WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise KeyError(name)
    return PromptVersion(**row)


def list_all(conn: sqlite3.Connection) -> list[PromptVersion]:
    """All versions, oldest first."""
    rows = conn.execute("SELECT name, text, sha256 FROM prompt_versions ORDER BY created_at, rowid").fetchall()
    return [PromptVersion(**row) for row in rows]


def ensure_default(conn: sqlite3.Connection) -> PromptVersion:
    """Save the default version on first use. Fails if the stored default differs from the code's text."""
    try:
        stored = get(conn, DEFAULT_NAME)
    except KeyError:
        return save(conn, DEFAULT_NAME, DEFAULT_TEXT)
    if stored.sha256 != sha256(DEFAULT_TEXT):
        raise ValueError("The stored default prompt differs from DEFAULT_TEXT; save the new text under a new name.")
    return stored
