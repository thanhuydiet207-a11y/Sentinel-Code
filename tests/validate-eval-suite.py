#!/usr/bin/env python3
"""Validate the repository's Claude Code plugin eval suite structure."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"

def frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path.relative_to(ROOT)}: missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError(f"{path.relative_to(ROOT)}: malformed frontmatter")
    return parts[1], parts[2]

def main():
    if not EVALS.is_dir():
        raise SystemExit("FAIL: evals/ directory is missing")
    cases = sorted(p for p in EVALS.iterdir() if p.is_dir() and (p / "prompt.md").is_file())
    if not cases:
        raise SystemExit("FAIL: no eval cases found")

    errors = []
    for case in cases:
        rel = case.relative_to(ROOT)
        try:
            prompt_meta, prompt_body = frontmatter(case / "prompt.md")
            if not re.search(r"(?m)^name:\\s*\\S+", prompt_meta):
                errors.append(f"{rel}: prompt frontmatter must declare name")
            if 'plugins: ["../.."]' not in prompt_meta:
                errors.append(f"{rel}: plugin path must resolve to repository root")
            if not re.search(r"(?m)^allowed_tools:.*\\bSkill\\b", prompt_meta):
                errors.append(f"{rel}: allowed_tools must include Skill")
            graders_dir = case / "graders"
            graders = sorted(graders_dir.glob("*.md")) if graders_dir.is_dir() else []
            if not graders:
                errors.append(f"{rel}: at least one grader is required")
                continue
            types = {}
            for grader in graders:
                meta, body = frontmatter(grader)
                match = re.search(r"(?m)^type:\\s*(\\w+)", meta)
                if not match:
                    errors.append(f"{grader.relative_to(ROOT)}: missing grader type")
                    continue
                types.setdefault(match.group(1), []).append((grader, meta, body))
            if "llm" not in types:
                errors.append(f"{rel}: an llm outcome grader is required")
            elif not any(body.strip() for _, _, body in types["llm"]):
                errors.append(f"{rel}: llm grader rubric is empty")
            if "tool_used" not in types:
                errors.append(f"{rel}: a tool_used grader is required to track skill invocation")
            else:
                if not any(re.search(r"(?m)^tool:\\s*Skill\\s*$", meta) and "pr-security-review" in meta
                           for _, meta, _ in types["tool_used"]):
                    errors.append(f"{rel}: tool_used grader must assert pr-security-review")
            if not prompt_body.strip():
                errors.append(f"{rel}: prompt body is empty")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: validated {len(cases)} eval cases; each has an LLM outcome grader and Skill invocation grader.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
