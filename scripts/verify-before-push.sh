#!/usr/bin/env bash
set -euo pipefail

INPUT_JSON="$(cat)"
if ! command -v jq >/dev/null 2>&1; then
  echo "[SecOps] BLOCK: jq is required to validate the PreToolUse payload." >&2
  exit 2
fi
if ! COMMAND_STR="$(printf '%s' "$INPUT_JSON" | jq -er '.tool_input.command | strings')"; then
  echo "[SecOps] BLOCK: invalid or missing tool_input.command payload." >&2
  exit 2
fi

if [[ ! "$COMMAND_STR" =~ (^|[[:space:];&|])git[[:space:]]+push([[:space:]]|$) ]]; then
  exit 0
fi

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
PROTECTED_BRANCH_RE='^(main|master|production)$'
if [[ "$CURRENT_BRANCH" =~ $PROTECTED_BRANCH_RE ]]; then
  echo "[SecOps] BLOCK: pushing from protected branch '$CURRENT_BRANCH' is not allowed. Use a feature branch and open a Pull Request." >&2
  exit 2
fi

# Parse the git push arguments to inspect the actual destination refspec.
read -r -a TOKENS <<< "$COMMAND_STR"
GIT_INDEX=-1
for i in "${!TOKENS[@]}"; do
  if [[ "${TOKENS[$i]}" == "git" ]]; then GIT_INDEX=$i; break; fi
done
if (( GIT_INDEX < 0 )); then exit 0; fi

i=$((GIT_INDEX + 1))
while (( i < ${#TOKENS[@]} )); do
  case "${TOKENS[$i]}" in
    -C|-c|--git-dir|--work-tree) i=$((i + 2));;
    push) break;;
    *) i=$((i + 1));;
  esac
done
if (( i >= ${#TOKENS[@]} )) || [[ "${TOKENS[$i]}" != "push" ]]; then exit 0; fi

i=$((i + 1))
POSITIONAL=()
while (( i < ${#TOKENS[@]} )); do
  token="${TOKENS[$i]}"
  case "$token" in
    --) i=$((i + 1)); while (( i < ${#TOKENS[@]} )); do POSITIONAL+=("${TOKENS[$i]}"); i=$((i + 1)); done; break;;
    -o|--push-option|-r|--repo|--receive-pack|--exec) i=$((i + 2));;
    --push-option=*|--repo=*|--receive-pack=*|--exec=*|-*) i=$((i + 1));;
    *) POSITIONAL+=("$token"); i=$((i + 1));;
  esac
done

# POSITIONAL[0] is the remote; POSITIONAL[1], when present, is the refspec.
DESTINATION="$CURRENT_BRANCH"
if (( ${#POSITIONAL[@]} >= 2 )); then
  REFSPEC="${POSITIONAL[1]}"
  REFSPEC="${REFSPEC#+}"
  if [[ "$REFSPEC" == *:* ]]; then DESTINATION="${REFSPEC##*:}"; else DESTINATION="$REFSPEC"; fi
fi
DESTINATION="${DESTINATION#refs/heads/}"
if [[ "$DESTINATION" =~ $PROTECTED_BRANCH_RE ]]; then
  echo "[SecOps] BLOCK: push destination '$DESTINATION' is a protected branch. Use a feature branch and open a Pull Request." >&2
  exit 2
fi

# Scan every local commit not already reachable from a remote-tracking ref.
# This also covers a branch's first push, where @{u} does not exist yet.
SECRET_PATTERN='(AKIA[0-9A-Z]{16}|-----BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY-----|-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-ant-[A-Za-z0-9_-]{20,})'
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "[SecOps] BLOCK: cannot determine HEAD; refusing to push." >&2
  exit 2
fi
while IFS= read -r commit; do
  [[ -z "$commit" ]] && continue
  if git show --format= --no-ext-diff --no-renames "$commit" 2>/dev/null | grep -Eiq "$SECRET_PATTERN"; then
    echo "[SecOps] BLOCK: secret-like material found in unpushed commit $commit. Remove it from Git history and rotate the credential." >&2
    exit 2
  fi
done < <(git rev-list HEAD --not --remotes)

exit 0
