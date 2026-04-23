"""绑定码与本地设备绑定存储。"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import string
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .store import get_task_db_path

BINDING_STATUS_ISSUED = "ISSUED"
BINDING_STATUS_PENDING = "PENDING"
BINDING_STATUS_BOUND = "BOUND"
BINDING_STATUS_EXPIRED = "EXPIRED"

DEVICE_STATUS_UNBOUND = "UNBOUND"
DEVICE_STATUS_BOUND = "BOUND"

DEFAULT_CODE_LENGTH = 6
DEFAULT_CODE_TTL_SECONDS = 90


def _now() -> datetime:
    return datetime.now()


def _now_iso() -> str:
    return _now().isoformat()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _random_code(length: int) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_task_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_binding_store() -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS binding_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                code_hash TEXT NOT NULL UNIQUE,
                code_suffix TEXT NOT NULL,
                status TEXT NOT NULL,
                device_id TEXT NOT NULL DEFAULT '',
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                device_name TEXT NOT NULL DEFAULT '',
                owner_user_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'UNBOUND',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                bound_at TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS binding_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                device_id TEXT NOT NULL DEFAULT '',
                code_suffix TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_binding_codes_user_status ON binding_codes(user_id, status, issued_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_binding_codes_expires ON binding_codes(expires_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_binding_events_user_time ON binding_events(user_id, created_at)"
        )
        conn.commit()


def issue_binding_code(
    user_id: str,
    ttl_seconds: int = DEFAULT_CODE_TTL_SECONDS,
    code_length: int = DEFAULT_CODE_LENGTH,
) -> dict[str, Any]:
    init_binding_store()
    user_id = user_id.strip()
    if not user_id:
        return {"ok": False, "reason": "user_id is required"}

    ttl_seconds = max(30, min(300, int(ttl_seconds)))
    code_length = max(4, min(10, int(code_length)))
    issued_at = _now_iso()
    expires_at = (_now() + timedelta(seconds=ttl_seconds)).isoformat()

    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE binding_codes
            SET status = ?
            WHERE user_id = ?
              AND status IN (?, ?)
            """,
            (BINDING_STATUS_EXPIRED, user_id, BINDING_STATUS_ISSUED, BINDING_STATUS_PENDING),
        )

        plain_code = ""
        code_hash = ""
        code_suffix = ""
        for _ in range(20):
            candidate = _random_code(code_length)
            candidate_hash = _hash_code(candidate)
            existing = conn.execute(
                "SELECT 1 FROM binding_codes WHERE code_hash = ? LIMIT 1",
                (candidate_hash,),
            ).fetchone()
            if existing is None:
                plain_code = candidate
                code_hash = candidate_hash
                code_suffix = candidate[-2:]
                break

        if not plain_code:
            return {"ok": False, "reason": "failed to generate unique code"}

        conn.execute(
            """
            INSERT INTO binding_codes(
                user_id, code_hash, code_suffix, status, issued_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                code_hash,
                code_suffix,
                BINDING_STATUS_ISSUED,
                issued_at,
                expires_at,
            ),
        )
        _insert_event(
            conn=conn,
            event_type="code_issued",
            user_id=user_id,
            code_suffix=code_suffix,
            details={"ttl_seconds": ttl_seconds},
        )
        conn.commit()

    return {
        "ok": True,
        "user_id": user_id,
        "code": plain_code,
        "code_suffix": code_suffix,
        "status": BINDING_STATUS_ISSUED,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "ttl_seconds": ttl_seconds,
    }


def submit_binding_code(code: str, device_id: str, device_name: str = "") -> dict[str, Any]:
    init_binding_store()
    normalized_code = code.strip().upper()
    normalized_device_id = device_id.strip()
    normalized_device_name = device_name.strip()
    if not normalized_code:
        return {"ok": False, "reason": "code is required"}
    if not normalized_device_id:
        return {"ok": False, "reason": "device_id is required"}

    code_hash = _hash_code(normalized_code)
    now_iso = _now_iso()
    now_dt = _now()

    with _get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT id, user_id, status, expires_at, code_suffix
            FROM binding_codes
            WHERE code_hash = ?
            LIMIT 1
            """,
            (code_hash,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return {"ok": False, "reason": "invalid_code"}

        status = str(row["status"])
        expires_at = datetime.fromisoformat(str(row["expires_at"]))
        if expires_at <= now_dt:
            conn.execute(
                "UPDATE binding_codes SET status = ? WHERE id = ? AND status = ?",
                (BINDING_STATUS_EXPIRED, row["id"], status),
            )
            _insert_event(
                conn=conn,
                event_type="code_expired",
                user_id=str(row["user_id"]),
                code_suffix=str(row["code_suffix"]),
            )
            conn.commit()
            return {"ok": False, "reason": "expired_code"}

        if status != BINDING_STATUS_ISSUED:
            conn.rollback()
            return {"ok": False, "reason": f"code_not_issuable:{status}"}

        updated = conn.execute(
            """
            UPDATE binding_codes
            SET status = ?, device_id = ?, consumed_at = ?
            WHERE id = ? AND status = ?
            """,
            (BINDING_STATUS_PENDING, normalized_device_id, now_iso, row["id"], BINDING_STATUS_ISSUED),
        )
        if updated.rowcount != 1:
            conn.rollback()
            return {"ok": False, "reason": "code_already_used"}

        existing_device = conn.execute(
            "SELECT device_id FROM devices WHERE device_id = ?",
            (normalized_device_id,),
        ).fetchone()
        if existing_device is None:
            conn.execute(
                """
                INSERT INTO devices(
                    device_id, device_name, owner_user_id, status, first_seen_at, last_seen_at, bound_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_device_id,
                    normalized_device_name,
                    str(row["user_id"]),
                    DEVICE_STATUS_BOUND,
                    now_iso,
                    now_iso,
                    now_iso,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE devices
                SET device_name = CASE WHEN ? != '' THEN ? ELSE device_name END,
                    owner_user_id = ?,
                    status = ?,
                    last_seen_at = ?,
                    bound_at = CASE WHEN bound_at = '' THEN ? ELSE bound_at END
                WHERE device_id = ?
                """,
                (
                    normalized_device_name,
                    normalized_device_name,
                    str(row["user_id"]),
                    DEVICE_STATUS_BOUND,
                    now_iso,
                    now_iso,
                    normalized_device_id,
                ),
            )

        conn.execute(
            "UPDATE binding_codes SET status = ? WHERE id = ?",
            (BINDING_STATUS_BOUND, row["id"]),
        )
        _insert_event(
            conn=conn,
            event_type="code_bound",
            user_id=str(row["user_id"]),
            device_id=normalized_device_id,
            code_suffix=str(row["code_suffix"]),
            details={"device_name": normalized_device_name},
        )
        conn.commit()

    return {
        "ok": True,
        "user_id": str(row["user_id"]),
        "device_id": normalized_device_id,
        "device_name": normalized_device_name,
        "status": BINDING_STATUS_BOUND,
    }


def get_binding_status(user_id: str = "", device_id: str = "") -> dict[str, Any]:
    init_binding_store()
    user_id = user_id.strip()
    device_id = device_id.strip()
    if not user_id and not device_id:
        return {"ok": False, "reason": "user_id or device_id is required"}

    payload: dict[str, Any] = {"ok": True}
    with _get_conn() as conn:
        if user_id:
            row = conn.execute(
                """
                SELECT user_id, code_suffix, status, device_id, issued_at, expires_at, consumed_at
                FROM binding_codes
                WHERE user_id = ?
                ORDER BY issued_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            payload["user"] = dict(row) if row is not None else None

        if device_id:
            row = conn.execute(
                """
                SELECT device_id, device_name, owner_user_id, status, first_seen_at, last_seen_at, bound_at
                FROM devices
                WHERE device_id = ?
                LIMIT 1
                """,
                (device_id,),
            ).fetchone()
            payload["device"] = dict(row) if row is not None else None
    return payload


def get_or_create_local_device_identity(device_name: str = "") -> dict[str, Any]:
    identity_dir = Path.home() / ".anaagent" / "tasks"
    identity_dir.mkdir(parents=True, exist_ok=True)
    identity_path = identity_dir / "device_identity.json"

    if identity_path.exists():
        try:
            payload = json.loads(identity_path.read_text(encoding="utf-8"))
            if payload.get("device_id"):
                return payload
        except Exception:
            pass

    now_iso = _now_iso()
    payload = {
        "device_id": str(uuid.uuid4()),
        "device_name": device_name.strip(),
        "created_at": now_iso,
    }
    identity_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _insert_event(
    conn: sqlite3.Connection,
    event_type: str,
    user_id: str = "",
    device_id: str = "",
    code_suffix: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO binding_events(event_type, user_id, device_id, code_suffix, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event_type,
            user_id,
            device_id,
            code_suffix,
            json.dumps(details or {}, ensure_ascii=False),
            _now_iso(),
        ),
    )
