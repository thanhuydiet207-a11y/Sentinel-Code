# Regression & Security Rescan Comparison (Phase 4C)

Compare normalized scanner finding snapshots before and after a proposed remediation.

    python3 -m sentinel_core compare-scans baseline.json candidate.json --output comparison.json

Inputs may be a finding list or an object containing \`findings\`. Identity uses path, scanner, rule ID, and evidence hash where available; without a hash, line and title are used as fallback. Output classifies fixed, new, persisting, duplicate, and severity changes.

A new finding or severity increase yields \`status=regression\`; otherwise \`clean\`. \`clean\` is not a security certification: scanners, configs, coverage, and identity heuristics can change. Confirm the candidate scan completed and compare scanner coverage. Findings marked fixed are not auto-dismissed and require human verification.
