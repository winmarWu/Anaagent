"""本地任务 Worker。"""

from __future__ import annotations

import time
from typing import Any

from anaagent.workflow import run_workflow
from anaagent.workflow.notifier import send_webhook_notification

from .store import (
    claim_next_pending_task,
    complete_task,
    reclaim_stale_running_tasks,
    requeue_or_fail_task,
)


def process_pending_tasks_once(stale_timeout_seconds: int = 900) -> dict[str, Any]:
    """处理一个待执行任务；无任务时返回 idle。"""
    reclaimed = reclaim_stale_running_tasks(timeout_seconds=stale_timeout_seconds)
    task = claim_next_pending_task()
    if task is None:
        return {"status": "idle", "reclaimed": reclaimed}

    task_id = task["task_id"]
    payload = task["payload"]
    callback_url = str(payload.get("callback_url", ""))
    try:
        result = run_workflow(
            user_request=str(payload.get("request", "")),
            team_name=str(payload.get("team_name", "")),
            task_description=str(payload.get("task_description", "")),
            workflow_type=str(payload.get("workflow_type", "software_company")),
            workspace_dir=str(payload.get("project_dir", "")),
            webhook_url=str(payload.get("workflow_webhook_url", "")),
            test_command=str(payload.get("test_command", "pytest -q")),
        )
        complete_task(task_id, result)
        if callback_url:
            send_webhook_notification(
                callback_url,
                {
                    "task_id": task_id,
                    "status": "SUCCEEDED",
                    "workflow_id": result.get("workflow_id", ""),
                    "current_stage": result.get("current_stage", ""),
                    "run_log_path": result.get("run_log_path", ""),
                },
            )
        return {"status": "processed", "task_id": task_id, "success": True}
    except Exception as exc:
        retry_result = requeue_or_fail_task(task_id, str(exc))
        if callback_url:
            callback_status = "FAILED" if retry_result.get("status") == "FAILED" else "RETRYING"
            send_webhook_notification(
                callback_url,
                {"task_id": task_id, "status": callback_status, "error_message": str(exc)},
            )
        return {
            "status": "processed",
            "task_id": task_id,
            "success": False,
            "error": str(exc),
            "retry": retry_result,
        }


def run_worker_loop(poll_interval_seconds: int = 2, stale_timeout_seconds: int = 900) -> None:
    """持续轮询并处理任务。"""
    while True:
        process_pending_tasks_once(stale_timeout_seconds=stale_timeout_seconds)
        time.sleep(max(1, poll_interval_seconds))
