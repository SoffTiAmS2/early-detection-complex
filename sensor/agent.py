#!/usr/bin/env python3
"""Управляемый sensor-agent распределённого комплекса раннего обнаружения.

Агент получает desired state из центра, пишет локальный applied state,
отправляет status и запускает реальные honeypot-контейнеры через Docker Compose.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agent_state import desired_signature, enroll_event, module_plan, now_ts, runtime_plan, status_event, write_state
from native_runtime import NativeRuntime
from runtime import DockerRuntime
from runtime_helpers import ARM32_ARCHES, sensor_architecture


DEFAULT_STATE_DIR = Path("var") / "sensor"
AGENT_VERSION = "0.4.0"


def get_json(url: str, timeout: int = 10) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("center response must be an object")
    return payload


def post_json(url: str, payload: dict[str, Any], timeout: int = 10) -> tuple[bool, dict[str, Any] | None]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body) if body else None
            return 200 <= response.status < 300, parsed if isinstance(parsed, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"sensor-agent: post failed: {exc}", flush=True)
        return False, None


def run_once(center_url: str, sensor_id: str, state_dir: Path, enroll: bool = True) -> dict[str, Any]:
    base_url = center_url.rstrip("/")
    enroll_url = f"{base_url}/api/enroll"
    desired_url = f"{base_url}/api/sensors/{sensor_id}/desired-state"
    event_url = f"{base_url}/api/events"
    enrollment_delivered = False
    enrollment_response = None
    if enroll:
        enrollment_delivered, enrollment_response = post_json(enroll_url, enroll_event(sensor_id, AGENT_VERSION))

    desired = get_json(desired_url)
    plan = module_plan(desired)
    state = {
        "sensor_id": sensor_id,
        "agent_version": AGENT_VERSION,
        "updated_at": now_ts(),
        "center_url": base_url,
        "enrollment_delivered": enrollment_delivered,
        "enrollment_response": enrollment_response,
        "desired": desired,
        "plan": plan,
    }
    write_state(state_dir / "applied_state.json", state)
    event = status_event(sensor_id, desired, plan, agent_mode="dry-run", agent_version=AGENT_VERSION)
    delivered, status_response = post_json(event_url, event)
    state["last_status_delivered"] = delivered
    state["last_status_response"] = status_response
    write_state(state_dir / "applied_state.json", state)
    print(json.dumps(event, ensure_ascii=False, sort_keys=True))
    return state


def fetch_desired_with_retry(base_url: str, sensor_id: str, retries: int = 30, delay: float = 2) -> dict[str, Any]:
    desired_url = f"{base_url}/api/sensors/{sensor_id}/desired-state"
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return get_json(desired_url)
        except Exception as exc:  # noqa: BLE001 - startup should tolerate center boot order.
            last_error = exc
            print(f"sensor-agent: desired-state unavailable, retry {attempt}/{retries}: {exc}", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"desired-state unavailable after {retries} retries: {last_error}")


def start_docker_runtime(
    sensor_id: str,
    base_url: str,
    desired: dict[str, Any],
    send_event: Any,
    state_dir: Path,
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]], str]:
    architecture = str(desired.get("architecture") or sensor_architecture())
    if architecture in ARM32_ARCHES:
        runtime = NativeRuntime(sensor_id=sensor_id, center_url=base_url, desired=desired, sender=send_event, state_dir=state_dir)
        mode = "native-runtime"
    else:
        runtime = DockerRuntime(sensor_id=sensor_id, center_url=base_url, desired=desired, sender=send_event, state_dir=state_dir)
        mode = "docker-runtime"
    runtime.start()
    active_services = runtime.active_services()
    plan = runtime_plan(module_plan(desired), active_services, runtime.errors)
    send_event(
        {
            "event_type": f"sensor.{mode}.started",
            "timestamp": now_ts(),
            "sensor_id": sensor_id,
            "agent_version": AGENT_VERSION,
            "applied_version": desired.get("version"),
            "agent_mode": mode,
            "active_services": active_services,
            "listener_errors": runtime.errors,
        }
    )
    return runtime, active_services, plan, mode


def run_service(center_url: str, sensor_id: str, state_dir: Path, interval: float, duration: float = 0) -> None:
    base_url = center_url.rstrip("/")
    enroll_url = f"{base_url}/api/enroll"
    event_url = f"{base_url}/api/events"
    while True:
        delivered, _ = post_json(enroll_url, enroll_event(sensor_id, AGENT_VERSION))
        if delivered:
            break
        print("sensor-agent: enrollment failed, retrying", flush=True)
        time.sleep(2)
    def send_event(event: dict[str, Any]) -> bool:
        delivered, _ = post_json(event_url, event)
        return delivered

    desired = fetch_desired_with_retry(base_url, sensor_id)
    signature = desired_signature(desired)
    runtime, active_services, plan, agent_mode = start_docker_runtime(sensor_id, base_url, desired, send_event, state_dir)
    started_at = now_ts()
    state = {
        "sensor_id": sensor_id,
        "agent_version": AGENT_VERSION,
        "updated_at": now_ts(),
        "started_at": started_at,
        "center_url": base_url,
        "desired": desired,
        "desired_signature": signature,
        "plan": plan,
        "active_services": active_services,
        "active_service_count": len(active_services),
        "listener_errors": runtime.errors,
        "agent_mode": agent_mode,
    }
    write_state(state_dir / "applied_state.json", state)

    try:
        while True:
            try:
                latest_desired = get_json(f"{base_url}/api/sensors/{sensor_id}/desired-state")
                latest_signature = desired_signature(latest_desired)
                if latest_signature != signature:
                    send_event(
                        {
                            "event_type": "sensor.runtime.reconfigure",
                            "timestamp": now_ts(),
                            "sensor_id": sensor_id,
                            "agent_version": AGENT_VERSION,
                            "old_version": desired.get("version"),
                            "new_version": latest_desired.get("version"),
                        }
                    )
                    runtime.stop()
                    desired = latest_desired
                    signature = latest_signature
                    runtime, active_services, plan, agent_mode = start_docker_runtime(sensor_id, base_url, desired, send_event, state_dir)
            except Exception as exc:  # noqa: BLE001 - keep current runtime while center is unavailable.
                print(f"sensor-agent: desired-state refresh failed: {exc}", flush=True)

            active_services = runtime.active_services()
            plan = runtime_plan(module_plan(desired), active_services, runtime.errors)
            event = status_event(
                sensor_id,
                desired,
                plan,
                agent_mode=agent_mode,
                agent_version=AGENT_VERSION,
                active_services=active_services,
                listener_errors=runtime.errors,
            )
            delivered, response = post_json(event_url, event)
            state.update(
                {
                    "updated_at": now_ts(),
                    "desired": desired,
                    "desired_signature": signature,
                    "plan": plan,
                    "active_services": active_services,
                    "active_service_count": len(active_services),
                    "uptime_seconds": round(now_ts() - started_at, 1),
                    "listener_errors": runtime.errors,
                    "agent_mode": agent_mode,
                    "last_status_delivered": delivered,
                    "last_status_response": response,
                }
            )
            write_state(state_dir / "applied_state.json", state)
            print(
                "sensor-agent: status "
                f"sensor={sensor_id} profile={desired.get('profile')} "
                f"modules={','.join(event['enabled_modules'])} "
                f"active_services={len(active_services)} delivered={delivered}",
                flush=True,
            )
            if duration > 0 and now_ts() - started_at >= duration:
                return
            time.sleep(interval)
    finally:
        runtime.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EDC sensor-agent")
    parser.add_argument("--center", default="http://127.0.0.1:8080")
    parser.add_argument("--sensor-id", default="sensor1")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--duration", type=float, default=0, help="Runtime duration in seconds; 0 means forever")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--serve", action="store_true", help="Run real honeypot containers from desired state")
    parser.add_argument("--no-enroll", action="store_true", help="Skip POST /api/enroll before polling desired state")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.serve:
        try:
            run_service(args.center, args.sensor_id, args.state_dir, args.interval, duration=args.duration)
        except KeyboardInterrupt:
            print("sensor-agent: stopped", flush=True)
        return
    while True:
        try:
            run_once(args.center, args.sensor_id, args.state_dir, enroll=not args.no_enroll)
        except Exception as exc:  # noqa: BLE001 - MVP agent keeps reporting instead of crashing the loop.
            print(f"sensor-agent: loop failed: {exc}", flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
