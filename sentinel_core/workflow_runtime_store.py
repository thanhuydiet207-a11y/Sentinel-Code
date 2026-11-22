"""SQLite-backed durable workflow runtime snapshots and event journal."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any


_ALLOWED_STATUS = {"ready", "running", "completed", "failed", "cancelled", "blocked"}


def _valid_time(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _json_object(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return None


class DurableWorkflowRuntimeStore:
    """Persist runtime snapshots with optimistic versions and append-only events.

    The caller owns connection lifecycle and SQLite durability configuration.
    All writes use explicit transactions; version conflicts fail closed.
    """

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS workflow_runtime_executions (
                execution_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('ready','running','completed','failed','cancelled','blocked')),
                version INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS workflow_runtime_events (
                execution_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                PRIMARY KEY(execution_id, sequence),
                FOREIGN KEY(execution_id) REFERENCES workflow_runtime_executions(execution_id)
            )"""
        )
        self.connection.commit()

    def create(self, execution_id: str, workflow_id: str, snapshot: Any, status: str, at: str, events: Any = None) -> dict:
        if not isinstance(execution_id, str) or not execution_id.strip() or not isinstance(workflow_id, str) or not workflow_id.strip():
            return {"action": "blocked", "reason": "identifiers_invalid"}
        encoded = _json_object(snapshot)
        if encoded is None:
            return {"action": "blocked", "reason": "snapshot_invalid"}
        if status not in _ALLOWED_STATUS:
            return {"action": "blocked", "reason": "status_invalid"}
        if not _valid_time(at):
            return {"action": "blocked", "reason": "timestamp_invalid"}
        normalized_events = self._validate_events(events or [])
        if normalized_events is None:
            return {"action": "blocked", "reason": "events_invalid"}
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute(
                "INSERT INTO workflow_runtime_executions(execution_id,workflow_id,status,version,snapshot_json,updated_at) VALUES(?,?,?,?,?,?)",
                (execution_id, workflow_id, status, 1, encoded, at),
            )
            for event in normalized_events:
                self.connection.execute(
                    "INSERT INTO workflow_runtime_events(execution_id,sequence,event_json) VALUES(?,?,?)",
                    (execution_id, event["sequence"], json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)),
                )
            self.connection.commit()
            return {"action": "created", "execution_id": execution_id, "version": 1}
        except sqlite3.IntegrityError:
            self.connection.rollback()
            return {"action": "blocked", "reason": "execution_id_duplicate"}
        except sqlite3.Error:
            self.connection.rollback()
            return {"action": "blocked", "reason": "storage_error"}

    @staticmethod
    def _validate_events(events: Any) -> list[dict] | None:
        if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
            return None
        normalized = []
        seen = set()
        for event in events:
            sequence = event.get("sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1 or sequence in seen:
                return None
            if not _valid_time(event.get("at")) or not isinstance(event.get("type"), str) or not event["type"].strip():
                return None
            if _json_object(event) is None:
                return None
            seen.add(sequence)
            normalized.append(event)
        return sorted(normalized, key=lambda event: event["sequence"])

    def load(self, execution_id: str, include_events: bool = False) -> dict:
        try:
            row = self.connection.execute(
                "SELECT workflow_id,status,version,snapshot_json,updated_at FROM workflow_runtime_executions WHERE execution_id=?",
                (execution_id,),
            ).fetchone()
            if row is None:
                return {"action": "not_found"}
            result = {"action": "loaded", "execution_id": execution_id, "workflow_id": row[0], "status": row[1], "version": row[2], "snapshot": json.loads(row[3]), "updated_at": row[4]}
            if include_events:
                rows = self.connection.execute("SELECT event_json FROM workflow_runtime_events WHERE execution_id=? ORDER BY sequence", (execution_id,)).fetchall()
                result["events"] = [json.loads(event[0]) for event in rows]
            return result
        except (sqlite3.Error, json.JSONDecodeError):
            return {"action": "blocked", "reason": "storage_error"}

    def save(self, execution_id: str, expected_version: int, snapshot: Any, status: str, at: str, events: Any = None) -> dict:
        encoded = _json_object(snapshot)
        if encoded is None:
            return {"action": "blocked", "reason": "snapshot_invalid"}
        if not isinstance(expected_version, int) or isinstance(expected_version, bool) or expected_version < 1:
            return {"action": "blocked", "reason": "version_invalid"}
        if status not in _ALLOWED_STATUS:
            return {"action": "blocked", "reason": "status_invalid"}
        if not _valid_time(at):
            return {"action": "blocked", "reason": "timestamp_invalid"}
        normalized_events = self._validate_events(events or [])
        if normalized_events is None:
            return {"action": "blocked", "reason": "events_invalid"}
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            cursor = self.connection.execute(
                "UPDATE workflow_runtime_executions SET status=?,version=version+1,snapshot_json=?,updated_at=? WHERE execution_id=? AND version=?",
                (status, encoded, at, execution_id, expected_version),
            )
            if cursor.rowcount != 1:
                row = self.connection.execute("SELECT version FROM workflow_runtime_executions WHERE execution_id=?", (execution_id,)).fetchone()
                self.connection.rollback()
                if row is None:
                    return {"action": "not_found"}
                return {"action": "conflict", "current_version": row[0]}
            for event in normalized_events:
                self.connection.execute(
                    "INSERT INTO workflow_runtime_events(execution_id,sequence,event_json) VALUES(?,?,?)",
                    (execution_id, event["sequence"], json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)),
                )
            self.connection.commit()
            return {"action": "saved", "execution_id": execution_id, "version": expected_version + 1}
        except sqlite3.IntegrityError:
            self.connection.rollback()
            return {"action": "blocked", "reason": "event_sequence_duplicate"}
        except sqlite3.Error:
            self.connection.rollback()
            return {"action": "blocked", "reason": "storage_error"}

    def list_recoverable(self, limit: int = 100) -> dict:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            return {"action": "blocked", "reason": "limit_invalid"}
        try:
            rows = self.connection.execute(
                "SELECT execution_id,workflow_id,status,version,updated_at FROM workflow_runtime_executions WHERE status IN ('ready','running') ORDER BY updated_at,execution_id LIMIT ?",
                (limit,),
            ).fetchall()
            return {"action": "listed", "executions": [
                {"execution_id": row[0], "workflow_id": row[1], "status": row[2], "version": row[3], "updated_at": row[4]}
                for row in rows
            ]}
        except sqlite3.Error:
            return {"action": "blocked", "reason": "storage_error"}

    def close(self) -> None:
        self.connection.close()
