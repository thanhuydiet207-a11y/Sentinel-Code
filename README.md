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

The repository includes a schema-declared root `plugin.json` for the portable Agent Plugins format and a Codex compatibility manifest at `.codex-plugin/plugin.json`. The root manifest points OpenAI setup to the packaged review Skill through `extensions.com.openai.onboardingSkill`; the `skills/` directory is discovered by the portable package format. The Claude `.mcp.json` remains Claude-specific and is not copied into the OpenAI package because its transport and authentication settings have not been revalidated for portable MCP use. The package has not been submitted to or published in a public plugin directory; publication requires separate listing, privacy, support, and review metadata.

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

## Sentinel Security Core

The repository includes a dependency-free Python core for deterministic finding validation, source-evidence verification, de-duplication, prioritization, Markdown reporting, and benchmark scoring.

### Finding workflow

1. Ask the AI agent or scanner to produce the shared JSON finding schema.
2. Calculate a source-line digest without copying the source excerpt into the report:
   `python3 -m sentinel_core hash-lines --root . --path src/file.py --start 12 --end 14`
3. Validate schema, repository-relative path, line range, and SHA-256 evidence:
   `python3 -m sentinel_core validate findings.json --root .`
4. De-duplicate and rank validated findings:
   `python3 -m sentinel_core dedupe findings.json --root . --output findings.dedup.json`
5. Generate a Markdown report:
   `python3 -m sentinel_core report findings.json --root . --scope "PR #123" --output security-report.md`

The priority score is severity base multiplied by finding confidence. It is an internal triage aid, **not CVSS**, and does not independently determine severity.

### Multi-provider AI review (opt-in)

Optional API adapters support OpenAI, Anthropic, and Gemini. Configure keys via environment variables and explicitly run:

```bash
python3 -m sentinel_core ai-review findings.json --providers openai anthropic gemini --output reviews.json
python3 -m sentinel_core review-consensus findings.json reviews.json --output consensus.json
```

API calls may incur charges and send finding data to selected providers. See [provider adapters](docs/AI-PROVIDER-ADAPTERS.md). No keys are stored and provider responses remain advisory.

### Offline AI review consensus

Sentinel-Code can aggregate imported AI reviewer verdicts without provider credentials or network calls:

```bash
python3 -m sentinel_core review-consensus findings.json reviews.json --output consensus.json
```

This phase summarizes reviewer votes and disagreements; it never automatically suppresses findings. See [AI review consensus](docs/AI-REVIEW-CONSENSUS.md) for the input contract and limitations.

### Benchmark workflow

See [benchmarks/README.md](benchmarks/README.md). Run the seed benchmark with:

```bash
python3 -m sentinel_core benchmark --dataset benchmarks/security-review-v1.json --results benchmarks/results-template.json
```

The seed set contains 16 synthetic cases, including safe negative controls. It is a regression harness, not a statistically representative security benchmark. Agent results must be collected separately; the checked-in template intentionally makes no accuracy claim.

## Versioning

This development line is version `1.1.0`. Keep `skills/pr-security-review/` and `.agents/skills/pr-security-review/` byte-for-byte identical. Run `tests/validate-agent-skills.py` after changing either copy.


## End-to-end Security Core pipeline

The deterministic CLI can combine normalized findings with existing Semgrep, Gitleaks,
and Trivy JSON output, then run evidence validation, deduplication, correlation,
false-positive triage, three-stage adversarial AI review, evidence-reference checks,
and a combined report:

```bash
python3 -m sentinel_core security-pipeline findings.json \
  --root . \
  --scanner-input semgrep=artifacts/semgrep.json \
  --scanner-input gitleaks=artifacts/gitleaks.json \
  --scanner-input trivy=artifacts/trivy.json \
  --providers openai anthropic gemini \
  --output artifacts/security-pipeline.json
```

The scanner JSON files must already exist; this command imports results but does not
launch scanner executables. The AI stages make three sequential requests per selected
provider and may incur provider charges. Invalid source evidence stops execution before
AI requests. The pipeline is advisory and never suppresses findings automatically.
See [Security Pipeline Orchestration](docs/SECURITY-PIPELINE-ORCHESTRATION.md).


## Phase 4A: Safe Remediation Patch Validation

Validate an AI-proposed unified diff against a finding and the current source without modifying files:

\`\`\`bash
python3 -m sentinel_core validate-patch proposal.json findings.json \\
  --root . --output artifacts/patch-validation.json
\`\`\`

A proposal must identify the finding, exact repository-relative source path, current file SHA-256, and a single-file unified diff. Stale hashes, mismatched paths, traversal, invalid hunk context, and unsupported patches are rejected. The output contains candidate content and its hash; it is not applied automatically. See [Remediation Patch Validation](docs/REMEDIATION-PATCH-VALIDATION.md).


## Phase 4B: Remediation Test Sandbox

Run explicit test/scanner commands against a candidate in a temporary workspace without modifying the repository:

    python3 -m sentinel_core test-candidate proposal.json --root . --timeout 120 --output artifacts/candidate-tests.json

Proposal JSON contains \`candidate_path\`, \`candidate_content\`, and \`commands\` (argv arrays). Commands are allowlisted, shell execution is disabled, and the runner stops on the first failure or timeout. This temporary workspace is **not OS-level isolation**; see [sandbox limitations](docs/REMEDIATION-TEST-SANDBOX.md). Do not run untrusted candidate code without a disposable container or VM.
