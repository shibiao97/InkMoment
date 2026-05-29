import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from server.state.local_store import (
    DB_FILE_NAME,
    SCHEMA_VERSION,
    LocalStateStore,
    default_state_dir,
)
from server.services.task_history_service import (
    job_history_payload,
    record_job_finished,
    record_job_started,
)


class FakeJob:
    task_id = "job-1"
    folder = "/photos/a"
    status = "done"
    mode = "copy"
    engine = "fast"
    dry_run = False
    started_at = 10.0
    finished_at = 20.0
    done = 3
    total = 5
    label = "完成"
    skipped = [("/photos/a/bad.jpg", "decode_error")]
    recent_events = [{"reject": True}, {"reject": False}]
    error = None


class LocalStateStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)

    def test_default_state_dir_uses_platform_conventions(self):
        home = self.tmp_path / "home"
        old_appdata = os.environ.pop("APPDATA", None)
        old_xdg_state_home = os.environ.pop("XDG_STATE_HOME", None)
        self.addCleanup(self._restore_env, "APPDATA", old_appdata)
        self.addCleanup(self._restore_env, "XDG_STATE_HOME", old_xdg_state_home)

        self.assertEqual(
            default_state_dir(home, "darwin"),
            home / "Library" / "Application Support" / "InkMoment",
        )
        self.assertEqual(
            default_state_dir(home, "win32"),
            home / "AppData" / "Roaming" / "InkMoment",
        )
        self.assertEqual(
            default_state_dir(home, "linux"),
            home / ".local" / "state" / "InkMoment",
        )

    def test_store_initializes_schema_and_round_trips_settings(self):
        store = LocalStateStore(self.tmp_path / DB_FILE_NAME)
        store.initialize()

        store.set_setting("theme", {"id": "garden", "accent": "#78a881"})
        store.set_setting("recent_folder", str(self.tmp_path / "photos"))

        self.assertEqual(store.get_setting("theme"), {"id": "garden", "accent": "#78a881"})
        self.assertEqual(store.get_setting("recent_folder"), str(self.tmp_path / "photos"))
        self.assertEqual(store.get_setting("missing", default="fallback"), "fallback")

        with closing(sqlite3.connect(store.path)) as conn:
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        self.assertEqual(version, SCHEMA_VERSION)

    def test_store_records_and_updates_task_history(self):
        store = LocalStateStore(self.tmp_path / DB_FILE_NAME)
        store.initialize()

        store.record_task({
            "id": "job-1",
            "folder": "/photos/a",
            "status": "running",
            "mode": "copy",
            "engine": "fast",
            "dry_run": False,
            "started_at": 10.0,
            "summary": {"total": 3},
        })
        store.record_task({
            "id": "job-2",
            "folder": "/photos/b",
            "status": "done",
            "mode": "move",
            "engine": "expert",
            "dry_run": True,
            "started_at": 20.0,
            "finished_at": 30.0,
            "summary": {"winners": 2},
        })
        store.record_task({
            "id": "job-1",
            "folder": "/photos/a",
            "status": "done",
            "mode": "copy",
            "engine": "fast",
            "dry_run": False,
            "started_at": 10.0,
            "finished_at": 15.0,
            "summary": {"winners": 1},
        })

        tasks = store.list_recent_tasks()

        self.assertEqual([task["id"] for task in tasks], ["job-2", "job-1"])
        self.assertIs(tasks[0]["dry_run"], True)
        self.assertEqual(tasks[0]["summary"], {"winners": 2})
        self.assertEqual(tasks[1]["status"], "done")
        self.assertEqual(tasks[1]["finished_at"], 15.0)
        self.assertEqual(tasks[1]["summary"], {"winners": 1})

    def test_record_task_rejects_missing_required_fields(self):
        store = LocalStateStore(self.tmp_path / DB_FILE_NAME)
        store.initialize()

        with self.assertRaisesRegex(ValueError, "folder"):
            store.record_task({
                "id": "job-1",
                "status": "done",
                "mode": "copy",
                "engine": "fast",
                "started_at": 1.0,
            })

    def test_image_analysis_cache_round_trips_and_invalidates_by_signature(self):
        store = LocalStateStore(self.tmp_path / DB_FILE_NAME)
        store.initialize()
        photo = self.tmp_path / "photos" / "a.jpg"
        photo.parent.mkdir()
        photo.write_bytes(b"first")
        signature = [{
            "role": "primary",
            "path": str(photo),
            "size": photo.stat().st_size,
            "mtime_ns": photo.stat().st_mtime_ns,
        }]
        payload = {
            "path": str(photo),
            "phash": "0" * 16,
            "quality": {"quality_score": 72.5, "flags": ["blurry"]},
        }

        store.put_image_analysis(
            path=str(photo),
            folder=str(photo.parent),
            engine="fast",
            strength="standard",
            face_aware=False,
            llm_model=None,
            input_signature=signature,
            payload=payload,
        )

        cached = store.get_image_analysis(
            path=str(photo),
            engine="fast",
            strength="standard",
            face_aware=False,
            llm_model=None,
            input_signature=signature,
        )
        self.assertEqual(cached["quality"]["quality_score"], 72.5)
        self.assertEqual(cached["quality"]["flags"], ["blurry"])

        stale_signature = [dict(signature[0], size=999)]
        self.assertIsNone(store.get_image_analysis(
            path=str(photo),
            engine="fast",
            strength="standard",
            face_aware=False,
            llm_model=None,
            input_signature=stale_signature,
        ))

        stats = store.image_analysis_stats(str(photo.parent))
        self.assertEqual(stats["entries"], 1)
        self.assertGreater(stats["payload_bytes"], 0)
        self.assertEqual(store.clear_image_analysis(str(photo.parent)), 1)
        self.assertEqual(store.image_analysis_stats(str(photo.parent))["entries"], 0)

    def test_task_history_service_records_job_lifecycle(self):
        store = LocalStateStore(self.tmp_path / DB_FILE_NAME)
        job = FakeJob()
        job.status = "pending"
        job.finished_at = 0.0

        record_job_started(store, job)
        job.status = "done"
        job.finished_at = 20.0
        record_job_finished(store, job)

        tasks = store.list_recent_tasks()
        self.assertEqual(tasks[0]["id"], "job-1")
        self.assertEqual(tasks[0]["status"], "done")
        self.assertEqual(tasks[0]["summary"]["skipped_count"], 1)
        self.assertEqual(tasks[0]["summary"]["rejected_running"], 1)

    def test_task_history_service_updates_cancelled_job(self):
        store = LocalStateStore(self.tmp_path / DB_FILE_NAME)
        job = FakeJob()
        job.status = "pending"
        job.finished_at = 0.0

        record_job_started(store, job)
        job.status = "cancelled"
        job.finished_at = 12.0
        record_job_finished(store, job)

        task = store.list_recent_tasks()[0]
        self.assertEqual(task["status"], "cancelled")
        self.assertEqual(task["finished_at"], 12.0)

    def test_job_history_payload_uses_running_without_mutating_job(self):
        job = FakeJob()
        job.status = "pending"

        payload = job_history_payload(job, status="running")

        self.assertEqual(payload["status"], "running")
        self.assertEqual(job.status, "pending")

    @staticmethod
    def _restore_env(name, value):
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
