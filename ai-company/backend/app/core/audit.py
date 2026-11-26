"""Nhật ký kiểm toán chuỗi băm (SRS §13, §15; SECURITY_PLAN §9).

Mỗi dòng: hash = SHA-256(hash dòng trước + nội dung chuẩn hóa). CSDL chặn UPDATE/DELETE/TRUNCATE bằng trigger;
nếu ai đó vẫn sửa bằng quyền superuser, `verify_chain` phát hiện ra dòng đầu tiên bị lệch.
Dữ liệu ghi vào nhật ký luôn đi qua `redact` (không có SĐT, email, khóa).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.core.logging import redact

GENESIS = "GENESIS"
_LOCK = 0x41_49_43_4F  # khóa tư vấn: ghi audit tuần tự để chuỗi không rẽ nhánh


def _clean(v: Any) -> Any:
    if isinstance(v, str):
        return redact(v)[:2000]
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_clean(x) for x in v][:200]
    return v


def _digest(prev: str, at: datetime, actor: str, action: str, resource: str | None, data: dict[str, Any], reason: str | None) -> str:
    body = json.dumps(
        {"at": at.astimezone(UTC).isoformat(), "actor": actor, "action": action, "resource": resource, "data": data, "reason": reason},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256((prev + body).encode()).hexdigest()


async def record(
    conn: AsyncConnection,
    actor: str,
    action: str,
    resource: str | None = None,
    data: dict[str, Any] | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> int:
    await db.execute(conn, "SELECT pg_advisory_xact_lock(:k)", {"k": _LOCK})
    prev = await db.scalar(conn, "SELECT hash FROM audit_logs ORDER BY id DESC LIMIT 1") or GENESIS
    at = datetime.now(UTC)
    clean = _clean(data or {})
    reason_c = redact(reason)[:500] if reason else None
    h = _digest(prev, at, actor, action, resource, clean, reason_c)
    rid = await db.scalar(
        conn,
        "INSERT INTO audit_logs(at, actor, action, resource, data, reason, request_id, prev_hash, hash) "
        "VALUES (:at, :actor, :action, :resource, CAST(:data AS jsonb), :reason, :rid, :prev, :h) RETURNING id",
        {
            "at": at,
            "actor": actor,
            "action": action,
            "resource": resource,
            "data": json.dumps(clean, ensure_ascii=False),
            "reason": reason_c,
            "rid": request_id,
            "prev": prev,
            "h": h,
        },
    )
    return int(rid)


@dataclass
class ChainReport:
    ok: bool
    checked: int
    first_bad_id: int | None = None


async def verify_chain(conn: AsyncConnection) -> ChainReport:
    prev = GENESIS
    n = 0
    rows = await db.all_(conn, "SELECT id, at, actor, action, resource, data, reason, prev_hash, hash FROM audit_logs ORDER BY id")
    for r in rows:
        n += 1
        expect = _digest(prev, r["at"], r["actor"], r["action"], r["resource"], r["data"], r["reason"])
        if r["prev_hash"] != prev or r["hash"] != expect:
            return ChainReport(False, n, int(r["id"]))
        prev = r["hash"]
    return ChainReport(True, n)
