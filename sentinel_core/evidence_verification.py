"""Deterministic source-location verification for AI reviewer evidence references.

This verifies that cited locations exist in the checked-out source and optionally
match a finding's declared evidence hash. It does not prove the security claim.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any

_REF_RE = re.compile(r"^(.+):([0-9]+)(?:-([0-9]+))?$")


def _resolve(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("evidence reference must use a POSIX relative path")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or any(part in ("", ".", "..") for part in posix.parts):
        raise ValueError("evidence reference path is unsafe")
    candidate = (root.resolve() / Path(*posix.parts)).resolve(strict=True)
    candidate.relative_to(root.resolve())
    if not candidate.is_file():
        raise ValueError("evidence reference must target a file")
    return candidate


def verify_ai_evidence(findings_payload: dict[str, Any], reviews_payload: dict[str, Any], repository_root: Path | str) -> dict[str, Any]:
    findings = findings_payload.get("findings")
    reviewers = reviews_payload.get("reviewers")
    if not isinstance(findings, list) or not isinstance(reviewers, list):
        raise ValueError("findings and reviewers must be arrays")
    finding_map: dict[str, dict[str, Any]] = {}
    for item in findings:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("each finding must be an object with an id")
        if item["id"] in finding_map:
            raise ValueError("duplicate finding id")
        finding_map[item["id"]] = item

    root = Path(repository_root).resolve()
    results = []
    for reviewer in reviewers:
        if not isinstance(reviewer, dict) or not isinstance(reviewer.get("reviews"), list):
            raise ValueError("reviewer entries must contain reviews arrays")
        reviewer_id = reviewer.get("reviewer_id", "unknown")
        for vote in reviewer["reviews"]:
            if not isinstance(vote, dict):
                raise ValueError("review entries must be objects")
            fid = vote.get("finding_id")
            if fid not in finding_map:
                raise ValueError(f"review references unknown finding: {fid!r}")
            finding = finding_map[fid]
            refs = vote.get("evidence_refs", [])
            if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs):
                raise ValueError("evidence_refs must be a string array")
            location = finding.get("location") or {}
            expected_path = location.get("path")
            expected_start = location.get("start_line")
            expected_end = location.get("end_line")
            declared_hash = (finding.get("evidence") or {}).get("line_hash")
            checks = []
            for ref in refs:
                match = _REF_RE.fullmatch(ref)
                if not match:
                    checks.append({"reference": ref, "valid": False, "reason": "invalid reference format"})
                    continue
                path, start_text, end_text = match.groups()
                start = int(start_text)
                end = int(end_text or start_text)
                if start < 1 or end < start or end - start > 200:
                    checks.append({"reference": ref, "valid": False, "reason": "invalid line range"})
                    continue
                try:
                    source_path = _resolve(root, path)
                    lines = source_path.read_text(encoding="utf-8").splitlines()
                except (OSError, ValueError, UnicodeError):
                    checks.append({"reference": ref, "valid": False, "reason": "source path unavailable or unsafe"})
                    continue
                if end > len(lines):
                    checks.append({"reference": ref, "valid": False, "reason": "line range exceeds source"})
                    continue
                excerpt = "\n".join(lines[start - 1:end])
                digest = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
                exact_location = path == expected_path and start == expected_start and end == expected_end
                hash_matches = bool(declared_hash) and digest == declared_hash if exact_location else None
                checks.append({
                    "reference": ref,
                    "valid": True,
                    "exact_finding_location": exact_location,
                    "source_line_hash": digest,
                    "declared_hash_matches": hash_matches,
                    "excerpt": excerpt[:2000],
                })
            valid_refs = sum(1 for check in checks if check.get("valid"))
            exact_refs = sum(1 for check in checks if check.get("valid") and check.get("exact_finding_location"))
            hash_matches = sum(1 for check in checks if check.get("declared_hash_matches") is True)
            results.append({
                "finding_id": fid,
                "reviewer_id": reviewer_id,
                "reference_count": len(refs),
                "valid_reference_count": valid_refs,
                "exact_location_reference_count": exact_refs,
                "hash_match_count": hash_matches,
                "verification_status": "verified_location_and_hash" if hash_matches else ("verified_location" if exact_refs else ("valid_references" if valid_refs else "unverified")),
                "checks": checks,
                "limitations": "Location and hash verification do not establish exploitability, data flow, or correctness of reviewer rationale.",
            })
    return {
        "schema_version": "1.0",
        "metadata": {"reviews_checked": len(results), "verified_hash_references": sum(x["hash_match_count"] for x in results)},
        "verification": results,
        "safety_note": "This tool verifies citation locations and evidence hashes only; it does not prove or disprove a security finding.",
    }
