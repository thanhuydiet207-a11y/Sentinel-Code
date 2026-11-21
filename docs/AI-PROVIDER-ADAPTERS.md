# AI Provider Adapters (Phase 3B)

Sentinel-Code provides explicit, opt-in HTTP adapters for OpenAI, Anthropic, and
Gemini using Python's standard library. This feature makes API requests only
when the `ai-review` command is executed. It does not run during scanner CI.

## Credentials

Supply keys as environment variables; never commit them or place them in CLI
arguments:

- `SENTINEL_OPENAI_API_KEY`
- `SENTINEL_ANTHROPIC_API_KEY`
- `SENTINEL_GEMINI_API_KEY`

Optional model variables:

- `SENTINEL_OPENAI_MODEL` (default `gpt-4o-mini`)
- `SENTINEL_ANTHROPIC_MODEL` (default `claude-3-5-haiku-latest`)
- `SENTINEL_GEMINI_MODEL` (default `gemini-2.0-flash`)

OpenAI-compatible endpoint can be set using `SENTINEL_OPENAI_BASE_URL`.
Anthropic and Gemini endpoints can be overridden for compatible gateways with
`SENTINEL_ANTHROPIC_BASE_URL` and `SENTINEL_GEMINI_BASE_URL`.

## Run reviews

```bash
export SENTINEL_OPENAI_API_KEY="..."
export SENTINEL_ANTHROPIC_API_KEY="..."
export SENTINEL_GEMINI_API_KEY="..."
python3 -m sentinel_core ai-review findings.json --providers openai anthropic gemini --output reviews.json
python3 -m sentinel_core review-consensus findings.json reviews.json --output consensus.json
```

Choose only providers you have configured. Calls can incur provider charges and
send finding titles, locations, descriptions, and evidence snippets to the
selected provider. Review local/private code before using cloud APIs. No keys
or provider responses are logged by the adapter.

## Contract and safety

Each response must return a JSON object with a `reviews` array, one vote per
finding, using the existing verdict contract. Responses are validated through the
consensus engine. Malformed output, missing IDs, invalid confidence, duplicate
votes, or unknown findings fail the run. The adapter does not retry or silently
discard a provider failure.

The prompt treats finding data as untrusted and requests evidence-based review.
This is a prompt-level defense, not a guarantee against prompt injection.
Provider verdicts remain advisory. No finding is auto-suppressed or marked safe.
