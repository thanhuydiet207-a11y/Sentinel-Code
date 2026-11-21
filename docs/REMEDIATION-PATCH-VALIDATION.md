# Remediation Patch Validation (Phase 4A)

This phase validates an AI-proposed unified diff against a finding and the current local source file. It does not apply or write the patch.

## Proposal format

```json
{
  "finding_id": "F-1",
  "path": "src/example.py",
  "base_sha256": "SHA256_OF_CURRENT_FILE",
  "patch": "--- a/src/example.py\\n+++ b/src/example.py\\n@@ -1,1 +1,1 @@\\n-old code\\n+new code\\n"
}
```

## Checks

- Finding ID resolves to exactly one finding.
- Target path exactly matches the finding's source path and is repository-relative.
- Current source-file SHA-256 matches `base_sha256` (stale proposals fail closed).
- Unified diff headers target only the same file.
- Hunk context and removed lines match current source; declared hunk counts are checked.
- Binary patches, oversized patches, path traversal, and unsupported multi-file diffs are rejected.

The validator returns candidate content and its SHA-256 for review. It never modifies the repository. Patch application, tests, rescanning, and human approval remain separate steps.
