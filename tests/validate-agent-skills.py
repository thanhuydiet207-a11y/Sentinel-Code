#!/usr/bin/env python3
"""Validate the portable Skill and its cross-host mirror without third-party packages."""
from pathlib import Path
import re
import sys
ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skills/pr-security-review/SKILL.md"
SHARED = ROOT / ".agents/skills/pr-security-review/SKILL.md"
def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1
def main() -> int:
    if not CANONICAL.is_file():
        return fail("canonical Skill is missing")
    if not SHARED.is_file():
        return fail("shared .agents/skills mirror is missing")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if canonical != SHARED.read_text(encoding="utf-8"):
        return fail("canonical Skill and .agents mirror are not byte-for-byte identical")
    if not canonical.startswith("---\\n"):
        return fail("SKILL.md must begin with YAML frontmatter")
    parts = canonical.split("---", 2)
    if len(parts) != 3:
        return fail("SKILL.md frontmatter is malformed")
    metadata = parts[1]
    for field in ("name", "description"):
        if not re.search(rf"(?m)^{field}:\\s*\\S", metadata):
            return fail(f"frontmatter must include {field}")
    name = re.search(r"(?m)^name:\\s*([a-z0-9-]+)\\s*$", metadata)
    if not name or name.group(1) != CANONICAL.parent.name:
        return fail("Skill name must match its directory and use kebab-case")
    description = re.search(r"(?m)^description:\\s*(.+)$", metadata)
    if not description or len(description.group(1)) > 1024:
        return fail("description is missing or exceeds 1024 characters")
    if "!" + chr(96) in canonical or "$ARGUMENTS" in canonical:
        return fail("portable Skill must not depend on Claude-only prompt interpolation")
    print("PASS: portable Agent Skill metadata valid; shared mirror matches canonical source.")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
