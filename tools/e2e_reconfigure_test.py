#!/usr/bin/env python3
"""Smoke-test the center manager API and Docker runtime materialization."""

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
sys.path.insert(0, str(ROOT / "sensor"))
from runtime import DockerRuntime  # noqa: E402


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


def get_text(url: str, timeout: float = 2) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8")


def post_json(url: str, payload: dict[str, Any], timeout: float = 2) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{url} returned non-object json")
    return parsed


def patch_json(url: str, payload: dict[str, Any], timeout: float = 2) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PATCH")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{url} returned non-object json")
    return parsed


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


def assert_compose_materializes(desired: dict[str, Any], state_dir: Path) -> None:
    runtime = DockerRuntime(
        sensor_id="sensor1",
        center_url="http://127.0.0.1:1",
        desired=desired,
        sender=lambda event: True,
        state_dir=state_dir,
    )
    runtime.runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime.prepare_module_dirs()
    runtime.write_compose()
    compose = runtime.compose_path.read_text(encoding="utf-8")
    expected = ["edc/cowrie:local", "thinkst/opencanary:latest", "2222:2222", "8081:80", "build:"]
    missing = [item for item in expected if item not in compose]
    if missing:
        raise RuntimeError(f"compose missing expected real runtime entries: {missing}\n{compose}")
    forbidden = ["lightweight-listener", "HoneypotTCPServer"]
    present = [item for item in forbidden if item in compose]
    if present:
        raise RuntimeError(f"compose contains listener-runtime leftovers: {present}")


def main() -> int:
    center_port = free_port()
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
                                "services": [{"id": "http", "host_port": 8081}],
                                "settings": {"http.banner": "Apache/2.4.57", "portscan.synrate": 5},
                            },
                            {
                                "id": "cowrie",
                                "enabled": True,
                                "services": [{"id": "ssh", "host_port": 2222}],
                                "settings": {"hostname": "e2e-filesrv"},
                            }
                        ],
                    },
                }
            ],
        }
        write_json(policy_path, policy)
        assert_compose_materializes(policy["sensors"][0]["desired_state"], state_dir)

        center = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "center.main",
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
            synced = post_json(
                f"http://127.0.0.1:{center_port}/api/sensors/sensor1/sync",
                {
                    "sensor_id": "sensor1",
                    "agent_version": "e2e",
                    "facts": {"hostname": "e2e-node", "architecture": "test"},
                    "status": {"state": "online", "mode": "dry-run", "modules": []},
                },
            )
            if not synced.get("registered") or synced.get("desired_state", {}).get("profile") != "test-profile":
                raise RuntimeError(f"sensor sync failed: {synced}")
            sensors = get_json(f"http://127.0.0.1:{center_port}/api/sensors")["sensors"]
            if not any(item.get("sensor_id") == "sensor1" and item.get("status") == "online" for item in sensors):
                raise RuntimeError(f"sensor sync did not update status: {sensors}")
            metrics = get_text(f"http://127.0.0.1:{center_port}/metrics")
            if "edc_sensor_online" not in metrics or "edc_events_window_total" not in metrics:
                raise RuntimeError(f"metrics endpoint missing expected series:\n{metrics}")
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
            enabled = patch_json(
                f"http://127.0.0.1:{center_port}/api/sensors/sensor1/modules/opencanary",
                {"enabled": True, "settings": {"http.banner": "lighttpd/1.4.76", "portscan.synrate": 7}},
            )
            if enabled.get("status") != "saved":
                raise RuntimeError(f"enable patch failed: {enabled}")
            assert_compose_materializes(enabled["policy"]["sensors"][0]["desired_state"], state_dir)
        finally:
            center.terminate()
            wait_process_exit(center, "center")

    print("ok: manager PATCH API and Docker runtime materialization passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
