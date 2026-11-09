"""Nightly copy of the database (D38): `python -m rag_playground.backup`, run inside the app container by the VPS's cron.

SQLite's backup API copies a consistent state while the app keeps running. The copy goes to `<var_dir>/backups/`,
is checked, and only the newest `KEEP` copies are kept."""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from rag_playground import logs, store
from rag_playground.settings import settings

KEEP = 7
backup_log = logging.getLogger("rag_playground.backup")


def copy_database(source: Path, target: Path) -> None:
    """Copy the database at `source` to `target` with the backup API, through a temporary file, so a copy that
    stopped halfway never has a backup's name. Raises if `source` does not exist (instead of copying a new empty
    database) or if the copy fails SQLite's integrity check."""
    partial = target.with_suffix(".partial")
    src = sqlite3.connect(f"{source.as_uri()}?mode=rw", uri=True)
    dst = sqlite3.connect(partial)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode = DELETE")  # one self-contained file; the app turns WAL back on (store.py)
        check = dst.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        src.close()
        dst.close()
    if check != "ok":
        raise RuntimeError(f"backup copy failed its integrity check: {check}")
    partial.replace(target)


def prune(folder: Path) -> list[Path]:
    """Delete all but the newest `KEEP` backups (names sort by date) and return the deleted ones."""
    old = sorted(folder.glob("rag_playground-*.db"))[:-KEEP]
    for path in old:
        path.unlink()
    return old


def run(today: str) -> Path:
    """Back up today's database as `backups/rag_playground-<today>.db` (a second run the same day replaces it), then
    prune."""
    folder = settings.var_dir / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"rag_playground-{today}.db"
    copy_database(store.db_path(), target)
    deleted = prune(folder)
    backup_log.info("backup done", extra={"fields": {"file": target.name, "bytes": target.stat().st_size,
                                                     "deleted": [path.name for path in deleted]}})
    return target


def main() -> None:
    """Log as the app does, so a failure also reaches `errors.log`, and exit non-zero on failure."""
    logs.setup()
    try:
        run(datetime.now(UTC).date().isoformat())
    except Exception:
        backup_log.exception("backup failed")
        raise


if __name__ == "__main__":
    main()
