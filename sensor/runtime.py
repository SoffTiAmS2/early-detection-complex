"""Docker runtime для honeypot-модулей EDC sensor-agent.

Runtime не имитирует протоколы сам: он превращает desired state в Docker
Compose, удаляет старые контейнеры EDC, запускает реальные open-source
honeypot images и отправляет сырые container logs в центр.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from runtime_configs import prepare_module_dirs
from runtime_helpers import (
    PROJECT_PREFIX,
    RUNTIME_VERSION,
    SUPPORTED_IMAGES,
    UPSTREAM_IMAGES,
    EventSender,
    compose_service_name,
    module_enabled,
    module_supported_on_arch,
    now_ts,
    safe_name,
    selected_host_port,
    selected_services,
    yaml_scalar,
)
from runtime_status import container_rows


class DockerRuntimeError(RuntimeError):
    pass


class DockerRuntime:
    def __init__(
        self,
        sensor_id: str,
        center_url: str,
        desired: dict[str, Any],
        sender: EventSender,
        state_dir: Path,
    ):
        self.sensor_id = sensor_id
        self.center_url = center_url
        self.desired = desired
        self.sender = sender
        self.state_dir = state_dir
        self.runtime_dir = state_dir / "docker-runtime"
        self.compose_path = self.runtime_dir / "docker-compose.yml"
        self.project_name = f"{PROJECT_PREFIX}-{safe_name(sensor_id)}"
        self.errors: list[dict[str, Any]] = []
        self.log_threads: list[threading.Thread] = []
        self.log_processes: list[subprocess.Popen[str]] = []
        self._stop_logs = threading.Event()
        self._compose_modules: list[dict[str, Any]] | None = None
        self._log_mode = "files"
        self.image_policy = str(os.environ.get("EDC_IMAGE_POLICY") or desired.get("image_policy") or "build_if_missing")

    def start(self) -> None:
        self.ensure_docker()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.prepare_module_dirs()
        self.write_compose()
        self.remove_old_containers()
        started = 0
        for service_name, module_id in self.compose_service_modules().items():
            args = ["up", "-d", "--no-deps"]
            if module_id != "idle" and not self.image_exists(SUPPORTED_IMAGES.get(module_id, "")):
                if self.image_policy == "prebuilt_only":
                    self.errors.append(
                        {
                            "module": module_id,
                            "service": service_name,
                            "stage": "image",
                            "error": f"missing prebuilt image: {SUPPORTED_IMAGES.get(module_id, '')}",
                        }
                    )
                    continue
                args.append("--build")
            args.append(service_name)
            result = self.run_compose(*args, check=False)
            if result.returncode != 0:
                self.errors.append(
                    {
                        "module": module_id,
                        "service": service_name,
                        "stage": "compose-up",
                        "error": result.stderr.strip() or result.stdout.strip(),
                    }
                )
                continue
            started += 1
        if started == 0:
            self.errors.append({"stage": "runtime", "error": "no honeypot containers started"})
        self.start_log_collectors()

    def stop(self) -> None:
        self._stop_logs.set()
        for process in self.log_processes:
            if process.poll() is None:
                process.terminate()
        for thread in self.log_threads:
            thread.join(timeout=2)
        self.log_threads = []
        self.log_processes = []
        if self.compose_path.exists():
            self.run_compose("down", "--remove-orphans", check=False)

    def active_services(self) -> list[dict[str, Any]]:
        active_containers = container_rows(self.sensor_id)
        active_modules = {container.get("LabelModule"): container for container in active_containers}
        items: list[dict[str, Any]] = []
        for module in self.desired.get("modules", []):
            module_id = str(module.get("id"))
            container = active_modules.get(module_id, {})
            if not container:
                continue
            container_state = str(container.get("ContainerState") or "unknown")
            state = "running" if container_state == "running" else container_state
            for service in selected_services(module):
                service_id = str(service.get("id"))
                items.append(
                    {
                        "module": module_id,
                        "service": service_id,
                        "host_port": service.get("host_port"),
                        "container_port": int(service.get("container_port") or self.container_port(module_id, service_id)),
                        "state": state,
                        "container": container.get("Names"),
                        "container_status": container.get("Status"),
                        "image": container.get("Image"),
                        "container_state": container.get("ContainerState"),
                        "running": container_state == "running",
                        "restart_count": container.get("RestartCount"),
                        "last_error": container.get("LastError"),
                        "port_bindings": container.get("PortBindings", []),
                    }
                )
        return items

    def ensure_docker(self) -> None:
        if shutil.which("docker") is None:
            raise DockerRuntimeError("docker executable not found on sensor")
        if self.compose_base() is None:
            raise DockerRuntimeError("docker compose plugin or docker-compose executable is not available on sensor")

    def compose_base(self) -> list[str] | None:
        plugin = subprocess.run(["docker", "compose", "version"], text=True, capture_output=True, check=False)
        if plugin.returncode == 0:
            return ["docker", "compose"]
        if shutil.which("docker-compose"):
            legacy = subprocess.run(["docker-compose", "version"], text=True, capture_output=True, check=False)
            if legacy.returncode == 0:
                return ["docker-compose"]
        return None

    def prepare_module_dirs(self) -> None:
        prepare_module_dirs(self.runtime_dir, self.desired, self.sensor_id, self.errors)

    def write_compose(self) -> None:
        lines = ["services:"]
        service_count = 0
        for module in self.compose_modules():
            block = self.compose_block(module)
            if block:
                service_count += 1
                lines.extend(block)
        if service_count == 0:
            lines.extend(["  idle:", "    image: alpine:3.20", "    command: [\"sh\", \"-c\", \"sleep infinity\"]"])
        self.compose_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def compose_modules(self) -> list[dict[str, Any]]:
        if self._compose_modules is not None:
            return self._compose_modules
        modules: list[dict[str, Any]] = []
        for module in self.desired.get("modules", []):
            if not module_enabled(module):
                continue
            module_id = str(module.get("id"))
            if module_id not in SUPPORTED_IMAGES:
                self.errors.append({"module": module_id, "stage": "compose", "error": "unsupported module"})
                continue
            supported, reason = module_supported_on_arch(module_id)
            if not supported:
                self.errors.append({"module": module_id, "stage": "architecture", "error": reason})
                continue
            modules.append(module)
        self._compose_modules = modules
        return modules

    def compose_service_names(self) -> list[str]:
        return list(self.compose_service_modules())

    def compose_service_modules(self) -> dict[str, str]:
        names = {compose_service_name(str(module.get("id"))): str(module.get("id")) for module in self.compose_modules()}
        return names or {"idle": "idle"}

    def compose_block(self, module: dict[str, Any]) -> list[str]:
        module_id = str(module.get("id"))
        name = compose_service_name(module_id)
        container_name = f"{self.project_name}-{name}"
        block = [
            f"  {name}:",
            f"    image: {yaml_scalar(SUPPORTED_IMAGES[module_id])}",
            f"    container_name: {yaml_scalar(container_name)}",
            "    restart: unless-stopped",
            "    labels:",
            f"      edc.sensor_id: {yaml_scalar(self.sensor_id)}",
            f"      edc.module: {yaml_scalar(module_id)}",
            f"      edc.runtime: {yaml_scalar(RUNTIME_VERSION)}",
        ]
        if module_id == "glutton":
            block.extend(["    cap_add:", "      - NET_ADMIN", "      - NET_RAW"])
        build = self.compose_build(module)
        if build:
            block.append("    build:")
            for key, value in build.items():
                if isinstance(value, dict):
                    block.append(f"      {key}:")
                    for nested_key, nested_value in value.items():
                        block.append(f"        {nested_key}: {yaml_scalar(nested_value)}")
                else:
                    block.append(f"      {key}: {yaml_scalar(value)}")
        ports = self.compose_ports(module)
        if ports:
            block.append("    ports:")
            block.extend(f"      - {yaml_scalar(port)}" for port in ports)
        volumes = self.compose_volumes(module)
        if volumes:
            block.append("    volumes:")
            block.extend(f"      - {yaml_scalar(volume)}" for volume in volumes)
        environment = self.compose_environment(module)
        if environment:
            block.append("    environment:")
            for key, value in environment.items():
                block.append(f"      {key}: {yaml_scalar(value)}")
        resource_limits = self.compose_resource_limits(module)
        if resource_limits.get("memory_limit"):
            block.append(f"    mem_limit: {yaml_scalar(resource_limits['memory_limit'])}")
        if resource_limits.get("cpu_limit"):
            block.append(f"    cpus: {yaml_scalar(resource_limits['cpu_limit'])}")
        command = self.compose_command(module)
        if command:
            block.append(f"    command: {command}")
        working_dir = self.compose_working_dir(module)
        if working_dir:
            block.append(f"    working_dir: {yaml_scalar(working_dir)}")
        return block

    def compose_build(self, module: dict[str, Any]) -> dict[str, Any]:
        module_id = str(module.get("id"))
        settings = module.get("settings", {})
        if settings.get("image_mode", "local") == "local":
            image_dir = self.runtime_dir / module_id / "image"
            if not (image_dir / "Dockerfile").exists():
                return {}
            if module_id == "cowrie":
                return {
                    "context": str(image_dir.resolve()),
                    "dockerfile": "Dockerfile",
                    "args": {
                        "COWRIE_BASE_IMAGE": settings.get("base_image", UPSTREAM_IMAGES.get(module_id, SUPPORTED_IMAGES[module_id])),
                        "COWRIE_REF": settings.get("cowrie_ref", "v2.6.1"),
                    },
                }
            if module_id == "glutton":
                return {
                    "context": str(image_dir.resolve()),
                    "dockerfile": "Dockerfile",
                    "args": {
                        "GLUTTON_BUILDER_IMAGE": settings.get("builder_image", settings.get("base_image", UPSTREAM_IMAGES[module_id])),
                        "GLUTTON_RUNTIME_IMAGE": settings.get("runtime_image", "debian:bookworm-slim"),
                    },
                }
            arg_names = {
                "conpot": "HONEYPOT_BASE_IMAGE",
                "honeypy": "HONEYPY_BASE_IMAGE",
                "mailoney": "MAILONEY_BASE_IMAGE",
            }
            arg_name = arg_names.get(module_id, "HONEYPOT_BASE_IMAGE")
            return {
                "context": str(image_dir.resolve()),
                "dockerfile": "Dockerfile",
                "args": {arg_name: settings.get("base_image", UPSTREAM_IMAGES.get(module_id, SUPPORTED_IMAGES[module_id]))},
            }
        return {}

    def compose_ports(self, module: dict[str, Any]) -> list[str]:
        module_id = str(module.get("id"))
        ports: list[str] = []
        for service in selected_services(module):
            service_id = str(service.get("id"))
            host_port = int(service.get("host_port"))
            container_port = int(service.get("container_port") or self.container_port(module_id, service_id))
            protocol = str(service.get("protocol") or "tcp")
            suffix = "" if protocol == "tcp" else f"/{protocol}"
            ports.append(f"{host_port}:{container_port}{suffix}")
        return ports

    def compose_volumes(self, module: dict[str, Any]) -> list[str]:
        module_id = str(module.get("id"))
        base = (self.runtime_dir / module_id).resolve()
        if module_id == "cowrie":
            return [
                f"{base / 'config' / 'cowrie.cfg'}:/home/cowrie/cowrie/etc/cowrie.cfg:ro",
                f"{base / 'config' / 'userdb.txt'}:/home/cowrie/cowrie/etc/userdb.txt:ro",
                f"{base / 'logs'}:/home/cowrie/cowrie/var/log/cowrie",
                f"{base / 'tty'}:/home/cowrie/cowrie/var/lib/cowrie/tty",
                f"{base / 'downloads'}:/home/cowrie/cowrie/var/lib/cowrie/downloads",
                f"{base / 'data'}:/home/cowrie/cowrie/var/lib/cowrie/data",
            ]
        if module_id == "conpot":
            return [f"{base / 'config' / 'conpot.cfg'}:/etc/conpot/conpot.cfg:ro", f"{base / 'data'}:/data", f"{base / 'logs'}:/logs"]
        if module_id == "mailoney":
            return [f"{base / 'config' / 'mailoney.cfg'}:/etc/mailoney/mailoney.cfg:ro", f"{base / 'logs'}:/logs"]
        if module_id == "honeypy":
            return [f"{base / 'config' / 'honeypy.yml'}:/etc/honeypy/config.yml:ro", f"{base / 'logs'}:/logs"]
        if module_id == "glutton":
            return [f"{base / 'config'}:/etc/glutton:ro", f"{base / 'logs'}:/logs"]
        return []

    def compose_environment(self, module: dict[str, Any]) -> dict[str, Any]:
        module_id = str(module.get("id"))
        settings = module.get("settings", {})
        if module_id == "cowrie":
            return {
                "COWRIE_TELNET_ENABLED": "yes" if any(service.get("id") == "telnet" for service in selected_services(module)) else "no",
                "COWRIE_HONEYPOT_HOSTNAME": settings.get("hostname", self.sensor_id),
                "COWRIE_SSH_VERSION": settings.get("ssh_version", "SSH-2.0-OpenSSH_8.4"),
            }
        return {}

    def compose_resource_limits(self, module: dict[str, Any]) -> dict[str, Any]:
        settings = module.get("settings", {}) if isinstance(module.get("settings"), dict) else {}
        limits = settings.get("resource_limits") if isinstance(settings.get("resource_limits"), dict) else {}
        desired_limits = self.desired.get("resource_limits") if isinstance(self.desired.get("resource_limits"), dict) else {}
        return {
            "memory_limit": limits.get("memory_limit") or desired_limits.get("memory_limit"),
            "cpu_limit": limits.get("cpu_limit") or desired_limits.get("cpu_limit"),
        }

    def compose_command(self, module: dict[str, Any]) -> str:
        module_id = str(module.get("id"))
        if module_id == "conpot":
            template = module.get("settings", {}).get("template", "default")
            return yaml_scalar(f"conpot --template {template} --config /etc/conpot/conpot.cfg --logfile /logs/conpot.log --temp_dir /tmp")
        if module_id == "glutton":
            return yaml_scalar("glutton --confpath /etc/glutton --ssh 22 --var-dir /var/lib/glutton --logpath /logs/glutton.log")
        return ""

    def compose_working_dir(self, module: dict[str, Any]) -> str:
        module_id = str(module.get("id"))
        return ""

    def container_port(self, module_id: str, service_id: str) -> int:
        defaults = {
            ("cowrie", "ssh"): 2222,
            ("cowrie", "telnet"): 2223,
            ("conpot", "modbus"): 5020,
            ("conpot", "http"): 8800,
            ("conpot", "s7comm"): 10201,
            ("conpot", "bacnet"): 47808,
            ("conpot", "ethernet_ip"): 44818,
            ("mailoney", "smtp"): 2525,
            ("honeypy", "http"): 10080,
            ("honeypy", "https"): 10080,
            ("honeypy", "http_alt"): 10080,
            ("honeypy", "elasticsearch"): 19200,
            ("honeypy", "echo"): 10007,
            ("honeypy", "motd"): 10008,
            ("honeypy", "random"): 12048,
            ("honeypy", "telnet"): 10023,
            ("glutton", "docker_api"): 2375,
            ("glutton", "mqtt"): 1883,
            ("glutton", "k8s_api"): 6443,
            ("glutton", "rdp"): 3389,
            ("glutton", "vnc"): 5900,
            ("glutton", "sip"): 5060,
            ("glutton", "snmp"): 161,
            ("glutton", "lpd"): 515,
            ("glutton", "ipp"): 631,
            ("glutton", "jetdirect"): 9100,
            ("glutton", "ftp"): 21,
            ("glutton", "rtsp"): 554,
            ("glutton", "camera_service"): 8000,
            ("glutton", "discovery"): 8899,
            ("glutton", "winbox"): 8291,
            ("glutton", "rsync"): 873,
            ("glutton", "nfs"): 2049,
            ("glutton", "smb"): 445,
            ("glutton", "netbios"): 139,
            ("glutton", "msrpc"): 135,
            ("glutton", "wsdiscovery"): 5357,
            ("glutton", "winrm"): 5985,
            ("glutton", "mysql"): 3306,
            ("glutton", "redis"): 6379,
            ("glutton", "postgres"): 5432,
            ("glutton", "pop3"): 110,
            ("glutton", "imap"): 143,
            ("glutton", "smtps"): 465,
            ("glutton", "submission"): 587,
            ("glutton", "imaps"): 993,
            ("glutton", "pop3s"): 995,
            ("glutton", "afp"): 548,
            ("glutton", "nas_web"): 5000,
        }
        return defaults.get((module_id, service_id), selected_host_port(self.module_by_id(module_id) or {}, service_id, 0))

    def module_by_id(self, module_id: str) -> dict[str, Any] | None:
        for module in self.desired.get("modules", []):
            if module.get("id") == module_id:
                return module
        return None

    def run_compose(self, *args: str, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        compose = self.compose_base()
        if compose is None:
            raise DockerRuntimeError("docker compose plugin or docker-compose executable is not available on sensor")
        command = [*compose, "-p", self.project_name, "-f", str(self.compose_path), *args]
        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            result = subprocess.CompletedProcess(
                command,
                124,
                stdout,
                stderr or f"docker compose timed out after {timeout}s",
            )
        if check and result.returncode != 0:
            raise DockerRuntimeError(result.stderr.strip() or result.stdout.strip())
        return result

    def image_exists(self, image: str) -> bool:
        if not image:
            return False
        result = subprocess.run(["docker", "image", "inspect", image], text=True, capture_output=True, check=False)
        return result.returncode == 0

    def remove_old_containers(self) -> None:
        rows = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"label=edc.sensor_id={self.sensor_id}"],
            text=True,
            capture_output=True,
            check=False,
        )
        ids = [line.strip() for line in rows.stdout.splitlines() if line.strip()]
        if ids:
            subprocess.run(["docker", "rm", "-f", *ids], text=True, capture_output=True, check=False)

    def start_log_collectors(self) -> None:
        # Default mode: collect events from mounted files in docker-runtime/*/logs.
        # This is deterministic and easier to debug than parsing docker stdout.
        for module in self.compose_modules():
            module_id = str(module.get("id"))
            for path, parse_as_json in self.module_log_sources(module_id):
                thread = threading.Thread(
                    target=self.collect_file_logs,
                    args=(path, module_id, parse_as_json),
                    daemon=True,
                )
                thread.start()
                self.log_threads.append(thread)

    def module_log_sources(self, module_id: str) -> list[tuple[Path, bool]]:
        base = self.runtime_dir / module_id / "logs"
        if module_id == "cowrie":
            return [(base / "cowrie.json", True)]
        if module_id == "conpot":
            return [(base / "conpot.json", True), (base / "conpot.log", False)]
        if module_id == "mailoney":
            return [(base / "mailoney.jsonl", True)]
        if module_id == "honeypy":
            return [(base / "honeypy-events.json", True), (base / "internal" / "honeypy.log", False)]
        if module_id == "glutton":
            return [(base / "glutton.log", False)]
        return []

    def collect_file_logs(self, path: Path, module_id: str, parse_as_json: bool) -> None:
        position = 0
        while not self._stop_logs.is_set():
            if not path.exists():
                time.sleep(1)
                continue
            if path.stat().st_size < position:
                position = 0
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(position)
                while not self._stop_logs.is_set():
                    line = handle.readline()
                    if not line:
                        position = handle.tell()
                        time.sleep(1)
                        continue
                    raw_line = line.rstrip("\n")
                    if not raw_line:
                        continue
                    parsed: Any = None
                    if parse_as_json:
                        try:
                            parsed = json.loads(raw_line)
                        except json.JSONDecodeError:
                            parsed = None
                    else:
                        parsed = None
                    event: dict[str, Any] = {
                        "event_type": self.raw_event_type(module_id, parsed),
                        "timestamp": now_ts(),
                        "sensor_id": self.sensor_id,
                        "active_profile": self.desired.get("active_profile") or self.desired.get("profile"),
                        "profile": self.desired.get("profile") or self.desired.get("active_profile"),
                        "device_type": self.desired.get("device_type"),
                        "module": module_id,
                        "service": self.raw_service(module_id, parsed),
                        "severity": "low",
                        "runtime": RUNTIME_VERSION,
                        "raw_sample": raw_line[:2000],
                        "honeypot_raw_event": parsed if parsed is not None else raw_line,
                        "log_hint": str(path),
                    }
                    self.copy_network_fields(event, parsed)
                    self.sender(event)

    def raw_event_type(self, module_id: str, parsed: Any) -> str:
        if isinstance(parsed, dict):
            for key in ("eventid", "event_type", "logtype", "type"):
                if parsed.get(key):
                    return str(parsed[key])
        return f"{module_id}.raw_log"

    def raw_service(self, module_id: str, parsed: Any) -> str | None:
        if isinstance(parsed, dict):
            for key in ("service", "protocol", "proto"):
                if parsed.get(key):
                    return str(parsed[key])
        return None

    def copy_network_fields(self, event: dict[str, Any], parsed: Any) -> None:
        if not isinstance(parsed, dict):
            return
        mapping = {
            "src_ip": ("src_ip", "src_host", "remote_host", "remote"),
            "src_port": ("src_port", "remote_port"),
            "dst_port": ("dst_port", "local_port", "port"),
        }
        for target, keys in mapping.items():
            for key in keys:
                if parsed.get(key) is not None:
                    event[target] = parsed[key]
                    break


ListenerRuntime = DockerRuntime
