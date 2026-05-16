from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from center.core.log_normalizer import normalize_honeypot_event, raw_log_record
from center.core.paths import MAX_EVENT_LIMIT
from center.persistence.store import connect_store, is_postgres_enabled


def write_honeypot_observation(store: Path, event: dict[str, Any]) -> dict[str, Any] | None:
    raw_record = raw_log_record(event)
    normalized = normalize_honeypot_event(event)
    if raw_record is None or normalized is None:
        return None
    with connect_store(store) as connection:
        raw_id = _insert_raw_log(connection, raw_record)
        normalized["raw_log_id"] = raw_id
        normalized_id = _insert_honeypot_event(connection, normalized)
        _mark_raw_normalized(connection, raw_id, normalized_id)
    normalized["id"] = normalized_id
    return normalized


def write_honeypot_batch(store: Path, events: list[dict[str, Any]]) -> dict[str, int]:
    accepted = 0
    normalized = 0
    for event in events:
        accepted += 1
        if write_honeypot_observation(store, event):
            normalized += 1
    return {"accepted": accepted, "normalized": normalized}


def read_honeypot_events(store: Path, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, MAX_EVENT_LIMIT))
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, raw_log_id, received_at, timestamp, sensor_id, profile, device_type,
                           honeypot, service, event_type, severity, src_ip, src_port, dst_ip, dst_port,
                           username, password, command, url, http_method, user_agent, payload_sample,
                           parser_name, parser_version, raw_event
                    FROM honeypot_events
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
                SELECT id, raw_log_id, received_at, timestamp, sensor_id, profile, device_type,
                       honeypot, service, event_type, severity, src_ip, src_port, dst_ip, dst_port,
                       username, password, command, url, http_method, user_agent, payload_sample,
                       parser_name, parser_version, raw_event
                FROM honeypot_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    return [_row_to_event(row) for row in reversed(rows)]


def read_raw_honeypot_logs(store: Path, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, MAX_EVENT_LIMIT))
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, received_at, sensor_id, profile, device_type, honeypot, service,
                           source_name, source_path, container_name, raw_line, parsed_json, raw_event,
                           normalized_event_id
                    FROM raw_honeypot_logs
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
                SELECT id, received_at, sensor_id, profile, device_type, honeypot, service,
                       source_name, source_path, container_name, raw_line, parsed_json, raw_event,
                       normalized_event_id
                FROM raw_honeypot_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    return [_row_to_raw(row) for row in reversed(rows)]


def honeypot_database_stats(store: Path) -> dict[str, Any]:
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS c FROM raw_honeypot_logs")
                raw_count = int(cursor.fetchone()["c"])
                cursor.execute("SELECT COUNT(*) AS c FROM honeypot_events")
                event_count = int(cursor.fetchone()["c"])
                cursor.execute("SELECT COUNT(DISTINCT src_ip) AS c FROM honeypot_events WHERE src_ip IS NOT NULL")
                source_count = int(cursor.fetchone()["c"])
        else:
            if not store.exists():
                return {"raw_log_count": 0, "honeypot_event_count": 0, "unique_sources": 0}
            raw_count = int(connection.execute("SELECT COUNT(*) FROM raw_honeypot_logs").fetchone()[0])
            event_count = int(connection.execute("SELECT COUNT(*) FROM honeypot_events").fetchone()[0])
            source_count = int(connection.execute("SELECT COUNT(DISTINCT src_ip) FROM honeypot_events WHERE src_ip IS NOT NULL").fetchone()[0])
    return {"raw_log_count": raw_count, "honeypot_event_count": event_count, "unique_sources": source_count}


def normalize_pending_raw_logs(store: Path, limit: int = 500) -> int:
    """Normalize raw rows inserted by log-receiver without blocking ingestion."""

    pending = _read_pending_raw(store, limit)
    count = 0
    for row in pending:
        raw_event = row.get("raw_event") if isinstance(row.get("raw_event"), dict) else {}
        normalized = normalize_honeypot_event(raw_event)
        if not normalized:
            continue
        normalized["raw_log_id"] = row["id"]
        with connect_store(store) as connection:
            normalized_id = _insert_honeypot_event(connection, normalized)
            _mark_raw_normalized(connection, int(row["id"]), normalized_id)
        count += 1
    return count


def _insert_raw_log(connection: Any, record: dict[str, Any]) -> int:
    if is_postgres_enabled():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO raw_honeypot_logs (
                    received_at, sensor_id, profile, device_type, honeypot, service, source_name,
                    source_path, container_name, raw_line, parsed_json, raw_event
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                RETURNING id
                """,
                (
                    record["received_at"],
                    record.get("sensor_id"),
                    record.get("profile"),
                    record.get("device_type"),
                    record.get("honeypot"),
                    record.get("service"),
                    record.get("source_name"),
                    record.get("source_path"),
                    record.get("container_name"),
                    record.get("raw_line") or "",
                    _json_or_none(record.get("parsed_json")),
                    json.dumps(record.get("raw_event") or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
            return int(cursor.fetchone()["id"])

    cursor = connection.execute(
        """
        INSERT INTO raw_honeypot_logs (
            received_at, sensor_id, profile, device_type, honeypot, service, source_name,
            source_path, container_name, raw_line, parsed_json, raw_event
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["received_at"],
            record.get("sensor_id"),
            record.get("profile"),
            record.get("device_type"),
            record.get("honeypot"),
            record.get("service"),
            record.get("source_name"),
            record.get("source_path"),
            record.get("container_name"),
            record.get("raw_line") or "",
            _json_or_none(record.get("parsed_json")),
            json.dumps(record.get("raw_event") or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    return int(cursor.lastrowid)


def _insert_honeypot_event(connection: Any, event: dict[str, Any]) -> int:
    values = (
        event.get("raw_log_id"),
        event.get("received_at"),
        event.get("timestamp"),
        event.get("sensor_id"),
        event.get("profile"),
        event.get("device_type"),
        event.get("honeypot") or event.get("module"),
        event.get("service"),
        event.get("event_type") or "honeypot.interaction",
        event.get("severity"),
        event.get("src_ip"),
        event.get("src_port"),
        event.get("dst_ip"),
        event.get("dst_port"),
        event.get("username"),
        event.get("password"),
        event.get("command"),
        event.get("url"),
        event.get("http_method"),
        event.get("user_agent"),
        event.get("payload_sample"),
        event.get("parser_name") or "unknown",
        event.get("parser_version") or "0",
        json.dumps(event.get("raw_event") or {}, ensure_ascii=False, sort_keys=True),
    )
    if is_postgres_enabled():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO honeypot_events (
                    raw_log_id, received_at, timestamp, sensor_id, profile, device_type,
                    honeypot, service, event_type, severity, src_ip, src_port, dst_ip, dst_port,
                    username, password, command, url, http_method, user_agent, payload_sample,
                    parser_name, parser_version, raw_event
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                RETURNING id
                """,
                values,
            )
            return int(cursor.fetchone()["id"])

    cursor = connection.execute(
        """
        INSERT INTO honeypot_events (
            raw_log_id, received_at, timestamp, sensor_id, profile, device_type,
            honeypot, service, event_type, severity, src_ip, src_port, dst_ip, dst_port,
            username, password, command, url, http_method, user_agent, payload_sample,
            parser_name, parser_version, raw_event
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    return int(cursor.lastrowid)


def _mark_raw_normalized(connection: Any, raw_id: int, normalized_id: int) -> None:
    if is_postgres_enabled():
        with connection.cursor() as cursor:
            cursor.execute("UPDATE raw_honeypot_logs SET normalized_event_id = %s WHERE id = %s", (normalized_id, raw_id))
        return
    connection.execute("UPDATE raw_honeypot_logs SET normalized_event_id = ? WHERE id = ?", (normalized_id, raw_id))


def _read_pending_raw(store: Path, limit: int) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, MAX_EVENT_LIMIT))
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, raw_event
                    FROM raw_honeypot_logs
                    WHERE normalized_event_id IS NULL
                    ORDER BY id
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
                rows = cursor.fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, raw_event
                FROM raw_honeypot_logs
                WHERE normalized_event_id IS NULL
                ORDER BY id
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    return [{"id": row["id"], "raw_event": _json_value(row["raw_event"], {})} for row in rows]


def _row_to_event(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "raw_log_id": row["raw_log_id"],
        "received_at": row["received_at"],
        "timestamp": row["timestamp"],
        "sensor_id": row["sensor_id"],
        "profile": row["profile"],
        "device_type": row["device_type"],
        "honeypot": row["honeypot"],
        "module": row["honeypot"],
        "service": row["service"],
        "event_type": row["event_type"],
        "severity": row["severity"],
        "src_ip": row["src_ip"],
        "src_port": row["src_port"],
        "dst_ip": row["dst_ip"],
        "dst_port": row["dst_port"],
        "username": row["username"],
        "password": row["password"],
        "command": row["command"],
        "url": row["url"],
        "http_method": row["http_method"],
        "user_agent": row["user_agent"],
        "payload_sample": row["payload_sample"],
        "raw_event": _json_value(row["raw_event"], {}),
        "parser_name": row["parser_name"],
        "parser_version": row["parser_version"],
    }


def _row_to_raw(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "received_at": row["received_at"],
        "sensor_id": row["sensor_id"],
        "profile": row["profile"],
        "device_type": row["device_type"],
        "honeypot": row["honeypot"],
        "service": row["service"],
        "source_name": row["source_name"],
        "source_path": row["source_path"],
        "container_name": row["container_name"],
        "raw_line": row["raw_line"],
        "parsed_json": _json_value(row["parsed_json"], None),
        "raw_event": _json_value(row["raw_event"], {}),
        "normalized_event_id": row["normalized_event_id"],
    }


def _json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_value(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default
