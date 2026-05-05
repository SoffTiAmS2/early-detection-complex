#!/usr/bin/env python3
"""Minimal EDC sensor-agent MVP.

The agent polls desired state from the center, writes local applied state and
reports status. Module execution is intentionally dry-run for this MVP.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_STATE_DIR = Path("var") / "sensor"


def now_ts() -> float:
    return time.time()


def get_json(url: str, timeout: int = 10) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("center response must be an object")
    return payload


def post_json(url: str, payload: dict[str, Any], timeout: int = 10) -> bool:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"sensor-agent: post failed: {exc}", flush=True)
        return False


def module_plan(desired: dict[str, Any]) -> list[dict[str, Any]]:
    plan = []
    for module in desired.get("modules", []):
        enabled = module.get("enabled", True) is not False
        services = []
        for service in module.get("services", []):
            services.append(
                {
                    "id": service.get("id"),
                    "protocol": service.get("protocol", "tcp"),
                    "host_port": service.get("host_port"),
                    "container_port": service.get("container_port", service.get("host_port")),
                    "state": "planned" if enabled else "disabled",
                }
            )
        plan.append(
            {
                "id": module.get("id"),
                "title": module.get("title"),
                "enabled": enabled,
                "status": "planned" if enabled else "disabled",
                "runtime": module.get("runtime"),
                "resource_class": module.get("resource_class"),
                "services": services,
            }
        )
    return plan


def write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def status_event(sensor_id: str, desired: dict[str, Any], plan: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "event_type": "sensor.status",
        "timestamp": now_ts(),
        "sensor_id": sensor_id,
        "status": "online",
        "agent_mode": "dry-run",
        "applied_version": desired.get("version"),
        "profile": desired.get("profile"),
        "persona": desired.get("persona", {}),
        "modules": plan,
    }


def run_once(center_url: str, sensor_id: str, state_dir: Path) -> dict[str, Any]:
    desired_url = f"{center_url.rstrip('/')}/api/sensors/{sensor_id}/desired-state"
    event_url = f"{center_url.rstrip('/')}/api/events"
    desired = get_json(desired_url)
    plan = module_plan(desired)
    state = {
        "sensor_id": sensor_id,
        "updated_at": now_ts(),
        "desired": desired,
        "plan": plan,
    }
    write_state(state_dir / "applied_state.json", state)
    event = status_event(sensor_id, desired, plan)
    delivered = post_json(event_url, event)
    state["last_status_delivered"] = delivered
    write_state(state_dir / "applied_state.json", state)
    print(json.dumps(event, ensure_ascii=False, sort_keys=True))
    return state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EDC sensor-agent MVP")
    parser.add_argument("--center", default="http://127.0.0.1:8080")
    parser.add_argument("--sensor-id", default="sensor1")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    while True:
        try:
            run_once(args.center, args.sensor_id, args.state_dir)
        except Exception as exc:  # noqa: BLE001 - MVP agent keeps reporting instead of crashing the loop.
            print(f"sensor-agent: loop failed: {exc}", flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
