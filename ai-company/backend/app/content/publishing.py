"""Hàng chờ và lịch đăng bài (ARCHITECTURE ADR-16 lớp 4, IT-PUB-*).

- Bài đã qua Content Gate + review (+ Owner duyệt nếu cần) vào `publish_queue` với một **khung giờ** (`slot_at`) theo giai đoạn:
  giờ vàng, số bài mỗi ngày/tuần, chỉ trong 07:00–21:30, hai bài cách nhau ≥ 3 giờ. Lịch là cài đặt, không hardcode.
- Đến giờ (`release_due`, worker gọi mỗi phút): **chạy lại Content Gate với giá mới nhất của website**, đổi giá thì chặn;
  đạt thì gọi website `publish` (website đếm hạn mức lần cuối), báo Telegram kèm link + nút Gỡ bài / Góp ý.
- Máy tắt lỡ giờ: không đăng muộn ngoài khung; xếp lại vào khung kế tiếp.
- Gỡ bài (`unpublish`): website gỡ ngay, bài vào trí nhớ của agent viết như một bài học (kênh học `retracted`).
- Lên/lùi giai đoạn (`evaluate_phase`): đủ thời gian và tỉ lệ gỡ < 10% thì lên; Owner gỡ ≥ 2 bài trong 7 ngày thì lùi một bậc.
- Tạm dừng (`/tamdung xuatban`) và ngày nghỉ: giữ nguyên hàng chờ, không đăng.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db
from app.core.errors import AppError
from app.core.ids import uuid7
from app.domain import notify, store
from app.domain.approvals import _json, digest

log = logging.getLogger("aico.publishing")
VN = ZoneInfo("Asia/Ho_Chi_Minh")
Kind = Literal["faq", "blog"]
LATE_OK = timedelta(minutes=30)  # máy bận/khởi động chậm: vẫn đăng nếu trễ ≤ 30 phút so với khung giờ


class KindPlan(BaseModel):
    times: list[str] = Field(min_length=1, max_length=6)
    weekdays: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])  # ISO: 1 = Thứ Hai … 7 = Chủ nhật
    per_day: int = Field(ge=0, le=10)
    per_week: int | None = Field(default=None, ge=0, le=50)

    @field_validator("times")
    @classmethod
    def _hhmm(cls, v: list[str]) -> list[str]:
        return sorted(store._hhmm(x) for x in v)


class Phase(BaseModel):
    blog: KindPlan
    faq: KindPlan


def _phases() -> dict[str, Phase]:
    return {
        "1": Phase(blog=KindPlan(times=["19:30"], weekdays=[2, 6], per_day=1, per_week=2), faq=KindPlan(times=["11:30"], per_day=1)),
        "2": Phase(
            blog=KindPlan(times=["19:30"], weekdays=[2, 4, 6], per_day=1, per_week=3), faq=KindPlan(times=["07:30", "11:30"], per_day=2)
        ),
        "3": Phase(blog=KindPlan(times=["19:30"], per_day=1), faq=KindPlan(times=["07:30", "11:30", "17:30"], per_day=3)),
    }


class PublishSettings(BaseModel):
    """Lịch đăng bài (Cài đặt → Lịch đăng bài). Mặc định theo bảng 3 giai đoạn của ADR-16."""

    phase: int = Field(default=1, ge=1, le=3)
    phase_since: datetime | None = None
    auto_progress: bool = True
    paused: bool = False
    paused_reason: str = ""
    holidays: list[date] = Field(default_factory=list, max_length=60)
    window_start: str = "07:00"
    window_end: str = "21:30"
    min_gap_hours: float = Field(default=3, ge=0, le=12)
    phases: dict[str, Phase] = Field(default_factory=_phases)

    @field_validator("window_start", "window_end")
    @classmethod
    def _w(cls, v: str) -> str:
        return store._hhmm(v)


store.register("publishing", PublishSettings)
PROGRESS = {1: 14, 2: 28}  # số ngày tối thiểu ở giai đoạn trước khi lên (giai đoạn 1: 2 tuần; giai đoạn 2: tuần 3–6)
MAX_RETRACT_RATE = 0.10
STEP_DOWN = 2  # Owner gỡ ≥ 2 bài trong 7 ngày thì lùi một giai đoạn


async def settings(conn: AsyncConnection) -> PublishSettings:
    s = await store.get_setting(conn, "publishing")
    assert isinstance(s, PublishSettings)
    return s


def _t(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


# ------------------------------------------------------------------ xếp khung giờ
def next_slot(s: PublishSettings, kind: Kind, after: datetime, busy: list[tuple[str, datetime]]) -> datetime | None:
    """Khung giờ sớm nhất > `after` thỏa: giờ vàng của giai đoạn, ngày trong tuần, số bài/ngày/tuần, khung 07:00–21:30,
    cách mọi bài khác ≥ `min_gap_hours`, không rơi vào ngày nghỉ. `busy` = (loại, giờ) của bài đã xếp/đã đăng."""
    plan: KindPlan = getattr(s.phases[str(s.phase)], kind)
    gap = timedelta(hours=s.min_gap_hours)
    ws, we = _t(s.window_start), _t(s.window_end)
    start = after.astimezone(VN)
    for d in range(0, 62):
        day = (start + timedelta(days=d)).date()
        if day in s.holidays or day.isoweekday() not in plan.weekdays:
            continue
        same_day = [t for k, t in busy if k == kind and t.astimezone(VN).date() == day]
        if len(same_day) >= plan.per_day:
            continue
        if plan.per_week is not None:
            wk = day.isocalendar()[:2]
            if len([1 for k, t in busy if k == kind and t.astimezone(VN).date().isocalendar()[:2] == wk]) >= plan.per_week:
                continue
        for hhmm in plan.times:
            tm = _t(hhmm)
            if tm < ws or tm > we:
                continue
            cand = datetime.combine(day, tm, VN)
            if cand <= after:
                continue
            if any(abs((cand - t).total_seconds()) < gap.total_seconds() for _, t in busy):
                continue
            return cand.astimezone(UTC)
    return None


async def _busy(conn: AsyncConnection, exclude: str | None = None) -> list[tuple[str, datetime]]:
    rows = await db.all_(
        conn,
        "SELECT kind, coalesce(published_at, slot_at) AS t FROM publish_queue WHERE (status IN ('scheduled','publishing') "
        "OR (status IN ('published','retracted') AND published_at > now() - interval '14 days')) "
        "AND coalesce(published_at, slot_at) IS NOT NULL AND id IS DISTINCT FROM CAST(:x AS uuid)",
        {"x": exclude},
    )
    return [(r["kind"], r["t"]) for r in rows]


async def enqueue(
    conn: AsyncConnection,
    *,
    key: str,
    agent_key: str,
    task_id: str | None,
    kind: Kind,
    data: dict[str, Any],
    gate: dict[str, Any],
    status: Literal["scheduled", "blocked"],
    approval_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Thêm bài vào hàng chờ (khóa chống trùng = khóa lời gọi công cụ). Bài hợp lệ được xếp khung giờ ngay."""
    old = await db.one(conn, "SELECT * FROM publish_queue WHERE invocation_key = :k", {"k": key})
    if old:
        return dict(old)
    s = await settings(conn)
    slot = None
    if status == "scheduled":
        await db.execute(conn, "SELECT pg_advisory_xact_lock(hashtext('publish_queue_slots'))")  # hai bài không tranh cùng khung
        slot = next_slot(s, kind, now or datetime.now(UTC), await _busy(conn))
        if slot is None:
            raise AppError("NO_PUBLISH_SLOT", "Không còn khung giờ đăng nào trong 2 tháng tới (xem Cài đặt → Lịch đăng bài).", 409)
    row = await db.one(
        conn,
        "INSERT INTO publish_queue(id, task_id, agent_key, kind, title, body, meta_description, keywords, product_id, category_id, "
        "source_refs, status, slot_at, gate, approval_id, invocation_key) VALUES (:id, CAST(:t AS uuid), :a, :k, :ti, :b, :m, :kw, :p, :c, "
        "CAST(:sr AS jsonb), :st, :slot, CAST(:g AS jsonb), CAST(:ap AS uuid), :key) RETURNING *",
        {
            "id": uuid7(),
            "t": task_id,
            "a": agent_key,
            "k": kind,
            "ti": data["title"],
            "b": data["body"],
            "m": data.get("meta_description"),
            "kw": data.get("keywords"),
            "p": data.get("product_id"),
            "c": data.get("category_id"),
            "sr": _json(data.get("source_refs") or []),
            "st": status,
            "slot": slot,
            "g": _json(gate),
            "ap": approval_id,
            "key": key,
        },
    )
    assert row is not None
    await audit.record(
        conn,
        f"agent:{agent_key}",
        f"publish.{status}",
        f"publish:{row['id']}",
        {"title": data["title"][:200], "slot": slot.isoformat() if slot else None},
    )
    return dict(row)


def _local(t: datetime) -> str:
    return t.astimezone(VN).strftime("%H:%M %d/%m")


# ------------------------------------------------------------------ đến giờ đăng
async def release_due(now: datetime | None = None) -> dict[str, int]:
    """Đăng các bài tới giờ. Mỗi bài một giao dịch; lỗi một bài không chặn bài khác."""
    from app.content import gate as cg
    from app.integrations import website

    now = now or datetime.now(UTC)
    out = {"published": 0, "blocked": 0, "rescheduled": 0, "failed": 0}
    async with db.engine().connect() as c:
        s = await settings(c)
    if s.paused or now.astimezone(VN).date() in s.holidays:
        return out
    for _ in range(5):
        async with db.engine().begin() as c:
            row = await db.one(
                c,
                "SELECT * FROM publish_queue WHERE status = 'scheduled' AND slot_at <= :n ORDER BY slot_at LIMIT 1 FOR UPDATE SKIP LOCKED",
                {"n": now},
            )
            if row is None:
                break
            it: dict[str, Any] = dict(row)
            local = now.astimezone(VN).time()
            late = now - it["slot_at"] > LATE_OK
            if late or local < _t(s.window_start) or local > _t(s.window_end):
                slot = next_slot(s, it["kind"], now, await _busy(c, str(it["id"])))
                await _set(c, it["id"], slot_at=slot, last_error="lỡ khung giờ (máy tắt hoặc bận): xếp lại")
                out["rescheduled"] += 1
                continue
            g = await cg.evaluate(
                c,
                kind=it["kind"],
                title=it["title"],
                body=it["body"],
                meta=it["meta_description"] or "",
                product_ids=[it["product_id"]] if it["product_id"] else None,
                fresh_catalog=True,
                use_classifier=False,
            )
            if not g.ok:
                await _block(c, it, g.blocked, "Kiểm lại ngay trước giờ đăng")
                out["blocked"] += 1
                continue
            await _set(c, it["id"], status="publishing", attempts=int(it["attempts"]) + 1)
        # gọi website NGOÀI giao dịch giữ khóa dòng lâu; khóa chống trùng ở website là client_ref
        payload = {
            "client_ref": f"co:{it['id']}",
            "kind": it["kind"],
            "data": {
                "title": it["title"],
                "body": it["body"],
                "meta_description": it["meta_description"],
                "keywords": it["keywords"],
                "product_id": it["product_id"],
                "category_id": it["category_id"],
                "source_refs": it["source_refs"],
                "generated_by": f"co:{it['agent_key']}",
            },
        }
        try:
            async with db.engine().connect() as c:
                res = await website.publish(c, payload)
        except AppError as e:
            async with db.engine().begin() as c:
                if e.code in ("AI_PUBLISH_QUOTA", "AI_PUBLISH_HOURS"):
                    slot = next_slot(s, it["kind"], now + timedelta(hours=1), await _busy(c, str(it["id"])))
                    await _set(c, it["id"], status="scheduled", slot_at=slot, last_error=f"website từ chối: {e.message}")
                    out["rescheduled"] += 1
                elif e.code in ("SOURCE_OUTDATED", "VALIDATION_ERROR", "FORBIDDEN"):
                    await _block(c, it, [f"website từ chối: {e.message}"], "Website kiểm tra lần cuối")
                    out["blocked"] += 1
                elif int(it["attempts"]) + 1 >= 5:
                    await _set(c, it["id"], status="failed", last_error=e.message)
                    await notify.enqueue(
                        c, "alert", f'⚠️ Không đăng được bài "{it["title"][:120]}": {e.message}', dedupe_key=f"pubfail:{it['id']}"
                    )
                    out["failed"] += 1
                else:
                    await _set(c, it["id"], status="scheduled", slot_at=now + timedelta(minutes=5), last_error=e.message)
                    out["rescheduled"] += 1
            continue
        async with db.engine().begin() as c:
            await _set(
                c, it["id"], status="published", content_id=int(res["content_id"]), url=res.get("url"), published_at=now, last_error=None
            )
            await audit.record(
                c, f"agent:{it['agent_key']}", "content.published", f"publish:{it['id']}", {"url": res.get("url"), "kind": it["kind"]}
            )
            dg = digest({"id": str(it["id"]), "content_id": int(res["content_id"])})
            await notify.enqueue(
                c,
                "publish",
                f"📰 Đã đăng {'FAQ' if it['kind'] == 'faq' else 'bài blog'}: {it['title'][:200]}\n{res.get('url') or ''}\n"
                "Bấm Gỡ bài nếu có gì sai; Góp ý để agent nhớ cho lần sau.",
                dedupe_key=f"published:{it['id']}",
                buttons=[
                    {"action": "unpublish", "text": "Gỡ bài", "subject_type": "publish", "subject_id": str(it["id"]), "digest": dg},
                    {"action": "feedback", "text": "Góp ý", "subject_type": "publish", "subject_id": str(it["id"]), "digest": dg},
                ],
            )
        out["published"] += 1
    return out


async def _set(c: AsyncConnection, item_id: Any, **f: Any) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in f)
    await db.execute(c, f"UPDATE publish_queue SET {sets}, updated_at = now() WHERE id = :id", {**f, "id": item_id})  # noqa: S608 — cột từ mã


async def _block(c: AsyncConnection, it: dict[str, Any], reasons: list[str], where: str) -> None:
    """Bị chặn: không đăng; gửi thành bản nháp chờ duyệt trên website (nếu được), báo Owner lý do."""
    from app.integrations import website

    draft_note = ""
    try:
        r = await website.draft(
            c,
            [
                {
                    "client_ref": f"co:draft:{it['id']}",
                    "kind": it["kind"],
                    "data": {
                        "title": it["title"],
                        "body": it["body"],
                        "meta_description": it["meta_description"],
                        "keywords": it["keywords"],
                        "product_id": it["product_id"],
                        "source_refs": it["source_refs"],
                        "generated_by": f"co:{it['agent_key']}",
                    },
                }
            ],
        )
        st = (r.get("results") or [{}])[0].get("status")
        draft_note = " Đã gửi thành bản nháp chờ duyệt trên website." if st == "accepted" else ""
    except AppError as e:
        draft_note = f" Chưa gửi được bản nháp ({e.code})."
    gate = dict(it.get("gate") or {})
    gate["blocked"] = reasons
    await db.execute(
        c,
        "UPDATE publish_queue SET status = 'blocked', last_error = :e, gate = CAST(:g AS jsonb), updated_at = now() WHERE id = :i",
        {"e": "; ".join(reasons)[:1000], "g": _json(gate), "i": it["id"]},
    )
    await notify.enqueue(
        c,
        "alert",
        f'⛔ Không tự đăng "{it["title"][:150]}" ({where}): ' + "; ".join(reasons)[:600] + draft_note,
        dedupe_key=f"blocked:{it['id']}",
    )
    await audit.record(c, "system:publisher", "publish.blocked", f"publish:{it['id']}", {"reasons": reasons[:5]})


# ------------------------------------------------------------------ gỡ bài, góp ý
async def unpublish(conn: AsyncConnection, item_id: str, *, actor: str, reason: str) -> dict[str, Any]:
    """Gỡ bài AI đã đăng. Bài gỡ thành bài học trong trí nhớ riêng của agent viết; Owner gỡ nhiều thì lùi giai đoạn."""
    from app.integrations import website
    from app.memory import store as mem

    it = await db.one(conn, "SELECT * FROM publish_queue WHERE id = CAST(:i AS uuid) FOR UPDATE", {"i": item_id})
    if it is None:
        raise AppError("PUBLISH_NOT_FOUND", "Không có bài này trong hàng chờ xuất bản.", 404)
    if it["status"] == "retracted":
        return dict(it)
    if it["status"] in ("scheduled", "blocked"):  # chưa lên website: chỉ hủy
        await _set(conn, it["id"], status="cancelled", retracted_by=actor, retract_reason=reason)
        await audit.record(conn, actor, "publish.cancelled", f"publish:{item_id}", {"reason": reason[:300]})
        return dict(await db.one(conn, "SELECT * FROM publish_queue WHERE id = :i", {"i": it["id"]}) or {})
    if it["status"] != "published" or not it["content_id"]:
        raise AppError("PUBLISH_NOT_LIVE", "Bài này chưa ở trên website.", 409)
    await website.unpublish(conn, int(it["content_id"]), reason[:500])
    await _set(conn, it["id"], status="retracted", retracted_at=datetime.now(UTC), retracted_by=actor, retract_reason=reason[:500])
    await audit.record(conn, actor, "content.unpublished", f"publish:{item_id}", {"reason": reason[:300], "url": it["url"]})
    await mem.remember_episode(
        conn,
        it["agent_key"],
        title=f'Bài học: bài bị gỡ "{it["title"][:150]}"',
        content=f'{"FAQ" if it["kind"] == "faq" else "Bài blog"} "{it["title"]}" đã đăng rồi bị gỡ. Lý do của Owner: {reason}',
        task_id=str(it["task_id"]) if it["task_id"] else None,
        task_type="publish",
        outcome="failure",
        metadata={"guidance": True, "retracted": True, "publish_id": str(it["id"])},
        source_ref=it["url"],
        confidence=0.9,
    )
    await notify.enqueue(conn, "publish", f"🗑️ Đã gỡ: {it['title'][:200]}. Lý do: {reason[:300]}", dedupe_key=f"retracted:{it['id']}")
    if actor.startswith(("user:", "telegram:")):
        await step_down_if_needed(conn)
    return dict(await db.one(conn, "SELECT * FROM publish_queue WHERE id = :i", {"i": it["id"]}) or {})


async def feedback(conn: AsyncConnection, item_id: str, *, actor: str, text: str) -> None:
    """Góp ý của Owner cho một bài (Telegram/dashboard): thành hướng dẫn trong trí nhớ riêng của agent viết."""
    from app.memory import store as mem

    it = await db.one(conn, "SELECT * FROM publish_queue WHERE id = CAST(:i AS uuid)", {"i": item_id})
    if it is None:
        raise AppError("PUBLISH_NOT_FOUND", "Không có bài này.", 404)
    await mem.remember_episode(
        conn,
        it["agent_key"],
        title=f'Bài học: góp ý cho bài "{it["title"][:150]}"',
        content=f'Góp ý của Owner cho {"FAQ" if it["kind"] == "faq" else "bài blog"} "{it["title"]}": {text}',
        task_id=str(it["task_id"]) if it["task_id"] else None,
        task_type="publish",
        outcome="partial",
        metadata={"guidance": True, "publish_id": str(it["id"])},
        source_ref=it["url"],
        confidence=0.9,
    )
    await audit.record(conn, actor, "publish.feedback", f"publish:{item_id}", {"text": text[:300]})


# ------------------------------------------------------------------ giai đoạn
async def _save(conn: AsyncConnection, s: PublishSettings, actor: str) -> None:
    await store.put_setting(conn, "publishing", s, actor)


async def step_down_if_needed(conn: AsyncConnection) -> bool:
    s = await settings(conn)
    n = int(
        await db.scalar(
            conn,
            "SELECT count(*) FROM publish_queue WHERE status = 'retracted' AND retracted_at > now() - interval '7 days' "
            "AND (retracted_by LIKE 'user:%' OR retracted_by LIKE 'telegram:%') "
            "AND (CAST(:since AS timestamptz) IS NULL OR retracted_at >= CAST(:since AS timestamptz))",
            {"since": s.phase_since},
        )
        or 0
    )
    if n < STEP_DOWN or s.phase <= 1:
        return False
    s.phase -= 1
    s.phase_since = datetime.now(UTC)
    await _save(conn, s, "system:publisher")
    await audit.record(conn, "system:publisher", "publish.phase_down", "settings:publishing", {"phase": s.phase, "retracted_7d": n})
    await notify.enqueue(
        conn,
        "alert",
        f"↩️ Lùi lịch đăng về giai đoạn {s.phase}: anh/chị đã gỡ {n} bài trong 7 ngày.",
        dedupe_key=f"phase_down:{s.phase_since:%Y%m%d%H%M}",
    )
    return True


async def evaluate_phase(conn: AsyncConnection, now: datetime | None = None) -> int:
    """Lên giai đoạn khi đủ thời gian và tỉ lệ bài bị gỡ < 10%. Trả giai đoạn hiện tại."""
    now = now or datetime.now(UTC)
    s = await settings(conn)
    if s.phase_since is None:
        s.phase_since = now
        await _save(conn, s, "system:publisher")
        return s.phase
    if not s.auto_progress or s.paused or s.phase >= 3:
        return s.phase
    if now - s.phase_since < timedelta(days=PROGRESS[s.phase]):
        return s.phase
    r = await db.one(
        conn,
        "SELECT count(*) FILTER (WHERE status IN ('published','retracted')) AS pub, count(*) FILTER (WHERE status = 'retracted') AS ret "
        "FROM publish_queue WHERE published_at >= :since",
        {"since": max(s.phase_since, now - timedelta(days=28))},
    )
    pub, ret = int(r["pub"] or 0) if r else 0, int(r["ret"] or 0) if r else 0
    if pub == 0 or ret / pub >= MAX_RETRACT_RATE:
        return s.phase
    s.phase += 1
    s.phase_since = now
    await _save(conn, s, "system:publisher")
    await audit.record(
        conn, "system:publisher", "publish.phase_up", "settings:publishing", {"phase": s.phase, "published": pub, "retracted": ret}
    )
    await notify.enqueue(
        conn,
        "report",
        f"📈 Lịch đăng lên giai đoạn {s.phase}: {pub} bài đã đăng, {ret} bài bị gỡ. Xem Cài đặt → Lịch đăng bài để chỉnh.",
        dedupe_key=f"phase_up:{s.phase}:{now:%Y%m%d}",
    )
    return s.phase


async def set_paused(conn: AsyncConnection, paused: bool, *, actor: str, reason: str = "") -> PublishSettings:
    s = await settings(conn)
    s.paused, s.paused_reason = paused, reason[:200] if paused else ""
    await _save(conn, s, actor)
    await audit.record(conn, actor, "publish.paused" if paused else "publish.resumed", "settings:publishing", {"reason": reason[:200]})
    return s
