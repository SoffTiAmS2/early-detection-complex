"""Web configurator for the early detection complex."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from center.honeypots.catalog import (
    HONEYPOT_CATALOG,
    SERVICE_CATALOG,
    catalog_payload,
    default_settings,
    legacy_honeypot,
    normalize_service,
)

FRONTEND_DIR = ROOT / "center" / "manager" / "frontend"
PROJECT_FILE = ROOT / "config" / "project.json"
GENERATOR = ROOT / "center" / "orchestrator" / "generate.py"
DEPLOY_PLAYBOOK = ROOT / "center" / "ansible" / "deploy_sensor.yml"
JOB_LOCK = threading.Lock()
JOBS: dict[str, dict[str, Any]] = {}

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
        for key in ("name", "host", "role", "mask"):
            if key not in sensor:
                return False, f"sensor is missing {key}"
        if not isinstance(sensor["name"], str) or not SAFE_SENSOR_NAME.fullmatch(sensor["name"]):
            return False, "sensor name must contain only letters, digits, underscore or hyphen"
        for key in ("host", "role"):
            if not isinstance(sensor[key], str) or not sensor[key].strip():
                return False, f"sensor {key} must be a non-empty string"
        honeypots = sensor.get("honeypots")
        if honeypots is None:
            profile = sensor.get("profile")
            if profile not in HONEYPOT_CATALOG:
                return False, f"unsupported profile: {profile}"
            honeypots = [legacy_honeypot(str(profile), sensor.get("services"))]
        if not isinstance(honeypots, list) or not honeypots:
            return False, "sensor honeypots must be a non-empty list"
        used_ports: dict[int, str] = {}
        for honeypot in honeypots:
            if not isinstance(honeypot, dict):
                return False, "sensor honeypot must be an object"
            honeypot_type = honeypot.get("type")
            if honeypot_type not in HONEYPOT_CATALOG:
                return False, f"unsupported honeypot: {honeypot_type}"
            if not isinstance(honeypot.get("services"), list):
                return False, f"{honeypot_type} services must be a list"
            for raw_service in honeypot["services"]:
                if isinstance(raw_service, dict) and "host_port" in raw_service:
                    try:
                        int(raw_service["host_port"])
                    except (TypeError, ValueError):
                        return False, f"host_port must be an integer for {honeypot_type}:{raw_service.get('name')}"
                service = normalize_service(raw_service, str(honeypot_type))
                if not service:
                    return False, f"unsupported service for {honeypot_type}: {raw_service}"
                if not 1 <= service["host_port"] <= 65535:
                    return False, f"invalid host port for {honeypot_type}:{service['name']}"
                if honeypot.get("enabled", True) and service["enabled"]:
                    port = service["host_port"]
                    if port in used_ports:
                        return False, f"port conflict: {honeypot_type}:{service['name']} and {used_ports[port]} both use tcp/{port}"
                    used_ports[port] = f"{honeypot_type}:{service['name']}"
            settings = honeypot.setdefault("settings", {})
            if not isinstance(settings, dict):
                return False, f"{honeypot_type} settings must be an object"
            defaults = default_settings(honeypot_type)
            for key in settings:
                if key not in defaults:
                    return False, f"unsupported setting for {honeypot_type}: {key}"
        if "services" in sensor and not isinstance(sensor["services"], list):
            return False, "sensor services must be a list"
        for service in sensor.get("services", []):
            if not isinstance(service, str):
                return False, "sensor service must be a string"
            if service not in SERVICE_CATALOG:
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


def now_ts() -> float:
    return time.time()


def update_job(job_id: str, **changes: Any) -> None:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if job:
            job.update(changes)


def append_job_output(job_id: str, line: str) -> None:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        output = job.setdefault("output", [])
        output.append(line.rstrip())
        if len(output) > 400:
            del output[:-400]
        if line.startswith("TASK ["):
            task = line.removeprefix("TASK [").split("]", 1)[0]
            job["step"] = task
            job["progress"] = min(int(job.get("progress", 10)) + 6, 92)


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"process"}}


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


def run_sensor_deploy(payload: dict[str, Any], job_id: str | None = None) -> dict[str, Any]:
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
    if job_id:
        update_job(job_id, step="configuration generated", progress=12)

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

        command = [ansible_playbook, "-i", str(inventory), str(DEPLOY_PLAYBOOK), "--extra-vars", f"@{extra_vars}"]
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={**os.environ, "ANSIBLE_HOST_KEY_CHECKING": "False"},
            )
            if job_id:
                update_job(job_id, process=process, step="ansible started", progress=15)

            lines: list[str] = []
            assert process.stdout is not None
            deadline = now_ts() + 1800
            while True:
                if job_id:
                    with JOB_LOCK:
                        cancelled = bool(JOBS.get(job_id, {}).get("cancel_requested"))
                    if cancelled and process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        update_job(job_id, status="cancelled", step="cancelled", finished_at=now_ts(), progress=100)
                        return {"ok": False, "returncode": 130, "stdout": "\n".join(lines), "stderr": "deployment cancelled"}

                line = process.stdout.readline()
                if line:
                    lines.append(line.rstrip())
                    if job_id:
                        append_job_output(job_id, line)
                    continue

                returncode = process.poll()
                if returncode is not None:
                    stdout = "\n".join(lines)
                    return {"ok": returncode == 0, "returncode": returncode, "stdout": stdout, "stderr": ""}

                if now_ts() > deadline:
                    os.killpg(process.pid, signal.SIGTERM)
                    return {"ok": False, "returncode": 124, "stdout": "\n".join(lines), "stderr": "sensor deploy timed out"}
                time.sleep(0.2)
        except Exception as exc:
            return {
                "ok": False,
                "returncode": 1,
                "stdout": "",
                "stderr": str(exc),
            }


def run_deploy_job(job_id: str, deploy_request: dict[str, Any]) -> None:
    update_job(job_id, status="running", step="starting", started_at=now_ts(), progress=5)
    result = run_sensor_deploy(deploy_request, job_id=job_id)
    status = "succeeded" if result["ok"] else "failed"
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if job and job.get("status") == "cancelled":
            return
    update_job(
        job_id,
        status=status,
        step="done" if result["ok"] else "failed",
        finished_at=now_ts(),
        progress=100,
        result=result,
    )


def start_deploy_job(deploy_request: dict[str, Any]) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "type": "deploy-sensor",
        "sensor": deploy_request["sensor"],
        "ssh_host": deploy_request["ssh_host"],
        "status": "queued",
        "step": "queued",
        "progress": 0,
        "created_at": now_ts(),
        "output": [],
        "cancel_requested": False,
    }
    with JOB_LOCK:
        JOBS[job_id] = job
    thread = threading.Thread(target=run_deploy_job, args=(job_id, deploy_request), daemon=True)
    thread.start()
    return public_job(job)


def get_jobs() -> list[dict[str, Any]]:
    with JOB_LOCK:
        return [public_job(job) for job in sorted(JOBS.values(), key=lambda item: item["created_at"], reverse=True)]


def get_job(job_id: str) -> dict[str, Any] | None:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        return public_job(job) if job else None


def cancel_job(job_id: str) -> bool:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return False
        job["cancel_requested"] = True
        process = job.get("process")
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        job["status"] = "cancelled"
        job["step"] = "cancelled"
        job["finished_at"] = now_ts()
        job["progress"] = 100
        return True


def fetch_json(url: str, timeout: int = 5) -> tuple[Any | None, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, str(exc)


def central_status() -> dict[str, Any]:
    project = read_project()
    central_host = project["network"]["central_node"]
    base = os.getenv("CENTRAL_API_BASE", f"http://{central_host}:8080").rstrip("/")
    health, health_error = fetch_json(f"{base}/health")
    sensors, sensors_error = fetch_json(f"{base}/api/sensors")
    return {
        "central_url": base,
        "collector": health,
        "collector_error": health_error,
        "sensors": (sensors or {}).get("sensors", []) if isinstance(sensors, dict) else [],
        "sensors_error": sensors_error,
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
            self._send_json(catalog_payload())
            return
        if parsed.path == "/api/health":
            self._send_json({"status": "ok", "project": str(PROJECT_FILE), "jobs": get_jobs()[:5]})
            return
        if parsed.path == "/api/center/status":
            self._send_json(central_status())
            return
        if parsed.path == "/api/jobs":
            self._send_json({"jobs": get_jobs()})
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = get_job(job_id)
            if not job:
                self._send_json({"error": "job not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(job)
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
            job = start_deploy_job(deploy_request)
            self._send_json({"status": "started", "job": job}, HTTPStatus.ACCEPTED)
            return
        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            job_id = path.split("/")[-2]
            if not cancel_job(job_id):
                self._send_json({"error": "job not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"status": "cancelled", "job": get_job(job_id)})
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
