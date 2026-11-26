"""Trưởng văn phòng: mỗi nhịp (tick) làm một vòng Cảm nhận → Cân nhắc → Giao việc → Học → Báo cáo.

Nguyên tắc bất biến (kế thừa thiết kế gốc):
- Mọi đầu ra gửi website đều ở trạng thái CHỜ DUYỆT; bộ não không xuất bản, không sửa giá/đơn/kho.
- Không có tên, SĐT, địa chỉ khách; nội dung gửi LLM được che SĐT/email.
- Website vẫn bán bình thường khi máy này tắt; bật lại thì việc quá hạn được làm bù.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time

from .. import sync as syncmod
from ..agents import content, crosssell, enqueue, flush_outbox
from ..client import SiteError
from . import brief, learning, planner, senses, state
from .model import ROSTER, Task, fmt, local, now_utc

log = logging.getLogger("xuong_ai.brain")


class Brain:
    def __init__(self, app, clock=now_utc):
        self.app, self.store, self.cfg, self.llm, self.client = app, app.store, app.cfg, app.llm, app.client
        self.clock = clock
        state.ensure(self.store)

    # ------------------------------------------------------------------ suy nghĩ (không làm gì)
    def ctx(self, now: dt.datetime | None = None) -> senses.Ctx:
        return senses.Ctx(self.store, self.cfg, self.llm, self.store.cache_get("catalog", {}) or {}, now or self.clock())

    def think(self, now: dt.datetime | None = None) -> dict:
        ctx = self.ctx(now)
        signals, escalations = senses.perceive(ctx)
        tasks = planner.propose(signals, ctx)
        decisions = planner.decide(tasks, ctx)
        return {"ctx": ctx, "signals": signals, "escalations": escalations, "decisions": decisions}

    # ------------------------------------------------------------------ một nhịp làm việc
    def tick(self) -> dict:
        now = self.clock()
        tid = self.store.db.execute("INSERT INTO brain_ticks(started_at) VALUES(?)", (fmt(now),)).lastrowid
        summary = {"tick": tid, "assigned": 0, "done": 0, "failed": 0, "ran": []}

        # 1) Mở mắt: đồng bộ trước để mọi nhận định dựa trên dữ liệu mới nhất
        first = self.think(now)
        for d in first["decisions"]:
            if d.task.action == "sync":
                state.record_decision(self.store, tid, now, d.task, d.verdict, d.why)
                if d.verdict == "assign":
                    self._run(d.task, summary)
                break

        # 2) Cảm nhận + cân nhắc trên dữ liệu vừa đồng bộ
        th = self.think(self.clock())
        now = th["ctx"].now
        state.record_signals(self.store, th["signals"], now)
        state.record_escalations(self.store, th["escalations"], now)
        for d in th["decisions"]:
            if d.task.action == "sync":
                continue
            state.record_decision(self.store, tid, now, d.task, d.verdict, d.why)
            if d.verdict == "assign":
                self._run(d.task, summary)

        # 3) Báo cáo mỗi sáng + dọn sổ cũ
        path = self.maybe_brief(self.clock())
        if path:
            summary["brief"] = str(path)
        self.store.db.execute("UPDATE brain_ticks SET finished_at=?, signals=?, escalations=?, assigned=?, done=?, failed=? WHERE id=?",
                              (fmt(self.clock()), len(th["signals"]), len(th["escalations"]), summary["assigned"], summary["done"], summary["failed"], tid))
        return summary

    def loop(self) -> None:
        log.info("Văn phòng AI bắt đầu làm việc (Ctrl+C để dừng)")
        while True:
            try:
                s = self.tick()
                if s["ran"]:
                    log.info("Nhịp %s: %s", s["tick"], ", ".join(s["ran"]))
            except Exception:  # bộ não không được chết vì một lỗi lạ; ghi lại và sang nhịp sau
                log.exception("Nhịp làm việc lỗi")
            time.sleep(self.cfg.brain.tick_seconds)

    def maybe_brief(self, now: dt.datetime, force: bool = False):
        loc = local(now)
        day = loc.date().isoformat()
        if not force and (loc.hour < self.cfg.brain.brief_hour or self.store.get("brain.brief_date") == day):
            return None
        path = brief.write(self, now)
        self.store.set("brain.brief_date", day)
        state.prune(self.store, now)
        return path

    # ------------------------------------------------------------------ giao việc cho nhân viên
    def _run(self, task: Task, summary: dict) -> None:
        now = self.clock()
        task.params = {k: v for k, v in task.params.items() if not k.startswith("_")}
        tid = state.start_task(self.store, task, now)
        summary["assigned"] += 1
        try:
            res = ACTIONS[task.action](self, task)
            state.finish_task(self.store, tid, True, self.clock(), res)
            self.app.record_job(task.action, True, res)
            summary["done"] += 1
            summary["ran"].append(f"{ROSTER[task.role].title}: {task.action} ✓")
        except Exception as e:
            log.warning("[%s] %s lỗi: %s", task.role, task.key, e)
            state.finish_task(self.store, tid, False, self.clock(), error=str(e))
            self.app.record_job(task.action, False, error=str(e))
            summary["failed"] += 1
            summary["ran"].append(f"{ROSTER[task.role].title}: {task.action} ✗")

    def _flush(self) -> dict:
        try:
            return flush_outbox(self.store, self.client)
        except SiteError as e:  # bản nháp vẫn nằm trong hộp thư đi; thư ký sẽ gửi lại
            return {"queued": True, "error": str(e)}


# ---------------------------------------------------------------------- việc của từng nhân viên
def _sync(b: Brain, t: Task):
    return syncmod.sync(b.store, b.client)


def _catalog(b: Brain, t: Task):
    return b.app.job_catalog()


def _feedback(b: Brain, t: Task):
    return learning.pull(b.store, b.client, b.store.cache_get("catalog"), b.clock())


def _outbox(b: Brain, t: Task):
    return flush_outbox(b.store, b.client)


def _maintenance(b: Brain, t: Task):
    return b.app.job_maintenance()


def _faq_draft(b: Brain, t: Task):
    r = content.draft_faq(b.store, b.llm, t.params["cluster"], t.params["ref"], guidance=learning.guidance(b.store, "faq"))
    if r is None:
        raise ValueError("LLM trả về nội dung không đúng định dạng JSON")
    r["outbox"] = b._flush()
    return r


def _blog_draft(b: Brain, t: Task):
    cat = b.store.cache_get("catalog", {}) or {}
    p = next((x for x in cat.get("products", []) if x["id"] == t.params["product_id"]), None)
    if p is None or p["info_version"] != t.params["info_version"]:
        return {"skipped": "Sản phẩm đã đổi hoặc ngừng bán trước khi soạn"}
    r = content.draft_blog(b.store, b.llm, p, t.params["ref"], guidance=learning.guidance(b.store, "blog"))
    if r is None:
        raise ValueError("LLM trả về nội dung không đúng định dạng JSON")
    r["outbox"] = b._flush()
    return r


def _care_list(b: Brain, t: Task):
    ctx = b.ctx()
    entries = senses.care_entries(ctx)
    if not entries:
        return {"entries": 0}
    batch = "care-" + ctx.today.strftime("%Y%m%d")
    with b.store.tx() as db:
        if enqueue(b.store, batch, "care_list", {"batch_id": batch, "entries": entries}):
            db.executemany("INSERT OR IGNORE INTO brain_care_sent(customer_key, category_id, sent_at, batch_id) VALUES(?,?,?,?)",
                           [(e["customer_key"], e["category_id"], fmt(ctx.now), batch) for e in entries])
    return {"entries": len(entries), "batch": batch, "outbox": b._flush()}


def _crosssell(b: Brain, t: Task):
    r = crosssell.run_new(b.store, b.cfg, int(t.params.get("limit", 10)))
    r["outbox"] = b._flush()
    return r


ACTIONS = {
    "sync": _sync, "catalog": _catalog, "feedback": _feedback, "outbox": _outbox, "maintenance": _maintenance,
    "faq_draft": _faq_draft, "blog_draft": _blog_draft, "care_list": _care_list, "crosssell": _crosssell,
}


def describe(task: Task) -> str:
    return json.dumps({k: v for k, v in task.params.items() if not k.startswith("_") and k != "cluster"}, ensure_ascii=False)
