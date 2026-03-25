"""Hooks 执行系统 - 参考 Claude Code Hooks 设计"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass

from anaagent.environment import get_current_environment


@dataclass
class HookResult:
    """Hook执行结果"""
    success: bool
    block: bool = False
    reason: str = ""
    output: str = ""
    error: str = ""


# Claude Code 15种Hook类型
HOOK_TYPES = [
    "PreToolUse",        # 工具调用前 - 可阻止
    "PostToolUse",       # 工具调用后
    "UserPromptSubmit",  # 用户输入后 - 可阻止
    "SessionStart",      # 会话开始时
    "SessionEnd",        # 会话结束时
    "Notification",      # 通知发送时
    "Stop",              # AI停止响应时
    "WorktreeCreate",    # 工作树创建时
    "WorktreeRemove",    # 工作树删除时
    "SubagentStart",     # 子代理启动时
    "SubagentStop",      # 子代理停止时
    "PermissionRequest", # 权限请求时 - 可阻止
    "PreCompact",        # 上下文压缩前
    "ConfigChange",      # 配置变更时
    "TeammateIdle",      # 队友空闲时
]


def get_hooks_dir() -> Optional[Path]:
    """获取hooks目录"""
    env_path = get_current_environment()
    if env_path:
        return env_path / "hooks"
    return None


def execute_hook(
    hook_name: str,
    hook_type: str,
    input_data: dict,
    timeout: int = 30
) -> HookResult:
    """
    执行单个Hook

    Args:
        hook_name: Hook文件名
        hook_type: Hook类型 (PreToolUse, PostToolUse等)
        input_data: 传给Hook的输入数据
        timeout: 超时时间(秒)

    Returns:
        HookResult: 执行结果
    """
    hooks_dir = get_hooks_dir()
    if not hooks_dir:
        return HookResult(success=False, error="No active team environment")

    hook_path = hooks_dir / hook_name
    if not hook_path.exists():
        return HookResult(success=False, error=f"Hook '{hook_name}' not found")

    # 根据文件类型执行
    if hook_name.endswith(".py"):
        return _execute_python_hook(hook_path, input_data, timeout)
    elif hook_name.endswith(".sh"):
        return _execute_shell_hook(hook_path, input_data, timeout)
    else:
        return HookResult(success=False, error=f"Unsupported hook type: {hook_name}")


def _execute_python_hook(hook_path: Path, input_data: dict, timeout: int) -> HookResult:
    """执行Python Hook"""
    try:
        result = subprocess.run(
            [sys.executable, str(hook_path)],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8"
        )

        if result.returncode == 0:
            try:
                output = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
                return HookResult(
                    success=True,
                    block=output.get("block", False),
                    reason=output.get("reason", ""),
                    output=result.stdout
                )
            except json.JSONDecodeError:
                return HookResult(success=True, output=result.stdout)
        else:
            return HookResult(
                success=False,
                error=result.stderr or f"Hook exited with code {result.returncode}"
            )

    except subprocess.TimeoutExpired:
        return HookResult(success=False, error=f"Hook timed out after {timeout}s")
    except Exception as e:
        return HookResult(success=False, error=str(e))


def _execute_shell_hook(hook_path: Path, input_data: dict, timeout: int) -> HookResult:
    """执行Shell Hook"""
    try:
        result = subprocess.run(
            ["bash", str(hook_path)],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8"
        )

        if result.returncode == 0:
            try:
                output = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
                return HookResult(
                    success=True,
                    block=output.get("block", False),
                    reason=output.get("reason", ""),
                    output=result.stdout
                )
            except json.JSONDecodeError:
                return HookResult(success=True, output=result.stdout)
        else:
            return HookResult(
                success=False,
                error=result.stderr or f"Hook exited with code {result.returncode}"
            )

    except subprocess.TimeoutExpired:
        return HookResult(success=False, error=f"Hook timed out after {timeout}s")
    except Exception as e:
        return HookResult(success=False, error=str(e))


def run_hooks_for_event(
    hook_type: str,
    tool_name: Optional[str] = None,
    tool_input: Optional[dict] = None,
    tool_result: Optional[Any] = None,
) -> list[HookResult]:
    """
    为特定事件运行所有匹配的Hooks

    Args:
        hook_type: Hook类型
        tool_name: 工具名称 (用于matcher匹配)
        tool_input: 工具输入
        tool_result: 工具输出 (PostToolUse时)

    Returns:
        所有Hook的执行结果列表
    """
    import yaml

    env_path = get_current_environment()
    if not env_path:
        return []

    # 读取settings.json获取hooks配置
    settings_path = env_path / ".claude" / "settings.json"
    if not settings_path.exists():
        return []

    try:
        import json
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        return []

    hooks_config = settings.get("hooks", {}).get(hook_type, [])
    results = []

    for hook_entry in hooks_config:
        # 检查matcher
        matcher = hook_entry.get("matcher", "")
        if matcher and tool_name:
            import re
            if not re.search(matcher, tool_name):
                continue

        # 执行hooks
        for hook_def in hook_entry.get("hooks", []):
            hook_command = hook_def.get("command", "")
            if not hook_command:
                continue

            # 构建输入数据
            input_data = {
                "hook_type": hook_type,
                "tool_name": tool_name,
                "tool_input": tool_input or {},
            }
            if tool_result:
                input_data["tool_result"] = str(tool_result)

            # 执行hook
            timeout = hook_def.get("timeout", 30)

            # 解析命令获取hook文件名
            hook_name = Path(hook_command).name

            result = execute_hook(hook_name, hook_type, input_data, timeout)
            results.append(result)

            # 如果hook阻止，停止执行后续hooks
            if result.block:
                break

    return results


def should_block_operation(hook_type: str, tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """
    检查是否应该阻止操作

    Returns:
        (should_block, reason)
    """
    results = run_hooks_for_event(hook_type, tool_name, tool_input)

    for result in results:
        if result.block:
            return True, result.reason

    return False, ""