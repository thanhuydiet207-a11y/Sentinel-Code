"""Cross-scanner correlation with evidence-aware grouping."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

_SEVERITY = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _key(finding: dict[str, Any]) -> tuple[str, str]:
    loc = finding.get("location") or {}
    evidence = finding.get("evidence") or {}
    path = str(loc.get("path", "")).replace("\\", "/")
    digest = str(evidence.get("line_hash", "")).lower()
    # Evidence hash is the preferred anchor. Fallback to location when evidence
    # hashes are unavailable; line overlap is intentionally not inferred here.
    anchor = digest if len(digest) == 64 else f"{loc.get('start_line', '')}:{loc.get('end_line', '')}"
    return path, anchor


def correlate_findings(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Group findings sharing a local path and evidence anchor.

    Scanner disagreement is preserved in each group. Confidence is a transparent
    noisy-OR aggregation of scanner confidence values, not a calibrated probability.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    input_count = 0
    for payload in payloads:
        for finding in payload.get("findings", []):
            if not isinstance(finding, dict):
                continue
            input_count += 1
            groups[_key(finding)].append(finding)

    correlated = []
    for (path, anchor), members in sorted(groups.items()):
        scanners = sorted({str(x.get("scanner") or x.get("rule_id", "").split("/", 1)[0]) for x in members})
        confidences = []
        for item in members:
            c = item.get("confidence", 0)
            if isinstance(c, (int, float)) and not isinstance(c, bool) and 0 <= c <= 1:
                confidences.append(float(c))
        combined = 1.0
        for confidence in confidences:
            combined *= 1.0 - confidence
        combined = round(min(0.99, 1.0 - combined), 4) if confidences else 0.0
        strongest = max(members, key=lambda x: _SEVERITY.get(x.get("severity"), 0))
        loc = strongest.get("location", {})
        material = f"{path}|{anchor}|{'|'.join(scanners)}"
        cid = hashlib.sha256(material.encode()).hexdigest()[:16]
        correlated.append({
            "id": f"CORR-{cid}",
            "path": path,
            "evidence_anchor": anchor,
            "location": dict(loc),
            "title": strongest.get("title", "Correlated security finding"),
            "severity": strongest.get("severity", "info"),
            "combined_confidence": combined,
            "scanner_count": len(scanners),
            "scanners": scanners,
            "corroborated": len(scanners) >= 2,
            "finding_ids": sorted(str(x.get("id", "")) for x in members),
            "rule_ids": sorted({str(x.get("rule_id", "")) for x in members}),
            "notes": "Confidence uses noisy-OR of adapter confidence values; it is not calibrated. Scanner absence is not evidence of safety.",
        })
    return {
        "schema_version": "1.0",
        "metadata": {
            "input_findings": input_count,
            "correlation_groups": len(correlated),
            "corroborated_groups": sum(1 for x in correlated if x["corroborated"]),
            "method": "exact path plus evidence line hash; fallback exact line range",
        },
        "correlations": correlated,
    }
