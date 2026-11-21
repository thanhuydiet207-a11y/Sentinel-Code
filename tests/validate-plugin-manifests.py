#!/usr/bin/env python3
"""Validate the root Agent Plugins and Codex compatibility manifests with stdlib only."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_URI = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
ROOT_MANIFEST = ROOT / "plugin.json"
CODEX_MANIFEST = ROOT / ".codex-plugin/plugin.json"


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def load(path: Path):
    if not path.is_file():
        raise ValueError(f"missing manifest: {path.relative_to(ROOT)}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc


def main() -> int:
    try:
        root = load(ROOT_MANIFEST)
        codex = load(CODEX_MANIFEST)
    except ValueError as exc:
        return fail(str(exc))

    if not isinstance(root, dict):
        return fail("root plugin.json must be an object")
    allowed = {"$schema", "name", "version", "description", "author", "homepage", "repository", "license", "keywords", "extensions"}
    extra = sorted(set(root) - allowed)
    if extra:
        return fail(f"root plugin.json contains unsupported Agent Plugins fields: {', '.join(extra)}")
    if root.get("$schema") != SCHEMA_URI:
        return fail("root plugin.json must declare the Agent Plugins 1.0.0 schema")
    name = root.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", name) or len(name) > 64:
        return fail("root plugin name is not a valid Agent Plugins identifier")
    if not isinstance(root.get("version"), str) or not isinstance(root.get("description"), str):
        return fail("root plugin must include string version and description")
    author = root.get("author")
    if author is not None:
        if not isinstance(author, dict) or set(author) - {"name", "email", "url"}:
            return fail("root plugin author object has invalid shape")
    keywords = root.get("keywords", [])
    if not isinstance(keywords, list) or not all(isinstance(item, str) for item in keywords):
        return fail("root plugin keywords must be an array of strings")
    extensions = root.get("extensions", {})
    if not isinstance(extensions, dict) or any(not isinstance(value, dict) for value in extensions.values()):
        return fail("root plugin extensions must map namespace names to objects")
    openai = extensions.get("com.openai", {})
    onboarding = openai.get("onboardingSkill")
    if onboarding != "./skills/pr-security-review/SKILL.md":
        return fail("OpenAI onboardingSkill must point to the packaged PR security-review Skill")

    if not isinstance(codex, dict):
        return fail(".codex-plugin/plugin.json must be an object")
    for field in ("name", "version", "description", "skills"):
        if not isinstance(codex.get(field), str) or not codex[field]:
            return fail(f"Codex compatibility manifest must include string {field}")
    if codex.get("skills") != "./skills/":
        return fail("Codex compatibility manifest must point to ./skills/")
    if "$schema" in codex:
        return fail("Codex compatibility manifest must omit the Agent Plugins $schema")

    print("PASS: root Agent Plugins manifest and Codex compatibility manifest are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
