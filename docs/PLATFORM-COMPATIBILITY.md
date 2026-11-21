# Platform compatibility

Sentinel-Code uses the open Agent Skills format for its portable review workflow. A `SKILL.md` is a reusable set of instructions; it does not make every host's hooks, subagents, MCP wiring, permission controls, or pull-request integrations portable.

## Documented skill discovery paths

| Host | Project path | Notes |
|---|---|---|
| Claude Code | `.claude/skills/<skill>/SKILL.md`; this repository also packages a Claude plugin | Full plugin includes Claude-specific subagent, Mods module, hooks, and optional MCP config |
| Cursor | `.agents/skills/` or `.cursor/skills/` | Cursor also recognizes some Claude and Codex skill paths |
| GitHub Copilot | `.agents/skills/`, `.github/skills/`, or `.claude/skills/` | Availability varies by Copilot surface and IDE version |
| OpenAI Codex | `.agents/skills/` | Loads Skill instructions and optional resources/scripts |
| Gemini CLI | `.agents/skills/` alias or `.gemini/skills/` | Gemini has its own discovery and activation lifecycle |

The canonical Skill lives in `skills/pr-security-review/` for Claude plugin packaging. A byte-identical mirror lives in `.agents/skills/pr-security-review/` for shared project discovery.

## Installing

Run `scripts/install-agent-skills.sh` to copy the canonical folder to one host's native location. Use `--agent shared` for the common `.agents/skills` path, or choose `claude`, `cursor`, `copilot`, `codex`, or `gemini` for a host-specific path.

A project install writes only inside the current workspace. A user install writes under the current user's home directory. The installer does not download packages, install dependencies, alter agent settings, or grant tool permissions.

## Additional hosts

GitHub CLI's preview `gh skill` workflow advertises a wider set of Agent Skills-compatible coding agents, including terminal and IDE agents beyond the five listed above. Availability and exact `--agent` identifiers depend on the installed GitHub CLI release. Check `gh skill --help` and inspect the skill using `gh skill preview` before installation.

## Capability boundaries

| Capability | Claude Code plugin | Other Agent Skills hosts |
|---|---|---|
| Portable security-review workflow | Yes | Yes, when the host supports Agent Skills |
| OWASP reference checklist | Yes | Yes, when the host can read Skill resources |
| Separate read-only subagent | Included | Host-specific; not created automatically |
| Pre-push Git guard | Included as Claude hook | Not installed by the portable Skill |
| Post-edit Prettier hook | Included as Claude hook | Not installed by the portable Skill |
| SecOps terminal dashboard | Included as Claude Mod | Not portable |
| GitHub/Sentry/PostgreSQL MCP wiring | Claude Code config | Configure MCP separately in each host |
| GitHub PR automation | GitHub Actions workflow | Not enabled by installing the Skill |

Do not advertise the portable Skill as a complete native plugin for every host. Cross-platform compatibility applies to the review instructions and supporting reference material.
