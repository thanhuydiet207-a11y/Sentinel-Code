#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/scripts/verify-before-push.sh"
command -v git >/dev/null
command -v jq >/dev/null
command -v python3 >/dev/null

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

new_repo multi_refspec
assert_block "second protected refspec is blocked" "$TMP/multi_refspec" "git push origin feature:feature main:main"

new_repo push_all
assert_block "--all push is blocked" "$TMP/push_all" "git push --all origin"

new_repo push_mirror
assert_block "--mirror push is blocked" "$TMP/push_mirror" "git push --mirror origin"

new_repo git_c
assert_block "git -C invocation is inspected" "$TMP/git_c" "git -C \"$TMP/git_c\" push origin HEAD:refs/heads/main"

new_repo implicit
assert_block "implicit destination push is blocked" "$TMP/implicit" "git push"

new_repo quoted
assert_allow "quoted feature refspec is allowed" "$TMP/quoted" "git push origin 'feature/test:feature/test'"

new_repo first_push_secret
printf 'AWS_ACCESS_KEY_ID=%s%s\n' 'AKIA' '1234567890ABCDEF' > "$TMP/first_push_secret/leak.txt"
git -C "$TMP/first_push_secret" add leak.txt
git -C "$TMP/first_push_secret" commit -qm "add aws key"
assert_block "secret is caught on first push without upstream" "$TMP/first_push_secret" "git push origin feature/test"

new_repo pem
printf '%s%s%s\n' '-----BEGIN ' 'OPENSSH PRIVATE KEY' '-----' > "$TMP/pem/leak.txt"
printf '%s\n' 'example' '-----END OPENSSH PRIVATE KEY-----' >> "$TMP/pem/leak.txt"
git -C "$TMP/pem" add leak.txt
git -C "$TMP/pem" commit -qm "add private key"
assert_block "OpenSSH private key is blocked" "$TMP/pem" "git push origin feature/test"

new_repo github_token
printf 'token=%s%s\n' 'ghp_' 'abcdefghijklmnopqrstuvwxyz1234567890' > "$TMP/github_token/leak.txt"
git -C "$TMP/github_token" add leak.txt
git -C "$TMP/github_token" commit -qm "add token"
assert_block "GitHub token is blocked" "$TMP/github_token" "git push origin feature/test"

new_repo jwt_secret
printf 'token=%s.%s.%s\n' 'eyJhbGciOiJIUzI1NiJ9' 'eyJzdWIiOiIxMjM0NTY3ODkwIn0' 'abcdefghijklmnopqrstuvwxyz1234567890' > "$TMP/jwt_secret/leak.txt"
git -C "$TMP/jwt_secret" add leak.txt
git -C "$TMP/jwt_secret" commit -qm "add jwt"
assert_block "JWT-like bearer token is blocked" "$TMP/jwt_secret" "git push origin feature/test"

new_repo database_uri
printf '%s\n' 'postgresql://appuser:correcthorsebatterystaple@db.example.invalid/app' > "$TMP/database_uri/leak.txt"
git -C "$TMP/database_uri" add leak.txt
git -C "$TMP/database_uri" commit -qm "add database uri"
assert_block "database connection URI with password is blocked" "$TMP/database_uri" "git push origin feature/test"

new_repo cloud_key
printf '%s\n' 'AccountKey=abcdefghijklmnopqrstuvwxyz0123456789ABCD==' > "$TMP/cloud_key/leak.txt"
git -C "$TMP/cloud_key" add leak.txt
git -C "$TMP/cloud_key" commit -qm "add cloud key"
assert_block "cloud storage account key is blocked" "$TMP/cloud_key" "git push origin feature/test"

new_repo named_api_key
printf 'API_KEY=%s\n' 'abcdefghijklmnopqrstuvwxyz0123456789' > "$TMP/named_api_key/leak.txt"
git -C "$TMP/named_api_key" add leak.txt
git -C "$TMP/named_api_key" commit -qm "add api key"
assert_block "named API key assignment is blocked" "$TMP/named_api_key" "git push origin feature/test"

new_repo placeholder
printf '%s\n' 'API_KEY=your_example_api_key_goes_here_123456789' > "$TMP/placeholder/config.env"
git -C "$TMP/placeholder" add config.env
git -C "$TMP/placeholder" commit -qm "add placeholder"
assert_allow "obvious API key placeholder is allowed" "$TMP/placeholder" "git push origin feature/test"

echo
echo "Results: $PASS passed, $FAIL failed"
(( FAIL == 0 ))
