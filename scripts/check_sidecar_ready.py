#!/usr/bin/env python3
"""Verify the Python sidecar emits ready JSON and serves /api/health."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check InkMoment Python sidecar startup readiness.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to launch app.py.")
    parser.add_argument("--timeout", type=float, default=60.0, help="Seconds to wait for ready JSON.")
    args = parser.parse_args()

    proc = subprocess.Popen(
        [
            args.python,
            "app.py",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--no-browser",
            "--json-ready",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready = _read_ready(proc, args.timeout)
        _check_health(ready["health_url"])
        print(
            json.dumps(
                {
                    "ok": True,
                    "pid": ready.get("pid"),
                    "port": ready.get("port"),
                    "health_url": ready.get("health_url"),
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        _terminate(proc)


def _read_ready(proc: subprocess.Popen[str], timeout: float) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("event") == "ready":
            return payload
    stderr = proc.stderr.read() if proc.stderr else ""
    raise RuntimeError(f"未收到 sidecar ready JSON；returncode={proc.poll()} stderr={stderr[-2000:]}")


def _check_health(health_url: str) -> None:
    with urllib.request.urlopen(health_url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if response.status != 200 or payload.get("status") != "ready":
        raise RuntimeError(f"sidecar health 异常：status={response.status} payload={payload}")


def _terminate(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=8)


if __name__ == "__main__":
    raise SystemExit(main())
