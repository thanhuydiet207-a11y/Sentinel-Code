# Security Pipeline Orchestration (Phase 3E)

The `security-pipeline` command runs the deterministic and AI-assisted stages in one
auditable operation:

1. Validate the normalized finding package against source paths and SHA-256 evidence.
2. Optionally import existing Semgrep, Gitleaks, and Trivy JSON files (it does not launch scanners).
3. Deduplicate exact rule/location matches and validate the combined finding set again.
4. Correlate findings using exact source path and evidence line hash.
5. Run explainable false-positive triage heuristics.
6. Run the three-stage adversarial AI review.
7. Verify AI evidence references against local source for each review stage.
8. Produce JSON output containing the stages and an embedded Markdown report.

## Usage

```bash
python3 -m sentinel_core security-pipeline findings.json \
  --root . \
  --scanner-input semgrep=artifacts/semgrep.json \
  --scanner-input gitleaks=artifacts/gitleaks.json \
  --scanner-input trivy=artifacts/trivy.json \
  --providers openai anthropic gemini \
  --output artifacts/security-pipeline.json
```

The `--scanner-input` option is repeatable and accepts `semgrep=PATH`,
`gitleaks=PATH`, or `trivy=PATH`. Scanner executables must be run separately;
this command imports their existing JSON outputs.

## Cost and safety

Adversarial review performs three sequential requests per selected provider, so all
three listed providers cause nine API requests. Credentials are read from provider
environment variables and are not written into reports. Findings and evidence are
sent to the selected providers when this command is explicitly invoked. Charges and
rate limits may apply.

Invalid source evidence stops the pipeline before any AI requests. No stage suppresses
findings automatically. Scanner findings that cannot be mapped to verifiable local
source are recorded in the import's skipped list. Final decisions remain with a human
security reviewer.
