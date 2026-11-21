# Offline AI Review Consensus

Phase 3A adds a provider-neutral contract for importing AI reviewer outputs and
summarizing agreement. It is **offline-only**: no API requests, credentials,
provider SDKs, or network access are performed.

## Input

Pass the existing findings JSON package and a reviewer package:

```json
{
  "reviewers": [
    {
      "reviewer_id": "reviewer-1",
      "provider": "provider-name",
      "model": "optional-model-id",
      "reviews": [
        {
          "finding_id": "F-001",
          "verdict": "confirmed",
          "confidence": 0.85,
          "rationale": "Brief reason",
          "evidence_refs": ["src/app.py:10-12"]
        }
      ]
    }
  ]
}
```

Verdicts: `confirmed`, `likely`, `uncertain`, `dismissed`. Confidence is a
reviewer's self-reported value, not calibrated probability. Each reviewer may
vote at most once per finding. Unknown finding IDs, duplicate reviewer IDs,
malformed verdicts, and non-finite/out-of-range confidence values are rejected.

## CLI

```bash
python3 -m sentinel_core review-consensus findings.json reviews.json --output consensus.json
```

The output reports per-finding verdict counts, dominant verdict, descriptive
agreement ratio, disagreement, positive-review corroboration (at least two
`confirmed`/`likely` votes), and reviewer rationales.

## Safety limits

- Votes are unweighted; provider/model identity does not imply reviewer independence.
- Agreement ratio is descriptive, not calibrated probability.
- No finding is auto-dismissed, auto-suppressed, or marked safe.
- Even unanimous dismissal remains `manual_review`.
- This phase defines an offline data contract only; provider API adapters and
  live requests are not implemented.
