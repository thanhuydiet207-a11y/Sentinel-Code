# Sentinel-Code — Multi-Agent DevSecOps Security Review

Sentinel-Code is a security-review toolkit for AI coding agents. Its portable core is an Agent Skill for evidence-based, read-only pull-request and code-change reviews. The Claude Code package adds a Claude plugin, a read-only security subagent, lifecycle integrations, optional MCP servers, and Git push safeguards.

**This toolkit assists a secure development process. It does not replace SAST/DAST, dependency scanning, secret-management controls, server-side branch protection, or human security review. No AI review or scanner can guarantee that all vulnerabilities are found.**

## Capabilities

| Component | What it does | Runtime |
|---|---|---|
| `pr-security-review` Skill | Reviews diffs, traces source-to-sink paths, checks access control, injection, secrets, SSRF, configuration, dependencies, and test gaps | Agent Skills-compatible hosts |
| `security-auditor` | Separate read-only security review | Claude Code subagent |
| Pre-push guard | Blocks configured protected-branch pushes and scans unpushed commits for high-confidence credential patterns | Claude Code hook + Bash, Git, Python 3 |
| Post-edit formatter | Best-effort Prettier formatting; failures never block an edit | Claude Code hook + optional Prettier |
| SecOps status pane | Displays Claude Code tool/edit counters | Claude Code Mods runtime |
| MCP configuration | Optional GitHub, Sentry, and PostgreSQL connections | Claude Code; credentials and remote permissions are separate |
| PR workflow | Runs Claude Code review from GitHub Actions | GitHub Actions + Anthropic API key |

## Multi-platform support

The portable Skill is mirrored at `.agents/skills/pr-security-review/SKILL.md`.

| Agent / host | Documented project skill location | Integration supplied here |
|---|---|---|
| Claude Code | Plugin `skills/`; standalone `.claude/skills/` | Full Claude plugin, subagent, Mods and hooks |
| Cursor | `.agents/skills/` or `.cursor/skills/` | Portable Skill |
| GitHub Copilot | `.agents/skills/` or `.github/skills/` | Portable Skill |
| OpenAI Codex | `.agents/skills/` | Portable Skill |
| Gemini CLI | `.agents/skills/` alias or `.gemini/skills/` | Portable Skill |

The shared `.agents/skills/` copy is the default cross-host installation for Cursor, Copilot, Codex and Gemini CLI. The instructions are portable; Claude-specific Mods, hooks, subagents, MCP config and GitHub Actions do **not** automatically run in those other hosts. Each host uses its own tools and permission model. See [Platform compatibility](docs/PLATFORM-COMPATIBILITY.md).

## Install

### Claude Code plugin

In Claude Code:

```text
/plugin marketplace add thanhuydiet207-a11y/Sentinel-Code
/plugin install secops-review-kit@internal-secops-marketplace
```

Or in a terminal:

```bash
claude plugin marketplace add thanhuydiet207-a11y/Sentinel-Code
claude plugin install secops-review-kit@internal-secops-marketplace --scope user
```

### Cursor, Copilot, Codex, Gemini CLI

Clone the repository and install the shared Agent Skill:

```bash
git clone https://github.com/thanhuydiet207-a11y/Sentinel-Code.git
cd Sentinel-Code
bash scripts/install-agent-skills.sh --agent shared --scope project
```

To install into a host-specific path instead:

```bash
bash scripts/install-agent-skills.sh --agent cursor --scope project
bash scripts/install-agent-skills.sh --agent copilot --scope project
bash scripts/install-agent-skills.sh --agent codex --scope project
bash scripts/install-agent-skills.sh --agent gemini --scope project
bash scripts/install-agent-skills.sh --agent claude --scope project
```

Use one location per host/workspace to avoid duplicate skill discovery. Use `--scope user` for a personal installation under your home directory. The installer only copies files; it does not install dependencies, change permissions, configure MCP, or enable hooks.

### GitHub CLI skill installer (optional)

Recent GitHub CLI releases include a preview `gh skill` command that can install skills into supported agent-specific locations. Check `gh skill --help` for your installed version and inspect the package with `gh skill preview` before installing skills from any repository.

## Optional MCP servers

The repository's `.mcp.json` is a Claude Code MCP configuration, not a universal configuration for all agents. It does not grant permissions by itself.

- **GitHub:** use a fine-grained token restricted to the intended repository and required permissions.
- **Sentry:** complete the authentication flow required by the Sentry MCP endpoint.
- **PostgreSQL:** use a dedicated database role with effective read-only privileges. Follow [MCP security configuration](docs/MCP-SECURITY.md).

Do not commit tokens, passwords, connection strings, or local secrets. A server name such as `postgres-readonly` does not enforce read-only access.

## Git push protection

The Claude Code PreToolUse hook examines Bash commands before execution. It is a client-side safety guard, not a server-side authorization boundary. It parses a limited shell grammar and scans local commits not reachable from remote-tracking refs for high-confidence credential patterns.

Requirements: Bash, Git and Python 3. If Python is unavailable, normal non-push Bash commands are allowed; commands that look like Git pushes are blocked because they cannot be checked safely.

The parser is not a full shell interpreter and cannot recognize every possible command construction. Enforce protected branches and secret scanning on the Git hosting service as authoritative controls.

## Validation

On Linux with Bash, Git, jq and Python 3:

```bash
bash -n scripts/verify-before-push.sh
bash -n scripts/format-after-edit.sh
bash -n scripts/install-agent-skills.sh
bash tests/verify-before-push.test.sh
bash tests/format-after-edit.test.sh
bash tests/install-agent-skills.test.sh
python3 tests/validate-agent-skills.py
python3 tests/validate-eval-suite.py
```

Validate the Claude plugin with a compatible Claude Code CLI:

```bash
claude plugin validate --strict .
claude plugin test .
```

Model-based evals call a real model and may incur cost. Run them deliberately, not on every CI push:

```bash
claude plugin eval . --runs 1 --ablation none --threshold 0.8 --no-publish --max-cost-usd 5
```

Eval cases test selected behaviors; they do not prove complete vulnerability coverage.

## Versioning

This development line is version `1.1.0`. Keep `skills/pr-security-review/SKILL.md` and `.agents/skills/pr-security-review/SKILL.md` byte-for-byte identical. Run `tests/validate-agent-skills.py` after changing either copy.
