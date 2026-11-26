"""Màn hình "Diễn biến trực tiếp" của văn phòng AI.

Một trang web chạy trên chính máy này (http://127.0.0.1:8765) cho chủ xưởng theo dõi:
văn phòng có đang làm việc không, từng nhân viên AI đang làm gì, việc gì đang chờ và vì sao,
việc gì cần người quyết, và dòng diễn biến cập nhật mỗi 2 giây.

- Chỉ ĐỌC sổ sách SQLite (mở ở chế độ read-only); không có nút nào thay đổi dữ liệu.
- Chỉ nghe trên 127.0.0.1; không có dữ liệu cá nhân của khách (CSDL cục bộ vốn không có).
- Chỉ dùng thư viện chuẩn Python.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .brain.model import FMT, ROSTER

log = logging.getLogger("xuong_ai.monitor")
ASSETS = Path(__file__).with_name("monitor_assets")
LANE_MINUTES = 60

ACTION_LABEL = {
    "sync": "đồng bộ đơn hàng",
    "catalog": "cập nhật danh mục sản phẩm",
    "feedback": "lấy kết quả duyệt bài",
    "outbox": "gửi lại bản nháp",
    "maintenance": "bảo trì, hiệu chỉnh ngưỡng chat",
    "faq_draft": "soạn FAQ",
    "blog_draft": "soạn bài blog",
    "care_list": "lập danh sách chăm sóc khách",
    "crosssell": "tìm cặp sản phẩm mua kèm",
}
LLM_TASK_ROLE = {"faq_draft": "tu_van", "blog_draft": "bien_tap"}
FEEDBACK_LABEL = {"approved": "duyệt nguyên văn", "edited": "sửa rồi duyệt", "rejected": "từ chối", "retracted": "gỡ bài",
                  "invalid": "website từ chối khi nhận", "pending": "đang chờ duyệt", "duplicate": "đã có từ trước", "gone": "đã xóa", "done": "đã xử lý xong"}
KIND_LABEL = {"faq": "FAQ", "blog": "bài blog", "cross_sell": "gợi ý mua kèm", "care_list": "danh sách chăm sóc"}


def _iso(s: str | None) -> str | None:
    """'YYYY-MM-DD HH:MM:SS' (UTC) → ISO có Z để trình duyệt tự đổi giờ."""
    return s.replace(" ", "T") + "Z" if s else None


def _parse(s: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s[:19], FMT) if s else None
    except ValueError:
        return None


def _json(s):
    try:
        return json.loads(s) if s else {}
    except ValueError:
        return {}


def summarize(action: str, result: str | None, error: str | None) -> str:
    """Tóm tắt kết quả một việc bằng lời dễ hiểu."""
    if error:
        return "Lỗi: " + error[:160]
    r = _json(result)
    if not isinstance(r, dict):
        return ""
    if action == "sync":
        if "orders" in r:
            return f"Tải lại toàn bộ: {r['orders']} đơn"
        n = r.get("applied", 0)
        return f"{n} thay đổi mới" if n else "Không có thay đổi mới"
    if action == "catalog":
        return f"{r.get('products', 0)} sản phẩm, {r.get('faqs', 0)} FAQ, {r.get('unanswered', 0)} câu hỏi chưa có trả lời"
    if action == "feedback":
        ch = r.get("changed") or {}
        parts = [f"{v} {FEEDBACK_LABEL.get(k, k)}" for k, v in ch.items()]
        return "Kết quả duyệt mới: " + ", ".join(parts) if parts else "Không có kết quả duyệt mới"
    if action == "outbox":
        return f"Đã gửi {r.get('sent', 0)} bản nháp"
    if action == "maintenance":
        return "Đã viết báo cáo bảo trì"
    if action in ("faq_draft", "blog_draft"):
        if r.get("skipped"):
            return r["skipped"]
        t = r.get("question") or r.get("title")
        return f"Đã gửi lên website chờ duyệt: “{t}”" if t else "Đã soạn xong"
    if action == "care_list":
        return f"{r.get('entries', 0)} khách đến kỳ mua lại" if r.get("entries") else "Không có khách mới đến kỳ"
    if action == "crosssell":
        return f"{r.get('queued', 0)} cặp mua kèm mới chờ duyệt"
    return ""


def _has_brain(db) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='brain_tasks'").fetchone() is not None


def build_state(db: sqlite3.Connection, cfg, now: dt.datetime | None = None) -> dict:
    """Ảnh chụp trạng thái văn phòng cho màn hình. Chỉ đọc."""
    now = now or dt.datetime.now(dt.UTC).replace(tzinfo=None)
    tick_s = cfg.brain.tick_seconds
    paused = cfg.brain.paused or bool(cfg.brain.stop_file and cfg.brain.stop_file.exists())
    out = {"now": _iso(now.strftime(FMT)), "lane_minutes": LANE_MINUTES, "office": {}, "agents": [], "lanes": [], "feed": [],
           "waiting": [], "escalations": [], "llm": {}, "backlog": {}}
    if not _has_brain(db):
        out["office"] = {"state": "new", "message": "Văn phòng chưa làm việc lần nào. Chạy: python -m xuong_ai run"}
        return out

    q = lambda sql, args=(): db.execute(sql, args).fetchall()  # noqa: E731
    one = lambda sql, args=(): db.execute(sql, args).fetchone()  # noqa: E731

    # ---------------- trạng thái chung
    last = one("SELECT started_at, finished_at FROM brain_ticks ORDER BY id DESC LIMIT 1")
    last_at = _parse(last["finished_at"] or last["started_at"]) if last else None
    alive = bool(last_at and (now - last_at).total_seconds() <= max(3 * tick_s, 120))
    state = "paused" if paused else ("running" if alive else "stopped")
    msg = {"paused": "Văn phòng đang tạm dừng (công tắc tạm dừng hoặc tệp STOP).",
           "running": "Văn phòng đang làm việc.",
           "stopped": "Văn phòng đang nghỉ: không thấy nhịp làm việc nào gần đây. Chạy: python -m xuong_ai run"}[state]
    out["office"] = {"state": state, "message": msg, "last_tick_at": _iso(last_at.strftime(FMT)) if last_at else None, "tick_seconds": tick_s}

    day = now.strftime("%Y-%m-%d")
    u = one("SELECT COUNT(*) calls, COALESCE(SUM(cost_usd),0) cost FROM llm_usage WHERE day = ?", (day,))
    m = one("SELECT COALESCE(SUM(cost_usd),0) cost FROM llm_usage WHERE day >= ?", (now.strftime("%Y-%m-01"),))
    out["llm"] = {"calls": u["calls"], "cost_usd": round(u["cost"], 4), "month_cost_usd": round(m["cost"], 4),
                  "max_calls": cfg.llm.max_calls_per_day, "max_cost_usd": cfg.llm.max_cost_per_day_usd,
                  "enabled": cfg.llm.provider != "none" and bool(cfg.llm.api_key)}
    bl = one("SELECT value FROM sync_state WHERE key = 'brain.backlog'")
    out["backlog"] = _json(bl["value"]) if bl else {}

    out["escalations"] = [{"key": r["key"], "title": r["title"], "detail": r["detail"], "severity": r["severity"], "since": _iso(r["first_seen"])}
                          for r in q("SELECT * FROM brain_escalations WHERE status='open' ORDER BY severity DESC, first_seen")]

    # ---------------- từng nhân viên
    since_day = (now - dt.timedelta(hours=24)).strftime(FMT)
    lane_from = now - dt.timedelta(minutes=LANE_MINUTES)
    tasks_window = q("SELECT * FROM brain_tasks WHERE started_at >= ? OR status = 'running' ORDER BY id", (lane_from.strftime(FMT),))
    for code, role in ROSTER.items():
        a = {"code": code, "title": role.title, "duty": role.duty, "uses_llm": role.uses_llm, "status": "idle",
             "current": None, "last": None, "today": {"done": 0, "failed": 0}, "note": ""}
        if code == "truong_phong":
            n = one("SELECT COUNT(*) n FROM brain_ticks WHERE started_at >= ?", (since_day,))["n"]
            a["status"] = "working" if state == "running" else ("paused" if paused else "idle")
            a["today"] = {"done": n, "failed": 0}
            a["note"] = f"{n} nhịp làm việc trong 24 giờ"
            dec = one("SELECT * FROM brain_decisions ORDER BY id DESC LIMIT 1")
            if dec:
                a["last"] = {"action": dec["action"], "label": f"quyết định: {dec['verdict']} {ACTION_LABEL.get(dec['action'], dec['action'])}",
                             "summary": dec["why"], "at": _iso(dec["at"]), "status": "done"}
        elif code == "chu_xuong":
            n = len(out["escalations"])
            a["status"] = "attention" if n else "idle"
            a["note"] = f"{n} việc đang chờ anh/chị" if n else "Không có việc nào cần anh/chị"
        else:
            cur = one("SELECT * FROM brain_tasks WHERE role = ? AND status = 'running' ORDER BY id DESC LIMIT 1", (code,))
            lt = one("SELECT * FROM brain_tasks WHERE role = ? AND status <> 'running' ORDER BY id DESC LIMIT 1", (code,))
            cnt = one("SELECT SUM(status='done') d, SUM(status='failed') f FROM brain_tasks WHERE role = ? AND started_at >= ?", (code, since_day))
            a["today"] = {"done": cnt["d"] or 0, "failed": cnt["f"] or 0}
            if cur:
                a["status"] = "working"
                a["current"] = {"action": cur["action"], "label": ACTION_LABEL.get(cur["action"], cur["action"]), "reason": cur["reason"], "since": _iso(cur["started_at"])}
            elif lt and lt["status"] == "failed":
                a["status"] = "error"
            if lt:
                a["last"] = {"action": lt["action"], "label": ACTION_LABEL.get(lt["action"], lt["action"]), "status": lt["status"],
                             "summary": summarize(lt["action"], lt["result"], lt["error"]), "at": _iso(lt["finished_at"] or lt["started_at"])}
            wait = one("SELECT d.* FROM brain_decisions d WHERE d.role = ? ORDER BY d.id DESC LIMIT 1", (code,))
            if wait and wait["verdict"] in ("defer", "block") and not cur:
                a["status"] = "waiting" if a["status"] == "idle" else a["status"]
                a["note"] = wait["why"]
        out["agents"].append(a)

    # ---------------- làn hoạt động 60 phút
    lanes = {c: [] for c in ROSTER}
    for t in tasks_window:
        s = max(_parse(t["started_at"]) or now, lane_from)
        e = _parse(t["finished_at"]) or now
        lanes.setdefault(t["role"], []).append({"start": _iso(s.strftime(FMT)), "end": _iso(e.strftime(FMT)), "status": t["status"],
                                                "label": ACTION_LABEL.get(t["action"], t["action"]),
                                                "summary": summarize(t["action"], t["result"], t["error"]) if t["status"] != "running" else (t["reason"] or "")})
    for r in q("SELECT started_at, finished_at FROM brain_ticks WHERE started_at >= ? ORDER BY id", (lane_from.strftime(FMT),)):
        lanes["truong_phong"].append({"start": _iso(r["started_at"]), "end": _iso(r["finished_at"] or r["started_at"]), "status": "tick",
                                      "label": "một nhịp cân nhắc", "summary": ""})
    for r in q("SELECT at, role, action, verdict, why FROM brain_decisions WHERE at >= ? AND verdict IN ('defer','block')", (lane_from.strftime(FMT),)):
        lanes.setdefault(r["role"], []).append({"start": _iso(r["at"]), "end": _iso(r["at"]), "status": r["verdict"],
                                                "label": ("hoãn " if r["verdict"] == "defer" else "chặn ") + ACTION_LABEL.get(r["action"], r["action"]), "summary": r["why"]})
    out["lanes"] = [{"code": c, "title": ROSTER[c].title, "blocks": lanes.get(c, [])} for c in ROSTER if c != "chu_xuong"]

    # ---------------- việc đang chờ / bị chặn (quyết định mới nhất của từng việc, 24 giờ)
    for r in q("SELECT d.* FROM brain_decisions d JOIN (SELECT task_key, MAX(id) mid FROM brain_decisions WHERE at >= ? GROUP BY task_key) m "
               "ON m.mid = d.id WHERE d.verdict IN ('defer','block') ORDER BY d.id DESC LIMIT 30", (since_day,)):
        out["waiting"].append({"role": r["role"], "role_title": ROSTER[r["role"]].title if r["role"] in ROSTER else r["role"],
                               "label": ACTION_LABEL.get(r["action"], r["action"]), "verdict": r["verdict"], "why": r["why"], "at": _iso(r["at"])})

    # ---------------- dòng diễn biến
    feed = []
    fr = (now - dt.timedelta(hours=24)).strftime(FMT)
    for t in q("SELECT * FROM brain_tasks WHERE started_at >= ? ORDER BY id DESC LIMIT 150", (fr,)):
        label = ACTION_LABEL.get(t["action"], t["action"])
        feed.append({"at": _iso(t["started_at"]), "role": t["role"], "kind": "start", "text": f"bắt đầu {label}", "detail": t["reason"] or ""})
        if t["finished_at"]:
            ok = t["status"] == "done"
            feed.append({"at": _iso(t["finished_at"]), "role": t["role"], "kind": "done" if ok else "failed",
                         "text": f"{'xong' if ok else 'lỗi khi'} {label}", "detail": summarize(t["action"], t["result"], t["error"])})
    for r in q("SELECT * FROM brain_decisions WHERE at >= ? AND verdict IN ('defer','block') ORDER BY id DESC LIMIT 60", (fr,)):
        feed.append({"at": _iso(r["at"]), "role": r["role"], "kind": r["verdict"],
                     "text": ("hoãn " if r["verdict"] == "defer" else "chặn ") + ACTION_LABEL.get(r["action"], r["action"]), "detail": r["why"]})
    for r in q("SELECT * FROM brain_escalations WHERE last_seen >= ? OR closed_at >= ?", (fr, fr)):
        if r["first_seen"] >= fr:
            feed.append({"at": _iso(r["first_seen"]), "role": "chu_xuong", "kind": "escalate", "text": "cần anh/chị: " + r["title"], "detail": r["detail"] or ""})
        if r["closed_at"] and r["closed_at"] >= fr:
            feed.append({"at": _iso(r["closed_at"]), "role": "truong_phong", "kind": "resolved", "text": "đã tự đóng: " + r["title"], "detail": "Điều kiện không còn nữa"})
    for r in q("SELECT * FROM llm_usage WHERE created_at >= ? ORDER BY id DESC LIMIT 60", (fr,)):
        feed.append({"at": _iso(r["created_at"]), "role": LLM_TASK_ROLE.get(r["task"], "truong_phong"), "kind": "llm" if r["ok"] else "failed",
                     "text": f"gọi {r['model'] or 'LLM'}" + ("" if r["ok"] else " (lỗi)"),
                     "detail": f"{(r['input_tokens'] or 0) + (r['output_tokens'] or 0):,} token, {r['cost_usd'] or 0:.4f} USD".replace(",", ".", 1)})
    for r in q("SELECT * FROM brain_feedback WHERE updated_at >= ? AND status NOT IN ('pending') ORDER BY updated_at DESC LIMIT 40", (fr,)):
        feed.append({"at": _iso(r["updated_at"]), "role": "truong_phong", "kind": "feedback",
                     "text": f"người duyệt {FEEDBACK_LABEL.get(r['status'], r['status'])} {KIND_LABEL.get(r['kind'], r['kind'] or '')}".strip(),
                     "detail": r["note"] or ""})
    feed.sort(key=lambda x: x["at"] or "", reverse=True)
    for f in feed:
        f["role_title"] = ROSTER[f["role"]].title if f["role"] in ROSTER else f["role"]
    out["feed"] = feed[:200]
    return out


# ---------------------------------------------------------------------- máy chủ web
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}


def make_handler(db_path: Path, cfg):
    class Handler(BaseHTTPRequestHandler):
        server_version = "XuongAIMonitor"

        def log_message(self, fmt, *args):  # không in mỗi lượt tải trang
            log.debug(fmt, *args)

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/state":
                try:
                    if not db_path.exists():
                        state = {"office": {"state": "new", "message": "Chưa có dữ liệu. Chạy: python -m xuong_ai run"}}
                    else:
                        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=2)
                        con.row_factory = sqlite3.Row
                        try:
                            state = build_state(con, cfg)
                        finally:
                            con.close()
                    self._send(200, json.dumps(state, ensure_ascii=False).encode(), "application/json; charset=utf-8")
                except Exception as e:  # màn hình không được làm sập văn phòng
                    log.exception("Lỗi dựng trạng thái")
                    self._send(500, json.dumps({"error": str(e)[:200]}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
                return
            name = {"/": "index.html", "/app.css": "app.css", "/app.js": "app.js", "/favicon.svg": "favicon.svg"}.get(path)
            if not name:
                self._send(404, "Không có trang này".encode(), "text/plain; charset=utf-8")
                return
            f = ASSETS / name
            self._send(200, f.read_bytes(), CONTENT_TYPES[f.suffix])

    return Handler


def serve(cfg, port: int = 8765, open_browser: bool = False, background: bool = False):
    """Chạy màn hình theo dõi. Chỉ nghe trên 127.0.0.1."""
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(Path(cfg.db_path), cfg))
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    log.info("Màn hình diễn biến: %s", url)
    if open_browser:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    if background:
        threading.Thread(target=srv.serve_forever, name="monitor", daemon=True).start()
        return srv, url
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return srv, url
