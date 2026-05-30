import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


class FakeThread:
    created = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        FakeThread.created.append(self)

    def start(self):
        return None


class TaskHistoryApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.db_path = self.tmp_path / "state.sqlite3"
        self.old_db_env = os.environ.get("INKMOMENT_STATE_DB")
        os.environ["INKMOMENT_STATE_DB"] = str(self.db_path)
        self.addCleanup(self._restore_db_env)

        sys.modules.setdefault("imagehash", types.SimpleNamespace(phash=lambda *args, **kwargs: "0" * 16))
        sys.modules.pop("app", None)
        self.app = importlib.import_module("app")
        self.addCleanup(lambda: sys.modules.pop("app", None))
        self.app.RUNTIME.session = None
        self.app.RUNTIME.job = None
        self.app.RUNTIME.last_infos = None
        self.app.RUNTIME.state_store = None
        self.original_thread = self.app.threading.Thread
        self.app.threading.Thread = FakeThread
        FakeThread.created = []
        self.addCleanup(self._restore_thread)

    def test_start_payload_records_running_task_history(self):
        photos = self.tmp_path / "photos"
        photos.mkdir()

        payload, status = self.app._start_job_payload(
            {
                "folder": str(photos),
                "dry_run": True,
                "mode": "copy",
                "engine": "fast",
                "wipe_cache": True,
            }
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["task_id"])
        self.assertEqual(len(FakeThread.created), 1)

        tasks = self.app._state_store().list_recent_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], payload["task_id"])
        self.assertEqual(tasks[0]["folder"], str(photos.resolve()))
        self.assertEqual(tasks[0]["status"], "running")
        self.assertIs(tasks[0]["dry_run"], True)

    def _restore_db_env(self):
        if self.old_db_env is None:
            os.environ.pop("INKMOMENT_STATE_DB", None)
        else:
            os.environ["INKMOMENT_STATE_DB"] = self.old_db_env

    def _restore_thread(self):
        self.app.threading.Thread = self.original_thread


if __name__ == "__main__":
    unittest.main()
