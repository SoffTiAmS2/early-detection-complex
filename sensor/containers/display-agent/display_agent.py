"""Display sensor status on console or LCD-compatible backend."""

from __future__ import annotations

import json
import os
import time
import urllib.request


def get_json(url: str, timeout: int = 5) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def format_line(value: str, width: int = 16) -> str:
    return value[:width].ljust(width)


def render_console(line1: str, line2: str) -> None:
    print(f"display-agent: |{format_line(line1)}| |{format_line(line2)}|")


def main() -> None:
    sensor = os.getenv("SENSOR_NAME", "sensor-unknown")
    profile = os.getenv("SENSOR_PROFILE", "fake-services")
    health_url = os.getenv("CENTRAL_HEALTH_URL", "http://central-node:8080/health")
    interval = float(os.getenv("DISPLAY_INTERVAL", "10"))

    while True:
        try:
            status = get_json(health_url)
            line1 = sensor
            line2 = f"{profile} ok:{status.get('events', 0)}"
        except Exception as exc:  # noqa: BLE001 - status display must not crash on network loss.
            line1 = sensor
            line2 = f"central down"
            print(f"display-agent: health check failed: {exc}")

        render_console(line1, line2)
        time.sleep(interval)


if __name__ == "__main__":
    main()

