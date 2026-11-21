# Phase 4J — AI Adjudication Policy Gates

Phase 4J makes multi-stage AI review an explicit, configurable policy gate. It consumes the validated output of Phase 4I's independent → challenger → adjudicator pipeline; it does not trust a manually supplied provider count when the pipeline has actually run.

## Policy fields

Add these fields to a remediation policy:

```json
{
  "require_ai_adjudication": true,
  "min_adjudicator_reviewers": 2,
  "max_cross_stage_disagreements": 0,
  "min_adjudicator_confidence": 0.8
}
```

- `require_ai_adjudication`: require a completed adjudicator stage. When absent or false, AI adjudication is not a mandatory gate.
- `min_adjudicator_reviewers`: minimum distinct adjudicator reviewer records. Defaults to 1 when the gate is enabled.
- `max_cross_stage_disagreements`: maximum number of findings with disagreement across independent/challenger/adjudicator stages. Defaults to 0.
- `min_adjudicator_confidence`: minimum confidence among adjudicator votes. Defaults to 0.0.

## Decision semantics

- Missing AI stage, fewer than the required adjudicators, missing confidence, or incomplete finding coverage produces `REVIEW`.
- Cross-stage disagreement above the configured ceiling or confidence below the threshold produces `REVIEW`; the workflow must be resolved by a human.
- Existing hard failures such as patch validation failure, sandbox failure, regression findings, excessive patch risk, or invalid provenance continue to produce `BLOCK`.
- `PASS` means the configured gates passed; it never authorizes patch application or merge. Human approval remains mandatory.

## Evidence source and limitations

When the opt-in AI pipeline runs, adjudicator reviewer counts, vote confidence, adjudicated finding coverage, and cross-stage disagreements are derived from its schema-validated output. Without the AI pipeline, supplying reviewer names alone cannot satisfy this gate. Provider responses remain untrusted advisory content: confidence is self-reported, agreement is not proof of correctness, and this policy does not independently authenticate provider identity or model execution.

The adjudicator stage calls one provider request for each selected provider. The full three-stage workflow therefore makes three requests per provider and may incur API charges. AI requests occur only when `ai_providers` is explicitly supplied to `remediation-orchestrate`.
