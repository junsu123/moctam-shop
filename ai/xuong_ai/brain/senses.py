"""Giác quan của bộ não: đọc dữ liệu cục bộ (không có tên/SĐT/địa chỉ khách) thành TÍN HIỆU và VIỆC CẦN NGƯỜI.

Chỉ đọc, không gọi mạng, không gọi LLM — chạy mỗi phút cũng rẻ.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from ..agents import care, content, crosssell
from ..memory import Memory, question_type
from . import learning
from .model import Escalation, Signal, fmt, local, parse

ROUTINE = {  # việc định kỳ: (nhân viên, mức ưu tiên khi đến hạn)
    "sync": ("thu_ky", 1.0),
    "catalog": ("thu_ky", 0.7),
    "feedback": ("thu_ky", 0.6),
    "maintenance": ("ky_thuat", 0.3),
}
LABEL_FIELDS = {"ingredients": "thành phần", "usage_guide": "cách dùng", "storage_guide": "bảo quản", "allergens": "dị ứng"}
QTYPE_LABEL = {"giao_hang": "giao hàng", "thanh_toan": "thanh toán", "doi_tra": "đổi trả", "bao_quan": "bảo quản", "cach_dung": "cách dùng",
               "di_ung": "dị ứng / sức khỏe", "uu_dai": "ưu đãi", "khac": "khác"}


@dataclass
class Ctx:
    store: object
    cfg: object
    llm: object
    catalog: dict
    now: dt.datetime
    facts: dict = field(default_factory=dict)

    @property
    def today(self) -> dt.date:
        return local(self.now).date()


def perceive(ctx: Ctx) -> tuple[list[Signal], list[Escalation]]:
    sig: list[Signal] = []
    esc: list[Escalation] = []
    for fn in (_routine, _health, _questions, _products, _sales, _care, _crosssell, _review):
        fn(ctx, sig, esc)
    sig.sort(key=lambda s: -s.severity)
    esc.sort(key=lambda e: -e.severity)
    return sig, esc


# ---------------------------------------------------------------------------------- việc định kỳ & sức khỏe
def _job(ctx, name):
    return ctx.store.one("SELECT * FROM jobs WHERE name = ?", (name,))


def _routine(ctx, sig, esc):
    now = fmt(ctx.now)
    for name, (role, sev) in ROUTINE.items():
        j = _job(ctx, name)
        if j is None or (j["next_run"] or "") <= now:
            last = j["last_run"] if j else None
            sig.append(Signal(f"due:{name}", "routine", "van_hanh", sev,
                              f"Đến lịch {name}" + (f" (lần trước {last} UTC)" if last else " (chưa chạy lần nào)"), {"role": role}))
    q = ctx.store.one("SELECT COUNT(*) n FROM outbox WHERE status = 'queued'")["n"]
    if q:
        sig.append(Signal("outbox", "routine", "van_hanh", 0.8, f"{q} bản nháp đã soạn nhưng chưa gửi được lên website", {"role": "thu_ky", "n": q}))


def _health(ctx, sig, esc):
    j = _job(ctx, "sync")
    fails = j["failures"] if j else 0
    ctx.facts["site_ok"] = fails == 0
    ctx.facts["sync_last_ok"] = j["last_run"] if j and fails == 0 else None
    if fails >= 3:
        esc.append(Escalation("site_unreachable", "van_hanh", 0.9, f"Không kết nối được API đồng bộ của website ({fails} lần liên tiếp)",
                              f"Lỗi gần nhất: {(j['last_error'] or '')[:200]}. Kiểm tra website có mở được không, khóa API còn hiệu lực không, "
                              "máy này có mạng không. Văn phòng tạm gác mọi việc cần website và tự thử lại."))
    for r in ctx.store.all("SELECT name, failures, last_error FROM jobs WHERE name <> 'sync' AND failures >= 3"):
        esc.append(Escalation(f"job_failing:{r['name']}", "van_hanh", 0.5, f"Việc '{r['name']}' lỗi {r['failures']} lần liên tiếp", (r["last_error"] or "")[:300]))
    since = fmt(ctx.now - dt.timedelta(hours=24))
    for r in ctx.store.all("SELECT action, COUNT(*) n, MAX(error) e FROM brain_tasks WHERE status = 'failed' AND started_at >= ? "
                           "AND action NOT IN ('sync','catalog','feedback','maintenance') GROUP BY action HAVING n >= 3", (since,)):
        esc.append(Escalation(f"task_failing:{r['action']}", "van_hanh", 0.5, f"Việc '{r['action']}' thất bại {r['n']} lần trong 24 giờ", (r["e"] or "")[:300]))
    if ctx.llm.available():
        last = ctx.store.all("SELECT ok FROM llm_usage ORDER BY id DESC LIMIT 3")
        if len(last) == 3 and not any(r["ok"] for r in last):
            esc.append(Escalation("llm_error", "van_hanh", 0.5, "3 lượt gọi LLM gần nhất đều lỗi",
                                  "Kiểm tra api_key, tên model và số dư tài khoản nhà cung cấp LLM. Các việc không cần LLM vẫn chạy."))
    ctx.facts["llm"] = {"available": ctx.llm.available(), **ctx.llm.usage_today(),
                        "max_calls": ctx.llm.cfg.max_calls_per_day, "max_cost_usd": ctx.llm.cfg.max_cost_per_day_usd}


# ---------------------------------------------------------------------------------- khách hỏi chưa có câu trả lời
def _questions(ctx, sig, esc):
    qs = ctx.catalog.get("unanswered_questions", [])
    if not qs:
        return
    mem = Memory(ctx.store)
    bcfg = ctx.cfg.brain
    human = set(bcfg.human_only_question_types)
    covered = 0
    for c in content.cluster_questions(qs):
        q, n = c["rep"], c["n"]
        qt = question_type(q)
        hits = mem.search(q, kinds=("faq",), statuses=("approved", "pending"), qtype=qt)
        if hits and hits[0][1] >= ctx.cfg.faq_threshold:
            covered += 1  # đã có FAQ (hoặc bản nháp đang chờ duyệt) đủ khớp
            continue
        base = content.faq_ref(q)
        h = base.rsplit(":", 1)[-1]
        variants = "; ".join(f"“{v}”" for v in c["variants"][:3])
        if qt in human:
            esc.append(Escalation(f"faq_human:{h}", "tra_loi_khach", min(0.9, 0.5 + 0.05 * n),
                                  f"Khách hỏi về {QTYPE_LABEL.get(qt, qt)} ({n} lần) — chỉ người được trả lời",
                                  f"Câu hỏi: {variants}. Nội quy văn phòng không để AI soạn câu trả lời loại này. "
                                  "Hãy viết FAQ trong Quản trị → Blog/FAQ dựa trên nhãn sản phẩm thật."))
            continue
        tried = learning.attempts(ctx.store, base)
        if tried >= bcfg.max_ai_attempts:
            esc.append(Escalation(f"faq_retry:{h}", "tra_loi_khach", 0.5, f"FAQ cho câu hỏi khách bị từ chối {tried} lần — cần người viết",
                                  f"Câu hỏi: {variants}. Góp ý của người duyệt đã được dùng nhưng bản nháp vẫn chưa đạt."))
            continue
        sev = min(1.0, 0.35 + 0.65 * math.log1p(n) / math.log1p(30))
        sig.append(Signal(f"faq_gap:{h}", "faq_gap", "tra_loi_khach", round(sev, 3),
                          f"{n} lượt hỏi chưa có câu trả lời: “{q}”" + (f" (lần soạn thứ {tried + 1})" if tried else ""),
                          {"cluster": c, "qtype": qt, "attempt": tried + 1, "ref_base": base}))
    ctx.facts["questions"] = {"asked": sum(int(x.get("n", 1)) for x in qs), "clusters_covered": covered}


# ---------------------------------------------------------------------------------- sản phẩm: nhãn & nội dung
def _products(ctx, sig, esc):
    products = ctx.catalog.get("products", [])
    if not products:
        return
    rev = {r["product_id"]: r["rev"] for r in ctx.store.all(
        "SELECT i.product_id, SUM(i.qty * i.unit_price) rev FROM orders o JOIN order_items i ON i.order_id = o.order_id "
        "WHERE o.status NOT IN ('cancelled','returned') AND o.created_at >= ? GROUP BY i.product_id", (fmt(ctx.now - dt.timedelta(days=90)),))}
    top = max(rev.values(), default=0) or 1
    has_blog = {b.get("product_id") for b in ctx.catalog.get("published_blogs", []) if b.get("product_id")}
    missing = []
    for p in products:
        gaps = [label for f, label in LABEL_FIELDS.items() if not (p.get(f) or "").strip()]
        if gaps:
            missing.append(f"{p['name']} (thiếu {', '.join(gaps)})")
        if p["id"] in has_blog:
            continue
        base = content.blog_ref(p)
        if ctx.store.one("SELECT 1 FROM knowledge WHERE kind = 'blog_outline' AND status <> 'retired' AND (source_ref = ? OR source_ref LIKE ?)",
                         (base, base + ":r%")):
            continue  # đã có bản nháp cho đúng phiên bản nhãn này
        tried = learning.attempts(ctx.store, base)
        if tried >= ctx.cfg.brain.max_ai_attempts:
            esc.append(Escalation(f"blog_retry:{p['id']}", "noi_dung_seo", 0.3, f"Bài blog cho “{p['name']}” bị từ chối {tried} lần — nên tự viết",
                                  "Hoặc chỉnh lời dặn của biên tập SEO (agents/content.py) theo góp ý của người duyệt."))
            continue
        share = rev.get(p["id"], 0) / top
        sig.append(Signal(f"blog_gap:{p['id']}", "blog_gap", "noi_dung_seo", round(0.25 + 0.55 * share, 3),
                          f"“{p['name']}” chưa có bài blog" + (" — đang bán chạy" if share >= 0.5 else "")
                          + (f" (lần soạn thứ {tried + 1}, theo góp ý)" if tried else ""),
                          {"product_id": p["id"], "info_version": p["info_version"], "attempt": tried + 1, "ref_base": base, "revenue_90d": rev.get(p["id"], 0)}))
    if missing:
        sev = 0.6 if any("dị ứng" in m for m in missing) else 0.4
        esc.append(Escalation("label_gap", "tra_loi_khach", sev, f"{len(missing)} sản phẩm thiếu thông tin nhãn",
                              "AI không được tự bịa thông tin nhãn; chat và bài viết sẽ thiếu câu trả lời cho các mục này. "
                              "Bổ sung trong Quản trị → Sản phẩm: " + "; ".join(missing[:8]) + (" …" if len(missing) > 8 else "")))


# ---------------------------------------------------------------------------------- bán hàng
def _pois_cdf(k: int, lam: float) -> float:
    term = total = math.exp(-lam)
    for i in range(1, k + 1):
        term *= lam / i
        total += term
    return min(1.0, total)


def _sales(ctx, sig, esc):
    now = ctx.now
    rows = ctx.store.all("SELECT status, payment_status, created_at, total FROM orders WHERE created_at >= ?", (fmt(now - dt.timedelta(days=60)),))
    orders = [(parse(r["created_at"]), r["status"], r["payment_status"], r["total"] or 0) for r in rows]
    last24 = sum(1 for t, *_ in orders if t and t > now - dt.timedelta(hours=24))
    daily = [sum(1 for t, *_ in orders if t and now - dt.timedelta(days=d + 1) < t <= now - dt.timedelta(days=d)) for d in range(1, 29)]
    first = ctx.store.one("SELECT MIN(created_at) m FROM orders")["m"]
    trimmed = sorted(daily)[3:-3]
    lam = sum(trimmed) / len(trimmed) if trimmed else 0.0
    week = [o for o in orders if o[0] and o[0] > now - dt.timedelta(days=7) and o[1] not in ("cancelled",)]
    sync_fresh = ctx.facts.get("sync_last_ok") and parse(ctx.facts["sync_last_ok"]) > now - dt.timedelta(hours=2)
    enough = bool(first and parse(first) < now - dt.timedelta(days=14) and lam >= 1.5)
    ctx.facts["sales"] = {"orders_24h": last24, "baseline_per_day": round(lam, 1), "enough_history": enough,
                          "orders_7d": len(week), "revenue_7d": sum(o[3] for o in week)}
    if sync_fresh and enough:
        p_low = _pois_cdf(last24, lam)
        if p_low < 0.01:  # ~1 lần báo nhầm mỗi 100 ngày
            esc.append(Escalation("sales_drop", "van_hanh", round(min(0.95, 0.7 + 0.25 * (1 - last24 / lam)), 2),
                                  f"Đơn 24 giờ qua thấp bất thường: {last24} đơn (bình thường khoảng {lam:.1f} đơn/ngày)",
                                  f"Xác suất ngẫu nhiên chỉ {p_low:.2%}. Thử đặt một đơn trên website, kiểm tra trang thanh toán/VietQR, "
                                  "tồn kho mặt hàng bán chạy và quảng cáo đang chạy."))
        elif last24 >= lam + 5 and 1 - _pois_cdf(last24 - 1, lam) < 0.001:
            ctx.facts.setdefault("notes", []).append(
                f"Đơn 24 giờ qua tăng mạnh: {last24} đơn (bình thường ~{lam:.1f}). Kiểm tra tồn kho mặt hàng bán chạy; nếu đơn lạ, xem có bị đặt ảo không.")
    elif not enough:
        ctx.facts.setdefault("notes", []).append("Chưa đủ lịch sử đơn (≥ 14 ngày, ≥ 1,5 đơn/ngày) để phát hiện bán hàng bất thường.")
    # tỷ lệ hủy: [8..2] ngày trước so với [60..9] ngày trước (đơn mới có thể còn chờ hết hạn)
    rec = [o for o in orders if o[0] and now - dt.timedelta(days=8) < o[0] <= now - dt.timedelta(days=2)]
    old = [o for o in orders if o[0] and o[0] <= now - dt.timedelta(days=9)]
    rc = sum(1 for o in rec if o[1] == "cancelled")
    base_rate = (sum(1 for o in old if o[1] == "cancelled") / len(old)) if len(old) >= 20 else 0.1
    if rc >= 3 and rec and rc / len(rec) >= max(0.15, 2 * base_rate):
        esc.append(Escalation("cancel_rate", "van_hanh", 0.6, f"Tỷ lệ hủy tăng: {rc}/{len(rec)} đơn ({rc / len(rec):.0%}, bình thường {base_rate:.0%})",
                              "Xem lý do hủy ở Quản trị → Đơn hàng: phí giao, chuyển khoản VietQR quá hạn, hay khách đặt nhầm?"))
    stuck_p = sum(1 for o in orders if o[1] == "pending" and o[0] and o[0] < now - dt.timedelta(hours=72))
    if stuck_p:
        esc.append(Escalation("stuck_pending", "van_hanh", 0.7, f"{stuck_p} đơn chờ xác nhận quá 3 ngày",
                              "Tác vụ hết hạn đơn (bin/cron.php) có thể không chạy, hoặc đơn bị đánh dấu cần xem lại. Kiểm tra trang Giám sát."))
    stuck_c = sum(1 for o in orders if o[1] == "confirmed" and o[0] and o[0] < now - dt.timedelta(days=5))
    if stuck_c:
        esc.append(Escalation("stuck_confirmed", "van_hanh", 0.6, f"{stuck_c} đơn đã xác nhận nhưng chưa bàn giao sau 5 ngày", "Xem Quản trị → Đơn hàng, lọc 'Đã xác nhận'."))
    pay = sum(1 for o in orders if o[2] in ("overpaid", "partial") and o[1] not in ("cancelled", "returned"))
    if pay:
        esc.append(Escalation("payment_attention", "van_hanh", 0.4, f"{pay} đơn chuyển khoản thiếu/thừa chưa xử lý", "Xem Quản trị → Đối soát → Sai lệch."))


# ---------------------------------------------------------------------------------- khách cũ & mua kèm
def care_sent_recently(store, now: dt.datetime, days: int = 30) -> set:
    return {(r["customer_key"], r["category_id"]) for r in store.all(
        "SELECT customer_key, category_id FROM brain_care_sent WHERE sent_at >= ?", (fmt(now - dt.timedelta(days=days)),))}


def care_entries(ctx) -> list[dict]:
    c = ctx.cfg
    entries = care.due_list(ctx.store, ctx.catalog, today=ctx.today, horizon=c.care_horizon_days, overdue=c.care_overdue_days, only_consented=c.care_only_consented)
    sent = care_sent_recently(ctx.store, ctx.now)
    return [e for e in entries if (e["customer_key"], e["category_id"]) not in sent]


def _care(ctx, sig, esc):
    if not ctx.catalog.get("categories"):
        return
    entries = care_entries(ctx)
    bl = learning.backlog(ctx.store)
    if int(bl.get("care") or 0) > ctx.cfg.brain.care_backlog_cap:
        esc.append(Escalation("care_backlog", "giu_chan", 0.4, f"{bl['care']} khách trong danh sách chăm sóc chưa được liên hệ",
                              "Văn phòng ngừng gửi danh sách mới cho tới khi nhân viên xử lý bớt (Quản trị → Chăm sóc lại)."))
        return
    if entries:
        sig.append(Signal("care_due", "care_due", "giu_chan", round(min(1.0, 0.3 + len(entries) / 30), 3),
                          f"{len(entries)} khách đã đồng ý nhận tin đến kỳ mua lại", {"n": len(entries)}))


def _crosssell(ctx, sig, esc):
    pairs = crosssell.new_pairs(ctx.store, ctx.cfg.crosssell_min_support, ctx.cfg.crosssell_max_per_product)
    if pairs:
        sig.append(Signal("crosssell_new", "crosssell_new", "gia_tri_don", round(0.3 + min(0.5, 0.1 * len(pairs)), 3),
                          f"Có {len(pairs)} cặp sản phẩm mới hay được mua cùng nhau", {"n": len(pairs)}))


def _review(ctx, sig, esc):
    bl = learning.backlog(ctx.store)
    ctx.facts["backlog"] = bl
    old = parse(bl.get("oldest_pending_at"))
    n = learning.pending_review_items(bl)
    if old and n and old < ctx.now - dt.timedelta(days=7):
        esc.append(Escalation("review_backlog", "tra_loi_khach", 0.4, f"{n} bản nháp AI chờ duyệt, lâu nhất {(ctx.now - old).days} ngày",
                              "Duyệt hoặc từ chối (kèm góp ý) trong Quản trị → Blog/FAQ và Gợi ý mua kèm. Văn phòng chỉ soạn thêm khi còn dưới "
                              f"{ctx.cfg.brain.max_pending_review} bản chờ duyệt."))
