#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLER="$ROOT/scripts/install-agent-skills.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/workspace" "$TMP/userhome"
(
  cd "$TMP/workspace"
  bash "$INSTALLER" --agent shared --scope project
  diff -ru "$ROOT/skills/pr-security-review" ".agents/skills/pr-security-review"
  bash "$INSTALLER" --agent shared --scope project
  diff -ru "$ROOT/skills/pr-security-review" ".agents/skills/pr-security-review"
  bash "$INSTALLER" --agent codex --scope project
  diff -ru "$ROOT/skills/pr-security-review" ".agents/skills/pr-security-review"
  bash "$INSTALLER" --agent claude --scope project
  diff -ru "$ROOT/skills/pr-security-review" ".claude/skills/pr-security-review"
  bash "$INSTALLER" --agent cursor --scope project
  diff -ru "$ROOT/skills/pr-security-review" ".cursor/skills/pr-security-review"
  bash "$INSTALLER" --agent copilot --scope project
  diff -ru "$ROOT/skills/pr-security-review" ".github/skills/pr-security-review"
  bash "$INSTALLER" --agent gemini --scope project
  diff -ru "$ROOT/skills/pr-security-review" ".gemini/skills/pr-security-review"
)
(
  cd "$TMP/workspace"
  HOME="$TMP/userhome" bash "$INSTALLER" --agent claude --scope user
  diff -ru "$ROOT/skills/pr-security-review" "$TMP/userhome/.claude/skills/pr-security-review"
  HOME="$TMP/userhome" bash "$INSTALLER" --agent copilot --scope user
  diff -ru "$ROOT/skills/pr-security-review" "$TMP/userhome/.copilot/skills/pr-security-review"
)
if bash "$INSTALLER" --agent unknown --scope project >/dev/null 2>&1; then
  echo "FAIL: unknown agent should be rejected" >&2
  exit 1
fi
if bash "$INSTALLER" --agent shared --scope invalid >/dev/null 2>&1; then
  echo "FAIL: invalid scope should be rejected" >&2
  exit 1
fi
if bash "$INSTALLER" --agent >/dev/null 2>&1; then
  echo "FAIL: missing agent value should be rejected" >&2
  exit 1
fi
if bash "$INSTALLER" --unknown >/dev/null 2>&1; then
  echo "FAIL: unknown option should be rejected" >&2
  exit 1
fi
bash "$INSTALLER" --help >/dev/null
echo "PASS: project/user skill installation for shared, Claude, Cursor, Copilot, Codex and Gemini; invalid input handling"
