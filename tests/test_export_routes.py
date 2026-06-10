from flask import Flask

from server.routes.export import ExportDeps, create_export_blueprint


def test_export_routes_delegate_to_dependencies():
    calls = []
    app = Flask(__name__)
    app.register_blueprint(
        create_export_blueprint(
            ExportDeps(
                preview_export=lambda data: _record(calls, "preview", data, ({"ok": True}, 200)),
                start_export=lambda data: _record(calls, "start", data, ({"started": True}, 200)),
                get_export_status=lambda: _record(calls, "status", None, {"status": "idle"}),
                cancel_export=lambda: _record(calls, "cancel", None, ({"ok": True}, 200)),
                open_export_out_dir=lambda: _record(calls, "open", None, ({"ok": True}, 200)),
            )
        )
    )
    client = app.test_client()

    assert client.post("/api/export/preview", json={"format": "jpeg"}).json == {"ok": True}
    assert client.post("/api/export/start", json={"format": "tiff"}).json == {"started": True}
    assert client.get("/api/export/status").json == {"status": "idle"}
    assert client.post("/api/export/cancel").json == {"ok": True}
    assert client.post("/api/export/open_out_dir").json == {"ok": True}
    assert calls == [
        ("preview", {"format": "jpeg"}),
        ("start", {"format": "tiff"}),
        ("status", None),
        ("cancel", None),
        ("open", None),
    ]


def _record(calls, name, payload, result):
    calls.append((name, payload))
    return result
