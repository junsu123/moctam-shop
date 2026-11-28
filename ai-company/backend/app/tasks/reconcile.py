"""Job đối soát (ARCHITECTURE ADR-05, IT-LG-03), chạy mỗi 5 phút trong worker.

- Task IN_PROGRESS mà lease đã hết (worker chết): báo lại và đánh thức worker; worker kế tiếp nhận và chạy tiếp từ checkpoint.
- Task quá `timeout_at` mà không còn worker giữ: chuyển lỗi TIMEOUT (thử lại nếu còn lượt).
- Yêu cầu duyệt hết hạn: hủy (im lặng không phải đồng ý), task đang chờ được đánh thức để kết thúc.
- Checkpoint mồ côi (không có task tương ứng): báo; checkpoint của task đã đóng quá 30 ngày: dọn.
- Task quá hạn chót mà chưa xong: báo một lần.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core import db
from app.domain import approvals, notify
from app.tasks import engine

log = logging.getLogger("aico.reconcile")
EVERY_S = 300
KEEP_DAYS = 30


@dataclass
class Report:
    requeued: list[str] = field(default_factory=list)
    timed_out: list[str] = field(default_factory=list)
    approvals_expired: int = 0
    orphan_checkpoints: list[str] = field(default_factory=list)
    pruned_checkpoints: int = 0
    overdue: list[str] = field(default_factory=list)


async def run() -> Report:
    rep = Report()
    async with db.engine().begin() as c:
        rep.approvals_expired = await approvals.expire_due(c)
        for r in await db.all_(
            c,
            "SELECT id, title FROM tasks WHERE status = 'IN_PROGRESS' AND lease_owner IS NOT NULL AND lease_until < now() FOR UPDATE SKIP LOCKED",
        ):
            await db.execute(c, "UPDATE tasks SET lease_owner = NULL, lease_until = NULL WHERE id = :i", {"i": r["id"]})
            await engine.log_event(
                c, str(r["id"]), "reconcile", "Không còn worker giữ việc này: đưa lại vào hàng đợi, chạy tiếp từ checkpoint"
            )
            rep.requeued.append(str(r["id"]))
        for r in await db.all_(
            c,
            "SELECT id FROM tasks WHERE status = 'IN_PROGRESS' AND timeout_at < now() AND (lease_until IS NULL OR lease_until < now()) "
            "FOR UPDATE SKIP LOCKED",
        ):
            await engine.fail(c, str(r["id"]), "TIMEOUT", "Quá thời gian cho phép", actor="system:reconcile")
            rep.timed_out.append(str(r["id"]))
        await engine.promote(c)
        for r in await db.all_(
            c,
            "SELECT id, title FROM tasks WHERE deadline < now() AND status NOT IN ('COMPLETED','CANCELLED') "
            "AND NOT EXISTS (SELECT 1 FROM task_logs l WHERE l.task_id = tasks.id AND l.event = 'overdue')",
        ):
            await engine.log_event(c, str(r["id"]), "overdue", "Đã quá hạn chót mà chưa xong")
            await notify.enqueue(c, "alert", f"⏰ Việc quá hạn chót: {r['title'][:150]}", dedupe_key=f"overdue:{r['id']}")
            rep.overdue.append(str(r["id"]))
        if await db.scalar(c, "SELECT to_regclass('langgraph.checkpoints') IS NOT NULL"):
            rep.orphan_checkpoints = [
                str(r["thread_id"])
                for r in await db.all_(
                    c,
                    "SELECT DISTINCT cp.thread_id FROM langgraph.checkpoints cp LEFT JOIN tasks t ON t.id::text = cp.thread_id "
                    "WHERE t.id IS NULL LIMIT 100",
                )
            ]
            if rep.orphan_checkpoints:
                log.warning("Có %d checkpoint mồ côi (không có task)", len(rep.orphan_checkpoints))
                await notify.enqueue(
                    c,
                    "alert",
                    f"⚠️ Đối soát: {len(rep.orphan_checkpoints)} checkpoint LangGraph không có task tương ứng.",
                    dedupe_key=f"orphans:{len(rep.orphan_checkpoints)}:{rep.orphan_checkpoints[0]}",
                )
            old = [
                str(r["id"])
                for r in await db.all_(
                    c,
                    "SELECT id FROM tasks WHERE status IN ('COMPLETED','CANCELLED') AND finished_at < now() - make_interval(days => :d)",
                    {"d": KEEP_DAYS},
                )
            ]
            for tbl in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                rep.pruned_checkpoints += await db.execute(
                    c,
                    f"DELETE FROM langgraph.{tbl} WHERE thread_id = ANY(:ids)",  # noqa: S608 — tên bảng cố định
                    {"ids": old},
                )
    if rep.requeued:
        await engine.kick()
    return rep
