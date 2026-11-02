"""D29: a jobs table made before build jobs is recreated at connect, keeping every row, all or nothing."""

import sqlite3
import threading

import pytest

from rag_playground import store
from rag_playground.rag import prompts, runs
from rag_playground.rag.runs import insert
from test_runs import STACK_B

OLD_JOBS = """CREATE TABLE jobs (
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
);"""
OLD_ROWS = [
    (1, "2026-10-31 10:00:00", "ladder_step", "done", None, "A", "S1", 5, 5, None, "2026-10-31 11:00:00"),
    (2, "2026-10-31 12:00:00", "ladder_step", "failed", None, "B", "S2", 3, 1, "Budget reached", "2026-10-31 12:30:00"),
    (4, "2026-10-31 13:00:00", "evaluate", "running", 1, None, None, None, 0, None, None),
]
ROW_COLUMNS = store.OLD_JOB_COLUMNS
BUILD = {"kind": "build", "stack": "B", "chunk_set_id": "fixed__c400__o0"}


def old_database(path, rows=OLD_ROWS, table=OLD_JOBS) -> None:
    """A database as it was before D29: today's tables with run 1, and the old jobs table and its rows."""
    conn = store.connect(path)
    prompts.ensure_default(conn)
    runs.create_run(conn, STACK_B)
    conn.executescript(f"DROP TABLE jobs; {table}")
    for row in rows:
        conn.execute(f"INSERT INTO jobs ({ROW_COLUMNS}) VALUES ({', '.join('?' * len(row))})", row)
    conn.commit()
    conn.close()


def rows(conn) -> list[tuple]:
    return [tuple(row) for row in conn.execute(f"SELECT {ROW_COLUMNS} FROM jobs ORDER BY id")]


def jobs_sql(conn) -> str:
    return conn.execute("SELECT sql FROM sqlite_master WHERE name = 'jobs'").fetchone()[0]


def test_every_old_row_is_kept_with_its_id_and_every_column(tmp_path):
    old_database(tmp_path / "t.db")
    conn = store.connect(tmp_path / "t.db")
    assert rows(conn) == OLD_ROWS
    assert "'build'" in jobs_sql(conn)


def test_a_build_job_is_accepted_after_the_upgrade_and_new_ids_follow_the_old_ones(tmp_path):
    old_database(tmp_path / "t.db")
    conn = store.connect(tmp_path / "t.db")
    assert insert(conn, "jobs", BUILD) == 5


def test_the_trigger_and_the_indexes_come_back_and_still_work(tmp_path):
    old_database(tmp_path / "t.db")
    conn = store.connect(tmp_path / "t.db")
    with pytest.raises(sqlite3.IntegrityError, match="a job moves forward only"):
        conn.execute("UPDATE jobs SET status = 'running', error = NULL, finished_at = NULL WHERE id = 1")
    insert(conn, "jobs", {"kind": "ladder_step", "stack": "A", "step": "S3", "runs_total": 1})
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert(conn, "jobs", {"kind": "ladder_step", "stack": "A", "step": "S3", "runs_total": 1})
    insert(conn, "jobs", BUILD)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert(conn, "jobs", BUILD)


def test_an_upgraded_table_is_left_alone_on_the_next_connect(tmp_path):
    old_database(tmp_path / "t.db")
    conn = store.connect(tmp_path / "t.db")
    insert(conn, "jobs", BUILD)
    before, sql = rows(conn), jobs_sql(conn)
    conn.close()
    again = store.connect(tmp_path / "t.db")
    assert (rows(again), jobs_sql(again)) == (before, sql)
    assert again.execute("SELECT chunk_set_id FROM jobs WHERE kind = 'build'").fetchone()[0] == BUILD["chunk_set_id"]


def test_a_row_the_new_rules_refuse_stops_the_upgrade_and_leaves_the_old_table_whole(tmp_path):
    """An evaluate job without a run: the old CHECKs are dropped here to plant it."""
    unchecked = OLD_JOBS.split("    CHECK ((kind")[0].rstrip().rstrip(",") + "\n);"
    planted = (9, "2026-10-31 14:00:00", "evaluate", "queued", None, None, None, None, 0, None, None)
    old_database(tmp_path / "t.db", [*OLD_ROWS, planted], unchecked)
    with pytest.raises(sqlite3.IntegrityError):
        store.connect(tmp_path / "t.db")
    raw = sqlite3.connect(tmp_path / "t.db")
    assert raw.execute("SELECT name FROM sqlite_master WHERE name = 'jobs_new'").fetchone() is None
    assert "'build'" not in jobs_sql(raw)
    assert rows(raw) == [*OLD_ROWS, planted]


def test_two_connections_opening_at_once_upgrade_once_and_lose_nothing(tmp_path):
    old_database(tmp_path / "t.db")
    start, errors = threading.Barrier(2), []

    def open_it():
        start.wait()
        try:
            store.connect(tmp_path / "t.db").close()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=open_it) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    conn = store.connect(tmp_path / "t.db")
    assert errors == []
    assert rows(conn) == OLD_ROWS


def test_a_second_connection_finds_the_table_upgraded_under_the_lock_and_copies_nothing(tmp_path, monkeypatch):
    """The race made exact: the first check still sees the old table, then another connection upgrades it."""
    old_database(tmp_path / "t.db")
    conn = sqlite3.connect(tmp_path / "t.db")
    answers = iter([True])
    real = store.old_jobs_table

    def stale_once(c):
        result = next(answers, None)
        if result is None:
            return real(c)
        store.connect(tmp_path / "t.db").execute("INSERT INTO jobs (kind, stack, chunk_set_id) VALUES ('build', 'A', 'x')").connection.commit()
        return result

    monkeypatch.setattr(store, "old_jobs_table", stale_once)
    store.upgrade_jobs(conn)
    assert conn.execute("SELECT chunk_set_id FROM jobs WHERE kind = 'build'").fetchone()[0] == "x"


def test_a_new_database_gets_the_new_table_directly(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    assert "'build'" in jobs_sql(conn)
    assert rows(conn) == []


@pytest.mark.parametrize("job, reason", [
    ({"kind": "x", "stack": "A"}, "only the three known kinds exist"),
    ({"kind": "build", "stack": "A"}, "a build names its chunk set"),
    ({"kind": "build", "chunk_set_id": "x"}, "a build names its stack"),
    ({"kind": "build", "stack": "A", "chunk_set_id": ""}, "a chunk set id is never blank"),
    ({"kind": "build", "stack": "A", "chunk_set_id": "x", "step": "S1"}, "a build is no ladder step"),
    ({"kind": "build", "stack": "A", "chunk_set_id": "x", "runs_total": 1}, "a build counts no runs"),
    ({"kind": "ladder_step", "stack": "A", "step": "S1", "runs_total": 1, "chunk_set_id": "x"}, "only a build names a chunk set"),
    ({"kind": "ladder_step", "stack": "A", "runs_total": 1}, "a ladder step names its step"),
    ({"kind": "ladder_step", "stack": "A", "step": "S1"}, "a ladder step counts its runs"),
])
def test_the_new_rules_refuse_a_job_of_the_wrong_shape(tmp_path, job, reason):
    conn = store.connect(tmp_path / "t.db")
    with pytest.raises(sqlite3.IntegrityError):
        insert(conn, "jobs", job)


def test_a_build_has_no_run_and_an_evaluate_job_needs_one(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    conn.execute("PRAGMA foreign_keys = OFF")
    with pytest.raises(sqlite3.IntegrityError):
        insert(conn, "jobs", {**BUILD, "run_id": 1})
    with pytest.raises(sqlite3.IntegrityError):
        insert(conn, "jobs", {"kind": "evaluate"})
    insert(conn, "jobs", {"kind": "evaluate", "run_id": 1})
