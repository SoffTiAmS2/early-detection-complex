from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import ROOT
from .policy import bump_policy_version, find_sensor, policy_errors
from .utils import load_json, now_ts, write_json

INSTALL_JOBS: dict[str, dict[str, Any]] = {}

def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def public_center_url(policy: dict[str, Any], headers: Any | None = None) -> str:
    configured = str(policy.get("site", {}).get("central_url") or "").strip()
    if configured:
        return configured.rstrip("/")
    host = headers.get("Host") if headers else "127.0.0.1:8080"
    return f"http://{host}".rstrip("/")


def new_job(sensor_id: str, host: str) -> dict[str, Any]:
    job = {
        "id": uuid.uuid4().hex[:12],
        "sensor_id": sensor_id,
        "host": host,
        "status": "queued",
        "step": "Ожидание запуска",
        "progress": 0,
        "logs": [],
        "started_at": now_ts(),
        "updated_at": now_ts(),
        "cancel_requested": False,
        "process": None,
    }
    INSTALL_JOBS[job["id"]] = job
    return job


def job_log(job: dict[str, Any], message: str, progress: int | None = None, step: str | None = None) -> None:
    job["updated_at"] = now_ts()
    if progress is not None:
        job["progress"] = max(0, min(100, progress))
    if step:
        job["step"] = step
    job.setdefault("logs", []).append(f"{time.strftime('%H:%M:%S')} {message}")
    job["logs"] = job["logs"][-160:]


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"process", "ssh_password"}}


def run_checked(job: dict[str, Any], args: list[str], input_text: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    if job.get("cancel_requested"):
        raise RuntimeError("Установка отменена пользователем")
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    job["process"] = process
    try:
        output, _ = process.communicate(input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate()
        raise RuntimeError(f"Команда превысила таймаут: {' '.join(args[:2])}\n{output[-4000:]}")
    finally:
        job["process"] = None
    if output:
        for line in output.splitlines()[-30:]:
            if line.strip():
                job_log(job, line.strip())
    if process.returncode != 0:
        raise RuntimeError(f"Команда завершилась с кодом {process.returncode}: {' '.join(args[:2])}\n{output[-4000:]}")
    return subprocess.CompletedProcess(args, process.returncode, output, "")


def normalize_remote_dir(remote_dir: str, remote_home: str) -> str:
    value = (remote_dir or "~/edc-mvp").strip() or "~/edc-mvp"
    home = remote_home.rstrip("/") or "/root"
    if value == "~":
        return home
    if value.startswith("~/"):
        return f"{home}/{value[2:]}"
    if value.startswith("/"):
        return value
    return f"{home}/{value}"


def make_sensor_bundle() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="edc-sensor-bundle-"))
    bundle = temp / "sensor.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        for relative in (Path("sensor/agent.py"), Path("sensor/runtime.py"), Path("scripts/run_sensor_runtime.sh")):
            archive.add(ROOT / relative, arcname=str(relative))
    return bundle


def ensure_sensor_policy(policy_path: Path, catalog_path: Path, sensor_id: str, host: str, ssh_user: str, ssh_port: int) -> dict[str, Any]:
    policy = load_json(policy_path)
    catalog = load_json(catalog_path)
    sensor = find_sensor(policy, sensor_id)
    if sensor:
        sensor["host"] = host
        sensor["enrollment"] = {"method": "ssh-bootstrap", "ssh_user": ssh_user, "ssh_port": ssh_port}
    else:
        source = find_sensor(policy, "sensor1") or (policy.get("sensors") or [None])[0]
        if not source:
            raise RuntimeError("В политике нет сенсора-образца для копирования профиля")
        sensor = {
            "id": sensor_id,
            "host": host,
            "architecture": source.get("architecture", ""),
            "enrollment": {"method": "ssh-bootstrap", "ssh_user": ssh_user, "ssh_port": ssh_port},
            "desired_state": json.loads(json.dumps(source.get("desired_state", {}))),
        }
        policy.setdefault("sensors", []).append(sensor)
    errors = policy_errors(policy, catalog)
    if errors:
        raise RuntimeError("; ".join(errors))
    policy = bump_policy_version(policy)
    write_json(policy_path, policy)
    return policy


def remote_install_script(sensor_id: str, center_url: str, ssh_password: str, remote_dir: str) -> str:
    password = shell_quote(ssh_password)
    return f"""set -eu
PASS={password}
REMOTE_DIR={shell_quote(remote_dir)}
SENSOR_ID={shell_quote(sensor_id)}
CENTER_URL={shell_quote(center_url)}
if [ "$(id -u)" = "0" ]; then
  SUDO=""
else
  SUDO="sudo -S"
fi
run_sudo() {{
  if [ -z "$SUDO" ]; then
    "$@"
  else
    printf '%s\\n' "$PASS" | $SUDO "$@"
  fi
}}
cd "$REMOTE_DIR"
if ! command -v python3 >/dev/null 2>&1; then
  run_sudo apt-get update
  run_sudo apt-get install -y python3
fi
if ! command -v docker >/dev/null 2>&1; then
  run_sudo apt-get update
  run_sudo apt-get install -y docker.io docker-compose-v2
fi
run_sudo systemctl enable --now docker
run_sudo docker rm -f $(run_sudo docker ps -aq --filter "label=edc.sensor_id=$SENSOR_ID") 2>/dev/null || true
SERVICE=/etc/systemd/system/edc-sensor.service
cat > /tmp/edc-sensor.service <<EOF
[Unit]
Description=EDC managed honeypot sensor
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
WorkingDirectory=$REMOTE_DIR
ExecStart=/usr/bin/python3 $REMOTE_DIR/sensor/agent.py --center $CENTER_URL --sensor-id $SENSOR_ID --serve --interval 20
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
run_sudo mv /tmp/edc-sensor.service "$SERVICE"
run_sudo systemctl daemon-reload
run_sudo systemctl enable edc-sensor.service
run_sudo systemctl restart edc-sensor.service
run_sudo systemctl --no-pager --full status edc-sensor.service || true
"""


def install_sensor_job(job: dict[str, Any], payload: dict[str, Any], policy_path: Path, catalog_path: Path, headers: Any | None = None) -> None:
    try:
        job["status"] = "running"
        sensor_id = str(payload.get("sensor_id") or "").strip()
        host = str(payload.get("host") or "").strip()
        ssh_user = str(payload.get("ssh_user") or "").strip()
        ssh_password = str(payload.get("ssh_password") or "")
        ssh_port = int(payload.get("ssh_port") or 22)
        remote_dir = str(payload.get("remote_dir") or "~/edc-mvp").strip() or "~/edc-mvp"
        if not sensor_id or not host or not ssh_user or not ssh_password:
            raise RuntimeError("Нужны sensor_id, IP, SSH-логин и SSH-пароль")
        if shutil.which("sshpass") is None:
            raise RuntimeError("На центре не установлен sshpass. Установите пакет sshpass или запускайте центр из Docker-образа проекта.")

        policy = ensure_sensor_policy(policy_path, catalog_path, sensor_id, host, ssh_user, ssh_port)
        center_url = str(payload.get("center_url") or public_center_url(policy, headers)).rstrip("/")
        job_log(job, "Сенсор добавлен/обновлён в политике центра", 10, "Политика центра")

        ssh_base = [
            "sshpass",
            "-p",
            ssh_password,
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            "-p",
            str(ssh_port),
            f"{ssh_user}@{host}",
        ]
        scp_base = [
            "sshpass",
            "-p",
            ssh_password,
            "scp",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            "-P",
            str(ssh_port),
        ]

        job_log(job, "Проверяю SSH-доступ", 18, "SSH")
        run_checked(job, [*ssh_base, "printf connected"], timeout=45)
        home_output = run_checked(job, [*ssh_base, "printf '%s\n' \"$HOME\""], timeout=45).stdout.strip()
        remote_home = home_output.splitlines()[-1].strip() if home_output else ""
        remote_dir = normalize_remote_dir(remote_dir, remote_home)
        job_log(job, f"Рабочий каталог сенсора: {remote_dir}")

        bundle = make_sensor_bundle()
        job_log(job, "Копирую sensor-agent на плату", 32, "Копирование файлов")
        run_checked(job, [*ssh_base, f"mkdir -p {shell_quote(remote_dir)}"], timeout=60)
        run_checked(job, [*scp_base, str(bundle), f"{ssh_user}@{host}:/tmp/edc-sensor.tar.gz"], timeout=180)
        run_checked(job, [*ssh_base, f"tar -xzf /tmp/edc-sensor.tar.gz -C {shell_quote(remote_dir)} && rm -f /tmp/edc-sensor.tar.gz"], timeout=120)

        job_log(job, "Устанавливаю Docker и systemd-сервис сенсора", 58, "Установка runtime")
        run_checked(job, [*ssh_base, "sh -s"], input_text=remote_install_script(sensor_id, center_url, ssh_password, remote_dir), timeout=1200)

        job["status"] = "completed"
        job_log(job, "Готово: sensor-agent запущен, дальше он сам скачает и поднимет honeypot-контейнеры", 100, "Готово")
    except Exception as exc:  # noqa: BLE001 - job errors must be returned to UI.
        job["status"] = "failed" if not job.get("cancel_requested") else "cancelled"
        job_log(job, str(exc), job.get("progress", 0), "Ошибка" if job["status"] == "failed" else "Отменено")
