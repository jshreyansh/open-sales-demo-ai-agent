"""Durable log of every visitor-gate submission (see server.py's
/api/visitor/gate) — name, company, and work email captured before someone
reaches /demo/dashboard or /demo/meet, plus every blocked personal-email
attempt. This is the only thing in the app that survives a restart; it's
deliberately separate from SessionState (context/store.py), which stays
exactly what it always was — in-memory, per-call conversation memory for the
live agent, not identity/audit history.

A single append-only table rather than a separate "visitors" table kept in
sync with a "sessions" table: "is this email known" and the admin panel's two
views are just queries over this one log, so there's nothing to keep
consistent across two writes.
"""

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, List, Optional, TypedDict

DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")

# WAL instead of the default rollback journal: readers no longer block
# writers (or each other) at all, and writers only block other writers —
# the busy_timeout below covers that remaining case. Matters once more than
# a couple of calls are writing transcript turns concurrently (see the
# concurrent-calls plan) — under the old default, a write from one call
# could make sqlite3.OperationalError: database is locked visible to
# another call's turn almost immediately, since the default busy timeout is
# 0. Both pragmas are connection-level, so every _connect() call sets them;
# WAL mode itself persists in the database file after the first time.
_BUSY_TIMEOUT_MS = 5000


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Retries a write a couple of times on the rare lock contention that
# outlasts even the busy_timeout above (a burst of concurrent writers all
# landing at once) — busy_timeout already makes SQLite itself wait and
# retry internally, this is the outer, application-level backstop for the
# tail case where that still isn't enough. Read-only functions don't need
# this: a lock only ever blocks a writer, so every read function in this
# file is already safe.
def _write_with_retry(fn, *args, attempts: int = 3, **kwargs):
    for attempt in range(attempts):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as e:
            if "locked" not in str(e).lower() or attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def init_db() -> None:
    """Called automatically at import time (see bottom of this file) — safe
    to call repeatedly (CREATE TABLE IF NOT EXISTS). Runs in both backend
    processes (server.py and, via agent/runtime.py, bot.py's voice
    pipeline), since either one could be the first to actually write here
    and there's no guaranteed startup order between them."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gate_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                email TEXT NOT NULL,
                name TEXT,
                company TEXT,
                path TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gate_attempts_email ON gate_attempts(email)")
        # Every turn of every conversation (chat or voice — both go through
        # the same run_turn(), see agent/runtime.py), keyed by visitor_id so
        # it can be joined back to the gate_attempts row for that session.
        # Written directly from both backend processes (server.py for
        # Product Mode's /chat, bot.py for the voice pipeline) — same file,
        # sqlite's own locking handles the concurrent writers.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transcript_turns_visitor ON transcript_turns(visitor_id)")
        # The qualification profile (5 required KPI questions + 4 bonus
        # MEDDIC fields — see agent/runtime.py's _qualification_note),
        # captured opportunistically over a call the same way transcript
        # turns are: one row per field the moment it's learned, not batched
        # at call-end. A flexible field_name/field_value shape (not one
        # column per field) means adding a 10th tracked field later needs no
        # migration, same reasoning as transcript_turns above.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS qualification_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                field_value TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qualification_fields_visitor ON qualification_fields(visitor_id)")
        # One row per session — generated once (see bot.py's
        # on_client_disconnected) and overwritten if ever regenerated, not
        # append-only like the tables above, since there's only ever one
        # current summary worth keeping per call.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS call_summaries (
                visitor_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                generated_at TEXT NOT NULL
            )
            """
        )
        # Email-verification codes for the gate (see server.py's
        # /api/visitor/otp/send). Append-only like gate_attempts rather than
        # one mutable row per email: the send rate limit is "how many rows
        # for this email in the last 15 minutes", which only works if every
        # issued code leaves a row behind. `consumed` and `attempts` are the
        # two things that DO mutate, both on the single newest row.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                consumed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_otp_codes_email ON otp_codes(email, created_at)")
        # One row per session that has had its recap email sent, written only
        # after Postmark confirms. This is the idempotency guard on the
        # post-call email: the summary path can legitimately run more than
        # once for the same visitor_id (bot.py's on_client_disconnected, plus
        # the admin endpoint's on-demand fallback regenerating an uncached
        # summary), and the visitor should not get the same recap twice.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS summary_emails (
                visitor_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                message_id TEXT NOT NULL,
                sent_at TEXT NOT NULL
            )
            """
        )
        # Post-call feedback screen (see server.py's /api/call-rating). One
        # row per session, upsert like call_summaries — there's only ever
        # one current rating worth keeping per call. tags is a JSON-encoded
        # list rather than its own table: a handful of short tag ids, same
        # "flexible shape, no migration for a new tag later" reasoning as
        # qualification_fields' field_name/field_value pair.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS call_ratings (
                visitor_id TEXT PRIMARY KEY,
                sentiment TEXT,
                reason TEXT,
                tags TEXT,
                call_duration_secs INTEGER,
                disconnect_reason TEXT,
                skipped INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        # Lifecycle events for the same feedback screen ("shown", "submitted",
        # "skipped") — append-only like transcript_turns, since funnel
        # drop-off (how many actually saw the prompt vs. acted on it) is
        # only answerable if every stage leaves its own row rather than
        # only the final outcome.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS call_rating_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                event TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_call_rating_events_visitor ON call_rating_events(visitor_id)")


class VisitorLookup(TypedDict):
    name: str
    company: str


class VisitorIdentity(TypedDict):
    """What get_visitor_identity() returns. name/company are Optional because
    a gate row can legitimately have neither — see list_visitors_summary."""

    email: str
    name: Optional[str]
    company: Optional[str]


def record_attempt(
    visitor_id: str,
    email: str,
    name: Optional[str],
    company: Optional[str],
    path: str,
    status: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO gate_attempts (visitor_id, email, name, company, path, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (visitor_id, email.strip().lower(), name, company, path, status, datetime.now(timezone.utc).isoformat()),
        )


def lookup_by_email(email: str) -> Optional[VisitorLookup]:
    """Most recent *allowed* attempt for this email — what lets the gate form
    skip straight to a Continue button for a returning visitor instead of
    asking for their name/company again."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT name, company FROM gate_attempts
            WHERE email = ? AND status = 'allowed'
            ORDER BY created_at DESC LIMIT 1
            """,
            (email.strip().lower(),),
        ).fetchone()
    if not row or not row["name"] or not row["company"]:
        return None
    return {"name": row["name"], "company": row["company"]}


def list_attempts(limit: int = 200, offset: int = 0) -> List[dict]:
    """Raw log, newest first — the admin panel's "Attempts" tab, including
    blocked personal-email rows."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, visitor_id, email, name, company, path, status, created_at
            FROM gate_attempts ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def list_visitors_summary() -> List[dict]:
    """One row per email — the admin panel's "Visitors" tab. Paths tried and
    session count come from every attempt (allowed or blocked) under that
    email; name/company shown are from the most recent *allowed* attempt,
    since a blocked attempt may have no name/company at all (see the
    email-first gate flow — blocked happens before those fields are shown)."""
    with _connect() as conn:
        emails = [r["email"] for r in conn.execute("SELECT DISTINCT email FROM gate_attempts").fetchall()]
        summaries = []
        for email in emails:
            rows = conn.execute(
                "SELECT * FROM gate_attempts WHERE email = ? ORDER BY created_at ASC",
                (email,),
            ).fetchall()
            latest_allowed = next((r for r in reversed(rows) if r["status"] == "allowed"), None)
            summaries.append(
                {
                    "email": email,
                    "name": latest_allowed["name"] if latest_allowed else None,
                    "company": latest_allowed["company"] if latest_allowed else None,
                    "first_seen_at": rows[0]["created_at"],
                    "last_seen_at": rows[-1]["created_at"],
                    "session_count": len(rows),
                    "paths_tried": sorted({r["path"] for r in rows}),
                    "ever_blocked": any(r["status"] != "allowed" for r in rows),
                }
            )
    summaries.sort(key=lambda s: s["last_seen_at"], reverse=True)
    return summaries


def get_visitor_detail(email: str) -> Optional[dict]:
    """Everything the admin panel's visitor detail view needs: the header
    (name/company/first-last seen) plus every individual session (gate
    attempt) under this email — each session's own visitor_id is what
    list_transcript() below is keyed on, since a returning visitor gets a
    fresh visitor_id every session (see frontend/src/lib/session.ts)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM gate_attempts WHERE email = ? ORDER BY created_at DESC",
            (email.strip().lower(),),
        ).fetchall()
    if not rows:
        return None
    latest_allowed = next((r for r in rows if r["status"] == "allowed"), None)
    return {
        "email": email.strip().lower(),
        "name": latest_allowed["name"] if latest_allowed else None,
        "company": latest_allowed["company"] if latest_allowed else None,
        "first_seen_at": rows[-1]["created_at"],
        "last_seen_at": rows[0]["created_at"],
        "sessions": [
            {
                "id": r["id"],
                "visitor_id": r["visitor_id"],
                "path": r["path"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    }


def _append_transcript_turn_once(visitor_id: str, role: str, text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO transcript_turns (visitor_id, role, text, created_at) VALUES (?, ?, ?, ?)",
            (visitor_id, role, text, datetime.now(timezone.utc).isoformat()),
        )


def append_transcript_turn(visitor_id: str, role: str, text: str) -> None:
    _write_with_retry(_append_transcript_turn_once, visitor_id, role, text)


def _amend_last_agent_turn_once(visitor_id: str, expected_text: str, new_text: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, text FROM transcript_turns WHERE visitor_id = ? AND role = 'agent' "
            "ORDER BY id DESC LIMIT 1",
            (visitor_id,),
        ).fetchone()
        if row is None or row["text"] != expected_text:
            return False
        conn.execute("UPDATE transcript_turns SET text = ? WHERE id = ?", (new_text, row["id"]))
    return True


def amend_last_agent_turn(visitor_id: str, expected_text: str, new_text: str) -> bool:
    """Rewrites the most recent agent row for this visitor, but ONLY if it
    still holds exactly `expected_text` — the caller's proof that the row it
    means to amend hasn't already been superseded by something else written
    since (a hand-raise handoff, a "still catching up" recovery line, the
    next turn entirely). Returns whether a row was actually changed.

    Used when a reply is cut off by a barge-in partway through being spoken:
    the row was written in full at finalize time, before anyone could know
    how much would actually be heard, so it gets corrected down to the
    spoken prefix afterward. See agent_processor's _amend_interrupted_turn."""
    return _write_with_retry(_amend_last_agent_turn_once, visitor_id, expected_text, new_text)


def list_transcript(visitor_id: str) -> List[dict]:
    """Oldest first — read top to bottom like an actual conversation, unlike
    the gate/attempts logs above which are newest-first audit trails."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, text, created_at FROM transcript_turns WHERE visitor_id = ? ORDER BY created_at ASC",
            (visitor_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _save_qualification_field_once(visitor_id: str, field_name: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO qualification_fields (visitor_id, field_name, field_value, created_at) VALUES (?, ?, ?, ?)",
            (visitor_id, field_name, value, datetime.now(timezone.utc).isoformat()),
        )


def save_qualification_field(visitor_id: str, field_name: str, value: str) -> None:
    _write_with_retry(_save_qualification_field_once, visitor_id, field_name, value)


def get_qualification_fields(visitor_id: str) -> dict:
    """Latest value per field_name for this visitor_id — a field is only
    ever written once per session (see runtime.py's "only set on the turn
    it's learned" pattern), but this takes the most recent row per name
    defensively rather than assuming that always holds."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT field_name, field_value FROM qualification_fields WHERE visitor_id = ? ORDER BY created_at ASC",
            (visitor_id,),
        ).fetchall()
    return {r["field_name"]: r["field_value"] for r in rows}


def _save_call_summary_once(visitor_id: str, summary: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO call_summaries (visitor_id, summary, generated_at) VALUES (?, ?, ?)
            ON CONFLICT(visitor_id) DO UPDATE SET summary = excluded.summary, generated_at = excluded.generated_at
            """,
            (visitor_id, summary, datetime.now(timezone.utc).isoformat()),
        )


def save_call_summary(visitor_id: str, summary: str) -> None:
    _write_with_retry(_save_call_summary_once, visitor_id, summary)


def get_call_summary(visitor_id: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT summary FROM call_summaries WHERE visitor_id = ?",
            (visitor_id,),
        ).fetchone()
    return row["summary"] if row else None


def _save_call_rating_once(
    visitor_id: str,
    sentiment: Optional[str],
    reason: Optional[str],
    tags: Optional[List[str]],
    call_duration_secs: Optional[int],
    disconnect_reason: Optional[str],
    skipped: bool,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO call_ratings
                (visitor_id, sentiment, reason, tags, call_duration_secs, disconnect_reason, skipped, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(visitor_id) DO UPDATE SET
                sentiment = excluded.sentiment,
                reason = excluded.reason,
                tags = excluded.tags,
                call_duration_secs = excluded.call_duration_secs,
                disconnect_reason = excluded.disconnect_reason,
                skipped = excluded.skipped,
                created_at = excluded.created_at
            """,
            (
                visitor_id,
                sentiment,
                reason,
                json.dumps(tags) if tags else None,
                call_duration_secs,
                disconnect_reason,
                1 if skipped else 0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def save_call_rating(
    visitor_id: str,
    sentiment: Optional[str],
    reason: Optional[str],
    tags: Optional[List[str]],
    call_duration_secs: Optional[int],
    disconnect_reason: Optional[str],
    skipped: bool,
) -> None:
    _write_with_retry(
        _save_call_rating_once,
        visitor_id,
        sentiment,
        reason,
        tags,
        call_duration_secs,
        disconnect_reason,
        skipped,
    )


def get_call_rating(visitor_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT sentiment, reason, tags, call_duration_secs, disconnect_reason, skipped, created_at
            FROM call_ratings WHERE visitor_id = ?
            """,
            (visitor_id,),
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["tags"] = json.loads(result["tags"]) if result["tags"] else []
    result["skipped"] = bool(result["skipped"])
    return result


def _log_call_rating_event_once(visitor_id: str, event: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO call_rating_events (visitor_id, event, created_at) VALUES (?, ?, ?)",
            (visitor_id, event, datetime.now(timezone.utc).isoformat()),
        )


def log_call_rating_event(visitor_id: str, event: str) -> None:
    _write_with_retry(_log_call_rating_event_once, visitor_id, event)


def list_call_rating_events(visitor_id: str) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT event, created_at FROM call_rating_events WHERE visitor_id = ? ORDER BY created_at ASC",
            (visitor_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_visitor_identity(visitor_id: str) -> Optional[VisitorIdentity]:
    """Who a given session belongs to — the reverse of the email-keyed lookups
    above, which can't answer this because a returning visitor gets a fresh
    visitor_id every session (see frontend/src/lib/session.ts). Needed by the
    post-call recap email, which starts from a visitor_id (that's all the
    call-summary path has) and has to work out where to send and who to
    address. Reads the newest allowed row so the name/company are the ones
    the visitor most recently confirmed at the gate."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT email, name, company FROM gate_attempts
            WHERE visitor_id = ? AND status = 'allowed'
            ORDER BY created_at DESC LIMIT 1
            """,
            (visitor_id,),
        ).fetchone()
    if not row:
        return None
    return {"email": row["email"], "name": row["name"], "company": row["company"]}


def create_otp_code(email: str, code: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO otp_codes (email, code, created_at) VALUES (?, ?, ?)",
            (email.strip().lower(), code, datetime.now(timezone.utc).isoformat()),
        )


def recent_otp_sends(email: str, within_seconds: int) -> List[datetime]:
    """Send timestamps for this email inside the given window, newest first —
    the raw material for both send limits in server.py (3 per 15 minutes, and
    the 30-second resend cooldown), returned as datetimes rather than a count
    so one query answers both without the caller re-deriving anything.

    Timestamps are parsed rather than compared as ISO strings: the string
    form only sorts correctly while every row shares an identical format, and
    a fractional-second difference is meaningless against a 15-minute window
    but not against a 30-second one."""
    cutoff = datetime.now(timezone.utc).timestamp() - within_seconds
    with _connect() as conn:
        rows = conn.execute(
            "SELECT created_at FROM otp_codes WHERE email = ? ORDER BY id DESC LIMIT 50",
            (email.strip().lower(),),
        ).fetchall()
    sends = []
    for r in rows:
        try:
            sent = datetime.fromisoformat(r["created_at"])
        except ValueError:
            continue
        if sent.timestamp() >= cutoff:
            sends.append(sent)
    return sends


def get_active_otp(email: str) -> Optional[dict]:
    """The single newest unconsumed code for this email. Only the newest one
    is ever live: requesting a fresh code has to invalidate the previous one,
    otherwise the 5-attempt cap means nothing — a caller could just keep
    requesting codes and keep guessing against every old one in parallel."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, code, created_at, attempts FROM otp_codes
            WHERE email = ? AND consumed = 0
            ORDER BY id DESC LIMIT 1
            """,
            (email.strip().lower(),),
        ).fetchone()
    return dict(row) if row else None


def burn_otp_codes(email: str) -> None:
    """Marks every outstanding code for this email consumed. Called just
    before issuing a new one — see get_active_otp for why only one code may
    be live at a time."""
    with _connect() as conn:
        conn.execute("UPDATE otp_codes SET consumed = 1 WHERE email = ? AND consumed = 0", (email.strip().lower(),))


def record_otp_attempt(otp_id: int) -> int:
    """Counts one verify attempt against a code and returns the new total.
    The increment happens before the code is compared (see server.py), so a
    wrong guess always costs an attempt even if the request dies afterward."""
    with _connect() as conn:
        conn.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?", (otp_id,))
        row = conn.execute("SELECT attempts FROM otp_codes WHERE id = ?", (otp_id,)).fetchone()
    return row["attempts"] if row else 0


def consume_otp(otp_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE otp_codes SET consumed = 1 WHERE id = ?", (otp_id,))


def summary_email_sent(visitor_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM summary_emails WHERE visitor_id = ?", (visitor_id,)).fetchone()
    return row is not None


def record_summary_email(visitor_id: str, email: str, message_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO summary_emails (visitor_id, email, message_id, sent_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(visitor_id) DO NOTHING
            """,
            (visitor_id, email.strip().lower(), message_id, datetime.now(timezone.utc).isoformat()),
        )


def get_stats() -> dict:
    """The admin dashboard's stat cards — deliberately just a handful of
    numbers that actually answer "how is the demo being used", not a
    kitchen-sink analytics dump."""
    with _connect() as conn:
        total_visitors = conn.execute("SELECT COUNT(DISTINCT email) FROM gate_attempts").fetchone()[0]
        total_sessions = conn.execute("SELECT COUNT(*) FROM gate_attempts WHERE status = 'allowed'").fetchone()[0]
        blocked_attempts = conn.execute("SELECT COUNT(*) FROM gate_attempts WHERE status != 'allowed'").fetchone()[0]
        dashboard_sessions = conn.execute(
            "SELECT COUNT(*) FROM gate_attempts WHERE status = 'allowed' AND path = 'dashboard'"
        ).fetchone()[0]
        meet_sessions = conn.execute(
            "SELECT COUNT(*) FROM gate_attempts WHERE status = 'allowed' AND path = 'meet'"
        ).fetchone()[0]
    recent = list_visitors_summary()[:5]
    return {
        "total_visitors": total_visitors,
        "total_sessions": total_sessions,
        "blocked_attempts": blocked_attempts,
        "dashboard_sessions": dashboard_sessions,
        "meet_sessions": meet_sessions,
        "recent_visitors": recent,
    }


init_db()
