import json
import unittest
from types import SimpleNamespace

from flask import Flask

from server.routes.job import JobDeps, create_job_blueprint
from server.services.job_stream_service import sse_message, stream_job_events


def make_job(**overrides):
    base = {
        "status": "hashing",
        "task_id": "job-1",
        "folder": "/photos",
        "dry_run": False,
        "mode": "copy",
        "engine": "fast",
        "prescreen_enabled": True,
        "prescreen_strength": "standard",
        "done": 1,
        "total": 3,
        "label": "处理中",
        "error": None,
        "error_info": None,
        "skipped": [],
        "started_at": 100.0,
        "finished_at": 0.0,
        "recent_events": [{"seq": 1, "name": "a.jpg", "ok": True}],
        "event_seq": 1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class JobStreamServiceTest(unittest.TestCase):
    def test_sse_message_encodes_json_payload(self):
        message = sse_message({"status": "处理中"}, event_id=7)

        self.assertIn("id: 7\n", message)
        self.assertIn("event: job\n", message)
        self.assertIn('data: {"status":"处理中"}\n\n', message)

    def test_stream_yields_changed_job_payload_and_updates_since(self):
        job = make_job()
        messages = list(
            stream_job_events(
                lambda: job,
                since=0,
                sleep=lambda _seconds: None,
                now=lambda: 101.0,
                max_messages=1,
            )
        )

        self.assertEqual(len(messages), 1)
        data_line = next(line for line in messages[0].splitlines() if line.startswith("data: "))
        payload = json.loads(data_line.removeprefix("data: "))
        self.assertEqual(payload["task_id"], "job-1")
        self.assertEqual(payload["event_seq"], 1)
        self.assertEqual(payload["events"], [{"seq": 1, "name": "a.jpg", "ok": True}])

    def test_stream_ends_after_terminal_payload(self):
        job = make_job(status="done", done=3, finished_at=110.0)

        messages = list(
            stream_job_events(
                lambda: job,
                since=1,
                sleep=lambda _seconds: None,
                now=lambda: 111.0,
            )
        )

        self.assertEqual(len(messages), 1)
        self.assertIn('"status":"done"', messages[0])

    def test_job_stream_route_returns_event_stream(self):
        flask_app = Flask(__name__)
        flask_app.register_blueprint(
            create_job_blueprint(
                JobDeps(
                    get_job=lambda: make_job(status="done", done=3, finished_at=110.0),
                    get_job_log=lambda: None,
                )
            )
        )

        response = flask_app.test_client().get("/api/job/stream?since=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertIn(b"event: job", response.data)
        self.assertIn(b'"status":"done"', response.data)


if __name__ == "__main__":
    unittest.main()
