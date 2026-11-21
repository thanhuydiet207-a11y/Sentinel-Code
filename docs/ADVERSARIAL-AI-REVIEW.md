# Adversarial AI Review (Phase 3D)

The adversarial workflow runs three sequential passes for each selected provider:

1. **Independent:** assess the finding without seeing another AI's opinion.
2. **Challenger:** attempt to falsify or weaken the initial reasoning; do not invent evidence.
3. **Adjudicator:** inspect the finding and both earlier stages, surface unresolved conflicts,
   and provide a final advisory vote.

All prior reviewer output is treated as untrusted data in subsequent prompts. Provider
responses are validated through the existing review contract and consensus engine.
Cross-stage disagreement is reported per finding. Even unanimous dismissal never
suppresses a finding automatically.

## Usage

```bash
python3 -m sentinel_core adversarial-review findings.json \
  --providers openai anthropic gemini \
  --output adversarial-review.json
```

## Request and cost considerations

The workflow makes three sequential API requests per selected provider. Selecting all
three providers therefore makes nine requests. API charges and provider rate limits may
apply. No provider call runs in CI unless explicitly invoked with API credentials.

## Limitations

The workflow compares model-generated verdicts and evidence references. It does not
prove exploitability, guarantee independent model reasoning, or replace source-level
verification and human security review.
