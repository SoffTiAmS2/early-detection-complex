from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from center.core.utils import now_ts
from center.persistence.store import connect_store, is_postgres_enabled


def status_is_healthy(event: dict[str, Any]) -> bool:
    if event.get("event_type") != "sensor.status":
        return False
    if str(event.get("status") or "") != "online":
        return False
    if event.get("listener_errors"):
        return False
    for module in event.get("modules", []):
        if not isinstance(module, dict):
            continue
        status = str(module.get("status") or "")
        if status in {"failed", "degraded", "skipped"}:
            return False
    return True


def should_persist_status_event(event: dict[str, Any]) -> bool:
    """Keep noisy healthy heartbeats out of the events log.

    The latest state is still persisted in sensor_states. Only non-status events
    and unhealthy status snapshots go into events for investigation.
    """

    if event.get("event_type") != "sensor.status":
        return True
    return not status_is_healthy(event)


def write_sensor_state(store: Path, event: dict[str, Any]) -> None:
    if event.get("event_type") != "sensor.status":
        return
    sensor_id = str(event.get("sensor_id") or "")
    if not sensor_id:
        return

    updated_at = float(event.get("received_at") or event.get("timestamp") or now_ts())
    modules = event.get("modules", [])
    active_services = event.get("active_services", [])
    listener_errors = event.get("listener_errors", [])
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sensor_states (
                        sensor_id, updated_at, status, active_profile, profile, device_type,
                        config_version, applied_version, agent_mode, host, architecture,
                        modules, active_services, listener_errors, raw_status
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
                    )
                    ON CONFLICT (sensor_id) DO UPDATE SET
                        updated_at = EXCLUDED.updated_at,
                        status = EXCLUDED.status,
                        active_profile = EXCLUDED.active_profile,
                        profile = EXCLUDED.profile,
                        device_type = EXCLUDED.device_type,
                        config_version = EXCLUDED.config_version,
                        applied_version = EXCLUDED.applied_version,
                        agent_mode = EXCLUDED.agent_mode,
                        host = EXCLUDED.host,
                        architecture = EXCLUDED.architecture,
                        modules = EXCLUDED.modules,
                        active_services = EXCLUDED.active_services,
                        listener_errors = EXCLUDED.listener_errors,
                        raw_status = EXCLUDED.raw_status
                    """,
                    (
                        sensor_id,
                        updated_at,
                        event.get("status"),
                        event.get("active_profile"),
                        event.get("profile"),
                        event.get("device_type"),
                        _int_or_none(event.get("config_version")),
                        _int_or_none(event.get("applied_version")),
                        event.get("agent_mode"),
                        event.get("host"),
                        event.get("architecture"),
                        json.dumps(modules, ensure_ascii=False),
                        json.dumps(active_services, ensure_ascii=False),
                        json.dumps(listener_errors, ensure_ascii=False),
                        json.dumps(event, ensure_ascii=False),
                    ),
                )
            return

        connection.execute(
            """
            INSERT INTO sensor_states (
                sensor_id, updated_at, status, active_profile, profile, device_type,
                config_version, applied_version, agent_mode, host, architecture,
                modules, active_services, listener_errors, raw_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sensor_id) DO UPDATE SET
                updated_at=excluded.updated_at,
                status=excluded.status,
                active_profile=excluded.active_profile,
                profile=excluded.profile,
                device_type=excluded.device_type,
                config_version=excluded.config_version,
                applied_version=excluded.applied_version,
                agent_mode=excluded.agent_mode,
                host=excluded.host,
                architecture=excluded.architecture,
                modules=excluded.modules,
                active_services=excluded.active_services,
                listener_errors=excluded.listener_errors,
                raw_status=excluded.raw_status
            """,
            (
                sensor_id,
                updated_at,
                event.get("status"),
                event.get("active_profile"),
                event.get("profile"),
                event.get("device_type"),
                _int_or_none(event.get("config_version")),
                _int_or_none(event.get("applied_version")),
                event.get("agent_mode"),
                event.get("host"),
                event.get("architecture"),
                json.dumps(modules, ensure_ascii=False),
                json.dumps(active_services, ensure_ascii=False),
                json.dumps(listener_errors, ensure_ascii=False),
                json.dumps(event, ensure_ascii=False),
            ),
        )


def read_sensor_states(store: Path) -> dict[str, dict[str, Any]]:
    with connect_store(store) as connection:
        if is_postgres_enabled():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sensor_id, updated_at, status, active_profile, profile, device_type,
                           config_version, applied_version, agent_mode, host, architecture,
                           modules, active_services, listener_errors, raw_status
                    FROM sensor_states
                    """
                )
                rows = cursor.fetchall()
        else:
            if not store.exists():
                return {}
            rows = connection.execute(
                """
                SELECT sensor_id, updated_at, status, active_profile, profile, device_type,
                       config_version, applied_version, agent_mode, host, architecture,
                       modules, active_services, listener_errors, raw_status
                FROM sensor_states
                """
            ).fetchall()
    return {str(row["sensor_id"]): _row_to_state(row) for row in rows}


def _row_to_state(row: Any) -> dict[str, Any]:
    return {
        "sensor_id": row["sensor_id"],
        "last_seen": row["updated_at"],
        "last_status_seen": row["updated_at"],
        "last_event_type": "sensor.status",
        "events": 0,
        "status": row["status"] or "unknown",
        "active_profile": row["active_profile"],
        "profile": row["profile"],
        "device_type": row["device_type"],
        "config_version": row["config_version"],
        "applied_version": row["applied_version"],
        "agent_mode": row["agent_mode"],
        "host": row["host"],
        "architecture": row["architecture"],
        "modules": _json_value(row["modules"], []),
        "active_services": _json_value(row["active_services"], []),
        "listener_errors": _json_value(row["listener_errors"], []),
        "raw_status": _json_value(row["raw_status"], {}),
    }


def _json_value(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
