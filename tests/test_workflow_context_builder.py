"""Workspace context builder tests."""

from pathlib import Path

from anaagent.workflow.context_builder import build_workspace_context, format_workspace_context


def test_build_workspace_context_collects_tree_and_key_files(tmp_path: Path):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Demo\n", encoding="utf-8")
    (workspace / "src").mkdir()
    (workspace / "src" / "main.py").write_text("print('x')\n", encoding="utf-8")

    context = build_workspace_context(workspace)
    assert context["workspace_dir"].endswith("proj")
    assert any("README.md" in line for line in context["tree_lines"])
    assert "README.md" in context["key_files"]


def test_format_workspace_context_returns_text(tmp_path: Path):
    workspace = tmp_path / "proj2"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    context = build_workspace_context(workspace)
    text = format_workspace_context(context)
    assert "Workspace Overview" in text
    assert "pyproject.toml" in text
