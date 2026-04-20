"""Webhook notification tests."""

from pathlib import Path

from anaagent.workflow.graph import run_workflow


def _make_fake_call_llm():
    calls = {"count": 0}

    def _fake_call_llm(prompt: str, system_prompt: str = "", max_tokens: int = 4096):
        calls["count"] += 1
        if calls["count"] == 1:
            return "PM plan", 1, 1, 1
        if calls["count"] == 2:
            return (
                '{"implementation_summary":"noop","actions":[{"tool":"write_file","args":{"path":"a.py","content":"print(1)"}}]}',
                1,
                1,
                1,
            )
        if calls["count"] == 3:
            return "report", 1, 1, 1
        return "## 审查结果\nPASS", 1, 1, 1

    return _fake_call_llm


def test_workflow_sends_webhook(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("anaagent.workflow.nodes.call_llm", _make_fake_call_llm())

    captured = {}

    def _fake_send(webhook_url: str, payload: dict, timeout: int = 10):
        captured["url"] = webhook_url
        captured["payload"] = payload
        return True, "status=200"

    monkeypatch.setattr("anaagent.workflow.graph.send_webhook_notification", _fake_send)

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_workflow(
        user_request="make file",
        workflow_type="software_company",
        workspace_dir=str(workspace),
        webhook_url="https://example.com/hook",
        test_command="python -c \"print('ok')\"",
    )

    assert result["success"] is True
    assert captured["url"] == "https://example.com/hook"
    assert captured["payload"]["workflow_id"] == result["workflow_id"]
    assert result["webhook_delivery"]["success"] is True
