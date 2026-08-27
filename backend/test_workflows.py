import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect
from sqlmodel import Session, create_engine, select

import app.database as database
import app.jobs.store as job_store_module
import app.workflows.store as workflow_store_module
from app.database import configure_sqlite_engine
from app.jobs.runtime import JobRuntime
from app.jobs.store import job_store
from app.migrations.runner import run_migrations
from app.models import Job, WorkflowRun, WorkflowStep
from app.services.projections import projection_coordinator
from app.workflows.store import workflow_store


class WorkflowRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self._tmp.name) / "workflow.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.database_path, app_version="test", backup_required=False)
        projection_coordinator.bootstrap(self.engine)
        self._engines = {
            module: module.engine
            for module in (database, job_store_module, workflow_store_module)
        }
        for module in self._engines:
            module.engine = self.engine

    def tearDown(self):
        for module, original in self._engines.items():
            module.engine = original
        self.engine.dispose()
        self._tmp.cleanup()

    def test_schema_v3_adds_workflow_tables_and_private_job_links(self):
        inspector = inspect(self.engine)
        self.assertTrue({"workflow_run", "workflow_step"}.issubset(inspector.get_table_names()))
        columns = {item["name"] for item in inspector.get_columns("job")}
        self.assertTrue({"workflow_run_id", "workflow_step_id"}.issubset(columns))

    def test_enqueue_is_deduplicated_and_public_view_is_path_free(self):
        first, created = workflow_store.create(
            "library.reconcile",
            {"media_root_ref": "manifest_abc"},
            dedupe_key="library.reconcile:test",
        )
        second, created_again = workflow_store.create(
            "library.reconcile",
            {"media_root_ref": "manifest_abc"},
            dedupe_key="library.reconcile:test",
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["current_step"], "discover")
        serialized = str(first)
        self.assertNotIn("media_root_ref", serialized)
        self.assertNotIn(str(self.database_path), serialized)
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(WorkflowRun)).all()), 1)
            self.assertEqual(len(session.exec(select(Job)).all()), 1)

    def test_job_execution_advances_steps_and_finishes_workflow(self):
        workflow, _created = workflow_store.create(
            "library.mark_path_missing",
            {"path_ref": "manifest_missing"},
            dedupe_key="missing:test",
        )
        job = job_store.claim_next()
        workflow_store.start_job(job["id"])

        def handler(_payload, ctx):
            ctx.progress(stage="resolve_subject", message="Resolving controlled reference")
            ctx.progress(stage="persist", message="Persisting missing state")
            ctx.progress(stage="finalize", message="Finalizing update")
            return {"status": "success", "updated": 1}

        with patch.dict("app.jobs.runtime.JOB_HANDLERS", {"library.mark_path_missing": handler}, clear=False):
            JobRuntime()._execute(job)

        completed = workflow_store.get(workflow["id"])
        self.assertEqual(completed["status"], "succeeded")
        self.assertTrue(all(step["status"] == "succeeded" for step in completed["steps"]))
        self.assertTrue(all(step["attempt"] >= 1 for step in completed["steps"] if step["started_at"]))

    def test_failure_retry_resumes_at_failed_step_and_preserves_completed_steps(self):
        workflow, _created = workflow_store.create(
            "analysis.analyze_film",
            {"film_id": "film_" + "a" * 32},
            dedupe_key="analysis:test",
        )
        job = job_store.claim_next()
        workflow_store.start_job(job["id"])
        workflow_store.progress(job["id"], "generate", "Generating candidates")
        failed = workflow_store.fail_job(job["id"], cancelled=False, error_code="provider_failed")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["current_step"], "generate")
        retried = workflow_store.retry(workflow["id"])
        self.assertEqual(retried["status"], "queued")
        self.assertEqual(retried["current_step"], "generate")
        self.assertEqual(retried["steps"][0]["status"], "succeeded")
        self.assertEqual(retried["steps"][1]["status"], "queued")
        with Session(self.engine) as session:
            jobs = session.exec(
                select(Job).where(Job.workflow_run_id == workflow["id"]).order_by(Job.created_at)
            ).all()
            self.assertEqual(len(jobs), 2)

    def test_queued_cancel_is_terminal_without_running_job(self):
        workflow, _created = workflow_store.create(
            "library.scan_folder",
            {"path_ref": "manifest_scan"},
            dedupe_key="scan:test",
        )
        cancelled = workflow_store.request_cancel(workflow["id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["steps"][0]["status"], "cancelled")
        self.assertTrue(cancelled["cancel_requested"])


if __name__ == "__main__":
    unittest.main()
