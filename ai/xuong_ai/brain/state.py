"""Sổ sách của văn phòng (SQLite): tín hiệu, sổ giao việc, quyết định, việc cần người, phản hồi duyệt, nhịp làm việc."""
from __future__ import annotations

import datetime as dt
import json

from ..store import Store
from .model import Escalation, Signal, Task, fmt

SCHEMA = """
CREATE TABLE IF NOT EXISTS brain_signals (
  key TEXT PRIMARY KEY, kind TEXT NOT NULL, goal TEXT, severity REAL, title TEXT, evidence TEXT,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS brain_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, action TEXT NOT NULL, role TEXT NOT NULL, goal TEXT,
  params TEXT, score REAL, reason TEXT, status TEXT NOT NULL,      -- running | done | failed
  result TEXT, error TEXT, started_at TEXT NOT NULL, finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_brain_tasks_key ON brain_tasks(key, started_at);
CREATE INDEX IF NOT EXISTS idx_brain_tasks_action ON brain_tasks(action, started_at);
CREATE TABLE IF NOT EXISTS brain_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tick INTEGER, at TEXT NOT NULL, task_key TEXT NOT NULL, action TEXT, role TEXT,
  verdict TEXT NOT NULL, score REAL, why TEXT
);
CREATE INDEX IF NOT EXISTS idx_brain_decisions_key ON brain_decisions(task_key, id);
CREATE TABLE IF NOT EXISTS brain_escalations (
  key TEXT PRIMARY KEY, goal TEXT, severity REAL, title TEXT, detail TEXT, status TEXT NOT NULL,   -- open | closed
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS brain_feedback (
  client_ref TEXT PRIMARY KEY, kind TEXT, status TEXT NOT NULL, note TEXT, received_at TEXT, reviewed_at TEXT, updated_at TEXT NOT NULL
);
-- Khách đã đưa vào danh sách chăm sóc (chỉ mã băm customer_key): không nhắc lại trong 30 ngày
CREATE TABLE IF NOT EXISTS brain_care_sent (
  customer_key TEXT NOT NULL, category_id INTEGER NOT NULL, sent_at TEXT NOT NULL, batch_id TEXT, PRIMARY KEY (customer_key, category_id, sent_at)
);
CREATE TABLE IF NOT EXISTS brain_ticks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
  signals INTEGER, escalations INTEGER, assigned INTEGER, done INTEGER, failed INTEGER, note TEXT
);
"""


def ensure(store: Store) -> None:
    store.db.executescript(SCHEMA)


def js(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


# ------------------------------------------------------------------ tín hiệu & việc cần người
def record_signals(store: Store, signals: list[Signal], now: dt.datetime) -> None:
    t = fmt(now)
    keys = [s.key for s in signals]
    with store.tx() as db:
        for s in signals:
            db.execute(
                "INSERT INTO brain_signals(key, kind, goal, severity, title, evidence, first_seen, last_seen) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET severity=excluded.severity, title=excluded.title, evidence=excluded.evidence, "
                "last_seen=excluded.last_seen, resolved_at=NULL, "
                "first_seen=CASE WHEN brain_signals.resolved_at IS NULL THEN brain_signals.first_seen ELSE excluded.first_seen END",
                (s.key, s.kind, s.goal, s.severity, s.title, js(s.evidence), t, t))
        ph = ",".join("?" * len(keys)) or "''"
        db.execute(f"UPDATE brain_signals SET resolved_at = ? WHERE resolved_at IS NULL AND key NOT IN ({ph})", (t, *keys))


def record_escalations(store: Store, items: list[Escalation], now: dt.datetime) -> None:
    t = fmt(now)
    keys = [e.key for e in items]
    with store.tx() as db:
        for e in items:
            db.execute(
                "INSERT INTO brain_escalations(key, goal, severity, title, detail, status, first_seen, last_seen) VALUES(?,?,?,?,?,'open',?,?) "
                "ON CONFLICT(key) DO UPDATE SET severity=excluded.severity, title=excluded.title, detail=excluded.detail, last_seen=excluded.last_seen, "
                "first_seen=CASE WHEN brain_escalations.status='open' THEN brain_escalations.first_seen ELSE excluded.first_seen END, "
                "status='open', closed_at=NULL",
                (e.key, e.goal, e.severity, e.title, e.detail, t, t))
        ph = ",".join("?" * len(keys)) or "''"
        # Điều kiện không còn → tự đóng (vd website đã phản hồi lại, chủ xưởng đã bổ sung nhãn)
        db.execute(f"UPDATE brain_escalations SET status='closed', closed_at=? WHERE status='open' AND key NOT IN ({ph})", (t, *keys))


def open_escalations(store: Store) -> list:
    return store.all("SELECT * FROM brain_escalations WHERE status='open' ORDER BY severity DESC, first_seen")


# ------------------------------------------------------------------ sổ giao việc
def start_task(store: Store, task: Task, now: dt.datetime) -> int:
    cur = store.db.execute(
        "INSERT INTO brain_tasks(key, action, role, goal, params, score, reason, status, started_at) VALUES(?,?,?,?,?,?,?,'running',?)",
        (task.key, task.action, task.role, task.goal, js(task.params), task.score, task.reason, fmt(now)))
    return cur.lastrowid


def finish_task(store: Store, tid: int, ok: bool, now: dt.datetime, result=None, error: str | None = None) -> None:
    store.db.execute("UPDATE brain_tasks SET status=?, result=?, error=?, finished_at=? WHERE id=?",
                     ("done" if ok else "failed", js(result)[:2000] if result is not None else None, (error or "")[:500] or None, fmt(now), tid))


def last_task(store: Store, key: str):
    return store.one("SELECT * FROM brain_tasks WHERE key = ? ORDER BY id DESC LIMIT 1", (key,))


def recent_failures(store: Store, key: str, since: dt.datetime) -> int:
    """Số lần thất bại LIÊN TIẾP gần nhất của một việc (dừng đếm khi gặp lần thành công)."""
    n = 0
    for r in store.all("SELECT status FROM brain_tasks WHERE key = ? AND started_at >= ? ORDER BY id DESC LIMIT 20", (key, fmt(since))):
        if r["status"] != "failed":
            break
        n += 1
    return n


def done_since(store: Store, action: str, since: dt.datetime) -> int:
    return store.one("SELECT COUNT(*) n FROM brain_tasks WHERE action = ? AND status = 'done' AND started_at >= ?", (action, fmt(since)))["n"]


# ------------------------------------------------------------------ quyết định (chỉ ghi khi đổi, để sổ không bị lặp mỗi phút)
def record_decision(store: Store, tick: int | None, now: dt.datetime, task: Task, verdict: str, why: str) -> bool:
    last = store.one("SELECT verdict, why FROM brain_decisions WHERE task_key = ? ORDER BY id DESC LIMIT 1", (task.key,))
    if last and last["verdict"] == verdict and last["why"] == why and verdict != "assign":
        return False
    store.db.execute("INSERT INTO brain_decisions(tick, at, task_key, action, role, verdict, score, why) VALUES(?,?,?,?,?,?,?,?)",
                     (tick, fmt(now), task.key, task.action, task.role, verdict, round(task.score, 4), why))
    return True


def prune(store: Store, now: dt.datetime, days: int = 60) -> None:
    cut = fmt(now - dt.timedelta(days=days))
    with store.tx() as db:
        db.execute("DELETE FROM brain_tasks WHERE started_at < ?", (cut,))
        db.execute("DELETE FROM brain_decisions WHERE at < ?", (cut,))
        db.execute("DELETE FROM brain_ticks WHERE started_at < ?", (cut,))
        db.execute("DELETE FROM brain_signals WHERE resolved_at IS NOT NULL AND resolved_at < ?", (cut,))
        db.execute("DELETE FROM brain_escalations WHERE status = 'closed' AND closed_at < ?", (cut,))
