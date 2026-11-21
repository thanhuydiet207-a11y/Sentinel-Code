# Sentinel-Code — Multi-Agent DevSecOps Security Review

Sentinel-Code is a security-review toolkit for AI coding agents. Its portable core is an Agent Skill for evidence-based, read-only pull-request and code-change reviews. The Claude Code package adds a Claude plugin, read-only security subagent, lifecycle integrations, optional MCP servers, and Git push safeguards. Portable plugin metadata is also included for the OpenAI/Codex plugin format.

**This toolkit assists a secure development process. It does not replace SAST/DAST, dependency scanning, secret-management controls, server-side branch protection, or human security review. No AI review or scanner can guarantee that all vulnerabilities are found.**

## Capabilities

| Component | What it does | Runtime |
|---|---|---|
| `pr-security-review` Skill | Reviews diffs, traces source-to-sink paths, checks access control, injection, secrets, SSRF, configuration, dependencies, and test gaps | Agent Skills-compatible hosts |
| Claude `security-auditor` | Separate read-only security review | Claude Code subagent |
| Pre-push guard | Blocks configured protected-branch pushes and scans unpushed commits for high-confidence credential patterns | Claude Code hook + Bash, Git, Python 3 |
| Post-edit formatter | Best-effort Prettier formatting; failures never block an edit | Claude Code hook + optional Prettier |
| SecOps status pane | Displays Claude Code tool/edit counters | Claude Code Mods runtime |
| MCP configuration | Optional GitHub, Sentry, and PostgreSQL connections | Claude Code; credentials and remote permissions are separate |
| PR workflow | Runs Claude Code review from GitHub Actions | GitHub Actions + Anthropic API key |
| Portable plugin manifests | Package identity for OpenAI/Codex-compatible plugin loading | ChatGPT/Codex plugin ecosystem; publication is separate |

## Supported AI coding agents

The portable Skill is stored under `skills/pr-security-review/` and mirrored under `.agents/skills/pr-security-review/`.

| Host | Project-level Skill path | Package included |
|---|---|---|
| Claude Code | `.claude/skills/` or Claude plugin | Full Claude plugin |
| Cursor | `.agents/skills/` or `.cursor/skills/` | Portable Skill |
| GitHub Copilot | `.agents/skills/` or `.github/skills/` | Portable Skill |
| OpenAI Codex | `.agents/skills/` | Portable Skill + Codex plugin compatibility manifest |
| Gemini CLI | `.agents/skills/` or `.gemini/skills/` | Portable Skill |
| Antigravity, Amp, Cline, Goose, OpenCode, and other GH CLI-supported agents | Host-specific location selected by GitHub CLI | Portable Skill via `gh skill install` |

The review instructions are portable; Claude-specific Mods, hooks, subagents, MCP config and GitHub Actions do **not** automatically run in other hosts. Each agent uses its own tools and permission model. See [Platform compatibility](docs/PLATFORM-COMPATIBILITY.md).

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

### Cursor, Copilot, Codex, Gemini CLI and other agents

Using the included installer for common targets:

```bash
git clone https://github.com/thanhuydiet207-a11y/Sentinel-Code.git
cd Sentinel-Code
bash scripts/install-agent-skills.sh --agent shared --scope project
```

The shared `.agents/skills/` location is supported by Cursor, GitHub Copilot, Codex, Gemini CLI, and several other coding agents. To install a host-specific location:

```bash
bash scripts/install-agent-skills.sh --agent cursor --scope project
bash scripts/install-agent-skills.sh --agent copilot --scope project
bash scripts/install-agent-skills.sh --agent codex --scope project
bash scripts/install-agent-skills.sh --agent gemini --scope project
bash scripts/install-agent-skills.sh --agent claude --scope project
```

For the broadest agent coverage, use the official GitHub CLI skill installer. It supports many more agent targets and handles their host-specific directories:

```bash
gh skill preview thanhuydiet207-a11y/Sentinel-Code
gh skill install thanhuydiet207-a11y/Sentinel-Code skills/pr-security-review --agent cursor --scope project
gh skill install thanhuydiet207-a11y/Sentinel-Code skills/pr-security-review --agent github-copilot --scope project
gh skill install thanhuydiet207-a11y/Sentinel-Code skills/pr-security-review --agent codex --scope project
gh skill install thanhuydiet207-a11y/Sentinel-Code skills/pr-security-review --agent gemini-cli --scope project
gh skill install thanhuydiet207-a11y/Sentinel-Code skills/pr-security-review --agent antigravity --scope project
gh skill install thanhuydiet207-a11y/Sentinel-Code skills/pr-security-review --agent opencode --scope project
```

Use `--scope user` for a personal installation in your home directory. Run `gh skill install --help` to see the exact agent identifiers supported by your installed GitHub CLI release. The custom installer only copies files; it does not install dependencies, alter agent permissions, configure MCP, or enable hooks.

### ChatGPT and Codex plugin package

The repository includes a portable root `plugin.json` plus a Codex compatibility manifest at `.codex-plugin/plugin.json`. This packages the Skill for OpenAI's Agent Plugins/Codex plugin format. Local plugin marketplace installation or public publication is a separate step and may require additional interface, privacy, support, and review metadata. The Claude `.mcp.json` remains a Claude-specific MCP configuration and is not bundled as a portable OpenAI MCP manifest.

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

Model-based evals call a real model and may incur cost. Run them deliberately, not on every CI push. Eval cases test selected behaviors; they do not prove complete vulnerability coverage.

## Versioning

This development line is version `1.1.0`. Keep `skills/pr-security-review/` and `.agents/skills/pr-security-review/` byte-for-byte identical. Run `tests/validate-agent-skills.py` after changing either copy.
