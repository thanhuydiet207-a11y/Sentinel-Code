#!/usr/bin/env bash
set -euo pipefail

INPUT_JSON="$(cat)"
if ! command -v jq >/dev/null 2>&1; then
  echo "[SecOps] BLOCK: jq is required to validate the PreToolUse payload." >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[SecOps] BLOCK: python3 is required to safely parse Bash command arguments." >&2
  exit 2
fi
if ! COMMAND_STR="$(printf '%s' "$INPUT_JSON" | jq -er '.tool_input.command | strings')"; then
  echo "[SecOps] BLOCK: invalid or missing tool_input.command payload." >&2
  exit 2
fi

# Parse shell-like tokens with quoting support. This is deliberately conservative:
# ambiguous pushes (implicit refspec, --all, --mirror, --tags) are blocked.
if ! PUSH_INFO="$(COMMAND_STR="$COMMAND_STR" python3 - <<'PY'
import os, shlex, sys
command = os.environ.get("COMMAND_STR", "")
try:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)
except ValueError as exc:
    print(f"PARSE_ERROR:{exc}")
    sys.exit(0)

separators = {";", "&&", "||", "|", "&", "\n"}
found = []
i = 0
while i < len(tokens):
    if tokens[i] != "git":
        i += 1
        continue
    j = i + 1
    # Git global options that consume a value.
    while j < len(tokens) and tokens[j] not in separators:
        t = tokens[j]
        if t in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"):
            j += 2
        elif t.startswith(("--git-dir=", "--work-tree=", "--namespace=", "--exec-path=")):
            j += 1
        elif t.startswith("-") and t not in ("--",):
            j += 1
        else:
            break
    if j >= len(tokens) or tokens[j] != "push":
        i += 1
        continue
    j += 1
    positional = []
    flags = []
    while j < len(tokens) and tokens[j] not in separators:
        t = tokens[j]
        if t == "--":
            positional.extend(tokens[j+1:])
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
        # A single positional argument is a repository, not a sufficiently
        # explicit destination. No positional argument uses configured defaults.
        refspecs = positional[1:] if len(positional) >= 2 else []
        if not refspecs:
            found.append("BLOCK_IMPLICIT_REFSPEC")
        else:
            for ref in refspecs:
                if ":" in ref:
                    dest = ref.rsplit(":", 1)[1]
                else:
                    dest = ref
                dest = dest.lstrip("+").removeprefix("refs/heads/")
                if any(ch in dest for ch in "*?[") or dest in ("", "HEAD"):
                    found.append("BLOCK_AMBIGUOUS_REFSPEC:" + ref)
                else:
                    found.append("REFSPEC:" + dest)
    i = j
print("\n".join(found))
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
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?):\/\/[^\s/:@]+:[^\s@]+@"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*[\"\x27]?([A-Za-z0-9_./+=-]{24,})"),
]
placeholders = ("example", "changeme", "your_", "dummy", "test_", "redacted", "placeholder", "xxxx")
for line in sys.stdin:
    if line.startswith(("--- ", "+++ ")):
        continue
    for pattern in patterns:
        match = pattern.search(line)
        if match:
            value = match.group(1) if match.lastindex else match.group(0)
            if any(word in value.lower() for word in placeholders):
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
