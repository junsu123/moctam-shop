"""API của Control Center: agent (tạm dừng/chạy lại), cài đặt (ngân sách, giờ), nhà cung cấp AI, tổng quan, diễn biến."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

import psycopg
from fastapi import APIRouter, Depends, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.v1.health import ready as health_ready
from app.core import audit, db, security
from app.core.errors import AppError
from app.domain import lifecycle, store
from app.gateway import models as gateway

router = APIRouter(tags=["control"])
Owner = Depends(security.require_role("owner", "manager"))
Viewer = Depends(security.current_user)


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


# ------------------------------------------------------------------ agent
@router.get("/agents")
async def list_agents(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> list[dict[str, Any]]:
    rows = await db.all_(
        conn,
        "SELECT a.agent_key, a.display_name, a.department, a.kind, a.reports_to, a.role_summary, "
        "s.state, s.reason, s.changed_by, s.updated_at "
        "FROM agents a JOIN agent_status s ON s.agent_id = a.id ORDER BY a.sort_order",
    )
    return [dict(r) for r in rows]


class PauseIn(BaseModel):
    reason: str = Field(default="", max_length=300)


async def _set_state(conn: AsyncConnection, key: str, state: str, reason: str, cur: security.Current, request: Request) -> dict[str, Any]:
    return await lifecycle.transition(conn, key, state, cur.actor, reason, _rid(request))


@router.post("/agents/{key}/pause")
async def pause(
    key: str, body: PauseIn, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    return await _set_state(conn, key, "paused", body.reason, cur, request)


@router.post("/agents/{key}/resume")
async def resume(key: str, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> dict[str, Any]:
    return await _set_state(conn, key, "active", "", cur, request)


@router.post("/agents/pause-all")
async def pause_all(
    body: PauseIn, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, int]:
    n = await db.execute(
        conn,
        "UPDATE agent_status SET state = 'paused', reason = :r, changed_by = :by, updated_at = now() "
        "WHERE state IN ('active','learning','waiting_approval','degraded')",
        {"r": body.reason or "Tạm dừng toàn bộ", "by": cur.actor},
    )
    await audit.record(conn, cur.actor, "agent.pause_all", "agents", {"count": n}, reason=body.reason or None, request_id=_rid(request))
    return {"paused": n}


# ------------------------------------------------------------------ cài đặt
@router.get("/settings")
async def get_settings_(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    return {
        "budget": (await store.get_setting(conn, "budget")).model_dump(),
        "hours": (await store.get_setting(conn, "hours")).model_dump(),
    }


@router.put("/settings/budget")
async def put_budget(
    body: store.Budget, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> store.Budget:
    if body.day_usd > body.day_burst_usd:
        raise AppError("VALIDATION_FAILED", "Trần ngày không được lớn hơn mức tối đa một ngày.", 422)
    old = await store.get_setting(conn, "budget")
    await store.put_setting(conn, "budget", body, cur.actor)
    await audit.record(
        conn, cur.actor, "settings.budget", "settings:budget", {"from": old.model_dump(), "to": body.model_dump()}, request_id=_rid(request)
    )
    return body


@router.put("/settings/hours")
async def put_hours(
    body: store.Hours, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> store.Hours:
    old = await store.get_setting(conn, "hours")
    await store.put_setting(conn, "hours", body, cur.actor)
    await audit.record(
        conn, cur.actor, "settings.hours", "settings:hours", {"from": old.model_dump(), "to": body.model_dump()}, request_id=_rid(request)
    )
    return body


# ------------------------------------------------------------------ nhà cung cấp AI
@router.get("/providers")
async def providers(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> list[dict[str, Any]]:
    out = []
    for p in await db.all_(conn, "SELECT * FROM provider_registry ORDER BY id"):
        info = await store.secret_info(conn, p["secret_name"]) if p["secret_name"] else None
        models = await db.all_(
            conn,
            "SELECT id, model_name, price_in_per_mtok, price_out_per_mtok, enabled FROM model_registry WHERE provider_id = :p ORDER BY price_out_per_mtok",
            {"p": p["id"]},
        )
        out.append(
            {
                "id": p["id"],
                "display_name": p["display_name"],
                "configured": info is not None,
                "key_last4": info["last4"] if info else None,
                "key_updated_at": info["updated_at"] if info else None,
                "last_test_at": p["last_test_at"],
                "last_test_ok": p["last_test_ok"],
                "last_test_detail": p["last_test_detail"],
                "models": [
                    {**dict(m), "price_in_per_mtok": float(m["price_in_per_mtok"]), "price_out_per_mtok": float(m["price_out_per_mtok"])}
                    for m in models
                ],
            }
        )
    return out


class KeyIn(BaseModel):
    api_key: str = Field(min_length=20, max_length=300)


@router.put("/providers/{pid}/key")
async def put_key(
    pid: Literal["anthropic", "openai"],
    body: KeyIn,
    request: Request,
    conn: AsyncConnection = Depends(db.get_db),
    cur: security.Current = Depends(security.recent_auth),
) -> dict[str, Any]:
    name = await db.scalar(conn, "SELECT secret_name FROM provider_registry WHERE id = :p", {"p": pid})
    last4 = await store.put_secret(conn, str(name), body.api_key.strip(), cur.actor)
    await db.execute(
        conn, "UPDATE provider_registry SET last_test_at = NULL, last_test_ok = NULL, last_test_detail = NULL WHERE id = :p", {"p": pid}
    )
    await audit.record(conn, cur.actor, "provider.key_set", f"provider:{pid}", {"last4": last4}, request_id=_rid(request))
    return {"configured": True, "key_last4": last4}


@router.post("/providers/{pid}/test")
async def test_provider(
    pid: Literal["anthropic", "openai"], request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    """Gọi thật một lời ngắn (≈ 20 token) qua Model Gateway để kiểm tra khóa API; chi phí được ghi như mọi lời gọi khác."""
    res = await gateway.ping_provider(conn, pid)
    await db.execute(
        conn,
        "UPDATE provider_registry SET last_test_at = now(), last_test_ok = :ok, last_test_detail = :d WHERE id = :p",
        {"ok": res["ok"], "d": res["detail"], "p": pid},
    )
    await audit.record(
        conn, cur.actor, "provider.test", f"provider:{pid}", {"ok": res["ok"], "detail": res["detail"]}, request_id=_rid(request)
    )
    return res


# ------------------------------------------------------------------ tổng quan
@router.get("/overview")
async def overview(request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    health = await health_ready(Response())
    spend = await gateway.spend(conn)
    states = {r["state"]: r["n"] for r in await db.all_(conn, "SELECT state, count(*) n FROM agent_status GROUP BY state")}
    tg_token = await store.secret_info(conn, "telegram.bot_token")
    tg_chats = await db.scalar(conn, "SELECT count(*) FROM telegram_chats WHERE enabled")
    prov = await db.all_(
        conn,
        "SELECT p.id, (s.name IS NOT NULL) AS configured, p.last_test_ok FROM provider_registry p LEFT JOIN secrets s ON s.name = p.secret_name",
    )
    return {
        "health": health.model_dump(),
        "budget": spend,
        "agents": {"total": sum(states.values()), "by_state": states},
        "telegram": {"configured": tg_token is not None, "chats": int(tg_chats or 0)},
        "approvals_pending": int(
            await db.scalar(conn, "SELECT count(*) FROM approvals WHERE status = 'pending' AND expires_at > now()") or 0
        ),
        "providers": [dict(p) for p in prov],
        "now": datetime.now(UTC),
    }


# ------------------------------------------------------------------ diễn biến
ACTION_TEXT = {
    "auth.setup_started": "bắt đầu thiết lập tài khoản Owner",
    "auth.setup_completed": "hoàn tất thiết lập tài khoản Owner",
    "auth.login": "đăng nhập",
    "auth.login_failed": "đăng nhập sai",
    "auth.logout": "đăng xuất",
    "auth.reauth": "xác thực lại",
    "agent.pause": "tạm dừng agent",
    "agent.resume": "cho agent chạy lại",
    "agent.pause_all": "tạm dừng toàn bộ agent",
    "settings.budget": "đổi ngân sách LLM",
    "settings.hours": "đổi giờ làm việc",
    "provider.key_set": "lưu khóa API",
    "provider.test": "kiểm tra kết nối nhà cung cấp AI",
    "telegram.token_set": "lưu token bot Telegram",
    "telegram.link_code": "tạo mã kết nối Telegram",
    "telegram.chat_linked": "kết nối chat Telegram",
    "telegram.chat_updated": "đổi cài đặt chat Telegram",
    "telegram.chat_removed": "gỡ chat Telegram",
    "telegram.link_failed": "nhập sai mã kết nối Telegram",
    "agent.disable": "tắt agent",
    "brain.bootstrap": "nạp bộ não lần đầu",
    "brain.sync": "đọc lại thư mục bộ não",
    "brain.activated": "kích hoạt phiên bản bộ não mới",
    "brain.rolled_back": "quay lại phiên bản bộ não cũ",
    "brain.shadow": "cho chạy thử phiên bản bộ não",
    "approval.requested": "gửi yêu cầu duyệt",
    "approval.approved": "duyệt",
    "approval.rejected": "từ chối duyệt",
    "approval.expired": "yêu cầu duyệt hết hạn",
    "tool.invoked": "dùng công cụ",
    "tool.denied": "bị chặn khi dùng công cụ",
    "tool.failed": "dùng công cụ lỗi",
    "memory.added": "thêm kiến thức vào trí nhớ",
    "memory.retired": "cho mục trí nhớ nghỉ hưu",
    "telegram.ignored": "bỏ qua tin từ chat lạ",
}


def _audit_ev(r: Any) -> dict[str, Any]:
    return {
        "source": "audit",
        "id": r["id"],
        "at": r["at"],
        "actor": r["actor"],
        "action": r["action"],
        "text": ACTION_TEXT.get(r["action"], r["action"]),
        "resource": r["resource"],
        "reason": r["reason"],
    }


def _note_ev(r: Any) -> dict[str, Any]:
    return {
        "source": "notification",
        "id": r["id"],
        "at": r["created_at"],
        "actor": "system",
        "action": f"notify.{r['kind']}",
        "text": r["text"],
        "status": r["status"],
        "urgent": r["urgent"],
    }


AUDIT_COLS = "id, at, actor, action, resource, reason"
NOTE_COLS = "id, created_at, kind, text, status, urgent"


async def _events(conn: AsyncConnection, limit: int = 100) -> list[dict[str, Any]]:
    out = [_audit_ev(r) for r in await db.all_(conn, f"SELECT {AUDIT_COLS} FROM audit_logs ORDER BY id DESC LIMIT :l", {"l": limit})]  # noqa: S608
    out += [_note_ev(r) for r in await db.all_(conn, f"SELECT {NOTE_COLS} FROM notifications ORDER BY id DESC LIMIT :l", {"l": limit})]  # noqa: S608
    out.sort(key=lambda e: e["at"], reverse=True)
    return out[:limit]


@router.get("/events")
async def events(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> list[dict[str, Any]]:
    return await _events(conn)


async def _event_by_id(source: str, eid: int) -> dict[str, Any] | None:
    async with db.engine().connect() as conn:
        if source == "audit":
            r = await db.one(conn, f"SELECT {AUDIT_COLS} FROM audit_logs WHERE id = :i", {"i": eid})  # noqa: S608
            return _audit_ev(r) if r else None
        r = await db.one(conn, f"SELECT {NOTE_COLS} FROM notifications WHERE id = :i", {"i": eid})  # noqa: S608
        return _note_ev(r) if r else None


@router.get("/events/stream")
async def stream(request: Request) -> StreamingResponse:
    """Server-Sent Events: Postgres NOTIFY 'aico_events' → trình duyệt, gần như tức thời. Nhịp tim mỗi 15 giây.

    Kiểm phiên bằng kết nối ngắn rồi trả lại pool ngay: luồng mở lâu không được giữ chỗ trong pool 10 kết nối.
    """
    async with db.engine().begin() as c:
        if await security._load(c, request) is None:
            raise AppError("UNAUTHENTICATED", "Cần đăng nhập.", 401)

    async def gen() -> AsyncIterator[str]:
        aconn = await psycopg.AsyncConnection.connect(db.psycopg_url(), autocommit=True)
        try:
            await aconn.execute("LISTEN aico_events")
            yield "retry: 3000\n\n"
            notifies = aconn.notifies()
            while not await request.is_disconnected():
                try:
                    n = await asyncio.wait_for(anext(notifies), timeout=15)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                msg = json.loads(n.payload)
                ev = await _event_by_id(msg["source"], int(msg["id"]))
                if ev:
                    yield "data: " + json.dumps(jsonable_encoder(ev), ensure_ascii=False) + "\n\n"  # thời gian ISO 8601 như /events
        finally:
            await aconn.close()

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
