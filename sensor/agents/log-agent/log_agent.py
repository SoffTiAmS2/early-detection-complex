"""Forward local honeypot events to the central node."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def now_ts() -> float:
    return time.time()


def post_json(url: str, payload: dict[str, Any], timeout: int = 5) -> bool:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"log-agent: send failed: {exc}")
        return False


def enrich_event(event: dict[str, Any]) -> dict[str, Any]:
    event.setdefault("timestamp", now_ts())
    event.setdefault("type", event.get("eventid", "honeypot_event"))
    event["sensor"] = os.getenv("SENSOR_NAME", "sensor-unknown")
    event["role"] = os.getenv("SENSOR_ROLE", "unknown")
    event["profile"] = os.getenv("SENSOR_PROFILE", "cowrie")
    return event


def parse_line(line: str) -> dict[str, Any]:
    try:
        event = json.loads(line)
        if isinstance(event, dict):
            return event
    except json.JSONDecodeError:
        pass
    return {"type": "raw_log", "message": line}


def follow_file(path: Path, central_url: str, poll_interval: float, heartbeat_interval: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(0, os.SEEK_END)
        last_heartbeat = 0.0
        while True:
            if now_ts() - last_heartbeat >= heartbeat_interval:
                send_heartbeat(central_url)
                last_heartbeat = now_ts()

            line = fh.readline()
            if not line:
                time.sleep(poll_interval)
                continue
            event = enrich_event(parse_line(line.strip()))
            last_heartbeat = deliver_event(central_url, event, poll_interval, heartbeat_interval, last_heartbeat)


def send_heartbeat(central_url: str) -> None:
    event = enrich_event({"type": "heartbeat", "status": "online"})
    post_json(central_url, event)


def deliver_event(
    central_url: str,
    event: dict[str, Any],
    poll_interval: float,
    heartbeat_interval: float,
    last_heartbeat: float,
) -> float:
    retry_delay = max(poll_interval, 1.0)
    while not post_json(central_url, event):
        now = now_ts()
        if now - last_heartbeat >= heartbeat_interval:
            send_heartbeat(central_url)
            last_heartbeat = now
        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 30.0)
    return last_heartbeat


def main() -> None:
    central_url = os.getenv("CENTRAL_URL", "http://central-node:8080/api/events")
    log_path = Path(os.getenv("HONEYPOT_LOG_PATH", "/logs/events.jsonl"))
    poll_interval = float(os.getenv("POLL_INTERVAL", "1"))
    heartbeat_interval = float(os.getenv("HEARTBEAT_INTERVAL", "30"))

    print(f"log-agent: forwarding {log_path} to {central_url}")
    follow_file(log_path, central_url, poll_interval, heartbeat_interval)


if __name__ == "__main__":
    main()
