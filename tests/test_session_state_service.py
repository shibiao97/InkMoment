import json
import unittest

from server.domain.models import GroupState, SessionState
from server.services.session_state_service import (
    STATE_FILENAME,
    STATE_SCHEMA,
    group_from_dict,
    load_state,
    migrate_state,
    save_state,
    state_path,
)


class SessionStateServiceTest(unittest.TestCase):
    def test_state_path_uses_session_state_filename(self):
        self.assertEqual(state_path("/photos").name, STATE_FILENAME)

    def test_save_and_load_state_round_trip(self):
        with self.subTest("round trip"):
            import tempfile
            from pathlib import Path

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                session = SessionState(
                    folder=str(root),
                    dry_run=True,
                    mode="move",
                    engine="fast",
                    groups=[
                        GroupState(
                            images=["a.jpg", "b.jpg"],
                            left="a.jpg",
                            right="b.jpg",
                            losers=["b.jpg"],
                            auto_rejected=["b.jpg"],
                            auto_reject_reasons={"b.jpg": "模糊"},
                        )
                    ],
                    current_group=1,
                    companions={"a.raw": ["a.jpg"]},
                )

                save_state(session)
                raw = json.loads((root / STATE_FILENAME).read_text(encoding="utf-8"))
                loaded = load_state(str(root))

                self.assertEqual(raw["schema"], STATE_SCHEMA)
                self.assertEqual(loaded.folder, str(root))
                self.assertEqual(loaded.mode, "move")
                self.assertEqual(loaded.current_group, 1)
                self.assertEqual(loaded.companions, {"a.raw": ["a.jpg"]})
                self.assertEqual(loaded.groups[0].auto_reject_reasons, {"b.jpg": "模糊"})

    def test_migrate_v4_adds_prescreen_and_companion_fields(self):
        payload = {
            "schema": 4,
            "folder": "/photos",
            "groups": [{"images": ["a.jpg"]}],
        }

        migrated = migrate_state(payload)

        self.assertEqual(migrated["schema"], STATE_SCHEMA)
        self.assertEqual(migrated["companions"], {})
        self.assertEqual(migrated["prescreen_enabled"], True)
        self.assertEqual(migrated["groups"][0]["auto_rejected"], [])
        self.assertEqual(migrated["groups"][0]["auto_reject_reasons"], {})

    def test_group_from_dict_generates_id_for_legacy_group(self):
        group = group_from_dict({"images": ["a.jpg"]})

        self.assertTrue(group.id)
        self.assertEqual(group.images, ["a.jpg"])


if __name__ == "__main__":
    unittest.main()
