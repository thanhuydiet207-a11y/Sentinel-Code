# Phase 4P.24 — Retry Queue Observability

## Scope
Read-only operational snapshot reports retry queue status counts, due queued jobs, worker lease counts/expiration, atomic retry job status counts, and idempotency reservation counts.

## Safety
- Read-only SQL queries only.
- No job payload or raw idempotency key is exposed.
- Missing tables and database errors fail closed with structured status.

## Use
Pass an ISO timestamp to evaluate due jobs and expired leases. Timestamp comparisons assume normalized ISO-8601 values from the existing stores.

## Limitations
This is a snapshot, not a metrics exporter or alerting integration. It does not mutate, reclaim or schedule jobs.
