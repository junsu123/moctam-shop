"""Học từ phản hồi: nhân viên duyệt, sửa hay từ chối bản nháp nào, vì sao.

- Độ tin cậy của từng loại việc = trung bình phân phối Beta trên kết quả duyệt 90 ngày gần nhất
  (duyệt nguyên văn = 1, sửa rồi duyệt = 0,6, từ chối/gỡ = 0). Chưa có dữ liệu → 0,5.
- Góp ý khi từ chối/sửa được đưa vào lần soạn sau (bộ não "nhớ" yêu cầu của người duyệt).
- Bản nháp bị từ chối → tri thức chờ duyệt tương ứng bị loại, để khoảng trống được soạn lại (có góp ý),
  tối đa max_ai_attempts lần rồi chuyển người viết.
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from ..agents import site_ref
from ..client import SiteError
from ..textnorm import redact
from .model import fmt

log = logging.getLogger("xuong_ai.brain.learning")

WEIGHT = {"approved": (1.0, 0.0), "edited": (0.6, 0.4), "rejected": (0.0, 1.0), "retracted": (0.0, 1.0)}
KIND_LABEL = {"faq": "FAQ", "blog": "Bài blog", "cross_sell": "Gợi ý mua kèm", "care_list": "Danh sách chăm sóc"}


def ingest(store, items: list[dict], now: dt.datetime) -> dict:
    """Ghi kết quả duyệt; trả số mục đổi trạng thái theo từng loại."""
    changed: dict[str, int] = {}
    t = fmt(now)
    with store.tx() as db:
        for it in items:
            ref = it.get("client_ref")
            if not ref:
                continue
            st = it.get("status") or "pending"
            cur = db.execute("SELECT status FROM brain_feedback WHERE client_ref = ?", (ref,)).fetchone()
            if cur and cur["status"] == st:
                continue
            db.execute(
                "INSERT INTO brain_feedback(client_ref, kind, status, note, received_at, reviewed_at, updated_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(client_ref) DO UPDATE SET status=excluded.status, note=excluded.note, reviewed_at=excluded.reviewed_at, updated_at=excluded.updated_at",
                (ref, it.get("kind"), st, (it.get("note") or None), it.get("received_at"), it.get("reviewed_at"), t))
            changed[st] = changed.get(st, 0) + 1
            if st in ("rejected", "retracted", "invalid", "gone"):
                # Bản nháp không được dùng → bỏ khỏi bộ nhớ "đang chờ duyệt" để khoảng trống mở lại
                db.execute("UPDATE knowledge SET status='retired', updated_at=datetime('now') WHERE source_ref = ? AND status = 'pending'", (ref,))
    return changed


def ingest_outbox(store, now: dt.datetime) -> dict:
    """Bản nháp bị chính website từ chối khi nhận (vd SOURCE_OUTDATED) cũng là phản hồi."""
    items = []
    for r in store.all("SELECT o.client_ref, o.kind, o.result FROM outbox o LEFT JOIN brain_feedback f ON f.client_ref = o.client_ref "
                       "WHERE o.status = 'rejected' AND f.client_ref IS NULL"):
        try:
            note = json.loads(r["result"] or "{}").get("error")
        except ValueError:
            note = r["result"]
        items.append({"client_ref": r["client_ref"], "kind": r["kind"], "status": "invalid", "note": note})
    return ingest(store, items, now) if items else {}


def pull(store, client, catalog: dict | None, now: dt.datetime) -> dict:
    """Thư ký dữ liệu lấy kết quả duyệt từ website. Website bản cũ (chưa có API) → suy ra từ FAQ đã xuất bản."""
    try:
        fb = client.feedback()
        backlog = fb.get("backlog") or {}
        backlog["fetched_at"] = fmt(now)
        store.set("brain.backlog", json.dumps(backlog))
        # Website lưu client_ref đã lọc ký tự → đổi về mã cục bộ để khớp tri thức và bộ đếm số lần thử
        local = {site_ref(r["client_ref"]): r["client_ref"] for r in store.all("SELECT client_ref FROM outbox")}
        items = [{**it, "client_ref": local.get(it.get("client_ref") or "", it.get("client_ref"))} for it in fb.get("items", [])]
        res = {"changed": ingest(store, items, now), "backlog": backlog, "source": "api"}
    except SiteError as e:
        if e.status != 404:
            raise
        published = {f["id"] for f in (catalog or {}).get("published_faqs", [])}
        items = []
        for r in store.all("SELECT client_ref, kind, result FROM outbox WHERE status='accepted' AND kind='faq'"):
            try:
                rid = json.loads(r["result"] or "{}").get("result", "")
            except ValueError:
                rid = ""
            if rid.startswith("content:") and int(rid[8:] or 0) in published:
                items.append({"client_ref": r["client_ref"], "kind": "faq", "status": "approved"})
        res = {"changed": ingest(store, items, now), "source": "suy_luan_tu_catalog"}
    res["outbox"] = ingest_outbox(store, now)
    return res


def backlog(store) -> dict:
    """Số bản nháp đang chờ nhân viên duyệt (lần lấy phản hồi gần nhất) + bản nháp mới gửi sau đó."""
    raw = store.get("brain.backlog")
    b = json.loads(raw) if raw else {}
    since = b.get("fetched_at") or "1970-01-01 00:00:00"
    fresh = store.all("SELECT kind, COUNT(*) n FROM outbox WHERE created_at >= ? AND status IN ('queued','accepted') GROUP BY kind", (since,))
    for r in fresh:
        if r["kind"] != "care_list":  # số khách của danh sách mới chỉ biết ở lần lấy phản hồi sau
            b[r["kind"]] = int(b.get(r["kind"]) or 0) + r["n"]
    b["known"] = bool(raw)
    return b


def pending_review_items(b: dict) -> int:
    # Một danh sách chăm sóc tính là 1 việc duyệt; số khách trong danh sách xét riêng bằng care_backlog_cap
    return int(b.get("faq") or 0) + int(b.get("blog") or 0) + int(b.get("cross_sell") or 0)


def reliability(store, kind: str, now: dt.datetime, days: int = 90) -> dict:
    a, b, n = 1.0, 1.0, {"approved": 0, "edited": 0, "rejected": 0, "retracted": 0}
    for r in store.all("SELECT status, COUNT(*) c FROM brain_feedback WHERE kind = ? AND updated_at >= ? GROUP BY status",
                       (kind, fmt(now - dt.timedelta(days=days)))):
        if r["status"] in WEIGHT:
            wa, wb = WEIGHT[r["status"]]
            a += wa * r["c"]
            b += wb * r["c"]
            n[r["status"]] += r["c"]
    return {"mean": a / (a + b), "reviewed": sum(n.values()), **n}


def attempts(store, ref_base: str) -> int:
    """Số lần bản nháp cho cùng một khoảng trống đã bị từ chối/không dùng được."""
    return store.one("SELECT COUNT(*) n FROM brain_feedback WHERE (client_ref = ? OR client_ref LIKE ?) AND status IN ('rejected','retracted')",
                     (ref_base, ref_base + ":r%"))["n"]


def guidance(store, kind: str, limit: int = 4) -> list[str]:
    """Góp ý gần nhất của người duyệt cho loại bản nháp này (từ chối hoặc sửa)."""
    out, seen = [], set()
    for r in store.all("SELECT note FROM brain_feedback WHERE kind = ? AND status IN ('rejected','edited') AND note IS NOT NULL AND note <> '' "
                       "ORDER BY updated_at DESC LIMIT 20", (kind,)):
        n = redact(r["note"]).strip()[:200]
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
        if len(out) >= limit:
            break
    return out


def lessons(store, now: dt.datetime) -> list[str]:
    """Điều văn phòng rút ra được, viết cho chủ xưởng đọc."""
    out = []
    for kind, label in KIND_LABEL.items():
        r = reliability(store, kind, now)
        notes = guidance(store, kind, 3)
        if r["reviewed"] < 3:
            if notes:
                out.append(f"Góp ý gần đây cho {label.lower()} (đã đưa vào lần soạn sau): " + "; ".join(f"“{n}”" for n in notes))
            continue
        ok = r["approved"] + r["edited"]
        line = f"{label}: {ok}/{r['reviewed']} bản được dùng ({r['approved']} nguyên văn, {r['edited']} có sửa), độ tin cậy {r['mean']:.0%}."
        if r["mean"] < 0.35:
            line += " Văn phòng đã tự giảm ưu tiên loại việc này; nên xem lại góp ý bên dưới hoặc chỉnh lời dặn cho AI."
        elif r["edited"] > r["approved"]:
            line += " Phần lớn phải sửa trước khi đăng — góp ý của người duyệt đang được đưa vào lần soạn sau."
        out.append(line)
        if notes:
            out.append(f"  Góp ý gần đây cho {label.lower()}: " + "; ".join(f"“{n}”" for n in notes))
    hits = store.one("SELECT COUNT(*) n, COALESCE(SUM(hit),0) h FROM memory_hits WHERE day >= date('now','-30 day')")
    if hits["n"] >= 5:
        out.append(f"Bộ nhớ trả lời được {hits['h'] / hits['n']:.0%} câu hỏi mà không cần gọi LLM (30 ngày, {hits['n']} lượt xét).")
    inv = store.one("SELECT COUNT(*) n FROM brain_feedback WHERE status='invalid' AND updated_at >= ?", (fmt(now - dt.timedelta(days=30)),))["n"]
    if inv:
        out.append(f"{inv} bản nháp bị website từ chối khi nhận (thường do thông tin nhãn đổi sau khi soạn) — đã tự soạn lại theo nhãn mới.")
    return out
