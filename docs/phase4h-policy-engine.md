# Phase 4H — Declarative Policy Engine

Policy evaluation consumes supplied evidence and returns **PASS**, **BLOCK**, or **REVIEW**. It never applies patches or authorizes merges.

Example policy:
```json
{
  "policy_id": "production-remediation",
  "version": 1,
  "max_risk_score": 25,
  "required_scanners": ["semgrep", "gitleaks"],
  "required_reviewers": ["openai"],
  "min_reviewers": 1,
  "require_evidence_verified": true,
  "require_sandbox_pass": true,
  "require_regression_clean": true,
  "require_manual_approval": true
}
```

Evidence JSON expects `patch_validation`, `sandbox`, `scan_comparison`, `patch_risk`, `scanners`, `reviewers`, and `evidence_verified`. Missing required evidence yields REVIEW; failed validation, sandbox, regression, or excessive risk yields BLOCK. CLI: `sentinel-security evaluate-policy policy.json evidence.json --output result.json`.

A PASS is only a policy gate result based on caller-provided evidence. Human approval remains required; automatic apply/merge is disabled.
