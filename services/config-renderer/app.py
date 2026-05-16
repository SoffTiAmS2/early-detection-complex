from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from center.core.paths import DEFAULT_CATALOG, DEFAULT_DEVICE_PROFILES
from center.core.profiles import apply_profile, available_profiles
from center.core.utils import load_json


class ConfigRendererHandler(BaseHTTPRequestHandler):
    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_json({"status": "ok", "service": "config-renderer"})
            return
        if self.path == "/profiles":
            catalog = load_json(DEFAULT_CATALOG)
            profiles = load_json(DEFAULT_DEVICE_PROFILES)
            self.send_json({"profiles": list(available_profiles({"sensors": []}, catalog, profiles).values())})
            return
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/render":
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_json({"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(payload, dict):
            self.send_json({"error": "payload must be an object"}, HTTPStatus.BAD_REQUEST)
            return
        profile_id = str(payload.get("profile_id") or payload.get("profile") or "").strip()
        if not profile_id:
            self.send_json({"error": "profile_id is required"}, HTTPStatus.BAD_REQUEST)
            return
        catalog = load_json(DEFAULT_CATALOG)
        policy = {"version": 1, "site": {}, "sensors": []}
        sensor = {
            "id": str(payload.get("sensor_id") or "preview-sensor"),
            "host": payload.get("host", ""),
            "architecture": payload.get("architecture", ""),
            "desired_state": {},
        }
        ok, error = apply_profile(policy, catalog, sensor, profile_id, load_json(DEFAULT_DEVICE_PROFILES))
        if not ok:
            self.send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return
        self.send_json({"sensor_id": sensor["id"], "profile_id": profile_id, "desired_state": sensor["desired_state"]})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"config-renderer: {self.address_string()} - {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8092), ConfigRendererHandler)
    print("config-renderer: listening on 0.0.0.0:8092")
    server.serve_forever()


if __name__ == "__main__":
    main()
