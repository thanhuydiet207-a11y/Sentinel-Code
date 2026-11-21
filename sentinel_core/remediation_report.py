"""Decision report builder for remediation workflow evidence; no automatic approval."""
from __future__ import annotations
from typing import Any

def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value

def build_remediation_report(bundle: Any) -> dict:
    bundle = _object(bundle, "bundle")
    validation = _object(bundle.get("patch_validation", {}), "patch_validation")
    risk = _object(bundle.get("patch_risk", {}), "patch_risk")
    tests = _object(bundle.get("sandbox", {}), "sandbox")
    scan = _object(bundle.get("scan_comparison", {}), "scan_comparison")
    issues = validation.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("patch_validation.issues must be a list")
    gates = {
        "patch_validation": validation.get("valid") is True,
        "sandbox": tests.get("status") == "pass",
        "regression_scan": scan.get("status") == "clean",
    }
    blockers = []
    if not gates["patch_validation"]:
        blockers.append("patch_validation_failed")
    if tests.get("status") != "pass":
        blockers.append("sandbox_not_passed")
    if scan.get("status") != "clean":
        blockers.append("security_regression_or_unverified_scan")
    risk_level = str(risk.get("risk_level", "unknown")).lower()
    risk_score = risk.get("risk_score")
    if risk_level not in ("low", "medium", "high"):
        blockers.append("patch_risk_unclassified")
    elif risk_level == "high":
        blockers.append("high_patch_risk_requires_manual_review")
    if not isinstance(risk_score, (int, float)) or isinstance(risk_score, bool) or not 0 <= risk_score <= 100:
        blockers.append("patch_risk_score_invalid")
    if blockers:
        decision = "blocked_or_manual_review"
    else:
        decision = "ready_for_manual_approval"
    return {
        "decision": decision,
        "gates": gates,
        "blockers": sorted(set(blockers)),
        "evidence_summary": {
            "validation_issue_count": len(issues),
            "sandbox_command_count": len(tests.get("commands", [])) if isinstance(tests.get("commands", []), list) else None,
            "scan_fixed_count": scan.get("summary", {}).get("fixed_count"),
            "scan_new_count": scan.get("summary", {}).get("new_count"),
            "scan_persisting_count": scan.get("summary", {}).get("persisting_count"),
            "patch_risk_level": risk_level,
            "patch_risk_score": risk_score,
        },
        "review_required": True,
        "human_approval_required": True,
        "automatic_apply_allowed": False,
        "automatic_merge_allowed": False,
        "limitations": [
            "This report trusts the supplied evidence bundle and does not independently execute validation, tests, or scanners.",
            "A clean scan comparison does not prove security or equivalent scanner coverage.",
            "Ready means evidence gates passed; it is not authorization to apply or merge.",
        ],
    }
