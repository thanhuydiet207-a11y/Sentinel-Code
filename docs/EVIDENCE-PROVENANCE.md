# Evidence Integrity & Provenance (Phase 4F)

Seal evidence artifact files and verify their content hashes later.

    python3 -m sentinel_core seal-evidence bundle.json --root . --output sealed-evidence.json
    python3 -m sentinel_core verify-evidence sealed-evidence.json --root .

Input fields:
- \`source_commit\`: optional caller-supplied source revision.
- \`candidate_sha256\`: optional SHA-256 of candidate patch/content.
- \`metadata\`: optional JSON metadata.
- \`artifacts\`: required list of \`{name, kind, path}\` records.

Sealing records each artifact's SHA-256 and byte size, then hashes canonical bundle metadata. Verification recalculates artifact and bundle hashes and reports mismatches. Artifact paths must be relative, traversal-free, regular files, and not symlinks.

Integrity hashes detect changed content but do not prove authorship, trusted time, or scanner completeness. Source commit/candidate hash values are caller-supplied and must be independently checked. No signatures, automatic approvals, or patch application are performed.
