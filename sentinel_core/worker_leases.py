"""Transactional SQLite worker lease primitives for retry jobs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


class RetryWorkerLeaseStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS retry_worker_leases (
                job_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                lease_expires_at TEXT NOT NULL,
                lease_token TEXT NOT NULL
            )"""
        )
        self.connection.commit()

    def claim_due(self, now: str, worker_id: str, lease_seconds: int, limit: int = 1) -> dict:
        current = _time(now)
        if current is None or not isinstance(worker_id, str) or not worker_id.strip() or not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds < 1 or not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            return {"action": "blocked", "reason": "claim_parameters_invalid"}
        expiry = (current + timedelta(seconds=lease_seconds)).isoformat()
        token = f"{worker_id}:{current.isoformat()}"
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            candidates = self.connection.execute(
                "SELECT job_id, payload_json FROM retry_jobs WHERE status='queued' AND due_at<=? ORDER BY due_at, job_id LIMIT ?",
                (current.isoformat(), limit),
            ).fetchall()
            claimed = []
            for job_id, payload in candidates:
                cursor = self.connection.execute("UPDATE retry_jobs SET status='claimed' WHERE job_id=? AND status='queued'", (job_id,))
                if cursor.rowcount == 1:
                    self.connection.execute("INSERT OR REPLACE INTO retry_worker_leases(job_id, worker_id, lease_expires_at, lease_token) VALUES(?,?,?,?)", (job_id, worker_id, expiry, token))
                    job = json.loads(payload)
                    job["status"] = "claimed"
                    self.connection.execute("UPDATE retry_jobs SET payload_json=? WHERE job_id=?", (json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=False), job_id))
                    claimed.append({"job": job, "lease": {"worker_id": worker_id, "lease_expires_at": expiry, "lease_token": token}})
            self.connection.commit()
            return {"action": "claimed", "jobs": claimed}
        except sqlite3.Error:
            self.connection.rollback()
            return {"action": "blocked", "reason": "storage_error"}

    def renew(self, job_id: str, worker_id: str, lease_token: str, now: str, lease_seconds: int) -> dict:
        current = _time(now)
        if current is None or not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds < 1:
            return {"action": "blocked", "reason": "renew_parameters_invalid"}
        row = self.connection.execute("SELECT lease_expires_at FROM retry_worker_leases WHERE job_id=? AND worker_id=? AND lease_token=?", (job_id, worker_id, lease_token)).fetchone()
        if row is None:
            return {"action": "blocked", "reason": "lease_not_owned"}
        expiry = _time(row[0])
        if expiry is None or expiry <= current:
            return {"action": "blocked", "reason": "lease_expired"}
        new_expiry = (current + timedelta(seconds=lease_seconds)).isoformat()
        self.connection.execute("UPDATE retry_worker_leases SET lease_expires_at=? WHERE job_id=? AND worker_id=? AND lease_token=?", (new_expiry, job_id, worker_id, lease_token))
        self.connection.commit()
        return {"action": "renewed", "lease_expires_at": new_expiry}

    def release(self, job_id: str, worker_id: str, lease_token: str, now: str) -> dict:
        current = _time(now)
        if current is None:
            return {"action": "blocked", "reason": "time_invalid"}
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute("SELECT lease_expires_at FROM retry_worker_leases WHERE job_id=? AND worker_id=? AND lease_token=?", (job_id, worker_id, lease_token)).fetchone()
            if row is None:
                self.connection.rollback()
                return {"action": "blocked", "reason": "lease_not_owned"}
            expiry = _time(row[0])
            if expiry is None or expiry <= current:
                self.connection.rollback()
                return {"action": "blocked", "reason": "lease_expired"}
            self.connection.execute("DELETE FROM retry_worker_leases WHERE job_id=?", (job_id,))
            row_job = self.connection.execute("SELECT payload_json FROM retry_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row_job is not None:
                job = json.loads(row_job[0])
                job["status"] = "queued"
                self.connection.execute("UPDATE retry_jobs SET status='queued', payload_json=? WHERE job_id=? AND status='claimed'", (json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=False), job_id))
            self.connection.commit()
            return {"action": "released"}
        except sqlite3.Error:
            self.connection.rollback()
            return {"action": "blocked", "reason": "storage_error"}

    def complete(self, job_id: str, worker_id: str, lease_token: str, outcome: str, now: str) -> dict:
        current = _time(now)
        if current is None or outcome not in {"completed", "failed"}:
            return {"action": "blocked", "reason": "completion_parameters_invalid"}
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute("SELECT lease_expires_at FROM retry_worker_leases WHERE job_id=? AND worker_id=? AND lease_token=?", (job_id, worker_id, lease_token)).fetchone()
            if row is None:
                self.connection.rollback()
                return {"action": "blocked", "reason": "lease_not_owned"}
            expiry = _time(row[0])
            if expiry is None or expiry <= current:
                self.connection.rollback()
                return {"action": "blocked", "reason": "lease_expired"}
            row_job = self.connection.execute("SELECT payload_json FROM retry_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row_job is not None:
                job = json.loads(row_job[0])
                job["status"] = outcome
                self.connection.execute("UPDATE retry_jobs SET status=?, payload_json=? WHERE job_id=? AND status='claimed'", (outcome, json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=False), job_id))
            self.connection.execute("DELETE FROM retry_worker_leases WHERE job_id=?", (job_id,))
            self.connection.commit()
            return {"action": "completed", "status": outcome}
        except sqlite3.Error:
            self.connection.rollback()
            return {"action": "blocked", "reason": "storage_error"}
