# Workflow Local Loop Demo

This guide verifies the local execution loop in one pass.

## 1) Prepare environment

```bash
pip install -e .
export ANTHROPIC_AUTH_TOKEN="your-token"
export ANTHROPIC_BASE_URL="https://api.anthropic.com"
export ANTHROPIC_MODEL="claude-sonnet-4-6"
```

## 2) Create and activate team

```bash
agent create demo-team
agent activate demo-team
```

## 3) Run executable workflow

```bash
agent workflow run "实现一个最小待办命令行" \
  --project-dir "$ANAAGENT_WORKSPACE_DIR" \
  --test-command "pytest -q" \
  --webhook-url "https://example.com/workflow-callback"
```

## 4) Validate outputs

- Check generated files under `workspace/projects`.
- Check workflow log via `agent workflow logs`.
- Confirm webhook receiver got `workflow_id/status/run_log_path`.
