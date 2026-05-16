from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from center.core.paths import DEFAULT_STORE
from center.persistence.events import write_event
from center.persistence.honeypot_logs import (
    honeypot_database_stats,
    read_honeypot_events,
    read_raw_honeypot_logs,
    write_honeypot_batch,
)


STORE = Path(DEFAULT_STORE)


class LogReceiverHandler(BaseHTTPRequestHandler):
    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_json({"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(payload, dict):
            self.send_json({"error": "payload must be an object"}, HTTPStatus.BAD_REQUEST)
            return None
        return payload

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_json({"status": "ok", "service": "log-receiver"})
            return
        if self.path.startswith("/logs/events"):
            self.send_json({"events": read_honeypot_events(STORE, 100)})
            return
        if self.path.startswith("/logs/raw"):
            self.send_json({"logs": read_raw_honeypot_logs(STORE, 100)})
            return
        if self.path == "/stats":
            self.send_json(honeypot_database_stats(STORE))
            return
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/logs/raw", "/logs/events", "/logs/batch"}:
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        payload = self.read_json()
        if payload is None:
            return
        items = payload.get("events") or payload.get("logs") or payload.get("items")
        if items is None:
            items = [payload]
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            self.send_json({"error": "events/logs/items must be a list of objects"}, HTTPStatus.BAD_REQUEST)
            return
        result = write_honeypot_batch(STORE, items)
        for item in items:
            write_event(STORE, {**item, "event_type": item.get("event_type", "honeypot.raw_log")})
        self.send_json({"status": "accepted", **result}, HTTPStatus.ACCEPTED)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"log-receiver: {self.address_string()} - {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8091), LogReceiverHandler)
    print("log-receiver: listening on 0.0.0.0:8091")
    server.serve_forever()


if __name__ == "__main__":
    main()
