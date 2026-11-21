# Phase 4P.2 — Recover Phase 4I–4O runtime files

## Recovery source

Runtime files and tests were recovered from the GitHub branch associated with merged PR #45 (Phase 4O), preserving the latest stacked implementation rather than reimplementing from the audit summary.

Recovered:
- `sentinel_core/remediation_orchestrator.py`
- `sentinel_core/workflow_state.py`
- `tests/test_remediation_orchestrator.py`
- `tests/test_workflow_state.py`
- `.github/workflows/sentinel-core-tests.yml`

The current-main `sentinel_core/cli.py` was retained and extended with the orchestrator and workflow commands from the recovered feature branch, rather than replacing the current CLI wholesale.

## Compatibility approach

- Current `main` policy engine and other modules were not overwritten.
- The recovered orchestrator imports current core modules; compatibility is not yet runtime-verified.
- The dedicated CI workflow compiles `sentinel_core` and `tests`, runs unittest discovery, and checks the CLI entry point on Python 3.11 and 3.12.

## Verification

No local test runner is available through the GitHub connector. Tests are included in this PR and should be executed by GitHub Actions. Do not mark this recovery verified until both matrix jobs complete successfully and any failures are resolved.

## Safety

The orchestration remains advisory: no automatic patch application or merge. Checkpoint data is local and may contain candidate patch output; restrict access and revalidate external side effects before using cached evidence.
