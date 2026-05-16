from __future__ import annotations

import json
import re
from typing import Any

from center.core.utils import now_ts


PARSER_NAME = "edc-honeypot-log-normalizer"
PARSER_VERSION = "1"

_KV_RE = re.compile(r"(?P<key>[a-zA-Z_][a-zA-Z0-9_.-]*)=(?P<value>\"[^\"]*\"|'[^']*'|\S+)")
_HTTP_RE = re.compile(r"(?P<method>GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH)\s+(?P<url>\S+)", re.IGNORECASE)
_IP_RE = re.compile(r"\b(?P<ip>(?:\d{1,3}\.){3}\d{1,3})\b")


def normalize_honeypot_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Convert raw honeypot output into one dashboard-friendly event row.

    The sensor already sends one event per log line. This normalizer extracts a
    stable set of fields that Grafana can group by without understanding each
    honeypot's native log schema.
    """

    if _is_control_event(event):
        return None

    raw_payload = event.get("honeypot_raw_event", event.get("raw_event", event))
    parsed = raw_payload if isinstance(raw_payload, dict) else _json_or_none(raw_payload)
    raw_line = _raw_line(event, raw_payload)
    kv = _parse_key_values(raw_line)
    module = str(event.get("module") or _dict_get(parsed, "module") or _dict_get(parsed, "sensor") or "unknown")
    service = _first_text(
        event.get("service"),
        _dict_get(parsed, "service"),
        _dict_get(parsed, "protocol"),
        _dict_get(parsed, "proto"),
        kv.get("service"),
        kv.get("protocol"),
        _service_from_port(event.get("dst_port") or _dict_get(parsed, "dst_port") or kv.get("dest_port") or kv.get("dst_port")),
    )
    normalized = {
        "received_at": float(event.get("received_at") or now_ts()),
        "timestamp": _float_or_none(event.get("timestamp") or _dict_get(parsed, "timestamp") or _dict_get(parsed, "time")),
        "sensor_id": _first_text(event.get("sensor_id"), event.get("sensor"), _dict_get(parsed, "sensor_id")),
        "profile": _first_text(event.get("active_profile"), event.get("profile"), _dict_get(parsed, "profile")),
        "device_type": _first_text(event.get("device_type"), _dict_get(parsed, "device_type")),
        "honeypot": module,
        "module": module,
        "service": service,
        "event_type": _event_type(module, event, parsed, kv, raw_line),
        "severity": _severity(module, event, parsed, raw_line),
        "src_ip": _first_text(event.get("src_ip"), _dict_get(parsed, "src_ip"), _dict_get(parsed, "src_host"), _dict_get(parsed, "remote_host"), kv.get("src_ip"), kv.get("src")),
        "src_port": _int_or_none(event.get("src_port") or _dict_get(parsed, "src_port") or _dict_get(parsed, "remote_port") or kv.get("src_port")),
        "dst_ip": _first_text(event.get("dst_ip"), _dict_get(parsed, "dst_ip"), _dict_get(parsed, "local_host"), kv.get("dst_ip")),
        "dst_port": _int_or_none(event.get("dst_port") or _dict_get(parsed, "dst_port") or _dict_get(parsed, "local_port") or kv.get("dest_port") or kv.get("dst_port") or kv.get("port")),
        "username": _first_text(_dict_get(parsed, "username"), _dict_get(parsed, "login"), _dict_get(parsed, "user"), kv.get("username"), kv.get("user")),
        "password": _first_text(_dict_get(parsed, "password"), _dict_get(parsed, "pass"), kv.get("password"), kv.get("pass")),
        "command": _first_text(_dict_get(parsed, "command"), _dict_get(parsed, "input"), kv.get("command"), kv.get("payload") if module == "glutton" else None),
        "url": _first_text(_dict_get(parsed, "url"), _dict_get(parsed, "path"), kv.get("url"), _http_match(raw_line, "url")),
        "http_method": _first_text(_dict_get(parsed, "method"), kv.get("method"), _http_match(raw_line, "method")),
        "user_agent": _first_text(_dict_get(parsed, "user_agent"), _dict_get(parsed, "user-agent"), kv.get("user_agent"), kv.get("ua")),
        "payload_sample": _payload_sample(event, parsed, kv, raw_line),
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
    module = str(event.get("module") or _dict_get(parsed, "module") or _dict_get(parsed, "sensor") or "unknown")
    return {
        "received_at": float(event.get("received_at") or now_ts()),
        "sensor_id": _first_text(event.get("sensor_id"), event.get("sensor"), _dict_get(parsed, "sensor_id")),
        "profile": _first_text(event.get("active_profile"), event.get("profile"), _dict_get(parsed, "profile")),
        "device_type": _first_text(event.get("device_type"), _dict_get(parsed, "device_type")),
        "honeypot": module,
        "service": _first_text(event.get("service"), _dict_get(parsed, "service"), _dict_get(parsed, "protocol")),
        "source_name": _first_text(event.get("source_name"), event.get("log_source"), event.get("module")),
        "source_path": _first_text(event.get("log_hint"), event.get("source_path")),
        "container_name": _first_text(event.get("container"), event.get("container_name")),
        "raw_line": raw_line,
        "parsed_json": parsed,
        "raw_event": event,
    }


def _is_control_event(event: dict[str, Any]) -> bool:
    return str(event.get("event_type") or "").startswith("sensor.")


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


def _dict_get(value: Any, key: str) -> Any:
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


def _parse_key_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in _KV_RE.finditer(line):
        value = match.group("value").strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[match.group("key")] = value
    return values


def _event_type(module: str, event: dict[str, Any], parsed: dict[str, Any] | None, kv: dict[str, str], raw_line: str) -> str:
    explicit = _first_text(event.get("event_type"), _dict_get(parsed, "eventid"), _dict_get(parsed, "event_type"), _dict_get(parsed, "type"), kv.get("eventid"))
    if explicit and not explicit.endswith(".raw_log"):
        return explicit
    lower = raw_line.lower()
    if module == "cowrie":
        if "login" in lower or _dict_get(parsed, "username"):
            return "cowrie.login_attempt"
        if _dict_get(parsed, "input"):
            return "cowrie.command"
    if module == "mailoney":
        verb = _first_text(_dict_get(parsed, "verb"), kv.get("verb"))
        if verb:
            return f"mailoney.command.{verb.lower()}"
    if module == "glutton":
        return "glutton.connection"
    if module == "honeypy":
        return "honeypy.interaction"
    if module == "conpot":
        return "conpot.interaction"
    return explicit or f"{module}.interaction"


def _severity(module: str, event: dict[str, Any], parsed: dict[str, Any] | None, raw_line: str) -> str:
    explicit = _first_text(event.get("severity"), _dict_get(parsed, "severity"))
    if explicit:
        return explicit
    text = raw_line.lower()
    if any(token in text for token in ("password", "auth", "login", "command", "shell")):
        return "high"
    if module in {"cowrie", "mailoney", "conpot"}:
        return "medium"
    return "low"


def _payload_sample(event: dict[str, Any], parsed: dict[str, Any] | None, kv: dict[str, str], raw_line: str) -> str | None:
    value = _first_text(
        event.get("payload_sample"),
        event.get("raw_sample"),
        _dict_get(parsed, "payload"),
        _dict_get(parsed, "message"),
        _dict_get(parsed, "command"),
        _dict_get(parsed, "input"),
        kv.get("payload"),
        kv.get("command"),
    )
    if value:
        return value[:2000]
    return raw_line[:2000] if raw_line else None


def _http_match(line: str, field: str) -> str | None:
    match = _HTTP_RE.search(line)
    if not match:
        return None
    if field == "method":
        return match.group("method").upper()
    return match.group("url")


def _first_ip(line: str) -> str | None:
    match = _IP_RE.search(line)
    return match.group("ip") if match else None


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
        3389: "rdp",
        5432: "postgres",
        6379: "redis",
        8000: "camera-service",
        8291: "winbox",
        8899: "discovery",
        9100: "jetdirect",
    }
    return names.get(port)
