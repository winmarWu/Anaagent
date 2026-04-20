"""Workflow ToolRuntime tests."""

from pathlib import Path

from anaagent.workflow.tools_runtime import execute_tool_call, parse_tool_calls


def test_write_and_read_file_in_workspace(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()

    write_result = execute_tool_call(
        workspace_dir=workspace,
        tool="write_file",
        args={"path": "src/hello.py", "content": "print('hello')\n"},
    )
    assert write_result["success"] is True

    read_result = execute_tool_call(
        workspace_dir=workspace,
        tool="read_file",
        args={"path": "src/hello.py"},
    )
    assert read_result["success"] is True
    assert "print('hello')" in read_result["output"]


def test_prevent_path_escape(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()

    result = execute_tool_call(
        workspace_dir=workspace,
        tool="write_file",
        args={"path": "../outside.txt", "content": "blocked"},
    )
    assert result["success"] is False
    assert "outside workspace" in result["error"]


def test_run_shell_command(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()

    result = execute_tool_call(
        workspace_dir=workspace,
        tool="run_shell",
        args={"command": "python -c \"print('ok')\""},
    )
    assert result["success"] is True
    assert "ok" in result["output"]


def test_block_dangerous_shell_command(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()

    result = execute_tool_call(
        workspace_dir=workspace,
        tool="run_shell",
        args={"command": "rm -rf ."},
    )
    assert result["success"] is False
    assert "blocked token" in result["error"] or "allowlist" in result["error"]


def test_parse_tool_calls_reports_schema_errors():
    calls, errors = parse_tool_calls(
        [
            {"tool": "write_file", "args": {"path": "a.py", "content": "ok"}},
            {"tool": "run_shell", "args": {"command": "whoami"}},
            {"tool": "read_file", "args": {"encoding": "utf-8"}},
        ]
    )
    assert len(calls) == 1
    assert len(errors) >= 2
