#!/usr/bin/env python3
"""Run the Sentinel-Code deep audit and emit evidence-based test metrics."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from collections import Counter
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = pathlib.Path(os.environ.get("SENTINEL_AUDIT_DIR", ROOT / ".sentinel-deep-audit"))
OUT.mkdir(parents=True, exist_ok=True)

def write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def read_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))

def run_unit(label: str) -> int:
    started = time.perf_counter()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test*.py")
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    duration = time.perf_counter() - started
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    expected_failures = len(result.expectedFailures)
    unexpected_successes = len(result.unexpectedSuccesses)
    passed = max(0, result.testsRun - failures - errors - skipped - expected_failures - unexpected_successes)
    data = {
        "label": label,
        "python": sys.version.split()[0],
        "tests_run": result.testsRun,
        "passed": passed,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "expected_failures": expected_failures,
        "unexpected_successes": unexpected_successes,
        "duration_seconds": round(duration, 6),
        "success": result.wasSuccessful(),
    }
    (OUT / f"{label}.log").write_text(stream.getvalue(), encoding="utf-8")
    write_json(OUT / f"{label}.json", data)
    print(json.dumps(data, sort_keys=True))
    return 0 if result.wasSuccessful() else 1

def command_record(name: str, argv: list[str], timeout: int = 2400, sensitive: bool = False) -> dict:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv, cwd=ROOT, text=True, capture_output=True, timeout=timeout,
            env={**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")},
        )
        duration = time.perf_counter() - started
        record = {
            "name": name,
            "command": argv,
            "exit_code": completed.returncode,
            "success": completed.returncode == 0,
            "duration_seconds": round(duration, 6),
        }
        if not sensitive:
            output = completed.stdout + completed.stderr
            record["output_tail"] = "\n".join(output.splitlines()[-12:])
        return record
    except subprocess.TimeoutExpired:
        return {
            "name": name, "command": argv, "exit_code": 124, "success": False,
            "duration_seconds": round(time.perf_counter() - started, 6),
            "output_tail": f"Timed out after {timeout} seconds",
        }
    except OSError as exc:
        return {
            "name": name, "command": argv, "exit_code": 127, "success": False,
            "duration_seconds": round(time.perf_counter() - started, 6),
            "output_tail": f"Could not start command: {type(exc).__name__}",
        }

def run_suite() -> int:
    py = sys.executable
    checks: list[dict] = []
    manifests = [
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        ".codex-plugin/plugin.json",
        "plugin.json",
        ".mcp.json",
        "hooks/hooks.json",
        "schemas/security-findings.schema.json",
    ]
    start = time.perf_counter()
    try:
        for relative in manifests:
            read_json(ROOT / relative)
        manifest_check = {
            "name": "Parse all plugin, MCP, hook and findings-schema JSON",
            "command": manifests,
            "exit_code": 0,
            "success": True,
            "duration_seconds": round(time.perf_counter() - start, 6),
            "count": len(manifests),
        }
    except Exception as exc:
        manifest_check = {
            "name": "Parse all plugin, MCP, hook and findings-schema JSON",
            "command": manifests,
            "exit_code": 1,
            "success": False,
            "duration_seconds": round(time.perf_counter() - start, 6),
            "output_tail": f"{type(exc).__name__}: {exc}",
        }
    checks.append(manifest_check)

    shell_files = [
        "scripts/verify-before-push.sh",
        "scripts/format-after-edit.sh",
        "scripts/install-agent-skills.sh",
        "tests/verify-before-push.test.sh",
        "tests/format-after-edit.test.sh",
        "tests/install-agent-skills.test.sh",
    ]
    syntax_checks = [
        command_record("Bash syntax: " + path, ["bash", "-n", path])
        for path in shell_files
    ]
    checks.extend(syntax_checks)
    for name, path in [
        ("Pre-push guard regression suite", "tests/verify-before-push.test.sh"),
        ("Post-edit formatter regression suite", "tests/format-after-edit.test.sh"),
        ("Cross-agent Skill installer regression suite", "tests/install-agent-skills.test.sh"),
    ]:
        checks.append(command_record(name, ["bash", path]))

    for name, path in [
        ("Portable Agent Skill validation", "tests/validate-agent-skills.py"),
        ("Agent Plugins and Codex manifest validation", "tests/validate-plugin-manifests.py"),
        ("Security eval suite structure validation", "tests/validate-eval-suite.py"),
        ("Labeled security benchmark validation", "tests/validate-security-benchmark.py"),
    ]:
        checks.append(command_record(name, [py, path]))

    checks.append(command_record("Compile all Python core and test modules", [py, "-m", "compileall", "-q", "sentinel_core", "tests"]))

    cli_commands = [
        ["--help"],
        ["import-scanner", "--help"],
        ["review-consensus", "--help"],
        ["ai-review", "--help"],
        ["adversarial-review", "--help"],
        ["security-pipeline", "--help"],
        ["validate-patch", "--help"],
        ["test-candidate", "--help"],
        ["compare-scans", "--help"],
        ["review-patch-risk", "--help"],
        ["remediation-report", "--help"],
        ["seal-evidence", "--help"],
        ["verify-evidence", "--help"],
        ["audit-trail", "--help"],
        ["verify-audit-trail", "--help"],
        ["audit-lifecycle", "--help"],
    ]
    for args in cli_commands:
        checks.append(command_record("Security Core CLI " + " ".join(args), [py, "-m", "sentinel_core", *args]))

    benchmark_path = OUT / "benchmark-smoke.json"
    checks.append(command_record(
        "Run seed benchmark against the empty results template",
        [py, "-m", "sentinel_core", "benchmark", "--dataset", "benchmarks/security-review-v1.json",
         "--results", "benchmarks/results-template.json", "--output", str(benchmark_path)],
    ))
    benchmark_metrics = None
    try:
        benchmark = read_json(benchmark_path)
        summary = benchmark["summary"]
        benchmark_metrics = {
            "cases_total": summary.get("cases_total"),
            "cases_scored": summary.get("cases_scored"),
            "precision": summary.get("precision"),
            "recall": summary.get("recall"),
            "f1": summary.get("f1"),
            "case_coverage": summary.get("case_coverage"),
        }
    except Exception as exc:
        benchmark_metrics = {"parse_error": f"{type(exc).__name__}: {exc}"}

    checks.append(command_record("Claude Code CLI version", ["claude", "--version"]))
    checks.append(command_record("Claude plugin strict manifest validation", ["claude", "plugin", "validate", "--strict", "."]))
    checks.append(command_record("Claude plugin runtime/mod tests", ["claude", "plugin", "test", "."], timeout=1200))

    scan_dir = OUT / "scans"
    scanner_check = command_record(
        "Semgrep, Gitleaks and Trivy repository scan plus evidence normalization",
        ["bash", "scripts/run-security-scanners.sh", str(scan_dir)],
        timeout=2400, sensitive=True,
    )
    checks.append(scanner_check)
    scanner_metrics = {"available": False}
    combined = scan_dir / "findings-combined.json"
    if combined.is_file():
        try:
            payload = read_json(combined)
            findings = payload.get("findings", [])
            severity_counts = Counter(
                str(item.get("severity", "unknown")).lower()
                for item in findings if isinstance(item, dict)
            )
            skipped = payload.get("metadata", {}).get("skipped", {})
            scanner_metrics = {
                "available": True,
                "combined_findings": len(findings),
                "severity_counts": dict(sorted(severity_counts.items())),
                "skipped_records": sum(len(v) if isinstance(v, list) else 1 for v in skipped.values()) if isinstance(skipped, dict) else None,
                "scanners": ["semgrep", "gitleaks", "trivy"],
            }
        except Exception as exc:
            scanner_metrics = {"available": False, "parse_error": f"{type(exc).__name__}: {exc}"}

    result = {
        "python": sys.version.split()[0],
        "checks": checks,
        "metrics": {
            "json_manifests_parsed": len(manifests) if manifest_check["success"] else 0,
            "shell_files_syntax_checked": sum(1 for item in syntax_checks if item["success"]),
            "cli_commands_attempted": len(cli_commands),
        },
        "benchmark": benchmark_metrics,
        "security_scan": scanner_metrics,
        "not_executed": [
            "Model-based LLM eval prompts: require a separately configured model/API and may incur usage cost; only eval-suite structure was validated.",
            "Live GitHub/Sentry/PostgreSQL MCP connectivity: requires operator credentials and remote permissions; configuration JSON was parsed but no remote connection was attempted.",
        ],
    }
    write_json(OUT / "plugin-suite.json", result)
    failed = [check["name"] for check in checks if not check["success"]]
    print(f"Deep plugin suite: {len(checks) - len(failed)}/{len(checks)} checks passed")
    if failed:
        print("Failed checks: " + "; ".join(failed))
    return 1 if failed else 0

def make_report() -> int:
    unit_files = [OUT / "python-3.11.json", OUT / "python-3.12.json"]
    unit_runs = []
    for path in unit_files:
        if path.is_file():
            unit_runs.append(read_json(path))
    suite_path = OUT / "plugin-suite.json"
    suite = read_json(suite_path) if suite_path.is_file() else None
    checks = suite["checks"] if suite else []
    failed_checks = [item["name"] for item in checks if not item.get("success")]
    missing = [path.name for path in unit_files if not path.is_file()]
    all_unit_success = len(unit_runs) == 2 and all(item.get("success") for item in unit_runs)
    all_check_success = suite is not None and not failed_checks and not missing
    total_run = sum(item["tests_run"] for item in unit_runs)
    total_passed = sum(item["passed"] for item in unit_runs)
    total_failed = sum(item["failures"] + item["errors"] + item["unexpected_successes"] for item in unit_runs)
    total_skipped = sum(item["skipped"] for item in unit_runs)
    status = "PASS" if all_unit_success and all_check_success else "FAIL"

    lines = [
        "# Sentinel-Code deep plugin audit",
        "",
        f"- Overall result: **{status}**",
        f"- Commit: `{os.environ.get('GITHUB_SHA', 'local/unset')}`",
        f"- Runner: `{os.environ.get('RUNNER_OS', 'local')}`",
        "",
        "## Python unit tests",
        "",
        "| Runtime | Tests run | Passed | Failures | Errors | Skipped | Duration (s) | Result |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in unit_runs:
        lines.append(
            f"| {item['python']} ({item['label']}) | {item['tests_run']} | {item['passed']} | "
            f"{item['failures']} | {item['errors']} | {item['skipped']} | {item['duration_seconds']:.3f} | "
            f"{'PASS' if item['success'] else 'FAIL'} |"
        )
    lines.extend([
        f"| **Total executions** | **{total_run}** | **{total_passed}** | **{total_failed}** | — | **{total_skipped}** | — | {'PASS' if all_unit_success else 'FAIL'} |",
        "",
        "The total is executions across Python runtimes; it is not a count of unique test methods.",
        "",
        "## Plugin checks",
        "",
    ])
    if suite:
        passed = sum(1 for item in checks if item.get("success"))
        lines.append(f"- Command/check results: **{passed}/{len(checks)} passed**")
        lines.append(f"- JSON manifests/schemas parsed: **{suite['metrics']['json_manifests_parsed']}**")
        lines.append(f"- Shell files syntax-checked: **{suite['metrics']['shell_files_syntax_checked']}**")
        lines.append(f"- CLI commands attempted: **{suite['metrics']['cli_commands_attempted']}**")
        lines.append("")
        lines.append("| Check | Exit code | Duration (s) | Result |")
        lines.append("|---|---:|---:|---|")
        for item in checks:
            lines.append(f"| {item['name']} | {item['exit_code']} | {item['duration_seconds']:.3f} | {'PASS' if item['success'] else 'FAIL'} |")
        if failed_checks:
            lines.extend(["", "### Failed checks", ""])
            lines.extend(f"- {name}" for name in failed_checks)
        benchmark = suite.get("benchmark")
        if benchmark and "cases_total" in benchmark:
            lines.extend([
                "",
                "## Benchmark smoke run",
                "",
                f"- Dataset cases: **{benchmark.get('cases_total')}**",
                f"- Scored cases: **{benchmark.get('cases_scored')}**",
                f"- Precision: **{benchmark.get('precision')}**",
                f"- Recall: **{benchmark.get('recall')}**",
                f"- F1: **{benchmark.get('f1')}**",
                f"- Case coverage: **{benchmark.get('case_coverage')}**",
                "",
                "This uses the repository's empty results template; these are pipeline/empty-input semantics, not model detection-quality scores.",
            ])
        scan = suite.get("security_scan", {})
        lines.extend(["", "## Automated scanner output", ""])
        if scan.get("available"):
            lines.append(f"- Combined normalized findings: **{scan.get('combined_findings')}**")
            lines.append(f"- Severity counts: `{json.dumps(scan.get('severity_counts', {}), sort_keys=True)}`")
            lines.append(f"- Skipped records: **{scan.get('skipped_records')}**")
        else:
            lines.append("- Scanner result metrics unavailable; inspect the workflow logs for the scanner command outcome.")
    else:
        lines.extend(["- Plugin suite report was not produced."])
    lines.extend(["", "## Not executed", ""])
    not_executed = suite.get("not_executed", []) if suite else []
    lines.extend(f"- {item}" for item in not_executed)
    if missing:
        lines.extend(["", "Missing reports: " + ", ".join(missing)])
    lines.append("")
    report = "\n".join(lines)
    (OUT / "audit-report.md").write_text(report, encoding="utf-8")
    metrics = {
        "status": status,
        "commit": os.environ.get("GITHUB_SHA"),
        "python_runs": unit_runs,
        "total_test_executions": total_run,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "plugin_checks_passed": sum(1 for item in checks if item.get("success")),
        "plugin_checks_total": len(checks),
        "missing_reports": missing,
        "failed_checks": failed_checks,
    }
    write_json(OUT / "audit-metrics.json", metrics)
    print(report)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(report + "\n")
    return 0 if status == "PASS" else 1

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    unit = sub.add_parser("unit")
    unit.add_argument("--label", required=True, choices=["python-3.11", "python-3.12"])
    sub.add_parser("suite")
    sub.add_parser("report")
    args = parser.parse_args()
    if args.mode == "unit":
        return run_unit(args.label)
    if args.mode == "suite":
        return run_suite()
    return make_report()

if __name__ == "__main__":
    raise SystemExit(main())
