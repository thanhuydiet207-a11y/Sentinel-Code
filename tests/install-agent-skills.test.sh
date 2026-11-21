#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLER="$ROOT/scripts/install-agent-skills.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/workspace"
(
  cd "$TMP/workspace"
  bash "$INSTALLER" --agent shared --scope project
  cmp "$ROOT/skills/pr-security-review/SKILL.md" ".agents/skills/pr-security-review/SKILL.md"
  bash "$INSTALLER" --agent shared --scope project
  cmp "$ROOT/skills/pr-security-review/SKILL.md" ".agents/skills/pr-security-review/SKILL.md"
)
(
  cd "$TMP/workspace"
  bash "$INSTALLER" --agent copilot --scope project
  cmp "$ROOT/skills/pr-security-review/SKILL.md" ".github/skills/pr-security-review/SKILL.md"
)
(
  cd "$TMP/workspace"
  bash "$INSTALLER" --agent gemini --scope project
  cmp "$ROOT/skills/pr-security-review/SKILL.md" ".gemini/skills/pr-security-review/SKILL.md"
)
if bash "$INSTALLER" --agent unknown --scope project >/dev/null 2>&1; then
  echo "FAIL: unknown agent should be rejected" >&2; exit 1
fi
echo "PASS: shared and host-specific skill installation"
