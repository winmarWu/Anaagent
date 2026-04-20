"""Workflow team env injection tests."""

import os
from pathlib import Path

import yaml

from anaagent.workflow.graph import run_workflow


def _make_fake_call_llm(captured_env: dict):
    calls = {"count": 0}

    def _fake_call_llm(prompt: str, system_prompt: str = "", max_tokens: int = 4096):
        calls["count"] += 1
        if calls["count"] == 1:
            captured_env["token"] = os.getenv("ANTHROPIC_AUTH_TOKEN")
            captured_env["api_key"] = os.getenv("ANTHROPIC_API_KEY")
            captured_env["base_url"] = os.getenv("ANTHROPIC_BASE_URL")
            captured_env["model"] = os.getenv("ANTHROPIC_MODEL")
            return "PM plan", 1, 1, 1
        if calls["count"] == 2:
            return (
                '{"implementation_summary":"noop","actions":[{"tool":"write_file","args":{"path":"main.py","content":"print(1)"}}]}',
                1,
                1,
                1,
            )
        if calls["count"] == 3:
            return "report", 1, 1, 1
        return "## 审查结果\nPASS", 1, 1, 1

    return _fake_call_llm


def test_run_workflow_injects_team_env(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    team_path = tmp_path / ".anaagent" / "environments" / "newT"
    team_path.mkdir(parents=True, exist_ok=True)
    with open(team_path / "team.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "name": "newT",
                "anthropic_auth_token": "token-from-team",
                "anthropic_base_url": "https://api.example.com",
                "anthropic_model": "claude-test",
            },
            f,
            allow_unicode=True,
            sort_keys=False,
        )

    captured_env = {}
    monkeypatch.setattr("anaagent.workflow.nodes.call_llm", _make_fake_call_llm(captured_env))

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_workflow(
        user_request="make file",
        team_name="newT",
        workflow_type="software_company",
        workspace_dir=str(workspace),
        webhook_url="",
        test_command="python -c \"print('ok')\"",
    )

    assert result["success"] is True
    assert captured_env["token"] == "token-from-team"
    assert captured_env["api_key"] == "token-from-team"
    assert captured_env["base_url"] == "https://api.example.com"
    assert captured_env["model"] == "claude-test"


def test_run_workflow_fallbacks_to_base_config(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    team_path = tmp_path / ".anaagent" / "environments" / "newT"
    team_path.mkdir(parents=True, exist_ok=True)
    with open(team_path / "team.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({"name": "newT"}, f, allow_unicode=True, sort_keys=False)

    base_config_dir = tmp_path / ".anaagent"
    base_config_dir.mkdir(parents=True, exist_ok=True)
    base_config_file = base_config_dir / "base_config.json"
    monkeypatch.setattr("anaagent.config_manager.BASE_CONFIG_FILE", base_config_file)
    base_config_file.write_text(
        (
            '{"anthropic_auth_token":"base-token",'
            '"anthropic_base_url":"https://api.base.example.com",'
            '"anthropic_model":"claude-base"}'
        ),
        encoding="utf-8",
    )

    captured_env = {}
    monkeypatch.setattr("anaagent.workflow.nodes.call_llm", _make_fake_call_llm(captured_env))

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_workflow(
        user_request="make file",
        team_name="newT",
        workflow_type="software_company",
        workspace_dir=str(workspace),
        webhook_url="",
        test_command="python -c \"print('ok')\"",
    )

    assert result["success"] is True
    assert captured_env["token"] == "base-token"
    assert captured_env["api_key"] == "base-token"
    assert captured_env["base_url"] == "https://api.base.example.com"
    assert captured_env["model"] == "claude-base"
