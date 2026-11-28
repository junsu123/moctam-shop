"""API Task Engine cho Control Center: giao việc, xem tiến độ từng bước, hủy, chạy lại, review thay Owner; lịch tự động; văn phòng trực tiếp."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db, security
from app.core.errors import AppError
from app.core.ids import uuid7
from app.domain.approvals import _json
from app.tasks import engine, graph, runtime, scheduler

router = APIRouter(tags=["tasks"])
Owner = Depends(security.require_role("owner", "manager"))
Viewer = Depends(security.current_user)
VN = ZoneInfo("Asia/Ho_Chi_Minh")
GROUPS = {
    "active": ("CREATED", "PENDING", "ASSIGNED", "IN_PROGRESS"),
    "waiting": ("WAITING_REVIEW", "WAITING_APPROVAL"),
    "done": ("COMPLETED",),
    "failed": ("FAILED", "CANCELLED"),
}
LIST_COLS = (
    "t.id, t.parent_id, t.root_id, t.depth, t.title, t.task_type, t.status, t.priority, t.assigned_agent, a.display_name AS agent_name, "
    "a.department, t.created_by, t.deadline, t.budget_usd, t.spent_usd, t.graph_node, t.wait_kind, t.attempt, t.max_attempts, "
    "t.error_code, t.error, t.result_summary, t.created_at, t.updated_at, t.finished_at, "
    "(SELECT count(*) FROM tasks c WHERE c.parent_id = t.id) AS children"
)


@router.get("/tasks/stats")
async def task_stats(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    by = {r["status"]: int(r["n"]) for r in await db.all_(conn, "SELECT status, count(*) n FROM tasks GROUP BY status")}
    owner_reviews = await db.scalar(
        conn,
        "SELECT count(*) FROM tasks WHERE status = 'WAITING_REVIEW' AND coalesce(reviewer, CASE WHEN created_by LIKE 'agent:%' "
        "THEN created_by ELSE 'owner' END) = 'owner'",
    )
    return {
        "by_status": by,
        "groups": {g: sum(by.get(s, 0) for s in sts) for g, sts in GROUPS.items()},
        "owner_reviews": int(owner_reviews or 0),
        "spent_today_usd": float(
            await db.scalar(
                conn,
                "SELECT coalesce(sum(spent_usd), 0) FROM tasks "
                "WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Ho_Chi_Minh') AT TIME ZONE 'Asia/Ho_Chi_Minh'",
            )
            or 0
        ),
    }


@router.get("/tasks")
async def task_list(
    group: Literal["active", "waiting", "done", "failed"] | None = None,
    agent: str | None = None,
    root: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    top: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    conn: AsyncConnection = Depends(db.get_db),
    cur: security.Current = Viewer,
) -> dict[str, Any]:
    where: list[str] = ["true"]
    p: dict[str, Any] = {"l": limit, "o": offset}
    if group:
        where.append("t.status = ANY(:sts)")
        p["sts"] = list(GROUPS[group])
    if agent:
        where.append("t.assigned_agent = :a")
        p["a"] = agent
    if root:
        where.append("t.root_id = CAST(:r AS uuid)")
        p["r"] = root
    if top:
        where.append("t.parent_id IS NULL AND t.task_type <> 'review'")
    if q:
        where.append("t.title ILIKE :q")
        p["q"] = f"%{q}%"
    w = " AND ".join(where)
    items = [
        dict(r)
        for r in await db.all_(
            conn,
            f"SELECT {LIST_COLS} FROM tasks t LEFT JOIN agents a ON a.agent_key = t.assigned_agent WHERE {w} "  # noqa: S608 — điều kiện cố định
            "ORDER BY t.updated_at DESC LIMIT :l OFFSET :o",
            p,
        )
    ]
    total = await db.scalar(conn, f"SELECT count(*) FROM tasks t WHERE {w}", p)  # noqa: S608
    return {"items": items, "total": int(total or 0)}


@router.get("/tasks/{task_id}")
async def task_detail(task_id: str, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    await engine.get(conn, task_id)  # kiểm định dạng id, 404 nếu không có
    t = await db.one(
        conn,
        f"SELECT {LIST_COLS}, t.description, t.input_data, t.output_data, t.success_criteria, t.requires_review, t.reviewer, "  # noqa: S608
        "t.requires_approval, t.autonomy_max, t.brain_id, t.started_at, t.lease_owner "
        "FROM tasks t LEFT JOIN agents a ON a.agent_key = t.assigned_agent WHERE t.id = CAST(:i AS uuid)",
        {"i": task_id},
    )
    if t is None:
        raise AppError("TASK_NOT_FOUND", "Không có việc này.", 404)
    logs = [
        dict(r)
        for r in await db.all_(
            conn,
            "SELECT l.id, l.at, l.event, l.node, l.step_no, l.text, l.agent_key, a.display_name AS agent_name FROM task_logs l "
            "LEFT JOIN agents a ON a.agent_key = l.agent_key WHERE l.task_id = :t ORDER BY l.id",
            {"t": t["id"]},
        )
    ]
    children = [
        dict(r)
        for r in await db.all_(
            conn,
            f"SELECT {LIST_COLS} FROM tasks t LEFT JOIN agents a ON a.agent_key = t.assigned_agent WHERE t.parent_id = :p ORDER BY t.created_at",  # noqa: S608
            {"p": t["id"]},
        )
    ]
    reviews = [
        dict(r)
        for r in await db.all_(
            conn, "SELECT round, reviewer, verdict, notes, created_at FROM task_reviews WHERE task_id = :t ORDER BY round", {"t": t["id"]}
        )
    ]
    messages = [
        dict(r)
        for r in await db.all_(
            conn,
            "SELECT id, message_type, sender, receiver, status, created_at, delivered_at, last_error FROM agent_messages "
            "WHERE task_id = :t ORDER BY created_at",
            {"t": t["id"]},
        )
    ]
    tools = [
        dict(r)
        for r in await db.all_(
            conn,
            "SELECT id, tool_id, action, status, error_code, error, at, finished_at, duration_ms FROM tool_invocations WHERE task_id = :t ORDER BY at",
            {"t": str(t["id"])},
        )
    ]
    appr = [
        dict(r)
        for r in await db.all_(
            conn,
            "SELECT id, title, status, created_at, decided_at, decision_note FROM approvals WHERE (subject_type = 'task_output' AND subject_id = :t) "
            "OR (subject_type = 'tool_call' AND subject_id IN (SELECT idempotency_key FROM tool_invocations WHERE task_id = :t)) ORDER BY created_at",
            {"t": str(t["id"])},
        )
    ]
    parent = None
    if t["parent_id"]:
        parent = await db.one(conn, "SELECT id, title, assigned_agent, status FROM tasks WHERE id = :p", {"p": t["parent_id"]})
    return {
        "task": dict(t),
        "parent": dict(parent) if parent else None,
        "logs": logs,
        "children": children,
        "reviews": reviews,
        "messages": messages,
        "tools": tools,
        "approvals": appr,
        "can_review": t["status"] == "WAITING_REVIEW" and _reviewer(dict(t)) == "owner",
        "next_round": int(
            await db.scalar(conn, "SELECT coalesce(max(round), 0) + 1 FROM task_reviews WHERE task_id = :t", {"t": t["id"]}) or 1
        ),
    }


def _reviewer(t: dict[str, Any]) -> str:
    return str(t.get("reviewer") or (t["created_by"] if str(t["created_by"]).startswith("agent:") else "owner"))


class TaskIn(BaseModel):
    agent: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=4000)
    success_criteria: list[str] = Field(default_factory=list, max_length=10)
    budget_usd: float = Field(default=0.5, gt=0, le=5)
    deadline: date | None = None
    priority: int = Field(default=2, ge=0, le=3)
    requires_approval: bool = False
    requires_review: bool = False
    task_type: Literal["generic", "faq", "blog"] = "generic"
    publish: bool = False  # FAQ/blog: viết xong, Giám đốc Marketing review, rồi vào lịch xuất bản (ADR-16)
    product_id: int | None = Field(default=None, ge=1)


@router.post("/tasks", status_code=201)
async def task_create(body: TaskIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> dict[str, Any]:
    dl = datetime.combine(body.deadline, time(23, 59), VN).astimezone(UTC) if body.deadline else None
    if dl and dl < datetime.now(UTC):
        raise AppError("TASK_DEADLINE_PAST", "Hạn chót đã qua.", 422)
    crit: list[Any] = [c.strip() for c in body.success_criteria if c.strip()]
    publish = body.publish and body.task_type in ("faq", "blog")
    if publish and body.agent == "marketing_director":
        raise AppError("TASK_REVIEWER_SELF", "Giám đốc Marketing là người review bài đăng; giao viết cho Nội dung hoặc SEO.", 422)
    t = await engine.create(
        conn,
        title=body.title,
        description=body.description,
        created_by=cur.actor,
        assigned_agent=body.agent,
        success_criteria=crit,
        budget_usd=body.budget_usd,
        deadline=dl,
        priority=body.priority,
        requires_approval=body.requires_approval,
        requires_review=body.requires_review or publish,
        reviewer="agent:marketing_director" if publish else ("owner" if body.requires_review else None),
        autonomy_max=3,
        task_type=body.task_type,
        input_data={"publish": True, "product_id": body.product_id}
        if publish
        else ({"product_id": body.product_id} if body.product_id else {}),
    )
    await engine.kick()
    return {"id": str(t["id"]), "status": t["status"]}


class CancelIn(BaseModel):
    reason: str = Field(default="Owner hủy", min_length=2, max_length=500)


@router.post("/tasks/{task_id}/cancel")
async def task_cancel(
    task_id: str, body: CancelIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    ids = await engine.cancel(conn, task_id, actor=cur.actor, reason=body.reason)
    if not ids:
        raise AppError("TASK_CLOSED", "Việc này đã kết thúc.", 409)
    return {"cancelled": len(ids)}


@router.post("/tasks/{task_id}/retry")
async def task_retry(task_id: str, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> dict[str, Any]:
    t = await engine.retry(conn, task_id, actor=cur.actor)
    return {"status": t["status"]}


class ReviewIn(BaseModel):
    verdict: Literal["approve", "request_changes", "reject"]
    notes: str = Field(default="", max_length=2000)


@router.post("/tasks/{task_id}/review")
async def task_review(
    task_id: str, body: ReviewIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    t = await engine.get(conn, task_id, lock=True)
    if t["status"] != "WAITING_REVIEW":
        raise AppError("TASK_NOT_IN_REVIEW", "Việc này không ở bước chờ review.", 409)
    if _reviewer(t) != "owner":
        raise AppError("TASK_REVIEWER_NOT_OWNER", "Việc này do agent cấp trên review.", 403)
    if body.verdict == "request_changes" and len(body.notes.strip()) < 5:
        raise AppError("REVIEW_NOTES_REQUIRED", "Yêu cầu sửa thì ghi rõ cần sửa gì.", 422)
    rnd = int(await db.scalar(conn, "SELECT coalesce(max(round), 0) + 1 FROM task_reviews WHERE task_id = :t", {"t": t["id"]}) or 1)
    await runtime.record_review(conn, task_id, rnd, cur.actor, body.verdict, body.notes.strip())
    await audit.record(conn, cur.actor, "task.reviewed", f"task:{task_id}", {"verdict": body.verdict, "round": rnd})
    return {"round": rnd}


@router.get("/tasks/{task_id}/state")
async def task_graph_state(task_id: str, cur: security.Current = Viewer) -> dict[str, Any]:
    """Trạng thái đồ thị đã lưu (checkpoint): nút kế tiếp, điều kiện đang chờ. Để chẩn đoán."""
    st = await graph.state(task_id)
    if st is None:
        return {"exists": False}
    v = st["values"]
    return {
        "exists": True,
        "next": st["next"],
        "interrupt": st["interrupt"],
        "round": v.get("round"),
        "step_index": v.get("step_index"),
        "recalled": [m["id"] for m in v.get("recalled") or []],
        "feedback": v.get("feedback") or [],
    }


# ------------------------------------------------------------------ văn phòng trực tiếp
@router.get("/live")
async def live(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    agents = [
        dict(r)
        for r in await db.all_(
            conn,
            "SELECT a.agent_key, a.display_name, a.department, a.kind, s.state, "
            "(SELECT row_to_json(x) FROM (SELECT id, title, status, graph_node, updated_at FROM tasks WHERE assigned_agent = a.agent_key "
            " AND status = 'IN_PROGRESS' ORDER BY updated_at DESC LIMIT 1) x) AS current, "
            "(SELECT count(*) FROM tasks WHERE assigned_agent = a.agent_key AND status IN ('ASSIGNED','PENDING')) AS queued, "
            "(SELECT count(*) FROM tasks WHERE assigned_agent = a.agent_key AND status IN ('WAITING_REVIEW','WAITING_APPROVAL')) AS waiting, "
            "(SELECT count(*) FROM tasks WHERE assigned_agent = a.agent_key AND status = 'COMPLETED' "
            "AND finished_at > now() - interval '24 hours') AS done_24h "
            "FROM agents a JOIN agent_status s ON s.agent_id = a.id ORDER BY a.sort_order",
        )
    ]
    need = {
        "approvals": int(await db.scalar(conn, "SELECT count(*) FROM approvals WHERE status = 'pending'") or 0),
        "reviews": int(
            await db.scalar(
                conn,
                "SELECT count(*) FROM tasks WHERE status = 'WAITING_REVIEW' AND coalesce(reviewer, CASE WHEN created_by LIKE 'agent:%' "
                "THEN created_by ELSE 'owner' END) = 'owner'",
            )
            or 0
        ),
        "failed": int(await db.scalar(conn, "SELECT count(*) FROM tasks WHERE status = 'FAILED' AND attempt >= max_attempts") or 0),
    }
    return {"agents": agents, "need_owner": need}


# ------------------------------------------------------------------ lịch tự động
class ScheduleIn(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    agent: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    cron: str = Field(min_length=9, max_length=100)
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=2000)
    success_criteria: list[str] = Field(default_factory=list, max_length=10)
    budget_usd: float = Field(default=0.2, gt=0, le=2)
    requires_approval: bool = False


@router.get("/schedules")
async def schedules(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in await db.all_(
            conn,
            "SELECT s.id, s.name, s.agent_key, a.display_name AS agent_name, s.cron, s.timezone, s.task_template, s.enabled, "
            "s.last_run_at, s.next_run_at FROM schedules s JOIN agents a ON a.agent_key = s.agent_key ORDER BY s.name",
        )
    ]


@router.post("/schedules", status_code=201)
async def schedule_create(body: ScheduleIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> dict[str, Any]:
    nxt = scheduler.next_after(body.cron, datetime.now(UTC))
    if not await db.scalar(conn, "SELECT EXISTS (SELECT 1 FROM agents WHERE agent_key = :a)", {"a": body.agent}):
        raise AppError("AGENT_NOT_FOUND", "Không có agent này.", 404)
    sid = uuid7()
    tpl = {
        "title": body.title,
        "description": body.description,
        "success_criteria": [c for c in body.success_criteria if c.strip()],
        "budget_usd": body.budget_usd,
        "requires_approval": body.requires_approval,
    }
    try:
        await db.execute(
            conn,
            "INSERT INTO schedules(id, name, agent_key, cron, task_template, next_run_at, created_by) VALUES (:i, :n, :a, :c, CAST(:t AS jsonb), :x, :by)",
            {"i": sid, "n": body.name, "a": body.agent, "c": body.cron, "t": _json(tpl), "x": nxt, "by": cur.actor},
        )
    except Exception as e:
        if "schedules_name_key" in str(e):
            raise AppError("SCHEDULE_EXISTS", "Đã có lịch cùng tên.", 409) from e
        raise
    await audit.record(conn, cur.actor, "schedule.created", f"schedule:{sid}", {"name": body.name, "cron": body.cron})
    return {"id": sid, "next_run_at": nxt}


class ScheduleToggle(BaseModel):
    enabled: bool


@router.patch("/schedules/{sid}")
async def schedule_toggle(
    sid: str, body: ScheduleToggle, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    r = await db.one(conn, "SELECT cron, timezone FROM schedules WHERE id = CAST(:i AS uuid)", {"i": sid})
    if r is None:
        raise AppError("SCHEDULE_NOT_FOUND", "Không có lịch này.", 404)
    nxt = scheduler.next_after(r["cron"], datetime.now(UTC), r["timezone"]) if body.enabled else None
    await db.execute(
        conn, "UPDATE schedules SET enabled = :e, next_run_at = :x WHERE id = CAST(:i AS uuid)", {"e": body.enabled, "x": nxt, "i": sid}
    )
    await audit.record(conn, cur.actor, "schedule.toggled", f"schedule:{sid}", {"enabled": body.enabled})
    return {"enabled": body.enabled, "next_run_at": nxt}


@router.delete("/schedules/{sid}")
async def schedule_delete(sid: str, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> dict[str, Any]:
    n = await db.execute(conn, "DELETE FROM schedules WHERE id = CAST(:i AS uuid)", {"i": sid})
    if n == 0:
        raise AppError("SCHEDULE_NOT_FOUND", "Không có lịch này.", 404)
    await audit.record(conn, cur.actor, "schedule.deleted", f"schedule:{sid}", {})
    return {"deleted": True}
