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

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, List, Optional, TypedDict

DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


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


class VisitorLookup(TypedDict):
    name: str
    company: str


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


def append_transcript_turn(visitor_id: str, role: str, text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO transcript_turns (visitor_id, role, text, created_at) VALUES (?, ?, ?, ?)",
            (visitor_id, role, text, datetime.now(timezone.utc).isoformat()),
        )


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


def list_transcript(visitor_id: str) -> List[dict]:
    """Oldest first — read top to bottom like an actual conversation, unlike
    the gate/attempts logs above which are newest-first audit trails."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, text, created_at FROM transcript_turns WHERE visitor_id = ? ORDER BY created_at ASC",
            (visitor_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_qualification_field(visitor_id: str, field_name: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO qualification_fields (visitor_id, field_name, field_value, created_at) VALUES (?, ?, ?, ?)",
            (visitor_id, field_name, value, datetime.now(timezone.utc).isoformat()),
        )


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


def save_call_summary(visitor_id: str, summary: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO call_summaries (visitor_id, summary, generated_at) VALUES (?, ?, ?)
            ON CONFLICT(visitor_id) DO UPDATE SET summary = excluded.summary, generated_at = excluded.generated_at
            """,
            (visitor_id, summary, datetime.now(timezone.utc).isoformat()),
        )


def get_call_summary(visitor_id: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT summary FROM call_summaries WHERE visitor_id = ?",
            (visitor_id,),
        ).fetchone()
    return row["summary"] if row else None


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
