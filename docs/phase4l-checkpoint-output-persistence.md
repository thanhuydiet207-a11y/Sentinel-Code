# Phase 4L — Checkpoint Output Persistence

Completed checkpoint events now retain their output payload alongside the SHA-256 output digest. The event hash covers both, so modifying or removing an output invalidates the chain.

Python API:

```python
from sentinel_core.workflow_state import checkpoint_outputs

outputs = checkpoint_outputs(store_dir, workflow_id, input_digest)
```

The helper verifies the entire workflow state and optionally checks the input digest before returning outputs keyed by completed stage. It raises `ValueError` for invalid state or mismatched input.

This fixes a Phase 4K gap: checkpoint events previously recorded an output digest but omitted the output itself, so a caller could know a stage completed but could not restore its result. This remains a state persistence primitive; the remediation orchestrator does not yet automatically checkpoint or resume individual stages. Workflow files contain output data and must be protected as sensitive local artifacts.
