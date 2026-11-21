"""Heuristic risk review for proposed unified diffs; advisory only."""
from __future__ import annotations
from pathlib import PurePosixPath
from typing import Any

_SENSITIVE = ("auth", "security", "permission", "policy", "crypto", "password", "token", "secret", "workflow", ".github")
_DEP_FILES = ("requirements", "pyproject.toml", "package.json", "package-lock.json", "pom.xml", "build.gradle", "gradle.lockfile")
_TEST_HINTS = ("test", "spec")

def review_patch_risk(proposal: Any) -> dict:
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be a JSON object")
    patch = proposal.get("patch")
    path = proposal.get("path")
    if not isinstance(patch, str) or not patch:
        raise ValueError("proposal patch must be a non-empty string")
    if not isinstance(path, str) or not path:
        raise ValueError("proposal path is required")
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or chr(92) in path:
        raise ValueError("proposal path must be relative and traversal-free")
    additions, deletions = [], []
    changed_paths = set()
    for line in patch.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            raw = line[4:].split("\t", 1)[0]
            if raw not in ("/dev/null", "dev/null"):
                raw = raw.removeprefix("a/").removeprefix("b/")
                changed_paths.add(raw)
        elif line.startswith("+") and not line.startswith("+++"):
            additions.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            deletions.append(line[1:])
    if not changed_paths:
        changed_paths.add(path)
    flags, score = [], 0
    lower_path = path.lower()
    if any(term in lower_path for term in _SENSITIVE):
        flags.append("sensitive_path")
        score += 25
    if any(any(term in pth.lower() for term in _DEP_FILES) for pth in changed_paths):
        flags.append("dependency_or_build_file")
        score += 20
    if len(changed_paths) > 1:
        flags.append("multi_file_patch")
        score += min(20, 5 * (len(changed_paths) - 1))
    if len(deletions) > 30:
        flags.append("large_deletion")
        score += 15
    if len(additions) + len(deletions) > 100:
        flags.append("large_patch")
        score += 15
    suspicious = ("eval(", "exec(", "subprocess", "shell=True", "verify=False", "chmod 777", "pickle.loads")
    found = [token for token in suspicious if any(token in line for line in additions)]
    if found:
        flags.append("dangerous_constructs")
        score += min(30, 10 * len(found))
    secret_markers = ("api_key", "private_key", "password =", "token =", "-----begin")
    if any(any(marker in line.lower() for marker in secret_markers) for line in additions):
        flags.append("possible_secret")
        score += 35
    if any(hint in lower_path for hint in _TEST_HINTS):
        flags.append("test_file_target")
        score -= 10
    score = max(0, min(100, score))
    if score >= 60:
        level = "high"
    elif score >= 30:
        level = "medium"
    else:
        level = "low"
    return {"path": path, "changed_paths": sorted(changed_paths), "additions": len(additions),
            "deletions": len(deletions), "flags": flags, "risk_score": score, "risk_level": level,
            "recommendation": "block_pending_manual_review" if level == "high" else "manual_review",
            "review_required": True, "automatic_apply_allowed": False,
            "limitations": ["Heuristic signals can miss malicious changes and produce false positives.",
                           "Risk score is not a calibrated probability or security verdict."]}
