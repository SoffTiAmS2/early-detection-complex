"""Central HTTP node for collecting and viewing sensor events.

The service intentionally uses only the Python standard library. That keeps the
central node easy to run on Debian/Armbian while the project is still a thesis
prototype.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


DEFAULT_STORE = Path("/data/events.jsonl")
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


def now_ts() -> float:
    """Return a UNIX timestamp used when an event has no client timestamp."""

    return time.time()


def load_events(store: Path, limit: int = 100) -> list[dict[str, Any]]:
    """Read the newest events from a JSON Lines store."""

    if not store.exists():
        return []

    events: list[dict[str, Any]] = []
    with store.open("r", encoding="utf-8") as fh:
        lines = deque(fh, maxlen=limit)
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"type": "parse_error", "raw": line})
    return events


def parse_limit(raw: str) -> int:
    """Parse and clamp a client supplied event limit."""

    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValueError("limit must be an integer") from exc
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    return limit


def append_event(store: Path, event: dict[str, Any]) -> None:
    """Append one normalized event to the JSON Lines store."""

    store.parent.mkdir(parents=True, exist_ok=True)
    event.setdefault("received_at", now_ts())
    with store.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def summarize_sensors(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a compact sensor status map from recent events."""

    sensors: dict[str, dict[str, Any]] = {}
    for event in events:
        sensor = str(event.get("sensor", "unknown"))
        item = sensors.setdefault(
            sensor,
            {
                "sensor": sensor,
                "events": 0,
                "last_type": None,
                "last_seen": None,
                "profile": event.get("profile"),
                "role": event.get("role"),
            },
        )
        item["events"] += 1
        item["last_type"] = event.get("type")
        item["last_seen"] = event.get("received_at") or event.get("timestamp")
        item["profile"] = event.get("profile") or item.get("profile")
        item["role"] = event.get("role") or item.get("role")
    return sensors


def render_dashboard(events: list[dict[str, Any]]) -> bytes:
    """Render a small HTML dashboard for manual thesis demonstrations."""

    sensors = summarize_sensors(events)
    rows = []
    for event in reversed(events[-100:]):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(event.get('received_at', '')))}</td>"
            f"<td>{html.escape(str(event.get('sensor', 'unknown')))}</td>"
            f"<td>{html.escape(str(event.get('type', 'event')))}</td>"
            f"<td>{html.escape(str(event.get('source_ip', '')))}</td>"
            f"<td><pre>{html.escape(json.dumps(event, ensure_ascii=False, sort_keys=True))}</pre></td>"
            "</tr>"
        )

    sensor_items = []
    for sensor in sensors.values():
        sensor_items.append(
            "<li>"
            f"<b>{html.escape(str(sensor['sensor']))}</b>: "
            f"{sensor['events']} events, "
            f"last={html.escape(str(sensor['last_type']))}, "
            f"profile={html.escape(str(sensor.get('profile')))}"
            "</li>"
        )

    body = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Early Detection Complex</title>
  <style>
    body {{ font-family: sans-serif; margin: 24px; background: #f7f7f4; color: #1f2933; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ border: 1px solid #d8dee4; padding: 8px; vertical-align: top; }}
    th {{ background: #eef2f3; text-align: left; }}
    pre {{ white-space: pre-wrap; margin: 0; }}
  </style>
</head>
<body>
  <h1>Early Detection Complex</h1>
  <h2>Сенсоры</h2>
  <ul>{''.join(sensor_items) or '<li>Нет событий</li>'}</ul>
  <h2>Последние события</h2>
  <table>
    <thead><tr><th>received_at</th><th>sensor</th><th>type</th><th>source_ip</th><th>event</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>"""
    return body.encode("utf-8")


class CentralHandler(BaseHTTPRequestHandler):
    """HTTP routes for ingest, status and dashboard."""

    store = DEFAULT_STORE

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, payload: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            limit = parse_limit(params.get("limit", [str(DEFAULT_LIMIT)])[0])
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        events = load_events(self.store, limit=limit)

        if parsed.path == "/health":
            self._send_json({"status": "ok", "events": len(events)})
        elif parsed.path == "/api/events":
            self._send_json({"events": events})
        elif parsed.path == "/api/sensors":
            self._send_json({"sensors": list(summarize_sensors(events).values())})
        elif parsed.path in ("/", "/dashboard"):
            self._send_html(render_dashboard(events))
        else:
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urlparse(self.path).path != "/api/events":
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            event = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return

        if not isinstance(event, dict):
            self._send_json({"error": "event must be an object"}, HTTPStatus.BAD_REQUEST)
            return

        append_event(self.store, event)
        self._send_json({"status": "accepted"}, HTTPStatus.ACCEPTED)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"collector: {self.address_string()} - {fmt % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run central event collector")
    parser.add_argument("--host", default=os.getenv("CENTRAL_BIND", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CENTRAL_PORT", "8080")))
    parser.add_argument("--store", type=Path, default=Path(os.getenv("EVENT_STORE", DEFAULT_STORE)))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    CentralHandler.store = args.store
    server = ThreadingHTTPServer((args.host, args.port), CentralHandler)
    print(f"collector: listening on http://{args.host}:{args.port}, store={args.store}")
    server.serve_forever()


if __name__ == "__main__":
    main()
