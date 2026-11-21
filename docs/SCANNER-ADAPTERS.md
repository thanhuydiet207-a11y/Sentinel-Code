# Phase 2: Scanner result adapters

Sentinel-Code can import JSON output from **Semgrep**, **Gitleaks**, and **Trivy** into its shared finding format.

This is an adapter/import layer, not scanner execution. Install and run each scanner separately, then pass its JSON output to Sentinel-Code.

## Supported inputs

- Semgrep: `semgrep --json --output semgrep.json`
- Gitleaks: `gitleaks detect --report-format json --report-path gitleaks.json`
- Trivy: `trivy fs --format json --output trivy.json .`

## Import

From the repository root:

```bash
python3 -m sentinel_core import-scanner semgrep semgrep.json --root . --output findings-semgrep.json
python3 -m sentinel_core import-scanner gitleaks gitleaks.json --root . --output findings-gitleaks.json
python3 -m sentinel_core import-scanner trivy trivy.json --root . --output findings-trivy.json
```

Then validate source evidence:

```bash
python3 -m sentinel_core validate findings-semgrep.json --root .
```

## Safety and limitations

- Scanner file paths must resolve inside the repository; traversal and outside-root symlinks are rejected.
- Source line ranges must exist. The adapter calculates SHA-256 evidence from the local source rather than trusting scanner-provided hashes.
- Records that cannot be mapped to a local file and line range are listed under `metadata.skipped`; they are not silently discarded.
- The current Trivy adapter maps findings to the reported target file and line 1 when the scanner doesn't supply a line. This provides a verifiable manifest-level anchor, not a claim that the vulnerability is located on that line.
- Scanner confidence is an adapter default, not a calibrated probability.
- No scanner binaries are installed or executed by the adapter. No network access is required to import JSON.
