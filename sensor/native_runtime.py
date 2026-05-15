"""Лёгкий native runtime для слабых ARMv7-сенсоров.

Он не пытается заменить полноценные контейнерные honeypots. Его задача -
держать реальные TCP-порты открытыми на платах вроде Banana Pi Pro, фиксировать
подключения и простые credential attempts, когда контейнерный runtime временно
недоступен.
"""

from __future__ import annotations

import socket
import threading
from dataclasses import dataclass
from typing import Any

from runtime_helpers import EventSender, now_ts, selected_services


RUNTIME_VERSION = "native-armv7-v1"


@dataclass
class NativeListener:
    module_id: str
    service_id: str
    host_port: int
    container_port: int
    thread: threading.Thread
    sock: socket.socket


class NativeRuntime:
    def __init__(
        self,
        sensor_id: str,
        center_url: str,
        desired: dict[str, Any],
        sender: EventSender,
        state_dir: Any,
    ):
        self.sensor_id = sensor_id
        self.center_url = center_url
        self.desired = desired
        self.sender = sender
        self.state_dir = state_dir
        self.errors: list[dict[str, Any]] = []
        self.listeners: list[NativeListener] = []
        self._stop = threading.Event()

    def start(self) -> None:
        for module in self.desired.get("modules", []):
            if module.get("enabled", True) is False:
                continue
            module_id = str(module.get("id"))
            for service in selected_services(module):
                service_id = str(service.get("id"))
                host_port = int(service.get("host_port") or service.get("default_host_port") or 0)
                container_port = int(service.get("container_port") or host_port)
                if host_port <= 0:
                    continue
                self.start_listener(module_id, service_id, host_port, container_port)

    def stop(self) -> None:
        self._stop.set()
        for listener in self.listeners:
            try:
                listener.sock.close()
            except OSError:
                pass
        for listener in self.listeners:
            listener.thread.join(timeout=1)
        self.listeners = []

    def active_services(self) -> list[dict[str, Any]]:
        return [
            {
                "module": listener.module_id,
                "service": listener.service_id,
                "host_port": listener.host_port,
                "container_port": listener.container_port,
                "state": "running",
                "container": None,
                "container_status": "native listener",
                "image": "stdlib-native",
                "container_state": "running",
                "running": True,
                "restart_count": 0,
                "last_error": None,
                "port_bindings": [{"host_ip": "0.0.0.0", "host_port": str(listener.host_port), "container_port": f"{listener.container_port}/tcp"}],
            }
            for listener in self.listeners
        ]

    def start_listener(self, module_id: str, service_id: str, host_port: int, container_port: int) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", host_port))
            sock.listen(64)
            sock.settimeout(1)
        except OSError as exc:
            self.errors.append(
                {
                    "module": module_id,
                    "service": service_id,
                    "host_port": host_port,
                    "stage": "bind",
                    "error": str(exc),
                }
            )
            return
        thread = threading.Thread(target=self.accept_loop, args=(module_id, service_id, host_port, sock), daemon=True)
        self.listeners.append(NativeListener(module_id, service_id, host_port, container_port, thread, sock))
        thread.start()

    def accept_loop(self, module_id: str, service_id: str, host_port: int, sock: socket.socket) -> None:
        while not self._stop.is_set():
            try:
                client, address = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            thread = threading.Thread(target=self.handle_client, args=(module_id, service_id, host_port, client, address), daemon=True)
            thread.start()

    def handle_client(self, module_id: str, service_id: str, host_port: int, client: socket.socket, address: tuple[str, int]) -> None:
        client.settimeout(8)
        raw_parts: list[str] = []
        event = self.base_event(module_id, service_id, host_port, address, "connect")
        try:
            protocol = service_id.lower()
            if protocol == "ssh":
                raw_parts = self.handle_ssh(client)
            elif protocol == "telnet":
                raw_parts = self.handle_line_login(client, "login: ", "Password: ")
            elif protocol == "ftp":
                raw_parts = self.handle_line_login(client, "220 FTP server ready\r\nUser: ", "Password: ")
            elif protocol == "smtp":
                raw_parts = self.handle_smtp(client)
            elif protocol == "pop3":
                raw_parts = self.handle_line_login(client, "+OK POP3 server ready\r\nUSER ", "PASS ")
            elif protocol == "http":
                raw_parts = self.handle_http(client)
            elif protocol == "redis":
                raw_parts = self.handle_banner(client, b"-NOAUTH Authentication required.\r\n")
            elif protocol == "mysql":
                raw_parts = self.handle_banner(client, b"\x0a5.5.43-0ubuntu0.14.04.1\x00")
            else:
                raw_parts = self.handle_banner(client, f"{module_id}/{service_id} ready\r\n".encode())
        except OSError as exc:
            event["last_error"] = str(exc)
        finally:
            try:
                client.close()
            except OSError:
                pass
        raw_sample = "\n".join(part for part in raw_parts if part)[:2000]
        if raw_sample:
            event["raw_sample"] = raw_sample
            event["event_type"] = f"{module_id}.{service_id}.input"
            event["severity"] = "medium" if self.looks_like_credentials(raw_sample) else "low"
        self.sender(event)

    def base_event(
        self,
        module_id: str,
        service_id: str,
        host_port: int,
        address: tuple[str, int],
        action: str,
    ) -> dict[str, Any]:
        return {
            "event_type": f"{module_id}.{service_id}.{action}",
            "timestamp": now_ts(),
            "sensor_id": self.sensor_id,
            "module": module_id,
            "service": service_id,
            "severity": "low",
            "runtime": RUNTIME_VERSION,
            "src_ip": address[0],
            "src_port": address[1],
            "dst_port": host_port,
        }

    def recv_text(self, client: socket.socket, limit: int = 512) -> str:
        data = client.recv(limit)
        return data.decode("utf-8", errors="replace").strip()

    def handle_banner(self, client: socket.socket, banner: bytes) -> list[str]:
        client.sendall(banner)
        try:
            return [self.recv_text(client)]
        except OSError:
            return []

    def handle_ssh(self, client: socket.socket) -> list[str]:
        client.sendall(b"SSH-2.0-OpenSSH_8.4\r\n")
        return [self.recv_text(client)]

    def handle_line_login(self, client: socket.socket, user_prompt: str, pass_prompt: str) -> list[str]:
        client.sendall(user_prompt.encode())
        user = self.recv_text(client)
        client.sendall(pass_prompt.encode())
        password = self.recv_text(client)
        client.sendall(b"Authentication failed\r\n")
        return [f"user={user}", f"password={password}"]

    def handle_smtp(self, client: socket.socket) -> list[str]:
        client.sendall(b"220 mail ESMTP service ready\r\n")
        first = self.recv_text(client)
        client.sendall(b"250 mail\r\n")
        second = self.recv_text(client)
        client.sendall(b"535 Authentication failed\r\n")
        return [first, second]

    def handle_http(self, client: socket.socket) -> list[str]:
        request = self.recv_text(client, limit=2048)
        body = b"login required\n"
        response = (
            b"HTTP/1.1 401 Unauthorized\r\n"
            b"Server: nginx/1.18.0\r\n"
            b"WWW-Authenticate: Basic realm=\"admin\"\r\n"
            b"Content-Type: text/plain\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        client.sendall(response)
        return [request]

    def looks_like_credentials(self, raw_sample: str) -> bool:
        lowered = raw_sample.lower()
        return any(marker in lowered for marker in ("user=", "password=", "authorization:", "pass ", "login"))
