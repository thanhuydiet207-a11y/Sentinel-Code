"""Integrity seals and provenance checks for remediation evidence bundles."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("artifact path must be relative and traversal-free")
    path = root / relative
    if path.is_symlink():
        raise ValueError("symlink artifacts are not allowed")
    resolved = path.resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError("artifact escapes root")
    if not resolved.is_file():
        raise ValueError(f"artifact is not a regular file: {relative}")
    return resolved

def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def seal_evidence_bundle(bundle: Any, root: str | Path = ".") -> dict:
    if not isinstance(bundle, dict):
        raise ValueError("bundle must be an object")
    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("artifacts must be a list")
    source_commit = bundle.get("source_commit")
    candidate_sha = bundle.get("candidate_sha256")
    if source_commit is not None and (not isinstance(source_commit, str) or not source_commit.strip()):
        raise ValueError("source_commit must be a non-empty string")
    if candidate_sha is not None and (not isinstance(candidate_sha, str) or len(candidate_sha) != 64 or any(c not in "0123456789abcdef" for c in candidate_sha.lower())):
        raise ValueError("candidate_sha256 must be a 64-character hex digest")
    base = Path(root).resolve()
    sealed = []
    names = set()
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("each artifact must contain a path")
        name = item.get("name") or item["path"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("artifact names must be non-empty and unique")
        names.add(name)
        path = _safe_file(base, item["path"])
        data = path.read_bytes()
        sealed.append({"name": name, "kind": str(item.get("kind", "unspecified")),
                      "path": item["path"], "size_bytes": len(data), "sha256": _sha256(data)})
    payload = {"schema_version": 1, "source_commit": source_commit,
               "candidate_sha256": candidate_sha, "metadata": bundle.get("metadata", {}),
               "artifacts": sorted(sealed, key=lambda a: a["name"])}
    payload["bundle_sha256"] = _sha256(_canonical(payload))
    payload["integrity"] = "sealed"
    payload["limitations"] = ["SHA-256 detects content changes but does not prove who created the evidence.",
                              "Seal creation time is not included; this is not a trusted timestamp or signature.",
                              "Source commit and candidate hash are caller-supplied metadata and must be independently verified."]
    return payload

def verify_evidence_bundle(sealed: Any, root: str | Path = ".") -> dict:
    if not isinstance(sealed, dict) or sealed.get("schema_version") != 1:
        raise ValueError("unsupported sealed bundle")
    artifacts = sealed.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("sealed artifacts must be a list")
    claimed_bundle_hash = sealed.get("bundle_sha256")
    base = Path(root).resolve()
    checks = []
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("artifact record must be object")
        path = _safe_file(base, item.get("path"))
        data = path.read_bytes()
        actual = _sha256(data)
        checks.append({"name": item.get("name"), "path": item.get("path"),
                      "expected_sha256": item.get("sha256"), "actual_sha256": actual,
                      "expected_size_bytes": item.get("size_bytes"), "actual_size_bytes": len(data),
                      "valid": actual == item.get("sha256") and len(data) == item.get("size_bytes")})
    core = {k: v for k, v in sealed.items() if k not in ("bundle_sha256", "integrity", "limitations")}
    calculated_bundle_hash = _sha256(_canonical(core))
    bundle_valid = calculated_bundle_hash == claimed_bundle_hash
    valid = bundle_valid and all(c["valid"] for c in checks)
    return {"valid": valid, "integrity": "verified" if valid else "invalid",
            "bundle_hash_valid": bundle_valid, "claimed_bundle_sha256": claimed_bundle_hash,
            "calculated_bundle_sha256": calculated_bundle_hash, "artifact_checks": checks,
            "review_required": True,
            "limitations": ["Integrity verification does not establish authenticity or trusted creation time.",
                            "Verify source commit, candidate hash, scan completeness, and CI identity separately."]}
