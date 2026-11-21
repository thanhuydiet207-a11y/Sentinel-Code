# Remediation Test Sandbox (Phase 4B)

The runner copies repository files into a temporary workspace, excludes common generated directories and secret-like files, writes one candidate file, and executes explicitly configured test/scanner commands using argv (never a shell). It stops at the first failed or timed-out command and never writes back to the original repository.

## API

    from sentinel_core.remediation_sandbox import run_remediation_sandbox
    result = run_remediation_sandbox(
        repository_root=".",
        candidate_path="src/example.py",
        candidate_content="candidate source",
        commands=[
            ["python3", "-m", "unittest", "discover", "-s", "tests"],
            ["semgrep", "scan", "--config", "auto", "."],
        ],
        timeout_seconds=120,
    )

Executable allowlist: python, python3, pytest, semgrep, gitleaks, trivy. Commands are argv arrays, no shell operators. At most 20 commands; timeout 1–600 seconds. Environment variables are minimized; credentials and environment secrets are not forwarded.

## Important limitation

This is a temporary copied workspace, **not OS-level isolation**. Tests and scanner plugins may execute code and may have access to the host network or kernel. Only run trusted, reviewed commands and candidate patches. For untrusted AI patches, use a disposable container/VM with network disabled, non-root user, resource limits, and mounted workspace only. This phase does not apply patches to the original repository or authorize automatic merging.
