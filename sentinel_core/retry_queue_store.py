"""SQLite persistence adapter for retry jobs with transactional enqueue/cancel."""
from __future__ import annotations

import json
import sqlite3
from typing import Any


class RetryQueueStore:
    """SQLite-backed retry queue. Caller owns connection lifecycle and durability settings."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS retry_jobs (
                job_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                attempt_number INTEGER,
                status TEXT NOT NULL CHECK(status IN ('queued', 'cancelled', 'claimed', 'completed', 'failed')),
                scheduled_at TEXT NOT NULL,
                due_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )"""
        )
        self.connection.commit()

    def enqueue(self, job: Any) -> dict:
        if not isinstance(job, dict) or job.get("schema") != 1:
            return {"action": "blocked", "reason": "job_invalid"}
        required = ("job_id", "workflow_id", "stage", "execution_id", "scheduled_at", "due_at", "status")
        if any(not isinstance(job.get(field), str) or not job[field] for field in required):
            return {"action": "blocked", "reason": "job_fields_invalid"}
        if job["status"] != "queued":
            return {"action": "blocked", "reason": "job_not_queued"}
        payload = json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        try:
            self.connection.execute(
                "INSERT INTO retry_jobs(job_id, workflow_id, stage, execution_id, attempt_number, status, scheduled_at, due_at, payload_json) VALUES(?,?,?,?,?,?,?,?,?)",
                (job["job_id"], job["workflow_id"], job["stage"], job["execution_id"], job.get("attempt_number"), job["status"], job["scheduled_at"], job["due_at"], payload),
            )
            self.connection.commit()
        except sqlite3.IntegrityError:
            self.connection.rollback()
            return {"action": "blocked", "reason": "job_id_duplicate"}
        return {"action": "stored", "job_id": job["job_id"]}

    def get(self, job_id: str) -> dict:
        row = self.connection.execute("SELECT payload_json FROM retry_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            return {"action": "not_found"}
        return {"action": "found", "job": json.loads(row[0])}

    def list_due(self, now: str, limit: int = 100) -> dict:
        if not isinstance(now, str) or not now or not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            return {"action": "blocked", "reason": "query_parameters_invalid"}
        rows = self.connection.execute(
            "SELECT payload_json FROM retry_jobs WHERE status='queued' AND due_at<=? ORDER BY due_at, job_id LIMIT ?",
            (now, limit),
        ).fetchall()
        return {"action": "listed", "jobs": [json.loads(row[0]) for row in rows]}

    def cancel(self, job_id: str, cancelled_at: str) -> dict:
        if not isinstance(cancelled_at, str) or not cancelled_at:
            return {"action": "blocked", "reason": "cancelled_at_invalid"}
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute("SELECT payload_json, status FROM retry_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                self.connection.rollback()
                return {"action": "not_found"}
            if row[1] != "queued":
                self.connection.rollback()
                return {"action": "blocked", "reason": "job_not_queued"}
            job = json.loads(row[0])
            job["status"] = "cancelled"
            job["cancelled_at"] = cancelled_at
            payload = json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            self.connection.execute("UPDATE retry_jobs SET status='cancelled', payload_json=? WHERE job_id=? AND status='queued'", (payload, job_id))
            self.connection.commit()
            return {"action": "cancelled", "job": job}
        except sqlite3.Error:
            self.connection.rollback()
            return {"action": "blocked", "reason": "storage_error"}

    def close(self) -> None:
        """Close the caller-provided connection."""
        self.connection.close()
