"""Atomic SQLite reservation plus retry-job persistence."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


class AtomicRetryPreparationStore:
    """Persist idempotency reservation and retry job in a single SQLite transaction."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS retry_reservations (
                key_digest TEXT PRIMARY KEY,
                payload_digest TEXT NOT NULL,
                execution_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('reserved','running','completed','failed'))
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS atomic_retry_jobs (
                job_id TEXT PRIMARY KEY,
                key_digest TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('queued','cancelled','claimed','completed','failed')),
                job_json TEXT NOT NULL,
                FOREIGN KEY(key_digest) REFERENCES retry_reservations(key_digest)
            )"""
        )
        self.connection.commit()

    def prepare(self, key: Any, payload: Any, execution_id: Any, job: Any) -> dict:
        if not isinstance(key, str) or not key.strip() or not isinstance(execution_id, str) or not execution_id.strip():
            return {"action": "blocked", "reason": "reservation_inputs_invalid"}
        if not isinstance(job, dict) or job.get("schema") != 1 or job.get("status") != "queued" or not isinstance(job.get("job_id"), str) or not job["job_id"]:
            return {"action": "blocked", "reason": "retry_job_invalid"}
        key_digest, payload_digest = _digest(key), _payload_digest(payload)
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self.connection.execute("SELECT payload_digest, execution_id, status FROM retry_reservations WHERE key_digest=?", (key_digest,)).fetchone()
            if existing:
                self.connection.rollback()
                if existing[0] != payload_digest:
                    return {"action": "blocked", "reason": "idempotency_key_payload_conflict"}
                return {"action": "replay", "record": {"key_digest": key_digest, "payload_digest": existing[0], "execution_id": existing[1], "status": existing[2]}}
            self.connection.execute("INSERT INTO retry_reservations(key_digest, payload_digest, execution_id, status) VALUES(?,?,?,'reserved')", (key_digest, payload_digest, execution_id))
            self.connection.execute("INSERT INTO atomic_retry_jobs(job_id, key_digest, status, job_json) VALUES(?,?,?,?)", (job["job_id"], key_digest, "queued", json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=False)))
            self.connection.commit()
            return {"action": "prepared", "record": {"key_digest": key_digest, "payload_digest": payload_digest, "execution_id": execution_id, "status": "reserved"}, "job": job}
        except sqlite3.IntegrityError:
            self.connection.rollback()
            return {"action": "blocked", "reason": "unique_constraint_conflict"}
        except sqlite3.Error:
            self.connection.rollback()
            return {"action": "blocked", "reason": "storage_error"}

    def get_job(self, job_id: str) -> dict:
        row = self.connection.execute("SELECT job_json, status FROM atomic_retry_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            return {"action": "not_found"}
        job = json.loads(row[0])
        job["status"] = row[1]
        return {"action": "found", "job": job}

    def counts(self) -> dict:
        reservations = self.connection.execute("SELECT COUNT(*) FROM retry_reservations").fetchone()[0]
        jobs = self.connection.execute("SELECT COUNT(*) FROM atomic_retry_jobs").fetchone()[0]
        return {"reservations": int(reservations), "jobs": int(jobs)}
    def audit(self) -> dict:
        """Report reservation/job inconsistencies without mutating persistent state."""
        errors = []
        reservations = self.connection.execute("SELECT key_digest, payload_digest, execution_id, status FROM retry_reservations").fetchall()
        jobs = self.connection.execute("SELECT job_id, key_digest, status, job_json FROM atomic_retry_jobs").fetchall()
        reservation_keys = {row[0] for row in reservations}
        job_keys = {row[1] for row in jobs}
        for key_digest in reservation_keys - job_keys:
            errors.append({"kind": "reservation_without_job", "key_digest": key_digest})
        for key_digest in job_keys - reservation_keys:
            errors.append({"kind": "job_without_reservation", "key_digest": key_digest})
        for job_id, key_digest, status, raw in jobs:
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                errors.append({"kind": "job_payload_invalid", "job_id": job_id})
                continue
            if payload.get("status") != status:
                errors.append({"kind": "job_status_mismatch", "job_id": job_id, "database_status": status, "payload_status": payload.get("status")})
        return {"valid": not errors, "errors": errors, "reservation_count": len(reservations), "job_count": len(jobs)}
