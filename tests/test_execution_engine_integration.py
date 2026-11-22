import sqlite3
import unittest

from sentinel_core.retry_queue_store import RetryQueueStore
from sentinel_core.worker_leases import RetryWorkerLeaseStore
from sentinel_core.task_handler_registry import TaskHandlerRegistry
from sentinel_core.task_execution_adapter import TaskExecutionAdapter
from sentinel_core.worker_execution_coordinator import WorkerExecutionCoordinator
from sentinel_core.retry_recovery import RetryPolicyEngine, RetryRecoveryCoordinator
from sentinel_core.workflow_runtime import WorkflowExecutionRuntime
from sentinel_core.workflow_runtime_store import DurableWorkflowRuntimeStore
from sentinel_core.durable_workflow_runtime import DurableWorkflowRuntime

T0 = "2026-01-01T00:00:00+00:00"
T1 = "2026-01-01T00:00:01+00:00"
T2 = "2026-01-01T00:00:10+00:00"
T3 = "2026-01-01T00:00:11+00:00"
T4 = "2026-01-01T00:00:20+00:00"

def _job(job_id, attempt):
    return {"schema": 1, "job_id": job_id, "workflow_id": "wf-integration",
            "stage": "stage-run", "execution_id": "exec-integration",
            "task_id": "task-integration", "attempt_number": attempt,
            "status": "queued", "scheduled_at": T0, "due_at": T0}

class ExecutionEngineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.queue = RetryQueueStore(self.connection)
        self.leases = RetryWorkerLeaseStore(self.connection)
        self.registry = TaskHandlerRegistry()
        self.adapter = TaskExecutionAdapter(self.registry)
        self.worker = WorkerExecutionCoordinator(self.leases, self.adapter)
        self.policy = RetryPolicyEngine(max_attempts=3, base_delay_seconds=1,
                                       max_delay_seconds=5, jitter_ratio=0)
        self.recovery = RetryRecoveryCoordinator(self.policy, self.queue)

    def tearDown(self):
        self.connection.close()

    def test_full_fail_retry_success_pipeline(self):
        calls = []
        def handler(payload, context=None):
            calls.append(context["retry"]["attempt_number"])
            if context["retry"]["attempt_number"] == 1:
                raise RuntimeError("transient failure")
            return {"value": payload["value"] + 1}
        self.assertEqual(self.registry.register("integration.handler", handler)["action"], "registered")
        task = {"task_id": "task-integration", "handler": "integration.handler",
                "handler_version": "1", "input": {"value": 40}}
        self.assertEqual(self.queue.enqueue(_job("job-1", 1))["action"], "stored")

        first_claim = self.worker.claim_due(T0, "worker-a", 30)
        self.assertEqual(first_claim["action"], "claimed")
        claimed_job, lease = first_claim["jobs"][0]["job"], first_claim["jobs"][0]["lease"]
        first_execution = self.worker.execute_claimed(claimed_job, lease, task, T0, T1, 30)
        self.assertEqual(first_execution["action"], "failed")
        self.assertEqual(first_execution["lease"]["action"], "completed")

        decision = self.recovery.recover(claimed_job, 1, "transient", T1, "job-2")
        self.assertEqual(decision["action"], "scheduled")
        self.assertEqual(decision["job"]["execution_id"], "exec-integration")
        self.assertEqual(decision["job"]["parent_job_id"], "job-1")

        second_claim = self.worker.claim_due(T2, "worker-b", 30)
        self.assertEqual(second_claim["action"], "claimed")
        retry_job, retry_lease = second_claim["jobs"][0]["job"], second_claim["jobs"][0]["lease"]
        second_execution = self.worker.execute_claimed(retry_job, retry_lease, task, T2, T3, 30)
        self.assertEqual(second_execution["action"], "completed")
        self.assertEqual(second_execution["execution"]["result"], {"value": 41})
        self.assertEqual(calls, [1, 2])
        self.assertEqual(self.queue.get("job-1")["job"]["status"], "failed")
        self.assertEqual(self.queue.get("job-2")["job"]["status"], "completed")

    def test_blocked_handler_does_not_invoke_and_releases_claim(self):
        invoked = []
        self.registry.register("integration.safe", lambda payload, context=None: invoked.append(True))
        self.queue.enqueue(_job("job-blocked", 1))
        claimed = self.worker.claim_due(T0, "worker-x", 20)["jobs"][0]
        wrong_task = {"task_id": "other-task", "handler": "integration.safe", "input": {}}
        result = self.worker.execute_claimed(claimed["job"], claimed["lease"], wrong_task, T0, T1, 20)
        self.assertEqual(result["action"], "blocked")
        self.assertEqual(result["execution"]["reason"], "task_job_mismatch")
        self.assertEqual(invoked, [])
        reclaimed = self.worker.claim_due(T2, "worker-y", 20)
        self.assertEqual(reclaimed["action"], "claimed")

    def test_durable_runtime_restore_and_version_conflict(self):
        store = DurableWorkflowRuntimeStore(self.connection)
        runtime = WorkflowExecutionRuntime(["one", "two"], {"two": ["one"]}, 1)
        created = DurableWorkflowRuntime.create(store, "exec-durable", "wf-durable", runtime, T0)
        self.assertEqual(created["action"], "created")
        durable = created["durable_runtime"]
        runtime.start_stage("one", T1)
        runtime.finish_stage("one", "completed", T2)
        persisted = durable.persist(T2)
        self.assertEqual(persisted["action"], "persisted")
        restored = DurableWorkflowRuntime.restore(store, "exec-durable")
        self.assertEqual(restored["action"], "restored")
        self.assertEqual(restored["durable_runtime"].runtime.stage_states["one"], "completed")
        stale = durable.persist(T3)
        self.assertEqual(stale["action"], "conflict")
        self.assertEqual(stale["current_version"], 2)

if __name__ == "__main__":
    unittest.main()
