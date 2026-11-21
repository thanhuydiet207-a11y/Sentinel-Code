"""Durable SQLite idempotency reservation store."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotencyStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS idempotency_records (
                key_digest TEXT PRIMARY KEY,
                payload_digest TEXT NOT NULL,
                execution_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('reserved','running','completed','failed'))
            )"""
        )
        self.connection.commit()

    def reserve(self, key: Any, payload: Any, execution_id: Any) -> dict:
        if not isinstance(key, str) or not key.strip() or not isinstance(execution_id, str) or not execution_id.strip():
            return {"action": "blocked", "reason": "reservation_inputs_invalid"}
        key_digest = _hash(key)
        payload_digest = _payload_hash(payload)
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self.connection.execute("SELECT payload_digest, execution_id, status FROM idempotency_records WHERE key_digest=?", (key_digest,)).fetchone()
            if existing:
                self.connection.rollback()
                if existing[0] != payload_digest:
                    return {"action": "blocked", "reason": "idempotency_key_payload_conflict"}
                return {"action": "replay", "record": {"key_digest": key_digest, "payload_digest": existing[0], "execution_id": existing[1], "status": existing[2]}}
            self.connection.execute("INSERT INTO idempotency_records(key_digest, payload_digest, execution_id, status) VALUES(?,?,?,'reserved')", (key_digest, payload_digest, execution_id))
            self.connection.commit()
            return {"action": "reserved", "record": {"key_digest": key_digest, "payload_digest": payload_digest, "execution_id": execution_id, "status": "reserved"}}
        except sqlite3.IntegrityError:
            self.connection.rollback()
            return {"action": "blocked", "reason": "execution_id_duplicate"}
        except sqlite3.Error:
            self.connection.rollback()
            return {"action": "blocked", "reason": "storage_error"}

    def transition(self, key: Any, new_status: Any) -> dict:
        if not isinstance(key, str) or not key or new_status not in {"running", "completed", "failed"}:
            return {"action": "blocked", "reason": "transition_inputs_invalid"}
        key_digest = _hash(key)
        allowed = {"reserved": {"running", "failed"}, "running": {"completed", "failed"}, "completed": set(), "failed": set()}
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute("SELECT payload_digest, execution_id, status FROM idempotency_records WHERE key_digest=?", (key_digest,)).fetchone()
            if row is None:
                self.connection.rollback()
                return {"action": "not_found"}
            if new_status not in allowed.get(row[2], set()):
                self.connection.rollback()
                return {"action": "blocked", "reason": "transition_invalid", "current_status": row[2]}
            self.connection.execute("UPDATE idempotency_records SET status=? WHERE key_digest=?", (new_status, key_digest))
            self.connection.commit()
            return {"action": "updated", "record": {"key_digest": key_digest, "payload_digest": row[0], "execution_id": row[1], "status": new_status}}
        except sqlite3.Error:
            self.connection.rollback()
            return {"action": "blocked", "reason": "storage_error"}

    def get(self, key: Any) -> dict:
        if not isinstance(key, str) or not key:
            return {"action": "blocked", "reason": "key_invalid"}
        row = self.connection.execute("SELECT payload_digest, execution_id, status FROM idempotency_records WHERE key_digest=?", (_hash(key),)).fetchone()
        if row is None:
            return {"action": "not_found"}
        return {"action": "found", "record": {"key_digest": _hash(key), "payload_digest": row[0], "execution_id": row[1], "status": row[2]}}

    def count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()
        return int(row[0])
