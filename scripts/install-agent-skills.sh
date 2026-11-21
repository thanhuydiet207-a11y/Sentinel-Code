#!/usr/bin/env bash
set -euo pipefail
usage() {
  cat <<'USAGE'
Install the Sentinel-Code Agent Skill into one host's native project or user directory.
Usage:
  bash scripts/install-agent-skills.sh [--agent shared|claude|cursor|copilot|codex|gemini] [--scope project|user]
Options:
  --agent   Target host. "shared" uses .agents/skills (default).
  --scope   "project" installs in the current repository (default);
            "user" installs under the current user's home directory.
  -h, --help  Show this help.
The installer only copies the Skill folder. It does not install dependencies,
change agent permissions, configure MCP, or enable hooks.
USAGE
}
AGENT="shared"
SCOPE="project"
while (($#)); do
  case "$1" in
    --agent) (($# >= 2)) || { echo "Missing value for --agent" >&2; exit 2; }; AGENT="$2"; shift 2 ;;
    --scope) (($# >= 2)) || { echo "Missing value for --scope" >&2; exit 2; }; SCOPE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SOURCE="$REPO_ROOT/skills/pr-security-review"
[[ -f "$SOURCE/SKILL.md" ]] || { echo "Skill source not found: $SOURCE" >&2; exit 1; }
case "$SCOPE" in
  project) BASE="$PWD" ;;
  user) BASE="$HOME" ;;
  *) echo "Invalid scope: $SCOPE" >&2; exit 2 ;;
esac
case "$AGENT" in
  shared|codex) DEST_ROOT="$BASE/.agents/skills" ;;
  claude) DEST_ROOT="$BASE/.claude/skills" ;;
  cursor) DEST_ROOT="$BASE/.cursor/skills" ;;
  copilot)
    if [[ "$SCOPE" == "user" ]]; then DEST_ROOT="$BASE/.copilot/skills"; else DEST_ROOT="$BASE/.github/skills"; fi
    ;;
  gemini) DEST_ROOT="$BASE/.gemini/skills" ;;
  *) echo "Invalid agent: $AGENT" >&2; usage >&2; exit 2 ;;
esac
DEST="$DEST_ROOT/pr-security-review"
mkdir -p -- "$DEST"
cp -R -- "$SOURCE/." "$DEST/"
echo "Installed pr-security-review for $AGENT ($SCOPE) at: $DEST"
