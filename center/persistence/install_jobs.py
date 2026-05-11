from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from center.core.utils import now_ts
from center.persistence.store import connect_store


def save_install_job(store: Path, job: dict[str, Any]) -> None:
    public = {key: value for key, value in job.items() if key not in {"process", "ssh_password", "_store_path"}}
    logs_json = json.dumps(public.get("logs", []), ensure_ascii=False)
    with connect_store(store) as connection:
        connection.execute(
            """
            INSERT INTO install_jobs (
                id, sensor_id, host, status, step, progress, logs_json,
                started_at, updated_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                sensor_id = excluded.sensor_id,
                host = excluded.host,
                status = excluded.status,
                step = excluded.step,
                progress = excluded.progress,
                logs_json = excluded.logs_json,
                updated_at = excluded.updated_at,
                finished_at = excluded.finished_at
            """,
            (
                public["id"],
                public["sensor_id"],
                public["host"],
                public["status"],
                public["step"],
                int(public["progress"]),
                logs_json,
                float(public["started_at"]),
                float(public["updated_at"]),
                public.get("finished_at"),
            ),
        )


def list_install_jobs(store: Path, limit: int = 100) -> list[dict[str, Any]]:
    if not store.exists():
        return []
    with connect_store(store) as connection:
        rows = connection.execute(
            """
            SELECT id, sensor_id, host, status, step, progress, logs_json,
                   started_at, updated_at, finished_at
            FROM install_jobs
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_to_job(row) for row in rows]


def get_install_job(store: Path, job_id: str) -> dict[str, Any] | None:
    if not store.exists():
        return None
    with connect_store(store) as connection:
        row = connection.execute(
            """
            SELECT id, sensor_id, host, status, step, progress, logs_json,
                   started_at, updated_at, finished_at
            FROM install_jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()
    return row_to_job(row) if row else None


def row_to_job(row: Any) -> dict[str, Any]:
    try:
        logs = json.loads(row["logs_json"])
    except json.JSONDecodeError:
        logs = []
    return {
        "id": row["id"],
        "sensor_id": row["sensor_id"],
        "host": row["host"],
        "status": row["status"],
        "step": row["step"],
        "progress": row["progress"],
        "logs": logs if isinstance(logs, list) else [],
        "started_at": row["started_at"],
        "updated_at": row["updated_at"],
        "finished_at": row["finished_at"],
    }


def mark_finished(job: dict[str, Any]) -> None:
    job["finished_at"] = now_ts()
