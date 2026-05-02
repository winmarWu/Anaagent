# Task API Contract (MVP)

This document defines the stable contract for task submission and status query.

## Base URL

- Local default: `http://127.0.0.1:8765`

## Endpoints

- `GET /health`
- `POST /api/v1/tasks`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/stats/summary`（今日 + 累计 token/费用/调用次数，数据来自本机 `~/.anaagent/usage.db`）
- `GET /api/v1/stats/recent-workflows?limit=20`（最近任务队列，供「最近工作流」列表）
- `GET /api/v1/meta/workflow-types`（可用 `workflow_type` 键及说明）
- `GET /api/v1/meta/team-types`（创建团队时的 `team_type` 合法值）
- `GET /api/v1/config/base`（读取 base 环境 `~/.anaagent/base_config.json`）
- `POST /api/v1/config/base`（**仅**更新 base 默认配置，不修改各团队 `team.yaml`）
- `GET /api/v1/config/teams/{team_name}`（读取指定团队 `team.yaml` 中 API 与 `team_type`）
- `POST /api/v1/config/teams/{team_name}`（按团队更新，等价于本地 `agent config set-team` + 写回 `team.yaml` / `.claude/settings.json`）

## Task Status Enum

- `PENDING`: waiting for worker
- `RUNNING`: claimed by worker
- `SUCCEEDED`: finished successfully
- `FAILED`: finished with error

## POST /api/v1/tasks

### Request JSON

```json
{
  "request": "实现一个简单待办CLI",
  "team_name": "demo-team",
  "project_dir": "/path/to/project",
  "test_command": "pytest -q",
  "workflow_type": "software_company",
  "callback_url": "https://example.com/callback",
  "idempotency_key": "wx-msg-20260420-0001",
  "max_retries": 2
}
```

### Response JSON

```json
{
  "task_id": "a1b2c3d4e5f6",
  "status": "PENDING",
  "created": true,
  "idempotency_key": "wx-msg-20260420-0001"
}
```

`created=false` means the request reused an existing task by idempotency key.

## GET /api/v1/tasks/{task_id}

Returns:

- `task_id`
- `status`
- `payload`
- `result`
- `error_message`
- `error_history`
- `retry_count`
- `max_retries`
- timestamps (`created_at`, `started_at`, `completed_at`, `updated_at`)

## Signature (optional but recommended)

When `ANAAGENT_TASK_API_SECRET` is configured on server side, every `POST /api/v1/tasks` must include:

- `X-Anaagent-Timestamp`: unix seconds
- `X-Anaagent-Signature`: hex(HMAC_SHA256(secret, `timestamp + "." + raw_body`))

If signature is invalid, server returns `401`.

### Python example

```python
import hmac
import hashlib
import json
import time
import requests

secret = "your-shared-secret"
url = "http://127.0.0.1:8765/api/v1/tasks"
payload = {"request": "实现一个简单待办CLI"}
raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
ts = str(int(time.time()))
sig = hmac.new(secret.encode("utf-8"), ts.encode("utf-8") + b"." + raw, hashlib.sha256).hexdigest()

resp = requests.post(
    url,
    data=raw,
    headers={
        "Content-Type": "application/json",
        "X-Anaagent-Timestamp": ts,
        "X-Anaagent-Signature": sig,
    },
)
print(resp.status_code, resp.text)
```

## `workflow_type` 常用键

- 软件开发类：`software_company`（PM→Dev→Review→Test）、`simple_dev`（Dev→Test）、`review_only`（仅审查）
- 文章撰写：`article_pipeline`（大纲→写作→润色）、`article_direct`（单步直接成文）
- 科研辅助：`research_pipeline`（规划→综合→报告）、`research_requirements`（单步需求分析报告）

## 配置 API（与小程序 / 管理端对接）

`POST` 在启用 `ANAAGENT_TASK_API_SECRET` 时与普通任务相同，需带签名头；未设置密钥时本地可免签名（仍建议仅绑定到本机或回环地址）。

### POST /api/v1/config/base

只写入 `~/.anaagent/base_config.json`，**不会**覆盖各团队目录下 `team.yaml`（与 `npx` 桥接中「个人页保存 = base 默认」一致）。

```json
{
  "anthropic_auth_token": "sk-...",
  "anthropic_base_url": "https://api.anthropic.com",
  "anthropic_model": "claude-sonnet-4-6"
}
```

可只传需要修改的字段（至少一个）。

### GET /api/v1/config/base

返回当前 `get_base_config()` 的 JSON。

### GET /api/v1/config/teams/{team_name}

返回该团队的 `anthropic_*` 与 `team_type`。

### POST /api/v1/config/teams/{team_name}

```json
{
  "anthropic_auth_token": "sk-...",
  "anthropic_base_url": "https://api.anthropic.com",
  "anthropic_model": "claude-sonnet-4-6",
  "team_type": "software_dev"
}
```

`team_type` 可选值：`software_dev`、`article_writing`、`research_assistant`（与创建团队时含义一致）。

### GET /api/v1/stats/summary

示例：

```json
{
  "today": {
    "total_tokens": 12500,
    "total_cost": 0.038,
    "api_calls": 23
  },
  "all_time": {
    "total_tokens": 120000,
    "total_cost": 0.42,
    "api_calls": 340
  }
}
```

### GET /api/v1/stats/recent-workflows?limit=20

返回 `{ "items": [ { "task_id", "status", "status_label", "team_name", "workflow_type", "workflow_label", "request_preview", "created_at" } ], "count": N }`

---

## 绑定服务（小程序 + `npx @wuran/local-cli`）：团队类型必须与团队名称一致贯通

团队**名称**能通，是因为全链路都用同一个 `name` 字符串。团队**类型**若始终在小程序里显示「软件开发」，通常不是「算法复杂」，而是下面三类问题之一（可同时存在）：

1. **绑定服务未持久化 `teamType`**  
   - 小程序创建团队时，HTTP/WebSocket 请求体里若没有把类型写入数据库，或写死默认 `software_dev`，则 `GET /api/teams`、列表卡片永远拿不到真实类型。  
   - `GET /api/sync/pending` 返回的每一项也必须带上用户选择的类型（建议字段名 **`teamType`**，值为 **`software_dev` | `article_writing` | `research_assistant`**；也可同时给 **`team_type`**）。仅给中文展示文案时，本地桥接会尝试规范化，但**仍以 canonical 字符串最可靠**。

2. **`POST /api/sync/teams` 未合并类型**  
   - 本地 `agent list` / `team.yaml` 已是 `article_writing`，但小程序仍显示软件开发：说明桥接上报的负载里虽有类型，**服务端 upsert 团队时忽略了 `teamType`/`team_type` 字段**，或列表接口仍读旧列默认值。  
   - 本地桥接每条团队会同时发送 **`teamType` 与 `team_type`**（同值），服务端至少应识别其一并写库。

3. **小程序前端只读了一个字段或写死默认**  
   - 列表/详情应用 **`item.teamType || item.team_type`** 映射到中文标签；若只读 `teamType` 而后端只返回 `team_type`，会得到 `undefined`，UI 回退成「软件开发」。  
   - 创建团队时，请求体应提交 **canonical 类型**（与上表三值一致），不要只传中文；展示层再用映射表转成「文章撰写」等。

**如何自检（不猜）**：用绑定拿到的 `Bearer` 调 `GET /api/teams`（或与小程序相同的列表接口），看 JSON 里每个团队是否有正确的 `teamType`/`team_type`。若没有，必须先改**绑定服务**再谈镜像；若已有而小程序仍错，则改**小程序映射**。本地 Docker 镜像只需包含会写 `team.yaml` 里 `team_type` 的 `anaagent` 版本（及可选：`pip install -e` 当前仓库）。
