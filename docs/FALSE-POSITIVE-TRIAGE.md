# False-positive triage

Run:

```bash
python3 -m sentinel_core triage findings.json --output triage.json
```

This module uses transparent heuristics to flag findings for review when confidence is low, evidence explanation/hash is missing or malformed, line range is invalid, severity is informational, or title uses generic uncertainty wording.

**It does not determine that a finding is false positive.** A score is a heuristic review-risk indicator, not a probability. Findings are never automatically suppressed. Human reviewers should verify code behavior and document any disposition.
