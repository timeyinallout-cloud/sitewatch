"""Job/message store for the chat UI -- SQLite, stdlib only, same
_connect/_cursor shape Fleetboard/Foreman's own jobs.py use.

`jobs` is the source of truth for what a sweep/accept action did; `messages`
is purely rendering state for the chat thread so it survives a page reload,
updated lazily the first time a terminal job status is observed.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path(
    os.environ.get("SITEWATCH_DB_PATH", Path(os.environ.get("SITEWATCH_DATA_DIR", "/data")) / "sitewatch.db")
)

ACTIVE_STATUSES = ("queued", "running")


class TargetBusyError(RuntimeError):
    """A job is already queued/running for this target (see the unique
    partial index on jobs.target)."""
    def __init__(self, existing_job_id: str):
        self.existing_job_id = existing_job_id
        super().__init__(f"a job is already active for this target: {existing_job_id}")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def cursor(db_path: Path | None = None):
    conn = _connect(db_path or DEFAULT_DB_PATH)
    try:
        yield conn.cursor()
        conn.commit()
    finally:
        conn.close()


_cursor = cursor


def init_db(db_path: Path | None = None) -> None:
    with _cursor(db_path or DEFAULT_DB_PATH) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                started_at TEXT,
                finished_at TEXT,
                kind TEXT NOT NULL CHECK (kind IN ('sweep','accept')),
                target TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','running','complete','failed')),
                source TEXT NOT NULL CHECK (source IN ('button','typed')),
                summary TEXT,
                detail TEXT,
                error TEXT
            )
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_target
                ON jobs(target) WHERE status IN ('queued','running')
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                role TEXT NOT NULL CHECK (role IN ('user','bot')),
                text TEXT NOT NULL,
                job_id TEXT REFERENCES jobs(id),
                actions_json TEXT
            )
        """)


def create_job(kind: str, target: str, source: str, db_path: Path | None = None) -> str:
    job_id = uuid.uuid4().hex
    try:
        with _cursor(db_path or DEFAULT_DB_PATH) as cur:
            cur.execute(
                "INSERT INTO jobs (id, kind, target, source) VALUES (?, ?, ?, ?)",
                (job_id, kind, target, source),
            )
    except sqlite3.IntegrityError as e:
        existing = get_active_job_for_target(target, db_path)
        if existing is not None:
            raise TargetBusyError(existing["id"]) from e
        raise
    return job_id


def get_active_job_for_target(target: str, db_path: Path | None = None) -> sqlite3.Row | None:
    with _cursor(db_path or DEFAULT_DB_PATH) as cur:
        cur.execute(
            "SELECT * FROM jobs WHERE target = ? AND status IN ('queued','running') "
            "ORDER BY created_at DESC LIMIT 1",
            (target,),
        )
        return cur.fetchone()


def get_job(job_id: str, db_path: Path | None = None) -> sqlite3.Row | None:
    with _cursor(db_path or DEFAULT_DB_PATH) as cur:
        cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return cur.fetchone()


def get_last_complete_job(kind: str, target: str, db_path: Path | None = None) -> sqlite3.Row | None:
    with _cursor(db_path or DEFAULT_DB_PATH) as cur:
        cur.execute(
            "SELECT * FROM jobs WHERE kind = ? AND target = ? AND status = 'complete' "
            "ORDER BY finished_at DESC LIMIT 1",
            (kind, target),
        )
        return cur.fetchone()


def get_last_complete_sweep(db_path: Path | None = None) -> sqlite3.Row | None:
    """The most recent completed sweep (any target) -- used by the chat's
    "status" command, which reports "what happened last" rather than a
    specific site's history. `kind='sweep'` covers both the GitHub Actions
    and local-fallback paths; which one actually ran is in `detail.origin`,
    decided only at execution time (see sweep_ops.py), not at creation."""
    with _cursor(db_path or DEFAULT_DB_PATH) as cur:
        cur.execute(
            "SELECT * FROM jobs WHERE kind = 'sweep' AND status = 'complete' "
            "ORDER BY finished_at DESC LIMIT 1"
        )
        return cur.fetchone()


def start_job(job_id: str, db_path: Path | None = None) -> None:
    with _cursor(db_path or DEFAULT_DB_PATH) as cur:
        cur.execute(
            "UPDATE jobs SET status = 'running', started_at = datetime('now') WHERE id = ?",
            (job_id,),
        )


def finish_job(job_id: str, status: str, *, summary: str = "",
                detail: object = None, error: str = "", db_path: Path | None = None) -> None:
    if status not in ("complete", "failed"):
        raise ValueError(f"finish_job status must be complete/failed, got {status!r}")
    with _cursor(db_path or DEFAULT_DB_PATH) as cur:
        cur.execute(
            "UPDATE jobs SET status = ?, finished_at = datetime('now'), "
            "summary = ?, detail = ?, error = ? WHERE id = ?",
            (status, summary, json.dumps(detail), error, job_id),
        )


def add_message(role: str, text: str, *, job_id: str | None = None,
                 actions: list[dict] | None = None, db_path: Path | None = None) -> str:
    msg_id = uuid.uuid4().hex
    with _cursor(db_path or DEFAULT_DB_PATH) as cur:
        cur.execute(
            "INSERT INTO messages (id, role, text, job_id, actions_json) VALUES (?, ?, ?, ?, ?)",
            (msg_id, role, text, job_id, json.dumps(actions) if actions is not None else None),
        )
    return msg_id


def list_messages(db_path: Path | None = None) -> list[sqlite3.Row]:
    with _cursor(db_path or DEFAULT_DB_PATH) as cur:
        cur.execute("SELECT * FROM messages ORDER BY created_at ASC")
        return cur.fetchall()


def update_message_for_job(job_id: str, text: str, actions: list[dict] | None,
                            db_path: Path | None = None) -> None:
    with _cursor(db_path or DEFAULT_DB_PATH) as cur:
        cur.execute(
            "UPDATE messages SET text = ?, actions_json = ? WHERE job_id = ?",
            (text, json.dumps(actions) if actions is not None else None, job_id),
        )
