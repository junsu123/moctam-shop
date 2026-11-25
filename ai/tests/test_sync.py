"""AT-08: Python mất kết nối rồi nhận lại một lô có cập nhật đơn cũ và sự kiện trùng."""
import pytest

from xuong_ai import sync as S
from xuong_ai.client import SiteError
from xuong_ai.store import Store


def order(oid, status, version, items=((1, 10, 1, 2, 50000),), key="ck1", consent=True, delivered=None):
    return {"order_id": oid, "code": f"TM{oid}", "status": status, "payment_method": "cod", "payment_status": "unpaid",
            "customer_key": key, "marketing_consent": consent, "zone_id": 1, "goods_subtotal": 100000, "voucher_code": None,
            "total": 120000, "created_at": "2026-11-01 10:00:00", "delivered_at": delivered, "version": version,
            "items": [{"sku_id": s, "product_id": p, "category_id": c, "qty": q, "unit_price": u} for s, p, c, q, u in items]}


def ev(seq, payload, eid=None):
    return {"seq": seq, "event_id": eid or f"E{seq:04d}", "entity_type": "order", "entity_id": payload["order_id"], "event_type": "x", "payload": payload, "created_at": ""}


class FakeSite:
    def __init__(self, log, snapshot_orders=(), as_of=0, pruned_through=0):
        self.log, self.snap, self.as_of, self.pruned = list(log), list(snapshot_orders), as_of, pruned_through
        self.fail_on_call = None
        self.calls = 0

    def events(self, after, limit=2):
        self.calls += 1
        if self.fail_on_call == self.calls:
            raise SiteError(0, "NETWORK", "mất kết nối")
        if after < self.pruned:
            raise SiteError(410, "CURSOR_EXPIRED", "hết hạn")
        rows = [e for e in self.log if e["seq"] > after][: limit + 1]
        more = len(rows) > limit
        rows = rows[:limit]
        return {"events": rows, "next_cursor": rows[-1]["seq"] if rows else after, "has_more": more}

    def snapshot(self, after_id=0, limit=500):
        rows = [o for o in self.snap if o["order_id"] > after_id][:limit]
        return {"as_of_seq": self.as_of, "orders": rows, "products": [], "next_after_id": rows[-1]["order_id"] if rows else None}


@pytest.fixture
def store():
    return Store(":memory:")


def test_lost_connection_then_old_order_update_and_duplicates(store):
    store.set("cursor", 0)
    log = [ev(1, order(1, "pending", 1)), ev(2, order(2, "pending", 2)), ev(3, order(1, "confirmed", 3)), ev(4, order(3, "pending", 4))]
    site = FakeSite(log)
    site.fail_on_call = 2  # lô đầu OK, lô thứ hai mất mạng
    with pytest.raises(SiteError):
        S.sync(store, site)
    assert int(store.get("cursor")) == 2, "con trỏ chỉ dời tới lô đã ghi thành công"
    assert store.one("SELECT status FROM orders WHERE order_id=1")["status"] == "pending"

    # Website gửi lại lô có sự kiện trùng (E0002) + cập nhật đơn CŨ #1 + sự kiện mới
    site.log = log + [ev(5, order(1, "shipping", 5)), ev(6, order(2, "cancelled", 6))]
    site.fail_on_call = None
    batch = [log[1], log[2], log[3], ev(5, order(1, "shipping", 5))]  # E0002 đã áp dụng → trùng
    st = S.apply_batch(store, batch, 5)
    assert st["duplicates"] == 1 and st["applied"] == 3
    res = S.sync(store, site)
    assert int(store.get("cursor")) == 6
    assert store.one("SELECT status, version FROM orders WHERE order_id=1")["status"] == "shipping"
    assert store.one("SELECT status FROM orders WHERE order_id=2")["status"] == "cancelled"
    assert store.one("SELECT COUNT(*) n FROM orders")["n"] == 3
    # mỗi sự kiện chỉ áp dụng một lần
    assert store.one("SELECT COUNT(*) n FROM processed_events")["n"] == 6
    # gửi lại toàn bộ lần nữa: không thay đổi gì
    st = S.apply_batch(store, site.log, 6)
    assert st["applied"] == 0 and st["duplicates"] == 6


def test_stale_version_ignored(store):
    store.set("cursor", 0)
    S.apply_batch(store, [ev(10, order(7, "delivered", 10))], 10)
    st = S.apply_batch(store, [ev(8, order(7, "pending", 8), eid="OLD")], 10)
    assert st["stale"] == 1
    assert store.one("SELECT status FROM orders WHERE order_id=7")["status"] == "delivered"


def test_batch_atomic_on_error(store):
    store.set("cursor", 0)
    bad = ev(2, {"order_id": 9})  # thiếu trường → lỗi giữa lô
    with pytest.raises(Exception):
        S.apply_batch(store, [ev(1, order(8, "pending", 1)), bad], 2)
    assert int(store.get("cursor")) == 0
    assert store.one("SELECT COUNT(*) n FROM orders")["n"] == 0
    assert store.one("SELECT COUNT(*) n FROM processed_events")["n"] == 0


def test_cursor_expired_reloads_snapshot(store):
    store.set("cursor", 3)
    site = FakeSite([ev(101, order(5, "delivered", 101))], snapshot_orders=[order(4, "delivered", 99), order(5, "shipping", 100)], as_of=100, pruned_through=50)
    res = S.sync(store, site)
    assert res["snapshot"]["as_of_seq"] == 100
    assert int(store.get("cursor")) == 101
    assert store.one("SELECT status FROM orders WHERE order_id=5")["status"] == "delivered"
    assert store.one("SELECT COUNT(*) n FROM orders")["n"] == 2


def test_no_pii_columns(store):
    cols = {r["name"] for r in store.all("PRAGMA table_info(orders)")}
    assert not cols & {"ship_name", "ship_phone", "ship_address", "phone", "full_name"}
