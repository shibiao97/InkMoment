import tempfile
import unittest
from pathlib import Path

from server.domain.models import GroupState, SessionState
from server.services.session_apply_service import (
    apply_group,
    apply_pending_groups,
    reopen_group,
    unique_target,
)


def write_file(path: Path, body: bytes = b"image") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


class SessionApplyServiceTest(unittest.TestCase):
    def test_unique_target_adds_incrementing_suffix(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_file(root / "photo.jpg")
            write_file(root / "photo_1.jpg")

            self.assertEqual(unique_target(root, "photo.jpg"), root / "photo_2.jpg")

    def test_dry_run_returns_preview_without_marking_group_applied(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            winner = str(write_file(root / "winner.jpg"))
            group = GroupState(images=[winner], winner=winner, finished=True)
            session = SessionState(
                folder=folder,
                dry_run=True,
                mode="copy",
                groups=[group],
            )

            result = apply_group(group, folder, True, "copy", session)

            self.assertEqual(result["winner"]["from"], winner)
            self.assertFalse(Path(result["winner"]["to"]).exists())
            self.assertFalse(group.applied)
            self.assertEqual(apply_pending_groups(session)[0]["winner"]["from"], winner)

    def test_copy_mode_keeps_originals_and_copies_companions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            winner = str(write_file(root / "IMG_0001.CR2", b"raw"))
            companion = str(write_file(root / "IMG_0001.JPG", b"jpeg"))
            loser = str(write_file(root / "blur.jpg", b"blur"))
            group = GroupState(
                images=[winner, loser],
                winner=winner,
                losers=[loser],
                finished=True,
            )
            session = SessionState(
                folder=folder,
                dry_run=False,
                mode="copy",
                groups=[group],
                companions={winner: [companion]},
            )

            result = apply_group(group, folder, False, "copy", session)

            self.assertEqual(result["failed"], [])
            self.assertTrue(Path(winner).exists())
            self.assertTrue(Path(companion).exists())
            self.assertTrue(Path(loser).exists())
            self.assertTrue((root / "winners" / "IMG_0001.CR2").exists())
            self.assertTrue((root / "winners" / "IMG_0001.JPG").exists())
            self.assertTrue((root / "losers" / "blur.jpg").exists())
            self.assertEqual(group.winner, winner)
            self.assertEqual(group.losers, [loser])
            self.assertTrue(group.applied)
            self.assertEqual(
                [entry["kind"] for entry in group.move_log],
                ["winner", "winner_companion", "loser"],
            )

    def test_move_mode_updates_session_paths_and_reopen_restores_group(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            winner = str(write_file(root / "IMG_0002.CR2", b"raw"))
            companion = str(write_file(root / "IMG_0002.JPG", b"jpeg"))
            group = GroupState(images=[winner], winner=winner, finished=True)
            session = SessionState(
                folder=folder,
                dry_run=False,
                mode="move",
                groups=[group],
                companions={winner: [companion]},
                meta={winner: {"datetime": "2026:05:29 12:00:00"}},
            )

            result = apply_group(group, folder, False, "move", session)

            moved_winner = result["winner"]["to"]
            moved_companion = session.companions[moved_winner][0]
            self.assertFalse(Path(winner).exists())
            self.assertFalse(Path(companion).exists())
            self.assertTrue(Path(moved_winner).exists())
            self.assertTrue(Path(moved_companion).exists())
            self.assertEqual(group.winner, moved_winner)
            self.assertEqual(session.meta[moved_winner]["datetime"], "2026:05:29 12:00:00")

            reopen_result = reopen_group(group, folder, "move", session)

            self.assertEqual(reopen_result["failed"], [])
            self.assertTrue(Path(winner).exists())
            self.assertTrue(Path(companion).exists())
            self.assertFalse(Path(moved_winner).exists())
            self.assertFalse(Path(moved_companion).exists())
            self.assertFalse(group.finished)
            self.assertFalse(group.applied)
            self.assertEqual(group.left, winner)
            self.assertEqual(session.companions[winner], [companion])


if __name__ == "__main__":
    unittest.main()
