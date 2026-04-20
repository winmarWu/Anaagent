"""Workflow execution loop tests."""

from pathlib import Path

from anaagent.workflow.graph import run_workflow
from anaagent.workflow.nodes import review_node
from anaagent.workflow.state import WorkflowStage, create_initial_state


def _make_fake_call_llm():
    calls = {"count": 0}

    def _fake_call_llm(prompt: str, system_prompt: str = "", max_tokens: int = 4096):
        calls["count"] += 1
        if calls["count"] == 1:  # PM
            return "PM plan", 10, 20, 50
        if calls["count"] == 2:  # Dev
            return (
                '{"implementation_summary":"create app","actions":[{"tool":"write_file","args":{"path":"app.py","content":"print(1)"}}],"notes":"done"}',
                10,
                20,
                50,
            )
        if calls["count"] == 3:  # Test
            return "Test report: PASS", 10, 20, 50
        return "## 审查结果\nPASS\n\n## 原因\n测试通过", 10, 20, 50  # Review

    return _fake_call_llm


def test_run_workflow_executes_tools_and_generates_artifacts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("anaagent.workflow.nodes.call_llm", _make_fake_call_llm())

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_workflow(
        user_request="实现一个hello程序",
        team_name="",
        workflow_type="software_company",
        workspace_dir=str(workspace),
        test_command="python -c \"print('ok')\"",
    )

    assert result["success"] is True
    assert result["current_stage"] == WorkflowStage.DONE.value
    assert any(r.get("label") == "test_command" for r in result.get("command_results", []))
    assert result["run_log_path"]


def test_review_requests_revision_when_test_failed(monkeypatch):
    monkeypatch.setattr("anaagent.workflow.nodes.call_llm", _make_fake_call_llm())
    state = create_initial_state("req")
    state["command_results"] = [
        {"stage": "test", "label": "test_command", "success": False, "error": "tests failed"}
    ]
    state["revision_count"] = 0
    state["max_revisions"] = 2

    result = review_node(state)
    assert result["needs_revision"] is True
    assert result["next_agent"] == "dev"
    assert result["revision_count"] == 1
