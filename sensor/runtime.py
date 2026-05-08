"""Docker based honeypot runtime for the EDC sensor-agent.

The runtime intentionally does not emulate honeypot protocols itself. It
materializes the desired state as Docker Compose, removes old EDC containers,
starts real open-source honeypot images and forwards their raw container logs
to the center.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable


EventSender = Callable[[dict[str, Any]], bool]


RUNTIME_VERSION = "docker-runtime-v1"
PROJECT_PREFIX = "edc"
SUPPORTED_IMAGES = {
    "cowrie": "cowrie/cowrie:latest",
    "opencanary": "thinkst/opencanary:latest",
    "dionaea": "dinotools/dionaea:latest",
    "conpot": "honeynet/conpot:latest",
    "heralding": "dtagdevsec/heralding:24.04.1",
}
MODULE_LOG_HINTS = {
    "cowrie": "/cowrie/cowrie-git/var/log/cowrie/cowrie.json",
    "opencanary": "/var/tmp/opencanary.log",
    "dionaea": "/opt/dionaea/var/log/dionaea",
    "conpot": "container stdout",
    "heralding": "container stdout",
}

HERALDING_CAPABILITIES = {
    "ftp": 21,
    "telnet": 23,
    "pop3": 110,
    "pop3s": 995,
    "postgresql": 5432,
    "imap": 143,
    "imaps": 993,
    "ssh": 22,
    "http": 80,
    "https": 443,
    "smtp": 25,
    "smtps": 465,
    "vnc": 5900,
    "socks5": 1080,
    "mysql": 3306,
    "rdp": 3389,
}


def now_ts() -> float:
    return time.time()


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value).strip("-") or "sensor"


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return json.dumps(text, ensure_ascii=False)


def service_lookup(module: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(service.get("id")): service for service in module.get("services", [])}


def selected_host_port(module: dict[str, Any], service_id: str, default: int) -> int:
    service = service_lookup(module).get(service_id, {})
    return int(service.get("host_port") or service.get("default_host_port") or default)


def module_enabled(module: dict[str, Any]) -> bool:
    return module.get("enabled", True) is not False


def selected_services(module: dict[str, Any]) -> list[dict[str, Any]]:
    if not module_enabled(module):
        return []
    return [service for service in module.get("services", []) if service.get("enabled", True) is not False]


def selected_service_ids(module: dict[str, Any]) -> set[str]:
    return {str(service.get("id")) for service in selected_services(module)}


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def compose_service_name(module_id: str) -> str:
    return f"honeypot-{safe_name(module_id)}"


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

    def start(self) -> None:
        self.ensure_docker()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.prepare_module_dirs()
        self.write_compose()
        self.remove_old_containers()
        result = self.run_compose("up", "-d", "--remove-orphans", check=False)
        if result.returncode != 0:
            self.errors.append({"stage": "compose-up", "error": result.stderr.strip() or result.stdout.strip()})
            raise DockerRuntimeError(result.stderr.strip() or result.stdout.strip())
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
        active_containers = self.container_rows()
        active_modules = {container.get("LabelModule"): container for container in active_containers}
        items: list[dict[str, Any]] = []
        for module in self.desired.get("modules", []):
            module_id = str(module.get("id"))
            state = "running" if module_id in active_modules else "planned"
            for service in selected_services(module):
                service_id = str(service.get("id"))
                items.append(
                    {
                        "module": module_id,
                        "service": service_id,
                        "host_port": service.get("host_port"),
                        "container_port": int(service.get("container_port") or self.container_port(module_id, service_id)),
                        "state": state,
                        "container": active_modules.get(module_id, {}).get("Names"),
                        "container_status": active_modules.get(module_id, {}).get("Status"),
                    }
                )
        return items

    def ensure_docker(self) -> None:
        if shutil.which("docker") is None:
            raise DockerRuntimeError("docker executable not found on sensor")
        result = subprocess.run(["docker", "compose", "version"], text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise DockerRuntimeError("docker compose plugin is not available on sensor")

    def prepare_module_dirs(self) -> None:
        for module_id in SUPPORTED_IMAGES:
            base = self.runtime_dir / module_id
            for child in ("config", "data", "logs"):
                path = base / child
                path.mkdir(parents=True, exist_ok=True)
                path.chmod(0o777)
        self.write_cowrie_config()
        self.write_opencanary_config()
        self.write_heralding_config()
        self.write_conpot_config()

    def write_cowrie_config(self) -> None:
        module = self.module_by_id("cowrie")
        if not module:
            return
        settings = module.get("settings", {})
        etc_dir = self.runtime_dir / "cowrie" / "config"
        userdb = str(settings.get("userdb_entries") or "root:x:!root\nadmin:x:admin")
        (etc_dir / "userdb.txt").write_text(userdb.rstrip() + "\n", encoding="utf-8")
        hostname = settings.get("hostname") or self.desired.get("persona", {}).get("hostname") or self.sensor_id
        cowrie_cfg = [
            "[honeypot]",
            f"hostname = {hostname}",
            f"logtype = {settings.get('logtype', 'rotating')}",
            f"download_limit_size = {int(settings.get('download_limit_size', 10485760))}",
            f"authentication_timeout = {int(settings.get('authentication_timeout', 120))}",
            f"idle_timeout = {int(settings.get('idle_timeout', 180))}",
            "",
            "[ssh]",
            f"enabled = {'yes' if 'ssh' in selected_service_ids(module) else 'no'}",
            f"version = {settings.get('ssh_version', 'SSH-2.0-OpenSSH_8.4')}",
            "",
            "[telnet]",
            f"enabled = {'yes' if 'telnet' in selected_service_ids(module) else 'no'}",
            "",
        ]
        raw = str(settings.get("raw_cowrie_cfg") or "").strip()
        if raw:
            cowrie_cfg.extend(["", raw])
        (etc_dir / "cowrie.cfg").write_text("\n".join(cowrie_cfg) + "\n", encoding="utf-8")

    def write_opencanary_config(self) -> None:
        module = self.module_by_id("opencanary")
        if not module:
            return
        settings = module.get("settings", {})
        enabled = {str(service.get("id")) for service in selected_services(module)}
        config = {
            "device.node_id": settings.get("device.node_id", f"opencanary-{self.sensor_id}"),
            "ip.ignorelist": [item.strip() for item in str(settings.get("ip.ignorelist", "")).replace("\n", ",").split(",") if item.strip()],
            "logger": {
                "class": "PyLogger",
                "kwargs": {
                    "formatters": {"plain": {"format": "%(message)s"}},
                    "handlers": {"console": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout"}},
                },
            },
        }
        for service_id in ("ftp", "http", "redis", "mysql", "mssql", "ssh", "telnet", "smb"):
            config[f"{service_id}.enabled"] = service_id in enabled
        config.update(
            {
                "ftp.banner": settings.get("ftp.banner", "FTP server ready"),
                "http.banner": settings.get("http.banner", "nginx/1.18.0"),
                "http.skin": settings.get("http.skin", "nasLogin"),
                "mysql.banner": settings.get("mysql.banner", "5.5.43-0ubuntu0.14.04.1"),
                "ssh.version": settings.get("ssh.version", "SSH-2.0-OpenSSH_5.1p1 Debian-4"),
                "telnet.banner": settings.get("telnet.banner", ""),
            }
        )
        raw = str(settings.get("raw_opencanary_conf") or "").strip()
        if raw:
            try:
                overlay = json.loads(raw)
                if isinstance(overlay, dict):
                    config.update(overlay)
            except json.JSONDecodeError as exc:
                self.errors.append({"module": "opencanary", "stage": "config", "error": str(exc)})
        config_dir = self.runtime_dir / "opencanary" / "config"
        (config_dir / "opencanary.conf").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def write_heralding_config(self) -> None:
        module = self.module_by_id("heralding")
        if not module:
            return
        settings = module.get("settings", {})
        enabled = selected_service_ids(module)
        lines = [
            "public_ip_as_destination_ip: false",
            f"bind_host: {yaml_scalar(settings.get('listen_addr', '0.0.0.0'))}",
            "activity_logging:",
            "  file:",
            "    enabled: true",
            f"    session_csv_log_file: {yaml_scalar('/logs/' + str(settings.get('session_csv_logfile', 'log_session.csv')))}",
            f"    session_json_log_file: {yaml_scalar('/logs/' + str(settings.get('session_json_logfile', 'log_session.json')))}",
            f"    authentication_log_file: {yaml_scalar('/logs/' + str(settings.get('auth_logfile', 'log_auth.csv')))}",
            "  syslog:",
            "    enabled: false",
            "  hpfeeds:",
            "    enabled: false",
            "  curiosum:",
            "    enabled: false",
            "hash_cracker:",
            "  enabled: true",
            "  wordlist_file: '/usr/lib/python3.12/site-packages/heralding/wordlist.txt'",
            "capabilities:",
        ]
        for capability, port in HERALDING_CAPABILITIES.items():
            lines.extend(
                [
                    f"  {capability}:",
                    f"    enabled: {'true' if capability in enabled else 'false'}",
                    f"    port: {port}",
                    "    timeout: 30",
                ]
            )
            if capability in {"ftp", "pop3", "smtp", "http", "ssh"}:
                lines.append("    protocol_specific_data:")
                if capability == "ftp":
                    lines.extend(["      max_attempts: 3", "      banner: \"Microsoft FTP Server\"", "      syst_type: \"Windows-NT\""])
                elif capability == "pop3":
                    lines.extend(["      max_attempts: 3", "      banner: \"+OK POP3 server ready\""])
                elif capability == "smtp":
                    lines.extend(["      banner: \"Microsoft ESMTP MAIL service ready\"", "      fqdn: \"\""])
                elif capability == "http":
                    lines.append("      banner: \"\"")
                elif capability == "ssh":
                    lines.append("      banner: \"SSH-2.0-OpenSSH_6.6.1p1 Ubuntu-2ubuntu2.8\"")
        raw = str(settings.get("raw_heralding_yml") or "").strip()
        if raw:
            lines.extend(["", "# raw_heralding_yml", raw])
        config_dir = self.runtime_dir / "heralding" / "config"
        (config_dir / "heralding.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_conpot_config(self) -> None:
        module = self.module_by_id("conpot")
        if not module:
            return
        settings = module.get("settings", {})
        fetch_public_ip = as_bool(settings.get("fetch_public_ip.enabled"), False)
        hpfriends_enabled = as_bool(settings.get("hpfriends.enabled"), False)
        sqlite_enabled = as_bool(settings.get("sqlite.enabled"), False)
        channels = settings.get("hpfriends.channels", "conpot.events")
        if isinstance(channels, str):
            channel_items = [item.strip() for item in channels.replace("\n", ",").split(",") if item.strip()]
        else:
            channel_items = [str(item) for item in channels]
        lines = [
            "[common]",
            f"sensorid = {self.sensor_id}",
            "",
            "[virtual_file_system]",
            "data_fs_url = osfs:///data",
            "fs_url = tar:///home/conpot/.local/lib/python3.6/site-packages/conpot-0.6.0-py3.6.egg/conpot/data.tar",
            "",
            "[session]",
            "timeout = 30",
            "",
            "[json]",
            "enabled = True",
            "filename = /logs/conpot.json",
            "",
            "[sqlite]",
            f"enabled = {'True' if sqlite_enabled else 'False'}",
            "filename = /data/conpot.sqlite",
            "",
            "[mysql]",
            "enabled = False",
            "",
            "[syslog]",
            "enabled = False",
            "",
            "[hpfriends]",
            f"enabled = {'True' if hpfriends_enabled else 'False'}",
            f"host = {settings.get('hpfriends.host', 'hpfriends.honeycloud.net')}",
            f"port = {int(settings.get('hpfriends.port', 20000))}",
            f"channels = {json.dumps(channel_items)}",
            "",
            "[taxii]",
            "enabled = False",
            "",
            "[fetch_public_ip]",
            f"enabled = {'True' if fetch_public_ip else 'False'}",
            f"urls = {json.dumps([settings.get('fetch_public_ip.url', 'http://whatismyip.akamai.com/')])}",
            "",
            "[change_mac_addr]",
            "enabled = False",
        ]
        raw = str(settings.get("raw_conpot_cfg") or "").strip()
        if raw:
            lines.extend(["", raw])
        config_dir = self.runtime_dir / "conpot" / "config"
        (config_dir / "conpot.cfg").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_compose(self) -> None:
        lines = ["services:"]
        service_count = 0
        for module in self.desired.get("modules", []):
            if not module_enabled(module):
                continue
            module_id = str(module.get("id"))
            if module_id not in SUPPORTED_IMAGES:
                self.errors.append({"module": module_id, "stage": "compose", "error": "unsupported module"})
                continue
            block = self.compose_block(module)
            if block:
                service_count += 1
                lines.extend(block)
        if service_count == 0:
            lines.extend(["  idle:", "    image: alpine:3.20", "    command: [\"sh\", \"-c\", \"sleep infinity\"]"])
        self.compose_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

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
        command = self.compose_command(module)
        if command:
            block.append(f"    command: {command}")
        working_dir = self.compose_working_dir(module)
        if working_dir:
            block.append(f"    working_dir: {yaml_scalar(working_dir)}")
        return block

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
                f"{base / 'config' / 'cowrie.cfg'}:/cowrie/cowrie-git/etc/cowrie.cfg:ro",
                f"{base / 'config' / 'userdb.txt'}:/cowrie/cowrie-git/etc/userdb.txt:ro",
                f"{base / 'data'}:/cowrie/cowrie-git/var/lib/cowrie",
                f"{base / 'logs'}:/cowrie/cowrie-git/var/log/cowrie",
            ]
        if module_id == "opencanary":
            return [f"{base / 'config' / 'opencanary.conf'}:/root/.opencanary.conf:ro", f"{base / 'logs'}:/var/tmp"]
        if module_id == "dionaea":
            return [
                f"{base / 'data'}:/opt/dionaea/var/lib",
                f"{base / 'logs'}:/opt/dionaea/var/log",
            ]
        if module_id == "conpot":
            return [f"{base / 'config' / 'conpot.cfg'}:/etc/conpot/conpot.cfg:ro", f"{base / 'data'}:/data", f"{base / 'logs'}:/logs"]
        if module_id == "heralding":
            return [f"{base / 'config' / 'heralding.yml'}:/etc/heralding/heralding.yml:ro", f"{base / 'data'}:/data", f"{base / 'logs'}:/logs"]
        if module_id in {"conpot", "heralding"}:
            return [f"{base / 'data'}:/data", f"{base / 'logs'}:/logs"]
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
        if module_id == "dionaea":
            return {"DIONAEA_FORCE_INIT": "1"}
        return {}

    def compose_command(self, module: dict[str, Any]) -> str:
        module_id = str(module.get("id"))
        if module_id == "heralding":
            return yaml_scalar("heralding -c /etc/heralding/heralding.yml -l /logs/heralding.log")
        if module_id == "conpot":
            template = module.get("settings", {}).get("template", "default")
            return yaml_scalar(
                f"/home/conpot/.local/bin/conpot --template {template} --config /etc/conpot/conpot.cfg --logfile /logs/conpot.log --temp_dir /tmp"
            )
        return ""

    def compose_working_dir(self, module: dict[str, Any]) -> str:
        module_id = str(module.get("id"))
        if module_id == "heralding":
            return "/tmp"
        return ""

    def container_port(self, module_id: str, service_id: str) -> int:
        defaults = {
            ("cowrie", "ssh"): 2222,
            ("cowrie", "telnet"): 2223,
            ("opencanary", "http"): 80,
            ("opencanary", "ftp"): 21,
            ("opencanary", "redis"): 6379,
            ("opencanary", "mysql"): 3306,
            ("opencanary", "mssql"): 1433,
            ("opencanary", "ssh"): 22,
            ("opencanary", "telnet"): 23,
            ("opencanary", "smb"): 445,
            ("dionaea", "smb"): 445,
            ("dionaea", "http"): 80,
            ("dionaea", "ftp"): 21,
            ("conpot", "modbus"): 5020,
            ("conpot", "http"): 8800,
            ("heralding", "ftp"): 21,
            ("heralding", "http"): 80,
            ("heralding", "pop3"): 110,
            ("heralding", "smtp"): 25,
        }
        return defaults.get((module_id, service_id), selected_host_port(self.module_by_id(module_id) or {}, service_id, 0))

    def module_by_id(self, module_id: str) -> dict[str, Any] | None:
        for module in self.desired.get("modules", []):
            if module.get("id") == module_id:
                return module
        return None

    def run_compose(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["docker", "compose", "-p", self.project_name, "-f", str(self.compose_path), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise DockerRuntimeError(result.stderr.strip() or result.stdout.strip())
        return result

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

    def container_rows(self) -> list[dict[str, Any]]:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"label=edc.sensor_id={self.sensor_id}",
                "--format",
                "{{json .}}",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        rows: list[dict[str, Any]] = []
        for line in result.stdout.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            labels = self.inspect_labels(row.get("ID", ""))
            row["LabelModule"] = labels.get("edc.module")
            rows.append(row)
        return rows

    def inspect_labels(self, container_id: str) -> dict[str, str]:
        if not container_id:
            return {}
        result = subprocess.run(
            ["docker", "inspect", container_id, "--format", "{{json .Config.Labels}}"],
            text=True,
            capture_output=True,
            check=False,
        )
        try:
            labels = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}
        return labels if isinstance(labels, dict) else {}

    def start_log_collectors(self) -> None:
        for row in self.container_rows():
            container_id = row.get("ID")
            labels = self.inspect_labels(container_id)
            module_id = labels.get("edc.module", "unknown")
            thread = threading.Thread(target=self.collect_container_logs, args=(container_id, module_id), daemon=True)
            thread.start()
            self.log_threads.append(thread)

    def collect_container_logs(self, container_id: str, module_id: str) -> None:
        process = subprocess.Popen(
            ["docker", "logs", "--follow", "--since", "0s", container_id],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.log_processes.append(process)
        if not process.stdout:
            return
        for line in process.stdout:
            if self._stop_logs.is_set():
                break
            raw_line = line.rstrip("\n")
            if not raw_line:
                continue
            parsed: Any = None
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError:
                parsed = None
            event: dict[str, Any] = {
                "event_type": self.raw_event_type(module_id, parsed),
                "timestamp": now_ts(),
                "sensor_id": self.sensor_id,
                "module": module_id,
                "service": self.raw_service(module_id, parsed),
                "severity": "low",
                "runtime": RUNTIME_VERSION,
                "container_id": container_id,
                "raw_sample": raw_line[:2000],
                "honeypot_raw_event": parsed if parsed is not None else raw_line,
                "log_hint": MODULE_LOG_HINTS.get(module_id, "container stdout"),
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
