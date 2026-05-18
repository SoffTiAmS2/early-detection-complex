from __future__ import annotations

import os
import shlex
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from center.core.paths import ROOT
from center.core.utils import now_ts


_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()


def list_bootstrap_jobs() -> list[dict[str, Any]]:
    with _LOCK:
        return sorted((dict(job) for job in _JOBS.values()), key=lambda item: item.get("created_at", 0), reverse=True)


def latest_bootstrap_job(sensor_id: str) -> dict[str, Any] | None:
    for job in list_bootstrap_jobs():
        if job.get("sensor_id") == sensor_id:
            return job
    return None


def start_sensor_bootstrap(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "type": "sensor-bootstrap",
        "sensor_id": str(payload.get("sensor_id") or ""),
        "host": str(payload.get("host") or ""),
        "ssh_user": str(payload.get("ssh_user") or ""),
        "ssh_port": int(payload.get("ssh_port") or 22),
        "remote_dir": str(payload.get("remote_dir") or "~/early-detection-complex"),
        "status": "queued",
        "stage": "queued",
        "progress": 5,
        "message": "Задание установки поставлено в очередь.",
        "logs": [],
        "created_at": now_ts(),
        "updated_at": now_ts(),
        "finished_at": None,
    }
    with _LOCK:
        _JOBS[job_id] = job
    thread = threading.Thread(target=_run_bootstrap, args=(job_id, dict(payload)), daemon=True)
    thread.start()
    return dict(job)


def _update(job_id: str, *, status: str | None = None, stage: str | None = None, progress: int | None = None, message: str | None = None, log: str | None = None) -> None:
    with _LOCK:
        job = _JOBS[job_id]
        if status is not None:
            job["status"] = status
        if stage is not None:
            job["stage"] = stage
        if progress is not None:
            job["progress"] = max(0, min(100, int(progress)))
        if message is not None:
            job["message"] = message
        if log:
            logs = job.setdefault("logs", [])
            logs.append({"at": now_ts(), "line": log[-4000:]})
            del logs[:-60]
        job["updated_at"] = now_ts()
        if status in {"completed", "failed"}:
            job["finished_at"] = now_ts()


def _run_bootstrap(job_id: str, payload: dict[str, Any]) -> None:
    try:
        host = str(payload["host"])
        user = str(payload["ssh_user"])
        password = str(payload.get("ssh_password") or "")
        port = int(payload.get("ssh_port") or 22)
        sensor_id = str(payload["sensor_id"])
        center_url = str(payload["center_url"])
        remote_dir = str(payload.get("remote_dir") or "~/early-detection-complex")
        image_policy = str(payload.get("image_policy") or "prebuilt_only")
        ssh_env = {**os.environ, "SSHPASS": password}

        _update(job_id, status="running", stage="ssh_check", progress=10, message="Проверяю SSH-доступ к сенсору.")
        _ssh(host, port, user, "true", ssh_env, timeout=20)

        _update(job_id, stage="packages", progress=25, message="Устанавливаю Docker/Python на сенсор, если их нет.")
        _ssh(host, port, user, _remote_install_script(password), ssh_env, timeout=600)

        if payload.get("load_artifacts", True):
            _update(job_id, stage="image_artifacts", progress=35, message="Проверяю локальные ARMv7 image artifacts центра.")
            _load_local_artifacts(job_id, host, port, user, password, ssh_env)

        _update(job_id, stage="transfer", progress=45, message="Передаю sensor-agent bundle на сенсор.")
        _transfer_bundle(host, port, user, remote_dir, ssh_env)

        env_text = "\n".join(
            [
                f"EDC_CENTER_URL={center_url}",
                f"EDC_SENSOR_ID={sensor_id}",
                f"EDC_IMAGE_POLICY={image_policy}",
                f"EDC_LOG_RECEIVER_URL={payload.get('log_receiver_url') or ''}",
                "",
            ]
        )
        _ssh_stdin(host, port, user, _remote_dir_command(remote_dir, 'mkdir -p "$REMOTE_DIR" && cat > "$REMOTE_DIR/.env"'), env_text.encode(), ssh_env)

        _update(job_id, stage="agent_start", progress=70, message="Собираю и запускаю контейнер sensor-agent на сенсоре.")
        start_command = _remote_dir_command(
            remote_dir,
            f'cd "$REMOTE_DIR" && {_sudo_command(password, "docker compose --env-file .env -f compose.sensor.yml up -d --build")}',
        )
        _ssh(host, port, user, start_command, ssh_env, timeout=900)

        _update(job_id, stage="verify", progress=90, message="Проверяю контейнер sensor-agent.")
        ps_command = _remote_dir_command(
            remote_dir,
            f'cd "$REMOTE_DIR" && {_sudo_command(password, "docker compose --env-file .env -f compose.sensor.yml ps")}',
        )
        result = _ssh(host, port, user, ps_command, ssh_env, timeout=60)
        _update(job_id, log=result.strip())
        _update(job_id, status="completed", stage="agent_started", progress=100, message="Sensor-agent установлен и запущен. Центр ожидает heartbeat/sync.")
    except Exception as exc:  # noqa: BLE001 - job status must preserve exact bootstrap failure.
        _update(job_id, status="failed", stage="failed", progress=100, message=str(exc), log=f"ERROR: {exc}")


def _ssh_base(host: str, port: int, user: str) -> list[str]:
    return [
        "sshpass",
        "-e",
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-p",
        str(port),
        f"{user}@{host}",
    ]


def _ssh(host: str, port: int, user: str, command: str, env: dict[str, str], timeout: int = 120) -> str:
    return _run(_ssh_base(host, port, user) + [command], env=env, timeout=timeout)


def _ssh_stdin(host: str, port: int, user: str, command: str, stdin: bytes, env: dict[str, str], timeout: int = 120) -> str:
    return _run(_ssh_base(host, port, user) + [command], input_bytes=stdin, env=env, timeout=timeout)


def _run(args: list[str], *, input_bytes: bytes | None = None, env: dict[str, str] | None = None, timeout: int = 120) -> str:
    result = subprocess.run(args, input=input_bytes, capture_output=True, check=False, timeout=timeout, env=env)
    stdout = result.stdout.decode("utf-8", "replace")
    stderr = result.stderr.decode("utf-8", "replace")
    if result.returncode != 0:
        raise RuntimeError((stderr or stdout or f"command failed: {' '.join(args)}").strip())
    return stdout + stderr


def _transfer_bundle(host: str, port: int, user: str, remote_dir: str, env: dict[str, str]) -> None:
    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as archive:
        with tarfile.open(archive.name, "w:gz") as tar:
            tar.add(ROOT / "compose.sensor.yml", arcname="compose.sensor.yml")
            tar.add(ROOT / "sensor", arcname="sensor")
        archive.seek(0)
        _ssh_stdin(
            host,
            port,
            user,
            _remote_dir_command(remote_dir, 'mkdir -p "$REMOTE_DIR" && tar -C "$REMOTE_DIR" -xzf -'),
            archive.read(),
            env,
            timeout=180,
        )


def _remote_dir_command(remote_dir: str, command: str) -> str:
    return (
        f"REMOTE_DIR={shlex.quote(remote_dir)}; "
        'case "$REMOTE_DIR" in "~") REMOTE_DIR="$HOME" ;; ~/*) REMOTE_DIR="$HOME/${REMOTE_DIR#~/}" ;; esac; '
        f"{command}"
    )


def _load_local_artifacts(job_id: str, host: str, port: int, user: str, password: str, env: dict[str, str]) -> None:
    artifact_root = ROOT / "artifacts"
    if not artifact_root.exists():
        _update(job_id, log="image artifacts directory is not mounted; skipping docker load")
        return
    archives = sorted(
        path
        for path in artifact_root.rglob("*.tar.gz")
        if _looks_like_docker_image_archive(path)
    )
    if not archives:
        _update(job_id, log="no local docker image artifacts found; skipping docker load")
        return
    for archive in archives:
        remote_path = f"/tmp/{archive.name}"
        _update(job_id, log=f"loading image artifact {archive.name}")
        _ssh_stdin(host, port, user, f"cat > {shlex.quote(remote_path)}", archive.read_bytes(), env, timeout=600)
        _ssh(host, port, user, _sudo_command(password, f"docker load -i {shlex.quote(remote_path)}"), env, timeout=900)


def _looks_like_docker_image_archive(path: Path) -> bool:
    name = path.name.lower()
    if "edc" not in name:
        return False
    if not any(marker in name for marker in ("armv7", "banana", "local")):
        return False
    return any(honeypot in name for honeypot in ("cowrie", "glutton", "honeypy", "mailoney", "conpot"))


def _sudo_command(password: str, command: str) -> str:
    quoted_command = shlex.quote(command)
    if not password:
        return f"sh -c {quoted_command}"
    return (
        'if [ "$(id -u)" -eq 0 ]; then '
        f"sh -c {quoted_command}; "
        "else "
        f"printf '%s\\n' {shlex.quote(password)} | sudo -S sh -c {quoted_command}; "
        "fi"
    )


def _remote_install_script(password: str) -> str:
    quoted_password = shlex.quote(password)
    return f"""
set -eu
run_root() {{
  if [ "$(id -u)" -eq 0 ]; then
    sh -c "$1"
  else
    printf '%s\\n' {quoted_password} | sudo -S sh -c "$1"
  fi
}}
if command -v apt-get >/dev/null 2>&1; then
  run_root 'apt-get update'
  run_root 'DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl python3'
  run_root 'DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-plugin || true'
elif command -v pacman >/dev/null 2>&1; then
  run_root 'pacman -Sy --noconfirm docker docker-compose python ca-certificates'
elif command -v dnf >/dev/null 2>&1; then
  run_root 'dnf install -y docker docker-compose-plugin python3 ca-certificates'
else
  echo 'unsupported package manager: install docker and python3 manually' >&2
  exit 20
fi
if ! command -v docker >/dev/null 2>&1; then
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    run_root 'sh /tmp/get-docker.sh'
  fi
fi
if ! command -v docker >/dev/null 2>&1; then
  echo 'docker command is still missing after package installation' >&2
  exit 21
fi
run_root 'systemctl enable --now docker || service docker start || true'
run_root 'mkdir -p /var/lib/edc-sensor && chmod 755 /var/lib/edc-sensor'
docker --version
docker compose version || true
"""
