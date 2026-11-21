# Sentinel-Code agent instructions

When a user asks for a security review, PR review, pre-merge audit, or secret-exposure review, invoke the `pr-security-review` Agent Skill if it is available.

The Skill is a read-only review workflow. Do not modify files, commit, push, approve, or merge as part of the review. Report exact file/line evidence, separate confirmed findings from potential risks, and state the scope and tests actually performed.

Platform-specific guards are not automatically portable. Respect the host's own permission model and never claim Claude Code hooks, subagents, MCP connections, or dashboard features are active on another host unless separately configured.
