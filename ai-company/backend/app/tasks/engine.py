"""Task Engine (SRS §7, ARCHITECTURE ADR-04): 9 trạng thái, lease, retry giãn cách, timeout, phụ thuộc, hủy lan xuống.

Bảng `tasks` là nguồn sự thật nghiệp vụ VÀ là hàng đợi bền: worker nhận việc bằng `FOR UPDATE SKIP LOCKED` + lease có hạn.
Worker chết thì lease hết hạn và worker khác nhận lại; đồ thị LangGraph chạy tiếp từ checkpoint (ADR-05).

Ý nghĩa trạng thái trong mã này:
- PENDING: đang chờ điều kiện (phụ thuộc/task con chưa xong, chờ giờ thử lại `not_before`).
- ASSIGNED: sẵn sàng, đang xếp hàng chờ worker.
- IN_PROGRESS: worker đang chạy (có lease), hoặc vừa được đánh thức sau duyệt/review (lease rỗng: worker kế tiếp nhận).
Mọi chuyển trạng thái đi qua `transition` (một hàm duy nhất, có khóa phiên bản); CSDL kiểm thêm bằng trigger.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db
from app.core.errors import AppError
from app.core.ids import uuid7
from app.domain.approvals import _json

log = logging.getLogger("aico.tasks")

STATUSES = (
    "CREATED",
    "PENDING",
    "ASSIGNED",
    "IN_PROGRESS",
    "WAITING_REVIEW",
    "WAITING_APPROVAL",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)
TERMINAL = {"COMPLETED", "CANCELLED"}
ALLOWED: dict[str, set[str]] = {
    "CREATED": {"PENDING", "CANCELLED"},
    "PENDING": {"ASSIGNED", "CANCELLED"},
    "ASSIGNED": {"IN_PROGRESS", "PENDING", "CANCELLED"},
    "IN_PROGRESS": {"PENDING", "WAITING_REVIEW", "WAITING_APPROVAL", "COMPLETED", "FAILED", "CANCELLED"},
    "WAITING_REVIEW": {"IN_PROGRESS", "WAITING_APPROVAL", "COMPLETED", "CANCELLED"},
    "WAITING_APPROVAL": {"IN_PROGRESS", "COMPLETED", "CANCELLED"},
    "FAILED": {"PENDING", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}
STATUS_TEXT = {
    "CREATED": "mới tạo",
    "PENDING": "đang chờ",
    "ASSIGNED": "chờ làm",
    "IN_PROGRESS": "đang làm",
    "WAITING_REVIEW": "chờ review",
    "WAITING_APPROVAL": "chờ duyệt",
    "COMPLETED": "xong",
    "FAILED": "lỗi",
    "CANCELLED": "đã hủy",
}
MAX_DEPTH = 4  # AGENT_DESIGN §5
MAX_CHILDREN = 6
LOOP_LIMIT = 3  # cùng (người giao, người nhận, loại việc) quá 3 lần/giờ thì chặn
LEASE_S = 120
RETRY_BASE_S = 30
RETRYABLE = {"LLM_FAILED", "TIMEOUT", "PROVIDER_DOWN", "RATE_LIMITED", "NETWORK", "ERROR", "TOOL_FAILED", "LEASE_LOST", "INTERNAL"}


def can(cur: str, to: str) -> bool:
    return cur == to or to in ALLOWED.get(cur, set())


async def log_event(
    conn: AsyncConnection,
    task_id: str,
    event: str,
    text: str,
    *,
    agent: str | None = None,
    node: str | None = None,
    step: int | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    await db.execute(
        conn,
        "INSERT INTO task_logs(task_id, agent_key, event, node, step_no, text, data) VALUES (CAST(:t AS uuid), :a, :e, :n, :s, :x, CAST(:d AS jsonb))",
        {"t": task_id, "a": agent, "e": event, "n": node, "s": step, "x": text[:1000], "d": _json(data or {})},
    )


async def get(conn: AsyncConnection, task_id: str, *, lock: bool = False) -> dict[str, Any]:
    try:
        uuid.UUID(str(task_id))
    except ValueError:
        raise AppError("TASK_NOT_FOUND", "Không có task này.", 404) from None
    sql = "SELECT * FROM tasks WHERE id = CAST(:i AS uuid) FOR UPDATE" if lock else "SELECT * FROM tasks WHERE id = CAST(:i AS uuid)"
    row = await db.one(conn, sql, {"i": task_id})
    if row is None:
        raise AppError("TASK_NOT_FOUND", "Không có task này.", 404)
    return dict(row)


async def transition(
    conn: AsyncConnection,
    task_id: str,
    to: str,
    *,
    actor: str,
    reason: str = "",
    expect: set[str] | None = None,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hàm DUY NHẤT đổi trạng thái task: kiểm bảng chuyển, khóa dòng, tăng `version`, ghi task_logs."""
    t = await get(conn, task_id, lock=True)
    cur = t["status"]
    if expect is not None and cur not in expect:
        raise AppError("TASK_STATE_CONFLICT", f"Task đang {STATUS_TEXT[cur]}, không thể chuyển sang {STATUS_TEXT[to]}.", 409)
    if not can(cur, to):
        raise AppError("TASK_TRANSITION_INVALID", f"Không thể chuyển task từ {STATUS_TEXT[cur]} sang {STATUS_TEXT[to]}.", 409)
    f = dict(fields or {})
    if to in ("COMPLETED", "CANCELLED", "FAILED"):
        f.setdefault("finished_at", datetime.now(UTC))
    if to != "IN_PROGRESS" or "lease_owner" not in f:
        f.setdefault("lease_owner", None)
        f.setdefault("lease_until", None)
    sets = ", ".join(f"{k} = :{k}" for k in f)
    params = {**f, "id": t["id"], "s": to, "v": t["version"]}
    for k in ("input_data", "output_data", "success_criteria"):
        if k in params and not isinstance(params[k], str) and params[k] is not None:
            params[k] = _json(params[k])
            sets = sets.replace(f"{k} = :{k}", f"{k} = CAST(:{k} AS jsonb)")
    row = await db.one(
        conn,
        f"UPDATE tasks SET status = :s, version = version + 1, updated_at = now(){', ' + sets if sets else ''} "  # noqa: S608 — tên cột từ mã
        "WHERE id = :id AND version = :v RETURNING *",
        params,
    )
    if row is None:
        raise AppError("TASK_VERSION_CONFLICT", "Task vừa được cập nhật ở nơi khác, thử lại.", 409)
    if cur != to:
        txt = f"{STATUS_TEXT[cur]} → {STATUS_TEXT[to]}" + (f": {reason}" if reason else "")
        await log_event(conn, task_id, "status", txt, agent=t["assigned_agent"], data={"from": cur, "to": to, "actor": actor})
    return dict(row)


# ------------------------------------------------------------------ tạo task
async def check_child(conn: AsyncConnection, p: dict[str, Any], budget_usd: float, *, exclude: str | None = None) -> tuple[int, str]:
    """Ràng buộc task con (AGENT_DESIGN §5): cha chưa đóng, độ sâu ≤ 4, ≤ 6 con, ngân sách con ≤ phần còn lại của cha.

    Ngân sách đã hứa cho task con đang chờ tạo (message `task_request` chưa phát) cũng được tính."""
    if p["status"] in TERMINAL:
        raise AppError("TASK_PARENT_CLOSED", "Task cha đã đóng.", 409)
    depth = int(p["depth"]) + 1
    if depth > MAX_DEPTH:
        raise AppError("TASK_TOO_DEEP", f"Cây việc sâu quá {MAX_DEPTH} tầng.", 422)
    kids = await db.all_(
        conn,
        "SELECT CAST(payload->>'task_id' AS uuid) AS id, CAST(payload->>'budget_usd' AS numeric) AS b FROM agent_messages "
        "WHERE task_id = :p AND message_type = 'task_request' AND status <> 'failed' "
        "UNION SELECT id, budget_usd FROM tasks WHERE parent_id = :p",
        {"p": p["id"]},
    )
    kids = [k for k in kids if str(k["id"]) != (exclude or "")]
    if len(kids) >= MAX_CHILDREN:
        raise AppError("TASK_TOO_MANY_CHILDREN", f"Một task tối đa {MAX_CHILDREN} task con.", 422)
    remaining = float(p["budget_usd"]) - float(p["spent_usd"]) - sum(float(k["b"] or 0) for k in kids)
    if budget_usd > remaining + 1e-9:
        raise AppError("TASK_BUDGET_EXCEEDED", f"Ngân sách task con vượt phần còn lại của task cha ({remaining:.4f} USD).", 422)
    return depth, str(p["root_id"])


async def _would_cycle(conn: AsyncConnection, task_id: str, deps: list[str]) -> bool:
    if not deps:
        return False
    hit = await db.scalar(
        conn,
        "WITH RECURSIVE up(id) AS (SELECT CAST(d AS uuid) FROM unnest(CAST(:deps AS text[])) d "
        "UNION SELECT td.depends_on FROM task_dependencies td JOIN up ON td.task_id = up.id) "
        "SELECT EXISTS (SELECT 1 FROM up WHERE id = CAST(:t AS uuid))",
        {"deps": deps, "t": task_id},
    )
    return bool(hit)


async def add_dependency(conn: AsyncConnection, task_id: str, depends_on: str) -> None:
    if task_id == depends_on or await _would_cycle(conn, task_id, [depends_on]):
        raise AppError("TASK_DEPENDENCY_CYCLE", "Phụ thuộc này tạo vòng lặp.", 422)
    await db.execute(
        conn,
        "INSERT INTO task_dependencies(task_id, depends_on) VALUES (CAST(:t AS uuid), CAST(:d AS uuid)) ON CONFLICT DO NOTHING",
        {"t": task_id, "d": depends_on},
    )


async def create(
    conn: AsyncConnection,
    *,
    title: str,
    created_by: str,
    assigned_agent: str,
    description: str = "",
    task_type: str = "generic",
    priority: int = 2,
    deadline: datetime | None = None,
    input_data: dict[str, Any] | None = None,
    success_criteria: list[Any] | None = None,
    requires_review: bool = False,
    reviewer: str | None = None,
    requires_approval: bool = False,
    autonomy_max: int = 2,
    budget_usd: float = 0.5,
    parent_id: str | None = None,
    depends_on: list[str] | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
    timeout_s: int = 1800,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Tạo task và đưa vào hàng đợi. Hợp đồng giao việc (AGENT_DESIGN §5) kiểm ở đây, sai thì từ chối tạo."""
    if idempotency_key:
        old = await db.one(conn, "SELECT * FROM tasks WHERE idempotency_key = :k", {"k": idempotency_key})
        if old:
            return dict(old)
    agent = await db.one(
        conn,
        "SELECT a.agent_key, s.state FROM agents a JOIN agent_status s ON s.agent_id = a.id WHERE a.agent_key = :k",
        {"k": assigned_agent},
    )
    if agent is None:
        raise AppError("AGENT_NOT_FOUND", f"Không có agent {assigned_agent}.", 404)
    if agent["state"] == "disabled":
        raise AppError("AGENT_DISABLED", "Agent này đang tắt.", 409)
    criteria = list(success_criteria or [])
    if task_type in ("faq", "blog") and not any(isinstance(c, dict) and c.get("type") == "required_fields" for c in criteria):
        criteria.append({"type": "required_fields", "fields": ["title", "body"], "description": "có tiêu đề và nội dung"})
    by_agent = created_by.startswith("agent:")
    if by_agent:  # hợp đồng giao việc giữa agent: tiêu chí đo được, ngân sách, hạn chót
        if not criteria:
            raise AppError("TASK_CONTRACT_INVALID", "Giao việc phải có tiêu chí thành công đo được.", 422)
        if budget_usd <= 0:
            raise AppError("TASK_CONTRACT_INVALID", "Giao việc phải có ngân sách.", 422)
        if deadline is None:
            raise AppError("TASK_CONTRACT_INVALID", "Giao việc phải có hạn chót.", 422)
    depth, root = 0, None
    if parent_id:
        p = await get(conn, parent_id, lock=True)
        depth, root = await check_child(conn, p, budget_usd, exclude=task_id)
        if p["deadline"] and (deadline is None or deadline > p["deadline"]):
            deadline = p["deadline"]
        autonomy_max = min(autonomy_max, int(p["autonomy_max"]))
    if by_agent:
        recent = await db.scalar(
            conn,
            "SELECT count(*) FROM tasks WHERE created_by = :c AND assigned_agent = :a AND task_type = :t AND created_at > now() - interval '1 hour'",
            {"c": created_by, "a": assigned_agent, "t": task_type},
        )
        if int(recent or 0) >= LOOP_LIMIT:
            raise AppError(
                "TASK_LOOP_BLOCKED", "Giao cùng một loại việc cho cùng agent quá 3 lần trong 1 giờ: đã chặn và báo cấp trên.", 429
            )
    tid = str(task_id or uuid7())
    deps = list(dict.fromkeys(depends_on or []))
    if await _would_cycle(conn, tid, deps):
        raise AppError("TASK_DEPENDENCY_CYCLE", "Phụ thuộc này tạo vòng lặp.", 422)
    brain_id = await db.scalar(conn, "SELECT id FROM agent_brains WHERE agent_key = :a AND state = 'active'", {"a": assigned_agent})
    row = await db.one(
        conn,
        "INSERT INTO tasks(id, parent_id, root_id, depth, title, description, task_type, created_by, assigned_agent, priority, deadline, "
        "input_data, success_criteria, requires_review, reviewer, requires_approval, autonomy_max, budget_usd, brain_id, idempotency_key, "
        "max_attempts, timeout_s) VALUES (:id, CAST(:p AS uuid), CAST(:r AS uuid), :d, :ti, :de, :tt, :cb, :a, :pr, :dl, CAST(:in AS jsonb), "
        "CAST(:sc AS jsonb), :rv, :rver, :ra, :am, :b, :bid, :k, :ma, :to) ON CONFLICT (idempotency_key) DO NOTHING RETURNING *",
        {
            "id": tid,
            "p": parent_id,
            "r": root or tid,
            "d": depth,
            "ti": title.strip()[:300],
            "de": description,
            "tt": task_type,
            "cb": created_by,
            "a": assigned_agent,
            "pr": priority,
            "dl": deadline,
            "in": _json(input_data or {}),
            "sc": _json(criteria),
            "rv": requires_review,
            "rver": reviewer,
            "ra": requires_approval,
            "am": autonomy_max,
            "b": budget_usd,
            "bid": brain_id,
            "k": idempotency_key,
            "ma": max_attempts,
            "to": timeout_s,
        },
    )
    if row is None:  # tranh chấp cùng khóa chống trùng
        old = await db.one(conn, "SELECT * FROM tasks WHERE idempotency_key = :k", {"k": idempotency_key})
        assert old is not None
        return dict(old)
    for d in deps:
        await add_dependency(conn, tid, d)
    await log_event(conn, tid, "created", f"Tạo việc: {title[:200]}", agent=assigned_agent, data={"by": created_by, "parent": parent_id})
    await audit.record(conn, created_by, "task.created", f"task:{tid}", {"title": title[:200], "agent": assigned_agent})
    await transition(conn, tid, "PENDING", actor=created_by)
    await promote(conn, tid)
    return await get(conn, tid)


# ------------------------------------------------------------------ hàng đợi
async def deps_done(conn: AsyncConnection, task_id: str) -> bool:
    """Mọi phụ thuộc đã kết thúc (xong, hủy, hoặc lỗi hết lượt thử). Phụ thuộc chưa tồn tại = chưa xong."""
    n = await db.scalar(
        conn,
        "SELECT count(*) FROM task_dependencies d LEFT JOIN tasks t ON t.id = d.depends_on WHERE d.task_id = CAST(:t AS uuid) "
        "AND (t.id IS NULL OR NOT (t.status IN ('COMPLETED','CANCELLED') OR (t.status = 'FAILED' AND t.attempt >= t.max_attempts)))",
        {"t": task_id},
    )
    return int(n or 0) == 0


async def promote(conn: AsyncConnection, task_id: str | None = None) -> list[str]:
    """PENDING → ASSIGNED cho task đủ điều kiện (có agent, phụ thuộc xong, đã tới giờ thử lại)."""
    rows = await db.all_(
        conn,
        "SELECT id FROM tasks WHERE status = 'PENDING' AND assigned_agent IS NOT NULL AND (not_before IS NULL OR not_before <= now()) "
        "AND (CAST(:t AS uuid) IS NULL OR id = CAST(:t AS uuid)) ORDER BY priority, created_at LIMIT 200",
        {"t": task_id},
    )
    out = []
    for r in rows:
        tid = str(r["id"])
        if await deps_done(conn, tid):
            await transition(conn, tid, "ASSIGNED", actor="system:engine", expect={"PENDING"}, fields={"not_before": None})
            out.append(tid)
    return out


async def claim(conn: AsyncConnection, worker: str, limit: int = 1, lease_s: int = LEASE_S) -> list[dict[str, Any]]:
    """Nhận việc: ASSIGNED, hoặc IN_PROGRESS không còn lease (worker cũ chết / vừa được duyệt). Mỗi agent một việc một lúc."""
    rows = await db.all_(
        conn,
        "SELECT t.id FROM tasks t JOIN agents a ON a.agent_key = t.assigned_agent JOIN agent_status s ON s.agent_id = a.id "
        "WHERE (t.status = 'ASSIGNED' OR (t.status = 'IN_PROGRESS' AND (t.lease_until IS NULL OR t.lease_until < now()))) "
        "AND s.state NOT IN ('paused','disabled') "
        "AND NOT EXISTS (SELECT 1 FROM tasks o WHERE o.assigned_agent = t.assigned_agent AND o.id <> t.id AND o.status = 'IN_PROGRESS' "
        "AND o.lease_until > now()) "
        "ORDER BY t.priority, t.created_at LIMIT :n FOR UPDATE OF t SKIP LOCKED",
        {"n": limit * 3},
    )
    out: list[dict[str, Any]] = []
    agents: set[str] = set()
    for r in rows:
        t = await get(conn, str(r["id"]))
        if t["assigned_agent"] in agents or len(out) >= limit:
            continue
        stolen = t["status"] == "IN_PROGRESS" and t["lease_owner"] is not None
        now = datetime.now(UTC)
        f: dict[str, Any] = {"lease_owner": worker, "lease_until": now + timedelta(seconds=lease_s)}
        if t["started_at"] is None:
            f["started_at"] = now
        if t["timeout_at"] is None:
            f["timeout_at"] = now + timedelta(seconds=int(t["timeout_s"]))
        t = await transition(conn, str(t["id"]), "IN_PROGRESS", actor=f"worker:{worker}", fields=f)
        if stolen:
            await log_event(conn, str(t["id"]), "lease", "Worker trước không còn phản hồi: nhận lại việc, chạy tiếp từ checkpoint.")
        agents.add(t["assigned_agent"])
        out.append(t)
    return out


async def heartbeat(conn: AsyncConnection, task_id: str, worker: str, lease_s: int = LEASE_S) -> bool:
    n = await db.execute(
        conn,
        "UPDATE tasks SET lease_until = now() + make_interval(secs => :s) WHERE id = CAST(:t AS uuid) AND lease_owner = :w AND status = 'IN_PROGRESS'",
        {"s": lease_s, "t": task_id, "w": worker},
    )
    return n == 1


async def owns(conn: AsyncConnection, task_id: str, worker: str) -> bool:
    return bool(
        await db.scalar(
            conn, "SELECT lease_owner = :w AND status = 'IN_PROGRESS' FROM tasks WHERE id = CAST(:t AS uuid)", {"t": task_id, "w": worker}
        )
    )


# ------------------------------------------------------------------ dừng chờ, lỗi, thử lại, hủy
async def park(conn: AsyncConnection, task_id: str, kind: str, *, actor: str, reason: str = "") -> dict[str, Any]:
    """Đồ thị dừng chờ (interrupt): nhả worker, giữ checkpoint."""
    to = {"approval": "WAITING_APPROVAL", "review": "WAITING_REVIEW", "children": "PENDING"}[kind]
    t = await transition(conn, task_id, to, actor=actor, reason=reason, fields={"wait_kind": kind})
    if kind == "children":
        await promote(conn, task_id)
    return t


async def wake(conn: AsyncConnection, task_id: str, *, actor: str, reason: str) -> None:
    """Điều kiện chờ đã có kết quả (duyệt, review): cho worker kế tiếp nhận lại."""
    t = await get(conn, task_id, lock=True)
    if t["status"] in ("WAITING_APPROVAL", "WAITING_REVIEW"):
        await transition(conn, task_id, "IN_PROGRESS", actor=actor, reason=reason)
        await kick()


async def fail(conn: AsyncConnection, task_id: str, code: str, message: str, *, actor: str) -> dict[str, Any]:
    """Lỗi: thử lại có giãn cách nếu còn lượt và lỗi tạm thời; hết lượt thì báo cấp trên."""
    t = await transition(conn, task_id, "FAILED", actor=actor, reason=message[:300], fields={"error_code": code, "error": message[:2000]})
    if code in RETRYABLE and t["attempt"] < t["max_attempts"]:
        delay = RETRY_BASE_S * 2 ** (int(t["attempt"]) - 1)
        t = await transition(
            conn,
            task_id,
            "PENDING",
            actor="system:engine",
            reason=f"thử lại lần {t['attempt'] + 1} sau {delay} giây",
            fields={"attempt": int(t["attempt"]) + 1, "not_before": datetime.now(UTC) + timedelta(seconds=delay), "finished_at": None},
        )
    else:
        from app.tasks import bus

        boss = await _manager(conn, t)
        await bus.send(
            conn,
            "error_report",
            sender=f"agent:{t['assigned_agent']}",
            receiver=boss,
            task_id=task_id,
            payload={"title": t["title"], "code": code, "error": message[:500]},
            key=f"error:{task_id}:{t['attempt']}",
        )
        await _parent_maybe_ready(conn, t)
    return t


async def complete(conn: AsyncConnection, task_id: str, output: dict[str, Any], summary: str, *, actor: str) -> dict[str, Any]:
    t = await transition(conn, task_id, "COMPLETED", actor=actor, fields={"output_data": output, "result_summary": summary[:1000]})
    await audit.record(conn, actor, "task.completed", f"task:{task_id}", {"title": t["title"][:200]})
    await _parent_maybe_ready(conn, t)
    return t


async def cancel(conn: AsyncConnection, task_id: str, *, actor: str, reason: str) -> list[str]:
    """Hủy task và mọi task con chưa đóng; yêu cầu duyệt đang chờ của chúng cũng bị hủy."""
    ids = [
        str(r["id"])
        for r in await db.all_(
            conn,
            "WITH RECURSIVE sub(id) AS (SELECT CAST(:t AS uuid) UNION SELECT c.id FROM tasks c JOIN sub ON c.parent_id = sub.id) "
            "SELECT t.id FROM tasks t JOIN sub ON sub.id = t.id WHERE t.status NOT IN ('COMPLETED','CANCELLED') ORDER BY t.depth DESC",
            {"t": task_id},
        )
    ]
    for i in ids:
        await transition(conn, i, "CANCELLED", actor=actor, reason=reason if i == task_id else "task cha bị hủy")
        await db.execute(
            conn,
            "UPDATE approvals SET status = 'cancelled', decided_at = now(), decided_by = :a WHERE status = 'pending' AND ("
            "(subject_type = 'task_output' AND subject_id = :t) OR (subject_type = 'tool_call' AND subject_id IN "
            "(SELECT idempotency_key FROM tool_invocations WHERE task_id = :t)))",
            {"a": actor, "t": i},
        )
    if ids:
        await audit.record(conn, actor, "task.cancelled", f"task:{task_id}", {"count": len(ids)}, reason=reason)
        t = await get(conn, task_id)
        await _parent_maybe_ready(conn, t)
    return ids


async def retry(conn: AsyncConnection, task_id: str, *, actor: str) -> dict[str, Any]:
    """Owner cho chạy lại task lỗi (thêm một lượt thử)."""
    t = await get(conn, task_id, lock=True)
    if t["status"] != "FAILED":
        raise AppError("TASK_NOT_FAILED", "Chỉ chạy lại được task đang lỗi.", 409)
    t = await transition(
        conn,
        task_id,
        "PENDING",
        actor=actor,
        reason="Owner cho chạy lại",
        fields={"attempt": int(t["attempt"]) + 1, "max_attempts": max(int(t["max_attempts"]), int(t["attempt"]) + 1), "finished_at": None},
    )
    await promote(conn, task_id)
    await kick()
    return t


async def _manager(conn: AsyncConnection, t: dict[str, Any]) -> str:
    if t["parent_id"]:
        p = await get(conn, str(t["parent_id"]))
        return f"agent:{p['assigned_agent']}"
    boss = await db.scalar(conn, "SELECT reports_to FROM agents WHERE agent_key = :a", {"a": t["assigned_agent"]})
    return f"agent:{boss}" if boss else "owner"


async def _parent_maybe_ready(conn: AsyncConnection, t: dict[str, Any]) -> None:
    """Task con kết thúc: task cha (hoặc task phụ thuộc) có thể chạy tiếp."""
    waiting = await db.all_(
        conn,
        "SELECT task_id FROM task_dependencies d JOIN tasks w ON w.id = d.task_id WHERE d.depends_on = :t AND w.status = 'PENDING'",
        {"t": t["id"]},
    )
    if waiting:
        for w in waiting:
            await promote(conn, str(w["task_id"]))
        await kick()


# ------------------------------------------------------------------ đánh thức worker
_kick_redis: Any = None


async def kick() -> None:
    """Đánh thức worker (Redis). Mất Redis cũng không sao: worker vẫn quét bảng mỗi vài giây."""
    global _kick_redis  # noqa: PLW0603
    try:
        from redis.asyncio import Redis

        from app.core.config import get_settings

        if _kick_redis is None:
            _kick_redis = Redis.from_url(get_settings().redis_url)
        await _kick_redis.lpush("aico:tasks:wake", "1")
        await _kick_redis.ltrim("aico:tasks:wake", 0, 50)
    except Exception as e:  # noqa: BLE001
        log.debug("Không đánh thức được worker qua Redis: %s", type(e).__name__)
        _kick_redis = None


def reset_kick() -> None:
    global _kick_redis  # noqa: PLW0603
    _kick_redis = None
