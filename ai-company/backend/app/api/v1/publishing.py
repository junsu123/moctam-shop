"""API xuất bản: hàng chờ, đã đăng, bị chặn, gỡ bài, góp ý; lịch đăng bài; Content Gate; kết nối website."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from app.content import gate as cg
from app.content import publishing
from app.core import audit, db, security
from app.core.errors import AppError
from app.domain import store
from app.integrations import website

router = APIRouter(tags=["publishing"])
Owner = Depends(security.require_role("owner", "manager"))
OwnerOnly = Depends(security.require_role("owner"))  # lịch đăng và từ điển Content Gate: chỉ Owner (SECURITY_PLAN §6.3)
Viewer = Depends(security.current_user)
GROUPS = {"queue": ("scheduled", "publishing"), "live": ("published", "retracted"), "blocked": ("blocked", "failed", "cancelled")}


@router.get("/publishing")
async def queue(
    group: Literal["queue", "live", "blocked"] = "queue", conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer
) -> dict[str, Any]:
    items = [
        dict(r)
        for r in await db.all_(
            conn,
            "SELECT q.id, q.task_id, q.agent_key, a.display_name AS agent_name, q.kind, q.title, q.status, q.slot_at, q.published_at, q.url, "
            "q.gate, q.last_error, q.retracted_at, q.retracted_by, q.retract_reason, q.created_at, q.approval_id, left(q.body, 600) AS excerpt "
            "FROM publish_queue q LEFT JOIN agents a ON a.agent_key = q.agent_key WHERE q.status = ANY(:s) "
            "ORDER BY CASE WHEN q.status IN ('scheduled','publishing') THEN q.slot_at END, coalesce(q.published_at, q.created_at) DESC LIMIT 200",
            {"s": list(GROUPS[group])},
        )
    ]
    counts = {
        g: int(await db.scalar(conn, "SELECT count(*) FROM publish_queue WHERE status = ANY(:s)", {"s": list(sts)}) or 0)
        for g, sts in GROUPS.items()
    }
    s = await publishing.settings(conn)
    return {"items": items, "counts": counts, "phase": s.phase, "paused": s.paused, "paused_reason": s.paused_reason}


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/publishing/{item_id}/unpublish")
async def unpublish(
    item_id: str, body: ReasonIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    it = await publishing.unpublish(conn, item_id, actor=cur.actor, reason=body.reason)
    return {"status": it.get("status")}


class FeedbackIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


@router.post("/publishing/{item_id}/feedback")
async def feedback(
    item_id: str, body: FeedbackIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    await publishing.feedback(conn, item_id, actor=cur.actor, text=body.text)
    return {"ok": True}


# ------------------------------------------------------------------ lịch đăng bài
@router.get("/publishing/settings")
async def get_settings(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    s = await publishing.settings(conn)
    upcoming = [
        r["slot_at"] for r in await db.all_(conn, "SELECT slot_at FROM publish_queue WHERE status = 'scheduled' ORDER BY slot_at LIMIT 10")
    ]
    return {**s.model_dump(mode="json"), "upcoming": upcoming}


class ScheduleIn(BaseModel):
    phase: int = Field(ge=1, le=3)
    auto_progress: bool
    holidays: list[date] = Field(default_factory=list, max_length=60)
    window_start: str
    window_end: str
    min_gap_hours: float = Field(ge=0, le=12)
    phases: dict[str, publishing.Phase] | None = None


@router.put("/publishing/settings")
async def put_settings(body: ScheduleIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = OwnerOnly) -> dict[str, Any]:
    s = await publishing.settings(conn)
    old_phase = s.phase
    data = s.model_dump()
    data.update(body.model_dump(exclude_none=True))
    try:
        new = publishing.PublishSettings.model_validate(data)
    except ValueError as e:
        raise AppError("SETTINGS_INVALID", f"Lịch đăng không hợp lệ: {str(e)[:200]}", 422) from e
    if new.window_start >= new.window_end:
        raise AppError("SETTINGS_INVALID", "Giờ bắt đầu phải trước giờ kết thúc.", 422)
    if new.phase != old_phase:
        from datetime import UTC, datetime

        new.phase_since = datetime.now(UTC)
    await store.put_setting(conn, "publishing", new, cur.actor)
    await audit.record(conn, cur.actor, "publish.schedule_changed", "settings:publishing", {"phase": new.phase, "from": old_phase})
    return new.model_dump(mode="json")


class PauseIn(BaseModel):
    paused: bool
    reason: str = Field(default="", max_length=200)


@router.post("/publishing/pause")
async def pause(body: PauseIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> dict[str, Any]:
    s = await publishing.set_paused(conn, body.paused, actor=cur.actor, reason=body.reason or "Owner bấm trên trang quản trị")
    return {"paused": s.paused}


# ------------------------------------------------------------------ Content Gate
@router.get("/publishing/gate")
async def get_gate(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    g = await store.get_setting(conn, "content_gate")
    return g.model_dump()


@router.put("/publishing/gate")
async def put_gate(body: cg.GateConfig, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = OwnerOnly) -> dict[str, Any]:
    body.risk_phrases = sorted({x.strip() for x in body.risk_phrases if x.strip()})
    body.compare_phrases = sorted({x.strip() for x in body.compare_phrases if x.strip()})
    await store.put_setting(conn, "content_gate", body, cur.actor)
    await audit.record(conn, cur.actor, "content_gate.changed", "settings:content_gate", {"risk_phrases": len(body.risk_phrases)})
    return body.model_dump()


class GateTestIn(BaseModel):
    kind: Literal["faq", "blog"] = "faq"
    title: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=60_000)
    product_id: int | None = None


@router.post("/publishing/gate/test")
async def test_gate(body: GateTestIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> dict[str, Any]:
    """Thử Content Gate với một đoạn văn (chỉ phần tất định, không gọi model)."""
    r = await cg.evaluate(
        conn,
        kind=body.kind,
        title=body.title,
        body=body.body,
        product_ids=[body.product_id] if body.product_id else None,
        use_classifier=False,
    )
    return {**r.as_dict(), "ok": r.ok, "needs_owner": r.needs_owner}


# ------------------------------------------------------------------ kết nối website
@router.get("/website")
async def get_website(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    w = await store.get_setting(conn, "website")
    keys = {k: await store.secret_info(conn, name) for k, name in website.KEYS.items()}
    return {**w.model_dump(), "keys": {k: ({"last4": v["last4"], "updated_at": v["updated_at"]} if v else None) for k, v in keys.items()}}


class WebsiteIn(BaseModel):
    base_url: str = Field(max_length=200)


@router.put("/website")
async def put_website(
    body: WebsiteIn, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Depends(security.recent_auth)
) -> dict[str, Any]:
    try:
        w = store.Website(base_url=body.base_url.strip().rstrip("/"))
    except ValueError as e:
        raise AppError("WEBSITE_URL_INVALID", "Địa chỉ website không hợp lệ (vd https://xuongtramoc.vn).", 422) from e
    await store.put_setting(conn, "website", w, cur.actor)
    website.clear_cache()
    await audit.record(conn, cur.actor, "website.url_set", "settings:website", {"base_url": w.base_url})
    return w.model_dump()


class SiteKeyIn(BaseModel):
    api_key: str = Field(min_length=20, max_length=200)


@router.put("/website/keys/{kind}")
async def put_site_key(
    kind: Literal["read", "drafts", "publish"],
    body: SiteKeyIn,
    conn: AsyncConnection = Depends(db.get_db),
    cur: security.Current = Depends(security.recent_auth),
) -> dict[str, Any]:
    last4 = await store.put_secret(conn, website.KEYS[kind], body.api_key.strip(), cur.actor)
    website.clear_cache()
    await audit.record(conn, cur.actor, "website.key_set", f"website_key:{kind}", {"last4": last4})
    return {"kind": kind, "last4": last4}


@router.delete("/website/keys/{kind}")
async def delete_site_key(
    kind: Literal["read", "drafts", "publish"],
    conn: AsyncConnection = Depends(db.get_db),
    cur: security.Current = Depends(security.recent_auth),
) -> dict[str, Any]:
    await store.delete_secret(conn, website.KEYS[kind])
    await audit.record(conn, cur.actor, "website.key_deleted", f"website_key:{kind}", {})
    return {"kind": kind, "deleted": True}


@router.post("/website/test")
async def test_website(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> dict[str, Any]:
    try:
        cat = await website.catalog(conn, fresh=True)
    except AppError as e:
        return {"ok": False, "code": e.code, "detail": e.message}
    return {
        "ok": True,
        "products": len(cat.get("products") or []),
        "faqs": len(cat.get("published_faqs") or []),
        "blogs": len(cat.get("published_blogs") or []),
    }
