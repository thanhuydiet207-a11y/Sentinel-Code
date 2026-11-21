"""Safe validation of AI-proposed source patches without modifying the repository."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")
_MAX_PATCH_BYTES = 200_000


class PatchValidationError(ValueError):
    """Raised when a proposed patch cannot be safely validated."""


def _safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise PatchValidationError("path must be a non-empty POSIX relative path")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or any(part in ("", ".", "..") for part in posix.parts):
        raise PatchValidationError("path is absolute or contains traversal segments")
    candidate = (root.resolve() / Path(*posix.parts)).resolve(strict=True)
    candidate.relative_to(root.resolve())
    if not candidate.is_file():
        raise PatchValidationError("patch target must be a regular file")
    return candidate


def _apply_unified_diff(original: str, patch: str) -> str:
    if not isinstance(patch, str) or not patch or len(patch.encode("utf-8")) > _MAX_PATCH_BYTES:
        raise PatchValidationError("patch must be non-empty and at most 200000 bytes")
    if "\x00" in patch or "GIT binary patch" in patch:
        raise PatchValidationError("binary patches are not supported")
    lines = patch.splitlines()
    if len(lines) < 3 or not lines[0].startswith("--- ") or not lines[1].startswith("+++ "):
        raise PatchValidationError("patch must contain unified diff file headers")
    if lines[0].startswith("--- /") or lines[1].startswith("+++ /"):
        raise PatchValidationError("absolute patch paths are not allowed")
    source = original.splitlines()
    output: list[str] = []
    cursor = 0
    index = 2
    saw_hunk = False
    while index < len(lines):
        match = _HUNK_RE.fullmatch(lines[index])
        if not match:
            raise PatchValidationError("unsupported unified diff structure")
        saw_hunk = True
        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_count = int(match.group(4) or "1")
        target_cursor = max(old_start - 1, 0)
        if target_cursor < cursor or target_cursor > len(source):
            raise PatchValidationError("hunk ranges are invalid or overlap")
        output.extend(source[cursor:target_cursor])
        cursor = target_cursor
        index += 1
        consumed_old = 0
        produced_new = 0
        while index < len(lines) and not lines[index].startswith("@@ "):
            line = lines[index]
            if line == "\\ No newline at end of file":
                index += 1
                continue
            if not line or line[0] not in (" ", "+", "-"):
                raise PatchValidationError("invalid unified diff hunk line")
            payload = line[1:]
            if line[0] == " ":
                if cursor >= len(source) or source[cursor] != payload:
                    raise PatchValidationError("patch context does not match source")
                output.append(source[cursor])
                cursor += 1
                consumed_old += 1
                produced_new += 1
            elif line[0] == "-":
                if cursor >= len(source) or source[cursor] != payload:
                    raise PatchValidationError("removed line does not match source")
                cursor += 1
                consumed_old += 1
            else:
                output.append(payload)
                produced_new += 1
            index += 1
        if consumed_old != old_count or produced_new != new_count:
            raise PatchValidationError("hunk line counts do not match header")
    if not saw_hunk:
        raise PatchValidationError("patch contains no hunks")
    output.extend(source[cursor:])
    result = "\n".join(output)
    if original.endswith("\n") or output:
        result += "\n"
    return result


def validate_patch_proposal(
    proposal: dict[str, Any],
    findings_payload: dict[str, Any],
    repository_root: Path | str,
) -> dict[str, Any]:
    """Validate target finding, source-file hash, and unified diff; never write files."""
    if not isinstance(proposal, dict):
        raise PatchValidationError("patch proposal must be a JSON object")
    finding_id = proposal.get("finding_id")
    if not isinstance(finding_id, str) or not finding_id:
        raise PatchValidationError("finding_id is required")
    findings = findings_payload.get("findings") if isinstance(findings_payload, dict) else None
    if not isinstance(findings, list):
        raise PatchValidationError("findings package must contain an array")
    matches = [f for f in findings if isinstance(f, dict) and f.get("id") == finding_id]
    if len(matches) != 1:
        raise PatchValidationError("finding_id must identify exactly one finding")
    finding = matches[0]
    expected_path = (finding.get("location") or {}).get("path")
    path = proposal.get("path")
    if not isinstance(expected_path, str) or path != expected_path:
        raise PatchValidationError("patch path must exactly match the finding source path")
    root = Path(repository_root).resolve(strict=True)
    target = _safe_path(root, path)
    original = target.read_text(encoding="utf-8")
    base_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
    if proposal.get("base_sha256") != base_hash:
        raise PatchValidationError("base_sha256 does not match current source file")
    patch = proposal.get("patch")
    if not isinstance(patch, str):
        raise PatchValidationError("patch must be a string")
    expected_header = f"--- a/{path}\n+++ b/{path}"
    if not patch.startswith(expected_header):
        raise PatchValidationError("patch headers must target the exact finding path")
    candidate = _apply_unified_diff(original, patch)
    return {
        "finding_id": finding_id,
        "path": path,
        "status": "validated_candidate",
        "base_sha256": base_hash,
        "candidate_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
        "candidate_content": candidate,
        "patch": patch,
        "file_modified": False,
        "automatic_application": False,
        "review_required": True,
    }
