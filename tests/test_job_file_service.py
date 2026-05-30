import json
import tempfile
import unittest
from pathlib import Path

from server.services.job_file_service import (
    pic_dir,
    record_skipped_items,
    skipped_log_path,
    wipe_job_caches,
)
from server.services.session_state_service import state_path


class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)


class JobFileServiceTest(unittest.TestCase):
    def test_record_skipped_items_appends_to_skipped_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = FakeLogger()

            record_skipped_items(tmp, [("/photos/a.raw", "decode"), ("/photos/b.raw", "empty")], logger)

            lines = skipped_log_path(tmp).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[0].endswith("\t/photos/a.raw\tdecode"))
            self.assertTrue(lines[1].endswith("\t/photos/b.raw\tempty"))
            self.assertEqual(logger.warnings, [])

    def test_wipe_job_caches_deletes_copy_mode_outputs_without_moving_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logger = FakeLogger()
            (root / "winners").mkdir()
            (root / "winners" / "copy.jpg").write_text("copy", encoding="utf-8")
            (root / "original.jpg").write_text("original", encoding="utf-8")
            pic_dir(tmp).mkdir()
            (pic_dir(tmp) / "log.txt").write_text("log", encoding="utf-8")
            state_path(tmp).write_text(json.dumps({"mode": "copy"}), encoding="utf-8")

            wipe_job_caches(tmp, logger)

            self.assertFalse((root / "winners").exists())
            self.assertFalse(pic_dir(tmp).exists())
            self.assertFalse(state_path(tmp).exists())
            self.assertEqual((root / "original.jpg").read_text(encoding="utf-8"), "original")
            self.assertFalse((root / "copy.jpg").exists())
            self.assertEqual(logger.warnings, [])

    def test_wipe_job_caches_restores_move_mode_outputs_with_collision_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logger = FakeLogger()
            (root / "winners").mkdir()
            (root / "losers").mkdir()
            (root / "photo.jpg").write_text("original", encoding="utf-8")
            (root / "winners" / "photo.jpg").write_text("winner", encoding="utf-8")
            (root / "losers" / "reject.jpg").write_text("reject", encoding="utf-8")
            state_path(tmp).write_text(json.dumps({"mode": "move"}), encoding="utf-8")

            wipe_job_caches(tmp, logger)

            self.assertFalse((root / "winners").exists())
            self.assertFalse((root / "losers").exists())
            self.assertEqual((root / "photo.jpg").read_text(encoding="utf-8"), "original")
            self.assertEqual((root / "photo_1.jpg").read_text(encoding="utf-8"), "winner")
            self.assertEqual((root / "reject.jpg").read_text(encoding="utf-8"), "reject")
            self.assertEqual(logger.warnings, [])


if __name__ == "__main__":
    unittest.main()
