"""Declarative remediation policy evaluation; advisory gate, never authorizes execution."""
from __future__ import annotations

import math
from typing import Any

_ALLOWED = {"policy_id", "version", "max_risk_score", "required_scanners",
            "required_reviewers", "min_reviewers", "require_evidence_verified",
            "require_sandbox_pass", "require_regression_clean", "require_manual_approval",
            "require_ai_adjudication", "min_adjudicator_reviewers",
            "max_cross_stage_disagreements", "min_adjudicator_confidence"}
_BOOL_FIELDS = {"require_evidence_verified", "require_sandbox_pass",
                "require_regression_clean", "require_manual_approval",
                "require_ai_adjudication"}


def _names(value: Any) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        return []
    return list(dict.fromkeys(value))


def evaluate_policy(policy: Any, evidence: Any) -> dict:
    """Return PASS/BLOCK/REVIEW from supplied evidence; never authorizes applying or merging."""
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object")
    unknown = sorted(set(policy) - _ALLOWED)
    if unknown:
        raise ValueError("unsupported policy fields: " + ", ".join(unknown))
    for field in _BOOL_FIELDS:
        if field in policy and not isinstance(policy[field], bool):
            raise ValueError(field + " must be a boolean")
    if policy.get("require_manual_approval", True) is not True:
        raise ValueError("require_manual_approval cannot be disabled")
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
    if not isinstance(scanners, list) or any(not isinstance(x, str) or not x.strip() for x in scanners):
        raise ValueError("required_scanners must be a list of non-empty names")
    if not isinstance(reviewers, list) or any(not isinstance(x, str) or not x.strip() for x in reviewers):
        raise ValueError("required_reviewers must be a list of non-empty names")
    min_reviewers = policy.get("min_reviewers", 0)
    if not isinstance(min_reviewers, int) or isinstance(min_reviewers, bool) or min_reviewers < 0:
        raise ValueError("min_reviewers must be a non-negative integer")

    min_adjudicators = policy.get("min_adjudicator_reviewers", 1)
    if not isinstance(min_adjudicators, int) or isinstance(min_adjudicators, bool) or min_adjudicators < 1:
        raise ValueError("min_adjudicator_reviewers must be a positive integer")
    max_disagreements = policy.get("max_cross_stage_disagreements", 0)
    if not isinstance(max_disagreements, int) or isinstance(max_disagreements, bool) or max_disagreements < 0:
        raise ValueError("max_cross_stage_disagreements must be a non-negative integer")
    min_confidence = policy.get("min_adjudicator_confidence", 0.0)
    if (isinstance(min_confidence, bool) or not isinstance(min_confidence, (int, float))
            or not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1):
        raise ValueError("min_adjudicator_confidence must be a finite number between 0 and 1")

    gates: dict[str, bool | None] = {}
    blockers: list[str] = []
    missing: list[str] = []
    review_reasons: list[str] = []

    validation = evidence.get("patch_validation")
    if not isinstance(validation, dict) or "valid" not in validation:
        gates["patch_validation"] = None
        missing.append("patch_validation_missing")
    else:
        gates["patch_validation"] = validation.get("valid") is True
        if validation.get("valid") is not True:
            blockers.append("patch_validation_failed")

    sandbox = evidence.get("sandbox")
    sandbox_status = sandbox.get("status") if isinstance(sandbox, dict) else None
    gates["sandbox"] = True if sandbox_status == "pass" else False if sandbox_status == "fail" else None
    if policy.get("require_sandbox_pass", True):
        if sandbox_status == "fail":
            blockers.append("sandbox_failed")
        elif sandbox_status != "pass":
            missing.append("sandbox_not_run")

    scan = evidence.get("scan_comparison")
    scan_status = scan.get("status") if isinstance(scan, dict) else None
    gates["regression_scan"] = True if scan_status == "clean" else False if scan_status == "regression" else None
    if policy.get("require_regression_clean", True):
        if scan_status == "regression":
            blockers.append("regression_scan_failed")
        elif scan_status != "clean":
            missing.append("regression_scan_not_run")

    risk = evidence.get("patch_risk")
    score = risk.get("risk_score") if isinstance(risk, dict) else None
    if score is None:
        gates["risk_score"] = None
        missing.append("patch_risk_score_missing")
    elif not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 100:
        gates["risk_score"] = False
        blockers.append("patch_risk_score_invalid")
    else:
        gates["risk_score"] = score <= max_risk
        if score > max_risk:
            blockers.append("patch_risk_exceeds_policy")

    scanner_names = _names(evidence.get("scanners"))
    missing_scanners = sorted(set(scanners) - set(scanner_names))
    gates["required_scanners"] = not missing_scanners
    if missing_scanners:
        missing.append("required_scanners_missing:" + ",".join(missing_scanners))

    provenance = evidence.get("evidence_verification")
    provenance_status = provenance.get("status") if isinstance(provenance, dict) else None
    verified = evidence.get("evidence_verified") is True or provenance_status == "verified"
    if provenance_status == "invalid":
        gates["evidence_verified"] = False
        blockers.append("evidence_integrity_failed")
    else:
        gates["evidence_verified"] = verified if verified else None
        if policy.get("require_evidence_verified", True) and not verified:
            missing.append("evidence_not_verified")

    reviewer_names = _names(evidence.get("reviewers"))
    missing_reviewers = sorted(set(reviewers) - set(reviewer_names))
    gates["required_reviewers"] = not missing_reviewers
    if missing_reviewers:
        missing.append("required_reviewers_missing:" + ",".join(missing_reviewers))
    if len(reviewer_names) < min_reviewers:
        missing.append("minimum_reviewer_count_not_met")

    if policy.get("require_ai_adjudication", False):
        ai_review = evidence.get("ai_adjudication")
        if not isinstance(ai_review, dict) or ai_review.get("status") != "complete":
            gates["ai_adjudication"] = None
            missing.append("ai_adjudication_not_completed")
        else:
            ai_gate_pass = True
            reviewer_count = ai_review.get("reviewer_count")
            finding_count = ai_review.get("finding_count")
            adjudicated_count = ai_review.get("adjudicated_finding_count")
            cross_stage_count = ai_review.get("cross_stage_finding_count")
            disagreements = ai_review.get("cross_stage_disagreements")
            confidence = ai_review.get("minimum_confidence")
            if not isinstance(reviewer_count, int) or isinstance(reviewer_count, bool) or reviewer_count < min_adjudicators:
                missing.append("minimum_adjudicator_reviewers_not_met")
                ai_gate_pass = False
            if (not isinstance(finding_count, int) or isinstance(finding_count, bool) or finding_count < 0
                    or not isinstance(adjudicated_count, int) or isinstance(adjudicated_count, bool)
                    or adjudicated_count != finding_count):
                missing.append("adjudicator_finding_coverage_incomplete")
                ai_gate_pass = False
            if (not isinstance(finding_count, int) or isinstance(finding_count, bool)
                    or not isinstance(cross_stage_count, int) or isinstance(cross_stage_count, bool)
                    or cross_stage_count != finding_count):
                missing.append("cross_stage_finding_coverage_incomplete")
                ai_gate_pass = False
            if not isinstance(disagreements, int) or isinstance(disagreements, bool) or disagreements < 0:
                missing.append("cross_stage_disagreement_count_missing")
                ai_gate_pass = False
            elif disagreements > max_disagreements:
                review_reasons.append("cross_stage_disagreement_limit_exceeded")
                ai_gate_pass = False
            if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                    or not math.isfinite(confidence) or not 0 <= confidence <= 1):
                missing.append("adjudicator_confidence_missing")
                ai_gate_pass = False
            elif confidence < min_confidence:
                review_reasons.append("adjudicator_confidence_below_policy")
                ai_gate_pass = False
            gates["ai_adjudication"] = ai_gate_pass

    decision = "BLOCK" if blockers else "REVIEW" if missing or review_reasons else "PASS"
    return {
        "policy_id": policy_id, "policy_version": str(version), "decision": decision,
        "gates": gates, "blockers": sorted(set(blockers)),
        "missing_evidence": sorted(set(missing)), "review_reasons": sorted(set(review_reasons)),
        "review_required": True, "human_approval_required": True,
        "automatic_apply_allowed": False, "automatic_merge_allowed": False,
        "limitations": ["Evaluation uses caller-supplied evidence and does not independently execute scanners or reviewers.",
                        "PASS indicates configured evidence gates passed; it is not authorization to apply or merge."],
    }
