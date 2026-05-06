"""Lightweight honeypot listener runtime for the EDC sensor-agent.

This module is intentionally stdlib-only. It gives the project a real
distributed detection loop before heavyweight container modules are added:
enabled services bind TCP ports, suspicious connections become normalized
events, and the center receives them through the existing ingest API.
"""

from __future__ import annotations

import socket
import socketserver
import threading
import time
from typing import Any, Callable


EventSender = Callable[[dict[str, Any]], bool]


def now_ts() -> float:
    return time.time()


def text_sample(data: bytes, limit: int = 240) -> str:
    return data[:limit].decode("utf-8", errors="replace").replace("\x00", "\\0")


def service_event_type(service_id: str, data: bytes) -> str:
    if service_id in {"ftp", "smtp", "pop3", "telnet"} and data:
        return "credential.attempt"
    if service_id == "http":
        return "http.request"
    if service_id in {"ssh", "smb", "redis", "mysql", "mssql", "modbus", "adb"}:
        return f"{service_id}.connection"
    return "network.connection"


def severity_for(service_id: str, data: bytes) -> str:
    if service_id in {"ssh", "telnet", "ftp", "smtp", "pop3"} and data:
        return "high"
    if service_id in {"smb", "mysql", "mssql", "redis", "modbus", "adb"}:
        return "medium"
    return "low"


def module_setting(module: dict[str, Any], key: str, default: Any = "") -> Any:
    return module.get("settings", {}).get(key, default)


def banner_for(module: dict[str, Any], service_id: str, persona: dict[str, Any]) -> bytes:
    hostname = str(persona.get("hostname") or "server")
    if service_id == "ssh":
        version = module_setting(module, "ssh_version") or module_setting(module, "ssh.version") or "SSH-2.0-OpenSSH_8.4"
        return f"{version}\r\n".encode()
    if service_id == "telnet":
        banner = module_setting(module, "telnet.banner")
        if banner:
            return f"{banner}\r\n{hostname} login: ".encode()
        return f"{hostname} login: ".encode()
    if service_id == "ftp":
        banner = module_setting(module, "ftp.banner", f"{hostname} FTP service ready")
        return f"220 {banner}\r\n".encode()
    if service_id == "smtp":
        return f"220 {hostname} ESMTP Postfix\r\n".encode()
    if service_id == "pop3":
        return f"+OK {hostname} POP3 server ready\r\n".encode()
    if service_id == "redis":
        return b"-NOAUTH Authentication required.\r\n"
    if service_id == "adb":
        return b"CNXN\x00\x00\x00\x01\x00\x10\x00\x00"
    if service_id == "mysql":
        return b"\x4a\x00\x00\x00\x0a5.7.44-edc\x00"
    if service_id == "mssql":
        return b"\x04\x01\x00%\x00\x00\x01\x00"
    if service_id == "modbus":
        return b""
    if service_id == "smb":
        return b""
    return b""


def response_for(module: dict[str, Any], service_id: str, data: bytes, persona: dict[str, Any]) -> bytes:
    hostname = str(persona.get("hostname") or "server")
    upper = data.upper()
    if service_id == "http":
        server = str(module_setting(module, "http.banner", "nginx/1.18.0"))
        body = (
            f"<html><title>{hostname}</title><body>"
            f"<h1>{hostname}</h1><p>Authentication required</p>"
            "</body></html>\n"
        ).encode()
        return (
            b"HTTP/1.1 401 Unauthorized\r\n"
            + f"Server: {server}\r\n".encode()
            + b"WWW-Authenticate: Basic realm=\"Restricted\"\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"Connection: close\r\n\r\n"
            + body
        )
    if service_id == "ftp":
        if upper.startswith(b"USER"):
            return b"331 Password required\r\n"
        return b"530 Login incorrect\r\n"
    if service_id == "smtp":
        return b"535 5.7.8 Authentication credentials invalid\r\n"
    if service_id == "pop3":
        return b"-ERR Authentication failed\r\n"
    if service_id == "telnet":
        return b"Password: "
    if service_id == "redis":
        return b"-NOAUTH Authentication required.\r\n"
    return b""


class HoneypotTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], context: dict[str, Any]):
        self.context = context
        super().__init__(address, HoneypotHandler)


class HoneypotHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        context = self.server.context  # type: ignore[attr-defined]
        service = context["service"]
        module = context["module"]
        persona = context["persona"]
        sender: EventSender = context["sender"]
        sensor_id = context["sensor_id"]
        center_url = context["center_url"]
        src_ip, src_port = self.client_address
        host_port = service["host_port"]
        service_id = service["id"]
        module_id = module["id"]
        first_payload = b""

        self.request.settimeout(1)
        banner = banner_for(module, service_id, persona)
        if banner:
            try:
                self.request.sendall(banner)
            except OSError:
                pass
        try:
            first_payload = self.request.recv(1024)
            response = response_for(module, service_id, first_payload, persona)
            if response:
                self.request.sendall(response)
            if service_id in {"ftp", "telnet", "smtp", "pop3"}:
                more = self.request.recv(1024)
                if more:
                    first_payload += b"\n" + more
                    followup = response_for(module, service_id, more, persona)
                    if followup:
                        self.request.sendall(followup)
        except (OSError, TimeoutError):
            pass

        sender(
            {
                "event_type": service_event_type(service_id, first_payload),
                "timestamp": now_ts(),
                "sensor_id": sensor_id,
                "module": module_id,
                "service": service_id,
                "protocol": service.get("protocol", "tcp"),
                "src_ip": src_ip,
                "src_port": src_port,
                "dst_port": host_port,
                "severity": severity_for(service_id, first_payload),
                "profile": context.get("profile"),
                "persona": persona,
                "raw_sample": text_sample(first_payload),
                "runtime": "lightweight-listener",
                "center_url": center_url,
            }
        )


class ListenerRuntime:
    def __init__(self, sensor_id: str, center_url: str, desired: dict[str, Any], sender: EventSender):
        self.sensor_id = sensor_id
        self.center_url = center_url
        self.desired = desired
        self.sender = sender
        self.servers: list[HoneypotTCPServer] = []
        self.threads: list[threading.Thread] = []
        self.errors: list[dict[str, Any]] = []

    def start(self) -> None:
        persona = self.desired.get("persona", {})
        for module in self.desired.get("modules", []):
            if module.get("enabled", True) is False:
                continue
            for service in module.get("services", []):
                host_port = int(service["host_port"])
                context = {
                    "sensor_id": self.sensor_id,
                    "center_url": self.center_url,
                    "profile": self.desired.get("profile"),
                    "persona": persona,
                    "module": module,
                    "service": service,
                    "sender": self.sender,
                }
                try:
                    server = HoneypotTCPServer(("0.0.0.0", host_port), context)
                except OSError as exc:
                    self.errors.append(
                        {
                            "module": module.get("id"),
                            "service": service.get("id"),
                            "host_port": host_port,
                            "error": str(exc),
                        }
                    )
                    continue
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                self.servers.append(server)
                self.threads.append(thread)

    def stop(self) -> None:
        for server in self.servers:
            server.shutdown()
        for server in self.servers:
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=1.0)
        self.servers = []
        self.threads = []

    def active_services(self) -> list[dict[str, Any]]:
        items = []
        for server in self.servers:
            context = server.context
            items.append(
                {
                    "module": context["module"]["id"],
                    "service": context["service"]["id"],
                    "host_port": context["service"]["host_port"],
                    "state": "listening",
                }
            )
        return items
