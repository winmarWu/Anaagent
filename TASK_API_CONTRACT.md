# Task API Contract (MVP)

This document defines the stable contract for task submission and status query.

## Base URL

- Local default: `http://127.0.0.1:8765`

## Endpoints

- `GET /health`
- `POST /api/v1/tasks`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`

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
