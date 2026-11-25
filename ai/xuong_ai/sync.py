"""Đồng bộ dữ liệu tối thiểu từ website (đặc tả §5.3, AT-08).

- Con trỏ chỉ được cập nhật SAU KHI ghi thành công cả lô (cùng một giao dịch SQLite).
- Sự kiện trùng bị bỏ qua theo event_id.
- Payload là trạng thái đơn kèm version (= seq); chỉ áp dụng khi version mới hơn bản đang có,
  nên nhận lại sự kiện cũ hoặc phát lại sau bản chụp đều an toàn.
- Con trỏ hết hiệu lực (410 CURSOR_EXPIRED) → tải lại bản chụp với mốc as_of_seq tương ứng.
"""
from __future__ import annotations

import logging

from .client import SiteClient, SiteError
from .store import Store

log = logging.getLogger("xuong_ai.sync")


def _upsert_order(db, p: dict) -> bool:
    cur = db.execute("SELECT version FROM orders WHERE order_id = ?", (p["order_id"],)).fetchone()
    if cur and cur["version"] >= p["version"]:
        return False
    db.execute(
        """INSERT INTO orders(order_id, code, status, payment_method, payment_status, customer_key, marketing_consent, zone_id,
                              goods_subtotal, total, voucher_code, created_at, delivered_at, version)
           VALUES(:order_id, :code, :status, :payment_method, :payment_status, :customer_key, :marketing_consent, :zone_id,
                  :goods_subtotal, :total, :voucher_code, :created_at, :delivered_at, :version)
           ON CONFLICT(order_id) DO UPDATE SET code=excluded.code, status=excluded.status, payment_method=excluded.payment_method,
             payment_status=excluded.payment_status, customer_key=excluded.customer_key, marketing_consent=excluded.marketing_consent,
             zone_id=excluded.zone_id, goods_subtotal=excluded.goods_subtotal, total=excluded.total, voucher_code=excluded.voucher_code,
             created_at=excluded.created_at, delivered_at=excluded.delivered_at, version=excluded.version""",
        {**p, "marketing_consent": 1 if p.get("marketing_consent") else 0},
    )
    db.execute("DELETE FROM order_items WHERE order_id = ?", (p["order_id"],))
    db.executemany(
        "INSERT INTO order_items(order_id, sku_id, product_id, category_id, qty, unit_price) VALUES(?,?,?,?,?,?)",
        [(p["order_id"], i["sku_id"], i["product_id"], i["category_id"], i["qty"], i["unit_price"]) for i in p.get("items", [])],
    )
    return True


def _upsert_product(db, p: dict, version: int) -> bool:
    cur = db.execute("SELECT version, info_version FROM products WHERE product_id = ?", (p["product_id"],)).fetchone()
    if cur and cur["version"] >= version:
        return False
    db.execute(
        """INSERT INTO products(product_id, category_id, status, info_version, version) VALUES(?,?,?,?,?)
           ON CONFLICT(product_id) DO UPDATE SET category_id=excluded.category_id, status=excluded.status, info_version=excluded.info_version, version=excluded.version""",
        (p["product_id"], p.get("category_id"), p.get("status"), p.get("info_version"), version),
    )
    # Thông tin nhãn đổi → ngừng dùng tri thức dựa trên phiên bản cũ
    if cur and cur["info_version"] is not None and p.get("info_version") != cur["info_version"]:
        db.execute(
            "UPDATE knowledge SET status = 'retired', updated_at = datetime('now') WHERE product_id = ? AND status <> 'retired' AND source_version <> ?",
            (p["product_id"], str(p.get("info_version"))),
        )
    return True


def apply_batch(store: Store, events: list[dict], next_cursor: int) -> dict:
    """Áp dụng một lô và dời con trỏ trong CÙNG giao dịch. Trả thống kê."""
    stats = {"received": len(events), "applied": 0, "duplicates": 0, "stale": 0}
    with store.tx() as db:
        for ev in events:
            ins = db.execute("INSERT OR IGNORE INTO processed_events(event_id, seq) VALUES(?, ?)", (ev["event_id"], ev["seq"]))
            if ins.rowcount == 0:
                stats["duplicates"] += 1
                continue
            p = ev["payload"]
            if ev["entity_type"] == "order":
                changed = _upsert_order(db, p)
            elif ev["entity_type"] == "product":
                changed = _upsert_product(db, p, p.get("version", ev["seq"]))
            else:
                changed = False
            stats["applied" if changed else "stale"] += 1
        old = int(store.get("cursor", "0"))
        store.set("cursor", max(old, int(next_cursor)))
    return stats


def load_snapshot(store: Store, client: SiteClient, page_size: int = 500) -> dict:
    """Tải lại toàn bộ đơn; đặt con trỏ = as_of_seq của trang đầu. Thay thế nguyên khối."""
    first = client.snapshot(0, page_size)
    as_of = first["as_of_seq"]
    pages = [first]
    nxt = first.get("next_after_id")
    while nxt:
        pg = client.snapshot(nxt, page_size)
        if not pg["orders"]:
            break
        pages.append(pg)
        nxt = pg.get("next_after_id")
    n = 0
    with store.tx() as db:
        db.execute("DELETE FROM order_items")
        db.execute("DELETE FROM orders")
        db.execute("DELETE FROM processed_events")
        for pg in pages:
            for o in pg["orders"]:
                _upsert_order(db, o)
                n += 1
        for p in first.get("products", []):
            db.execute(
                "INSERT INTO products(product_id, category_id, status, info_version, version) VALUES(?,?,?,?,0) "
                "ON CONFLICT(product_id) DO UPDATE SET category_id=excluded.category_id, status=excluded.status, info_version=excluded.info_version",
                (p["product_id"], p["category_id"], p["status"], p["info_version"]),
            )
        store.set("cursor", as_of)
        store.set("snapshot_at_seq", as_of)
    log.info("Đã tải bản chụp %s đơn, con trỏ = %s", n, as_of)
    return {"orders": n, "as_of_seq": as_of}


def sync(store: Store, client: SiteClient, max_batches: int = 50) -> dict:
    """Kéo sự kiện cho tới khi hết. Mất kết nối giữa chừng → các lô đã ghi vẫn giữ, con trỏ đúng."""
    if store.get("cursor") is None:
        snap = load_snapshot(store, client)
        total = {"snapshot": snap, "batches": 0, "applied": 0, "duplicates": 0, "stale": 0}
    else:
        total = {"batches": 0, "applied": 0, "duplicates": 0, "stale": 0}
    for _ in range(max_batches):
        cursor = int(store.get("cursor", "0"))
        try:
            res = client.events(cursor)
        except SiteError as e:
            if e.code == "CURSOR_EXPIRED":
                log.warning("Con trỏ %s hết hiệu lực, tải lại bản chụp", cursor)
                total["snapshot"] = load_snapshot(store, client)
                continue
            raise
        st = apply_batch(store, res["events"], res["next_cursor"])
        total["batches"] += 1
        for k in ("applied", "duplicates", "stale"):
            total[k] += st[k]
        if not res.get("has_more"):
            break
    total["cursor"] = int(store.get("cursor", "0"))
    return total
