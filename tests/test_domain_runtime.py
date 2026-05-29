import unittest

from server.domain.models import (
    DEFAULT_NEAR_SECONDS,
    DEFAULT_THRESHOLD_FAR,
    DEFAULT_THRESHOLD_NEAR,
    GroupState,
    JobState,
    SessionState,
)
from server.runtime.app_runtime import AppRuntime, new_grouping_state


class DomainRuntimeTest(unittest.TestCase):
    def test_domain_defaults_match_desktop_workflow_defaults(self):
        session = SessionState(folder="/photos", dry_run=False)
        job = JobState(folder="/photos", dry_run=False)

        self.assertEqual(session.threshold_near, DEFAULT_THRESHOLD_NEAR)
        self.assertEqual(session.threshold_far, DEFAULT_THRESHOLD_FAR)
        self.assertEqual(session.near_seconds, DEFAULT_NEAR_SECONDS)
        self.assertEqual(job.threshold_near, DEFAULT_THRESHOLD_NEAR)
        self.assertEqual(job.threshold_far, DEFAULT_THRESHOLD_FAR)
        self.assertEqual(job.near_seconds, DEFAULT_NEAR_SECONDS)
        self.assertEqual(session.engine, "fast")
        self.assertEqual(job.status, "pending")

    def test_group_state_generates_independent_ids_and_lists(self):
        first = GroupState(images=["a.jpg"])
        second = GroupState(images=["b.jpg"])

        first.pending.append("c.jpg")

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.pending, ["c.jpg"])
        self.assertEqual(second.pending, [])

    def test_runtime_grouping_state_isolated_per_instance(self):
        first = AppRuntime()
        second = AppRuntime()

        first.grouping["status"] = "running"
        first.grouping["groups"].append({"id": "g1"})

        self.assertEqual(second.grouping, new_grouping_state())
        self.assertEqual(first.grouping["groups"], [{"id": "g1"}])


if __name__ == "__main__":
    unittest.main()
