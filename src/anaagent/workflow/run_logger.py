"""Workflow 运行日志。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anaagent.environment import get_current_environment


def resolve_logs_dir(workspace_dir: str = "") -> Path:
    """解析日志目录，优先团队环境目录。"""
    env_path = get_current_environment()
    if env_path:
        logs_dir = env_path / "logs"
    elif workspace_dir:
        logs_dir = Path(workspace_dir).resolve() / ".anaagent-logs"
    else:
        logs_dir = Path.cwd() / ".anaagent-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def write_workflow_log(state: dict[str, Any], workspace_dir: str = "") -> Path:
    """将 workflow 最终状态落盘为 JSON。"""
    logs_dir = resolve_logs_dir(workspace_dir=workspace_dir)
    workflow_id = state.get("workflow_id", "unknown")
    log_path = logs_dir / f"workflow_{workflow_id}.json"
    payload = {
        "workflow_id": workflow_id,
        "status": "success" if state.get("success", False) else "failed",
        "user_request": state.get("user_request", ""),
        "team_name": state.get("team_name", ""),
        "current_stage": state.get("current_stage", ""),
        "started_at": state.get("started_at", ""),
        "completed_at": state.get("completed_at", ""),
        "workspace_dir": state.get("workspace_dir", ""),
        "error_message": state.get("error_message", ""),
        "outputs": state.get("outputs", []),
        "tool_calls": state.get("tool_calls", []),
        "command_results": state.get("command_results", []),
        "artifacts": state.get("artifacts", []),
        "final_result": state.get("final_result", ""),
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return log_path
