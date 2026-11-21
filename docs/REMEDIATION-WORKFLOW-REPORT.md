# Remediation Workflow Report (Phase 4E)

This command combines previously generated evidence into a decision report. It does **not** run patch validation, tests, or scanners; it trusts the supplied bundle.

    python3 -m sentinel_core remediation-report evidence-bundle.json --output remediation-report.json

Bundle JSON shape:

    {
      "patch_validation": {"valid": true, "issues": []},
      "patch_risk": {"risk_level": "low", "risk_score": 10},
      "sandbox": {"status": "pass", "commands": []},
      "scan_comparison": {"status": "clean", "summary": {}}
    }

Decision values:
- \`ready_for_manual_approval\`: all evidence gates passed and risk is classified low/medium. Human approval is still mandatory.
- \`blocked_or_manual_review\`: one or more gates failed, evidence is incomplete, or patch risk is high/unclassified.

No automatic patch application, approval, or merge is permitted. The report is a decision aid and must be reviewed alongside raw artifacts.
