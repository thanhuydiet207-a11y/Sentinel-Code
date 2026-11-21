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

new_repo sudo_wrapper
assert_block "sudo-wrapped Git push is inspected" "$TMP/sudo_wrapper" "sudo git push origin HEAD:refs/heads/main"

new_repo env_wrapper
assert_block "environment-prefixed Git push is inspected" "$TMP/env_wrapper" "env GIT_TRACE=1 git push origin HEAD:refs/heads/main"

new_repo command_wrapper
assert_block "command-wrapped Git push is inspected" "$TMP/command_wrapper" "command git push origin HEAD:refs/heads/main"

new_repo shell_wrapper
assert_block "bash -c Git push is inspected" "$TMP/shell_wrapper" "bash -c 'git push origin HEAD:refs/heads/main'"

new_repo nested_wrapper
assert_block "sudo bash -c Git push is inspected" "$TMP/nested_wrapper" "sudo bash -c 'git push origin HEAD:refs/heads/main'"

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

new_repo stripe_test_key
printf '%s\\n' 'STRIPE_SECRET_KEY=sk_test_1234567890abcdefghijklmnop' > "$TMP/stripe_test_key/config.env"
git -C "$TMP/stripe_test_key" add config.env
git -C "$TMP/stripe_test_key" commit -qm "add stripe test key"
assert_block "Stripe test-mode secret key is blocked" "$TMP/stripe_test_key" "git push origin feature/test"

new_repo google_api_key
printf '%s\\n' 'GOOGLE_API_KEY=AIza0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ' > "$TMP/google_api_key/config.env"
git -C "$TMP/google_api_key" add config.env
git -C "$TMP/google_api_key" commit -qm "add Google API key"
assert_block "Google API key is blocked" "$TMP/google_api_key" "git push origin feature/test"

new_repo npm_token
printf '%s\\n' 'NPM_TOKEN=npm_abcdefghijklmnopqrstuvwxyz1234567890ABCD' > "$TMP/npm_token/config.env"
git -C "$TMP/npm_token" add config.env
git -C "$TMP/npm_token" commit -qm "add npm token"
assert_block "npm access token is blocked" "$TMP/npm_token" "git push origin feature/test"

new_repo example_substring
printf '%s\\n' 'API_KEY=prod_example_abcdefghijklmnopqrstuvwxyz123456789' > "$TMP/example_substring/config.env"
git -C "$TMP/example_substring" add config.env
git -C "$TMP/example_substring" commit -qm "add credential containing example substring"
assert_block "credential containing example as a substring is not suppressed" "$TMP/example_substring" "git push origin feature/test"


new_repo twilio_token
printf '%s\\n' 'TWILIO_AUTH_TOKEN=SG.abcdefghijklmnopqrstuvwxyz1234567890.ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890' > "$TMP/twilio_token/config.env"
git -C "$TMP/twilio_token" add config.env
git -C "$TMP/twilio_token" commit -qm "add Twilio token"
assert_block "Twilio auth token is blocked" "$TMP/twilio_token" "git push origin feature/test"

echo
echo "Results: $PASS passed, $FAIL failed"
(( FAIL == 0 ))
