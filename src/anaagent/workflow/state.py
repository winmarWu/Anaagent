"""工作流状态定义"""

from enum import Enum
from typing import TypedDict

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """Agent 角色枚举"""

    PM = "pm"  # 产品经理
    DEVELOPER = "dev"  # 开发
    REVIEWER = "review"  # 代码审查
    TESTER = "test"  # 测试


class WorkflowStage(str, Enum):
    """工作流阶段"""

    INIT = "init"
    PLAN = "plan"
    DEVELOP = "develop"
    REVIEW = "review"
    TEST = "test"
    DONE = "done"
    FAILED = "failed"


class AgentOutput(BaseModel):
    """单个 Agent 的输出"""

    agent_name: str
    role: AgentRole
    content: str
    success: bool = True
    error_message: str = ""
    tokens_used: int = 0
    duration_ms: int = 0


# LangGraph 使用 TypedDict 作为状态
class WorkflowState(TypedDict, total=False):
    """
    工作流状态 - 在 Agent 间传递

    注意：LangGraph 要求状态必须是 TypedDict
    """

    # 用户输入
    user_request: str
    task_description: str

    # 当前阶段
    current_stage: str  # WorkflowStage 的值

    # 各 Agent 输出
    pm_output: str
    dev_output: str
    review_output: str
    test_output: str

    # 所有输出历史
    outputs: list[dict]  # List[AgentOutput.model_dump()]

    # 消息历史（用于上下文传递）
    messages: list[dict]

    # 下一个执行的 Agent
    next_agent: str

    # 是否需要修改（审查不通过时）
    needs_revision: bool
    revision_count: int
    max_revisions: int

    # 最终结果
    final_result: str
    success: bool
    error_message: str

    # 元数据
    team_name: str
    workflow_id: str
    started_at: str
    completed_at: str

    # 执行上下文
    workspace_dir: str
    webhook_url: str
    test_command: str
    run_log_path: str

    # 工具执行轨迹
    tool_calls: list[dict]
    command_results: list[dict]
    artifacts: list[dict]


def create_initial_state(
    user_request: str,
    task_description: str = "",
    team_name: str = "",
    workspace_dir: str = "",
    webhook_url: str = "",
    test_command: str = "pytest -q",
) -> WorkflowState:
    """创建初始状态"""
    import uuid
    from datetime import datetime

    return WorkflowState(
        user_request=user_request,
        task_description=task_description,
        team_name=team_name,
        workflow_id=str(uuid.uuid4())[:8],
        started_at=datetime.now().isoformat(),
        workspace_dir=workspace_dir,
        webhook_url=webhook_url,
        test_command=test_command,
        run_log_path="",
        current_stage=WorkflowStage.INIT.value,
        pm_output="",
        dev_output="",
        review_output="",
        test_output="",
        outputs=[],
        messages=[],
        next_agent="pm",
        needs_revision=False,
        revision_count=0,
        max_revisions=3,
        final_result="",
        success=True,
        error_message="",
        completed_at="",
        tool_calls=[],
        command_results=[],
        artifacts=[],
    )


class WorkflowConfig(BaseModel):
    """工作流配置"""

    name: str
    description: str = ""
    workflow_type: str = "sequential"  # sequential | parallel | conditional
    agents: list[str] = Field(default_factory=list)
    max_iterations: int = 10
    timeout_seconds: int = 300
    retry_on_failure: bool = True
    max_retries: int = 3


class WorkflowTemplate(BaseModel):
    """工作流模板"""

    name: str
    description: str = ""
    agents: list[dict] = Field(default_factory=list)
    workflow: dict = Field(default_factory=dict)
