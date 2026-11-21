"""Declarative remediation policy evaluation; advisory gate, never authorizes execution."""
from __future__ import annotations
from typing import Any

_ALLOWED = {"policy_id", "version", "max_risk_score", "required_scanners",
            "required_reviewers", "min_reviewers", "require_evidence_verified",
            "require_sandbox_pass", "require_regression_clean", "require_manual_approval"}

def evaluate_policy(policy: Any, evidence: Any) -> dict:
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object")
    unknown = sorted(set(policy) - _ALLOWED)
    if unknown:
        raise ValueError("unsupported policy fields: " + ", ".join(unknown))
    policy_id = policy.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id.strip():
        raise ValueError("policy_id is required")
    version = policy.get("version", "1")
    if not isinstance(version, (str, int)) or isinstance(version, bool):
        raise ValueError("policy version must be string or integer")
    max_risk = policy.get("max_risk_score", 30)
    if not isinstance(max_risk, int) or isinstance(max_risk, bool) or not 0 <= max_risk <= 100:
        raise ValueError("max_risk_score must be integer 0..100")
    scanners = policy.get("required_scanners", [])
    reviewers = policy.get("required_reviewers", [])
    if not isinstance(scanners, list) or any(not isinstance(x, str) or not x for x in scanners):
        raise ValueError("required_scanners must be a list of names")
    if not isinstance(reviewers, list) or any(not isinstance(x, str) or not x for x in reviewers):
        raise ValueError("required_reviewers must be a list of provider names")
    min_reviewers = policy.get("min_reviewers", 0)
    if not isinstance(min_reviewers, int) or isinstance(min_reviewers, bool) or min_reviewers < 0:
        raise ValueError("min_reviewers must be a non-negative integer")
    gates, blockers, missing = {}, [], []
    validation = evidence.get("patch_validation")
    gates["patch_validation"] = isinstance(validation, dict) and validation.get("valid") is True
    if not gates["patch_validation"]:
        blockers.append("patch_validation_failed")
    sandbox = evidence.get("sandbox")
    gates["sandbox"] = isinstance(sandbox, dict) and sandbox.get("status") == "pass"
    if policy.get("require_sandbox_pass", True) and not gates["sandbox"]:
        blockers.append("sandbox_not_passed")
    scan = evidence.get("scan_comparison")
    gates["regression_scan"] = isinstance(scan, dict) and scan.get("status") == "clean"
    if policy.get("require_regression_clean", True) and not gates["regression_scan"]:
        blockers.append("regression_scan_not_clean")
    risk = evidence.get("patch_risk")
    score = risk.get("risk_score") if isinstance(risk, dict) else None
    gates["risk_score"] = isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= max_risk
    if score is None:
        missing.append("patch_risk_score_missing")
    elif not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 100:
        blockers.append("patch_risk_score_invalid")
    elif score > max_risk:
        blockers.append("patch_risk_exceeds_policy")
    scanner_names = evidence.get("scanners")
    if not isinstance(scanner_names, list):
        scanner_names = []
    missing_scanners = sorted(set(scanners) - set(scanner_names))
    gates["required_scanners"] = not missing_scanners
    if missing_scanners:
        missing.append("required_scanners_missing:" + ",".join(missing_scanners))
    verified = evidence.get("evidence_verified") is True
    gates["evidence_verified"] = verified
    if policy.get("require_evidence_verified", True) and not verified:
        missing.append("evidence_not_verified")
    reviewer_names = evidence.get("reviewers")
    if not isinstance(reviewer_names, list):
        reviewer_names = []
    missing_reviewers = sorted(set(reviewers) - set(reviewer_names))
    gates["required_reviewers"] = not missing_reviewers
    if missing_reviewers:
        missing.append("required_reviewers_missing:" + ",".join(missing_reviewers))
    if len(set(reviewer_names)) < min_reviewers:
        missing.append("minimum_reviewer_count_not_met")
    decision = "BLOCK" if blockers else "REVIEW" if missing else "PASS"
    return {
        "policy_id": policy_id, "policy_version": str(version), "decision": decision,
        "gates": gates, "blockers": sorted(set(blockers)), "missing_evidence": sorted(set(missing)),
        "review_required": True, "human_approval_required": policy.get("require_manual_approval", True) is not False,
        "automatic_apply_allowed": False, "automatic_merge_allowed": False,
        "limitations": ["Evaluation uses caller-supplied evidence and does not independently execute tools.",
                        "PASS indicates configured evidence gates passed; it is not authorization to apply or merge."],
    }
