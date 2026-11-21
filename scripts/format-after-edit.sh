#!/usr/bin/env bash
set -u

# Best-effort convenience hook: formatting failures must never block an Edit/Write.
INPUT_JSON="$(cat)"
if ! command -v jq >/dev/null 2>&1; then
  echo "[SecOps] WARN: jq unavailable; skipping automatic formatting." >&2
  exit 0
fi

FILE_PATH="$(printf '%s' "$INPUT_JSON" | jq -er '.tool_input.file_path | strings' 2>/dev/null)" || exit 0
[[ -f "$FILE_PATH" ]] || exit 0

case "$FILE_PATH" in
  *.js|*.jsx|*.ts|*.tsx|*.json|*.jsonc|*.css|*.scss|*.less|*.md|*.mdx|*.html|*.yml|*.yaml|*.graphql) ;;
  *) exit 0 ;;
esac

if command -v prettier >/dev/null 2>&1; then
  FORMATTER=(prettier)
elif command -v npx >/dev/null 2>&1; then
  FORMATTER=(npx --no-install prettier)
else
  echo "[SecOps] WARN: Prettier unavailable; skipping automatic formatting." >&2
  exit 0
fi

if "${FORMATTER[@]}" --write -- "$FILE_PATH"; then
  :
else
  STATUS=$?
  echo "[SecOps] WARN: Prettier exited with status $STATUS; edit remains accepted." >&2
fi
exit 0
