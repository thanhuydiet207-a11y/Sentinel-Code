"""Pure health assessment for retry queue snapshots."""
from __future__ import annotations

from typing import Any


def assess_retry_health(snapshot: Any, thresholds: Any = None) -> dict:
    if not isinstance(snapshot, dict) or snapshot.get("action") != "snapshot":
        return {"action": "blocked", "reason": "snapshot_invalid"}
    if thresholds is None:
        thresholds = {}
    if not isinstance(thresholds, dict):
        return {"action": "blocked", "reason": "thresholds_invalid"}
    max_due = thresholds.get("max_due_queued", 100)
    max_expired = thresholds.get("max_expired_leases", 0)
    max_active = thresholds.get("max_active_leases", 1000)
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (max_due, max_expired, max_active)):
        return {"action": "blocked", "reason": "thresholds_invalid"}
    queue = snapshot.get("queue", {})
    leases = snapshot.get("leases", {})
    due = snapshot.get("due_queued")
    expired = leases.get("expired") if isinstance(leases, dict) else None
    active = leases.get("active") if isinstance(leases, dict) else None
    if not isinstance(queue, dict) or any(not isinstance(v, int) or v < 0 for v in queue.values()):
        return {"action": "blocked", "reason": "snapshot_queue_invalid"}
    if any(not isinstance(v, int) or v < 0 for v in (due, expired, active)):
        return {"action": "blocked", "reason": "snapshot_lease_metrics_invalid"}
    findings = []
    if due > max_due:
        findings.append({"severity": "warning", "code": "due_queue_backlog", "value": due, "threshold": max_due})
    if expired > max_expired:
        findings.append({"severity": "critical", "code": "expired_leases", "value": expired, "threshold": max_expired})
    if active > max_active:
        findings.append({"severity": "warning", "code": "active_leases_high", "value": active, "threshold": max_active})
    status = "critical" if any(f["severity"] == "critical" for f in findings) else "warning" if findings else "healthy"
    return {"action": "assessed", "status": status, "findings": findings, "metrics": {"due_queued": due, "expired_leases": expired, "active_leases": active}}
