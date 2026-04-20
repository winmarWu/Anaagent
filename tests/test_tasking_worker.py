"""Task worker tests."""

from anaagent.tasking.store import create_task, get_task
from anaagent.tasking.worker import process_pending_tasks_once


def test_worker_processes_task_success(monkeypatch):
    task_id = create_task(
        "workflow_run",
        {
            "request": "实现 hello",
            "project_dir": "",
            "test_command": "pytest -q",
            "callback_url": "",
        },
    )

    def _fake_run_workflow(**kwargs):
        return {
            "workflow_id": "wf-001",
            "success": True,
            "current_stage": "done",
            "run_log_path": "/tmp/log.json",
        }

    monkeypatch.setattr("anaagent.tasking.worker.run_workflow", _fake_run_workflow)
    info = process_pending_tasks_once()
    assert info["status"] == "processed"
    assert info["success"] is True

    task = get_task(task_id)
    assert task is not None
    assert task["status"] == "SUCCEEDED"
    assert task["result"]["workflow_id"] == "wf-001"


def test_worker_processes_task_failure(monkeypatch):
    from anaagent.tasking.store import enqueue_task

    task_id, _ = enqueue_task(
        "workflow_run",
        {"request": "实现 hello", "project_dir": "", "test_command": "pytest -q", "callback_url": ""},
        max_retries=0,
    )

    def _fake_run_workflow(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("anaagent.tasking.worker.run_workflow", _fake_run_workflow)
    info = process_pending_tasks_once()
    assert info["status"] == "processed"
    assert info["success"] is False

    task = get_task(task_id)
    assert task is not None
    assert task["status"] == "FAILED"
    assert "boom" in task["error_message"]


def test_worker_failure_requeues_when_retries_remaining(monkeypatch):
    from anaagent.tasking.store import enqueue_task

    task_id, _ = enqueue_task(
        "workflow_run",
        {"request": "实现 hello", "project_dir": "", "test_command": "pytest -q", "callback_url": ""},
        max_retries=1,
    )

    def _fake_run_workflow(**kwargs):
        raise RuntimeError("retry me")

    monkeypatch.setattr("anaagent.tasking.worker.run_workflow", _fake_run_workflow)
    info = process_pending_tasks_once()
    assert info["status"] == "processed"
    assert info["success"] is False
    assert info["retry"]["status"] == "REQUEUED"

    task = get_task(task_id)
    assert task is not None
    assert task["status"] == "PENDING"
    assert task["retry_count"] == 1
