# AI Evidence Verification (Phase 3C)

The `verify-ai-evidence` command checks reviewer evidence references against the
checked-out repository. It verifies safe relative paths, line ranges, and whether
a reference exactly matches the finding location and declared SHA-256 line hash.

This is deterministic source-location validation, **not proof of exploitability,
data flow, or the correctness of an AI rationale**. It never suppresses findings.

## Usage

```bash
python3 -m sentinel_core verify-ai-evidence findings.json reviews.json --root . --output verification.json
```

References use `path:line` or `path:start-end`. Unsafe paths, missing files, and
out-of-range references are marked invalid. The declared hash is compared only
when a reviewer reference exactly matches the finding's path and line range.
