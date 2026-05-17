#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from center.core.log_normalizer import normalize_honeypot_event
from center.persistence.honeypot_logs import read_honeypot_events, reparse_honeypot_events, write_honeypot_batch


def normalize(module: str, payload: dict | str, **extra):
    event = {
        "event_type": f"{module}.raw_log",
        "sensor_id": "sensor-test",
        "module": module,
        "honeypot_raw_event": payload,
        "raw_sample": json.dumps(payload) if isinstance(payload, dict) else payload,
        **extra,
    }
    return normalize_honeypot_event(event)


def assert_field(row: dict | None, key: str, value):
    assert row is not None, f"expected normalized row for {key}"
    assert row.get(key) == value, f"{key}: expected {value!r}, got {row.get(key)!r}; row={row}"


def main() -> None:
    cowrie = normalize(
        "cowrie",
        {
            "eventid": "cowrie.login.failed",
            "username": "admin",
            "password": "qwe",
            "message": "login attempt [admin/qwe] failed",
            "src_ip": "192.168.0.121",
            "dst_port": 2222,
            "timestamp": "2026-05-16T12:08:38.740268Z",
        },
    )
    assert_field(cowrie, "username", "admin")
    assert_field(cowrie, "password", "qwe")
    assert_field(cowrie, "severity", "high")

    mailoney = normalize(
        "mailoney",
        {
            "eventid": "mailoney.auth.login",
            "username": "postmaster",
            "password": "secret",
            "src_ip": "172.17.0.1",
            "src_port": 44876,
            "dst_port": 2525,
            "protocol": "smtp",
            "timestamp": "2026-05-17T17:49:54.639762+00:00",
        },
    )
    assert_field(mailoney, "service", "smtp")
    assert_field(mailoney, "username", "postmaster")
    assert_field(mailoney, "password", "secret")

    glutton = normalize(
        "glutton",
        '{"time":"2026-05-16T11:59:45.504939088Z","level":"INFO","msg":"HTTP GET request handled: /login.cgi","handler":"http","dest_port":"8000","src_ip":"192.168.0.121","src_port":"52716","path":"/login.cgi","method":"GET","query":""}',
    )
    assert_field(glutton, "dst_port", 8000)
    assert_field(glutton, "service", "camera-service")
    assert_field(glutton, "http_method", "GET")
    assert_field(glutton, "url", "/login.cgi")

    honeypy = normalize(
        "honeypy",
        {
            "event": "RX",
            "service": "Web",
            "local_port": "10080",
            "remote_host": "172.17.0.1",
            "remote_port": "33236",
            "date_time": "2026-05-17T17:49:39",
            "data": "474554202f736e617073686f742e6a706720485454502f312e310d0a486f73743a203132372e302e302e310d0a557365722d4167656e743a206375726c2f382e31342e310d0a0d0a",
        },
    )
    assert_field(honeypy, "dst_port", 10080)
    assert_field(honeypy, "http_method", "GET")
    assert_field(honeypy, "url", "/snapshot.jpg")
    assert_field(honeypy, "user_agent", "curl/8.14.1")

    conpot = normalize(
        "conpot",
        {
            "timestamp": "2026-05-17T16:50:03.852276",
            "sensorid": "banana-pi-pro-1",
            "src_ip": "172.17.0.1",
            "src_port": 40406,
            "data_type": "http",
            "request": "('/login.html', [('Host', '127.0.0.1'), ('User-Agent', 'curl/8.14.1'), ('Accept', '*/*')], None)",
            "response": "404",
            "event_type": None,
        },
    )
    assert_field(conpot, "service", "http")
    assert_field(conpot, "dst_port", 80)
    assert_field(conpot, "url", "/login.html")
    assert_field(conpot, "user_agent", "curl/8.14.1")

    conpot_closed = normalize(
        "conpot",
        {
            "timestamp": "2026-05-17T16:49:28.682339",
            "src_ip": "172.17.0.1",
            "data_type": "s7comm",
            "event_type": "CONNECTION_LOST",
        },
    )
    assert conpot_closed is None, "CONNECTION_LOST must stay raw-only"

    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "events.sqlite3"
        write_honeypot_batch(
            store,
            [
                {
                    "event_type": "glutton.raw_log",
                    "sensor_id": "sensor-test",
                    "module": "glutton",
                    "honeypot_raw_event": "loading configurations from /etc/glutton",
                    "raw_sample": "loading configurations from /etc/glutton",
                },
                {
                    "event_type": "cowrie.raw_log",
                    "sensor_id": "sensor-test",
                    "module": "cowrie",
                    "honeypot_raw_event": {
                        "eventid": "cowrie.login.failed",
                        "username": "root",
                        "password": "toor",
                        "src_ip": "10.0.0.5",
                    },
                },
            ],
        )
        result = reparse_honeypot_events(store, batch_size=1)
        assert result == {"raw": 2, "normalized": 1, "skipped": 1}, result
        events = read_honeypot_events(store, limit=10)
        assert len(events) == 1, events
        assert_field(events[0], "username", "root")
        assert_field(events[0], "password", "toor")

    print("log normalizer ok")


if __name__ == "__main__":
    main()
