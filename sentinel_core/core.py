"""Deterministic validation and reporting primitives for Sentinel-Code findings."""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "1.0"
SEVERITIES = ("critical", "high", "medium", "low", "info")
SEVERITY_BASE = {"critical": 100.0, "high": 80.0, "medium": 55.0, "low": 30.0, "info": 10.0}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RULE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_CATEGORY_RE = re.compile(r"^(?:CWE-[0-9]{1,5}|OWASP-A[0-9]{2}|custom:[a-z0-9._-]{1,64})$")
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


class FindingValidationError(ValueError):
    """Raised when a finding package cannot be validated safely."""


def line_hash_from_text(source: str, start_line: int, end_line: int) -> str:
    """Hash normalized source lines using LF separators, without a trailing LF."""
    lines = source.splitlines()
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        raise ValueError("line range is outside the source file")
    excerpt = "\n".join(lines[start_line - 1:end_line])
    return hashlib.sha256(excerpt.encode("utf-8")).hexdigest()


def line_hash_for_file(path: Path, start_line: int, end_line: int) -> str:
    return line_hash_from_text(path.read_text(encoding="utf-8"), start_line, end_line)


def _safe_source_path(root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        raise FindingValidationError("location.path must be a non-empty POSIX relative path")
    posix = PurePosixPath(relative_path)
    if posix.is_absolute() or any(part in ("", ".", "..") for part in posix.parts):
        raise FindingValidationError("location.path must not be absolute or contain traversal segments")
    if re.match(r"^[A-Za-z]:", relative_path):
        raise FindingValidationError("Windows absolute paths are not allowed")
    root_resolved = root.resolve()
    candidate = (root_resolved / Path(*posix.parts)).resolve(strict=True)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise FindingValidationError("location.path resolves outside the repository root") from exc
    if not candidate.is_file():
        raise FindingValidationError("location.path must point to a regular file")
    return candidate


def validate_payload(payload: Any, repository_root: Path | str) -> list[str]:
    """Validate schema, source locations, and line hashes; return all errors."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["finding package must be a JSON object"]
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION!r}")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return errors + ["findings must be an array"]

    root = Path(repository_root)
    seen_ids: set[str] = set()
    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object")
            continue

        required = ("id", "title", "rule_id", "category", "severity", "confidence",
                    "location", "evidence", "impact", "remediation")
        for field in required:
            if field not in finding:
                errors.append(f"{prefix}.{field} is required")
        if any(field not in finding for field in required):
            continue

        fid = finding["id"]
        if not isinstance(fid, str) or not _ID_RE.fullmatch(fid):
            errors.append(f"{prefix}.id must be 1-128 safe identifier characters")
        elif fid in seen_ids:
            errors.append(f"{prefix}.id duplicates another finding")
        else:
            seen_ids.add(fid)

        for field, maximum in (("title", 300), ("impact", 2000), ("remediation", 3000)):
            value = finding[field]
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                errors.append(f"{prefix}.{field} must be non-empty and at most {maximum} characters")

        rule_id = finding["rule_id"]
        if not isinstance(rule_id, str) or not _RULE_RE.fullmatch(rule_id):
            errors.append(f"{prefix}.rule_id has an invalid format")
        category = finding["category"]
        if not isinstance(category, str) or not _CATEGORY_RE.fullmatch(category):
            errors.append(f"{prefix}.category must be CWE-n, OWASP-Ann, or custom:slug")

        severity = finding["severity"]
        if severity not in SEVERITIES:
            errors.append(f"{prefix}.severity must be one of {', '.join(SEVERITIES)}")

        confidence = finding["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            errors.append(f"{prefix}.confidence must be a finite number from 0 to 1")

        location = finding["location"]
        if not isinstance(location, dict):
            errors.append(f"{prefix}.location must be an object")
            continue
        path_value = location.get("path")
        start = location.get("start_line")
        end = location.get("end_line")
        if isinstance(start, bool) or not isinstance(start, int) or start < 1:
            errors.append(f"{prefix}.location.start_line must be a positive integer")
        if isinstance(end, bool) or not isinstance(end, int) or end < 1:
            errors.append(f"{prefix}.location.end_line must be a positive integer")
        if isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int) and not isinstance(end, bool):
            if end < start or end - start > 199:
                errors.append(f"{prefix}.location line range is invalid or exceeds 200 lines")

        evidence = finding["evidence"]
        if not isinstance(evidence, dict):
            errors.append(f"{prefix}.evidence must be an object")
            continue
        reason = evidence.get("reason")
        digest = evidence.get("line_hash")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            errors.append(f"{prefix}.evidence.reason must be non-empty and at most 2000 characters")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            errors.append(f"{prefix}.evidence.line_hash must be a SHA-256 hex digest")
        data_flow = evidence.get("data_flow", [])
        if not isinstance(data_flow, list) or any(not isinstance(step, str) or not step.strip() for step in data_flow):
            errors.append(f"{prefix}.evidence.data_flow must be an array of non-empty strings")

        references = finding.get("references", [])
        if not isinstance(references, list) or any(not isinstance(item, str) for item in references):
            errors.append(f"{prefix}.references must be an array of strings")

        if isinstance(path_value, str) and isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int) and not isinstance(end, bool) and isinstance(digest, str) and _SHA256_RE.fullmatch(digest):
            try:
                source_path = _safe_source_path(root, path_value)
                actual_digest = line_hash_for_file(source_path, start, end)
                if actual_digest.lower() != digest.lower():
                    errors.append(f"{prefix}.evidence.line_hash does not match {path_value}:{start}-{end}")
            except (OSError, UnicodeError, ValueError, FindingValidationError) as exc:
                errors.append(f"{prefix}.location/evidence cannot be verified: {exc}")

    return errors


def priority_score(finding: dict[str, Any]) -> float:
    """Transparent triage score, not CVSS and not a replacement for severity."""
    severity = finding.get("severity")
    confidence = finding.get("confidence")
    if not isinstance(severity, str) or severity not in SEVERITY_BASE:
        return 0.0
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return 0.0
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        return 0.0
    return round(SEVERITY_BASE[severity] * confidence, 2)


def _confidence_value(finding: dict[str, Any]) -> float:
    confidence = finding.get("confidence", 0)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
        return 0.0
    return float(confidence)


def finding_fingerprint(finding: dict[str, Any]) -> str:
    location = finding.get("location", {})
    material = "|".join((
        str(finding.get("rule_id", "")).strip().lower(),
        str(location.get("path", "")).replace("\\", "/").strip(),
        str(location.get("start_line", "")),
        str(location.get("end_line", "")),
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def deduplicate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse exact rule/location duplicates, retaining the best-supported candidate."""
    selected: dict[str, dict[str, Any]] = {}
    duplicate_counts: dict[str, int] = {}
    for finding in findings:
        fingerprint = finding_fingerprint(finding)
        duplicate_counts[fingerprint] = duplicate_counts.get(fingerprint, 0) + 1
        current = selected.get(fingerprint)
        candidate_rank = (priority_score(finding), _confidence_value(finding))
        current_rank = (priority_score(current), _confidence_value(current)) if current else (-1, -1)
        if current is None or candidate_rank > current_rank:
            selected[fingerprint] = dict(finding)
    output = []
    for fingerprint, finding in selected.items():
        item = dict(finding)
        item["fingerprint"] = fingerprint
        item["priority_score"] = priority_score(item)
        item["duplicate_count"] = duplicate_counts[fingerprint]
        output.append(item)
    return sorted(output, key=lambda item: (-item["priority_score"], item["location"]["path"], item["location"]["start_line"]))


def render_markdown_report(findings: list[dict[str, Any]], scope: str = "unspecified") -> str:
    rows = deduplicate_findings(findings)
    lines = [
        "# Sentinel-Code Security Review",
        "",
        f"- **Review scope:** {scope}",
        f"- **Unique findings:** {len(rows)}",
        "- **Scoring note:** Priority score = severity base × confidence. It is an internal triage aid, not CVSS.",
        "",
        "| Severity | Priority | Rule | Location | Finding |",
        "|---|---:|---|---|---|",
    ]
    for item in rows:
        loc = item["location"]
        title = str(item.get("title", "")).replace("|", "\\|").replace("\n", " ")
        location_text = f"{loc['path']}:{loc['start_line']}-{loc['end_line']}"
        lines.append(f"| {item['severity'].upper()} | {item['priority_score']:.2f} | {item['rule_id']} | {location_text} | {title} |")
    if not rows:
        lines.append("| — | — | — | — | No findings supplied. |")
    for item in rows:
        loc = item["location"]
        lines.extend([
            "",
            f"## {item['id']} — {item['title']}",
            "",
            f"- **Severity:** {item['severity'].upper()}",
            f"- **Priority score:** {item['priority_score']:.2f}",
            f"- **Rule/category:** {item['rule_id']} / {item['category']}",
            f"- **Location:** {loc['path']}:{loc['start_line']}-{loc['end_line']}",
            f"- **Confidence:** {float(item['confidence']):.2f}",
            f"- **Impact:** {item['impact']}",
            f"- **Evidence:** {item['evidence']['reason']}",
            f"- **Remediation:** {item['remediation']}",
        ])
        flow = item["evidence"].get("data_flow", [])
        if flow:
            lines.append("- **Data flow:** " + " → ".join(flow))
        if item.get("references"):
            lines.append("- **References:** " + ", ".join(item["references"]))
    lines.append("")
    return "\n".join(lines)


def load_json(path: Path | str) -> Any:
    import json
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)
