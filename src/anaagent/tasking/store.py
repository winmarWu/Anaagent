"""任务存储（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def get_task_db_path() -> Path:
    base = Path.home() / ".anaagent" / "tasks"
    base.mkdir(parents=True, exist_ok=True)
    return base / "tasks.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_task_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_task_store() -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                task_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT NOT NULL DEFAULT '',
                error_history_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 2,
                idempotency_key TEXT NOT NULL DEFAULT ''
            )
            """
        )
        _ensure_column(conn, "tasks", "error_history_json", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, "tasks", "updated_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "tasks", "retry_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "tasks", "max_retries", "INTEGER NOT NULL DEFAULT 2")
        _ensure_column(conn, "tasks", "idempotency_key", "TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_idempotency_key ON tasks(idempotency_key)"
        )
        conn.commit()


def create_task(task_type: str, payload: dict[str, Any]) -> str:
    """兼容旧接口：创建任务并返回 task_id。"""
    task_id, _ = enqueue_task(task_type=task_type, payload=payload)
    return task_id


def enqueue_task(
    task_type: str,
    payload: dict[str, Any],
    idempotency_key: str = "",
    max_retries: int = 2,
) -> tuple[str, bool]:
    """创建任务；若 idempotency_key 已存在则返回已有任务。"""
    init_task_store()
    now = datetime.now().isoformat()
    max_retries = max(0, max_retries)
    with _get_conn() as conn:
        if idempotency_key:
            existing = conn.execute(
                "SELECT task_id FROM tasks WHERE idempotency_key = ? ORDER BY created_at DESC LIMIT 1",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return str(existing["task_id"]), False

        task_id = str(uuid.uuid4())[:12]
        conn.execute(
            """
            INSERT INTO tasks(
                task_id, status, task_type, payload_json, created_at, updated_at, max_retries, idempotency_key
            )
            VALUES (?, 'PENDING', ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                json.dumps(payload, ensure_ascii=False),
                now,
                now,
                max_retries,
                idempotency_key,
            ),
        )
        conn.commit()
    return task_id, True


def get_task(task_id: str) -> dict[str, Any] | None:
    init_task_store()
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    return _row_to_task(row)


def list_tasks(status: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_task_store()
    with _get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_task(r) for r in rows]


def claim_next_pending_task() -> dict[str, Any] | None:
    init_task_store()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        task_id = row["task_id"]
        started_at = datetime.now().isoformat()
        conn.execute(
            "UPDATE tasks SET status = 'RUNNING', started_at = ?, updated_at = ? WHERE task_id = ?",
            (started_at, started_at, task_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    return _row_to_task(updated) if updated else None


def complete_task(task_id: str, result: dict[str, Any]) -> None:
    completed_at = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET status = 'SUCCEEDED',
                result_json = ?,
                completed_at = ?,
                updated_at = ?
            WHERE task_id = ?
            """,
            (json.dumps(result, ensure_ascii=False), completed_at, completed_at, task_id),
        )
        conn.commit()


def fail_task(task_id: str, error_message: str, result: dict[str, Any] | None = None) -> None:
    completed_at = datetime.now().isoformat()
    payload = result or {}
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT error_history_json, retry_count FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        history: list[str] = []
        if row is not None:
            try:
                history = json.loads(row["error_history_json"])
            except Exception:
                history = []
        history.append(error_message)
        conn.execute(
            """
            UPDATE tasks
            SET status = 'FAILED',
                error_message = ?,
                result_json = ?,
                completed_at = ?,
                updated_at = ?,
                error_history_json = ?
            WHERE task_id = ?
            """,
            (
                error_message,
                json.dumps(payload, ensure_ascii=False),
                completed_at,
                completed_at,
                json.dumps(history, ensure_ascii=False),
                task_id,
            ),
        )
        conn.commit()


def requeue_or_fail_task(task_id: str, error_message: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    """失败后按重试上限决定回队或失败。"""
    payload = result or {}
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT retry_count, max_retries, error_history_json FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return {"task_id": task_id, "status": "MISSING"}

        retry_count = int(row["retry_count"] or 0)
        max_retries = int(row["max_retries"] or 0)
        try:
            history = json.loads(row["error_history_json"])
        except Exception:
            history = []
        history.append(error_message)
        next_retry = retry_count + 1

        if next_retry <= max_retries:
            conn.execute(
                """
                UPDATE tasks
                SET status = 'PENDING',
                    retry_count = ?,
                    error_message = ?,
                    result_json = ?,
                    started_at = '',
                    updated_at = ?,
                    error_history_json = ?
                WHERE task_id = ?
                """,
                (
                    next_retry,
                    error_message,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                    json.dumps(history, ensure_ascii=False),
                    task_id,
                ),
            )
            conn.commit()
            return {
                "task_id": task_id,
                "status": "REQUEUED",
                "retry_count": next_retry,
                "max_retries": max_retries,
            }

    failed_at = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET status = 'FAILED',
                retry_count = ?,
                error_message = ?,
                result_json = ?,
                completed_at = ?,
                updated_at = ?,
                error_history_json = ?
            WHERE task_id = ?
            """,
            (
                next_retry,
                error_message,
                json.dumps(payload, ensure_ascii=False),
                failed_at,
                failed_at,
                json.dumps(history, ensure_ascii=False),
                task_id,
            ),
        )
        conn.commit()
    return {"task_id": task_id, "status": "FAILED", "retry_count": next_retry}


def reclaim_stale_running_tasks(timeout_seconds: int = 900) -> int:
    """回收超时 RUNNING 任务（重试+1，超上限则失败）。"""
    init_task_store()
    cutoff = datetime.now() - timedelta(seconds=max(1, timeout_seconds))
    reclaimed = 0
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT task_id, started_at FROM tasks WHERE status = 'RUNNING'"
        ).fetchall()
    for row in rows:
        started_at = str(row["started_at"] or "")
        if not started_at:
            continue
        try:
            started_time = datetime.fromisoformat(started_at)
        except ValueError:
            started_time = datetime.min
        if started_time <= cutoff:
            result = requeue_or_fail_task(
                task_id=str(row["task_id"]),
                error_message=f"stale running task reclaimed after {timeout_seconds}s timeout",
            )
            if result.get("status") in {"REQUEUED", "FAILED"}:
                reclaimed += 1
    return reclaimed


def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
    try:
        error_history = json.loads(row["error_history_json"])
    except Exception:
        error_history = []
    return {
        "task_id": row["task_id"],
        "status": row["status"],
        "task_type": row["task_type"],
        "payload": json.loads(row["payload_json"]),
        "result": json.loads(row["result_json"]),
        "error_message": row["error_message"],
        "error_history": error_history,
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "updated_at": row["updated_at"],
        "retry_count": row["retry_count"],
        "max_retries": row["max_retries"],
        "idempotency_key": row["idempotency_key"],
    }


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    names = {str(r[1]) for r in rows}
    if column_name in names:
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")
