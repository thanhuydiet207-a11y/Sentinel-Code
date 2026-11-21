# Platform compatibility

Sentinel-Code uses the open Agent Skills format for its portable review workflow. A `SKILL.md` is a reusable set of instructions; it does not make every host's hooks, subagents, MCP wiring, permission controls, or pull-request integrations portable.

## Documented skill discovery paths

| Host | Project path | Notes |
|---|---|---|
| Claude Code | `.claude/skills/<skill>/SKILL.md`; this repository also packages a Claude plugin | Full plugin includes Claude-specific subagent, Mods module, hooks, and optional MCP config |
| Cursor | `.agents/skills/` or `.cursor/skills/` | Cursor discovers shared Agent Skills and its own directory |
| GitHub Copilot | `.agents/skills/` or `.github/skills/` | Exact support varies by Copilot surface and version |
| OpenAI Codex | `.agents/skills/` | Portable Skill plus Codex compatibility manifest |
| Gemini CLI | `.agents/skills/` or `.gemini/skills/` | Gemini has its own discovery and activation lifecycle |

For the wider ecosystem, GitHub CLI's `gh skill install` supports numerous additional coding agents, including Antigravity, Amp, Cline, Goose, OpenCode and others. Check `gh skill install --help` for the current supported identifiers and use the command to place the Skill in the selected host's native directory.

The canonical Skill lives in `skills/pr-security-review/` for Claude and plugin packaging. A byte-identical mirror (including the OWASP reference) lives in `.agents/skills/pr-security-review/` for shared project discovery.

## Installing

For common agents, run `scripts/install-agent-skills.sh` to copy the canonical Skill folder to one host's native location. Use `--agent shared` for the common `.agents/skills` path, or choose `claude`, `cursor`, `copilot`, `codex`, or `gemini` for a host-specific path.

For wider coverage, GitHub CLI can install from this repository directly:

```bash
gh skill preview thanhuydiet207-a11y/Sentinel-Code
gh skill install thanhuydiet207-a11y/Sentinel-Code skills/pr-security-review --agent antigravity --scope project
gh skill install thanhuydiet207-a11y/Sentinel-Code skills/pr-security-review --agent opencode --scope project
```

The exact agent identifiers depend on the installed GitHub CLI version. A project install writes inside the current workspace; a user install writes in the selected host's personal skill directory.

## OpenAI/Codex plugin packaging

The root `plugin.json` is the portable Agent Plugins manifest. The `.codex-plugin/plugin.json` file is the Codex compatibility manifest. Both point to the package identity; the canonical workflow remains in `skills/`. The repository does not claim that the plugin has been submitted to or published in a public plugin directory.

The Claude `.mcp.json` is not an Agent Plugins portable MCP file. ChatGPT/Codex portable MCP configuration uses a distinct root `mcp.json` schema and requires transport/auth metadata. It is intentionally not generated from the Claude configuration without revalidating each server's authentication and transport support.

## Capability boundaries

| Capability | Claude Code plugin | Other Agent Skills hosts |
|---|---|---|
| Portable security-review workflow | Yes | Yes, when host supports Agent Skills |
| OWASP reference checklist | Yes | Yes, when host can read Skill resources |
| Separate read-only subagent | Included | Host-specific; not created automatically |
| Pre-push Git guard | Included as Claude hook | Not installed by portable Skill |
| Post-edit Prettier hook | Included as Claude hook | Not installed by portable Skill |
| SecOps terminal dashboard | Included as Claude Mod | Not portable |
| GitHub/Sentry/PostgreSQL MCP wiring | Claude Code config | Configure MCP separately in each host |
| GitHub PR automation | GitHub Actions workflow | Not enabled by installing the Skill |

Do not advertise the portable Skill as a complete native plugin for every host. Cross-platform compatibility applies to the review instructions and supporting reference material.
