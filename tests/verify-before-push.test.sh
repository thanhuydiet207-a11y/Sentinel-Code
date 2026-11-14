#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/scripts/verify-before-push.sh"
command -v git >/dev/null
command -v jq >/dev/null

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PASS=0
FAIL=0

new_repo() {
  local name="$1"
  mkdir -p "$TMP/$name"
  git -C "$TMP/$name" init -q -b feature/test
  git -C "$TMP/$name" config user.name "SecOps Tests"
  git -C "$TMP/$name" config user.email "secops-tests@example.invalid"
  printf 'baseline\n' > "$TMP/$name/base.txt"
  git -C "$TMP/$name" add base.txt
  git -C "$TMP/$name" commit -qm "baseline"
}

run_hook() {
  local repo="$1" command="$2"
  (cd "$repo" && jq -n --arg command "$command" '{tool_input:{command:$command}}' | bash "$HOOK")
}

assert_block() {
  local name="$1" repo="$2" command="$3"
  if run_hook "$repo" "$command" >/dev/null 2>&1; then
    echo "FAIL: $name (expected block)"
    FAIL=$((FAIL + 1))
  else
    local status=$?
    if [[ "$status" -eq 2 ]]; then
      echo "PASS: $name"
      PASS=$((PASS + 1))
    else
      echo "FAIL: $name (unexpected exit $status)"
      FAIL=$((FAIL + 1))
    fi
  fi
}

assert_allow() {
  local name="$1" repo="$2" command="$3"
  if run_hook "$repo" "$command" >/dev/null 2>&1; then
    echo "PASS: $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $name"
    FAIL=$((FAIL + 1))
  fi
}

new_repo clean
assert_allow "feature push without secret is allowed" "$TMP/clean" "git push origin feature/test"

new_repo protected
git -C "$TMP/protected" branch -m main
assert_block "push from main is blocked" "$TMP/protected" "git push origin main"

new_repo refspec
assert_block "HEAD:refs/heads/main refspec is blocked" "$TMP/refspec" "git push origin HEAD:refs/heads/main"

new_repo shorthand
assert_block "HEAD:production shorthand refspec is blocked" "$TMP/shorthand" "git push origin HEAD:production"

new_repo first_push_secret
printf 'AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\n' > "$TMP/first_push_secret/leak.txt"
git -C "$TMP/first_push_secret" add leak.txt
git -C "$TMP/first_push_secret" commit -qm "add aws key"
assert_block "secret is caught on first push without upstream" "$TMP/first_push_secret" "git push origin feature/test"

new_repo pem
printf '%s\n' '-----BEGIN OPENSSH PRIVATE KEY-----' 'example' '-----END OPENSSH PRIVATE KEY-----' > "$TMP/pem/leak.txt"
git -C "$TMP/pem" add leak.txt
git -C "$TMP/pem" commit -qm "add private key"
assert_block "OpenSSH private key is blocked" "$TMP/pem" "git push origin feature/test"

new_repo github_token
printf 'token=ghp_abcdefghijklmnopqrstuvwxyz1234567890\n' > "$TMP/github_token/leak.txt"
git -C "$TMP/github_token" add leak.txt
git -C "$TMP/github_token" commit -qm "add token"
assert_block "GitHub token is blocked" "$TMP/github_token" "git push origin feature/test"

echo
echo "Results: $PASS passed, $FAIL failed"
(( FAIL == 0 ))
