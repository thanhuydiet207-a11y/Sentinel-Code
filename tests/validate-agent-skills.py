#!/usr/bin/env python3
"""Validate the portable Skill and its cross-host mirror without third-party packages."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skills/pr-security-review"
SHARED = ROOT / ".agents/skills/pr-security-review"


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    if not CANONICAL.is_dir():
        return fail("canonical Skill directory is missing")
    if not SHARED.is_dir():
        return fail("shared .agents/skills mirror is missing")

    canonical_files = {
        path.relative_to(CANONICAL).as_posix()
        for path in CANONICAL.rglob("*")
        if path.is_file()
    }
    shared_files = {
        path.relative_to(SHARED).as_posix()
        for path in SHARED.rglob("*")
        if path.is_file()
    }
    if canonical_files != shared_files:
        return fail("canonical Skill and shared mirror contain different files")

    for relative in sorted(canonical_files):
        if (CANONICAL / relative).read_bytes() != (SHARED / relative).read_bytes():
            return fail(f"canonical Skill and shared mirror differ at {relative}")

    skill_path = CANONICAL / "SKILL.md"
    if not skill_path.is_file():
        return fail("SKILL.md is missing")
    canonical = skill_path.read_text(encoding="utf-8")
    if not canonical.startswith("---" + chr(10)):
        return fail("SKILL.md must begin with YAML frontmatter")

    parts = canonical.split("---", 2)
    if len(parts) != 3:
        return fail("SKILL.md frontmatter is malformed")
    metadata = parts[1]
    for field in ("name", "description"):
        if not re.search(rf"(?m)^{field}:\s*\S", metadata):
            return fail(f"frontmatter must include {field}")
    name = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", metadata)
    if not name or name.group(1) != CANONICAL.name:
        return fail("Skill name must match its directory and use kebab-case")
    description = re.search(r"(?m)^description:\s*(.+)$", metadata)
    if not description or len(description.group(1)) > 1024:
        return fail("description is missing or exceeds 1024 characters")
    if "!" + chr(96) in canonical or "$ARGUMENTS" in canonical:
        return fail("portable Skill must not depend on Claude-only prompt interpolation")

    print(f"PASS: portable Agent Skill valid; {len(canonical_files)} mirrored file(s) match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
