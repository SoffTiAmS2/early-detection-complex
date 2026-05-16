#!/usr/bin/env python3
"""Управляемый sensor-agent распределённого комплекса раннего обнаружения.

Агент получает desired state из центра, пишет локальный applied state,
отправляет status и запускает реальные honeypot-контейнеры через Docker Compose.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

from agent_state import desired_signature, module_plan, now_ts, runtime_plan, sync_payload, write_state
from native_runtime import NativeRuntime
from runtime import DockerRuntime


DEFAULT_STATE_DIR = Path("var") / "sensor"
AGENT_VERSION = "0.4.0"


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


def sync_with_center(base_url: str, sensor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url}/api/sensors/{quote(sensor_id, safe='')}/sync"
    delivered, response = post_json(url, payload)
    if not delivered or not response:
        raise RuntimeError("center sync failed")
    if not response.get("registered"):
        raise RuntimeError(str(response.get("warning") or "sensor is not registered in center policy"))
    desired = response.get("desired_state")
    if not isinstance(desired, dict):
        raise RuntimeError("center sync response does not contain desired_state")
    return desired


def sync_with_retry(
    base_url: str,
    sensor_id: str,
    payload: dict[str, Any],
    retries: int = 30,
    delay: float = 2,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return sync_with_center(base_url, sensor_id, payload)
        except Exception as exc:  # noqa: BLE001 - startup should tolerate center boot order.
            last_error = exc
            print(f"sensor-agent: center sync unavailable, retry {attempt}/{retries}: {exc}", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"center sync unavailable after {retries} retries: {last_error}")


def run_once(center_url: str, sensor_id: str, state_dir: Path) -> dict[str, Any]:
    base_url = center_url.rstrip("/")
    desired = sync_with_retry(base_url, sensor_id, sync_payload(sensor_id, AGENT_VERSION, agent_mode="dry-run"))
    plan = module_plan(desired)
    status = sync_payload(sensor_id, AGENT_VERSION, desired=desired, plan=plan, agent_mode="dry-run")
    sync_with_center(base_url, sensor_id, status)
    state = {
        "sensor_id": sensor_id,
        "agent_version": AGENT_VERSION,
        "updated_at": now_ts(),
        "center_url": base_url,
        "desired": desired,
        "plan": plan,
        "last_sync_payload": status,
    }
    write_state(state_dir / "applied_state.json", state)
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return state


def start_runtime(
    sensor_id: str,
    base_url: str,
    desired: dict[str, Any],
    send_event: Any,
    state_dir: Path,
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]], str]:
    if desired.get("runtime_mode") == "native":
        runtime = NativeRuntime(sensor_id=sensor_id, center_url=base_url, desired=desired, sender=send_event, state_dir=state_dir)
        mode = "native-runtime"
    else:
        runtime = DockerRuntime(sensor_id=sensor_id, center_url=base_url, desired=desired, sender=send_event, state_dir=state_dir)
        mode = "docker-runtime"
    runtime.start()
    active_services = runtime.active_services()
    plan = runtime_plan(module_plan(desired), active_services, runtime.errors)
    return runtime, active_services, plan, mode


def run_service(center_url: str, sensor_id: str, state_dir: Path, interval: float, duration: float = 0) -> None:
    base_url = center_url.rstrip("/")
    event_url = os.environ.get("EDC_LOG_RECEIVER_URL", "").strip() or f"{base_url}/api/events"
    def send_event(event: dict[str, Any]) -> bool:
        delivered, _ = post_json(event_url, event)
        return delivered

    desired = sync_with_retry(base_url, sensor_id, sync_payload(sensor_id, AGENT_VERSION))
    signature = desired_signature(desired)
    runtime, active_services, plan, agent_mode = start_runtime(sensor_id, base_url, desired, send_event, state_dir)
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
            active_services = runtime.active_services()
            plan = runtime_plan(module_plan(desired), active_services, runtime.errors)
            status = sync_payload(
                sensor_id,
                AGENT_VERSION,
                desired=desired,
                plan=plan,
                agent_mode=agent_mode,
                active_services=active_services,
                listener_errors=runtime.errors,
                started_at=started_at,
            )
            try:
                latest_desired = sync_with_center(base_url, sensor_id, status)
                latest_signature = desired_signature(latest_desired)
                if latest_signature != signature:
                    runtime.stop()
                    desired = latest_desired
                    signature = latest_signature
                    runtime, active_services, plan, agent_mode = start_runtime(sensor_id, base_url, desired, send_event, state_dir)
                    plan = runtime_plan(module_plan(desired), active_services, runtime.errors)
                    status = sync_payload(
                        sensor_id,
                        AGENT_VERSION,
                        desired=desired,
                        plan=plan,
                        agent_mode=agent_mode,
                        active_services=active_services,
                        listener_errors=runtime.errors,
                        started_at=started_at,
                    )
            except Exception as exc:  # noqa: BLE001 - keep current runtime while center is unavailable.
                print(f"sensor-agent: center sync failed: {exc}", flush=True)

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
                    "last_sync_payload": status,
                }
            )
            write_state(state_dir / "applied_state.json", state)
            print(
                "sensor-agent: status "
                f"sensor={sensor_id} profile={desired.get('profile')} "
                f"modules={','.join(status['status']['enabled_modules'])} "
                f"active_services={len(active_services)}",
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
            run_once(args.center, args.sensor_id, args.state_dir)
        except Exception as exc:  # noqa: BLE001 - the agent keeps reporting instead of crashing the loop.
            print(f"sensor-agent: loop failed: {exc}", flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
