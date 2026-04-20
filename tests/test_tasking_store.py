"""Task store tests."""

import sqlite3
from pathlib import Path

from anaagent.tasking.store import (
    claim_next_pending_task,
    create_task,
    enqueue_task,
    get_task,
    get_task_db_path,
    init_task_store,
    list_tasks,
    reclaim_stale_running_tasks,
    requeue_or_fail_task,
)


def test_create_and_get_task():
    init_task_store()
    task_id = create_task("workflow_run", {"request": "hello"})
    task = get_task(task_id)

    assert task is not None
    assert task["task_id"] == task_id
    assert task["status"] == "PENDING"
    assert task["payload"]["request"] == "hello"


def test_claim_pending_task():
    create_task("workflow_run", {"request": "task-1"})
    task = claim_next_pending_task()
    assert task is not None
    assert task["status"] == "RUNNING"


def test_list_tasks_returns_items():
    create_task("workflow_run", {"request": "task-list"})
    tasks = list_tasks(limit=5)
    assert len(tasks) > 0


def test_task_db_created():
    create_task("workflow_run", {"request": "db-check"})
    assert Path(get_task_db_path()).exists()


def test_enqueue_task_idempotency():
    task_id_1, created_1 = enqueue_task(
        "workflow_run",
        {"request": "same"},
        idempotency_key="demo-key-1",
    )
    task_id_2, created_2 = enqueue_task(
        "workflow_run",
        {"request": "same"},
        idempotency_key="demo-key-1",
    )
    assert created_1 is True
    assert created_2 is False
    assert task_id_1 == task_id_2


def test_requeue_or_fail_task_respects_retry_limit():
    task_id, _ = enqueue_task(
        "workflow_run",
        {"request": "retry"},
        max_retries=1,
    )
    first = requeue_or_fail_task(task_id, "error-1")
    assert first["status"] == "REQUEUED"

    second = requeue_or_fail_task(task_id, "error-2")
    assert second["status"] == "FAILED"
    task = get_task(task_id)
    assert task is not None
    assert task["status"] == "FAILED"
    assert task["retry_count"] >= 2


def test_reclaim_stale_running_tasks():
    task_id = create_task("workflow_run", {"request": "stale"})
    task = claim_next_pending_task()
    assert task is not None

    # 强制把 started_at 调整为很久以前
    with sqlite3.connect(get_task_db_path()) as conn:
        conn.execute(
            "UPDATE tasks SET started_at = '2000-01-01T00:00:00' WHERE task_id = ?",
            (task_id,),
        )
        conn.commit()

    reclaimed = reclaim_stale_running_tasks(timeout_seconds=1)
    assert reclaimed >= 1
