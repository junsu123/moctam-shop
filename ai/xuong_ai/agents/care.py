"""Đề xuất khách đến kỳ mua lại (FR-11) theo nhóm hàng và đơn đã giao. Nhân viên quyết định cách xử lý.

Ước tính chu kỳ cho mỗi (khách, nhóm hàng):
  1. Trung vị khoảng cách giữa các lần mua của chính khách (≥ 2 đơn);
  2. nếu chưa đủ: trung vị khoảng cách của cả nhóm hàng (≥ 5 mẫu);
  3. nếu vẫn chưa đủ: chu kỳ tham khảo của danh mục (repurchase_days do xưởng cấu hình).
Chu kỳ nhân theo số lượng của lần mua cuối (mua 2 hộp ~ dùng gấp đôi thời gian, tối đa ×3).
"""
from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict

from ..store import Store
from . import enqueue


def _d(s: str | None) -> dt.date | None:
    return dt.date.fromisoformat(s[:10]) if s else None


def due_list(store: Store, catalog: dict, today: dt.date | None = None, horizon: int = 7, overdue: int = 21, only_consented: bool = True) -> list[dict]:
    today = today or dt.date.today()
    cat_default = {c["id"]: c.get("repurchase_days") for c in catalog.get("categories", [])}
    rows = store.all(
        """SELECT o.order_id, o.customer_key, o.marketing_consent, COALESCE(o.delivered_at, o.created_at) AS at, i.category_id, SUM(i.qty) AS qty
             FROM orders o JOIN order_items i ON i.order_id = o.order_id
            WHERE o.status = 'delivered' GROUP BY o.order_id, i.category_id ORDER BY at""")
    # đơn đang xử lý (chưa giao) → khách đã mua lại, không nhắc
    open_rows = store.all("SELECT DISTINCT o.customer_key, i.category_id FROM orders o JOIN order_items i ON i.order_id = o.order_id WHERE o.status IN ('pending','confirmed','shipping')")
    in_progress = {(r["customer_key"], r["category_id"]) for r in open_rows}
    consent = {r["customer_key"]: r["marketing_consent"] for r in store.all("SELECT customer_key, marketing_consent FROM orders ORDER BY version")}

    hist: dict[tuple[str, int], list[tuple[dt.date, int]]] = defaultdict(list)
    for r in rows:
        hist[(r["customer_key"], r["category_id"])].append((_d(r["at"]), r["qty"]))
    cat_gaps: dict[int, list[int]] = defaultdict(list)
    for (ck, cat), h in hist.items():
        for (a, _), (b, _) in zip(h, h[1:]):
            if (b - a).days > 0:
                cat_gaps[cat].append((b - a).days)

    out = []
    for (ck, cat), h in hist.items():
        if (ck, cat) in in_progress:
            continue
        if only_consented and not consent.get(ck):
            continue
        own = [(b - a).days for (a, _), (b, _) in zip(h, h[1:]) if (b - a).days > 0]
        if len(own) >= 1:
            base, basis, conf = statistics.median(own), "chu kỳ của chính khách", 0.9 if len(own) >= 2 else 0.7
        elif len(cat_gaps[cat]) >= 5:
            base, basis, conf = statistics.median(cat_gaps[cat]), "chu kỳ trung vị của nhóm hàng", 0.55
        elif cat_default.get(cat):
            base, basis, conf = cat_default[cat], "chu kỳ tham khảo của danh mục", 0.4
        else:
            continue
        last, qty = h[-1]
        interval = base * max(1, min(3, qty))
        due = last + dt.timedelta(days=round(interval))
        if not (today - dt.timedelta(days=overdue) <= due <= today + dt.timedelta(days=horizon)):
            continue
        out.append({
            "customer_key": ck, "category_id": cat, "last_order_at": f"{last.isoformat()} 00:00:00", "due_date": due.isoformat(),
            "score": round(conf, 2), "reason": f"Lần mua cuối {last.strftime('%d/%m')} ({qty} sp), {basis} ≈ {round(base)} ngày",
        })
    out.sort(key=lambda x: x["due_date"])
    return out


def run(store: Store, cfg, catalog: dict) -> dict:
    entries = due_list(store, catalog, horizon=cfg.care_horizon_days, overdue=cfg.care_overdue_days, only_consented=cfg.care_only_consented)
    if not entries:
        return {"entries": 0, "queued": 0}
    batch = "care-" + dt.date.today().strftime("%Y%m%d")
    q = enqueue(store, batch, "care_list", {"batch_id": batch, "entries": entries})
    return {"entries": len(entries), "queued": int(q), "batch": batch}
