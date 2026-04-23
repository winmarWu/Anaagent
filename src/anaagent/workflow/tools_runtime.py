"""Workflow 工具执行运行时。

提供可控的本地工具执行能力：
- read_file
- write_file
- run_shell
- git_status
"""

from __future__ import annotations

import subprocess
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from typing import Any


DEFAULT_COMMAND_TIMEOUT = 120
MAX_OUTPUT_CHARS = 8000
MAX_READ_FILE_CHARS = 20000
MAX_WRITE_FILE_CHARS = 200000
MAX_TOOL_CALLS = 20
MAX_COMMAND_TIMEOUT = 300

DENYLIST_COMMAND_TOKENS = [
    "rm -rf",
    "shutdown",
    "reboot",
    "mkfs",
    "poweroff",
    "format ",
    "del /f",
    "git reset --hard",
    "git clean -fd",
]

ALLOWLIST_COMMAND_PREFIXES = [
    "python",
    "pytest",
    "pip",
    "uv",
    "ls",
    "dir",
    "echo",
    "cat",
    "type",
    "git status",
    "git diff",
]


class ToolName(str, Enum):
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    RUN_SHELL = "run_shell"
    GIT_STATUS = "git_status"


class ReadFileArgs(BaseModel):
    path: str
    encoding: str = "utf-8"


class WriteFileArgs(BaseModel):
    path: str
    content: str
    mode: Literal["overwrite", "append"] = "overwrite"
    encoding: str = "utf-8"

    @field_validator("content")
    @classmethod
    def _limit_content_size(cls, value: str) -> str:
        if len(value) > MAX_WRITE_FILE_CHARS:
            raise ValueError(f"content exceeds max length {MAX_WRITE_FILE_CHARS}")
        return value


class RunShellArgs(BaseModel):
    command: str
    timeout_seconds: int = Field(default=DEFAULT_COMMAND_TIMEOUT, ge=1, le=MAX_COMMAND_TIMEOUT)


class ToolCall(BaseModel):
    tool: ToolName
    args: dict[str, Any] = Field(default_factory=dict)


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... (truncated, total={len(text)} chars)"


def _resolve_workspace(workspace_dir: str | Path) -> Path:
    workspace = Path(workspace_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _resolve_target_path(workspace: Path, raw_path: str) -> Path:
    target = (workspace / raw_path).resolve()
    if workspace == target or workspace in target.parents:
        return target
    raise ValueError(f"path '{raw_path}' is outside workspace")


def _is_command_allowed(command: str) -> tuple[bool, str]:
    lowered = command.strip().lower()
    if not lowered:
        return False, "empty command is not allowed"

    for token in DENYLIST_COMMAND_TOKENS:
        if token in lowered:
            return False, f"command contains blocked token: {token}"

    for prefix in ALLOWLIST_COMMAND_PREFIXES:
        if lowered.startswith(prefix):
            return True, ""
    return False, "command is not in allowlist"


def read_file_tool(workspace_dir: str | Path, path: str, encoding: str = "utf-8") -> dict[str, Any]:
    workspace = _resolve_workspace(workspace_dir)
    target = _resolve_target_path(workspace, path)
    if not target.exists():
        return {"success": False, "tool": "read_file", "error": f"file not found: {path}"}

    if not target.is_file():
        return {"success": False, "tool": "read_file", "error": f"not a file: {path}"}

    content = target.read_text(encoding=encoding)
    return {
        "success": True,
        "tool": "read_file",
        "output": _truncate(content, MAX_READ_FILE_CHARS),
        "metadata": {"path": str(target)},
    }


def write_file_tool(
    workspace_dir: str | Path,
    path: str,
    content: str,
    mode: str = "overwrite",
    encoding: str = "utf-8",
) -> dict[str, Any]:
    workspace = _resolve_workspace(workspace_dir)
    target = _resolve_target_path(workspace, path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if len(content) > MAX_WRITE_FILE_CHARS:
        return {"success": False, "tool": "write_file", "error": "content too large"}

    if mode == "append":
        with open(target, "a", encoding=encoding) as f:
            f.write(content)
    else:
        target.write_text(content, encoding=encoding)

    return {
        "success": True,
        "tool": "write_file",
        "output": f"wrote {len(content)} chars to {path}",
        "metadata": {"path": str(target), "mode": mode},
    }


def run_shell_tool(
    workspace_dir: str | Path,
    command: str,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT,
) -> dict[str, Any]:
    workspace = _resolve_workspace(workspace_dir)
    allowed, reason = _is_command_allowed(command)
    if not allowed:
        return {
            "success": False,
            "tool": "run_shell",
            "error": reason,
            "metadata": {"command": command, "cwd": str(workspace)},
        }

    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "tool": "run_shell",
            "error": f"command timed out after {timeout_seconds}s",
            "metadata": {"command": command, "cwd": str(workspace)},
        }
    except Exception as exc:  # pragma: no cover - 防御性处理
        return {
            "success": False,
            "tool": "run_shell",
            "error": str(exc),
            "metadata": {"command": command, "cwd": str(workspace)},
        }

    stdout = _truncate(completed.stdout or "")
    stderr = _truncate(completed.stderr or "")
    success = completed.returncode == 0
    output = stdout if success else (stderr or stdout)
    return {
        "success": success,
        "tool": "run_shell",
        "output": output,
        "error": "" if success else (stderr or f"command exited with {completed.returncode}"),
        "metadata": {
            "command": command,
            "cwd": str(workspace),
            "return_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        },
    }


def git_status_tool(workspace_dir: str | Path) -> dict[str, Any]:
    return run_shell_tool(workspace_dir=workspace_dir, command="git status --short")


def parse_tool_calls(raw_calls: Any) -> tuple[list[ToolCall], list[str]]:
    """解析并校验工具调用列表。"""
    if not isinstance(raw_calls, list):
        return [], ["actions is not a list"]
    errors: list[str] = []
    if len(raw_calls) > MAX_TOOL_CALLS:
        errors.append(
            f"too many actions (max={MAX_TOOL_CALLS}), truncated from {len(raw_calls)} to {MAX_TOOL_CALLS}"
        )
        raw_calls = raw_calls[:MAX_TOOL_CALLS]

    parsed_calls: list[ToolCall] = []
    for idx, raw in enumerate(raw_calls):
        try:
            call = ToolCall.model_validate(raw)
        except ValidationError as exc:
            errors.append(f"action[{idx}] invalid: {exc.errors()}")
            continue

        try:
            if call.tool == ToolName.READ_FILE:
                ReadFileArgs.model_validate(call.args)
            elif call.tool == ToolName.WRITE_FILE:
                WriteFileArgs.model_validate(call.args)
            elif call.tool == ToolName.RUN_SHELL:
                shell_args = RunShellArgs.model_validate(call.args)
                allowed, reason = _is_command_allowed(shell_args.command)
                if not allowed:
                    errors.append(f"action[{idx}] blocked: {reason}")
                    continue
            elif call.tool == ToolName.GIT_STATUS:
                pass
        except ValidationError as exc:
            errors.append(f"action[{idx}] args invalid: {exc.errors()}")
            continue

        parsed_calls.append(call)

    return parsed_calls, errors


def execute_tool_call(workspace_dir: str | Path, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """执行单个工具调用并返回统一结果结构。"""
    try:
        if tool == "read_file":
            parsed = ReadFileArgs.model_validate(args)
            return read_file_tool(
                workspace_dir=workspace_dir,
                path=parsed.path,
                encoding=parsed.encoding,
            )
        if tool == "write_file":
            parsed = WriteFileArgs.model_validate(args)
            return write_file_tool(
                workspace_dir=workspace_dir,
                path=parsed.path,
                content=parsed.content,
                mode=parsed.mode,
                encoding=parsed.encoding,
            )
        if tool == "run_shell":
            parsed = RunShellArgs.model_validate(args)
            return run_shell_tool(
                workspace_dir=workspace_dir,
                command=parsed.command,
                timeout_seconds=parsed.timeout_seconds,
            )
        if tool == "git_status":
            return git_status_tool(workspace_dir=workspace_dir)

        return {"success": False, "tool": tool, "error": f"unsupported tool: {tool}"}
    except ValidationError as exc:
        return {"success": False, "tool": tool, "error": f"validation error: {exc.errors()}"}
    except Exception as exc:
        return {"success": False, "tool": tool, "error": str(exc)}


def execute_tool_calls(workspace_dir: str | Path, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """顺序执行多个工具调用。"""
    results: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        tool = str(call.get("tool", "")).strip()
        args = dict(call.get("args", {}))
        result = execute_tool_call(workspace_dir=workspace_dir, tool=tool, args=args)
        result["index"] = index
        results.append(result)
    return results
