# Cross-scanner correlation

Run `python3 -m sentinel_core correlate findings-semgrep.json findings-gitleaks.json findings-trivy.json --output correlations.json`.

Findings are grouped only when repository path and local evidence line hash match. If a hash is unavailable, exact line ranges are used as a fallback anchor. This intentionally avoids fuzzy matching that could create false corroboration.

- `corroborated` means two or more distinct scanner labels report the same anchor.
- `combined_confidence` is noisy-OR over input confidence values, capped at 0.99. It is a heuristic, not a calibrated probability.
- Severity is the highest severity in the group.
- Scanner disagreement and finding IDs/rules are retained.
- A scanner not reporting an issue is not treated as evidence that the issue is absent.
