from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from center.core.log_normalizer import normalize_honeypot_event, raw_log_record
from center.core.paths import MAX_EVENT_LIMIT
from center.persistence.store import connect_store, is_postgres_enabled

HoneypotFilters = dict[str, str]


def write_honeypot_observation(store: Path, event: dict[str, Any]) -> dict[str, Any] | None:
    raw_record = raw_log_record(event)
    normalized = normalize_honeypot_event(event)
    if raw_record is None:
        return None
    with connect_store(store) as connection:
        raw_id = _insert_raw_log(connection, raw_record)
        if normalized is None:
            return None
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


def read_honeypot_events(store: Path, limit: int = 100, filters: HoneypotFilters | None = None) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, MAX_EVENT_LIMIT))
    with connect_store(store) as connection:
        where_sql, values = _honeypot_event_where(filters or {})
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, raw_log_id, received_at, timestamp, sensor_id, profile, device_type,
                           honeypot, service, event_type, severity, src_ip, src_port, dst_ip, dst_port,
                           username, password, command, url, http_method, user_agent, payload_sample,
                           parser_name, parser_version, raw_event
                    FROM honeypot_events
                    {where_sql}
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (*values, safe_limit),
                )
                rows = cursor.fetchall()
        else:
            if not store.exists():
                return []
            rows = connection.execute(
                f"""
                SELECT id, raw_log_id, received_at, timestamp, sensor_id, profile, device_type,
                       honeypot, service, event_type, severity, src_ip, src_port, dst_ip, dst_port,
                       username, password, command, url, http_method, user_agent, payload_sample,
                       parser_name, parser_version, raw_event
                FROM honeypot_events
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                (*values, safe_limit),
            ).fetchall()
    return [_row_to_event(row) for row in reversed(rows)]


def read_raw_honeypot_logs(store: Path, limit: int = 100, filters: HoneypotFilters | None = None) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, MAX_EVENT_LIMIT))
    with connect_store(store) as connection:
        where_sql, values = _raw_log_where(filters or {})
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, received_at, sensor_id, profile, device_type, honeypot, service,
                           source_name, source_path, container_name, raw_line, parsed_json, raw_event,
                           normalized_event_id
                    FROM raw_honeypot_logs
                    {where_sql}
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (*values, safe_limit),
                )
                rows = cursor.fetchall()
        else:
            if not store.exists():
                return []
            rows = connection.execute(
                f"""
                SELECT id, received_at, sensor_id, profile, device_type, honeypot, service,
                       source_name, source_path, container_name, raw_line, parsed_json, raw_event,
                       normalized_event_id
                FROM raw_honeypot_logs
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                (*values, safe_limit),
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
                cursor.execute("SELECT COUNT(*) AS c FROM honeypot_events WHERE severity = 'high'")
                high_count = int(cursor.fetchone()["c"])
                cursor.execute("SELECT COUNT(*) AS c FROM honeypot_events WHERE username IS NOT NULL OR password IS NOT NULL")
                credential_count = int(cursor.fetchone()["c"])
                cursor.execute("SELECT COALESCE(MAX(received_at), 0) AS ts FROM honeypot_events")
                latest = float(cursor.fetchone()["ts"] or 0)
        else:
            if not store.exists():
                return _empty_stats()
            raw_count = int(connection.execute("SELECT COUNT(*) FROM raw_honeypot_logs").fetchone()[0])
            event_count = int(connection.execute("SELECT COUNT(*) FROM honeypot_events").fetchone()[0])
            source_count = int(connection.execute("SELECT COUNT(DISTINCT src_ip) FROM honeypot_events WHERE src_ip IS NOT NULL").fetchone()[0])
            high_count = int(connection.execute("SELECT COUNT(*) FROM honeypot_events WHERE severity = 'high'").fetchone()[0])
            credential_count = int(connection.execute("SELECT COUNT(*) FROM honeypot_events WHERE username IS NOT NULL OR password IS NOT NULL").fetchone()[0])
            latest = float(connection.execute("SELECT COALESCE(MAX(received_at), 0) FROM honeypot_events").fetchone()[0] or 0)
    return {
        "raw_log_count": raw_count,
        "honeypot_event_count": event_count,
        "unique_sources": source_count,
        "high_honeypot_events": high_count,
        "credential_events": credential_count,
        "latest_honeypot_received_at": latest,
        "by_severity": _group_counts(store, "severity", "honeypot_events"),
        "top_sources": _group_counts(store, "src_ip", "honeypot_events", where="src_ip IS NOT NULL"),
        "top_profiles": _group_counts(store, "profile", "honeypot_events"),
        "top_honeypots": _group_counts(store, "honeypot", "honeypot_events"),
        "top_services": _group_counts(store, "service", "honeypot_events"),
        "top_ports": _group_counts(store, "dst_port", "honeypot_events", where="dst_port IS NOT NULL"),
    }


def normalize_pending_raw_logs(store: Path, limit: int = 500) -> int:
    """Normalize raw rows inserted by log-receiver without blocking ingestion."""

    pending = _claim_pending_raw(store, limit)
    count = 0
    for row in pending:
        raw_event = row.get("raw_event") if isinstance(row.get("raw_event"), dict) else {}
        normalized = normalize_honeypot_event(raw_event)
        if not normalized:
            with connect_store(store) as connection:
                _mark_raw_skipped(connection, int(row["id"]))
            continue
        normalized["raw_log_id"] = row["id"]
        with connect_store(store) as connection:
            normalized_id = _insert_honeypot_event(connection, normalized)
            _mark_raw_normalized(connection, int(row["id"]), normalized_id)
        count += 1
    return count


def reparse_honeypot_events(store: Path, batch_size: int = 500) -> dict[str, int]:
    """Rebuild normalized honeypot_events from preserved raw_honeypot_logs."""

    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS c FROM raw_honeypot_logs")
                raw_count = int(cursor.fetchone()["c"])
                cursor.execute("DELETE FROM honeypot_events")
                cursor.execute("UPDATE raw_honeypot_logs SET normalized_event_id = NULL")
        else:
            if not store.exists():
                return {"raw": 0, "normalized": 0, "skipped": 0}
            raw_count = int(connection.execute("SELECT COUNT(*) FROM raw_honeypot_logs").fetchone()[0])
            connection.execute("DELETE FROM honeypot_events")
            connection.execute("UPDATE raw_honeypot_logs SET normalized_event_id = NULL")

    normalized = 0
    safe_batch = max(1, min(int(batch_size), MAX_EVENT_LIMIT))
    while _pending_raw_count(store) > 0:
        normalized += normalize_pending_raw_logs(store, safe_batch)
    return {"raw": raw_count, "normalized": normalized, "skipped": raw_count - normalized}


def _empty_stats() -> dict[str, Any]:
    return {
        "raw_log_count": 0,
        "honeypot_event_count": 0,
        "unique_sources": 0,
        "high_honeypot_events": 0,
        "credential_events": 0,
        "latest_honeypot_received_at": 0,
        "by_severity": [],
        "top_sources": [],
        "top_profiles": [],
        "top_honeypots": [],
        "top_services": [],
        "top_ports": [],
    }


def _group_counts(store: Path, column: str, table: str, where: str = "", limit: int = 8) -> list[dict[str, Any]]:
    allowed_columns = {"severity", "src_ip", "profile", "honeypot", "service", "dst_port"}
    allowed_tables = {"honeypot_events"}
    if column not in allowed_columns or table not in allowed_tables:
        return []
    safe_where = f"WHERE {where}" if where else f"WHERE {column} IS NOT NULL"
    safe_limit = max(1, min(limit, 20))
    label_expr = f"COALESCE(CAST({column} AS TEXT), 'unknown')"
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {label_expr} AS label, COUNT(*) AS count
                    FROM {table}
                    {safe_where}
                    GROUP BY 1
                    ORDER BY count DESC, label ASC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
                rows = cursor.fetchall()
        else:
            rows = connection.execute(
                f"""
                SELECT {label_expr} AS label, COUNT(*) AS count
                FROM {table}
                {safe_where}
                GROUP BY 1
                ORDER BY count DESC, label ASC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    return [{"label": str(row["label"]), "count": int(row["count"])} for row in rows]


def _honeypot_event_where(filters: HoneypotFilters) -> tuple[str, list[Any]]:
    exact_columns = {
        "sensor_id": "sensor_id",
        "profile": "profile",
        "device_type": "device_type",
        "honeypot": "honeypot",
        "module": "honeypot",
        "service": "service",
        "event_type": "event_type",
        "severity": "severity",
        "src_ip": "src_ip",
        "dst_port": "dst_port",
    }
    return _where_clause(
        filters,
        exact_columns,
        ["payload_sample", "url", "command", "user_agent", "username", "password", "src_ip", "raw_event"],
    )


def _raw_log_where(filters: HoneypotFilters) -> tuple[str, list[Any]]:
    exact_columns = {
        "sensor_id": "sensor_id",
        "profile": "profile",
        "device_type": "device_type",
        "honeypot": "honeypot",
        "module": "honeypot",
        "service": "service",
        "source_name": "source_name",
        "container_name": "container_name",
    }
    return _where_clause(filters, exact_columns, ["raw_line", "source_name", "source_path", "container_name", "raw_event"])


def _where_clause(filters: HoneypotFilters, exact_columns: dict[str, str], search_columns: list[str]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    pg = is_postgres_enabled()
    placeholder = "%s" if pg else "?"
    for key, column in exact_columns.items():
        value = str(filters.get(key) or "").strip()
        if not value:
            continue
        if key == "dst_port":
            try:
                values.append(int(value))
            except ValueError:
                continue
        else:
            values.append(value)
        clauses.append(f"{column} = {placeholder}")

    query = str(filters.get("q") or "").strip()
    if query:
        like_value = f"%{query}%"
        search_parts: list[str] = []
        for column in search_columns:
            if pg:
                expr = f"{column}::text ILIKE {placeholder}" if column == "raw_event" else f"{column} ILIKE {placeholder}"
            else:
                expr = f"LOWER(COALESCE(CAST({column} AS TEXT), '')) LIKE LOWER({placeholder})"
            search_parts.append(expr)
            values.append(like_value)
        clauses.append("(" + " OR ".join(search_parts) + ")")

    if not clauses:
        return "", values
    return "WHERE " + " AND ".join(clauses), values


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


def _mark_raw_skipped(connection: Any, raw_id: int) -> None:
    if is_postgres_enabled():
        with connection.cursor() as cursor:
            cursor.execute("UPDATE raw_honeypot_logs SET normalized_event_id = 0 WHERE id = %s", (raw_id,))
        return
    connection.execute("UPDATE raw_honeypot_logs SET normalized_event_id = 0 WHERE id = ?", (raw_id,))


def _pending_raw_count(store: Path) -> int:
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS c FROM raw_honeypot_logs WHERE normalized_event_id IS NULL")
                return int(cursor.fetchone()["c"])
        if not store.exists():
            return 0
        return int(connection.execute("SELECT COUNT(*) FROM raw_honeypot_logs WHERE normalized_event_id IS NULL").fetchone()[0])


def _claim_pending_raw(store: Path, limit: int) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, MAX_EVENT_LIMIT))
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH picked AS (
                        SELECT id
                        FROM raw_honeypot_logs
                        WHERE normalized_event_id IS NULL
                        ORDER BY id
                        LIMIT %s
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE raw_honeypot_logs
                    SET normalized_event_id = -1
                    WHERE id IN (SELECT id FROM picked)
                    RETURNING id, raw_event
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
            ids = [int(row["id"]) for row in rows]
            if ids:
                placeholders = ", ".join("?" for _ in ids)
                connection.execute(
                    f"UPDATE raw_honeypot_logs SET normalized_event_id = -1 WHERE id IN ({placeholders})",
                    ids,
                )
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
