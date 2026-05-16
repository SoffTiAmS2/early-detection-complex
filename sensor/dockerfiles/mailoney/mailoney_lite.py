#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
import socket
import socketserver
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_filename(value: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in value)


def decode_b64(value: str) -> tuple[Optional[str], bool]:
    try:
        raw = base64.b64decode(value.strip(), validate=False)
        return raw.decode("utf-8", errors="replace"), True
    except Exception:
        return None, False


def parse_auth_plain(decoded: str) -> dict:
    # AUTH PLAIN обычно: authzid\0authcid\0password
    parts = decoded.split("\x00")
    if len(parts) >= 3:
        return {
            "authzid": parts[0],
            "username": parts[-2],
            "password": parts[-1],
        }
    return {
        "authzid": None,
        "username": None,
        "password": None,
        "decoded": decoded,
    }


def extract_headers(message: str) -> dict:
    headers = {}
    current_key = None

    for line in message.splitlines():
        if line == "":
            break

        if line.startswith((" ", "\t")) and current_key:
            headers[current_key] += " " + line.strip()
            continue

        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            headers[key] = value.strip()
            current_key = key

    useful = {}
    for key in ("from", "to", "cc", "bcc", "subject", "date", "message-id", "user-agent", "x-mailer"):
        if key in headers:
            useful[key] = headers[key]

    return useful


@dataclass
class Config:
    host: str
    port: int
    server_name: str
    log_dir: str
    sensor_id: str
    auth_mode: str
    timeout: int
    max_line_bytes: int
    max_message_bytes: int
    preview_chars: int
    save_messages: bool


class JsonLogger:
    def __init__(self, log_dir: str, sensor_id: str):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / "mailoney.jsonl"
        self.sensor_id = sensor_id
        self.lock = threading.Lock()

    def write(self, event: dict) -> None:
        event.setdefault("timestamp", now_iso())
        event.setdefault("sensor", "mailoney-lite")
        event.setdefault("sensor_id", self.sensor_id)
        event.setdefault("protocol", "smtp")

        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))

        with self.lock:
            print(line, flush=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


class SMTPHandler(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self.request.settimeout(self.server.config.timeout)

    @property
    def cfg(self) -> Config:
        return self.server.config

    @property
    def logger(self) -> JsonLogger:
        return self.server.logger

    def send_line(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode("utf-8", errors="replace"))
        self.wfile.flush()

    def read_line(self) -> Optional[str]:
        data = self.rfile.readline(self.cfg.max_line_bytes + 2)
        if not data:
            return None
        return data.decode("utf-8", errors="replace").rstrip("\r\n")

    def log(self, event: dict) -> None:
        event.setdefault("session", self.session)
        event.setdefault("src_ip", self.src_ip)
        event.setdefault("src_port", self.src_port)
        event.setdefault("dst_port", self.cfg.port)
        self.logger.write(event)

    def handle(self):
        self.src_ip, self.src_port = self.client_address[0], self.client_address[1]
        self.session = hashlib.sha256(
            f"{self.src_ip}:{self.src_port}:{uuid.uuid4()}:{now_iso()}".encode()
        ).hexdigest()[:12]

        self.state = {
            "helo": None,
            "mail_from": None,
            "rcpt_to": [],
            "auth": [],
            "commands": 0,
        }

        self.log({
            "eventid": "mailoney.session.connect",
        })

        try:
            self.send_line(f"220 {self.cfg.server_name} ESMTP Postfix")

            while True:
                line = self.read_line()
                if line is None:
                    break

                self.state["commands"] += 1

                if len(line) > self.cfg.max_line_bytes:
                    self.log({
                        "eventid": "mailoney.line.too_long",
                        "line_size": len(line),
                    })
                    self.send_line("500 5.5.2 Line too long")
                    continue

                raw = line
                parts = line.split(" ", 1)
                verb = parts[0].upper() if parts and parts[0] else ""
                arg = parts[1] if len(parts) > 1 else ""

                self.log({
                    "eventid": "mailoney.command",
                    "command": raw,
                    "verb": verb,
                    "arg": arg,
                })

                if verb in ("EHLO", "HELO"):
                    self.handle_helo(verb, arg)

                elif verb == "AUTH":
                    self.handle_auth(arg)

                elif verb == "MAIL" and arg.upper().startswith("FROM:"):
                    self.handle_mail_from(arg)

                elif verb == "RCPT" and arg.upper().startswith("TO:"):
                    self.handle_rcpt_to(arg)

                elif verb == "DATA":
                    self.handle_data()

                elif verb == "RSET":
                    self.state["mail_from"] = None
                    self.state["rcpt_to"] = []
                    self.send_line("250 2.0.0 Ok")

                elif verb == "NOOP":
                    self.send_line("250 2.0.0 Ok")

                elif verb == "VRFY":
                    self.log({
                        "eventid": "mailoney.vrfy",
                        "target": arg,
                    })
                    self.send_line("252 2.0.0 Cannot VRFY user, but will accept message")

                elif verb == "EXPN":
                    self.log({
                        "eventid": "mailoney.expn",
                        "target": arg,
                    })
                    self.send_line("550 5.1.1 Access denied")

                elif verb == "STARTTLS":
                    self.log({
                        "eventid": "mailoney.starttls.attempt",
                    })
                    self.send_line("454 4.7.0 TLS not available due to temporary reason")

                elif verb == "HELP":
                    self.send_line("214-Commands: EHLO HELO AUTH MAIL RCPT DATA RSET NOOP VRFY EXPN STARTTLS QUIT")
                    self.send_line("214 End of HELP info")

                elif verb == "QUIT":
                    self.send_line("221 2.0.0 Bye")
                    break

                elif verb == "":
                    self.send_line("500 5.5.2 Error: bad syntax")

                else:
                    self.log({
                        "eventid": "mailoney.unknown_command",
                        "command": raw,
                        "verb": verb,
                    })
                    self.send_line("250 2.0.0 Ok")

        except socket.timeout:
            self.log({
                "eventid": "mailoney.session.timeout",
            })

        except Exception as e:
            self.log({
                "eventid": "mailoney.error",
                "error": repr(e),
            })

        finally:
            try:
                self.request.close()
            except Exception:
                pass

            self.log({
                "eventid": "mailoney.session.closed",
                "commands_count": self.state.get("commands", 0),
                "helo": self.state.get("helo"),
                "mail_from": self.state.get("mail_from"),
                "rcpt_to": self.state.get("rcpt_to"),
                "auth_attempts": len(self.state.get("auth", [])),
            })

    def handle_helo(self, verb: str, arg: str) -> None:
        self.state["helo"] = f"{verb} {arg}".strip()
        self.send_line(f"250-{self.cfg.server_name}")
        self.send_line("250-AUTH LOGIN PLAIN")
        self.send_line("250-PIPELINING")
        self.send_line("250-SIZE 52428800")
        self.send_line("250-ENHANCEDSTATUSCODES")
        self.send_line("250 8BITMIME")

    def handle_auth(self, arg: str) -> None:
        auth_parts = arg.split(" ", 1)
        method = auth_parts[0].upper() if auth_parts and auth_parts[0] else ""
        initial = auth_parts[1] if len(auth_parts) > 1 else ""

        if method == "LOGIN":
            if initial:
                username_raw = initial.strip()
            else:
                self.send_line("334 VXNlcm5hbWU6")
                username_raw = self.read_line() or ""

            self.send_line("334 UGFzc3dvcmQ6")
            password_raw = self.read_line() or ""

            username, username_ok = decode_b64(username_raw)
            password, password_ok = decode_b64(password_raw)

            event = {
                "eventid": "mailoney.auth.login",
                "auth_method": "LOGIN",
                "username": username if username_ok else username_raw,
                "password": password if password_ok else password_raw,
                "username_raw": username_raw,
                "password_raw": password_raw,
                "username_decoded": username_ok,
                "password_decoded": password_ok,
            }

            self.state["auth"].append(event)
            self.log(event)

            if self.cfg.auth_mode == "success":
                self.send_line("235 2.7.0 Authentication successful")
            else:
                self.send_line("535 5.7.8 Authentication credentials invalid")

        elif method == "PLAIN":
            raw = initial.strip()
            if not raw:
                self.send_line("334")
                raw = self.read_line() or ""

            decoded, ok = decode_b64(raw)
            parsed = parse_auth_plain(decoded or raw)

            event = {
                "eventid": "mailoney.auth.plain",
                "auth_method": "PLAIN",
                "raw": raw,
                "decoded_ok": ok,
                **parsed,
            }

            self.state["auth"].append(event)
            self.log(event)

            if self.cfg.auth_mode == "success":
                self.send_line("235 2.7.0 Authentication successful")
            else:
                self.send_line("535 5.7.8 Authentication credentials invalid")

        else:
            self.log({
                "eventid": "mailoney.auth.unsupported",
                "auth_method": method,
                "arg": arg,
            })
            self.send_line("504 5.5.4 Unrecognized authentication type")

    def handle_mail_from(self, arg: str) -> None:
        value = arg[5:].strip()
        self.state["mail_from"] = value
        self.log({
            "eventid": "mailoney.mail_from",
            "mail_from": value,
        })
        self.send_line("250 2.1.0 Ok")

    def handle_rcpt_to(self, arg: str) -> None:
        value = arg[3:].strip()
        self.state["rcpt_to"].append(value)
        self.log({
            "eventid": "mailoney.rcpt_to",
            "rcpt_to": value,
            "rcpt_count": len(self.state["rcpt_to"]),
        })
        self.send_line("250 2.1.5 Ok")

    def handle_data(self) -> None:
        self.send_line("354 End data with <CR><LF>.<CR><LF>")

        captured = bytearray()
        total_bytes = 0
        lines_count = 0
        truncated = False

        while True:
            line = self.read_line()

            if line is None:
                break

            if line == ".":
                break

            # SMTP dot-stuffing
            if line.startswith(".."):
                line = line[1:]

            raw = (line + "\r\n").encode("utf-8", errors="replace")
            total_bytes += len(raw)
            lines_count += 1

            remaining = self.cfg.max_message_bytes - len(captured)
            if remaining > 0:
                captured.extend(raw[:remaining])
            else:
                truncated = True

        message_bytes = bytes(captured)
        message_text = message_bytes.decode("utf-8", errors="replace")
        message_hash = hashlib.sha256(message_bytes).hexdigest()
        headers = extract_headers(message_text)

        message_file = None
        if self.cfg.save_messages:
            messages_dir = Path(self.cfg.log_dir) / "messages"
            messages_dir.mkdir(parents=True, exist_ok=True)

            ts = safe_filename(now_iso())
            message_file = messages_dir / f"{ts}_{self.session}.eml"
            message_file.write_bytes(message_bytes)

        self.log({
            "eventid": "mailoney.message",
            "helo": self.state["helo"],
            "mail_from": self.state["mail_from"],
            "rcpt_to": self.state["rcpt_to"],
            "auth_attempts": self.state["auth"],
            "message_size_total": total_bytes,
            "message_size_captured": len(message_bytes),
            "message_lines": lines_count,
            "message_truncated": truncated,
            "message_sha256": message_hash,
            "message_headers": headers,
            "message_preview": message_text[:self.cfg.preview_chars],
            "message_file": str(message_file) if message_file else None,
        })

        queue_id = f"EDC{self.session[:8].upper()}"
        self.send_line(f"250 2.0.0 Ok: queued as {queue_id}")


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_class, config: Config, logger: JsonLogger):
        self.config = config
        self.logger = logger
        super().__init__(server_address, handler_class)


def main() -> None:
    parser = argparse.ArgumentParser(description="EDC Mailoney-lite SMTP honeypot")
    parser.add_argument("--host", default=os.getenv("MAILONEY_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MAILONEY_PORT", "2525")))
    parser.add_argument("--server-name", default=os.getenv("MAILONEY_SERVER_NAME", "mail.company.local"))
    parser.add_argument("--sensor-id", default=os.getenv("EDC_SENSOR_ID", "banana-pi-mailoney"))
    parser.add_argument("--log-dir", default=os.getenv("MAILONEY_LOG_DIR", "/logs"))
    parser.add_argument("--auth-mode", choices=["success", "fail"], default=os.getenv("MAILONEY_LOGIN_RESULT", "success"))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("MAILONEY_TIMEOUT", "60")))
    parser.add_argument("--max-line-bytes", type=int, default=int(os.getenv("MAILONEY_MAX_LINE_BYTES", "8192")))
    parser.add_argument("--max-message-bytes", type=int, default=int(os.getenv("MAILONEY_MAX_MESSAGE_BYTES", "262144")))
    parser.add_argument("--preview-chars", type=int, default=int(os.getenv("MAILONEY_PREVIEW_CHARS", "2000")))
    parser.add_argument("--no-save-messages", action="store_true")

    args = parser.parse_args()

    config = Config(
        host=args.host,
        port=args.port,
        server_name=args.server_name,
        log_dir=args.log_dir,
        sensor_id=args.sensor_id,
        auth_mode=args.auth_mode,
        timeout=args.timeout,
        max_line_bytes=args.max_line_bytes,
        max_message_bytes=args.max_message_bytes,
        preview_chars=args.preview_chars,
        save_messages=not args.no_save_messages,
    )

    logger = JsonLogger(config.log_dir, config.sensor_id)

    logger.write({
        "eventid": "mailoney.start",
        "listen_host": config.host,
        "listen_port": config.port,
        "server_name": config.server_name,
        "log_path": str(Path(config.log_dir) / "mailoney.jsonl"),
        "auth_mode": config.auth_mode,
        "max_message_bytes": config.max_message_bytes,
        "save_messages": config.save_messages,
    })

    with ThreadedTCPServer((config.host, config.port), SMTPHandler, config, logger) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
