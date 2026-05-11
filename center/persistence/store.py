from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_VERSION = 1


def connect_store(store: Path) -> sqlite3.Connection:
    store.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(store)
    connection.row_factory = sqlite3.Row
    migrate(connection)
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
        )
        """
    )
    applied = {
        int(row["version"])
        for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
    }
    if 1 not in applied:
        apply_v1(connection)
        connection.execute("INSERT INTO schema_migrations (version) VALUES (?)", (1,))
    connection.commit()


def apply_v1(connection: sqlite3.Connection) -> None:
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

        CREATE TABLE IF NOT EXISTS install_jobs (
            id TEXT PRIMARY KEY,
            sensor_id TEXT NOT NULL,
            host TEXT NOT NULL,
            status TEXT NOT NULL,
            step TEXT NOT NULL,
            progress INTEGER NOT NULL,
            logs_json TEXT NOT NULL,
            started_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            finished_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_install_jobs_updated_at ON install_jobs(updated_at);
        CREATE INDEX IF NOT EXISTS idx_install_jobs_sensor_id ON install_jobs(sensor_id);
        """
    )
