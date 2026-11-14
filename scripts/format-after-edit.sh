#!/usr/bin/env bash
set -euo pipefail

INPUT_JSON="$(cat)"

# Formatting is a convenience hook, not a security gate: missing tooling or
# malformed metadata must not block the user's edit.
if ! command -v jq >/dev/null 2>&1; then
  echo "[SecOps] WARN: jq is unavailable; skipping automatic formatting." >&2
  exit 0
fi

if ! FILE_PATH="$(printf '%s' "$INPUT_JSON" | jq -er '.tool_input.file_path | strings')"; then
  exit 0
fi

if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

if command -v prettier >/dev/null 2>&1; then
  prettier --write -- "$FILE_PATH"
elif command -v npx >/dev/null 2>&1; then
  npx --no-install prettier --write -- "$FILE_PATH"
else
  echo "[SecOps] WARN: Prettier is unavailable; skipping automatic formatting." >&2
fi

exit 0
