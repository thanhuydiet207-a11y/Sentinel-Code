# Security finding contract

The canonical machine-readable schema is `schemas/security-findings.schema.json`. The Python core applies additional repository-aware checks that JSON Schema alone cannot perform:

- Resolve `location.path` inside the selected repository and reject path traversal or symlinks that escape the root.
- Verify line bounds against the current file.
- Recompute SHA-256 over the referenced normalized lines and compare it with `evidence.line_hash`.
- Require a reasoned evidence statement and constrained confidence.
- Reject duplicate finding IDs and malformed severity/category identifiers.

## Line hash algorithm

The hash is SHA-256 of the UTF-8 bytes of the selected file lines joined with a single LF character, with no trailing LF. Python text-mode newline normalization is used. Generate it with:

```bash
python3 -m sentinel_core hash-lines --root . --path src/file.py --start 12 --end 14
```

Do not include raw credentials or full source excerpts in a report. The digest binds the finding to exact source lines without publishing those lines.

## Example finding

```json
{
  "schema_version": "1.0",
  "findings": [{
    "id": "PR123-CWE89-001",
    "title": "Untrusted input reaches a SQL query",
    "rule_id": "CWE-89/SQL-INJECTION",
    "category": "CWE-89",
    "severity": "high",
    "confidence": 0.92,
    "location": {"path": "src/invoice.py", "start_line": 12, "end_line": 14},
    "evidence": {
      "reason": "The request-controlled value is concatenated into the SQL statement.",
      "line_hash": "REPLACE_WITH_OUTPUT_FROM_HASH_LINES",
      "data_flow": ["request.args.email", "string concatenation", "database query"]
    },
    "impact": "An attacker may alter the database query.",
    "remediation": "Replace string concatenation with a parameterized query."
  }]
}
```

The example digest is deliberately a placeholder and will not pass runtime validation until replaced with the digest of the actual source.
