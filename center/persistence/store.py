from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - optional in sqlite-only local setup
    psycopg = None
    dict_row = None


SCHEMA_VERSION = 4


def db_dsn() -> str:
    return os.environ.get("CENTER_DB_DSN", "").strip()


def is_postgres_enabled() -> bool:
    return db_dsn().startswith("postgres")


@contextmanager
def connect_store(store: Path) -> Iterator[Any]:
    if is_postgres_enabled():
        if psycopg is None:
            raise RuntimeError("postgres backend requested but psycopg is not installed")
        connection = psycopg.connect(db_dsn(), row_factory=dict_row)
        try:
            migrate_postgres(connection)
            yield connection
            connection.commit()
        finally:
            connection.close()
        return

    store.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(store)
    connection.row_factory = sqlite3.Row
    try:
        migrate_sqlite(connection)
        yield connection
        connection.commit()
    finally:
        connection.close()


def migrate_postgres(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute("SELECT version FROM schema_migrations")
        applied = {int(row["version"]) for row in cursor.fetchall()}
        if 1 not in applied:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id BIGSERIAL PRIMARY KEY,
                    received_at DOUBLE PRECISION NOT NULL,
                    timestamp DOUBLE PRECISION NULL,
                    event_type TEXT NOT NULL,
                    sensor_id TEXT NULL,
                    module TEXT NULL,
                    service TEXT NULL,
                    severity TEXT NULL,
                    src_ip TEXT NULL,
                    src_port INTEGER NULL,
                    dst_port INTEGER NULL,
                    raw_sample TEXT NULL,
                    raw_event JSONB NOT NULL
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_received_at ON events(received_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_sensor_id ON events(sensor_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_module ON events(module)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_service ON events(service)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type)")
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (1)")
        if 2 not in applied:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sensor_states (
                    sensor_id TEXT PRIMARY KEY,
                    updated_at DOUBLE PRECISION NOT NULL,
                    status TEXT NULL,
                    active_profile TEXT NULL,
                    profile TEXT NULL,
                    device_type TEXT NULL,
                    config_version INTEGER NULL,
                    applied_version INTEGER NULL,
                    agent_mode TEXT NULL,
                    host TEXT NULL,
                    architecture TEXT NULL,
                    modules JSONB NOT NULL,
                    active_services JSONB NOT NULL,
                    listener_errors JSONB NOT NULL,
                    raw_status JSONB NOT NULL
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sensor_states_updated_at ON sensor_states(updated_at)")
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (2)")
        if 3 not in applied:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_honeypot_logs (
                    id BIGSERIAL PRIMARY KEY,
                    received_at DOUBLE PRECISION NOT NULL,
                    sensor_id TEXT NULL,
                    profile TEXT NULL,
                    device_type TEXT NULL,
                    honeypot TEXT NULL,
                    service TEXT NULL,
                    source_name TEXT NULL,
                    source_path TEXT NULL,
                    container_name TEXT NULL,
                    raw_line TEXT NOT NULL,
                    parsed_json JSONB NULL,
                    raw_event JSONB NOT NULL,
                    normalized_event_id BIGINT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS honeypot_events (
                    id BIGSERIAL PRIMARY KEY,
                    raw_log_id BIGINT NULL REFERENCES raw_honeypot_logs(id) ON DELETE SET NULL,
                    received_at DOUBLE PRECISION NOT NULL,
                    timestamp DOUBLE PRECISION NULL,
                    sensor_id TEXT NULL,
                    profile TEXT NULL,
                    device_type TEXT NULL,
                    honeypot TEXT NULL,
                    service TEXT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NULL,
                    src_ip TEXT NULL,
                    src_port INTEGER NULL,
                    dst_ip TEXT NULL,
                    dst_port INTEGER NULL,
                    username TEXT NULL,
                    password TEXT NULL,
                    command TEXT NULL,
                    url TEXT NULL,
                    http_method TEXT NULL,
                    user_agent TEXT NULL,
                    payload_sample TEXT NULL,
                    parser_name TEXT NOT NULL,
                    parser_version TEXT NOT NULL,
                    raw_event JSONB NOT NULL
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_received_at ON raw_honeypot_logs(received_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_sensor_id ON raw_honeypot_logs(sensor_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_honeypot ON raw_honeypot_logs(honeypot)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_normalized_event_id ON raw_honeypot_logs(normalized_event_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_honeypot_events_received_at ON honeypot_events(received_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_honeypot_events_sensor_id ON honeypot_events(sensor_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_honeypot_events_profile ON honeypot_events(profile)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_honeypot_events_honeypot ON honeypot_events(honeypot)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_honeypot_events_service ON honeypot_events(service)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_honeypot_events_event_type ON honeypot_events(event_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_honeypot_events_src_ip ON honeypot_events(src_ip)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_honeypot_events_dst_port ON honeypot_events(dst_port)")
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (3)")
        if 4 not in applied:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_honeypot_events_severity ON honeypot_events(severity)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_honeypot_events_device_type ON honeypot_events(device_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_service ON raw_honeypot_logs(service)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_profile ON raw_honeypot_logs(profile)")
            cursor.execute(
                """
                CREATE OR REPLACE VIEW honeypot_event_readable AS
                SELECT
                    id,
                    raw_log_id,
                    received_at,
                    to_timestamp(received_at) AS received_time,
                    sensor_id,
                    profile,
                    device_type,
                    honeypot,
                    service,
                    event_type,
                    severity,
                    src_ip,
                    src_port,
                    dst_ip,
                    dst_port,
                    COALESCE(src_ip, '') ||
                        CASE WHEN src_port IS NULL THEN '' ELSE ':' || src_port::text END AS source,
                    COALESCE(dst_ip, '') ||
                        CASE WHEN dst_port IS NULL THEN '' ELSE ':' || dst_port::text END AS destination,
                    NULLIF(
                        COALESCE(username, '') ||
                        CASE WHEN password IS NULL THEN '' ELSE ':' || password END,
                        ''
                    ) AS credential,
                    COALESCE(command, url, payload_sample, '') AS evidence,
                    LEFT(COALESCE(payload_sample, ''), 500) AS sample,
                    raw_event
                FROM honeypot_events
                """
            )
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (4)")


def migrate_sqlite(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
        )
        """
    )
    applied = {int(row["version"]) for row in connection.execute("SELECT version FROM schema_migrations").fetchall()}
    if 1 not in applied:
        connection.executescript(
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
            );
            CREATE INDEX IF NOT EXISTS idx_events_received_at ON events(received_at);
            CREATE INDEX IF NOT EXISTS idx_events_sensor_id ON events(sensor_id);
            CREATE INDEX IF NOT EXISTS idx_events_module ON events(module);
            CREATE INDEX IF NOT EXISTS idx_events_service ON events(service);
            CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
            CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
            """
        )
        connection.execute("INSERT INTO schema_migrations (version) VALUES (?)", (1,))
    if 2 not in applied:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sensor_states (
                sensor_id TEXT PRIMARY KEY,
                updated_at REAL NOT NULL,
                status TEXT,
                active_profile TEXT,
                profile TEXT,
                device_type TEXT,
                config_version INTEGER,
                applied_version INTEGER,
                agent_mode TEXT,
                host TEXT,
                architecture TEXT,
                modules TEXT NOT NULL,
                active_services TEXT NOT NULL,
                listener_errors TEXT NOT NULL,
                raw_status TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sensor_states_updated_at ON sensor_states(updated_at);
            """
        )
        connection.execute("INSERT INTO schema_migrations (version) VALUES (?)", (2,))
    if 3 not in applied:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS raw_honeypot_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at REAL NOT NULL,
                sensor_id TEXT,
                profile TEXT,
                device_type TEXT,
                honeypot TEXT,
                service TEXT,
                source_name TEXT,
                source_path TEXT,
                container_name TEXT,
                raw_line TEXT NOT NULL,
                parsed_json TEXT,
                raw_event TEXT NOT NULL,
                normalized_event_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS honeypot_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_log_id INTEGER,
                received_at REAL NOT NULL,
                timestamp REAL,
                sensor_id TEXT,
                profile TEXT,
                device_type TEXT,
                honeypot TEXT,
                service TEXT,
                event_type TEXT NOT NULL,
                severity TEXT,
                src_ip TEXT,
                src_port INTEGER,
                dst_ip TEXT,
                dst_port INTEGER,
                username TEXT,
                password TEXT,
                command TEXT,
                url TEXT,
                http_method TEXT,
                user_agent TEXT,
                payload_sample TEXT,
                parser_name TEXT NOT NULL,
                parser_version TEXT NOT NULL,
                raw_event TEXT NOT NULL,
                FOREIGN KEY(raw_log_id) REFERENCES raw_honeypot_logs(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_received_at ON raw_honeypot_logs(received_at);
            CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_sensor_id ON raw_honeypot_logs(sensor_id);
            CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_honeypot ON raw_honeypot_logs(honeypot);
            CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_normalized_event_id ON raw_honeypot_logs(normalized_event_id);
            CREATE INDEX IF NOT EXISTS idx_honeypot_events_received_at ON honeypot_events(received_at);
            CREATE INDEX IF NOT EXISTS idx_honeypot_events_sensor_id ON honeypot_events(sensor_id);
            CREATE INDEX IF NOT EXISTS idx_honeypot_events_profile ON honeypot_events(profile);
            CREATE INDEX IF NOT EXISTS idx_honeypot_events_honeypot ON honeypot_events(honeypot);
            CREATE INDEX IF NOT EXISTS idx_honeypot_events_service ON honeypot_events(service);
            CREATE INDEX IF NOT EXISTS idx_honeypot_events_event_type ON honeypot_events(event_type);
            CREATE INDEX IF NOT EXISTS idx_honeypot_events_src_ip ON honeypot_events(src_ip);
            CREATE INDEX IF NOT EXISTS idx_honeypot_events_dst_port ON honeypot_events(dst_port);
            """
        )
        connection.execute("INSERT INTO schema_migrations (version) VALUES (?)", (3,))
    if 4 not in applied:
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_honeypot_events_severity ON honeypot_events(severity);
            CREATE INDEX IF NOT EXISTS idx_honeypot_events_device_type ON honeypot_events(device_type);
            CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_service ON raw_honeypot_logs(service);
            CREATE INDEX IF NOT EXISTS idx_raw_honeypot_logs_profile ON raw_honeypot_logs(profile);
            DROP VIEW IF EXISTS honeypot_event_readable;
            CREATE VIEW honeypot_event_readable AS
            SELECT
                id,
                raw_log_id,
                received_at,
                datetime(received_at, 'unixepoch') AS received_time,
                sensor_id,
                profile,
                device_type,
                honeypot,
                service,
                event_type,
                severity,
                src_ip,
                src_port,
                dst_ip,
                dst_port,
                COALESCE(src_ip, '') ||
                    CASE WHEN src_port IS NULL THEN '' ELSE ':' || CAST(src_port AS TEXT) END AS source,
                COALESCE(dst_ip, '') ||
                    CASE WHEN dst_port IS NULL THEN '' ELSE ':' || CAST(dst_port AS TEXT) END AS destination,
                NULLIF(
                    COALESCE(username, '') ||
                    CASE WHEN password IS NULL THEN '' ELSE ':' || password END,
                    ''
                ) AS credential,
                COALESCE(command, url, payload_sample, '') AS evidence,
                substr(COALESCE(payload_sample, ''), 1, 500) AS sample,
                raw_event
            FROM honeypot_events;
            """
        )
        connection.execute("INSERT INTO schema_migrations (version) VALUES (?)", (4,))
