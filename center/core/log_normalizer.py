from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from typing import Any

from center.core.utils import now_ts


PARSER_NAME = "edc-honeypot-log-normalizer"
PARSER_VERSION = "2"

_KV_RE = re.compile(r"(?P<key>[a-zA-Z_][a-zA-Z0-9_.-]*)=(?P<value>\"[^\"]*\"|'[^']*'|\S+)")
_HTTP_RE = re.compile(r"(?P<method>GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH)\s+(?P<url>\S+)", re.IGNORECASE)
_IP_RE = re.compile(r"\b(?P<ip>(?:\d{1,3}\.){3}\d{1,3})\b")
_AUTH_BRACKET_RE = re.compile(r"\[(?P<username>[^/\]\s]+)/(?P<password>[^\]\s]+)\]")
_BASIC_AUTH_RE = re.compile(r"Authorization:\s*Basic\s+(?P<token>[A-Za-z0-9+/=]+)", re.IGNORECASE)


def normalize_honeypot_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Convert native honeypot log lines into dashboard-friendly events."""

    if _is_control_event(event):
        return None

    raw_payload = event.get("honeypot_raw_event", event.get("raw_event", event))
    parsed = raw_payload if isinstance(raw_payload, dict) else _json_or_none(raw_payload)
    raw_line = _raw_line(event, raw_payload)
    kv = _parse_key_values(raw_line)
    module = _module_alias(
        _first_text(
            event.get("honeypot"),
            event.get("module"),
            _get(parsed, "honeypot"),
            _get(parsed, "module"),
            _get(parsed, "sensor"),
            "unknown",
        )
        or "unknown"
    )

    if _is_non_observable_honeypot_line(module, event, parsed, raw_line):
        return None
    if str(event.get("event_type") or "").endswith(".raw_log") and not _has_observable_activity(event, parsed, kv, raw_line):
        return None

    decoded_payload = _decoded_payload(parsed)
    credential = _credential(parsed, raw_line, decoded_payload)
    dst_port = _dst_port(module, event, parsed, kv)
    service = _service(module, event, parsed, kv, dst_port)

    normalized = {
        "received_at": float(event.get("received_at") or now_ts()),
        "timestamp": _timestamp_or_none(event.get("timestamp") or _get(parsed, "timestamp") or _get(parsed, "time") or _get(parsed, "date_time")),
        "sensor_id": _first_text(event.get("sensor_id"), event.get("sensor"), _get(parsed, "sensor_id"), _get(parsed, "sensorid")),
        "profile": _first_text(event.get("active_profile"), event.get("profile"), _get(parsed, "profile")),
        "device_type": _first_text(event.get("device_type"), _get(parsed, "device_type")),
        "honeypot": module,
        "module": module,
        "service": service,
        "event_type": _event_type(module, event, parsed, kv, raw_line, decoded_payload),
        "severity": _severity(module, event, parsed, raw_line, credential, decoded_payload),
        "src_ip": _first_text(
            event.get("src_ip"),
            _get(parsed, "src_ip"),
            _get(parsed, "source_ip"),
            _get(parsed, "src_host"),
            _get(parsed, "remote_host"),
            _get(parsed, "remote"),
            _get(parsed, "client_ip"),
            kv.get("src_ip"),
            kv.get("src"),
        ),
        "src_port": _int_or_none(event.get("src_port") or _get(parsed, "src_port") or _get(parsed, "source_port") or _get(parsed, "remote_port") or kv.get("src_port")),
        "dst_ip": _first_text(event.get("dst_ip"), _get(parsed, "dst_ip"), _get(parsed, "destination_ip"), _get(parsed, "local_host"), kv.get("dst_ip")),
        "dst_port": dst_port,
        "username": _first_text(credential.get("username"), _get(parsed, "username"), _get(parsed, "login"), _get(parsed, "user"), _get(parsed, "username_raw"), kv.get("username"), kv.get("user")),
        "password": _first_text(credential.get("password"), _get(parsed, "password"), _get(parsed, "pass"), _get(parsed, "password_raw"), kv.get("password"), kv.get("pass")),
        "command": _first_text(
            _get(parsed, "command"),
            _get(parsed, "input"),
            _get(parsed, "verb"),
            kv.get("command"),
            kv.get("payload") if module == "glutton" else None,
            decoded_payload if module in {"honeypy", "glutton"} else None,
        ),
        "url": _first_text(_get(parsed, "url"), _get(parsed, "path"), _get(parsed, "uri"), kv.get("url"), _conpot_request_field(parsed, "url"), _http_match(decoded_payload or raw_line, "url")),
        "http_method": _first_text(_get(parsed, "method"), kv.get("method"), _conpot_request_field(parsed, "method"), _http_match(decoded_payload or raw_line, "method")),
        "user_agent": _first_text(_get(parsed, "user_agent"), _get(parsed, "user-agent"), kv.get("user_agent"), kv.get("ua"), _conpot_request_field(parsed, "user_agent"), _header_value(decoded_payload, "User-Agent")),
        "payload_sample": _payload_sample(event, parsed, kv, raw_line, decoded_payload),
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "raw_event": event,
    }
    if not normalized["src_ip"]:
        normalized["src_ip"] = _first_ip(raw_line)
    if normalized["dst_port"] and not normalized["service"]:
        normalized["service"] = _service_from_port(normalized["dst_port"])
    return normalized


def raw_log_record(event: dict[str, Any]) -> dict[str, Any] | None:
    if _is_control_event(event):
        return None
    raw_payload = event.get("honeypot_raw_event", event.get("raw_event", event))
    parsed = raw_payload if isinstance(raw_payload, dict) else _json_or_none(raw_payload)
    raw_line = _raw_line(event, raw_payload)
    module = _module_alias(
        _first_text(
            event.get("honeypot"),
            event.get("module"),
            _get(parsed, "honeypot"),
            _get(parsed, "module"),
            _get(parsed, "sensor"),
            "unknown",
        )
        or "unknown"
    )
    return {
        "received_at": float(event.get("received_at") or now_ts()),
        "sensor_id": _first_text(event.get("sensor_id"), event.get("sensor"), _get(parsed, "sensor_id"), _get(parsed, "sensorid")),
        "profile": _first_text(event.get("active_profile"), event.get("profile"), _get(parsed, "profile")),
        "device_type": _first_text(event.get("device_type"), _get(parsed, "device_type")),
        "honeypot": module,
        "service": _first_text(event.get("service"), _get(parsed, "service"), _get(parsed, "protocol"), _get(parsed, "data_type")),
        "source_name": _first_text(event.get("source_name"), event.get("log_source"), event.get("module")),
        "source_path": _first_text(event.get("log_hint"), event.get("source_path")),
        "container_name": _first_text(event.get("container"), event.get("container_name")),
        "raw_line": raw_line,
        "parsed_json": parsed,
        "raw_event": event,
    }


def _is_control_event(event: dict[str, Any]) -> bool:
    return str(event.get("event_type") or "").startswith("sensor.")


def _has_observable_activity(event: dict[str, Any], parsed: dict[str, Any] | None, kv: dict[str, str], raw_line: str) -> bool:
    if _first_text(
        event.get("src_ip"),
        _get(parsed, "src_ip"),
        _get(parsed, "source_ip"),
        _get(parsed, "src_host"),
        _get(parsed, "remote_host"),
        _get(parsed, "remote"),
        kv.get("src_ip"),
        kv.get("src"),
        _first_ip(raw_line),
    ):
        return True
    if _int_or_none(
        event.get("dst_port")
        or _get(parsed, "dst_port")
        or _get(parsed, "dest_port")
        or _get(parsed, "local_port")
        or kv.get("dest_port")
        or kv.get("dst_port")
        or kv.get("port")
    ):
        return True
    if _first_text(
        _get(parsed, "username"),
        _get(parsed, "login"),
        _get(parsed, "user"),
        _get(parsed, "password"),
        _get(parsed, "command"),
        _get(parsed, "input"),
        _get(parsed, "eventid"),
        _get(parsed, "event"),
        _get(parsed, "event_type"),
        _decoded_payload(parsed),
        kv.get("username"),
        kv.get("user"),
        kv.get("password"),
        kv.get("command"),
        kv.get("payload"),
        _http_match(raw_line, "method"),
    ):
        return True
    lower = raw_line.lower()
    return any(token in lower for token in ("login attempt", "new connection", "remote", "src_ip", "dest_port", "payload=", "command=", "data_type", "auth"))


def _raw_line(event: dict[str, Any], raw_payload: Any) -> str:
    if event.get("raw_sample"):
        return str(event["raw_sample"])
    if isinstance(raw_payload, str):
        return raw_payload
    return json.dumps(raw_payload, ensure_ascii=False, sort_keys=True)


def _json_or_none(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _timestamp_or_none(value: Any) -> float | None:
    direct = _float_or_none(value)
    if direct is not None:
        return direct
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _parse_key_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in _KV_RE.finditer(line):
        value = match.group("value").strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[match.group("key")] = value
    return values


def _module_alias(value: str) -> str:
    lowered = value.strip().lower()
    aliases = {
        "mailoney-lite": "mailoney",
        "honey.py": "honeypy",
        "honeyd": "honeypy",
        "honey_py": "honeypy",
    }
    return aliases.get(lowered, lowered or "unknown")


def _decoded_payload(parsed: dict[str, Any] | None) -> str | None:
    if not isinstance(parsed, dict):
        return None
    data = parsed.get("data")
    if not isinstance(data, str) or not data:
        return _first_text(parsed.get("payload"), parsed.get("request"))
    text = data.strip()
    if len(text) % 2 != 0 or not re.fullmatch(r"[0-9a-fA-F]+", text):
        return text[:2000]
    try:
        return bytes.fromhex(text).decode("utf-8", errors="replace")[:2000]
    except ValueError:
        return text[:2000]


def _credential(parsed: dict[str, Any] | None, raw_line: str, decoded_payload: str | None) -> dict[str, str]:
    username = _first_text(_get(parsed, "username"), _get(parsed, "login"), _get(parsed, "user"), _get(parsed, "username_raw"))
    password = _first_text(_get(parsed, "password"), _get(parsed, "pass"), _get(parsed, "password_raw"))
    message = _first_text(_get(parsed, "message"), raw_line, decoded_payload)
    if (not username or not password) and message:
        match = _AUTH_BRACKET_RE.search(message)
        if match:
            username = username or match.group("username")
            password = password or match.group("password")
    if (not username or not password) and decoded_payload:
        basic = _basic_auth(decoded_payload)
        username = username or basic.get("username")
        password = password or basic.get("password")
    return {"username": username or "", "password": password or ""}


def _basic_auth(text: str) -> dict[str, str]:
    match = _BASIC_AUTH_RE.search(text)
    if not match:
        return {}
    try:
        decoded = base64.b64decode(match.group("token"), validate=False).decode("utf-8", errors="replace")
    except Exception:
        return {}
    if ":" not in decoded:
        return {"username": decoded, "password": ""}
    username, password = decoded.split(":", 1)
    return {"username": username, "password": password}


def _dst_port(module: str, event: dict[str, Any], parsed: dict[str, Any] | None, kv: dict[str, str]) -> int | None:
    return _int_or_none(
        event.get("dst_port")
        or _get(parsed, "dst_port")
        or _get(parsed, "dest_port")
        or _get(parsed, "destination_port")
        or _get(parsed, "local_port")
        or _get(parsed, "listen_port")
        or kv.get("dest_port")
        or kv.get("dst_port")
        or kv.get("port")
        or _default_port_for_module_service(module, _get(parsed, "data_type") or _get(parsed, "service") or event.get("service"))
    )


def _service(module: str, event: dict[str, Any], parsed: dict[str, Any] | None, kv: dict[str, str], dst_port: int | None) -> str | None:
    return _first_text(
        event.get("service"),
        _get(parsed, "service"),
        _get(parsed, "protocol"),
        _get(parsed, "proto"),
        _get(parsed, "data_type"),
        kv.get("service"),
        kv.get("protocol"),
        _service_from_port(dst_port),
        _get(parsed, "handler"),
    )


def _event_type(module: str, event: dict[str, Any], parsed: dict[str, Any] | None, kv: dict[str, str], raw_line: str, decoded_payload: str | None = None) -> str:
    explicit = _first_text(event.get("event_type"), _get(parsed, "eventid"), _get(parsed, "event_type"), _get(parsed, "event"), _get(parsed, "type"), kv.get("eventid"))
    if explicit and not explicit.endswith(".raw_log"):
        if module == "honeypy":
            return f"honeypy.{explicit.lower()}"
        if module == "conpot" and not str(explicit).startswith("conpot."):
            return f"conpot.{str(explicit).lower()}"
        return explicit
    lower = raw_line.lower()
    if module == "cowrie":
        if "login" in lower or _get(parsed, "username"):
            return "cowrie.login_attempt"
        if _get(parsed, "input"):
            return "cowrie.command"
    if module == "mailoney":
        verb = _first_text(_get(parsed, "verb"), kv.get("verb"))
        if verb:
            return f"mailoney.command.{verb.lower()}"
        eventid = _first_text(_get(parsed, "eventid"))
        if eventid:
            return eventid
    if module == "glutton":
        if _first_text(_get(parsed, "method"), _http_match(raw_line, "method")):
            return "glutton.http_request"
        return "glutton.connection"
    if module == "honeypy":
        if str(_get(parsed, "service") or "").lower() == "web" and str(_get(parsed, "event") or "").upper() == "RX":
            return "honeypy.http_request"
        return "honeypy.interaction"
    if module == "conpot":
        if _get(parsed, "request"):
            return "conpot.request"
        return "conpot.interaction"
    return explicit or f"{module}.interaction"


def _severity(module: str, event: dict[str, Any], parsed: dict[str, Any] | None, raw_line: str, credential: dict[str, str] | None = None, decoded_payload: str | None = None) -> str:
    parsed_explicit = _first_text(_get(parsed, "severity"))
    if parsed_explicit:
        return parsed_explicit
    text = " ".join([raw_line, decoded_payload or "", _first_text(_get(parsed, "eventid"), _get(parsed, "event_type"), _get(parsed, "message")) or ""]).lower()
    if credential and (credential.get("username") or credential.get("password")):
        return "high"
    if any(token in text for token in ("password", "auth", "login attempt", "command", "shell", "cowrie.login")):
        return "high"
    explicit = _first_text(event.get("severity"))
    if explicit and explicit.lower() not in {"low", "info", "informational"}:
        return explicit
    if module in {"cowrie", "mailoney", "conpot", "honeypy"}:
        return "medium"
    return "low"


def _payload_sample(event: dict[str, Any], parsed: dict[str, Any] | None, kv: dict[str, str], raw_line: str, decoded_payload: str | None = None) -> str | None:
    value = _first_text(
        event.get("payload_sample") if decoded_payload is None else None,
        decoded_payload,
        _get(parsed, "payload"),
        _get(parsed, "request"),
        _get(parsed, "message"),
        _get(parsed, "command"),
        _get(parsed, "input"),
        kv.get("payload"),
        kv.get("command"),
        event.get("raw_sample"),
    )
    if value:
        return value[:2000]
    return raw_line[:2000] if raw_line else None


def _http_match(line: str | None, field: str) -> str | None:
    if not line:
        return None
    match = _HTTP_RE.search(line)
    if not match:
        return None
    if field == "method":
        return match.group("method").upper()
    return match.group("url")


def _first_ip(line: str) -> str | None:
    match = _IP_RE.search(line)
    return match.group("ip") if match else None


def _header_value(text: str | None, name: str) -> str | None:
    if not text:
        return None
    prefix = name.lower() + ":"
    for line in text.splitlines():
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def _conpot_request_field(parsed: dict[str, Any] | None, field: str) -> str | None:
    request = _get(parsed, "request")
    if not isinstance(request, str) or not request:
        return None
    if field == "url":
        match = re.search(r"\('(?P<url>[^']+)'", request)
        return match.group("url") if match else None
    if field == "method":
        return "GET" if re.search(r"\('(?P<url>[^']+)'", request) else None
    if field == "user_agent":
        match = re.search(r"\('User-Agent',\s*'(?P<ua>[^']+)'\)", request)
        return match.group("ua") if match else None
    return None


def _is_non_observable_honeypot_line(module: str, event: dict[str, Any], parsed: dict[str, Any] | None, raw_line: str) -> bool:
    event_type = str(event.get("event_type") or _get(parsed, "eventid") or _get(parsed, "event") or _get(parsed, "event_type") or "").lower()
    lower = raw_line.lower()
    if module == "mailoney" and event_type == "mailoney.start":
        return True
    if module == "glutton" and any(token in lower for token in ("loading configurations", "using configuration file")):
        return True
    if module == "conpot" and any(token in lower for token in ("config file found", "template not found")):
        return True
    if module == "honeypy" and str(_get(parsed, "event") or "").upper() == "TX":
        return True
    if module == "conpot" and str(_get(parsed, "event_type") or "").upper() == "CONNECTION_LOST":
        return True
    return False


def _default_port_for_module_service(module: str, service: Any) -> int | None:
    key = str(service or "").strip().lower()
    if module == "conpot":
        return {"modbus": 502, "s7comm": 102, "s7": 102, "http": 80, "ethernet_ip": 44818, "enip": 44818}.get(key)
    return None


def _service_from_port(value: Any) -> str | None:
    port = _int_or_none(value)
    names = {
        21: "ftp",
        22: "ssh",
        23: "telnet",
        25: "smtp",
        80: "http",
        102: "s7comm",
        110: "pop3",
        135: "msrpc",
        139: "netbios",
        143: "imap",
        161: "snmp",
        443: "https",
        445: "smb",
        502: "modbus",
        515: "lpd",
        554: "rtsp",
        587: "submission",
        631: "ipp",
        873: "rsync",
        1883: "mqtt",
        2049: "nfs",
        3306: "mysql",
        3389: "rdp",
        44818: "ethernet-ip",
        5432: "postgres",
        6379: "redis",
        8000: "camera-service",
        8291: "winbox",
        8899: "discovery",
        9100: "jetdirect",
        10080: "http",
        19200: "elasticsearch",
    }
    return names.get(port)
