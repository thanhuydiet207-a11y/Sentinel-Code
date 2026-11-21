"""Command-line interface for the Sentinel-Code Security Core."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .benchmark import evaluate_benchmark
from .core import deduplicate_findings, line_hash_for_file, load_json, render_markdown_report, validate_payload
from .scanner_adapters import SUPPORTED, import_scanner_results
from .correlation import correlate_findings
from .false_positive import analyze_findings
from .ai_review import aggregate_reviews
from .provider_adapters import run_provider_reviews
from .evidence_verification import verify_ai_evidence
from .adversarial_review import run_adversarial_reviews
from .security_pipeline import run_security_pipeline
from .patch_validation import validate_patch_proposal


def _write_json(value: Any, destination: str | None) -> None:
    rendered = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if destination:
        Path(destination).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def _load_and_validate(input_path: str, root: str) -> dict[str, Any]:
    payload = load_json(input_path)
    errors = validate_payload(payload, Path(root))
    if errors:
        raise ValueError("\n".join(errors))
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sentinel-security", description="Sentinel-Code deterministic finding and benchmark engine")
    sub = parser.add_subparsers(dest="command", required=True)

    hash_parser = sub.add_parser("hash-lines", help="Calculate SHA-256 for a repository line range")
    hash_parser.add_argument("--root", default=".")
    hash_parser.add_argument("--path", required=True)
    hash_parser.add_argument("--start", type=int, required=True)
    hash_parser.add_argument("--end", type=int, required=True)

    validate_parser = sub.add_parser("validate", help="Validate finding schema, safe paths, and source evidence")
    validate_parser.add_argument("input")
    validate_parser.add_argument("--root", default=".")

    dedupe_parser = sub.add_parser("dedupe", help="Validate and collapse exact rule/location duplicates")
    dedupe_parser.add_argument("input")
    dedupe_parser.add_argument("--root", default=".")
    dedupe_parser.add_argument("--output")

    report_parser = sub.add_parser("report", help="Generate a Markdown security report")
    report_parser.add_argument("input")
    report_parser.add_argument("--root", default=".")
    report_parser.add_argument("--scope", default="unspecified")
    report_parser.add_argument("--output")

    bench_parser = sub.add_parser("benchmark", help="Evaluate findings against labeled ground truth")
    bench_parser.add_argument("--dataset", required=True)
    bench_parser.add_argument("--results", required=True)
    bench_parser.add_argument("--output")

    correlate_parser = sub.add_parser("correlate", help="Correlate findings from multiple scanner JSON packages")
    correlate_parser.add_argument("inputs", nargs="+")
    correlate_parser.add_argument("--output")

    triage_parser = sub.add_parser("triage", help="Flag findings with weak evidence for manual review")
    triage_parser.add_argument("input")
    triage_parser.add_argument("--output")

    ai_parser = sub.add_parser("ai-review", help="Run opt-in provider API reviews; requires environment API keys")
    ai_parser.add_argument("findings")
    ai_parser.add_argument("--providers", nargs="+", choices=("openai", "anthropic", "gemini"), required=True)
    ai_parser.add_argument("--output", required=True)

    consensus_parser = sub.add_parser("review-consensus", help="Aggregate offline AI reviewer outputs without suppressing findings")
    consensus_parser.add_argument("findings")
    consensus_parser.add_argument("reviews")
    consensus_parser.add_argument("--output")

    adversarial_parser = sub.add_parser("adversarial-review", help="Run independent, challenger, and adjudicator AI review stages")
    adversarial_parser.add_argument("findings")
    adversarial_parser.add_argument("--providers", nargs="+", choices=("openai", "anthropic", "gemini"), required=True)
    adversarial_parser.add_argument("--output", required=True)

    verify_parser = sub.add_parser("verify-ai-evidence", help="Verify AI reviewer evidence references against local source")
    verify_parser.add_argument("findings")
    verify_parser.add_argument("reviews")
    verify_parser.add_argument("--root", default=".")
    verify_parser.add_argument("--output")

    pipeline_parser = sub.add_parser("security-pipeline", help="Run validation, scanner imports, triage, correlation, adversarial AI review, and evidence verification")
    pipeline_parser.add_argument("findings")
    pipeline_parser.add_argument("--root", default=".")
    pipeline_parser.add_argument("--scanner-input", action="append", default=[], metavar="SCANNER=PATH")
    pipeline_parser.add_argument("--providers", nargs="+", choices=("openai", "anthropic", "gemini"), required=True)
    pipeline_parser.add_argument("--output", required=True)

    patch_parser = sub.add_parser("validate-patch", help="Validate an AI patch proposal against current source without applying it")
    patch_parser.add_argument("proposal")
    patch_parser.add_argument("findings")
    patch_parser.add_argument("--root", default=".")
    patch_parser.add_argument("--output")

    import_parser = sub.add_parser("import-scanner", help="Import Semgrep, Gitleaks, or Trivy JSON with local evidence hashes")
    import_parser.add_argument("scanner", choices=SUPPORTED)
    import_parser.add_argument("input")
    import_parser.add_argument("--root", default=".")
    import_parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "hash-lines":
            root = Path(args.root).resolve()
            relative = Path(args.path)
            if relative.is_absolute() or ".." in relative.parts or "\\" in args.path:
                raise ValueError("path must be repository-relative without traversal segments")
            source = (root / relative).resolve(strict=True)
            source.relative_to(root)
            print(line_hash_for_file(source, args.start, args.end))
            return 0

        if args.command == "validate":
            payload = load_json(args.input)
            errors = validate_payload(payload, Path(args.root))
            if errors:
                for error in errors:
                    print(f"FAIL: {error}", file=sys.stderr)
                return 1
            print(f"PASS: validated {len(payload['findings'])} finding(s) and verified source evidence.")
            return 0

        if args.command == "dedupe":
            payload = _load_and_validate(args.input, args.root)
            output = dict(payload)
            output["findings"] = deduplicate_findings(payload["findings"])
            _write_json(output, args.output)
            return 0

        if args.command == "report":
            payload = _load_and_validate(args.input, args.root)
            markdown = render_markdown_report(payload["findings"], args.scope)
            if args.output:
                Path(args.output).write_text(markdown, encoding="utf-8")
            else:
                sys.stdout.write(markdown)
            return 0

        if args.command == "benchmark":
            dataset = load_json(args.dataset)
            results = load_json(args.results)
            _write_json(evaluate_benchmark(dataset, results), args.output)
            return 0

        if args.command == "correlate":
            payloads = [load_json(path) for path in args.inputs]
            _write_json(correlate_findings(payloads), args.output)
            return 0

        if args.command == "triage":
            _write_json(analyze_findings(load_json(args.input)), args.output)
            return 0

        if args.command == "ai-review":
            findings_data = load_json(args.findings)
            reviews_data = run_provider_reviews(findings_data, args.providers)
            _write_json(reviews_data, args.output)
            print("AI provider review package written.", file=sys.stderr)
            return 0

        if args.command == "review-consensus":
            findings_data = load_json(args.findings)
            reviews_data = load_json(args.reviews)
            _write_json(aggregate_reviews(findings_data, reviews_data), args.output)
            return 0

        if args.command == "adversarial-review":
            findings_data = load_json(args.findings)
            result = run_adversarial_reviews(findings_data, args.providers)
            _write_json(result, args.output)
            print("Adversarial AI review package written.", file=sys.stderr)
            return 0

        if args.command == "verify-ai-evidence":
            findings_data = load_json(args.findings)
            reviews_data = load_json(args.reviews)
            _write_json(verify_ai_evidence(findings_data, reviews_data, args.root), args.output)
            return 0

        if args.command == "security-pipeline":
            scanner_inputs = []
            for specification in args.scanner_input:
                scanner, separator, input_path = specification.partition("=")
                if not separator or not scanner or not input_path:
                    raise ValueError("--scanner-input must use SCANNER=PATH")
                if scanner not in SUPPORTED:
                    raise ValueError("scanner must be one of: " + ", ".join(SUPPORTED))
                scanner_inputs.append({"scanner": scanner, "data": load_json(input_path)})
            findings_data = load_json(args.findings)
            result = run_security_pipeline(
                findings_data, args.root, args.providers, scanner_inputs=scanner_inputs
            )
            _write_json(result, args.output)
            print("Security pipeline report written.", file=sys.stderr)
            return 0

        if args.command == "validate-patch":
            proposal = load_json(args.proposal)
            findings_data = load_json(args.findings)
            result = validate_patch_proposal(proposal, findings_data, args.root)
            _write_json(result, args.output)
            print("Patch proposal validated; source file was not modified.", file=sys.stderr)
            return 0

        if args.command == "import-scanner":
            scanner_data = load_json(args.input)
            payload = import_scanner_results(args.scanner, scanner_data, args.root)
            _write_json(payload, args.output)
            print("Scanner import summary written.", file=sys.stderr)
            return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2
