"""Import supported scanner JSON into Sentinel-Code's evidence-backed finding format."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from .core import line_hash_for_file

SUPPORTED = ("semgrep", "gitleaks", "trivy")
SEVERITY_MAP = {
    "critical": "critical", "high": "high", "error": "high",
    "medium": "medium", "moderate": "medium", "warning": "medium",
    "low": "low", "info": "info", "informational": "info",
}


def _records(scanner: str, data: Any) -> list[dict[str, Any]]:
    if scanner == "semgrep":
        return data.get("results", []) if isinstance(data, dict) else []
    if scanner == "gitleaks":
        return data if isinstance(data, list) else []
    if scanner == "trivy":
        records = []
        if isinstance(data, dict):
            for result in data.get("Results", []) or []:
                for vuln in result.get("Vulnerabilities", []) or []:
                    records.append({"_kind": "vulnerability", "_target": result.get("Target"), **vuln})
                for secret in result.get("Secrets", []) or []:
                    records.append({"_kind": "secret", "_target": result.get("Target"), **secret})
        return records
    raise ValueError(f"unsupported scanner: {scanner}")


def _normalize_path(root: Path, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("scanner record has no file path")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("scanner path must be repository-relative and traversal-free")
    resolved = (root / Path(*path.parts)).resolve(strict=True)
    resolved.relative_to(root.resolve())
    if not resolved.is_file():
        raise ValueError("scanner path is not a file")
    return path.as_posix()


def _severity(record: dict[str, Any], scanner: str) -> str:
    raw = record.get("severity") or record.get("Severity") or record.get("level") or "medium"
    if scanner == "gitleaks":
        return "high"
    return SEVERITY_MAP.get(str(raw).lower(), "medium")


def _category(record: dict[str, Any], scanner: str) -> str:
    cwe = record.get("cwe") or record.get("CWE") or record.get("CweID")
    if isinstance(cwe, list):
        cwe = cwe[0] if cwe else None
    if isinstance(cwe, str):
        cwe = cwe.upper().replace("CWE-", "")
        if cwe.isdigit():
            return f"CWE-{cwe}"
    if scanner == "gitleaks":
        return "custom:secret-detection"
    if scanner == "trivy":
        return "custom:dependency-vulnerability"
    return "custom:scanner-finding"


def _location(record: dict[str, Any], scanner: str) -> tuple[str, int, int]:
    if scanner == "semgrep":
        path = record.get("path")
        start = record.get("start", {}).get("line", 1)
        end = record.get("end", {}).get("line", start)
    elif scanner == "gitleaks":
        path = record.get("File")
        start = record.get("StartLine") or 1
        end = record.get("EndLine") or start
    else:
        path = record.get("_target") or record.get("Target")
        start = record.get("StartLine") or 1
        end = record.get("EndLine") or start
    return str(path or ""), max(1, int(start)), max(1, int(end))


def import_scanner_results(scanner: str, data: Any, repository_root: Path | str) -> dict[str, Any]:
    """Convert scanner output; records lacking a verifiable local source are reported as skipped."""
    scanner = scanner.lower()
    if scanner not in SUPPORTED:
        raise ValueError(f"unsupported scanner {scanner!r}; choose from {', '.join(SUPPORTED)}")
    root = Path(repository_root).resolve()
    findings, skipped = [], []
    for index, record in enumerate(_records(scanner, data)):
        if not isinstance(record, dict):
            skipped.append({"index": index, "reason": "record is not an object"})
            continue
        try:
            raw_path, start, end = _location(record, scanner)
            path = _normalize_path(root, raw_path)
            source_file = root / path
            digest = line_hash_for_file(source_file, start, end)
        except (ValueError, OSError, TypeError) as exc:
            skipped.append({"index": index, "reason": str(exc)})
            continue
        rule = str(record.get("check_id") or record.get("RuleID") or record.get("VulnerabilityID") or record.get("ID") or "scanner/unknown")
        message = str(record.get("message") or record.get("Description") or record.get("Title") or record.get("RuleDescription") or rule)
        stable = hashlib.sha256(f"{scanner}:{rule}:{path}:{start}:{end}".encode()).hexdigest()[:16]
        findings.append({
            "id": f"{scanner.upper()}-{stable}",
            "title": message[:300],
            "rule_id": f"{scanner}/{rule}"[:128],
            "category": _category(record, scanner),
            "severity": _severity(record, scanner),
            "confidence": 0.85 if scanner == "semgrep" else 0.9,
            "location": {"path": path, "start_line": start, "end_line": end},
            "evidence": {
                "reason": f"Imported from {scanner} JSON output; source lines are hash-verified by Sentinel-Code.",
                "line_hash": digest,
            },
            "impact": message[:2000],
            "remediation": str(record.get("fix") or record.get("Remediation") or "Review the scanner finding and apply a safe fix.")[:3000],
            "references": [str(x) for x in (record.get("references") or record.get("References") or []) if isinstance(x, str)][:20],
            "scanner": scanner,
        })
    return {"schema_version": "1.0", "metadata": {"scanner": scanner, "imported": len(findings), "skipped": skipped}, "findings": findings}
