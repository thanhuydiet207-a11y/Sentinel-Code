"""Orchestrate remediation validation, sandbox, regression, provenance, and policy gates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import hashlib
import json
import os
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
from .security_pipeline import run_security_pipeline
from .workflow_state import create_workflow, checkpoint_stage, checkpoint_outputs, load_workflow


def _repository_digest(root: Path, excluded: Path | None = None) -> str:
    digest = hashlib.sha256()
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "__pycache__", ".pytest_cache", ".sentinel-workflows"})
        for name in sorted(files):
            path = Path(current) / name
            if excluded is not None and path.resolve().is_relative_to(excluded):
                continue
            relative = path.relative_to(root).as_posix()
            digest.update(relative.encode("utf-8"))
            try:
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError as exc:
                raise ValueError(f"repository snapshot failed for {relative}") from exc
    return digest.hexdigest()


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
    scanner_inputs: Any = None,
    ai_providers: Any = None,
    timeout_seconds: int = 120,
    checkpoint_store: str | Path | None = None,
    workflow_id: str | None = None,
) -> dict:
    """Run all locally executable remediation gates without modifying repository files.

    Scanner JSON and baseline/candidate snapshots are supplied inputs; scanner
    executables are never launched. AI provider requests run only when
    ai_providers is explicitly supplied.
    """
    root = Path(repository_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository_root must be a directory")
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be an object")
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")

    checkpoint_digest = None
    restored: dict[str, Any] = {}
    if checkpoint_store is not None:
        if not isinstance(workflow_id, str) or not workflow_id:
            raise ValueError("workflow_id is required when checkpoint_store is supplied")
        repository_digest = _repository_digest(root, Path(checkpoint_store).resolve())
        checkpoint_inputs = {
            "repository_digest": repository_digest,
            "findings_payload": findings_payload, "proposal": proposal,
            "baseline_scan": baseline_scan, "candidate_scan": candidate_scan,
            "sandbox_commands": sandbox_commands, "policy": policy, "scanner_names": scanner_names,
            "reviewer_names": reviewer_names, "sealed_evidence": sealed_evidence,
            "scanner_inputs": scanner_inputs, "ai_providers": ai_providers,
            "timeout_seconds": timeout_seconds,
        }
        try:
            canonical = json.dumps(checkpoint_inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("checkpointed orchestration inputs must be JSON-serializable") from exc
        checkpoint_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        try:
            existing = load_workflow(checkpoint_store, workflow_id)
        except FileNotFoundError:
            create_workflow(checkpoint_store, workflow_id,
                           ["security_review", "patch_validation", "patch_risk", "sandbox", "regression_scan", "provenance", "orchestration"], checkpoint_digest,
                           metadata={"workflow": "sentinel-remediation-orchestrator-v1", "repository_digest": repository_digest})
        else:
            if existing.get("input_digest") != checkpoint_digest:
                raise ValueError("checkpoint input digest mismatch; use a new workflow_id")
            restored = checkpoint_outputs(checkpoint_store, workflow_id, checkpoint_digest)
            if "orchestration" in restored:
                return restored["orchestration"]
            if existing.get("stages") != ["security_review", "patch_validation", "patch_risk", "sandbox", "regression_scan", "provenance", "orchestration"]:
                raise ValueError("checkpoint workflow stage plan is incompatible; use a new workflow_id")
            if existing.get("status") != "running":
                raise ValueError("checkpoint workflow is not resumable")

    stages: dict[str, dict] = {}
    security_review = None
    validation_findings = findings_payload
    resolved_scanners = scanner_names if isinstance(scanner_names, list) else []
    resolved_reviewers = reviewer_names if isinstance(reviewer_names, list) else []
    ai_adjudication_evidence: dict[str, Any] = {"status": "not_run"}

    if checkpoint_store is not None and "security_review" in restored:
        cached_review = restored["security_review"]
        security_review = cached_review["security_review"]
        validation_findings = cached_review["validation_findings"]
        resolved_scanners = cached_review["resolved_scanners"]
        resolved_reviewers = cached_review["resolved_reviewers"]
        ai_adjudication_evidence = cached_review["ai_adjudication_evidence"]
        stages.update(cached_review["stages"])
    elif scanner_inputs is not None and ai_providers is None:
        raise ValueError("scanner_inputs require ai_providers so the security pipeline can process them")
    elif ai_providers is not None:
        if not isinstance(ai_providers, list) or not ai_providers:
            raise ValueError("ai_providers must be a non-empty list when supplied")
        try:
            security_review = run_security_pipeline(
                findings_payload, root, ai_providers, scanner_inputs=scanner_inputs or []
            )
            validation_findings = security_review["findings"]
            resolved_scanners = [
                item["scanner"] for item in security_review.get("scanner_imports", [])
                if isinstance(item, dict) and isinstance(item.get("scanner"), str)
            ]
            adversarial = security_review.get("adversarial_review", {})
            stages_data = adversarial.get("stages", {}) if isinstance(adversarial, dict) else {}
            adjudicator = stages_data.get("adjudicator", {}) if isinstance(stages_data, dict) else {}
            adjudicator_reviewers = adjudicator.get("reviewers", []) if isinstance(adjudicator, dict) else []
            resolved_reviewers = list(dict.fromkeys(
                item["provider"] for item in adjudicator_reviewers
                if isinstance(item, dict) and isinstance(item.get("provider"), str)
            ))
            stage_consensus = adversarial.get("stage_consensus", {}) if isinstance(adversarial, dict) else {}
            adjudicator_consensus = stage_consensus.get("adjudicator", {}) if isinstance(stage_consensus, dict) else {}
            consensus_items = adjudicator_consensus.get("consensus", []) if isinstance(adjudicator_consensus, dict) else []
            cross_stage = adversarial.get("cross_stage_analysis", []) if isinstance(adversarial, dict) else []
            confidence_values = [
                vote.get("confidence")
                for reviewer in adjudicator_reviewers if isinstance(reviewer, dict)
                for vote in reviewer.get("reviews", []) if isinstance(reviewer.get("reviews"), list)
                if isinstance(vote, dict)
                and isinstance(vote.get("confidence"), (int, float))
                and not isinstance(vote.get("confidence"), bool)
                and math.isfinite(vote.get("confidence"))
                and 0 <= vote.get("confidence") <= 1
            ]
            finding_count = len(security_review.get("findings", {}).get("findings", [])) if isinstance(security_review.get("findings"), dict) else 0
            disagreement_count = sum(
                1 for item in cross_stage
                if isinstance(item, dict) and item.get("cross_stage_disagreement") is True
            ) if isinstance(cross_stage, list) else 0
            ai_adjudication_evidence = {
                "status": "complete",
                "reviewer_count": len(adjudicator_reviewers),
                "finding_count": finding_count,
                "adjudicated_finding_count": len(consensus_items) if isinstance(consensus_items, list) else 0,
                "cross_stage_finding_count": len(cross_stage) if isinstance(cross_stage, list) else 0,
                "cross_stage_disagreements": disagreement_count,
                "minimum_confidence": min(confidence_values) if confidence_values else None,
            }
            stages["ai_adjudication"] = {
                "status": "complete" if ai_adjudication_evidence["adjudicated_finding_count"] == finding_count else "incomplete",
                "reviewer_count": ai_adjudication_evidence["reviewer_count"],
                "adjudicated_finding_count": ai_adjudication_evidence["adjudicated_finding_count"],
                "finding_count": finding_count,
                "cross_stage_disagreements": disagreement_count,
                "minimum_confidence": ai_adjudication_evidence["minimum_confidence"],
            }
            evidence_stages = security_review.get("evidence_verification", {})
            verified_refs = sum(
                result.get("metadata", {}).get("verified_hash_references", 0)
                for result in evidence_stages.values() if isinstance(result, dict)
            ) if isinstance(evidence_stages, dict) else 0
            stages["ai_evidence_verification"] = {
                "status": "complete", "verified_hash_references": verified_refs,
            }
            stages["security_review"] = {
                "status": "complete",
                "provider_requests": security_review.get("summary", {}).get("adversarial_provider_requests"),
                "scanner_packages": len(resolved_scanners),
                "reviewers": resolved_reviewers,
            }
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            stages["security_review"] = {"status": "failed", "error": str(exc)}
            stages["ai_adjudication"] = {"status": "not_run", "error": "security_review_failed"}
            ai_adjudication_evidence = {"status": "failed"}
            resolved_scanners = []
            resolved_reviewers = []
    elif checkpoint_store is None or "security_review" not in restored:
        stages["security_review"] = {"status": "not_run", "error": "ai_providers_not_supplied"}
        stages["ai_adjudication"] = {"status": "not_run", "error": "ai_providers_not_supplied"}

    if checkpoint_store is not None and "security_review" not in restored:
        checkpoint_stage(checkpoint_store, workflow_id, "security_review", "completed", {
            "security_review": security_review,
            "validation_findings": validation_findings,
            "resolved_scanners": resolved_scanners,
            "resolved_reviewers": resolved_reviewers,
            "ai_adjudication_evidence": ai_adjudication_evidence,
            "stages": {key: stages[key] for key in ("security_review", "ai_adjudication", "ai_evidence_verification") if key in stages},
        })

    try:
        if checkpoint_store is not None and "patch_validation" in restored:
            cached = restored["patch_validation"]
            validation, validation_stage = cached["validation"], cached["stage"]
        else:
            validation = validate_patch_proposal(proposal, validation_findings, root)
            validation_stage = {
                "status": "pass", "valid": True, "candidate_sha256": validation["candidate_sha256"],
                "path": validation["path"], "file_modified": False,
            }
            if checkpoint_store is not None:
                checkpoint_stage(checkpoint_store, workflow_id, "patch_validation", "completed",
                                 {"validation": validation, "stage": validation_stage})
        stages["patch_validation"] = validation_stage
    except (OSError, UnicodeError, ValueError, RuntimeError, TypeError, KeyError) as exc:
        validation = None
        validation_stage = {"status": "fail", "valid": False, "error": str(exc)}
        stages["patch_validation"] = validation_stage
        if checkpoint_store is not None and "patch_validation" not in restored:
            checkpoint_stage(checkpoint_store, workflow_id, "patch_validation", "completed",
                             {"validation": None, "stage": validation_stage})

    try:
        if checkpoint_store is not None and "patch_risk" in restored:
            cached = restored["patch_risk"]
            risk, risk_stage = cached["risk"], cached["stage"]
        else:
            risk = review_patch_risk(proposal)
            risk_stage = {"status": "complete", "risk_score": risk["risk_score"],
                          "risk_level": risk["risk_level"], "flags": risk["flags"]}
            if checkpoint_store is not None:
                checkpoint_stage(checkpoint_store, workflow_id, "patch_risk", "completed",
                                 {"risk": risk, "stage": risk_stage})
        stages["patch_risk"] = risk_stage
    except (TypeError, ValueError, KeyError) as exc:
        risk = None
        stages["patch_risk"] = {"status": "not_run", "error": str(exc)}

    if checkpoint_store is not None and "sandbox" in restored:
        sandbox = restored["sandbox"]["sandbox"]
        sandbox_stage = restored["sandbox"]["stage"]
        stages["sandbox"] = sandbox_stage
    elif validation is not None and isinstance(sandbox_commands, list) and sandbox_commands:
        try:
            sandbox = run_remediation_sandbox(
                root, validation["path"], validation["candidate_content"],
                sandbox_commands, timeout_seconds=timeout_seconds,
            )
            sandbox_stage = {"status": sandbox["status"], "commands": sandbox["commands"],
                            "original_repository_modified": sandbox["original_repository_modified"],
                            "os_level_isolation": sandbox["os_level_isolation"]}
            stages["sandbox"] = sandbox_stage
        except (OSError, ValueError, RuntimeError) as exc:
            sandbox = {"status": "not_run", "error": str(exc)}
            sandbox_stage = {"status": "not_run", "error": str(exc)}
            stages["sandbox"] = sandbox_stage
        if checkpoint_store is not None:
            checkpoint_stage(checkpoint_store, workflow_id, "sandbox", "completed",
                             {"sandbox": sandbox, "stage": sandbox_stage})
    else:
        reason = "patch_validation_failed" if validation is None else "sandbox_commands_not_supplied"
        sandbox = {"status": "not_run", "error": reason}
        sandbox_stage = {"status": "not_run", "error": reason}
        stages["sandbox"] = sandbox_stage
        if checkpoint_store is not None:
            checkpoint_stage(checkpoint_store, workflow_id, "sandbox", "completed",
                             {"sandbox": sandbox, "stage": sandbox_stage})

    if baseline_scan is not None and candidate_scan is not None:
        try:
            if checkpoint_store is not None and "regression_scan" in restored:
                cached = restored["regression_scan"]
                scan, scan_stage = cached["scan"], cached["stage"]
            else:
                scan = compare_scan_snapshots(baseline_scan, candidate_scan)
                scan_stage = {"status": scan["status"], "summary": scan["summary"]}
                if checkpoint_store is not None:
                    checkpoint_stage(checkpoint_store, workflow_id, "regression_scan", "completed",
                                    {"scan": scan, "stage": scan_stage})
            stages["regression_scan"] = scan_stage
        except (TypeError, ValueError, KeyError) as exc:
            scan = {"status": "not_run", "error": str(exc)}
            stages["regression_scan"] = {"status": "not_run", "error": str(exc)}
    else:
        scan = {"status": "not_run", "error": "baseline_or_candidate_scan_missing"}
        scan_stage = {"status": "not_run", "error": scan["error"]}
        stages["regression_scan"] = scan_stage
        if checkpoint_store is not None:
            checkpoint_stage(checkpoint_store, workflow_id, "regression_scan", "completed",
                             {"scan": scan, "stage": scan_stage})

    if checkpoint_store is not None and "provenance" in restored:
        provenance = restored["provenance"]["provenance"]
        provenance_status = restored["provenance"]["status"]
        stages["provenance"] = restored["provenance"]["stage"]
    elif sealed_evidence is not None:
        try:
            provenance = verify_evidence_bundle(sealed_evidence, root)
            provenance_status = "verified" if provenance["valid"] else "invalid"
            provenance_stage = {"status": provenance_status,
                               "bundle_hash_valid": provenance["bundle_hash_valid"],
                               "artifact_checks": provenance["artifact_checks"]}
            stages["provenance"] = provenance_stage
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            provenance = {"valid": False, "integrity": "invalid", "error": str(exc)}
            provenance_status = "invalid"
            provenance_stage = {"status": "invalid", "error": str(exc)}
            stages["provenance"] = provenance_stage
        if checkpoint_store is not None:
            checkpoint_stage(checkpoint_store, workflow_id, "provenance", "completed",
                             {"provenance": provenance, "status": provenance_status, "stage": stages["provenance"]})
    else:
        provenance = {"valid": False, "integrity": "not_run"}
        provenance_status = "not_run"
        provenance_stage = {"status": "not_run", "error": "sealed_evidence_not_supplied"}
        stages["provenance"] = provenance_stage
        if checkpoint_store is not None:
            checkpoint_stage(checkpoint_store, workflow_id, "provenance", "completed",
                             {"provenance": provenance, "status": provenance_status, "stage": provenance_stage})

    scanners = resolved_scanners
    reviewers = resolved_reviewers
    policy_evidence = {
        "patch_validation": {"valid": validation is not None},
        "patch_risk": risk or {},
        "sandbox": sandbox,
        "scan_comparison": scan,
        "evidence_verification": {"status": provenance_status},
        "evidence_verified": provenance.get("valid") is True,
        "scanners": scanners,
        "reviewers": reviewers,
        "ai_adjudication": ai_adjudication_evidence,
    }
    policy_result = evaluate_policy(policy, policy_evidence)
    stages["policy"] = {"status": policy_result["decision"].lower(),
                        "blockers": policy_result["blockers"],
                        "missing_evidence": policy_result["missing_evidence"],
                        "review_reasons": policy_result["review_reasons"]}

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
    result = {
        "schema_version": "1.0", "workflow": "sentinel-remediation-orchestrator-v1",
        "status": overall, "stages": stages, "policy": policy_result,
        "security_review": security_review,
        "remediation_report": remediation_report,
        "audit_trail": audit_trail, "audit_verification": audit_verification,
        "summary": {
            "completed_stages": sum(1 for item in stages.values() if item["status"] in ("pass", "complete", "clean", "verified")),
            "stage_count": len(stages), "patch_candidate_created": validation is not None,
            "repository_modified": False, "automatic_apply_allowed": False,
            "automatic_merge_allowed": False, "human_approval_required": True,
        },
        "limitations": [
            "Scanner JSON packages are supplied by the caller; scanner executables are not launched. AI provider calls occur only when ai_providers is explicitly supplied.",
            "The sandbox uses a temporary workspace and is not OS-level isolation.",
            "AI reviewer evidence references are location/hash checks and do not prove reviewer conclusions.",
            "Audit-trail timestamps are local-process timestamps, not trusted timestamps.",
            "Provenance verifies supplied hashes but does not establish artifact authenticity or trusted timestamps.",
            "A passing policy is not authorization to apply or merge a patch.",
        ],
    }
    if checkpoint_store is not None:
        checkpoint_stage(checkpoint_store, workflow_id, "orchestration", "completed", result)
    return result
