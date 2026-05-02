"""简单任务 API 服务（标准库 HTTPServer）。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from anaagent.config_manager import (
    get_base_config,
    load_team_yaml_dict,
    set_base_config,
    update_team_claude_config_for_team,
)
from anaagent.usage_monitor import get_dashboard_summary

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


_WORKFLOW_LABELS = {
    "software_company": "软件开发 · 全流程",
    "simple_dev": "软件开发 · 快速开发",
    "review_only": "软件开发 · 仅审查",
    "article_pipeline": "文章撰写 · 管线",
    "article_direct": "文章撰写 · 直接撰写",
    "research_pipeline": "科研辅助 · 管线",
    "research_requirements": "科研辅助 · 需求分析",
}


def _recent_workflows_payload(limit: int) -> dict[str, Any]:
    """最近任务列表（供首页「最近工作流」）。"""
    tasks = list_tasks(limit=min(max(limit, 1), 100))
    status_cn = {
        "SUCCEEDED": "已完成",
        "FAILED": "失败",
        "RUNNING": "运行中",
        "PENDING": "等待中",
    }
    items: list[dict[str, Any]] = []
    for t in tasks:
        payload = t.get("payload") or {}
        wf = str(payload.get("workflow_type") or "software_company")
        items.append(
            {
                "task_id": t.get("task_id"),
                "status": t.get("status"),
                "status_label": status_cn.get(str(t.get("status")), str(t.get("status"))),
                "team_name": payload.get("team_name", ""),
                "workflow_type": wf,
                "workflow_label": _WORKFLOW_LABELS.get(wf, wf),
                "request_preview": str(payload.get("request", ""))[:120],
                "created_at": t.get("created_at", ""),
            }
        )
    return {"items": items, "count": len(items)}


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

        if parsed.path == "/api/v1/stats/summary":
            _json_response(self, 200, get_dashboard_summary())
            return

        if parsed.path == "/api/v1/meta/workflow-types":
            from anaagent.workflow import list_workflow_types

            _json_response(self, 200, {"ok": True, "workflows": list_workflow_types()})
            return

        if parsed.path == "/api/v1/meta/team-types":
            from anaagent.config_manager import VALID_TEAM_TYPES

            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "team_types": sorted(VALID_TEAM_TYPES),
                    "labels": {
                        "software_dev": "软件开发",
                        "article_writing": "文章撰写",
                        "research_assistant": "科研辅助",
                    },
                },
            )
            return

        if parsed.path == "/api/v1/stats/recent-workflows":
            limit = 20
            if "limit" in query and query["limit"]:
                try:
                    limit = int((query.get("limit") or ["20"])[0])
                except ValueError:
                    _json_response(self, 400, {"error": "limit must be an integer"})
                    return
            _json_response(self, 200, _recent_workflows_payload(limit))
            return

        if parsed.path == "/api/v1/config/base":
            _json_response(self, 200, {"ok": True, "config": get_base_config()})
            return

        if parsed.path.startswith("/api/v1/config/teams/"):
            name = unquote(parsed.path.removeprefix("/api/v1/config/teams/").strip().strip("/"))
            if not name:
                _json_response(self, 400, {"error": "team name required"})
                return
            data = load_team_yaml_dict(name)
            if data is None:
                _json_response(self, 404, {"error": "team not found"})
                return
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "team_name": name,
                    "anthropic_auth_token": data.get("anthropic_auth_token", ""),
                    "anthropic_base_url": data.get("anthropic_base_url", ""),
                    "anthropic_model": data.get("anthropic_model", ""),
                    "team_type": data.get("team_type", "software_dev"),
                },
            )
            return

        _json_response(self, 404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        allowed = {
            "/api/v1/tasks",
            "/api/v1/binding/code/refresh",
            "/api/v1/binding/submit",
            "/api/v1/config/base",
        }
        if parsed.path not in allowed and not parsed.path.startswith("/api/v1/config/teams/"):
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

        if parsed.path == "/api/v1/config/base":
            if not any(
                k in body for k in ("anthropic_auth_token", "anthropic_base_url", "anthropic_model")
            ):
                _json_response(self, 400, {"error": "no config fields to update"})
                return
            res = set_base_config(
                auth_token=body.get("anthropic_auth_token")
                if "anthropic_auth_token" in body
                else None,
                base_url=body.get("anthropic_base_url") if "anthropic_base_url" in body else None,
                model=body.get("anthropic_model") if "anthropic_model" in body else None,
            )
            if not res.success:
                _json_response(self, 400, {"error": res.message or "save failed"})
                return
            _json_response(self, 200, {"ok": True, "config": get_base_config()})
            return

        if parsed.path.startswith("/api/v1/config/teams/"):
            name = unquote(parsed.path.removeprefix("/api/v1/config/teams/").strip().strip("/"))
            if not name:
                _json_response(self, 400, {"error": "team name required"})
                return
            if not any(
                k in body
                for k in (
                    "anthropic_auth_token",
                    "anthropic_base_url",
                    "anthropic_model",
                    "team_type",
                    "teamType",
                )
            ):
                _json_response(self, 400, {"error": "no config fields to update"})
                return
            tt_body = None
            if "team_type" in body:
                tt_body = body.get("team_type")
            elif "teamType" in body:
                tt_body = body.get("teamType")
            res = update_team_claude_config_for_team(
                name,
                auth_token=body.get("anthropic_auth_token")
                if "anthropic_auth_token" in body
                else None,
                base_url=body.get("anthropic_base_url") if "anthropic_base_url" in body else None,
                model=body.get("anthropic_model") if "anthropic_model" in body else None,
                team_type=tt_body,
            )
            if not res.success:
                _json_response(self, 400, {"error": res.message or "save failed"})
                return
            data = load_team_yaml_dict(name) or {}
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "team_name": name,
                    "anthropic_auth_token": data.get("anthropic_auth_token", ""),
                    "anthropic_base_url": data.get("anthropic_base_url", ""),
                    "anthropic_model": data.get("anthropic_model", ""),
                    "team_type": data.get("team_type", "software_dev"),
                },
            )
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
