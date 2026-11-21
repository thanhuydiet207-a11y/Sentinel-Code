"""Orchestrate remediation validation, sandbox, regression, provenance, and policy gates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .patch_risk import review_patch_risk
from .patch_validation import validate_patch_proposal
from .audit_trail import build_audit_trail, verify_audit_trail
from .policy_engine import evaluate_policy
from .provenance import verify_evidence_bundle
from .regression import compare_scan_snapshots
from .remediation_report import build_remediation_report
from .remediation_sandbox import run_remediation_sandbox


def run_remediation_orchestration(
    findings_payload: Any,
    proposal: Any,
    repository_root: str | Path,
    baseline_scan: Any = None,
    candidate_scan: Any = None,
    sandbox_commands: Any = None,
    policy: Any = None,
    scanner_names: Any = None,
    reviewer_names: Any = None,
    sealed_evidence: Any = None,
    timeout_seconds: int = 120,
) -> dict:
    """Run all locally executable remediation gates without modifying repository files.

    Scanner snapshots, reviewer names, and sealed evidence are supplied inputs;
    this function does not launch scanner binaries or AI provider requests.
    """
    root = Path(repository_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository_root must be a directory")
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be an object")
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")

    stages: dict[str, dict] = {}

    try:
        validation = validate_patch_proposal(proposal, findings_payload, root)
        stages["patch_validation"] = {
            "status": "pass", "valid": True, "candidate_sha256": validation["candidate_sha256"],
            "path": validation["path"], "file_modified": False,
        }
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        validation = None
        stages["patch_validation"] = {"status": "fail", "valid": False, "error": str(exc)}

    try:
        risk = review_patch_risk(proposal)
        stages["patch_risk"] = {"status": "complete", "risk_score": risk["risk_score"],
                                "risk_level": risk["risk_level"], "flags": risk["flags"]}
    except (TypeError, ValueError) as exc:
        risk = None
        stages["patch_risk"] = {"status": "not_run", "error": str(exc)}

    if validation is not None and isinstance(sandbox_commands, list) and sandbox_commands:
        try:
            sandbox = run_remediation_sandbox(
                root, validation["path"], validation["candidate_content"],
                sandbox_commands, timeout_seconds=timeout_seconds,
            )
            stages["sandbox"] = {"status": sandbox["status"], "commands": sandbox["commands"],
                                 "original_repository_modified": sandbox["original_repository_modified"],
                                 "os_level_isolation": sandbox["os_level_isolation"]}
        except (OSError, ValueError, RuntimeError) as exc:
            sandbox = {"status": "not_run", "error": str(exc)}
            stages["sandbox"] = {"status": "not_run", "error": str(exc)}
    else:
        reason = "patch_validation_failed" if validation is None else "sandbox_commands_not_supplied"
        sandbox = {"status": "not_run", "error": reason}
        stages["sandbox"] = {"status": "not_run", "error": reason}

    if baseline_scan is not None and candidate_scan is not None:
        try:
            scan = compare_scan_snapshots(baseline_scan, candidate_scan)
            stages["regression_scan"] = {"status": scan["status"], "summary": scan["summary"]}
        except (TypeError, ValueError) as exc:
            scan = {"status": "not_run", "error": str(exc)}
            stages["regression_scan"] = {"status": "not_run", "error": str(exc)}
    else:
        scan = {"status": "not_run", "error": "baseline_or_candidate_scan_missing"}
        stages["regression_scan"] = {"status": "not_run", "error": scan["error"]}

    if sealed_evidence is not None:
        try:
            provenance = verify_evidence_bundle(sealed_evidence, root)
            provenance_status = "verified" if provenance["valid"] else "invalid"
            stages["provenance"] = {"status": provenance_status,
                                    "bundle_hash_valid": provenance["bundle_hash_valid"],
                                    "artifact_checks": provenance["artifact_checks"]}
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            provenance = {"valid": False, "integrity": "invalid", "error": str(exc)}
            provenance_status = "invalid"
            stages["provenance"] = {"status": "invalid", "error": str(exc)}
    else:
        provenance = {"valid": False, "integrity": "not_run"}
        provenance_status = "not_run"
        stages["provenance"] = {"status": "not_run", "error": "sealed_evidence_not_supplied"}

    scanners = scanner_names if isinstance(scanner_names, list) else []
    reviewers = reviewer_names if isinstance(reviewer_names, list) else []
    policy_evidence = {
        "patch_validation": {"valid": validation is not None},
        "patch_risk": risk or {},
        "sandbox": sandbox,
        "scan_comparison": scan,
        "evidence_verification": {"status": provenance_status},
        "evidence_verified": provenance.get("valid") is True,
        "scanners": scanners,
        "reviewers": reviewers,
    }
    policy_result = evaluate_policy(policy, policy_evidence)
    stages["policy"] = {"status": policy_result["decision"].lower(),
                        "blockers": policy_result["blockers"],
                        "missing_evidence": policy_result["missing_evidence"]}

    report_bundle = {
        "patch_validation": {"valid": validation is not None, "issues": [] if validation else [stages["patch_validation"].get("error", "validation_failed")]},
        "patch_risk": risk or {},
        "sandbox": sandbox,
        "scan_comparison": scan,
    }
    remediation_report = build_remediation_report(report_bundle)

    overall = {"PASS": "ready_for_human_approval", "BLOCK": "blocked",
               "REVIEW": "needs_review"}[policy_result["decision"]]
    remediation_report["evidence_gate_decision"] = remediation_report["decision"]
    remediation_report["decision"] = overall
    remediation_report["policy_decision"] = policy_result["decision"]

    event_types = [
        ("created", {"workflow": "sentinel-remediation-orchestrator-v1"}),
        ("finding_selected", {"finding_id": proposal.get("finding_id")}),
        ("patch_proposed", {"path": proposal.get("path")}),
        ("patch_validated", {"valid": validation is not None}),
        ("risk_assessed", {"risk_score": risk.get("risk_score") if risk else None}),
        ("sandbox_completed", {"status": sandbox.get("status")}),
        ("scan_completed", {"status": scan.get("status")}),
        ("evidence_verified", {"status": provenance_status}),
        ("report_generated", {"policy_decision": policy_result["decision"], "status": overall}),
    ]
    audit_start = datetime.now(timezone.utc)
    audit_events = [
        {"type": event_type,
         "timestamp": (audit_start + timedelta(microseconds=index)).isoformat().replace("+00:00", "Z"),
         "payload": payload}
        for index, (event_type, payload) in enumerate(event_types)
    ]
    audit_trail = build_audit_trail("remediation-" + uuid4().hex, audit_events)
    audit_verification = verify_audit_trail(audit_trail)
    stages["audit_trail"] = {
        "status": "verified" if audit_verification["valid"] else "invalid",
        "event_count": audit_verification["event_count"],
    }
    return {
        "schema_version": "1.0", "workflow": "sentinel-remediation-orchestrator-v1",
        "status": overall, "stages": stages, "policy": policy_result,
        "remediation_report": remediation_report,
        "audit_trail": audit_trail, "audit_verification": audit_verification,
        "summary": {
            "completed_stages": sum(1 for item in stages.values() if item["status"] in ("pass", "complete", "clean", "verified")),
            "stage_count": len(stages), "patch_candidate_created": validation is not None,
            "repository_modified": False, "automatic_apply_allowed": False,
            "automatic_merge_allowed": False, "human_approval_required": True,
        },
        "limitations": [
            "Scanner snapshots and reviewer identities are supplied by the caller; no scanner executable or AI provider is launched.",
            "The sandbox uses a temporary workspace and is not OS-level isolation.",
            "Provenance verifies supplied hashes but does not establish artifact authenticity or trusted timestamps.",
            "A passing policy is not authorization to apply or merge a patch.",
        ],
    }
