"""Task API server tests."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from anaagent.tasking.api_server import TaskAPIHandler
from anaagent.tasking.store import init_task_store


@pytest.fixture
def api_base_url() -> str:
    init_task_store()
    server = ThreadingHTTPServer(("127.0.0.1", 0), TaskAPIHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _request_json(
    method: str,
    url: str,
    payload: dict | None = None,
) -> tuple[int, dict]:
    data = b""
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = Request(url=url, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310
            body = response.read().decode("utf-8")
            return response.getcode(), json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body)


def test_binding_endpoints_happy_path(api_base_url: str):
    refresh_status, refresh_body = _request_json(
        "POST",
        f"{api_base_url}/api/v1/binding/code/refresh",
        {"user_id": "wx-user-api", "ttl_seconds": 90},
    )
    assert refresh_status == 200
    assert refresh_body["ok"] is True
    code = refresh_body["code"]

    submit_status, submit_body = _request_json(
        "POST",
        f"{api_base_url}/api/v1/binding/submit",
        {"code": code, "device_id": "device-api", "device_name": "docker-api"},
    )
    assert submit_status == 200
    assert submit_body["ok"] is True
    assert submit_body["status"] == "BOUND"

    query = urlencode({"user_id": "wx-user-api", "device_id": "device-api"})
    status_status, status_body = _request_json(
        "GET",
        f"{api_base_url}/api/v1/binding/status?{query}",
    )
    assert status_status == 200
    assert status_body["ok"] is True
    assert status_body["user"]["status"] == "BOUND"
    assert status_body["device"]["owner_user_id"] == "wx-user-api"


def test_binding_refresh_rejects_non_integer_ttl(api_base_url: str):
    status, body = _request_json(
        "POST",
        f"{api_base_url}/api/v1/binding/code/refresh",
        {"user_id": "wx-user-api", "ttl_seconds": "abc"},
    )
    assert status == 400
    assert body["error"] == "ttl_seconds must be an integer"


def test_tasks_reject_non_integer_max_retries(api_base_url: str):
    status, body = _request_json(
        "POST",
        f"{api_base_url}/api/v1/tasks",
        {"request": "hello", "max_retries": "bad"},
    )
    assert status == 400
    assert body["error"] == "max_retries must be an integer"
