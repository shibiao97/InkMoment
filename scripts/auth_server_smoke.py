#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 8


class SmokeError(RuntimeError):
    pass


@dataclass
class SmokeClient:
    base_url: str
    admin_token: str = ""
    admin_session_token: str = ""
    timeout: int = DEFAULT_TIMEOUT_SECONDS

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        token: str = "",
        admin: bool = False,
        device_fingerprint: str = "",
        expected_status: int = 200,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if admin:
            if self.admin_session_token:
                headers["Authorization"] = f"Bearer {self.admin_session_token}"
            elif self.admin_token:
                headers["X-Admin-Token"] = self.admin_token
        if device_fingerprint:
            headers["X-Device-Fingerprint"] = device_fingerprint

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
            raise SmokeError(f"{method} {path} failed: {exc}") from exc

        if status != expected_status:
            raise SmokeError(
                f"{method} {path} expected HTTP {expected_status}, got {status}: {payload}"
            )
        return payload


def _read_json(response) -> dict[str, Any]:
    raw = response.read().decode("utf-8", errors="replace")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SmokeError(f"response is not JSON: {raw[:200]}") from exc
    if not isinstance(payload, dict):
        raise SmokeError(f"response JSON is not an object: {payload!r}")
    return payload


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def _assert_fields(payload: dict[str, Any], fields: set[str], context: str) -> None:
    missing = sorted(fields - set(payload.keys()))
    if missing:
        raise SmokeError(f"{context} missing fields: {', '.join(missing)}")


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    client = SmokeClient(
        base_url=args.base_url.rstrip("/"),
        admin_token=args.admin_token,
        admin_session_token=args.admin_session_token,
        timeout=args.timeout,
    )
    _ensure_admin_session(client, args)
    unique = args.unique_suffix or str(int(time.time()))
    email = args.email or f"smoke+{unique}@example.invalid"
    password = args.password
    cdk_code = (args.cdk_code or f"SMOKE-{unique}").strip().upper()
    device_a = {
        "fingerprint": f"smoke-device-a-{unique}",
        "name": "Smoke Device A",
        "os": "smoke-os",
        "arch": "smoke-arch",
        "app_version": args.app_version,
    }
    device_b = {
        "fingerprint": f"smoke-device-b-{unique}",
        "name": "Smoke Device B",
        "os": "smoke-os",
        "arch": "smoke-arch",
        "app_version": args.app_version,
    }

    print(f"[1/8] health {client.base_url}/health")
    health = client.request("GET", "/health")
    _assert(health.get("ok") is True, f"health response not ok: {health}")

    print(f"[2/8] create CDK {cdk_code}")
    cdk = client.request(
        "POST",
        "/admin/cdks",
        {"code": cdk_code, "duration_days": args.duration_days},
        admin=True,
        expected_status=201,
    )
    _assert(cdk.get("code") == cdk_code, f"unexpected CDK response: {cdk}")

    print(f"[3/8] register {email}")
    registered = client.request(
        "POST",
        "/auth/register",
        {
            "email": email,
            "password": password,
            "display_name": "Smoke User",
            "device": device_a,
        },
        expected_status=201,
    )
    _assert_auth_payload(registered, expect_token=True)
    token = str(registered["token"])
    _assert(registered["license"]["reason"] == "not_activated", f"unexpected license: {registered['license']}")

    print("[4/8] status before activation")
    status = client.request(
        "GET",
        "/auth/status",
        token=token,
        device_fingerprint=device_a["fingerprint"],
    )
    _assert_auth_payload(status, expect_token=False)
    _assert(status["license"]["reason"] == "not_activated", f"unexpected status: {status['license']}")

    print("[5/8] redeem CDK")
    redeemed = client.request(
        "POST",
        "/auth/redeem",
        {"code": cdk_code},
        token=token,
        device_fingerprint=device_a["fingerprint"],
    )
    _assert_auth_payload(redeemed, expect_token=False)
    _assert(redeemed["license"]["authorized"] is True, f"redeem did not authorize: {redeemed['license']}")

    print("[6/8] reject login from a different device")
    mismatch = client.request(
        "POST",
        "/auth/login",
        {"email": email, "password": password, "device": device_b},
        expected_status=403,
    )
    _assert(mismatch.get("code") == "device_mismatch", f"unexpected mismatch response: {mismatch}")

    print("[7/8] unbind device with penalty")
    unbound = client.request(
        "POST",
        "/auth/device/unbind",
        {"confirm_penalty": True, "reason": "deployment smoke test"},
        token=token,
        device_fingerprint=device_a["fingerprint"],
    )
    _assert_auth_payload(unbound, expect_token=False)
    _assert(unbound.get("penalty_days") == 3, f"unexpected unbind response: {unbound}")
    _assert(unbound["device"]["bound"] is False, f"device still bound: {unbound['device']}")

    print("[8/8] login from the replacement device")
    replacement_login = client.request(
        "POST",
        "/auth/login",
        {"email": email, "password": password, "device": device_b},
    )
    _assert_auth_payload(replacement_login, expect_token=True)
    replacement_token = str(replacement_login["token"])
    client.request("POST", "/auth/logout", {}, token=replacement_token)

    return {
        "ok": True,
        "base_url": client.base_url,
        "email": email,
        "cdk_code": cdk_code,
        "device_a": device_a["fingerprint"],
        "device_b": device_b["fingerprint"],
    }


def _ensure_admin_session(client: SmokeClient, args: argparse.Namespace) -> None:
    if client.admin_session_token:
        return
    if args.admin_username or args.admin_password:
        if not args.admin_username or not args.admin_password:
            raise SmokeError("--admin-username 和 --admin-password 必须同时提供")
        payload = client.request(
            "POST",
            "/admin/login",
            {"username": args.admin_username, "password": args.admin_password},
        )
        token = str(payload.get("token") or "")
        if not token:
            raise SmokeError("admin login response missing token")
        client.admin_session_token = token
        return
    if client.admin_token:
        return
    raise SmokeError("需要提供 --admin-session-token，或 --admin-username/--admin-password")


def _assert_auth_payload(payload: dict[str, Any], *, expect_token: bool) -> None:
    _assert_fields(
        payload,
        {"account", "license", "device", "limits", "plan", "latest_session"},
        "auth payload",
    )
    if expect_token:
        _assert(bool(payload.get("token")), "auth payload missing token")
    else:
        _assert("token" not in payload, "auth payload unexpectedly returned token")
    _assert_fields(payload["account"], {"id", "email", "status", "device", "limits"}, "account")
    _assert_fields(payload["license"], {"authorized", "reason", "server_time", "expires_at"}, "license")
    _assert_fields(payload["device"], {"bound", "fingerprint", "matches_current"}, "device")
    _assert_fields(payload["limits"], {"max_bound_devices", "unbind_penalty_days", "can_unbind"}, "limits")
    _assert_fields(payload["plan"], {"name", "source", "expires_at", "status"}, "plan")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a production-like smoke test against a deployed InkMoment auth server.",
    )
    parser.add_argument("--base-url", required=True, help="Authorization server URL, e.g. https://auth.example.com")
    parser.add_argument("--admin-token", default="", help="Bootstrap token fallback, only works before the first admin exists")
    parser.add_argument("--admin-session-token", default="", help="Existing admin session token")
    parser.add_argument("--admin-username", default="", help="Admin username used to log in before management API calls")
    parser.add_argument("--admin-password", default="", help="Admin password used with --admin-username")
    parser.add_argument("--email", default="", help="Optional smoke account email. Defaults to smoke+<timestamp>@example.invalid")
    parser.add_argument("--password", default="smoke-password123", help="Smoke account password")
    parser.add_argument("--cdk-code", default="", help="Optional smoke CDK code. Defaults to SMOKE-<timestamp>")
    parser.add_argument("--duration-days", type=int, default=1, help="Smoke CDK duration in days")
    parser.add_argument("--app-version", default="smoke", help="Device app_version field")
    parser.add_argument("--unique-suffix", default="", help="Optional deterministic suffix for tests")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        summary = run_smoke(args)
    except SmokeError as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 1
    print("SMOKE OK")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
