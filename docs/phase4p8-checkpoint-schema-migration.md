# Phase 4P.8 — Checkpoint Schema Validation and Migration

## Schema v2
New workflows use schema version 2 and require structural fields including workflow ID, status, timestamps, input digest, stage plan, checkpoints, event count, head hash, metadata, limitations, and migration history.

## APIs
- `validate_workflow_schema(state)`: structural validation; accepts supported schema v1 and v2.
- `verify_workflow(state)`: validates structure plus event hash-chain and output digests.
- `migrate_workflow(store, workflow_id)`: migrates v1 to v2 under the workflow writer lock.

## Migration safety
- Refuses malformed structures or invalid checkpoint chains.
- Creates a non-overwriting `.schema1.bak` backup before replacing the original.
- Records migration source, destination, timestamp, and backup filename.
- Migration is idempotent for schema v2.
- If post-migration verification fails, restores the original state while retaining the backup.

## Compatibility
Checkpoint event hashes are unchanged by migration. Schema v1 remains verifiable and can be migrated explicitly; no automatic migration occurs during load/resume.

## Verification
Tests added for successful migration, backup creation, preserved outputs/hash chain, malformed schema, and corrupted checkpoint refusal. CI must execute them.
