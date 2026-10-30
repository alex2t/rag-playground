"""Step 6 check of D26: while the job holds a write open, the dashboard can still connect and read."""

from rag_playground import store
from rag_playground.rag.runs import insert


def spend_row(cost: float) -> dict:
    return {"model": "m", "prompt_tokens": 1, "completion_tokens": 1, "reasoning_tokens": 0, "cost_usd": cost}


def test_the_database_uses_the_write_ahead_log(tmp_path):
    path = tmp_path / "t.db"
    store.connect(path).close()
    assert store.connect(path).execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_a_reader_is_not_blocked_by_an_open_write_and_sees_the_last_committed_data(tmp_path):
    """EXCLUSIVE is the lock a commit takes; without the log it locks readers out. The reader must not wait at all
    (busy_timeout 0): it would fail with "database is locked" otherwise."""
    path = tmp_path / "t.db"
    writer = store.connect(path)
    insert(writer, "spend", spend_row(1.0))
    writer.execute("BEGIN EXCLUSIVE")
    writer.execute("UPDATE spend SET cost_usd = 2.0")
    reader = store.connect(path)
    reader.execute("PRAGMA busy_timeout = 0")
    assert reader.execute("SELECT cost_usd FROM spend").fetchone()[0] == 1.0
    writer.commit()
    assert reader.execute("SELECT cost_usd FROM spend").fetchone()[0] == 2.0
