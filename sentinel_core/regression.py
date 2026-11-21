"""Compare normalized security scan snapshots to identify regressions."""
from __future__ import annotations
from collections import Counter
from typing import Any

_SEVERITY = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1, "informational": 1, "unknown": 0}

def _findings(payload: Any, label: str) -> list[dict]:
    if isinstance(payload, dict):
        items = payload.get("findings")
    else:
        items = payload
    if not isinstance(items, list):
        raise ValueError(f"{label} scan must be a list or object with findings list")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{label} findings must contain objects")
        location = item.get("location", {})
        evidence = item.get("evidence", {})
        if not isinstance(location, dict) or not isinstance(evidence, dict):
            raise ValueError(f"{label} finding location/evidence must be objects")
    return items

def _identity(finding: dict) -> tuple:
    location = finding.get("location") or {}
    evidence = finding.get("evidence") or {}
    path = location.get("path") or finding.get("path") or ""
    rule = finding.get("rule_id") or finding.get("rule") or ""
    scanner = finding.get("scanner") or finding.get("source") or ""
    evidence_hash = evidence.get("line_hash") or evidence.get("sha256") or finding.get("evidence_hash") or ""
    line = location.get("start_line") or location.get("line") or finding.get("line") or ""
    title = finding.get("title") or finding.get("message") or ""
    # Prefer stable source evidence; use line/title fallback where a scanner lacks hashes.
    return (str(path), str(scanner), str(rule), str(evidence_hash), str(line) if not evidence_hash else "", str(title) if not evidence_hash else "")

def compare_scan_snapshots(baseline: Any, candidate: Any) -> dict:
    before = _findings(baseline, "baseline")
    after = _findings(candidate, "candidate")
    before_by_key, after_by_key = {}, {}
    duplicates = []
    for side, items, target in (("baseline", before, before_by_key), ("candidate", after, after_by_key)):
        for item in items:
            key = _identity(item)
            if key in target:
                duplicates.append({"snapshot": side, "finding": item})
                continue
            target[key] = item
    fixed = [before_by_key[k] for k in before_by_key.keys() - after_by_key.keys()]
    new = [after_by_key[k] for k in after_by_key.keys() - before_by_key.keys()]
    persisting = []
    severity_changes = []
    for key in before_by_key.keys() & after_by_key.keys():
        old, current = before_by_key[key], after_by_key[key]
        persisting.append({"baseline": old, "candidate": current})
        old_sev = str(old.get("severity", "unknown")).lower()
        new_sev = str(current.get("severity", "unknown")).lower()
        if old_sev != new_sev:
            severity_changes.append({"baseline": old_sev, "candidate": new_sev, "finding": current,
                "direction": "worsened" if _SEVERITY.get(new_sev, 0) > _SEVERITY.get(old_sev, 0) else "improved"})
    counts = Counter(str(item.get("severity", "unknown")).lower() for item in after)
    return {"summary": {"baseline_count": len(before), "candidate_count": len(after),
                        "fixed_count": len(fixed), "new_count": len(new),
                        "persisting_count": len(persisting), "severity_change_count": len(severity_changes),
                        "duplicate_count": len(duplicates), "candidate_severity_counts": dict(counts)},
            "fixed": fixed, "new": new, "persisting": persisting, "severity_changes": severity_changes,
            "duplicates": duplicates, "status": "regression" if new or any(x["direction"] == "worsened" for x in severity_changes) else "clean",
            "review_required": True,
            "limitations": ["Identity is heuristic; scanner rule/path/evidence changes may split or merge findings.",
                           "A clean comparison does not prove security; scanner coverage and configuration may differ.",
                           "Fixed findings are absent from the candidate snapshot only; verify scan completeness."]}
