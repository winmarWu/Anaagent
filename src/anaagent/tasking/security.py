"""Task API 签名校验（HMAC-SHA256）。"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

DEFAULT_SIGNATURE_WINDOW_SECONDS = 300


def get_api_secret() -> str:
    """读取 Task API 共享密钥。"""
    return os.environ.get("ANAAGENT_TASK_API_SECRET", "").strip()


def generate_signature(secret: str, timestamp: str, body: bytes) -> str:
    """生成签名：hex(hmac_sha256(secret, f'{timestamp}.{body}'))."""
    payload = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str,
    timestamp: str,
    signature: str,
    body: bytes,
    tolerance_seconds: int = DEFAULT_SIGNATURE_WINDOW_SECONDS,
) -> tuple[bool, str]:
    """校验签名与时间窗口。"""
    if not secret:
        return True, "signature disabled"
    if not timestamp:
        return False, "missing header: X-Anaagent-Timestamp"
    if not signature:
        return False, "missing header: X-Anaagent-Signature"

    try:
        request_ts = int(timestamp)
    except ValueError:
        return False, "invalid timestamp"

    now = int(time.time())
    if abs(now - request_ts) > max(1, tolerance_seconds):
        return False, "timestamp expired"

    expected = generate_signature(secret, timestamp, body)
    if not hmac.compare_digest(expected, signature):
        return False, "signature mismatch"
    return True, "ok"
