"""SQLite storage, one database file per environment (decision.md D06)."""

import sqlite3
from pathlib import Path

from rag_playground.settings import settings

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS prompt_versions (
    name TEXT PRIMARY KEY CHECK (trim(name, char(9, 10, 13, 32)) <> ''),
    text TEXT NOT NULL CHECK (trim(text, char(9, 10, 13, 32)) <> ''),
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, sha256)
);
-- REPLACE deletes the old row without firing delete triggers, so inserts over an existing row are blocked here.
CREATE TRIGGER IF NOT EXISTS prompt_versions_no_replace BEFORE INSERT ON prompt_versions
WHEN EXISTS (SELECT 1 FROM prompt_versions WHERE name = NEW.name OR rowid = NEW.rowid)
BEGIN SELECT RAISE(ABORT, 'prompt versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prompt_versions_no_update BEFORE UPDATE ON prompt_versions
BEGIN SELECT RAISE(ABORT, 'prompt versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prompt_versions_no_delete BEFORE DELETE ON prompt_versions
BEGIN SELECT RAISE(ABORT, 'prompt versions are immutable'); END;

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'failed')),
    error TEXT,
    stack TEXT NOT NULL CHECK (stack IN ('A', 'B')),
    split TEXT NOT NULL CHECK (split IN ('dev', 'heldout')),
    question_count INTEGER NOT NULL CHECK (question_count > 0),
    chunk_set_id TEXT NOT NULL,
    top_k INTEGER NOT NULL CHECK (top_k > 0),
    hybrid INTEGER NOT NULL,
    openai_ranking TEXT,
    answer_model TEXT NOT NULL,
    answer_slug TEXT NOT NULL,
    judge_model TEXT NOT NULL,
    judge_slug TEXT NOT NULL,
    rerank_model TEXT,
    rerank_slug TEXT,
    rerank_candidates INTEGER CHECK (rerank_candidates >= top_k),
    temperature_controlled INTEGER NOT NULL,
    prompt_name TEXT NOT NULL,
    prompt_sha256 TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL,
    app_version TEXT NOT NULL,
    FOREIGN KEY (prompt_name, prompt_sha256) REFERENCES prompt_versions (name, sha256),
    CHECK ((stack = 'A') = (openai_ranking IS NOT NULL)),
    CHECK ((rerank_model IS NULL) = (rerank_slug IS NULL) AND (rerank_model IS NULL) = (rerank_candidates IS NULL))
);
CREATE TABLE IF NOT EXISTS results (
    run_id INTEGER NOT NULL REFERENCES runs (id),
    test_id TEXT NOT NULL,
    hits TEXT NOT NULL,
    rerank_repaired INTEGER,
    answer TEXT NOT NULL,
    refused INTEGER NOT NULL CHECK (refused IN (0, 1)),
    accuracy INTEGER NOT NULL CHECK (accuracy BETWEEN 1 AND 5),
    completeness INTEGER NOT NULL CHECK (completeness BETWEEN 1 AND 5),
    relevance INTEGER NOT NULL CHECK (relevance BETWEEN 1 AND 5),
    faithfulness INTEGER NOT NULL CHECK (faithfulness BETWEEN 1 AND 5),
    feedback TEXT NOT NULL,
    faithfulness_feedback TEXT NOT NULL,
    cost_usd REAL NOT NULL,
    latency_s REAL NOT NULL,
    PRIMARY KEY (run_id, test_id)
);
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
