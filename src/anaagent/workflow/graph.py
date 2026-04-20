"""LangGraph 工作流图定义"""

import json
import os
from pathlib import Path
from typing import Literal

import yaml
from langgraph.graph import END, StateGraph

from anaagent.config_manager import get_base_config
from anaagent.environment import get_envs_dir
from anaagent.workflow.notifier import send_webhook_notification
from anaagent.workflow.nodes import dev_node, pm_node, review_node, test_node
from anaagent.workflow.run_logger import write_workflow_log
from anaagent.workflow.state import WorkflowStage, WorkflowState, create_initial_state


def create_software_workflow() -> StateGraph:
    """
    创建软件开发工作流图

    流程：
    PM (需求分析) -> Dev (开发) -> Review (审查) -> Test (测试)
                                              |
                                              v
                                         (如需修改)
                                              |
                                              v
                                           Dev (修改)
    """
    workflow = StateGraph(WorkflowState)

    # 添加节点
    workflow.add_node("pm", pm_node)
    workflow.add_node("dev", dev_node)
    workflow.add_node("review", review_node)
    workflow.add_node("test", test_node)

    # 设置入口点
    workflow.set_entry_point("pm")

    # 定义边：PM -> Dev
    workflow.add_edge("pm", "dev")

    # 定义边：Dev -> Test
    workflow.add_edge("dev", "test")

    # 定义边：Test -> Review
    workflow.add_edge("test", "review")

    # 定义条件边：Review -> Dev 或 End
    def review_router(state: WorkflowState) -> Literal["dev", "__end__"]:
        """根据审查结果决定下一步"""
        current_stage = state.get("current_stage", "")
        if current_stage == WorkflowStage.FAILED.value:
            return "__end__"

        needs_revision = state.get("needs_revision", False)
        if needs_revision:
            return "dev"
        return "__end__"

    workflow.add_conditional_edges(
        "review",
        review_router,
        {
            "dev": "dev",
            "__end__": END,
        },
    )

    return workflow


def create_simple_dev_workflow() -> StateGraph:
    """
    简单开发流：Dev -> Test -> END（跳过 PM 与审查）
    """
    workflow = StateGraph(WorkflowState)
    workflow.add_node("dev", dev_node)
    workflow.add_node("test", test_node)
    workflow.set_entry_point("dev")
    workflow.add_edge("dev", "test")
    workflow.add_edge("test", END)
    return workflow


def create_review_only_workflow() -> StateGraph:
    """
    仅审查流：Review -> END（适合已在 task_description / 状态中提供代码上下文的场景）
    """
    workflow = StateGraph(WorkflowState)
    workflow.add_node("review", review_node)
    workflow.set_entry_point("review")
    workflow.add_edge("review", END)
    return workflow


# 预定义的工作流类型（须在 _compile_workflow 之前定义）
WORKFLOW_TYPES = {
    "software_company": {
        "name": "软件公司工作流",
        "description": "完整的软件开发生命周期：PM -> Dev -> Review -> Test",
        "nodes": ["pm", "dev", "review", "test"],
        "create": create_software_workflow,
    },
    "simple_dev": {
        "name": "简单开发工作流",
        "description": "直接开发，无审查：Dev -> Test",
        "nodes": ["dev", "test"],
        "create": create_simple_dev_workflow,
    },
    "review_only": {
        "name": "仅审查工作流",
        "description": "已有代码，仅进行审查：Review",
        "nodes": ["review"],
        "create": create_review_only_workflow,
    },
}


def _compile_workflow(workflow_type: str) -> StateGraph:
    spec = WORKFLOW_TYPES.get(workflow_type)
    if not spec:
        raise ValueError(f"未知工作流类型: {workflow_type}")
    factory = spec.get("create")
    if factory is None:
        raise ValueError(f"工作流类型未实现: {workflow_type}")
    return factory()


def _infer_team_path(team_name: str, workspace_dir: str) -> Path | None:
    """根据 team_name 或 workspace_dir 推断团队目录。"""
    if team_name:
        path = get_envs_dir() / team_name
        if path.exists():
            return path

    if workspace_dir:
        workspace = Path(workspace_dir).expanduser().resolve()
        parts = list(workspace.parts)
        if "environments" in parts:
            idx = parts.index("environments")
            if idx + 1 < len(parts):
                team_dir = Path(*parts[: idx + 2])
                if team_dir.exists():
                    return team_dir
    return None


def _apply_team_env(team_name: str, workspace_dir: str) -> None:
    """在 workflow 执行前注入团队 API 配置到环境变量。"""
    team_path = _infer_team_path(team_name=team_name, workspace_dir=workspace_dir)
    if not team_path:
        return

    token = ""
    base_url = ""
    model = ""

    team_yaml = team_path / "team.yaml"
    if team_yaml.exists():
        try:
            with open(team_yaml, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            token = str(config.get("anthropic_auth_token", "") or "")
            if not token:
                token = str((config.get("api_keys") or {}).get("anthropic", "") or "")
            base_url = str(config.get("anthropic_base_url", "") or "")
            model = str(config.get("anthropic_model", "") or "")
        except Exception:
            pass

    # 兼容仅在 .claude/settings.json 中配置的场景
    if not token or not base_url or not model:
        settings_file = team_path / ".claude" / "settings.json"
        if settings_file.exists():
            try:
                with open(settings_file, encoding="utf-8") as f:
                    settings = json.load(f)
                env = settings.get("env", {})
                token = token or str(env.get("ANTHROPIC_AUTH_TOKEN", "") or "")
                token = token or str(env.get("ANTHROPIC_API_KEY", "") or "")
                base_url = base_url or str(env.get("ANTHROPIC_BASE_URL", "") or "")
                model = model or str(env.get("ANTHROPIC_MODEL", "") or "")
            except Exception:
                pass

    # 最后兜底：base_config
    if not token or not base_url or not model:
        try:
            base = get_base_config()
            token = token or str(base.get("anthropic_auth_token", "") or "")
            base_url = base_url or str(base.get("anthropic_base_url", "") or "")
            model = model or str(base.get("anthropic_model", "") or "")
        except Exception:
            pass

    if token:
        os.environ["ANTHROPIC_AUTH_TOKEN"] = token
        os.environ["ANTHROPIC_API_KEY"] = token
    if base_url:
        os.environ["ANTHROPIC_BASE_URL"] = base_url
    if model:
        os.environ["ANTHROPIC_MODEL"] = model


def run_workflow(
    user_request: str,
    team_name: str = "",
    task_description: str = "",
    workflow_type: str = "software_company",
    workspace_dir: str = "",
    webhook_url: str = "",
    test_command: str = "pytest -q",
) -> WorkflowState:
    """
    运行完整的工作流

    Args:
        user_request: 用户请求
        team_name: 团队名称
        task_description: 任务描述（可选）
        workflow_type: 工作流类型键，见 WORKFLOW_TYPES
        workspace_dir: 执行工作目录
        webhook_url: 完成时回调地址
        test_command: 测试命令

    Returns:
        最终的工作流状态
    """
    _apply_team_env(team_name=team_name, workspace_dir=workspace_dir)
    workflow = _compile_workflow(workflow_type)
    app = workflow.compile()

    # 初始化状态
    initial_state = create_initial_state(
        user_request=user_request,
        task_description=task_description,
        team_name=team_name,
        workspace_dir=workspace_dir,
        webhook_url=webhook_url,
        test_command=test_command,
    )

    # 运行工作流
    result = app.invoke(initial_state)

    # 统一日志与通知
    log_path = write_workflow_log(result, workspace_dir=workspace_dir)
    result["run_log_path"] = str(log_path)
    if not result.get("completed_at"):
        from datetime import datetime

        result["completed_at"] = datetime.now().isoformat()
    webhook = result.get("webhook_url", webhook_url)
    if webhook:
        payload = {
            "workflow_id": result.get("workflow_id", ""),
            "status": "success" if result.get("success", False) else "failed",
            "team_name": result.get("team_name", ""),
            "error_message": result.get("error_message", ""),
            "run_log_path": str(log_path),
            "current_stage": result.get("current_stage", ""),
        }
        ok, message = send_webhook_notification(webhook, payload)
        result["webhook_delivery"] = {"success": ok, "message": message}

    return result


def run_workflow_step_by_step(
    user_request: str,
    team_name: str = "",
    task_description: str = "",
    workflow_type: str = "software_company",
    workspace_dir: str = "",
    webhook_url: str = "",
    test_command: str = "pytest -q",
):
    """
    逐步运行工作流（用于调试或展示）

    Yields:
        每一步的状态更新
    """
    _apply_team_env(team_name=team_name, workspace_dir=workspace_dir)
    workflow = _compile_workflow(workflow_type)
    app = workflow.compile()

    initial_state = create_initial_state(
        user_request=user_request,
        task_description=task_description,
        team_name=team_name,
        workspace_dir=workspace_dir,
        webhook_url=webhook_url,
        test_command=test_command,
    )

    for state in app.stream(initial_state):
        yield state


def get_workflow_type(name: str) -> dict | None:
    """获取指定类型的工作流配置"""
    return WORKFLOW_TYPES.get(name)


def list_workflow_types() -> list[dict]:
    """列出所有可用的工作流类型"""
    return [
        {
            "name": key,
            "display_name": config["name"],
            "description": config["description"],
            "nodes": config["nodes"],
        }
        for key, config in WORKFLOW_TYPES.items()
    ]
