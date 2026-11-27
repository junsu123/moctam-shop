"""API Agent Core cho Control Center: trang từng agent (danh tính, bộ não, quyền công cụ, lịch sử), phiên bản bộ não
(so sánh, chạy thử, quay lại, nạp lại), danh mục công cụ, hàng chờ phê duyệt."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from app.brain import registry
from app.brain.loader import diff
from app.core import db, security
from app.core.config import get_settings
from app.core.errors import AppError
from app.domain import approvals
from app.tools.gateway import sync_registry

router = APIRouter(tags=["agent-core"])
Owner = Depends(security.require_role("owner", "manager"))
Viewer = Depends(security.current_user)
VN = ZoneInfo("Asia/Ho_Chi_Minh")
BRAIN_META = "id, brain_version, prompt_version, knowledge_version, skill_version, bundle_hash, core_rules_hash, state, created_at, created_by, activated_at"


async def _agent(conn: AsyncConnection, key: str) -> dict[str, Any]:
    row = await db.one(
        conn,
        "SELECT a.agent_key, a.display_name, a.department, a.kind, a.reports_to, a.role_summary, s.state, s.reason, s.changed_by, s.updated_at "
        "FROM agents a JOIN agent_status s ON s.agent_id = a.id WHERE a.agent_key = :k",
        {"k": key},
    )
    if row is None:
        raise AppError("AGENT_NOT_FOUND", "Không có agent này.", 404)
    return dict(row)


@router.get("/agents/{key}")
async def agent_detail(key: str, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    a = await _agent(conn, key)
    brain = await db.one(conn, f"SELECT {BRAIN_META}, bundle FROM agent_brains WHERE agent_key = :k AND state = 'active'", {"k": key})  # noqa: S608
    perms = await db.all_(
        conn,
        "SELECT p.tool_id, p.action, p.autonomy_level, p.limits, p.requires_approval, p.granted_by, p.expires_at, "
        "t.description AS tool_description, t.risk, t.available, t.actions -> p.action AS action_info "
        "FROM agent_permissions p LEFT JOIN tool_registry t ON t.id = p.tool_id WHERE p.agent_key = :k ORDER BY p.autonomy_level, p.tool_id, p.action",
        {"k": key},
    )
    day0 = datetime.now(VN).replace(hour=0, minute=0, second=0, microsecond=0)
    spent = float(
        await db.scalar(conn, "SELECT COALESCE(SUM(cost_usd), 0) FROM model_usage WHERE agent_key = :k AND at >= :d", {"k": key, "d": day0})
        or 0
    )
    reports = [
        dict(r)
        for r in await db.all_(conn, "SELECT agent_key, display_name FROM agents WHERE reports_to = :k ORDER BY sort_order", {"k": key})
    ]
    manager = (
        await db.one(conn, "SELECT agent_key, display_name FROM agents WHERE agent_key = :k", {"k": a["reports_to"]})
        if a["reports_to"]
        else None
    )
    integrity: dict[str, Any] = {"ok": False, "detail": "Chưa nạp bộ não"}
    if brain:
        try:
            await registry.resolve(conn, key)
            integrity = {"ok": True, "detail": "Hash khớp, quy tắc cốt lõi đã được duyệt"}
        except Exception as e:  # noqa: BLE001 — hiển thị cho Owner, không làm hỏng trang
            integrity = {"ok": False, "detail": "; ".join(getattr(e, "problems", [str(e)]))}
    pending = await db.scalar(
        conn, "SELECT count(*) FROM approvals a WHERE status = 'pending' AND expires_at > now() AND (payload ->> 'agent') = :k", {"k": key}
    )
    return {
        **a,
        "manager": dict(manager) if manager else None,
        "direct_reports": reports,
        "brain": {k: v for k, v in dict(brain).items() if k != "bundle"} if brain else None,
        "bundle": brain["bundle"] if brain else None,
        "integrity": integrity,
        "permissions": [dict(p) for p in perms],
        "spend_today_usd": round(spent, 4),
        "approvals_pending": int(pending or 0),
    }


@router.get("/agents/{key}/brains")
async def brain_versions(key: str, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> list[dict[str, Any]]:
    await _agent(conn, key)
    rows = await db.all_(conn, f"SELECT {BRAIN_META} FROM agent_brains WHERE agent_key = :k ORDER BY created_at DESC", {"k": key})  # noqa: S608
    return [dict(r) for r in rows]


@router.get("/agents/{key}/brains/diff")
async def brain_diff(
    key: str, a: str = Query(...), b: str = Query(...), conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer
) -> dict[str, Any]:
    rows = {
        str(r["id"]): r
        for r in await db.all_(
            conn,
            "SELECT id, brain_version, bundle FROM agent_brains WHERE agent_key = :k AND id IN (CAST(:a AS uuid), CAST(:b AS uuid))",
            {"k": key, "a": a, "b": b},
        )
    }
    if a not in rows or b not in rows:
        raise AppError("BRAIN_NOT_FOUND", "Không có phiên bản bộ não này.", 404)
    return {"from": rows[a]["brain_version"], "to": rows[b]["brain_version"], "changes": diff(rows[a]["bundle"], rows[b]["bundle"])}


@router.get("/agents/{key}/history")
async def agent_history(key: str, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    await _agent(conn, key)
    versions = await db.all_(
        conn,
        "SELECT id, at, event, component, from_version, to_version, brain_id, proposed_by, approved_by, jsonb_array_length(diff) AS changes "
        "FROM agent_versions WHERE agent_key = :k ORDER BY id DESC LIMIT 100",
        {"k": key},
    )
    decisions = await db.all_(
        conn,
        "SELECT id, at, tool_id, action, decision, rule, reason FROM policy_decisions WHERE agent_key = :k ORDER BY id DESC LIMIT 50",
        {"k": key},
    )
    calls = await db.all_(
        conn,
        "SELECT id, at, tool_id, action, task_id, status, error_code, error, attempts, duration_ms, approval_id "
        "FROM tool_invocations WHERE agent_key = :k ORDER BY at DESC LIMIT 50",
        {"k": key},
    )
    return {"versions": [dict(r) for r in versions], "decisions": [dict(r) for r in decisions], "invocations": [dict(r) for r in calls]}


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.post("/agents/{key}/brains/{brain_id}/shadow")
async def brain_shadow(
    key: str, brain_id: str, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, bool]:
    owner = await db.scalar(conn, "SELECT agent_key FROM agent_brains WHERE id = CAST(:i AS uuid)", {"i": brain_id})
    if owner != key:
        raise AppError("BRAIN_NOT_FOUND", "Không có phiên bản bộ não này.", 404)
    await registry.set_shadow(conn, brain_id, cur.actor)
    return {"ok": True}


@router.post("/agents/{key}/brains/{brain_id}/rollback")
async def brain_rollback(
    key: str, brain_id: str, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Depends(security.recent_auth)
) -> dict[str, bool]:
    await registry.rollback(conn, key, brain_id, cur.actor)
    return {"ok": True}


@router.post("/brains/sync")
async def brains_sync(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> list[dict[str, Any]]:
    """Đọc lại thư mục brains/. Bản mới chỉ thành bản nháp chờ duyệt; không có gì được kích hoạt tự động (trừ lần nạp đầu)."""
    await sync_registry(conn)
    items = await registry.sync_all(conn, get_settings().brains_dir, cur.actor)
    return [i.__dict__ for i in items]


# ------------------------------------------------------------------ công cụ
@router.get("/tools")
async def tool_list(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> list[dict[str, Any]]:
    rows = await db.all_(
        conn,
        "SELECT id, description, actions, side_effects, risk, default_timeout_s, retry_policy, available FROM tool_registry ORDER BY id",
    )
    grants = await db.all_(
        conn,
        "SELECT p.tool_id, p.action, p.agent_key, a.display_name, p.autonomy_level "
        "FROM agent_permissions p JOIN agents a ON a.agent_key = p.agent_key ORDER BY a.sort_order",
    )
    by_tool: dict[str, list[dict[str, Any]]] = {}
    for g in grants:
        by_tool.setdefault(g["tool_id"], []).append(
            {"action": g["action"], "agent_key": g["agent_key"], "display_name": g["display_name"], "level": g["autonomy_level"]}
        )
    return [{**dict(r), "grants": by_tool.get(r["id"], [])} for r in rows]


# ------------------------------------------------------------------ phê duyệt
@router.get("/approvals")
async def approval_list(
    status: Literal["pending", "done"] = "pending", conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer
) -> list[dict[str, Any]]:
    await approvals.expire_due(conn)
    where = "status = 'pending'" if status == "pending" else "status <> 'pending'"
    order = "created_at DESC" if status == "pending" else "decided_at DESC NULLS LAST"
    rows = await db.all_(conn, f"SELECT * FROM approvals WHERE {where} ORDER BY {order} LIMIT 200")  # noqa: S608
    return [dict(r) for r in rows]


@router.get("/approvals/count")
async def approval_count(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, int]:
    n = await db.scalar(conn, "SELECT count(*) FROM approvals WHERE status = 'pending' AND expires_at > now()")
    return {"pending": int(n or 0)}


class DecideIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=500)


@router.post("/approvals/{approval_id}/decide")
async def approval_decide(
    approval_id: str, body: DecideIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    row = await db.one(conn, "SELECT risk, status FROM approvals WHERE id = CAST(:i AS uuid)", {"i": approval_id})
    if row is None:
        raise AppError("APPROVAL_NOT_FOUND", "Không có yêu cầu duyệt này.", 404)
    if row["risk"] == "high" and body.approve and (cur.reauth_until is None or cur.reauth_until < datetime.now(UTC)):
        # Rủi ro cao (đổi quyền, thăng hạng bộ não, tiêu tiền…): chỉ duyệt sau khi xác thực lại (SECURITY_PLAN §3.2)
        raise AppError("REAUTH_REQUIRED", "Duyệt việc rủi ro cao cần nhập lại mật khẩu và mã xác thực.", 403)
    return await approvals.decide(conn, approval_id, body.approve, cur.actor, body.note)
