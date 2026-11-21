#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/scripts/format-after-edit.sh"
command -v jq >/dev/null
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/project dir"
printf 'const x={a:1}\n' > "$TMP/project dir/file with spaces.js"

cat > "$TMP/bin/npx" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$FORMAT_LOG"
exit "${FORMAT_EXIT:-0}"
SH
chmod +x "$TMP/bin/npx"

jq -n --arg path "$TMP/project dir/file with spaces.js" '{tool_input:{file_path:$path}}' |
  PATH="$TMP/bin:$PATH" FORMAT_LOG="$TMP/format.log" bash "$HOOK"
mapfile -t args < "$TMP/format.log"
[[ "${#args[@]}" -eq 5 ]]
[[ "${args[0]}" == "--no-install" ]]
[[ "${args[1]}" == "prettier" ]]
[[ "${args[2]}" == "--write" ]]
[[ "${args[3]}" == "--" ]]
[[ "${args[4]-}" == "$TMP/project dir/file with spaces.js" ]]

# A formatter failure is a warning, never a failure of the user's edit.
jq -n --arg path "$TMP/project dir/file with spaces.js" '{tool_input:{file_path:$path}}' |
  PATH="$TMP/bin:$PATH" FORMAT_LOG="$TMP/fail.log" FORMAT_EXIT=2 bash "$HOOK"

# Unsupported files are skipped without invoking Prettier.
jq -n --arg path "$TMP/project dir/file.txt" '{tool_input:{file_path:$path}}' |
  PATH="$TMP/bin:$PATH" FORMAT_LOG="$TMP/skip.log" bash "$HOOK"
[[ ! -e "$TMP/skip.log" ]]
echo "PASS: formatter args, failure isolation, and unsupported-file skip"
