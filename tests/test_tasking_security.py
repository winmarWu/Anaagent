"""Task API signature tests."""

import time

from anaagent.tasking.security import generate_signature, verify_signature


def test_verify_signature_success():
    secret = "demo-secret"
    body = b'{"request":"hello"}'
    timestamp = str(int(time.time()))
    signature = generate_signature(secret, timestamp, body)

    ok, reason = verify_signature(secret, timestamp, signature, body)
    assert ok is True
    assert reason == "ok"


def test_verify_signature_mismatch():
    secret = "demo-secret"
    body = b'{"request":"hello"}'
    timestamp = str(int(time.time()))
    bad_signature = "0" * 64

    ok, reason = verify_signature(secret, timestamp, bad_signature, body)
    assert ok is False
    assert "mismatch" in reason


def test_verify_signature_expired():
    secret = "demo-secret"
    body = b'{"request":"hello"}'
    timestamp = str(int(time.time()) - 1000)
    signature = generate_signature(secret, timestamp, body)

    ok, reason = verify_signature(secret, timestamp, signature, body, tolerance_seconds=10)
    assert ok is False
    assert "expired" in reason


def test_verify_signature_disabled_without_secret():
    ok, reason = verify_signature("", "", "", b"{}")
    assert ok is True
    assert reason == "signature disabled"
