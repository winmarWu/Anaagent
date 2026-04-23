"""Agent 节点实现 - 每个 Agent 作为一个节点函数"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from anaagent.usage_monitor import record_usage
from anaagent.workflow.context_builder import build_workspace_context, format_workspace_context
from anaagent.workflow.state import AgentOutput, AgentRole, WorkflowStage, WorkflowState
from anaagent.workflow.tools_runtime import execute_tool_call, execute_tool_calls, parse_tool_calls

if TYPE_CHECKING:
    from anthropic import Anthropic


def get_anthropic_client() -> "Anthropic":
    """获取 Anthropic 客户端（使用环境变量中的配置）。"""
    from anthropic import Anthropic

    token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    return Anthropic(
        api_key=token,
        base_url=os.environ.get("ANTHROPIC_BASE_URL"),
    )


def get_model() -> str:
    """获取当前使用的模型"""
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def call_llm(prompt: str, system_prompt: str = "", max_tokens: int = 4096) -> tuple[str, int, int, int]:
    """
    调用 LLM API

    返回: (响应内容, 输入token数, 输出token数, 耗时ms)
    """
    client = get_anthropic_client()
    model = get_model()

    start_time = time.time()
    messages = [{"role": "user", "content": prompt}]
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system_prompt:
        kwargs["system"] = system_prompt

    response = client.messages.create(**kwargs)
    duration_ms = int((time.time() - start_time) * 1000)

    content_parts = []
    for block in response.content:
        if hasattr(block, "text"):
            content_parts.append(block.text)
        elif hasattr(block, "content"):
            content_parts.append(str(block.content) if block.content else "")
        else:
            content_parts.append(str(block))

    content = "\n".join(content_parts)
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    return content, input_tokens, output_tokens, duration_ms


def _get_state_value(state: WorkflowState, key: str, default: Any = None) -> Any:
    return state.get(key, default) if state.get(key) is not None else default


def _append_agent_output(state: WorkflowState, output: AgentOutput) -> list[dict]:
    existing_outputs = _get_state_value(state, "outputs", [])
    return existing_outputs + [output.model_dump()]


def _record_usage_from_llm(
    state: WorkflowState,
    agent_name: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int,
    stage: str,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    team_name = _get_state_value(state, "team_name", "")
    metadata: dict[str, Any] = {"stage": stage, "duration_ms": duration_ms}
    if extra_metadata:
        metadata.update(extra_metadata)
    record_usage(
        agent_name=agent_name,
        model=get_model(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        team_name=team_name,
        metadata=metadata,
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}

    maybe_json = text[start : end + 1]
    try:
        parsed = json.loads(maybe_json)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _collect_artifacts(existing: list[dict], tool_results: list[dict[str, Any]]) -> list[dict]:
    artifacts = list(existing)
    for result in tool_results:
        if result.get("tool") != "write_file" or not result.get("success"):
            continue
        metadata = result.get("metadata", {})
        artifacts.append(
            {
                "type": "file",
                "path": metadata.get("path", ""),
                "created_at": datetime.now().isoformat(),
            }
        )
    return artifacts


def _compose_final_result(state: WorkflowState, review_output: str) -> str:
    outputs = _get_state_value(state, "outputs", [])
    total_tokens = sum(o.get("tokens_used", 0) for o in outputs)
    artifacts = _get_state_value(state, "artifacts", [])
    artifact_lines = "\n".join(f"- {a.get('path', '')}" for a in artifacts[:30]) or "- (none)"
    return f"""# 工作流完成报告

## 用户请求
{_get_state_value(state, "user_request", "")}

## PM 规划
{_get_state_value(state, "pm_output", "")}

## Dev 输出
{_get_state_value(state, "dev_output", "")}

## Test 输出
{_get_state_value(state, "test_output", "")}

## Review 结论
{review_output}

## 产物文件
{artifact_lines}

## 总 Token 消耗
{total_tokens} tokens
"""


def _is_pytest_no_tests_case(shell_result: dict[str, Any]) -> bool:
    """识别 pytest 无测试文件场景（退出码 5）。"""
    if shell_result.get("tool") != "run_shell":
        return False
    metadata = shell_result.get("metadata", {}) or {}
    command = str(metadata.get("command", "") or "").lower()
    if "pytest" not in command:
        return False
    return_code = metadata.get("return_code")
    combined = (
        f"{shell_result.get('output', '')}\n"
        f"{shell_result.get('error', '')}\n"
        f"{metadata.get('stdout', '')}\n"
        f"{metadata.get('stderr', '')}"
    ).lower()
    return return_code == 5 and (
        "no tests ran" in combined
        or "no tests collected" in combined
        or "collected 0 items" in combined
    )


def pm_node(state: WorkflowState) -> dict:
    system_prompt = """你是一个专业的产品经理 Agent，属于一个软件开发团队。

你的职责：
1. 分析用户的原始需求
2. 提取核心功能点
3. 生成详细的功能规格说明
4. 将任务拆分为具体的开发任务
"""

    user_request = _get_state_value(state, "user_request", "")
    task_description = _get_state_value(state, "task_description", "")
    prompt = f"""请分析以下用户需求，并生成功能规格和任务拆分：

用户请求：{user_request}

上下文：
{task_description if task_description else '无额外上下文'}
"""
    try:
        content, input_tokens, output_tokens, duration = call_llm(prompt, system_prompt)
        _record_usage_from_llm(state, "pm", input_tokens, output_tokens, duration, "plan")
        output = AgentOutput(
            agent_name="pm",
            role=AgentRole.PM,
            content=content,
            success=True,
            tokens_used=input_tokens + output_tokens,
            duration_ms=duration,
        )
        return {
            "pm_output": content,
            "current_stage": WorkflowStage.DEVELOP.value,
            "next_agent": "dev",
            "outputs": _append_agent_output(state, output),
        }
    except Exception as exc:
        output = AgentOutput(
            agent_name="pm",
            role=AgentRole.PM,
            content="",
            success=False,
            error_message=str(exc),
        )
        return {
            "current_stage": WorkflowStage.FAILED.value,
            "success": False,
            "error_message": f"PM Agent 失败: {exc}",
            "outputs": _append_agent_output(state, output),
        }


def dev_node(state: WorkflowState) -> dict:
    system_prompt = """你是一个高级软件工程师 Agent。
必须输出 JSON（不要 markdown）：
{
  "implementation_summary": "本轮做了什么",
  "actions": [
    {"tool":"write_file","args":{"path":"src/main.py","content":"print('hello')","mode":"overwrite"}},
    {"tool":"run_shell","args":{"command":"python -m pytest -q","timeout_seconds":120}}
  ],
  "notes": "补充说明"
}

可用工具（严格）:
- read_file(path)
- write_file(path, content, mode=overwrite|append)
- run_shell(command, timeout_seconds)
- git_status()

执行约束（必须遵守）:
1) actions 总数 <= 10，优先最关键文件，避免无效大批量操作。
2) 至少创建一个非空业务源码文件（如 src/main.py），内容不能只有注释或空白。
3) 至少创建一个非空测试文件（如 tests/test_main.py），包含可执行测试用例。
4) 除非明确需要，不要只创建 __init__.py / 占位文件后结束。
"""
    workspace_dir = _get_state_value(state, "workspace_dir", str(Path.cwd()))
    user_request = _get_state_value(state, "user_request", "")
    pm_output = _get_state_value(state, "pm_output", "")
    review_output = _get_state_value(state, "review_output", "")
    needs_revision = _get_state_value(state, "needs_revision", False)
    revision_note = f"\n上一轮审查建议：{review_output}" if needs_revision and review_output else ""
    workspace_context = build_workspace_context(workspace_dir)
    workspace_context_text = format_workspace_context(workspace_context)

    prompt = f"""请根据需求和规划执行本地开发任务。

工作目录：{workspace_dir}
用户请求：{user_request}
PM规划：{pm_output}
{revision_note}

{workspace_context_text}
"""

    try:
        content, input_tokens, output_tokens, duration = call_llm(prompt, system_prompt, max_tokens=8192)
        _record_usage_from_llm(
            state,
            "dev",
            input_tokens,
            output_tokens,
            duration,
            "develop",
            {"revision": _get_state_value(state, "revision_count", 0)},
        )

        parsed = _extract_json_object(content)
        parsed_calls, action_errors = parse_tool_calls(parsed.get("actions", []))
        actions = [{"tool": c.tool.value, "args": c.args} for c in parsed_calls]
        tool_results = execute_tool_calls(workspace_dir=workspace_dir, calls=actions)
        artifacts = _collect_artifacts(_get_state_value(state, "artifacts", []), tool_results)

        summary = parsed.get("implementation_summary", "") if isinstance(parsed, dict) else ""
        notes = parsed.get("notes", "") if isinstance(parsed, dict) else ""
        results_preview = "\n".join(
            f"- {r.get('tool')}: {'OK' if r.get('success') else 'FAIL'}"
            for r in tool_results
        )
        action_error_text = "\n".join(f"- {err}" for err in action_errors) if action_errors else "(none)"
        dev_output = (
            f"## Implementation Summary\n{summary or '(none)'}\n\n"
            f"## Tool Results\n{results_preview or '(no actions)'}\n\n"
            f"## Action Validation Errors\n{action_error_text}\n\n"
            f"## Notes\n{notes or '(none)'}"
        )

        output = AgentOutput(
            agent_name="dev",
            role=AgentRole.DEVELOPER,
            content=dev_output,
            success=True,
            tokens_used=input_tokens + output_tokens,
            duration_ms=duration,
        )

        existing_calls = _get_state_value(state, "tool_calls", [])
        call_records = existing_calls + [{"stage": "dev", **action} for action in actions]
        existing_results = _get_state_value(state, "command_results", [])
        command_results = existing_results + [{"stage": "dev", **r} for r in tool_results]
        if action_errors:
            command_results.append(
                {
                    "stage": "dev",
                    "tool": "validation",
                    "success": False,
                    "error": "; ".join(action_errors),
                    "metadata": {"error_count": len(action_errors)},
                }
            )

        return {
            "dev_output": dev_output,
            "current_stage": WorkflowStage.TEST.value,
            "next_agent": "test",
            "needs_revision": False,
            "outputs": _append_agent_output(state, output),
            "tool_calls": call_records,
            "command_results": command_results,
            "artifacts": artifacts,
        }
    except Exception as exc:
        output = AgentOutput(
            agent_name="dev",
            role=AgentRole.DEVELOPER,
            content="",
            success=False,
            error_message=str(exc),
        )
        return {
            "current_stage": WorkflowStage.FAILED.value,
            "success": False,
            "error_message": f"Dev Agent 失败: {exc}",
            "outputs": _append_agent_output(state, output),
        }


def test_node(state: WorkflowState) -> dict:
    workspace_dir = _get_state_value(state, "workspace_dir", str(Path.cwd()))
    test_command = _get_state_value(state, "test_command", "pytest -q")
    shell_result = execute_tool_call(
        workspace_dir=workspace_dir,
        tool="run_shell",
        args={"command": test_command},
    )
    shell_result["stage"] = "test"
    shell_result["label"] = "test_command"
    no_tests_case = _is_pytest_no_tests_case(shell_result)
    if no_tests_case:
        shell_result["success"] = True
        note = "pytest 未发现测试文件（collected 0 items），按通过处理。"
        original_output = str(shell_result.get("output", "") or "").strip()
        shell_result["output"] = f"{note}\n{original_output}".strip()
        shell_result["error"] = ""

    review_output = _get_state_value(state, "review_output", "")
    prompt = f"""请根据以下测试命令结果生成简短测试报告：

命令：{test_command}
成功：{shell_result.get('success')}
输出：{shell_result.get('output', '')}
错误：{shell_result.get('error', '')}

此前审查意见：{review_output}
"""
    llm_report = ""
    input_tokens = 0
    output_tokens = 0
    duration = 0
    try:
        llm_report, input_tokens, output_tokens, duration = call_llm(prompt, max_tokens=2048)
        _record_usage_from_llm(state, "test", input_tokens, output_tokens, duration, "test")
    except Exception:
        llm_report = (
            f"测试命令 `{test_command}` "
            f"{'通过' if shell_result.get('success') else '失败'}。\n"
            f"输出：{shell_result.get('output', '')}\n错误：{shell_result.get('error', '')}"
        )

    output = AgentOutput(
        agent_name="test",
        role=AgentRole.TESTER,
        content=llm_report,
        success=shell_result.get("success", False),
        error_message=shell_result.get("error", ""),
        tokens_used=input_tokens + output_tokens,
        duration_ms=duration,
    )

    existing_calls = _get_state_value(state, "tool_calls", [])
    existing_results = _get_state_value(state, "command_results", [])
    return {
        "test_output": llm_report,
        "current_stage": WorkflowStage.REVIEW.value,
        "next_agent": "review",
        "outputs": _append_agent_output(state, output),
        "tool_calls": existing_calls + [{"stage": "test", "tool": "run_shell", "args": {"command": test_command}}],
        "command_results": existing_results + [shell_result],
    }


def review_node(state: WorkflowState) -> dict:
    revision_count = _get_state_value(state, "revision_count", 0)
    max_revisions = _get_state_value(state, "max_revisions", 3)
    command_results = _get_state_value(state, "command_results", [])
    test_results = [r for r in command_results if r.get("stage") == "test" and r.get("label") == "test_command"]
    last_test = test_results[-1] if test_results else {}
    test_failed = bool(last_test) and not last_test.get("success", False)
    validation_failed = any(
        r.get("stage") == "dev" and r.get("tool") == "validation" and not r.get("success", False)
        for r in command_results
    )

    system_prompt = """你是代码审查专家。请基于真实执行结果给出结论。
输出格式：
## 审查结果
PASS 或 NEEDS_REVISION

## 原因
...
"""
    prompt = f"""请审查本轮开发与测试结果：
用户请求：{_get_state_value(state, "user_request", "")}
Dev 输出：{_get_state_value(state, "dev_output", "")}
Test 输出：{_get_state_value(state, "test_output", "")}
测试命令成功：{last_test.get('success', 'unknown')}
测试命令错误：{last_test.get('error', '')}
"""
    content = ""
    input_tokens = 0
    output_tokens = 0
    duration = 0
    try:
        content, input_tokens, output_tokens, duration = call_llm(prompt, system_prompt, max_tokens=2048)
        _record_usage_from_llm(
            state,
            "review",
            input_tokens,
            output_tokens,
            duration,
            "review",
            {"revision_count": revision_count},
        )
    except Exception as exc:
        content = f"审查降级为规则判断：{exc}"

    llm_requests_revision = "NEEDS_REVISION" in content.upper()
    strict_review = os.environ.get("ANAAGENT_REVIEW_STRICT", "").lower() == "true"
    should_revise = test_failed or validation_failed or (strict_review and llm_requests_revision)
    needs_revision = should_revise and revision_count < max_revisions
    review_text = (
        f"{content}\n\n"
        f"规则判断：测试{'失败' if test_failed else '通过'}，"
        f"开发动作校验{'失败' if validation_failed else '通过'}，"
        f"当前修订轮次 {revision_count}/{max_revisions}"
    )
    output = AgentOutput(
        agent_name="review",
        role=AgentRole.REVIEWER,
        content=review_text,
        success=not needs_revision,
        tokens_used=input_tokens + output_tokens,
        duration_ms=duration,
    )

    if needs_revision:
        return {
            "review_output": review_text,
            "current_stage": WorkflowStage.DEVELOP.value,
            "next_agent": "dev",
            "needs_revision": True,
            "revision_count": revision_count + 1,
            "outputs": _append_agent_output(state, output),
        }

    if should_revise and revision_count >= max_revisions:
        return {
            "review_output": review_text,
            "current_stage": WorkflowStage.FAILED.value,
            "next_agent": "",
            "success": False,
            "error_message": "达到最大修订次数，工作流仍未通过质量门禁",
            "completed_at": datetime.now().isoformat(),
            "outputs": _append_agent_output(state, output),
        }

    return {
        "review_output": review_text,
        "current_stage": WorkflowStage.DONE.value,
        "next_agent": "",
        "needs_revision": False,
        "final_result": _compose_final_result(state, review_text),
        "success": True,
        "completed_at": datetime.now().isoformat(),
        "outputs": _append_agent_output(state, output),
    }


NODE_MAPPING = {"pm": pm_node, "dev": dev_node, "review": review_node, "test": test_node}
