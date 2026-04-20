"""简单任务 API 服务（标准库 HTTPServer）。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .security import get_api_secret, verify_signature
from .store import enqueue_task, get_task, init_task_store, list_tasks


def _json_response(handler: BaseHTTPRequestHandler, status_code: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class TaskAPIHandler(BaseHTTPRequestHandler):
    server_version = "AnaagentTaskAPI/0.1"

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            _json_response(self, 200, {"ok": True})
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
        if parsed.path != "/api/v1/tasks":
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

        request_text = str(body.get("request", "")).strip()
        if not request_text:
            _json_response(self, 400, {"error": "field 'request' is required"})
            return

        idempotency_key = str(body.get("idempotency_key", "")).strip()
        max_retries = int(body.get("max_retries", 2))
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
