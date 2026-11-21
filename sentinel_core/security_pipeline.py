"""End-to-end deterministic and AI-assisted security review orchestration."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .adversarial_review import run_adversarial_reviews
from .core import deduplicate_findings, render_markdown_report, validate_payload
from .correlation import correlate_findings
from .evidence_verification import verify_ai_evidence
from .false_positive import analyze_findings
from .scanner_adapters import SUPPORTED, import_scanner_results
from .provider_adapters import Transport


def run_security_pipeline(
    findings_payload: dict[str, Any],
    repository_root: Path | str,
    providers: list[str],
    scanner_inputs: list[dict[str, Any]] | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Validate, import, deduplicate, correlate, triage, and adversarially review.

    Scanner input entries have the shape {"scanner": "semgrep", "data": parsed_json}.
    No scanner executable is launched here; raw scanner JSON must already exist.
    """
    root = Path(repository_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository_root must be a directory")
    if not isinstance(findings_payload, dict):
        raise ValueError("findings payload must be an object")
    base_errors = validate_payload(findings_payload, root)
    if base_errors:
        raise ValueError("input findings failed validation: " + "; ".join(base_errors))

    imported_packages = []
    scanner_summaries = []
    for entry in scanner_inputs or []:
        if not isinstance(entry, dict):
            raise ValueError("scanner input entry must be an object")
        scanner = entry.get("scanner")
        if not isinstance(scanner, str) or scanner not in SUPPORTED:
            raise ValueError("scanner must be one of: " + ", ".join(SUPPORTED))
        if "data" not in entry:
            raise ValueError(f"scanner input {scanner} is missing parsed JSON data")
        imported = import_scanner_results(scanner, entry["data"], root)
        errors = validate_payload(imported, root)
        if errors:
            raise ValueError(f"imported {scanner} findings failed validation: " + "; ".join(errors))
        imported_packages.append(imported)
        metadata = imported.get("metadata", {})
        scanner_summaries.append({
            "scanner": scanner,
            "imported": metadata.get("imported", len(imported.get("findings", []))),
            "skipped": metadata.get("skipped", []),
        })

    all_findings = list(findings_payload["findings"])
    for package in imported_packages:
        all_findings.extend(package["findings"])
    deduplicated = deduplicate_findings(all_findings)
    normalized = {
        "schema_version": findings_payload.get("schema_version", "1.0"),
        "metadata": {
            **(findings_payload.get("metadata") if isinstance(findings_payload.get("metadata"), dict) else {}),
            "orchestration": "sentinel-security-pipeline-v1",
            "source_packages": 1 + len(imported_packages),
        },
        "findings": deduplicated,
    }
    final_errors = validate_payload(normalized, root)
    if final_errors:
        raise ValueError("combined findings failed validation: " + "; ".join(final_errors))

    correlations = correlate_findings([normalized])
    triage = analyze_findings(normalized)
    if transport is None:
        adversarial = run_adversarial_reviews(normalized, providers)
    else:
        adversarial = run_adversarial_reviews(normalized, providers, transport=transport)

    evidence_verification = {
        stage: verify_ai_evidence(normalized, package, root)
        for stage, package in adversarial["stages"].items()
    }
    markdown_report = render_markdown_report(normalized["findings"], scope="orchestrated security review")

    cross_stage = adversarial["cross_stage_analysis"]
    summary = {
        "input_findings": len(findings_payload["findings"]),
        "scanner_packages": len(imported_packages),
        "scanner_findings_imported": sum(item["imported"] for item in scanner_summaries),
        "unique_findings": len(normalized["findings"]),
        "duplicate_findings_removed": len(all_findings) - len(deduplicated),
        "correlation_groups": correlations["metadata"]["correlation_groups"],
        "corroborated_groups": correlations["metadata"]["corroborated_groups"],
        "triage_needs_review": triage["metadata"]["needs_review"],
        "adversarial_provider_requests": adversarial["metadata"]["total_provider_requests"],
        "cross_stage_disagreements": sum(1 for item in cross_stage if item["cross_stage_disagreement"]),
        "verified_source_hash_references": sum(
            result["metadata"]["verified_hash_references"]
            for result in evidence_verification.values()
        ),
        "automatic_suppression": False,
    }
    return {
        "schema_version": "1.0",
        "summary": summary,
        "scanner_imports": scanner_summaries,
        "findings": normalized,
        "correlation": correlations,
        "triage": triage,
        "adversarial_review": adversarial,
        "evidence_verification": evidence_verification,
        "markdown_report": markdown_report,
        "safety_note": (
            "This pipeline validates supplied source evidence and scanner imports, then performs advisory AI review. "
            "It does not execute scanners, prove exploitability, or automatically suppress findings. Human review remains required."
        ),
    }
