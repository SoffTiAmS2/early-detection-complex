from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


MANAGER_URL = os.environ.get("MANAGER_API_URL", "http://center:8080").rstrip("/")


class AgentGatewayHandler(BaseHTTPRequestHandler):
    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_json({"status": "ok", "service": "agent-gateway", "manager_api": MANAGER_URL})
            return
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parts = [part for part in self.path.split("/") if part]
        if len(parts) != 3 or parts[0] != "agent" or parts[2] != "sync":
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        sensor_id = quote(parts[1], safe="")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            request = Request(
                f"{MANAGER_URL}/api/sensors/{sensor_id}/sync",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=15) as response:
                payload = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except Exception as exc:
            self.send_json({"error": "manager api unavailable", "detail": str(exc)}, HTTPStatus.BAD_GATEWAY)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"agent-gateway: {self.address_string()} - {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8081), AgentGatewayHandler)
    print("agent-gateway: listening on 0.0.0.0:8081")
    server.serve_forever()


if __name__ == "__main__":
    main()
