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
  diff -ru "$ROOT/skills/pr-security-review" ".agents/skills/pr-security-review"
  bash "$INSTALLER" --agent shared --scope project
  diff -ru "$ROOT/skills/pr-security-review" ".agents/skills/pr-security-review"
)
(
  cd "$TMP/workspace"
  bash "$INSTALLER" --agent copilot --scope project
  diff -ru "$ROOT/skills/pr-security-review" ".github/skills/pr-security-review"
)
(
  cd "$TMP/workspace"
  bash "$INSTALLER" --agent gemini --scope project
  diff -ru "$ROOT/skills/pr-security-review" ".gemini/skills/pr-security-review"
)
if bash "$INSTALLER" --agent unknown --scope project >/dev/null 2>&1; then
  echo "FAIL: unknown agent should be rejected" >&2
  exit 1
fi
echo "PASS: shared and host-specific skill installation, including reference assets"
