# Sentinel-Code benchmark

This seed benchmark contains 16 small, labeled source fixtures covering JavaScript, Python, and Java. It includes vulnerable and deliberately safe examples so a reviewer that reports every suspicious-looking pattern is penalized.

## Files

- `security-review-v1.json`: ground-truth fixtures, inline source files, and expected rule/location/severity.
- `results-template.json`: input template for an AI agent or scanner.
- `../sentinel_core/benchmark.py`: deterministic scoring engine.

## Result format

For each case, populate `findings` with items shaped as:

```json
{
  "rule_id": "CWE-89/SQL-INJECTION",
  "category": "CWE-89",
  "path": "src/invoice.js",
  "start_line": 2,
  "end_line": 3,
  "severity": "high"
}
```

Use the fixture-relative path and a line range overlapping the ground-truth range. Each case ID must occur no more than once. Unknown case IDs and malformed findings are rejected. Exact duplicate predictions are collapsed before scoring.

## Run

From the repository root:

```bash
python3 -m sentinel_core benchmark --dataset benchmarks/security-review-v1.json --results benchmarks/results-template.json
```

Metrics include precision, recall, F1, safe-case false-positive rate, case coverage, severity accuracy, per-CWE results, and matched/false-positive/missed finding details. If no predictions were submitted, precision is `null` (undefined), not 100%. If there are no severity comparisons, severity accuracy is also `null`. The report lists case IDs that were not scored.

Missing vulnerable cases count as false negatives. Missing safe cases do not count as a clean result; they reduce case coverage. Always report coverage beside model scores.

## Limitations

This is an initial seed set, not a statistically representative security benchmark. Fixtures are synthetic and intentionally small. Matching uses exact rule ID, exact path, and overlapping lines; it does not independently prove exploitability. Expand with reviewed, licensed real-world cases, more languages/frameworks, multi-file data flows, business-logic issues, and mitigated near-misses before using scores for product claims.
