import json
import sqlite3
from pathlib import Path
from typing import Any
try:
    from utils import now_ts
except ModuleNotFoundError:  # Imported as center.storage.json_store.
    from center.utils import now_ts

MAX_EVENT_LIMIT = 1000

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def bump_policy_version(policy: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(policy))
    try:
        version = int(updated.get("version", 0))
    except (TypeError, ValueError):
        version = 0
    updated["version"] = version + 1
    updated["updated_at"] = now_ts()
    return updated


def connect_store(store: Path) -> sqlite3.Connection:
    store.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(store)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at REAL NOT NULL,
            timestamp REAL,
            event_type TEXT NOT NULL,
            sensor_id TEXT,
            module TEXT,
            service TEXT,
            severity TEXT,
            src_ip TEXT,
            src_port INTEGER,
            dst_port INTEGER,
            raw_sample TEXT,
            raw_event TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_received_at ON events(received_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_sensor_id ON events(sensor_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_module ON events(module)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_service ON events(service)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type)")
    return connection


def write_event(store: Path, event: dict[str, Any]) -> None:
    stored = json.loads(json.dumps(event, ensure_ascii=False))
    stored.setdefault("received_at", now_ts())
    stored.setdefault("event_type", stored.get("type", "sensor.event"))
    raw_event = json.dumps(stored, ensure_ascii=False, sort_keys=True)
    with connect_store(store) as connection:
        connection.execute(
            """
            INSERT INTO events (
                received_at, timestamp, event_type, sensor_id, module, service, severity,
                src_ip, src_port, dst_port, raw_sample, raw_event
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                float(stored.get("received_at") or now_ts()),
                stored.get("timestamp"),
                str(stored.get("event_type") or "sensor.event"),
                stored.get("sensor_id") or stored.get("sensor"),
                stored.get("module"),
                stored.get("service"),
                stored.get("severity"),
                stored.get("src_ip"),
                stored.get("src_port"),
                stored.get("dst_port"),
                stored.get("raw_sample") or stored.get("message"),
                raw_event,
            ),
        )

def read_events(store: Path, limit: int) -> list[dict[str, Any]]:
    if not store.exists():
        return []
    with connect_store(store) as connection:
        rows = connection.execute(
            """
            SELECT id, received_at, timestamp, event_type, sensor_id, module, service, severity,
                   src_ip, src_port, dst_port, raw_sample, raw_event
            FROM events
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(limit, MAX_EVENT_LIMIT)),),
        ).fetchall()
    events: list[dict[str, Any]] = []
    for row in reversed(rows):
        try:
            raw_event = json.loads(row["raw_event"])
        except json.JSONDecodeError:
            raw_event = {"event_type": "parse_error", "raw": row["raw_event"]}
        event = dict(raw_event) if isinstance(raw_event, dict) else {"event_type": row["event_type"]}
        event.update(
            {
                "_event_id": row["id"],
                "received_at": row["received_at"],
                "event_type": row["event_type"],
                "sensor_id": row["sensor_id"] or event.get("sensor_id") or event.get("sensor"),
                "module": row["module"] or event.get("module"),
                "service": row["service"] or event.get("service"),
                "severity": row["severity"] or event.get("severity"),
                "src_ip": row["src_ip"] or event.get("src_ip"),
                "src_port": row["src_port"] if row["src_port"] is not None else event.get("src_port"),
                "dst_port": row["dst_port"] if row["dst_port"] is not None else event.get("dst_port"),
                "raw_sample": row["raw_sample"] or event.get("raw_sample"),
                "raw_event": raw_event,
            }
        )
        events.append(event)
    return events
