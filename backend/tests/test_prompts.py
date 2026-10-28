"""Step 6 checks of system prompt versions (T36): saving creates a version, a version never changes."""

import hashlib
import sqlite3

import pytest

from rag_playground import store
from rag_playground.rag import prompts


@pytest.fixture
def conn(tmp_path):
    connection = store.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def test_saving_creates_a_version_with_the_sha256_of_its_text(conn):
    saved = prompts.save(conn, "strict", "Answer only from the context.")
    assert saved.sha256 == hashlib.sha256(b"Answer only from the context.").hexdigest()
    assert prompts.get(conn, "strict") == saved


def test_each_save_adds_a_version_and_keeps_the_older_ones(conn):
    prompts.save(conn, "v1", "First text.")
    prompts.save(conn, "v2", "Second text.")
    assert [(v.name, v.text) for v in prompts.list_all(conn)] == [("v1", "First text."), ("v2", "Second text.")]


def test_saving_under_an_existing_name_is_refused_and_the_old_text_is_kept(conn):
    prompts.save(conn, "v1", "First text.")
    with pytest.raises(sqlite3.IntegrityError):
        prompts.save(conn, "v1", "Changed text.")
    assert prompts.get(conn, "v1").text == "First text."


@pytest.mark.parametrize("sql", [
    "UPDATE prompt_versions SET text = 'Changed.' WHERE name = 'v1'",
    "DELETE FROM prompt_versions WHERE name = 'v1'",
    "INSERT OR REPLACE INTO prompt_versions (name, text, sha256) VALUES ('v1', 'Changed.', 'x')",
    "REPLACE INTO prompt_versions (name, text, sha256) VALUES ('v1', 'Changed.', 'x')",
    "INSERT OR REPLACE INTO prompt_versions (rowid, name, text, sha256) VALUES (1, 'v2', 'Changed.', 'x')",
])
def test_the_database_refuses_any_sql_that_changes_or_removes_a_version(conn, sql):
    """Immutability is enforced by the database itself, not only by our functions (fix.md 2026-10-28)."""
    prompts.save(conn, "v1", "First text.")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute(sql)
    assert prompts.list_all(conn) == [prompts.PromptVersion("v1", "First text.", prompts.sha256("First text."))]


@pytest.mark.parametrize("name, text", [("", "Text."), ("   ", "Text."), ("v1", ""), ("v1", " \n ")])
def test_a_blank_name_or_text_is_refused(conn, name, text):
    """A blank version could never be removed, so it must never be saved."""
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        prompts.save(conn, name, text)
    assert prompts.list_all(conn) == []


def test_the_same_text_can_be_saved_under_two_names(conn):
    """Versions are identified by name; runs also store the hash, so identical texts stay recognisable."""
    first = prompts.save(conn, "v1", "Same text.")
    second = prompts.save(conn, "v2", "Same text.")
    assert first.sha256 == second.sha256
    assert [v.name for v in prompts.list_all(conn)] == ["v1", "v2"]


def test_versions_survive_reopening_the_database(tmp_path):
    path = tmp_path / "test.db"
    first = store.connect(path)
    prompts.save(first, "v1", "First text.")
    first.close()
    second = store.connect(path)
    assert prompts.get(second, "v1").text == "First text."
    second.close()


def test_unknown_version_raises_key_error(conn):
    with pytest.raises(KeyError):
        prompts.get(conn, "missing")


def test_ensure_default_saves_it_once(conn):
    first = prompts.ensure_default(conn)
    second = prompts.ensure_default(conn)
    assert first == second == prompts.PromptVersion("default", prompts.DEFAULT_TEXT,
                                                    prompts.sha256(prompts.DEFAULT_TEXT))
    assert len(prompts.list_all(conn)) == 1


def test_ensure_default_refuses_a_changed_default_text(conn, monkeypatch):
    """Editing DEFAULT_TEXT in code must not silently give old and new runs the same version name."""
    prompts.ensure_default(conn)
    monkeypatch.setattr(prompts, "DEFAULT_TEXT", "Edited default.")
    with pytest.raises(ValueError, match="differs"):
        prompts.ensure_default(conn)
