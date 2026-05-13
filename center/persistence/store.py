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


SCHEMA_VERSION = 1


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

