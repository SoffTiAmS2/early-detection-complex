"""Web configurator for the early detection complex."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import shutil
import subprocess
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "manager" / "frontend"
PROJECT_FILE = ROOT / "inventory" / "project.json"
GENERATOR = ROOT / "orchestrator" / "generate.py"
DEPLOY_PLAYBOOK = ROOT / "ansible" / "deploy_sensor.yml"

PROFILES = {
    "opencanary": {
        "title": "OpenCanary-like",
        "role": "dmz",
        "services": ["ssh", "http", "ftp", "smtp"],
        "description": "Мультисервисная приманка для DMZ и внутренних decoy-узлов.",
    },
    "cowrie": {
        "title": "Cowrie-like",
        "role": "office",
        "services": ["ssh", "telnet"],
        "description": "SSH/Telnet профиль для brute force и интерактивных попыток входа.",
    },
    "heralding": {
        "title": "Heralding-like",
        "role": "office",
        "services": ["ssh", "telnet", "ftp", "smtp", "http"],
        "description": "Профиль для сбора попыток аутентификации на нескольких протоколах.",
    },
    "conpot": {
        "title": "Conpot-like",
        "role": "ot-mining",
        "services": ["http", "modbus"],
        "description": "OT/ICS профиль для технологического сегмента предприятия.",
    },
    "dionaea": {
        "title": "Dionaea-like",
        "role": "dmz",
        "services": ["http", "ftp", "mysql"],
        "description": "Профиль для сетевых вредоносных подключений в изолированной зоне.",
    },
    "honeytrap": {
        "title": "Honeytrap-like",
        "role": "custom",
        "services": ["ssh", "http", "ftp", "printer"],
        "description": "Универсальный профиль для набора сервисов-приманок.",
    },
}

SERVICES = {
    "ssh": {"title": "SSH", "port": 2222},
    "telnet": {"title": "Telnet", "port": 2323},
    "http": {"title": "HTTP", "port": 8081},
    "ftp": {"title": "FTP", "port": 2121},
    "smtp": {"title": "SMTP", "port": 2525},
    "mysql": {"title": "MySQL", "port": 33060},
    "modbus": {"title": "Modbus", "port": 1502},
    "printer": {"title": "Printer", "port": 9100},
}

SAFE_SENSOR_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
FRONTEND_ROOT = FRONTEND_DIR.resolve()


def read_project() -> dict[str, Any]:
    if not PROJECT_FILE.exists():
        return {
            "network": {
                "subnet": "192.168.10.0/24",
                "gateway": "192.168.10.1",
                "central_node": "192.168.10.2",
            },
            "sensors": [],
        }
    return json.loads(PROJECT_FILE.read_text(encoding="utf-8"))


def write_project(project: dict[str, Any]) -> None:
    PROJECT_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_FILE.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_project(project: Any) -> tuple[bool, str]:
    if not isinstance(project, dict):
        return False, "project must be an object"
    if not isinstance(project.get("network"), dict):
        return False, "network must be an object"
    for key in ("subnet", "gateway", "central_node"):
        if not isinstance(project["network"].get(key), str) or not project["network"][key].strip():
            return False, f"network.{key} must be a non-empty string"
    if not isinstance(project.get("sensors"), list):
        return False, "sensors must be a list"
    for sensor in project["sensors"]:
        if not isinstance(sensor, dict):
            return False, "sensor must be an object"
        for key in ("name", "host", "role", "profile", "services", "mask"):
            if key not in sensor:
                return False, f"sensor is missing {key}"
        if not isinstance(sensor["name"], str) or not SAFE_SENSOR_NAME.fullmatch(sensor["name"]):
            return False, "sensor name must contain only letters, digits, underscore or hyphen"
        for key in ("host", "role", "profile"):
            if not isinstance(sensor[key], str) or not sensor[key].strip():
                return False, f"sensor {key} must be a non-empty string"
        if sensor["profile"] not in PROFILES:
            return False, f"unsupported profile: {sensor['profile']}"
        if not isinstance(sensor["services"], list):
            return False, "sensor services must be a list"
        for service in sensor["services"]:
            if not isinstance(service, str):
                return False, "sensor service must be a string"
            if service not in SERVICES:
                return False, f"unsupported service: {service}"
        if not isinstance(sensor["mask"], dict):
            return False, "sensor mask must be an object"
    return True, "ok"


def run_generator() -> dict[str, Any]:
    result = subprocess.run(
        ["python3", str(GENERATOR)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def read_json_body(handler: BaseHTTPRequestHandler) -> tuple[Any | None, str | None]:
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        return None, "invalid content length"
    try:
        return json.loads(handler.rfile.read(length).decode("utf-8")), None
    except json.JSONDecodeError:
        return None, "invalid json"


def find_sensor(project: dict[str, Any], name: str) -> dict[str, Any] | None:
    for sensor in project["sensors"]:
        if sensor.get("name") == name:
            return sensor
    return None


def validate_deploy_request(payload: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "deploy request must be an object"
    sensor_name = payload.get("sensor")
    ssh_host = payload.get("ssh_host")
    ssh_user = payload.get("ssh_user")
    if not isinstance(sensor_name, str) or not SAFE_SENSOR_NAME.fullmatch(sensor_name):
        return None, "sensor must be a safe sensor name"
    if not isinstance(ssh_host, str) or not ssh_host.strip():
        return None, "ssh_host must be a non-empty string"
    if not isinstance(ssh_user, str) or not ssh_user.strip():
        return None, "ssh_user must be a non-empty string"
    try:
        ssh_port = int(payload.get("ssh_port", 22))
    except (TypeError, ValueError):
        return None, "ssh_port must be an integer"
    if not 1 <= ssh_port <= 65535:
        return None, "ssh_port must be between 1 and 65535"

    return {
        "sensor": sensor_name,
        "ssh_host": ssh_host.strip(),
        "ssh_user": ssh_user.strip(),
        "ssh_port": ssh_port,
        "ssh_password": payload.get("ssh_password") or "",
        "become_password": payload.get("become_password") or payload.get("ssh_password") or "",
    }, None


def run_sensor_deploy(payload: dict[str, Any]) -> dict[str, Any]:
    if not DEPLOY_PLAYBOOK.exists():
        return {"ok": False, "returncode": 1, "stdout": "", "stderr": f"missing playbook: {DEPLOY_PLAYBOOK}"}
    ansible_playbook = shutil.which("ansible-playbook")
    if not ansible_playbook:
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": "ansible-playbook is not installed on the central node",
        }

    project = read_project()
    valid, message = validate_project(project)
    if not valid:
        return {"ok": False, "returncode": 1, "stdout": "", "stderr": message}
    if not find_sensor(project, payload["sensor"]):
        return {"ok": False, "returncode": 1, "stdout": "", "stderr": f"unknown sensor: {payload['sensor']}"}

    generated = run_generator()
    if not generated["ok"]:
        return generated

    with tempfile.TemporaryDirectory(prefix="edc-ansible-") as tmp:
        tmp_path = Path(tmp)
        inventory = tmp_path / "inventory.ini"
        extra_vars = tmp_path / "vars.json"
        inventory.write_text(
            "[sensors]\n"
            f"{payload['sensor']} ansible_host={payload['ssh_host']} "
            f"ansible_user={payload['ssh_user']} ansible_port={payload['ssh_port']}\n",
            encoding="utf-8",
        )
        vars_payload = {
            "target_sensor": payload["sensor"],
            "project_root": str(ROOT),
            "remote_root": "/opt/early-detection-complex",
        }
        if payload["ssh_password"]:
            vars_payload["ansible_password"] = payload["ssh_password"]
        if payload["become_password"]:
            vars_payload["ansible_become_password"] = payload["become_password"]
        extra_vars.write_text(json.dumps(vars_payload, ensure_ascii=False), encoding="utf-8")
        extra_vars.chmod(0o600)

        try:
            result = subprocess.run(
                [ansible_playbook, "-i", str(inventory), str(DEPLOY_PLAYBOOK), "--extra-vars", f"@{extra_vars}"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=1800,
                env={**os.environ, "ANSIBLE_HOST_KEY_CHECKING": "False"},
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "returncode": 124,
                "stdout": exc.stdout or "",
                "stderr": "sensor deploy timed out",
            }
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


class ManagerHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.is_relative_to(FRONTEND_ROOT):
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        if not resolved.exists() or not resolved.is_file():
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        data = resolved.read_bytes()
        content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/project":
            self._send_json(read_project())
            return
        if parsed.path == "/api/catalog":
            self._send_json({"profiles": PROFILES, "services": SERVICES})
            return
        if parsed.path == "/api/health":
            self._send_json({"status": "ok", "project": str(PROJECT_FILE)})
            return

        relative = "index.html" if parsed.path in ("", "/") else parsed.path.lstrip("/")
        self._send_file(FRONTEND_DIR / relative)

    def do_PUT(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/project":
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        project, error = read_json_body(self)
        if error:
            self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return

        valid, message = validate_project(project)
        if not valid:
            self._send_json({"error": message}, HTTPStatus.BAD_REQUEST)
            return
        write_project(project)
        self._send_json({"status": "saved"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/generate":
            result = run_generator()
            status = HTTPStatus.OK if result["ok"] else HTTPStatus.INTERNAL_SERVER_ERROR
            self._send_json(result, status)
            return
        if path == "/api/deploy-sensor":
            payload, error = read_json_body(self)
            if error:
                self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                return
            deploy_request, error = validate_deploy_request(payload)
            if error:
                self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                return
            result = run_sensor_deploy(deploy_request)
            status = HTTPStatus.OK if result["ok"] else HTTPStatus.INTERNAL_SERVER_ERROR
            self._send_json(result, status)
            return
        else:
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"manager: {self.address_string()} - {fmt % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run web configurator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ManagerHandler)
    print(f"manager: listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
