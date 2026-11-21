"""Read-only integrity audit for retry pipeline persistence tables."""
from __future__ import annotations

import json
import sqlite3
from typing import Any


_EXPECTED = {"retry_jobs", "retry_worker_leases", "retry_reservations", "atomic_retry_jobs"}


def audit_retry_pipeline(connection: sqlite3.Connection) -> dict:
    """Audit cross-table invariants; report findings without changing the database."""
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = sorted(_EXPECTED - tables)
        if missing:
            return {"action": "blocked", "reason": "tables_missing", "missing_tables": missing}

        findings: list[dict[str, Any]] = []
        retry_rows = connection.execute(
            "SELECT job_id, status, payload_json FROM retry_jobs"
        ).fetchall()
        leases = connection.execute(
            "SELECT job_id, worker_id, lease_expires_at, lease_token FROM retry_worker_leases"
        ).fetchall()
        reservations = connection.execute(
            "SELECT key_digest, execution_id, status FROM retry_reservations"
        ).fetchall()
        atomic_rows = connection.execute(
            "SELECT job_id, key_digest, status, job_json FROM atomic_retry_jobs"
        ).fetchall()

        retry_by_id = {row[0]: row for row in retry_rows}
        lease_by_job = {row[0]: row for row in leases}
        reservation_keys = {row[0] for row in reservations}
        atomic_by_key = {row[1]: row for row in atomic_rows}

        for job_id, db_status, raw in retry_rows:
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                findings.append({"code": "retry_payload_invalid", "job_id": job_id})
                continue
            if not isinstance(payload, dict):
                findings.append({"code": "retry_payload_shape_invalid", "job_id": job_id})
                continue
            if payload.get("job_id") != job_id:
                findings.append({"code": "retry_job_id_mismatch", "job_id": job_id})
            if payload.get("status") != db_status:
                findings.append({"code": "retry_status_mismatch", "job_id": job_id})
            if db_status == "claimed" and job_id not in lease_by_job:
                findings.append({"code": "claimed_job_without_lease", "job_id": job_id})

        for job_id, _worker, _expires, _token in leases:
            if job_id not in retry_by_id:
                findings.append({"code": "lease_without_job", "job_id": job_id})
            elif retry_by_id[job_id][1] != "claimed":
                findings.append({"code": "lease_for_unclaimed_job", "job_id": job_id})

        for key_digest in reservation_keys - set(atomic_by_key):
            findings.append({"code": "reservation_without_atomic_job"})
        for key_digest, row in atomic_by_key.items():
            job_id, _stored_key_digest, _status, raw = row
            if key_digest not in reservation_keys:
                findings.append({"code": "atomic_job_without_reservation", "job_id": job_id})
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                findings.append({"code": "atomic_payload_invalid", "job_id": job_id})
                continue
            if not isinstance(payload, dict):
                findings.append({"code": "atomic_payload_shape_invalid", "job_id": job_id})
                continue
            if payload.get("job_id") != job_id:
                findings.append({"code": "atomic_job_id_mismatch", "job_id": job_id})
            if payload.get("status") != _status:
                findings.append({"code": "atomic_status_mismatch", "job_id": job_id})

        counts = {
            "retry_jobs": len(retry_rows),
            "leases": len(leases),
            "reservations": len(reservations),
            "atomic_jobs": len(atomic_rows),
        }
        return {"action": "audited", "valid": not findings, "counts": counts, "findings": findings}
    except sqlite3.Error:
        return {"action": "blocked", "reason": "storage_error"}
