import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from server.state.local_store import (
    DB_FILE_NAME,
    LocalStateStore,
    default_state_dir,
)


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

        with sqlite3.connect(store.path) as conn:
            version = conn.execute("SELECT version FROM schema_migrations").fetchone()[0]
        self.assertEqual(version, 1)

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

    @staticmethod
    def _restore_env(name, value):
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


if __name__ == "__main__":
    unittest.main()

