"""Regression tests for gate_log's concurrency hardening (part of the
5-10 concurrent calls plan, Phase 1) — WAL mode + busy_timeout so writers
don't immediately collide, plus an application-level retry for the rare
case that still isn't enough.

Uses a temporary sqlite file (never the real app.db) so these tests can't
touch production data.
"""
from __future__ import annotations

import sqlite3

import pytest

from src.data import gate_log


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"
    monkeypatch.setattr(gate_log, "DB_PATH", str(db_path))
    gate_log.init_db()
    return db_path


def test_connect_enables_wal_mode(temp_db):
    with gate_log._connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_append_transcript_turn_writes_the_correct_row(temp_db):
    gate_log.append_transcript_turn("visitor-1", "user", "hello there")

    rows = gate_log.list_transcript("visitor-1")
    assert len(rows) == 1
    assert rows[0]["role"] == "user"
    assert rows[0]["text"] == "hello there"


def test_write_with_retry_retries_on_locked_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return "done"

    result = gate_log._write_with_retry(flaky)

    assert result == "done"
    assert calls["n"] == 3


def test_write_with_retry_gives_up_after_max_attempts():
    def always_locked():
        raise sqlite3.OperationalError("database is locked")

    with pytest.raises(sqlite3.OperationalError):
        gate_log._write_with_retry(always_locked, attempts=3)


def test_write_with_retry_does_not_retry_unrelated_errors():
    calls = {"n": 0}

    def bad_sql():
        calls["n"] += 1
        raise sqlite3.OperationalError("no such table: nonsense")

    with pytest.raises(sqlite3.OperationalError):
        gate_log._write_with_retry(bad_sql)

    assert calls["n"] == 1


def test_concurrent_writes_from_multiple_threads_all_land(temp_db):
    """Simulates several calls writing transcript turns at the same moment
    (asyncio.to_thread would run each on its own OS thread) — every write
    must land, none silently lost to lock contention."""
    import threading

    def write(i):
        gate_log.append_transcript_turn(f"visitor-{i}", "user", f"turn {i}")

    threads = [threading.Thread(target=write, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(20):
        rows = gate_log.list_transcript(f"visitor-{i}")
        assert len(rows) == 1
        assert rows[0]["text"] == f"turn {i}"
