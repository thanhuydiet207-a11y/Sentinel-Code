"""Read-only operational snapshot for retry pipeline SQLite stores."""
from __future__ import annotations

import sqlite3
from typing import Any


def retry_queue_snapshot(connection: sqlite3.Connection, now: str) -> dict:
    """Summarize queue, lease, and reservation state without mutation."""
    if not isinstance(now, str) or not now.strip():
        return {"action": "blocked", "reason": "snapshot_time_invalid"}
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"retry_jobs", "retry_worker_leases", "retry_reservations", "atomic_retry_jobs"}
    missing = sorted(expected - tables)
    if missing:
        return {"action": "blocked", "reason": "tables_missing", "missing_tables": missing}
    try:
        queue_rows = connection.execute("SELECT status, COUNT(*) FROM retry_jobs GROUP BY status").fetchall()
        lease_count = connection.execute("SELECT COUNT(*) FROM retry_worker_leases").fetchone()[0]
        expired_leases = connection.execute("SELECT COUNT(*) FROM retry_worker_leases WHERE lease_expires_at<=?", (now,)).fetchone()[0]
        due_queued = connection.execute("SELECT COUNT(*) FROM retry_jobs WHERE status='queued' AND due_at<=?", (now,)).fetchone()[0]
        reservations = connection.execute("SELECT status, COUNT(*) FROM retry_reservations GROUP BY status").fetchall()
        atomic_rows = connection.execute("SELECT status, COUNT(*) FROM atomic_retry_jobs GROUP BY status").fetchall()
        return {
            "action": "snapshot",
            "at": now,
            "queue": {status: int(count) for status, count in queue_rows},
            "due_queued": int(due_queued),
            "leases": {"active": int(lease_count), "expired": int(expired_leases)},
            "reservations": {status: int(count) for status, count in reservations},
            "atomic_jobs": {status: int(count) for status, count in atomic_rows},
        }
    except sqlite3.Error:
        return {"action": "blocked", "reason": "storage_error"}
