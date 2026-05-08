#!/usr/bin/env python3
"""Smoke-test the center manager API and live sensor reconfiguration loop."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_json(url: str, timeout: float = 2) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} returned non-object json")
    return payload


def patch_json(url: str, payload: dict[str, Any], timeout: float = 2) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PATCH")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{url} returned non-object json")
    return parsed


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def tcp_sample(port: int) -> str:
    with socket.create_connection(("127.0.0.1", port), timeout=1) as sock:
        sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        return sock.recv(2048).decode("utf-8", errors="replace")


def patch_expect_error(url: str, payload: dict[str, Any]) -> int:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PATCH")
    try:
        urllib.request.urlopen(request, timeout=2)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    raise RuntimeError("request unexpectedly succeeded")


def wait_for(label: str, predicate: Any, timeout: float = 12.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if predicate():
                return
        except Exception as exc:  # noqa: BLE001 - smoke-test waits through startup races.
            last_error = exc
        time.sleep(0.2)
    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(f"timeout waiting for {label}{detail}")


def wait_process_exit(proc: subprocess.Popen[str], name: str) -> None:
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    output = ""
    if proc.stdout:
        output = proc.stdout.read()
    if proc.returncode not in (0, -15):
        raise RuntimeError(f"{name} exited with {proc.returncode}\n{output}")


def main() -> int:
    center_port = free_port()
    honeypot_port = free_port()
    with tempfile.TemporaryDirectory(prefix="edc-e2e-") as tmp:
        tmp_path = Path(tmp)
        policy_path = tmp_path / "policy.json"
        store_path = tmp_path / "events.sqlite3"
        state_dir = tmp_path / "sensor-state"
        policy = {
            "version": 1,
            "site": {"name": "e2e", "central_url": f"http://127.0.0.1:{center_port}"},
            "sensors": [
                {
                    "id": "sensor1",
                    "host": "127.0.0.1",
                    "architecture": "test",
                    "desired_state": {
                        "profile": "test-profile",
                        "persona": {"hostname": "e2e-filesrv"},
                        "modules": [
                            {
                                "id": "opencanary",
                                "enabled": True,
                                "services": [{"id": "http", "host_port": honeypot_port}],
                                "settings": {"http.banner": "Apache/2.4.57", "portscan.synrate": 5},
                            }
                        ],
                    },
                }
            ],
        }
        write_json(policy_path, policy)

        center = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "center" / "server.py"),
                "--host",
                "127.0.0.1",
                "--port",
                str(center_port),
                "--policy",
                str(policy_path),
                "--catalog",
                str(ROOT / "catalog" / "honeypots.json"),
                "--store",
                str(store_path),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_for("center health", lambda: get_json(f"http://127.0.0.1:{center_port}/health")["status"] == "ok")
            sensor = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "sensor" / "agent.py"),
                    "--center",
                    f"http://127.0.0.1:{center_port}",
                    "--sensor-id",
                    "sensor1",
                    "--state-dir",
                    str(state_dir),
                    "--serve",
                    "--interval",
                    "0.5",
                    "--duration",
                    "16",
                ],
                cwd=ROOT / "sensor",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                wait_for("initial listener open", lambda: port_open(honeypot_port))
                wait_for("initial configured http banner", lambda: "Server: Apache/2.4.57" in tcp_sample(honeypot_port))
                bad_status = patch_expect_error(
                    f"http://127.0.0.1:{center_port}/api/sensors/sensor1/modules/opencanary",
                    {"settings": {"portscan.synrate": "wrong"}},
                )
                if bad_status != 400:
                    raise RuntimeError(f"invalid settings returned {bad_status}, expected 400")
                disabled = patch_json(
                    f"http://127.0.0.1:{center_port}/api/sensors/sensor1/modules/opencanary",
                    {"enabled": False},
                )
                if disabled.get("status") != "saved":
                    raise RuntimeError(f"disable patch failed: {disabled}")
                wait_for("listener closed after disable", lambda: not port_open(honeypot_port))
                enabled = patch_json(
                    f"http://127.0.0.1:{center_port}/api/sensors/sensor1/modules/opencanary",
                    {"enabled": True, "settings": {"http.banner": "lighttpd/1.4.76", "portscan.synrate": 7}},
                )
                if enabled.get("status") != "saved":
                    raise RuntimeError(f"enable patch failed: {enabled}")
                wait_for("listener open after enable", lambda: port_open(honeypot_port))
                wait_for("updated configured http banner", lambda: "Server: lighttpd/1.4.76" in tcp_sample(honeypot_port))
                wait_for(
                    "sensor applies latest version",
                    lambda: any(
                        sensor.get("applied_version") == enabled["policy"]["version"]
                        for sensor in get_json(f"http://127.0.0.1:{center_port}/api/sensors")["sensors"]
                    ),
                )
            finally:
                wait_process_exit(sensor, "sensor-agent")
        finally:
            center.terminate()
            wait_process_exit(center, "center")

    print("ok: manager PATCH API and live sensor reconfigure passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
