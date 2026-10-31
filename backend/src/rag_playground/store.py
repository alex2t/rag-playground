"""SQLite storage, one database file per environment (decision.md D06)."""

import sqlite3
from pathlib import Path

from rag_playground.settings import MAX_TOP_K, settings

SCHEMA = f"""
PRAGMA journal_mode = WAL;
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
    test_ids TEXT NOT NULL CHECK (json_array_length(test_ids) > 0),
    chunk_set_id TEXT NOT NULL,
    top_k INTEGER NOT NULL CHECK (top_k BETWEEN 1 AND {MAX_TOP_K}),
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
-- A result is only stored for a question the run declared when it was created.
CREATE TRIGGER IF NOT EXISTS results_declared_test BEFORE INSERT ON results
WHEN EXISTS (SELECT 1 FROM runs WHERE id = NEW.run_id)
 AND NOT EXISTS (SELECT 1 FROM runs, json_each(runs.test_ids)
                 WHERE runs.id = NEW.run_id AND json_each.value = NEW.test_id)
BEGIN SELECT RAISE(ABORT, 'test is not part of this run'); END;
-- Runs and results are the evidence behind every score, so the database keeps them as written:
-- a run starts "running", its settings never change, it finishes once, and nothing is deleted or replaced.
-- "done" needs a result for every declared question.
CREATE TRIGGER IF NOT EXISTS runs_start_running BEFORE INSERT ON runs
WHEN NEW.status <> 'running' OR NEW.error IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a new run starts running, with no error'); END;
CREATE TRIGGER IF NOT EXISTS runs_no_replace BEFORE INSERT ON runs
WHEN EXISTS (SELECT 1 FROM runs WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'runs are permanent'); END;
CREATE TRIGGER IF NOT EXISTS runs_no_delete BEFORE DELETE ON runs
BEGIN SELECT RAISE(ABORT, 'runs are permanent'); END;
CREATE TRIGGER IF NOT EXISTS runs_settings_fixed BEFORE UPDATE OF
    id, created_at, stack, split, test_ids, chunk_set_id, top_k, hybrid, openai_ranking, answer_model, answer_slug,
    judge_model, judge_slug, rerank_model, rerank_slug, rerank_candidates, temperature_controlled, prompt_name,
    prompt_sha256, dataset_sha256, app_version ON runs
BEGIN SELECT RAISE(ABORT, 'run settings are permanent'); END;
-- "UPDATE OF id" does not fire for "SET rowid = ...", which renumbers the run just the same.
CREATE TRIGGER IF NOT EXISTS runs_id_fixed BEFORE UPDATE ON runs
WHEN NEW.id <> OLD.id
BEGIN SELECT RAISE(ABORT, 'run settings are permanent'); END;
CREATE TRIGGER IF NOT EXISTS runs_finish_once BEFORE UPDATE ON runs
WHEN OLD.status <> 'running' OR NEW.status = 'running'
BEGIN SELECT RAISE(ABORT, 'a run changes once, from running to finished'); END;
CREATE TRIGGER IF NOT EXISTS results_running_run BEFORE INSERT ON results
WHEN (SELECT status FROM runs WHERE id = NEW.run_id) <> 'running'
BEGIN SELECT RAISE(ABORT, 'the run is finished'); END;
-- REPLACE deletes the old row without firing delete triggers, so inserts over an existing row are blocked here.
CREATE TRIGGER IF NOT EXISTS results_no_replace BEFORE INSERT ON results
WHEN EXISTS (SELECT 1 FROM results WHERE (run_id = NEW.run_id AND test_id = NEW.test_id) OR rowid = NEW.rowid)
BEGIN SELECT RAISE(ABORT, 'stored results are permanent'); END;
CREATE TRIGGER IF NOT EXISTS results_no_update BEFORE UPDATE ON results
BEGIN SELECT RAISE(ABORT, 'stored results are permanent'); END;
CREATE TRIGGER IF NOT EXISTS results_no_delete BEFORE DELETE ON results
BEGIN SELECT RAISE(ABORT, 'stored results are permanent'); END;
CREATE TRIGGER IF NOT EXISTS runs_done_complete BEFORE UPDATE OF status ON runs
WHEN OLD.status = 'running' AND NEW.status = 'done'
 AND (SELECT count(*) FROM results WHERE run_id = NEW.id) <> json_array_length(NEW.test_ids)
BEGIN SELECT RAISE(ABORT, 'a run is done only with a result for every question'); END;
-- Where each chunk set is indexed: the OpenAI vector store id (Stack A) or the Qdrant collection name (Stack B).
CREATE TABLE IF NOT EXISTS indexes (
    stack TEXT NOT NULL CHECK (stack IN ('A', 'B')),
    chunk_set_id TEXT NOT NULL,
    ref TEXT NOT NULL CHECK (ref <> ''),
    chunk_count INTEGER NOT NULL CHECK (chunk_count > 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (stack, chunk_set_id)
);
-- Background jobs (D07), run one at a time; the UI polls a job's status. An evaluate job is one run. A ladder step
-- job (T50) runs several, and run_id holds its current run, empty until the first one starts.
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    kind TEXT NOT NULL CHECK (kind IN ('evaluate', 'ladder_step')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    run_id INTEGER REFERENCES runs (id),
    stack TEXT CHECK (stack IN ('A', 'B')),
    step TEXT,
    runs_total INTEGER CHECK (runs_total > 0),
    runs_done INTEGER NOT NULL DEFAULT 0 CHECK (runs_done <= runs_total),
    error TEXT,
    finished_at TEXT,
    CHECK ((kind = 'evaluate') = (stack IS NULL)),
    CHECK ((kind = 'evaluate') = (step IS NULL)),
    CHECK ((kind = 'evaluate') = (runs_total IS NULL)),
    CHECK (kind = 'ladder_step' OR run_id IS NOT NULL),
    CHECK ((status = 'failed') = (error IS NOT NULL)),
    CHECK ((status IN ('done', 'failed')) = (finished_at IS NOT NULL))
);
-- A job moves forward only: queued -> running -> done or failed; queued -> failed when interrupted.
CREATE TRIGGER IF NOT EXISTS jobs_forward_only BEFORE UPDATE OF status ON jobs
WHEN NOT ((OLD.status = 'queued' AND NEW.status IN ('running', 'failed'))
          OR (OLD.status = 'running' AND NEW.status IN ('done', 'failed')))
BEGIN SELECT RAISE(ABORT, 'a job moves forward only'); END;
CREATE UNIQUE INDEX IF NOT EXISTS jobs_one_active_step ON jobs (stack)
WHERE kind = 'ladder_step' AND status IN ('queued', 'running');
-- The prompt versions chosen for ladder step S6 (T50), once per stack: a later change would rewrite the ladder's past.
CREATE TABLE IF NOT EXISTS ladder_prompts (
    stack TEXT PRIMARY KEY CHECK (stack IN ('A', 'B')),
    names TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS ladder_prompts_no_replace BEFORE INSERT ON ladder_prompts
WHEN EXISTS (SELECT 1 FROM ladder_prompts WHERE stack = NEW.stack)
BEGIN SELECT RAISE(ABORT, 'ladder prompts are chosen once per stack'); END;
CREATE TRIGGER IF NOT EXISTS ladder_prompts_no_update BEFORE UPDATE ON ladder_prompts
BEGIN SELECT RAISE(ABORT, 'ladder prompts are chosen once per stack'); END;
CREATE TRIGGER IF NOT EXISTS ladder_prompts_no_delete BEFORE DELETE ON ladder_prompts
BEGIN SELECT RAISE(ABORT, 'ladder prompts are chosen once per stack'); END;
-- One row per paid OpenRouter call, written as soon as it returns (T44). run_id is NULL outside runs.
CREATE TABLE IF NOT EXISTS spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    run_id INTEGER REFERENCES runs (id),
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    reasoning_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL CHECK (cost_usd >= 0)
);
-- Judge calibration (T48): the sample is fixed once drawn, and each human grade is given once, blind to the judge.
CREATE TABLE IF NOT EXISTS calibrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    run_a INTEGER NOT NULL REFERENCES runs (id),
    run_b INTEGER NOT NULL REFERENCES runs (id),
    per_run INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    size INTEGER NOT NULL CHECK (size > 0),
    UNIQUE (run_a, run_b)
);
CREATE TRIGGER IF NOT EXISTS calibrations_no_replace BEFORE INSERT ON calibrations
WHEN EXISTS (SELECT 1 FROM calibrations WHERE id = NEW.id OR (run_a = NEW.run_a AND run_b = NEW.run_b))
BEGIN SELECT RAISE(ABORT, 'calibrations are permanent'); END;
CREATE TRIGGER IF NOT EXISTS calibrations_no_update BEFORE UPDATE ON calibrations
BEGIN SELECT RAISE(ABORT, 'calibrations are permanent'); END;
CREATE TRIGGER IF NOT EXISTS calibrations_no_delete BEFORE DELETE ON calibrations
BEGIN SELECT RAISE(ABORT, 'calibrations are permanent'); END;
CREATE TABLE IF NOT EXISTS calibration_items (
    calibration_id INTEGER NOT NULL REFERENCES calibrations (id),
    position INTEGER NOT NULL CHECK (position > 0),
    run_id INTEGER NOT NULL,
    test_id TEXT NOT NULL,
    grade INTEGER CHECK (grade IN (1, 2, 3, 4, 5)),
    PRIMARY KEY (calibration_id, position),
    UNIQUE (calibration_id, run_id, test_id),
    FOREIGN KEY (run_id, test_id) REFERENCES results (run_id, test_id)
) WITHOUT ROWID;
-- A sample stops growing at its size, which also blocks replacing an item, and every item starts ungraded.
CREATE TRIGGER IF NOT EXISTS calibration_items_fixed_size BEFORE INSERT ON calibration_items
WHEN NEW.grade IS NOT NULL
  OR (SELECT count(*) FROM calibration_items WHERE calibration_id = NEW.calibration_id)
     >= (SELECT size FROM calibrations WHERE id = NEW.calibration_id)
BEGIN SELECT RAISE(ABORT, 'a calibration sample is fixed once drawn'); END;
CREATE TRIGGER IF NOT EXISTS calibration_items_sample_fixed BEFORE UPDATE OF calibration_id, position, run_id, test_id
ON calibration_items
BEGIN SELECT RAISE(ABORT, 'a calibration sample is fixed once drawn'); END;
CREATE TRIGGER IF NOT EXISTS calibration_items_grade_once BEFORE UPDATE OF grade ON calibration_items
WHEN OLD.grade IS NOT NULL OR NEW.grade IS NULL
BEGIN SELECT RAISE(ABORT, 'a grade is given once'); END;
CREATE TRIGGER IF NOT EXISTS calibration_items_no_delete BEFORE DELETE ON calibration_items
BEGIN SELECT RAISE(ABORT, 'a calibration sample is fixed once drawn'); END;
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
