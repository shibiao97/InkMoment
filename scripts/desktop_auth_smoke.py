#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 8


class DesktopSmokeError(RuntimeError):
    pass


def default_python() -> str:
    candidate = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(candidate)


@dataclass
class HttpClient:
    base_url: str
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    origin: str = ""

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        token: str = "",
        admin_token: str = "",
        admin_session_token: str = "",
        expected_status: int = 200,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if self.origin:
            headers["Origin"] = self.origin
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if admin_session_token:
            headers["Authorization"] = f"Bearer {admin_session_token}"
        elif admin_token:
            headers["X-Admin-Token"] = admin_token

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = _read_json(response)
                status = response.status
        except urllib.error.HTTPError as exc:
            payload = _read_json(exc)
            status = exc.code
        except (urllib.error.URLError, TimeoutError) as exc:
            raise DesktopSmokeError(f"{method} {self.base_url}{path} failed: {exc}") from exc

        if status != expected_status:
            raise DesktopSmokeError(
                f"{method} {self.base_url}{path} expected HTTP {expected_status}, got {status}: {payload}"
            )
        return payload


def _read_json(response) -> dict[str, Any]:
    raw = response.read().decode("utf-8", errors="replace")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DesktopSmokeError(f"response is not JSON: {raw[:200]}") from exc
    if not isinstance(payload, dict):
        raise DesktopSmokeError(f"response JSON is not an object: {payload!r}")
    return payload


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise DesktopSmokeError(message)


class ManagedSidecar:
    def __init__(self, args: argparse.Namespace, state_dir: str) -> None:
        self.args = args
        self.state_dir = state_dir
        self.process: subprocess.Popen[str] | None = None
        self.url = args.sidecar_url.rstrip("/") if args.sidecar_url else ""

    def __enter__(self) -> str:
        if self.url:
            return self.url

        env = os.environ.copy()
        env["INKMOMENT_AUTH_SERVER_URL"] = self.args.auth_base_url.rstrip("/")
        env["INKMOMENT_DEVICE_ID"] = self.args.device_id
        env["INKMOMENT_STATE_DB"] = str(Path(self.state_dir) / "desktop-smoke-state.sqlite3")
        env.setdefault("INKMOMENT_DEV_ORIGINS", "http://localhost")

        command = self._sidecar_command()
        self.process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert self.process.stdout is not None
        deadline = time.time() + self.args.startup_timeout
        captured: list[str] = []
        while time.time() < deadline:
            line = self.process.stdout.readline()
            if not line:
                if self.process.poll() is not None:
                    raise DesktopSmokeError(
                        f"sidecar exited before ready with code {self.process.returncode}: {''.join(captured)}"
                    )
                continue
            captured.append(line)
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("event") == "ready" and payload.get("url"):
                health_url = str(payload.get("health_url") or "")
                if health_url.endswith("/api/health"):
                    self.url = health_url[: -len("/api/health")].rstrip("/")
                else:
                    self.url = str(payload["url"]).rstrip("/")
                return self.url
        raise DesktopSmokeError(f"sidecar did not become ready: {''.join(captured[-20:])}")

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        if self.process.stdout is not None:
            self.process.stdout.close()

    def _sidecar_command(self) -> list[str]:
        if self.args.sidecar_binary:
            return [
                self.args.sidecar_binary,
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--no-browser",
                "--json-ready",
            ]
        return [
            self.args.python,
            str(ROOT / "app.py"),
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--no-browser",
            "--json-ready",
        ]


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    auth_client = HttpClient(args.auth_base_url.rstrip("/"), timeout=args.timeout)
    admin_session_token = _resolve_admin_session_token(auth_client, args)
    unique = args.unique_suffix or str(int(time.time()))
    email = args.email or f"desktop-smoke+{unique}@example.invalid"
    cdk_code = args.cdk_code or f"DESKTOP-SMOKE-{unique}"

    print(f"[1/9] provision remote CDK {cdk_code}")
    auth_client.request(
        "POST",
        "/admin/cdks",
        {"code": cdk_code, "duration_days": args.duration_days},
        admin_token=args.admin_token if not admin_session_token else "",
        admin_session_token=admin_session_token,
        expected_status=201,
    )

    with tempfile.TemporaryDirectory() as state_dir, ManagedSidecar(args, state_dir) as sidecar_url:
        sidecar = HttpClient(sidecar_url, timeout=args.timeout, origin=sidecar_url)
        print(f"[2/9] sidecar health {sidecar_url}/api/health")
        health = sidecar.request("GET", "/api/health")
        _assert(health.get("ok") is True, f"sidecar health not ok: {health}")

        print("[3/9] core API rejected before login")
        before_login = sidecar.request("GET", "/api/status", expected_status=401)
        _assert(before_login.get("code") == "unauthenticated", f"unexpected pre-login response: {before_login}")

        print(f"[4/9] register through sidecar {email}")
        registered = sidecar.request(
            "POST",
            "/api/auth/register",
            {"email": email, "password": args.password, "display_name": "Desktop Smoke"},
        )
        _assert(registered.get("authenticated") is True, f"not authenticated: {registered}")
        _assert(registered.get("authorized") is False, f"unexpected authorized state: {registered}")
        _assert(registered.get("reason") == "not_activated", f"unexpected reason: {registered}")

        print("[5/9] core API rejected before CDK activation")
        before_activation = sidecar.request("GET", "/api/status", expected_status=403)
        _assert(
            before_activation.get("code") == "not_activated",
            f"unexpected pre-activation response: {before_activation}",
        )

        print("[6/9] redeem CDK through sidecar")
        redeemed = sidecar.request("POST", "/api/auth/redeem", {"code": cdk_code})
        _assert(redeemed.get("authorized") is True, f"redeem did not authorize: {redeemed}")
        _assert(redeemed.get("reason") == "active", f"unexpected redeem reason: {redeemed}")

        print("[7/9] core API allowed after activation")
        allowed = sidecar.request("GET", "/api/status")
        _assert("ready" in allowed, f"unexpected core status response: {allowed}")

        print("[8/9] revoke remote session")
        quoted_email = urllib.parse.quote(email, safe="")
        revoked = auth_client.request(
            "POST",
            f"/admin/users/{quoted_email}/sessions/revoke",
            {"confirm_action": "CONFIRM"},
            admin_token=args.admin_token if not admin_session_token else "",
            admin_session_token=admin_session_token,
        )
        _assert(revoked.get("revoked", 0) >= 1, f"session was not revoked: {revoked}")

        print("[9/9] sidecar force refresh clears auth and blocks core API")
        forced = sidecar.request("GET", "/api/auth/status?force=1", expected_status=401)
        _assert(forced.get("code") == "unauthenticated", f"unexpected forced refresh response: {forced}")
        blocked = sidecar.request("GET", "/api/status", expected_status=401)
        _assert(blocked.get("code") == "unauthenticated", f"unexpected post-revoke core response: {blocked}")

    return {
        "ok": True,
        "auth_base_url": args.auth_base_url.rstrip("/"),
        "email": email,
        "cdk_code": cdk_code,
    }


def _resolve_admin_session_token(client: HttpClient, args: argparse.Namespace) -> str:
    if args.admin_session_token:
        return args.admin_session_token
    if args.admin_username or args.admin_password:
        if not args.admin_username or not args.admin_password:
            raise DesktopSmokeError("--admin-username 和 --admin-password 必须同时提供")
        payload = client.request(
            "POST",
            "/admin/login",
            {"username": args.admin_username, "password": args.admin_password},
        )
        token = str(payload.get("token") or "")
        if not token:
            raise DesktopSmokeError("admin login response missing token")
        return token
    if args.admin_token:
        return ""
    raise DesktopSmokeError("需要提供 --admin-session-token，或 --admin-username/--admin-password")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the desktop sidecar authorization flow against a remote auth server.",
    )
    parser.add_argument("--auth-base-url", required=True, help="Authorization server URL")
    parser.add_argument("--admin-token", default="", help="Bootstrap token fallback, only works before the first admin exists")
    parser.add_argument("--admin-session-token", default="", help="Existing admin session token")
    parser.add_argument("--admin-username", default="", help="Admin username used to log in before management API calls")
    parser.add_argument("--admin-password", default="", help="Admin password used with --admin-username")
    parser.add_argument("--sidecar-url", default="", help="Already-running sidecar URL, e.g. http://127.0.0.1:5057")
    parser.add_argument("--sidecar-binary", default="", help="Packaged sidecar binary path to launch")
    parser.add_argument("--python", default=default_python(), help="Python executable for app.py")
    parser.add_argument("--email", default="", help="Optional smoke account email")
    parser.add_argument("--password", default="desktop-smoke-password123", help="Smoke account password")
    parser.add_argument("--cdk-code", default="", help="Optional smoke CDK code")
    parser.add_argument("--duration-days", type=int, default=1, help="Smoke CDK duration")
    parser.add_argument("--device-id", default="desktop-smoke-device", help="Device id exposed to sidecar")
    parser.add_argument("--unique-suffix", default="", help="Optional deterministic suffix for tests")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds")
    parser.add_argument("--startup-timeout", type=int, default=30, help="Sidecar startup timeout in seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        summary = run_smoke(args)
    except DesktopSmokeError as exc:
        print(f"DESKTOP AUTH SMOKE FAILED: {exc}", file=sys.stderr)
        return 1
    print("DESKTOP AUTH SMOKE OK")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
