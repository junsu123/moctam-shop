"""Lịch tự động (SRS §14): cron 5 trường lưu trong CSDL, theo múi giờ của lịch; chạy bù khi máy bật lại.

- Lần chạy bị lỡ trong vòng `catch_up_hours` (mặc định 24 giờ): chạy bù MỘT lần (không dồn nhiều lần), rồi tính lần kế tiếp từ hiện tại.
- Lỡ quá hạn chạy bù: bỏ qua và ghi lại.
- Khóa chống trùng `schedule:<id>:<giờ dự kiến>`: hai worker cùng quét không tạo hai task.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.core.errors import AppError
from app.tasks import engine

log = logging.getLogger("aico.scheduler")
_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _field(spec: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
            if step < 1:
                raise ValueError("bước phải ≥ 1")
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            x, y = part.split("-", 1)
            a, b = int(x), int(y)
        else:
            a = b = int(part)
            if step > 1:
                b = hi
        if a < lo or b > hi or a > b:
            raise ValueError(f"giá trị {part} ngoài khoảng {lo}–{hi}")
        out.update(range(a, b + 1, step))
    return out


def parse(cron: str) -> tuple[set[int], ...]:
    """Cron 5 trường: phút giờ ngày tháng thứ (0 = Chủ nhật, 7 cũng là Chủ nhật)."""
    parts = cron.split()
    if len(parts) != 5:
        raise AppError("CRON_INVALID", "Lịch cron cần đúng 5 trường: phút giờ ngày tháng thứ.", 422)
    try:
        f = [_field(p, *_RANGES[i]) for i, p in enumerate(parts)]
        f[4] = {0 if d == 7 else d for d in f[4]}
    except ValueError as e:
        raise AppError("CRON_INVALID", f"Lịch cron không hợp lệ: {e}.", 422) from e
    f.append({0} if parts[2] == "*" else {1})  # cờ: ngày-trong-tháng có bị giới hạn không
    f.append({0} if parts[4] == "*" else {1})
    return tuple(f)


def next_after(cron: str, after: datetime, tz: str = "Asia/Ho_Chi_Minh") -> datetime:
    """Lần chạy kế tiếp sau `after` (UTC) theo múi giờ `tz`."""
    mins, hours, doms, months, dows, dom_r, dow_r = parse(cron)
    z = ZoneInfo(tz)
    t = after.astimezone(z).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        dow = (t.weekday() + 1) % 7
        day_ok = (t.day in doms or dow in dows) if (1 in dom_r and 1 in dow_r) else (t.day in doms and dow in dows)
        if t.month in months and day_ok and t.hour in hours and t.minute in mins:
            return t.astimezone(UTC)
        if t.month not in months or not day_ok:
            t = (t + timedelta(days=1)).replace(hour=0, minute=0)
        elif t.hour not in hours:
            t = (t + timedelta(hours=1)).replace(minute=0)
        else:
            t += timedelta(minutes=1)
    raise AppError("CRON_INVALID", "Lịch cron không bao giờ chạy.", 422)


async def tick(conn: AsyncConnection, now: datetime | None = None) -> list[str]:
    """Tạo task cho các lịch đã tới giờ. Trả danh sách task đã tạo."""
    now = now or datetime.now(UTC)
    rows = await db.all_(
        conn,
        "SELECT * FROM schedules WHERE enabled AND (next_run_at IS NULL OR next_run_at <= :n) ORDER BY next_run_at NULLS FIRST FOR UPDATE SKIP LOCKED",
        {"n": now},
    )
    created: list[str] = []
    for s in rows:
        due = s["next_run_at"]
        nxt = next_after(s["cron"], now, s["timezone"])
        if due is None:  # lịch mới: chỉ tính lần chạy đầu
            await db.execute(conn, "UPDATE schedules SET next_run_at = :x WHERE id = :i", {"x": nxt, "i": s["id"]})
            continue
        late = now - due
        if late <= timedelta(hours=int(s["catch_up_hours"])):
            tpl: dict[str, Any] = dict(s["task_template"])
            try:
                t = await engine.create(
                    conn,
                    idempotency_key=f"schedule:{s['id']}:{due.isoformat()}",
                    title=tpl.get("title", s["name"]),
                    description=tpl.get("description", ""),
                    task_type=tpl.get("task_type", "generic"),
                    created_by="system:scheduler",
                    assigned_agent=s["agent_key"],
                    priority=int(tpl.get("priority", 2)),
                    input_data={**tpl.get("input", {}), "scheduled_for": due.isoformat(), "late_minutes": int(late.total_seconds() // 60)},
                    success_criteria=tpl.get("success_criteria", []),
                    requires_approval=bool(tpl.get("requires_approval", False)),
                    autonomy_max=int(tpl.get("autonomy_max", 2)),
                    budget_usd=float(tpl.get("budget_usd", 0.2)),
                )
                created.append(str(t["id"]))
                if late > timedelta(minutes=5):
                    await engine.log_event(
                        conn, str(t["id"]), "catch_up", f"Chạy bù lịch '{s['name']}' (lỡ {int(late.total_seconds() // 60)} phút do máy tắt)"
                    )
            except AppError as e:
                log.warning("Lịch %s không tạo được task: %s", s["name"], e.code)
        else:
            log.info("Lịch %s lỡ quá %s giờ, bỏ qua lần %s", s["name"], s["catch_up_hours"], due)
        await db.execute(conn, "UPDATE schedules SET last_run_at = :d, next_run_at = :x WHERE id = :i", {"d": due, "x": nxt, "i": s["id"]})
    return created
