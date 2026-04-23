"""简单任务 API 服务（标准库 HTTPServer）。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .binding import get_binding_status, issue_binding_code, submit_binding_code
from .security import get_api_secret, verify_signature
from .store import enqueue_task, get_task, init_task_store, list_tasks


def _json_response(handler: BaseHTTPRequestHandler, status_code: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _parse_int_field(body: dict[str, Any], key: str, default: int) -> tuple[int, bool]:
    value = body.get(key, default)
    try:
        return int(value), True
    except (TypeError, ValueError):
        return default, False


class TaskAPIHandler(BaseHTTPRequestHandler):
    server_version = "AnaagentTaskAPI/0.1"

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            _json_response(self, 200, {"ok": True})
            return

        if parsed.path == "/api/v1/binding/status":
            user_id = str((query.get("user_id") or [""])[0])
            device_id = str((query.get("device_id") or [""])[0])
            status = get_binding_status(user_id=user_id, device_id=device_id)
            if not status.get("ok"):
                _json_response(self, 400, status)
                return
            _json_response(self, 200, status)
            return

        if parsed.path == "/api/v1/tasks":
            tasks = list_tasks(limit=50)
            _json_response(self, 200, {"tasks": tasks})
            return

        if parsed.path.startswith("/api/v1/tasks/"):
            task_id = parsed.path.removeprefix("/api/v1/tasks/").strip()
            task = get_task(task_id)
            if task is None:
                _json_response(self, 404, {"error": "task not found"})
                return
            _json_response(self, 200, task)
            return

        _json_response(self, 404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/v1/tasks", "/api/v1/binding/code/refresh", "/api/v1/binding/submit"}:
            _json_response(self, 404, {"error": "not found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        secret = get_api_secret()
        ok, reason = verify_signature(
            secret=secret,
            timestamp=str(self.headers.get("X-Anaagent-Timestamp", "")),
            signature=str(self.headers.get("X-Anaagent-Signature", "")),
            body=raw,
        )
        if not ok:
            _json_response(self, 401, {"error": "unauthorized", "reason": reason})
            return

        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            _json_response(self, 400, {"error": "invalid json"})
            return

        if parsed.path == "/api/v1/binding/code/refresh":
            user_id = str(body.get("user_id", "")).strip()
            ttl_seconds, ttl_ok = _parse_int_field(body, "ttl_seconds", 90)
            if not ttl_ok:
                _json_response(self, 400, {"error": "ttl_seconds must be an integer"})
                return
            result = issue_binding_code(user_id=user_id, ttl_seconds=ttl_seconds)
            if not result.get("ok"):
                _json_response(self, 400, {"error": result.get("reason", "unknown")})
                return
            _json_response(self, 200, result)
            return

        if parsed.path == "/api/v1/binding/submit":
            code = str(body.get("code", "")).strip()
            device_id = str(body.get("device_id", "")).strip()
            device_name = str(body.get("device_name", "")).strip()
            result = submit_binding_code(code=code, device_id=device_id, device_name=device_name)
            if not result.get("ok"):
                _json_response(self, 400, {"error": result.get("reason", "unknown")})
                return
            _json_response(self, 200, result)
            return

        request_text = str(body.get("request", "")).strip()
        if not request_text:
            _json_response(self, 400, {"error": "field 'request' is required"})
            return

        idempotency_key = str(body.get("idempotency_key", "")).strip()
        max_retries, retry_ok = _parse_int_field(body, "max_retries", 2)
        if not retry_ok:
            _json_response(self, 400, {"error": "max_retries must be an integer"})
            return
        task_id, created = enqueue_task(
            task_type="workflow_run",
            payload=body,
            idempotency_key=idempotency_key,
            max_retries=max_retries,
        )
        status_code = 202 if created else 200
        _json_response(
            self,
            status_code,
            {
                "task_id": task_id,
                "status": "PENDING",
                "created": created,
                "idempotency_key": idempotency_key,
            },
        )

    def log_message(self, format: str, *args):  # noqa: A003
        # 保持 CLI 输出简洁
        return


def run_task_api_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    init_task_store()
    server = ThreadingHTTPServer((host, port), TaskAPIHandler)
    print(f"Task API server listening on http://{host}:{port}")
    server.serve_forever()
