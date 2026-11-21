#!/usr/bin/env bash
set -euo pipefail

INPUT_JSON="$(cat)"
if ! command -v python3 >/dev/null 2>&1; then
  # Fail closed only for commands that look like a Git push; unrelated Bash
  # commands should not be blocked by a missing optional parser runtime.
  if grep -Eiq '(^|[^[:alnum:]_])git[[:space:]]+push([^[:alnum:]_]|$)' <<< "$INPUT_JSON"; then
    echo "[SecOps] BLOCK: Python 3 is required to inspect this possible Git push." >&2
    exit 2
  fi
  exit 0
fi
if ! COMMAND_STR="$(INPUT_JSON="$INPUT_JSON" python3 -c 'import json, os; print(json.loads(os.environ["INPUT_JSON"])["tool_input"]["command"])')"; then
  echo "[SecOps] BLOCK: invalid or missing PreToolUse command payload." >&2
  exit 2
fi

# Parse shell-like tokens with quoting support. Inspect common command wrappers
# as well as direct Git invocations; this is not a full Bash interpreter.
if ! PUSH_INFO="$(COMMAND_STR="$COMMAND_STR" python3 - <<'PY'
import os, re, shlex, sys

command = os.environ.get("COMMAND_STR", "")
separators = {";", "&&", "||", "|", "&", "\n"}
assignment = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
shells = {"sh", "bash", "dash", "zsh", "ksh"}

def tokenize(source):
    lexer = shlex.shlex(source, posix=True, punctuation_chars=";&|\n")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)

def command_index(tokens, start, end):
    j = start
    wrappers = {"sudo", "env", "command", "exec", "nohup", "time", "nice", "stdbuf"}
    takes_value = {
        "sudo": {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "--close-from", "-T", "--command-timeout", "-R", "--chroot", "-D", "--chdir"},
        "env": {"-u", "--unset", "-C", "--chdir"},
        "time": {"-o", "--output", "-f", "--format"},
        "nice": {"-n", "--adjustment"},
        "stdbuf": {"-i", "-o", "-e"},
    }
    while j < end:
        if assignment.match(tokens[j]):
            j += 1
            continue
        wrapper = tokens[j]
        if wrapper not in wrappers:
            return j
        j += 1
        while j < end:
            token = tokens[j]
            if token == "--":
                j += 1
                break
            if wrapper == "env" and assignment.match(token):
                j += 1
                continue
            if token in takes_value.get(wrapper, set()):
                j += 2
                continue
            if token.startswith("-"):
                j += 1
                continue
            break
    return j

def inspect(tokens, depth=0):
    if depth > 4:
        return ["PARSE_ERROR:nested shell command depth exceeded"]
    found = []
    i = 0
    while i < len(tokens):
        while i < len(tokens) and tokens[i] in separators:
            i += 1
        if i >= len(tokens):
            break
        end = i
        while end < len(tokens) and tokens[end] not in separators:
            end += 1
        cmd = command_index(tokens, i, end)
        if cmd < end and tokens[cmd] in shells:
            # Inspect scripts passed to sh/bash -c, including sudo/command wrappers.
            for k in range(cmd + 1, end - 1):
                if tokens[k] in ("-c", "-lc", "-cl", "-ec", "-ce"):
                    try:
                        found.extend(inspect(tokenize(tokens[k + 1]), depth + 1))
                    except ValueError as exc:
                        found.append("PARSE_ERROR:" + str(exc))
                    break
        elif cmd < end and tokens[cmd] == "git":
            j = cmd + 1
            while j < end:
                t = tokens[j]
                if t in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"):
                    j += 2
                elif t.startswith(("--git-dir=", "--work-tree=", "--namespace=", "--exec-path=")):
                    j += 1
                elif t.startswith("-") and t != "--":
                    j += 1
                else:
                    break
            if j < end and tokens[j] == "push":
                j += 1
                positional = []
                flags = []
                while j < end:
                    t = tokens[j]
                    if t == "--":
                        positional.extend(tokens[j + 1:end])
                        break
                    if t in ("-o", "--push-option", "-r", "--repo", "--receive-pack", "--exec"):
                        j += 2
                        continue
                    if t.startswith(("--push-option=", "--repo=", "--receive-pack=", "--exec=")):
                        j += 1
                        continue
                    if t in ("--all", "--mirror", "--tags", "--delete", "-d"):
                        flags.append(t)
                    if t.startswith("-"):
                        j += 1
                        continue
                    positional.append(t)
                    j += 1

                if any(flag in ("--all", "--mirror", "--tags") for flag in flags):
                    found.append("BLOCK_BROAD_PUSH:" + ",".join(flags))
                else:
                    refspecs = positional[1:] if len(positional) >= 2 else []
                    if not refspecs:
                        found.append("BLOCK_IMPLICIT_REFSPEC")
                    else:
                        for ref in refspecs:
                            dest = ref.rsplit(":", 1)[1] if ":" in ref else ref
                            dest = dest.lstrip("+").removeprefix("refs/heads/")
                            if any(ch in dest for ch in "*?[") or dest in ("", "HEAD"):
                                found.append("BLOCK_AMBIGUOUS_REFSPEC:" + ref)
                            else:
                                found.append("REFSPEC:" + dest)
        i = end + 1
    return found

try:
    result = inspect(tokenize(command))
except ValueError as exc:
    result = ["PARSE_ERROR:" + str(exc)]
print("\n".join(result))
PY
)"; then
  echo "[SecOps] BLOCK: unable to parse the Bash command safely." >&2
  exit 2
fi

if [[ "$PUSH_INFO" == PARSE_ERROR:* ]]; then
  echo "[SecOps] BLOCK: unable to parse the Bash command safely." >&2
  exit 2
fi
if [[ -z "$PUSH_INFO" ]]; then
  exit 0
fi

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
PROTECTED_BRANCH_RE='^(main|master|production)$'
if [[ "$CURRENT_BRANCH" =~ $PROTECTED_BRANCH_RE ]]; then
  echo "[SecOps] BLOCK: pushing from protected branch '$CURRENT_BRANCH' is not allowed. Use a feature branch and open a Pull Request." >&2
  exit 2
fi

while IFS= read -r entry; do
  case "$entry" in
    BLOCK_*)
      echo "[SecOps] BLOCK: $entry. Use an explicit feature-branch refspec; broad or ambiguous pushes are not allowed." >&2
      exit 2
      ;;
    REFSPEC:*)
      destination="${entry#REFSPEC:}"
      if [[ "$destination" =~ $PROTECTED_BRANCH_RE ]]; then
        echo "[SecOps] BLOCK: push destination '$destination' is a protected branch. Use a feature branch and open a Pull Request." >&2
        exit 2
      fi
      ;;
  esac
done <<< "$PUSH_INFO"

# If a push has no explicit refspec, it was already blocked. For an explicit
# source-only refspec, Git's push.default/upstream can still choose a different
# destination; reject protected upstreams rather than assuming source==target.
UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
if [[ "$UPSTREAM" == */main || "$UPSTREAM" == */master || "$UPSTREAM" == */production ]]; then
  while IFS= read -r entry; do
    if [[ "$entry" == REFSPEC:* && "${entry#REFSPEC:}" != *:* ]]; then
      echo "[SecOps] BLOCK: configured upstream '$UPSTREAM' is protected." >&2
      exit 2
    fi
  done <<< "$PUSH_INFO"
fi

# Scan local commits not reachable from remote-tracking refs, including first push.
# Detection is intentionally high-confidence and suppresses common placeholder values.
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "[SecOps] BLOCK: cannot determine HEAD; refusing to push." >&2
  exit 2
fi
while IFS= read -r commit; do
  [[ -z "$commit" ]] && continue
  if git show --format= --no-ext-diff --no-renames "$commit" 2>/dev/null | python3 -c '
import re, sys
patterns = [
    re.compile(r"\bA(?:KIA|SIA)[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\bAccountKey=[A-Za-z0-9+/]{20,}={0,2}"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bpypi-[A-Za-z0-9_-]{50,}\b"),
    re.compile(r"\bSG\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bSK[0-9a-fA-F]{32}\b"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?):\/\/[^\s/:@]+:[^\s@]+@"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*[\"\x27]?([A-Za-z0-9_./+=-]{24,})"),
]
placeholder_prefix = re.compile(r"(?i)^(?:your_|dummy_|redacted_|placeholder_|changeme_|xxxx)")
known_test_values = {"AKIAIOSFODNN7EXAMPLE"}
for line in sys.stdin:
    if line.startswith(("--- ", "+++ ")):
        continue
    for pattern in patterns:
        match = pattern.search(line)
        if match:
            value = match.group(1) if match.lastindex else match.group(0)
            if value in known_test_values or placeholder_prefix.search(value):
                continue
            print("SECRET_FOUND")
            sys.exit(0)
sys.exit(1)
'; then
    echo "[SecOps] BLOCK: secret-like material found in unpushed commit $commit. Remove it from Git history and rotate the credential." >&2
    exit 2
  fi
done < <(git rev-list HEAD --not --remotes)

exit 0
