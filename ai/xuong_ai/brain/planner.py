"""Cân nhắc: biến tín hiệu thành việc, chấm điểm ưu tiên, rồi đối chiếu NỘI QUY văn phòng để quyết giao / hoãn / chặn.

Điểm = trọng số mục tiêu × mức độ tín hiệu × hệ số tin cậy (học từ kết quả duyệt: 0,5 … 1,5).
Việc điểm cao được xét trước nên được dùng hạn mức (LLM, sức duyệt của nhân viên) trước.
"""
from __future__ import annotations

import datetime as dt

from . import learning, state
from .model import Decision, Signal, Task, local
from .senses import ROUTINE, Ctx

ROUTINE_ACTIONS = set(ROUTINE) | {"outbox"}
CROSSSELL_PER_DAY = 5  # nhân viên duyệt từng cặp; gửi ít mà chất lượng (điểm cao trước)


def propose(signals: list[Signal], ctx: Ctx) -> list[Task]:
    tasks: list[Task] = []
    day = ctx.today.strftime("%Y%m%d")
    for s in signals:
        if s.kind == "routine":
            name = s.key.split(":", 1)[1] if s.key.startswith("due:") else s.key
            tasks.append(Task(name, name, s.evidence.get("role", "thu_ky"), s.goal, s.severity, s.title,
                              needs_site=name != "maintenance"))
        elif s.kind == "faq_gap":
            e = s.evidence
            ref = e["ref_base"] if e["attempt"] <= 1 else f"{e['ref_base']}:r{e['attempt']}"
            tasks.append(Task(ref, "faq_draft", "tu_van", s.goal, s.severity, s.title, {"cluster": e["cluster"], "ref": ref},
                              llm_calls=1, drafts=1, review_kind="faq"))
        elif s.kind == "blog_gap":
            e = s.evidence
            ref = e["ref_base"] if e["attempt"] <= 1 else f"{e['ref_base']}:r{e['attempt']}"
            tasks.append(Task(ref, "blog_draft", "bien_tap", s.goal, s.severity, s.title,
                              {"product_id": e["product_id"], "info_version": e["info_version"], "ref": ref}, llm_calls=1, drafts=1, review_kind="blog"))
        elif s.kind == "care_due":
            tasks.append(Task(f"care:{day}", "care_list", "cham_soc", s.goal, s.severity, s.title, {"n": s.evidence["n"]}, review_kind="care_list"))
        elif s.kind == "crosssell_new":
            n = min(s.evidence["n"], CROSSSELL_PER_DAY)
            tasks.append(Task(f"crosssell:{day}", "crosssell", "phan_tich", s.goal, s.severity, s.title, {"limit": n}, drafts=n, review_kind="cross_sell"))
    for t in tasks:
        _score(t, ctx)
    tasks.sort(key=lambda t: -t.score)
    return tasks


def _score(t: Task, ctx: Ctx) -> None:
    if t.action == "sync":
        t.score, t.why_score = 10.0, "mắt của văn phòng — luôn làm trước"
        return
    w = float(ctx.cfg.brain.goals.get(t.goal, 0.5))
    rel = 1.0
    if t.review_kind:
        r = learning.reliability(ctx.store, t.review_kind, ctx.now)
        rel = 0.5 + r["mean"]
        t.params.setdefault("_reliability", r)
    t.score = round(w * t.severity * rel, 4)
    t.why_score = f"mục tiêu {w:g} × mức độ {t.severity:.2f}" + (f" × tin cậy {rel:.2f}" if t.review_kind else "")


def decide(tasks: list[Task], ctx: Ctx) -> list[Decision]:
    """Áp nội quy theo thứ tự ưu tiên. Không ghi gì — chỉ quyết định."""
    b = ctx.cfg.brain
    out: list[Decision] = []
    assigned: dict[str, int] = {}
    llm_planned = 0
    review_planned = 0
    backlog = ctx.facts.get("backlog") or learning.backlog(ctx.store)
    pending_review = learning.pending_review_items(backlog)
    llm = ctx.facts.get("llm") or {}
    midnight_utc = _local_midnight_utc(ctx.now)
    paused = b.paused or (b.stop_file is not None and b.stop_file.exists())

    def put(t, verdict, why):
        out.append(Decision(t, verdict, why))

    for t in tasks:
        if paused:
            put(t, "block", "Văn phòng đang tạm dừng (công tắc tạm dừng trong config.toml hoặc tệp STOP)")
            continue
        last = state.last_task(ctx.store, t.key)
        if t.action not in ROUTINE_ACTIONS and last is not None and last["status"] == "done":
            put(t, "skip", "Đã làm hôm nay — lượt tiếp theo vào ngày mai" if t.action in ("crosssell", "care_list") else "Đã soạn xong, đang chờ kết quả duyệt")
            continue
        fails = state.recent_failures(ctx.store, t.key, ctx.now - dt.timedelta(hours=24))
        if fails and t.action not in ROUTINE:  # việc định kỳ đã giãn cách theo bảng jobs
            wait = min(60, 2 ** (fails - 1))
            ready = dt.datetime.strptime(last["started_at"], "%Y-%m-%d %H:%M:%S") + dt.timedelta(minutes=wait)
            if fails >= 5:
                put(t, "block", f"Thất bại {fails} lần trong 24 giờ — chờ người kiểm tra (lỗi: {(last['error'] or '')[:120]})")
                continue
            if ctx.now < ready:
                put(t, "defer", f"Lần trước lỗi, thử lại sau {ready.strftime('%H:%M')} UTC")
                continue
        if t.needs_site and t.action != "sync" and not ctx.facts.get("site_ok", True):
            put(t, "defer", "Website chưa phản hồi — chờ thư ký dữ liệu kết nối lại")
            continue
        rel = t.params.get("_reliability")
        if rel and rel["reviewed"] >= 5 and rel["mean"] < 0.2:
            put(t, "block", f"Loại bản nháp này bị từ chối liên tục ({rel['rejected']}/{rel['reviewed']}) — tạm dừng cho tới khi chỉnh lời dặn")
            continue
        if t.llm_calls:
            if not llm.get("available"):
                put(t, "block", "Chưa bật LLM (provider/api_key) — việc soạn nháp tạm gác")
                continue
            if llm.get("calls", 0) + llm_planned + t.llm_calls > llm.get("max_calls", 0) or llm.get("cost_usd", 0) >= llm.get("max_cost_usd", 0):
                put(t, "defer", f"Hết hạn mức LLM hôm nay ({llm.get('calls', 0)} lượt, {llm.get('cost_usd', 0):.3f} USD)")
                continue
        cap = b.daily_caps.get(t.action)
        if cap is not None:
            used = state.done_since(ctx.store, t.action, midnight_utc) + assigned.get(t.action, 0)
            if used >= cap:
                put(t, "defer", f"Đã đủ {cap} việc '{t.action}' hôm nay")
                continue
        if t.drafts:
            room = b.max_pending_review - pending_review - review_planned
            if room <= 0:
                put(t, "defer", f"Đang có {pending_review + review_planned} bản nháp chờ duyệt (tối đa {b.max_pending_review}) — chờ nhân viên duyệt bớt")
                continue
            if t.drafts > room and t.action == "crosssell":
                t.params["limit"], t.drafts = room, room
        if sum(assigned.values()) >= b.max_tasks_per_tick:
            put(t, "defer", f"Để lượt sau (mỗi lượt tối đa {b.max_tasks_per_tick} việc)")
            continue
        assigned[t.action] = assigned.get(t.action, 0) + 1
        llm_planned += t.llm_calls
        review_planned += t.drafts
        put(t, "assign", f"Điểm {t.score:.2f} ({t.why_score})")
    return out


def _local_midnight_utc(now: dt.datetime) -> dt.datetime:
    loc = local(now)
    return now - (loc - loc.replace(hour=0, minute=0, second=0, microsecond=0))
