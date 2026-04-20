"""Tests for pytest no-tests-collected behavior in test node."""

from pathlib import Path

from anaagent.workflow import nodes as workflow_nodes
from anaagent.workflow.state import create_initial_state


def test_test_node_treats_pytest_no_tests_as_success(monkeypatch, tmp_path: Path):
    def _fake_execute_tool_call(workspace_dir: str, tool: str, args: dict):
        return {
            "success": False,
            "tool": "run_shell",
            "output": "============================ test session starts ============================\ncollected 0 items\n\n=========================== no tests ran in 0.01s ===========================",
            "error": "command exited with 5",
            "metadata": {
                "command": "pytest -q",
                "cwd": str(workspace_dir),
                "return_code": 5,
                "stdout": "collected 0 items",
                "stderr": "",
            },
        }

    def _fake_call_llm(*_args, **_kwargs):
        raise RuntimeError("skip llm in test")

    monkeypatch.setattr("anaagent.workflow.nodes.execute_tool_call", _fake_execute_tool_call)
    monkeypatch.setattr("anaagent.workflow.nodes.call_llm", _fake_call_llm)

    state = create_initial_state(
        user_request="hello world",
        team_name="newT",
        workspace_dir=str(tmp_path),
        test_command="pytest -q",
    )

    result = workflow_nodes.test_node(state)
    assert result["current_stage"] == "review"
    assert result["command_results"][-1]["success"] is True
    assert "按通过处理" in result["command_results"][-1]["output"]
