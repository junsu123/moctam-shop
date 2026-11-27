"""Memory Service: ghi và đọc trí nhớ có phạm vi (BRAIN_SPEC §3, §6).

Hai lớp phân quyền:
1. Ở đây: tính phạm vi đọc của từng principal (`scopes_for`) và chọn vai trò CSDL.
2. Row-Level Security của Postgres: mọi truy vấn thay agent chạy dưới `SET LOCAL ROLE aico_agent` với `app.scopes`;
   lỗi ở lớp ứng dụng vẫn không làm lộ trí nhớ của agent khác.

| Phạm vi        | Đọc                                                     | Ghi                                               |
|----------------|---------------------------------------------------------|---------------------------------------------------|
| agent:<id>     | chính agent; Director quản lý trực tiếp; Owner          | chính agent (episodic/working); Learning Engine   |
| dept:<id>      | agent trong phòng; Director; AI CEO; Owner              | Learning Engine/Director sau thẩm định            |
| company        | mọi agent                                               | chỉ qua duyệt kiến thức (Owner)                   |
| owner_only     | Owner                                                   | Owner                                             |
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db
from app.core.errors import AppError
from app.core.ids import uuid7
from app.memory import textnorm

Role = Literal["aico_agent", "aico_learning"]
Trust = Literal["owner", "internal", "verified_external", "unverified_external"]
SCOPE_RE = r"^(agent:[a-z0-9_]+|dept:[a-z0-9_]+|company|owner_only)$"


async def scopes_for(conn: AsyncConnection, principal: str) -> list[str]:
    """Phạm vi được đọc của một principal: `agent:<key>`, `owner` (đọc tất cả) hoặc `learning_engine`."""
    if principal in ("owner", "learning_engine"):
        rows = await db.all_(conn, "SELECT agent_key, department FROM agents")
        out = {"company"} | {f"agent:{r['agent_key']}" for r in rows} | {f"dept:{r['department']}" for r in rows}
        if principal == "owner":
            out.add("owner_only")
        return sorted(out)
    if not principal.startswith("agent:"):
        raise AppError("PRINCIPAL_INVALID", "Principal không hợp lệ.", 400)
    key = principal[6:]
    a = await db.one(conn, "SELECT agent_key, department, kind FROM agents WHERE agent_key = :k", {"k": key})
    if a is None:
        raise AppError("AGENT_NOT_FOUND", "Không có agent này.", 404)
    out = {f"agent:{key}", f"dept:{a['department']}", "company"}
    if a["kind"] == "executive":  # AI CEO đọc trí nhớ chung của mọi phòng
        out |= {f"dept:{r['department']}" for r in await db.all_(conn, "SELECT DISTINCT department FROM agents")}
    if a["kind"] in ("executive", "director"):  # cấp trên đọc (chỉ đọc) trí nhớ riêng của cấp dưới trực tiếp
        out |= {f"agent:{r['agent_key']}" for r in await db.all_(conn, "SELECT agent_key FROM agents WHERE reports_to = :k", {"k": key})}
    return sorted(out)


@asynccontextmanager
async def acting_as(conn: AsyncConnection, role: Role, principal: str, scopes: list[str]) -> AsyncIterator[AsyncConnection]:
    """Chạy các câu lệnh trong khối dưới vai trò CSDL bị RLS ràng buộc, rồi trả lại vai trò cũ."""
    await db.execute(conn, f"SET LOCAL ROLE {role}")  # role là Literal cố định, không lấy từ người dùng
    await db.execute(
        conn,
        "SELECT set_config('app.principal', :p, true), set_config('app.scopes', :s, true)",
        {"p": principal, "s": ",".join(scopes)},
    )
    # SET LOCAL chỉ có tác dụng trong một giao dịch: kiểm tra vai trò thật sự đã đổi, nếu không RLS sẽ không áp dụng
    if await db.scalar(conn, "SELECT current_user") != role:
        raise AppError("RLS_NOT_ACTIVE", "Truy cập trí nhớ phải chạy trong một giao dịch (RLS chưa được áp dụng).", 500)
    try:
        yield conn
    finally:
        try:
            await db.execute(conn, "RESET ROLE")
            await db.execute(conn, "SELECT set_config('app.principal', '', true), set_config('app.scopes', '', true)")
        except Exception:  # noqa: BLE001,S110 — giao dịch đã hỏng: SET LOCAL tự hết khi giao dịch kết thúc
            pass


def content_hash(scope: str, type_: str, title: str, content: str) -> str:
    return hashlib.sha256(f"{scope}\n{type_}\n{textnorm.fold(title)}\n{textnorm.fold(content)}".encode()).hexdigest()


async def _insert(
    conn: AsyncConnection,
    *,
    scope: str,
    type_: str,
    title: str,
    content: str,
    trust: Trust,
    principal: str,
    confidence: float,
    status: str,
    metadata: dict[str, Any] | None,
    source_ref: str | None,
    valid_to: datetime | None,
    supersedes: str | None = None,
) -> tuple[str, bool]:
    """Thêm một trí nhớ (đã ở trong `acting_as`). Trả (id, mới_tạo); trùng nội dung trong cùng phạm vi thì trả bản cũ."""
    from app.domain.approvals import _json

    h = content_hash(scope, type_, title, content)
    mid = str(uuid7())
    row = await db.one(
        conn,
        "INSERT INTO agent_memories(id, owner_scope, type, title, content, search_text, metadata, source_ref, source_trust, confidence, "
        "verification_status, valid_to, content_hash, supersedes_id, created_by_principal) VALUES (:id, :sc, :t, :ti, :c, :st, CAST(:m AS jsonb), "
        ":sr, :tr, :cf, :vs, :vt, :h, CAST(:sup AS uuid), :by) ON CONFLICT (owner_scope, content_hash) DO NOTHING RETURNING id",
        {
            "id": mid,
            "sc": scope,
            "t": type_,
            "ti": title[:300],
            "c": content,
            "st": textnorm.search_text(f"{title} {content}"),
            "m": _json(metadata or {}),
            "sr": source_ref,
            "tr": trust,
            "cf": round(confidence, 2),
            "vs": status,
            "vt": valid_to,
            "h": h,
            "sup": supersedes,
            "by": principal,
        },
    )
    if row is None:
        old = await db.scalar(conn, "SELECT id FROM agent_memories WHERE owner_scope = :sc AND content_hash = :h", {"sc": scope, "h": h})
        return str(old), False
    return mid, True


async def remember_episode(
    conn: AsyncConnection,
    agent_key: str,
    *,
    title: str,
    content: str,
    task_id: str | None = None,
    task_type: str | None = None,
    outcome: Literal["success", "failure", "partial"] | None = None,
    cost_usd: float | None = None,
    metadata: dict[str, Any] | None = None,
    source_ref: str | None = None,
    confidence: float = 0.6,
) -> str:
    """Agent ghi trải nghiệm vào vùng nhớ riêng (episodic). Runtime gọi tự động sau mỗi task (Sprint 4)."""
    principal = f"agent:{agent_key}"
    meta = {**(metadata or {}), **({"task_type": task_type} if task_type else {})}
    async with acting_as(conn, "aico_agent", principal, await scopes_for(conn, principal)) as c:
        mid, new = await _insert(
            c,
            scope=principal,
            type_="episodic",
            title=title,
            content=content,
            trust="internal",
            principal=principal,
            confidence=confidence,
            status="active",
            metadata=meta,
            source_ref=source_ref,
            valid_to=None,
        )
        if new:
            await db.execute(
                c,
                "INSERT INTO episodic_memories(memory_id, task_id, task_type, outcome, cost_usd) VALUES (CAST(:m AS uuid), :t, :tt, :o, :c)",
                {"m": mid, "t": task_id, "tt": task_type, "o": outcome, "c": cost_usd},
            )
    return mid


async def add_knowledge(
    conn: AsyncConnection,
    *,
    principal: str,  # "user:<email>" (Owner) hoặc "learning_engine"
    scope: str,
    type_: Literal["semantic", "procedural"],
    title: str,
    content: str,
    trust: Trust,
    confidence: float = 0.8,
    status: Literal["candidate", "verified", "active"] = "active",
    metadata: dict[str, Any] | None = None,
    source_ref: str | None = None,
    valid_to: datetime | None = None,
    evidence: list[dict[str, Any]] | None = None,
    evidence_level: str | None = None,
    topic: str | None = None,
    procedure: dict[str, Any] | None = None,
    supersedes: str | None = None,
) -> tuple[str, bool]:
    """Ghi kiến thức đã thẩm định (semantic) hoặc quy trình (procedural). Chỉ Learning Engine hoặc Owner (BRAIN_SPEC §6)."""
    from app.domain.approvals import _json

    async with acting_as(conn, "aico_learning", principal, [scope]) as c:
        mid, new = await _insert(
            c,
            scope=scope,
            type_=type_,
            title=title,
            content=content,
            trust=trust,
            principal=principal,
            confidence=confidence,
            status=status,
            metadata=metadata,
            source_ref=source_ref,
            valid_to=valid_to,
            supersedes=supersedes,
        )
        if new and type_ == "semantic":
            await db.execute(
                c,
                "INSERT INTO semantic_memories(memory_id, claim, evidence, evidence_level, topic) VALUES (CAST(:m AS uuid), :cl, CAST(:e AS jsonb), :l, :t)",
                {"m": mid, "cl": content[:2000], "e": _json(evidence or []), "l": evidence_level, "t": topic},
            )
        if new and type_ == "procedural":
            pr = procedure or {}
            await db.execute(
                c,
                "INSERT INTO procedural_memories(memory_id, procedure_key, version, steps, checklist, applies_to_task_types) "
                "VALUES (CAST(:m AS uuid), :k, :v, CAST(:s AS jsonb), CAST(:c AS jsonb), :a)",
                {
                    "m": mid,
                    "k": pr.get("key") or textnorm.fold(title).replace(" ", "_")[:60],
                    "v": pr.get("version", "1.0.0"),
                    "s": _json(pr.get("steps", [])),
                    "c": _json(pr.get("checklist", [])),
                    "a": pr.get("applies_to", []),
                },
            )
        if new and supersedes:
            await db.execute(
                c,
                "UPDATE agent_memories SET verification_status = 'deprecated', updated_at = now(), version = version + 1 "
                "WHERE id = CAST(:i AS uuid)",
                {"i": supersedes},
            )
    return mid, new


async def retire(conn: AsyncConnection, memory_id: str, actor: str, reason: str | None = None) -> None:
    """Owner cho một mục trí nhớ nghỉ hưu (không còn được truy hồi; vẫn giữ để truy vết)."""
    row = await db.one(
        conn,
        "UPDATE agent_memories SET verification_status = 'retired', updated_at = now(), version = version + 1 "
        "WHERE id = CAST(:i AS uuid) AND verification_status <> 'retired' RETURNING owner_scope, title",
        {"i": memory_id},
    )
    if row is None:
        raise AppError("MEMORY_NOT_FOUND", "Không có mục trí nhớ này (hoặc đã nghỉ hưu).", 404)
    await audit.record(
        conn, actor, "memory.retired", f"memory:{memory_id}", {"scope": row["owner_scope"], "title": row["title"]}, reason=reason
    )
