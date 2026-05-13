from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from center.core.paths import MAX_EVENT_LIMIT
from center.core.utils import now_ts
from center.persistence.store import connect_store, is_postgres_enabled


def write_event(store: Path, event: dict[str, Any]) -> None:
    stored = json.loads(json.dumps(event, ensure_ascii=False))
    stored.setdefault("received_at", now_ts())
    stored.setdefault("event_type", stored.get("type", "sensor.event"))
    raw_sample = stored.get("raw_sample") or stored.get("message")
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO events (
                        received_at, timestamp, event_type, sensor_id, module, service, severity,
                        src_ip, src_port, dst_port, raw_sample, raw_event
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
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
                        raw_sample,
                        json.dumps(stored, ensure_ascii=False, sort_keys=True),
                    ),
                )
            return

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
                raw_sample,
                json.dumps(stored, ensure_ascii=False, sort_keys=True),
            ),
        )


def read_events(store: Path, limit: int) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, MAX_EVENT_LIMIT))
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, received_at, timestamp, event_type, sensor_id, module, service, severity,
                           src_ip, src_port, dst_port, raw_sample, raw_event
                    FROM events
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
                rows = cursor.fetchall()
        else:
            if not store.exists():
                return []
            rows = connection.execute(
                """
                SELECT id, received_at, timestamp, event_type, sensor_id, module, service, severity,
                       src_ip, src_port, dst_port, raw_sample, raw_event
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    return _rows_to_events(rows)


def _rows_to_events(rows: list[Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in reversed(rows):
        raw_value = row["raw_event"]
        if isinstance(raw_value, (dict, list)):
            raw_event = raw_value
        else:
            try:
                raw_event = json.loads(raw_value)
            except Exception:
                raw_event = {"event_type": "parse_error", "raw": str(raw_value)}
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


def is_sensor_event(event: dict[str, Any]) -> bool:
    return str(event.get("event_type", "")).startswith("sensor.")


def count_by(events: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        value = str(event.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def event_matches(event: dict[str, Any], filters: dict[str, str]) -> bool:
    for key, expected in filters.items():
        if not expected:
            continue
        if str(event.get(key, "")) != expected:
            return False
    return True


def filter_events(events: list[dict[str, Any]], params: dict[str, list[str]]) -> list[dict[str, Any]]:
    filters = {
        "sensor_id": params.get("sensor_id", [""])[0],
        "module": params.get("module", [""])[0],
        "service": params.get("service", [""])[0],
        "severity": params.get("severity", [""])[0],
        "event_type": params.get("event_type", [""])[0],
    }
    suspicious_only = params.get("suspicious", ["0"])[0] in {"1", "true", "yes"}
    filtered = []
    for event in events:
        if suspicious_only and is_sensor_event(event):
            continue
        if event_matches(event, filters):
            filtered.append(event)
    return filtered


def purge_sensor_events(store: Path, sensor_id: str) -> int:
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM events WHERE sensor_id = %s", (sensor_id,))
                return int(cursor.rowcount or 0)
        if not store.exists():
            return 0
        cursor = connection.execute("DELETE FROM events WHERE sensor_id = ?", (sensor_id,))
        return int(cursor.rowcount or 0)


def database_stats(store: Path) -> dict[str, Any]:
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS c FROM events")
                total = int(cursor.fetchone()["c"])
                cursor.execute("SELECT COUNT(DISTINCT sensor_id) AS c FROM events WHERE sensor_id IS NOT NULL")
                sensors = int(cursor.fetchone()["c"])
                cursor.execute("SELECT COALESCE(MIN(received_at), 0) AS min_ts, COALESCE(MAX(received_at), 0) AS max_ts FROM events")
                period = cursor.fetchone()
        else:
            if not store.exists():
                return {"backend": "sqlite", "total_events": 0, "unique_sensors": 0, "min_received_at": 0, "max_received_at": 0}
            total = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
            sensors = int(connection.execute("SELECT COUNT(DISTINCT sensor_id) FROM events WHERE sensor_id IS NOT NULL").fetchone()[0])
            period_row = connection.execute("SELECT COALESCE(MIN(received_at),0), COALESCE(MAX(received_at),0) FROM events").fetchone()
            period = {"min_ts": period_row[0], "max_ts": period_row[1]}
    return {
        "backend": "postgres" if is_postgres_enabled() else "sqlite",
        "total_events": total,
        "unique_sensors": sensors,
        "min_received_at": float(period["min_ts"] or 0),
        "max_received_at": float(period["max_ts"] or 0),
    }


def purge_all_events(store: Path) -> int:
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM events")
                return int(cursor.rowcount or 0)
        if not store.exists():
            return 0
        cursor = connection.execute("DELETE FROM events")
        return int(cursor.rowcount or 0)
