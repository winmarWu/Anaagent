"""Workflow 通知模块。"""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request


def send_webhook_notification(webhook_url: str, payload: dict[str, Any], timeout: int = 10) -> tuple[bool, str]:
    """发送 workflow 完成通知。"""
    if not webhook_url:
        return False, "webhook_url is empty"

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            if 200 <= status < 300:
                return True, f"status={status}"
            return False, f"unexpected status={status}"
    except error.HTTPError as exc:
        return False, f"http error: {exc.code}"
    except error.URLError as exc:
        return False, f"url error: {exc.reason}"
    except Exception as exc:  # pragma: no cover - 防御性处理
        return False, str(exc)
