"""SQLite storage, one database file per environment (decision.md D06)."""

import sqlite3
from pathlib import Path

from rag_playground.settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS prompt_versions (
    name TEXT PRIMARY KEY CHECK (trim(name, char(9, 10, 13, 32)) <> ''),
    text TEXT NOT NULL CHECK (trim(text, char(9, 10, 13, 32)) <> ''),
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- REPLACE deletes the old row without firing delete triggers, so inserts over an existing row are blocked here.
CREATE TRIGGER IF NOT EXISTS prompt_versions_no_replace BEFORE INSERT ON prompt_versions
WHEN EXISTS (SELECT 1 FROM prompt_versions WHERE name = NEW.name OR rowid = NEW.rowid)
BEGIN SELECT RAISE(ABORT, 'prompt versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prompt_versions_no_update BEFORE UPDATE ON prompt_versions
BEGIN SELECT RAISE(ABORT, 'prompt versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prompt_versions_no_delete BEFORE DELETE ON prompt_versions
BEGIN SELECT RAISE(ABORT, 'prompt versions are immutable'); END;
"""


def db_path() -> Path:
    return settings.var_dir / "rag_playground.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the database (creating it and its tables if needed); rows behave like dicts."""
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
