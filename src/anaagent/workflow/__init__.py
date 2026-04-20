"""LangGraph 多 Agent 工作流模块

这个模块实现了真正的多 Agent 协作功能：
- WorkflowState: 工作流状态定义
- Agent 节点: PM, Dev, Review, Test
- 工作流图: 定义 Agent 间的协作流程

使用方法:
    from anaagent.workflow import run_workflow

    result = run_workflow("实现一个计算器功能")
    print(result["final_result"])
"""

from anaagent.workflow.graph import (
    WORKFLOW_TYPES,
    create_review_only_workflow,
    create_simple_dev_workflow,
    create_software_workflow,
    get_workflow_type,
    list_workflow_types,
    run_workflow,
    run_workflow_step_by_step,
)
from anaagent.workflow.context_builder import build_workspace_context, format_workspace_context
from anaagent.workflow.notifier import send_webhook_notification
from anaagent.workflow.nodes import (
    NODE_MAPPING,
    dev_node,
    pm_node,
    review_node,
    test_node,
)
from anaagent.workflow.run_logger import write_workflow_log
from anaagent.workflow.state import (
    AgentOutput,
    AgentRole,
    WorkflowConfig,
    WorkflowStage,
    WorkflowState,
    WorkflowTemplate,
    create_initial_state,
)
from anaagent.workflow.tools_runtime import execute_tool_call, execute_tool_calls

__all__ = [
    # 状态类
    "WorkflowState",
    "AgentOutput",
    "AgentRole",
    "WorkflowStage",
    "WorkflowConfig",
    "WorkflowTemplate",
    "create_initial_state",
    # 节点函数
    "pm_node",
    "dev_node",
    "review_node",
    "test_node",
    "NODE_MAPPING",
    # 工作流
    "create_software_workflow",
    "create_simple_dev_workflow",
    "create_review_only_workflow",
    "run_workflow",
    "run_workflow_step_by_step",
    "list_workflow_types",
    "get_workflow_type",
    "WORKFLOW_TYPES",
    # 执行与集成
    "execute_tool_call",
    "execute_tool_calls",
    "build_workspace_context",
    "format_workspace_context",
    "write_workflow_log",
    "send_webhook_notification",
]
