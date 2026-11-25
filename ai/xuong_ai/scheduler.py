"""Điều phối: chạy công việc theo lịch, thử lại có giãn cách khi gián đoạn, ghi trạng thái vào SQLite.

Máy tắt rồi bật lại → các việc quá hạn chạy bù ngay lần đầu.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
import traceback

from . import sync as syncmod
from .agents import care, content, crosssell, flush_outbox, maintenance
from .calibrate import evaluate, load_cases
from .client import SiteClient
from .llm import Llm
from .memory import Memory
from .store import Store

log = logging.getLogger("xuong_ai.scheduler")
FMT = "%Y-%m-%d %H:%M:%S"


class App:
    def __init__(self, cfg, store: Store | None = None, client: SiteClient | None = None, llm: Llm | None = None):
        self.cfg = cfg
        self.store = store or Store(cfg.db_path)
        self.client = client or SiteClient(cfg.site.base_url, cfg.site.read_key, cfg.site.write_key, cfg.site.timeout)
        self.llm = llm or Llm(cfg.llm, self.store)

    def catalog(self, refresh: bool = False) -> dict:
        cat = self.store.cache_get("catalog")
        if refresh or cat is None:
            cat = self.client.catalog()
            self.store.cache_put("catalog", cat)
            Memory(self.store).refresh_from_catalog(cat)
        return cat

    # các công việc ---------------------------------------------------------
    def job_sync(self):
        return syncmod.sync(self.store, self.client)

    def job_catalog(self):
        cat = self.catalog(refresh=True)
        return {"products": len(cat.get("products", [])), "faqs": len(cat.get("published_faqs", [])), "unanswered": len(cat.get("unanswered_questions", []))}

    def job_crosssell(self):
        r = crosssell.run(self.store, self.cfg)
        r["outbox"] = flush_outbox(self.store, self.client)
        return r

    def job_care(self):
        r = care.run(self.store, self.cfg, self.catalog())
        r["outbox"] = flush_outbox(self.store, self.client)
        return r

    def job_faq_drafts(self):
        r = content.faq_drafts(self.store, self.llm, self.catalog(), self.cfg.faq_threshold, self.cfg.faq_drafts_per_run)
        r["outbox"] = flush_outbox(self.store, self.client)
        return r

    def job_blog_drafts(self):
        r = content.blog_drafts(self.store, self.llm, self.catalog(), self.cfg.blog_drafts_per_run)
        r["outbox"] = flush_outbox(self.store, self.client)
        return r

    def job_maintenance(self):
        calib = self.calibrate()
        path = maintenance.report(self.store, self.cfg, calib)
        return {"report": str(path)}

    def calibrate(self, eval_path=None) -> dict | None:
        from pathlib import Path
        p = Path(eval_path) if eval_path else Path(__file__).resolve().parent.parent / "eval" / "faq_eval.jsonl"
        faqs = self.catalog().get("published_faqs", [])
        if not p.exists() or not faqs:
            return None
        return evaluate(faqs, load_cases(p))

    # điều phối -------------------------------------------------------------
    def run_job(self, name: str):
        fn = getattr(self, f"job_{name}")
        now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
        try:
            res = fn()
            every = int(self.cfg.schedule.get(name, 60))
            self.store.db.execute(
                "INSERT INTO jobs(name, last_run, next_run, failures, last_error, last_result) VALUES(?,?,?,0,NULL,?) "
                "ON CONFLICT(name) DO UPDATE SET last_run=excluded.last_run, next_run=excluded.next_run, failures=0, last_error=NULL, last_result=excluded.last_result",
                (name, now.strftime(FMT), (now + dt.timedelta(minutes=every)).strftime(FMT), json.dumps(res, ensure_ascii=False, default=str)[:2000]))
            log.info("[%s] %s", name, res)
            return res
        except Exception as e:  # thử lại có giãn cách: 1, 2, 4, … tối đa 60 phút
            row = self.store.one("SELECT failures FROM jobs WHERE name = ?", (name,))
            fails = (row["failures"] if row else 0) + 1
            wait = min(60, 2 ** (fails - 1))
            self.store.db.execute(
                "INSERT INTO jobs(name, last_run, next_run, failures, last_error) VALUES(?,?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET next_run=excluded.next_run, failures=excluded.failures, last_error=excluded.last_error",
                (name, now.strftime(FMT), (now + dt.timedelta(minutes=wait)).strftime(FMT), fails, str(e)[:500]))
            log.warning("[%s] lỗi lần %s, thử lại sau %s phút: %s", name, fails, wait, e)
            log.debug(traceback.format_exc())
            return None

    def due_jobs(self) -> list[str]:
        now = dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime(FMT)
        due = []
        for name in self.cfg.schedule:
            r = self.store.one("SELECT next_run FROM jobs WHERE name = ?", (name,))
            if not r or (r["next_run"] or "") <= now:
                due.append(name)
        # đồng bộ trước, danh mục trước các tác nhân
        order = ["sync", "catalog", "crosssell", "care", "faq_drafts", "blog_drafts", "maintenance"]
        return sorted(due, key=lambda n: order.index(n) if n in order else 99)

    def loop(self, tick: int = 30):
        log.info("Bắt đầu vòng điều phối (Ctrl+C để dừng)")
        while True:
            for name in self.due_jobs():
                self.run_job(name)
                if name == "sync" and self.store.one("SELECT failures FROM jobs WHERE name='sync'")["failures"] > 0:
                    break  # website không truy cập được: chờ vòng sau
            time.sleep(tick)
