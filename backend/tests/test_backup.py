"""Tests for the nightly database copy (D38): a consistent, checked copy of the live database, 7 kept, one per day;
run as cron runs it (`python -m rag_playground.backup` in its own process)."""

import json
import os
import sqlite3
import subprocess
import sys

import pytest

from rag_playground import backup, store
from rag_playground.settings import settings


@pytest.fixture
def var(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    return tmp_path


def live_database(var):
    """A real app database with one saved prompt, left open with its last write still in the WAL file (not yet
    copied into the main file), as in the running app."""
    conn = store.connect()
    conn.execute("PRAGMA wal_autocheckpoint = 0")
    with conn:
        conn.execute("INSERT INTO prompt_versions (name, text, sha256) VALUES ('kept', 'A text.', 'a')")
    assert (var / "rag_playground.db-wal").stat().st_size > 0
    return conn


def prompt_names(path):
    conn = sqlite3.connect(path)
    names = [row[0] for row in conn.execute("SELECT name FROM prompt_versions")]
    conn.close()
    return names


def run_module(var):
    env = {**os.environ, "VAR_DIR": str(var)}
    return subprocess.run([sys.executable, "-m", "rag_playground.backup"], capture_output=True, text=True, env=env)


def test_the_copy_holds_writes_still_in_the_wal_file_and_passes_its_check(var):
    conn = live_database(var)
    target = backup.run("2026-11-09")
    conn.close()
    assert target == var / "backups" / "rag_playground-2026-11-09.db"
    assert sorted(p.name for p in (var / "backups").iterdir()) == ["rag_playground-2026-11-09.db"]
    copy = sqlite3.connect(target)
    assert copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    copy.close()
    assert prompt_names(target) == ["kept"]


def test_a_restored_copy_is_back_in_wal_mode_when_the_app_opens_it(var):
    live_database(var).close()
    target = backup.run("2026-11-09")
    target.replace(var / "rag_playground.db")
    conn = store.connect()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert [row[0] for row in conn.execute("SELECT name FROM prompt_versions WHERE name = 'kept'")] == ["kept"]
    conn.close()


def test_a_missing_database_is_an_error_not_an_empty_copy(var):
    with pytest.raises(sqlite3.OperationalError):
        backup.run("2026-11-09")
    assert not (var / "rag_playground.db").exists()
    assert list((var / "backups").iterdir()) == []


def test_a_second_run_the_same_day_replaces_that_days_copy(var):
    conn = live_database(var)
    backup.run("2026-11-09")
    with conn:
        conn.execute("INSERT INTO prompt_versions (name, text, sha256) VALUES ('later', 'B text.', 'b')")
    backup.run("2026-11-09")
    conn.close()
    assert [p.name for p in (var / "backups").iterdir()] == ["rag_playground-2026-11-09.db"]
    assert sorted(prompt_names(var / "backups" / "rag_playground-2026-11-09.db")) == ["kept", "later"]


def test_only_the_newest_seven_copies_are_kept(var):
    live_database(var).close()
    folder = var / "backups"
    folder.mkdir()
    for day in range(1, 10):
        (folder / f"rag_playground-2026-11-0{day}.db").write_bytes(b"old")
    backup.run("2026-11-10")
    assert sorted(p.name for p in folder.iterdir()) == [f"rag_playground-2026-11-{d:02d}.db" for d in range(4, 11)]


def test_the_module_run_by_cron_logs_the_copy_on_stdout(var):
    live_database(var).close()
    result = run_module(var)
    assert result.returncode == 0, result.stderr
    [line] = [json.loads(line) for line in result.stdout.splitlines()]
    assert (line["logger"], line["message"]) == ("rag_playground.backup", "backup done")
    assert line["file"].startswith("rag_playground-") and line["bytes"] > 0
    assert (var / "backups" / line["file"]).exists()
    assert not (var / "errors.log").exists()


def test_a_failed_run_exits_non_zero_and_writes_errors_log(var):
    result = run_module(var)
    assert result.returncode != 0
    [line] = [json.loads(line) for line in (var / "errors.log").read_text(encoding="utf-8").splitlines()]
    assert (line["level"], line["message"]) == ("ERROR", "backup failed")
    assert "OperationalError" in line["exception"]
