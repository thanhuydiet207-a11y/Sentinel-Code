"""Explainable false-positive triage heuristics. Never suppress findings automatically."""
from __future__ import annotations

from typing import Any

def analyze_findings(payload: dict[str, Any]) -> dict[str, Any]:
    findings = payload.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("findings must be an array")
    results = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        reasons = []
        evidence = finding.get("evidence") or {}
        location = finding.get("location") or {}
        confidence = finding.get("confidence", 0)
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            confidence = 0
        if confidence < 0.4:
            reasons.append("low scanner confidence")
        if not evidence.get("reason"):
            reasons.append("missing evidence explanation")
        digest = evidence.get("line_hash", "")
        if not isinstance(digest, str) or len(digest) != 64:
            reasons.append("missing or malformed source evidence hash")
        start, end = location.get("start_line"), location.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            reasons.append("invalid source line range")
        if finding.get("severity") == "info":
            reasons.append("informational severity")
        title = str(finding.get("title", "")).lower()
        generic = ("potential", "possible", "might", "could", "generic")
        if any(word in title for word in generic):
            reasons.append("generic or uncertainty wording in title")
        if not reasons:
            disposition = "review"
            score = 0.0
        else:
            disposition = "needs_review"
            score = min(0.95, round(0.2 + 0.15 * len(reasons), 2))
        results.append({
            "finding_id": finding.get("id"),
            "rule_id": finding.get("rule_id"),
            "disposition": disposition,
            "heuristic_fp_risk": score,
            "reasons": reasons,
            "automatic_suppression": False,
            "recommendation": "Verify source behavior and exploitability; retain finding unless a human documents a justified disposition.",
        })
    return {
        "schema_version": "1.0",
        "metadata": {
            "findings_analyzed": len(results),
            "needs_review": sum(x["disposition"] == "needs_review" for x in results),
            "automatic_suppression": False,
            "method": "explainable evidence-quality heuristics; not a learned classifier",
        },
        "triage": results,
    }
