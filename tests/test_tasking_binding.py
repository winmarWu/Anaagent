"""Binding flow tests."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta

from anaagent.tasking.binding import (
    BINDING_STATUS_EXPIRED,
    get_binding_status,
    get_or_create_local_device_identity,
    issue_binding_code,
    submit_binding_code,
)
from anaagent.tasking.store import get_task_db_path


def test_issue_code_invalidates_previous_active_code():
    first = issue_binding_code(user_id="wx-user-1", ttl_seconds=90)
    assert first["ok"] is True

    second = issue_binding_code(user_id="wx-user-1", ttl_seconds=90)
    assert second["ok"] is True
    assert second["code"] != first["code"]

    with sqlite3.connect(get_task_db_path()) as conn:
        row = conn.execute(
            """
            SELECT status
            FROM binding_codes
            WHERE code_hash = ?
            """,
            (
                hashlib.sha256(first["code"].encode("utf-8")).hexdigest(),
            ),
        ).fetchone()
    assert row is not None
    assert row[0] == BINDING_STATUS_EXPIRED


def test_submit_code_is_one_time_use():
    issue = issue_binding_code(user_id="wx-user-2", ttl_seconds=90)
    assert issue["ok"] is True

    first = submit_binding_code(code=issue["code"], device_id="device-a", device_name="docker-a")
    assert first["ok"] is True
    assert first["status"] == "BOUND"

    second = submit_binding_code(code=issue["code"], device_id="device-b", device_name="docker-b")
    assert second["ok"] is False


def test_submit_expired_code_fails():
    issue = issue_binding_code(user_id="wx-user-3", ttl_seconds=90)
    assert issue["ok"] is True

    with sqlite3.connect(get_task_db_path()) as conn:
        conn.execute(
            """
            UPDATE binding_codes
            SET expires_at = ?
            WHERE code_hash = ?
            """,
            (
                (datetime.now() - timedelta(seconds=1)).isoformat(),
                hashlib.sha256(issue["code"].encode("utf-8")).hexdigest(),
            ),
        )
        conn.commit()

    result = submit_binding_code(code=issue["code"], device_id="device-expired")
    assert result["ok"] is False
    assert result["reason"] == "expired_code"


def test_local_device_identity_is_persistent():
    first = get_or_create_local_device_identity("local-node")
    second = get_or_create_local_device_identity("local-node")

    assert first["device_id"]
    assert first["device_id"] == second["device_id"]


def test_get_binding_status_returns_user_and_device():
    issue = issue_binding_code(user_id="wx-user-4", ttl_seconds=90)
    bind = submit_binding_code(code=issue["code"], device_id="device-status", device_name="node-status")
    assert bind["ok"] is True

    payload = get_binding_status(user_id="wx-user-4", device_id="device-status")
    assert payload["ok"] is True
    assert payload["user"] is not None
    assert payload["user"]["status"] == "BOUND"
    assert payload["device"] is not None
    assert payload["device"]["owner_user_id"] == "wx-user-4"
