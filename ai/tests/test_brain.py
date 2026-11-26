"""Bộ não Trưởng văn phòng: cảm nhận, nội quy, giao việc, học từ phản hồi, bản tin."""
import datetime as dt
import json

import pytest

from xuong_ai import config as C
from xuong_ai.agents import site_ref
from xuong_ai.brain import Brain, brief, learning, state
from xuong_ai.client import SiteError
from xuong_ai.llm import Llm
from xuong_ai.scheduler import App
from xuong_ai.store import Store

from .test_sync import order

NOW = dt.datetime.now(dt.UTC).replace(tzinfo=None)


def ts(days=0, hours=0):
    return (NOW - dt.timedelta(days=days, hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


CATALOG = {
    "categories": [{"id": 1, "name": "Trà", "repurchase_days": 30}],
    "products": [
        {"id": 5, "category_id": 1, "name": "Trà gừng mật ong", "short_desc": "", "ingredients": "Gừng 70%", "usage_guide": "Hãm 5 phút",
         "storage_guide": "Khô ráo", "allergens": "Mật ong", "info_version": 3, "skus": [{"variant_label": "Hộp 20 túi"}]},
        {"id": 6, "category_id": 1, "name": "Trà hoa cúc", "short_desc": "", "ingredients": "Hoa cúc", "usage_guide": "", "storage_guide": "Khô ráo",
         "allergens": "", "info_version": 1, "skus": [{"variant_label": "Hộp 20 túi"}]},
    ],
    "published_faqs": [{"id": 1, "question": "Phí giao hàng được tính thế nào?", "answer": "Theo vùng.",
                        "search_text": "phi giao hang duoc tinh the nao theo vung mien phi", "version_id": 11, "category_id": None, "product_id": None}],
    "published_blogs": [{"id": 9, "product_id": 6, "title": "Hoa cúc"}],
    "unanswered_questions": [{"question": "Có xuất hóa đơn VAT không?", "n": 6}, {"question": "Bé 2 tuổi dị ứng đậu nành uống được không", "n": 2}],
}


class FakeSite:
    def __init__(self, orders=(), catalog=CATALOG):
        self.orders, self.cat = list(orders), catalog
        self.down = False
        self.sent, self.fb_items, self.backlog = [], [], {"faq": 0, "blog": 0, "cross_sell": 0, "care": 0, "oldest_pending_at": None}

    def _net(self):
        if self.down:
            raise SiteError(0, "NETWORK", "mất mạng")

    def events(self, after, limit=500):
        self._net()
        return {"events": [], "next_cursor": after, "has_more": False}

    def snapshot(self, after_id=0, limit=500):
        self._net()
        rows = [o for o in self.orders if o["order_id"] > after_id]
        return {"as_of_seq": 100, "orders": rows, "products": [], "next_after_id": None}

    def catalog(self):
        self._net()
        return json.loads(json.dumps(self.cat))

    def feedback(self, since=None):
        self._net()
        return {"items": self.fb_items, "backlog": dict(self.backlog)}

    def send_drafts(self, items):
        self._net()
        self.sent.extend(items)
        # như website thật: client_ref được lọc ký tự ('blog:product:5@v3' → 'blog:product:5v3')
        return {"results": [{"client_ref": site_ref(i["client_ref"]), "status": "accepted", "result": f"content:{len(self.sent)}"} for i in items]}


class FakeLlm(Llm):
    def __init__(self, cfg, store, reply='{"question": "Xưởng có xuất hóa đơn VAT không?", "answer": "Có, liên hệ hotline.", "keywords": "hoa don", "sufficient": true}'):
        super().__init__(cfg.llm, store, transport=self._t)
        self.reply, self.prompts = reply, []

    def _t(self, system, user, max_tokens):
        self.prompts.append(user)
        r = self.reply if '"title"' not in user else '{"title": "Bài", "meta_description": "m", "keywords": "k", "body": "<p>x</p>"}'
        if "Viết một bài blog" in user:
            r = '{"title": "Trà gừng mật ong: cách pha", "meta_description": "m", "keywords": "k", "body": "<p>x</p>"}'
        return r, 500, 100


@pytest.fixture
def mk(tmp_path):
    def make(orders=(), llm=True, **brain):
        cfg = C.load(tmp_path / "config.toml")
        cfg.llm.api_key = "test" if llm else ""
        for k, v in brain.items():
            setattr(cfg.brain, k, v)
        store = Store(":memory:")
        site = FakeSite(orders)
        app = App(cfg, store=store, client=site, llm=None)
        app.llm = FakeLlm(cfg, store)
        return Brain(app), site
    return make


def run_ticks(b, n=2):
    out = []
    for _ in range(n):
        out.append(b.tick())
        # giả lập thời gian trôi: mọi việc định kỳ đến hạn lại
        b.store.db.execute("UPDATE jobs SET next_run = '2000-01-01 00:00:00' WHERE failures = 0")
    return out


def decisions(b):
    return {(r["action"], r["verdict"]): r["why"] for r in b.store.all("SELECT * FROM brain_decisions")}


def test_tick_drafts_faq_and_escalates_sensitive(mk):
    b, site = mk()
    run_ticks(b, 2)
    # thư ký đồng bộ + nạp danh mục; tư vấn viên soạn FAQ hóa đơn
    acts = {r["action"] for r in b.store.all("SELECT action FROM brain_tasks WHERE status='done'")}
    assert {"sync", "catalog", "feedback", "faq_draft"} <= acts
    faq = [i for i in site.sent if i["kind"] == "faq"]
    assert len(faq) == 1 and "hóa đơn" in faq[0]["data"]["title"]
    # câu hỏi dị ứng: KHÔNG gửi LLM, chuyển người
    assert not any("dị ứng" in p for p in b.llm.prompts)
    esc = {e["key"].split(":")[0]: e for e in state.open_escalations(b.store)}
    assert "faq_human" in esc and "dị ứng" in esc["faq_human"]["title"]
    # sản phẩm thiếu nhãn → chuyển người (AI không bịa nhãn)
    assert "label_gap" in esc and "Trà hoa cúc" in esc["label_gap"]["detail"]
    # blog: trà gừng chưa có bài → soạn; hoa cúc đã có bài nhân viên viết → không soạn
    blogs = [i for i in site.sent if i["kind"] == "blog"]
    assert [x["data"]["product_id"] for x in blogs] == [5]
    assert b.store.one("SELECT status FROM outbox WHERE kind='blog'")["status"] == "accepted", "khớp client_ref đã bị website lọc '@'"
    # người duyệt từ chối bài blog (website trả client_ref đã lọc) → khoảng trống mở lại, lần 2 có góp ý
    site.fb_items = [{"client_ref": site_ref(blogs[0]["client_ref"]), "kind": "blog", "status": "rejected", "note": "Bỏ phần lịch sử, thêm cách pha đá"}]
    # lần sau không soạn lại cùng câu hỏi; bài blog bị từ chối được soạn lại kèm góp ý
    run_ticks(b, 2)
    assert len([i for i in site.sent if i["kind"] == "faq"]) == 1
    blogs = [i for i in site.sent if i["kind"] == "blog"]
    assert len(blogs) == 2 and blogs[1]["client_ref"].endswith(":r2")
    assert "thêm cách pha đá" in next(p for p in reversed(b.llm.prompts) if "Viết một bài blog" in p)


def test_review_capacity_defers_drafts(mk):
    b, site = mk(max_pending_review=3)
    site.backlog = {"faq": 2, "blog": 1, "cross_sell": 0, "care": 0, "oldest_pending_at": ts(days=9)}
    run_ticks(b, 2)
    assert not [i for i in site.sent if i["kind"] in ("faq", "blog")]
    why = decisions(b)[("faq_draft", "defer")]
    assert "chờ duyệt" in why
    assert any(e["key"] == "review_backlog" for e in state.open_escalations(b.store))


def test_no_llm_blocks_drafts_but_office_keeps_working(mk):
    b, site = mk(llm=False)
    run_ticks(b, 2)
    assert "Chưa bật LLM" in decisions(b)[("faq_draft", "block")]
    assert b.store.one("SELECT COUNT(*) n FROM brain_tasks WHERE action='catalog' AND status='done'")["n"] >= 1


def test_rejection_feedback_redrafts_with_guidance_then_escalates(mk):
    b, site = mk()
    run_ticks(b, 2)
    ref = next(i["client_ref"] for i in site.sent if i["kind"] == "faq")
    site.fb_items = [{"client_ref": ref, "kind": "faq", "status": "rejected", "note": "Không nhắc hotline, ghi rõ xuất hóa đơn trong 3 ngày"}]
    run_ticks(b, 2)
    faqs = [i for i in site.sent if i["kind"] == "faq"]
    assert len(faqs) == 2 and faqs[1]["client_ref"] == ref + ":r2"
    assert "xuất hóa đơn trong 3 ngày" in b.llm.prompts[-1] or any("xuất hóa đơn trong 3 ngày" in p for p in b.llm.prompts[-2:])
    # bị từ chối lần 2 → chuyển người viết, không soạn lần 3
    site.fb_items.append({"client_ref": ref + ":r2", "kind": "faq", "status": "rejected", "note": "Vẫn sai"})
    run_ticks(b, 2)
    assert len([i for i in site.sent if i["kind"] == "faq"]) == 2
    assert any(e["key"].startswith("faq_retry:") for e in state.open_escalations(b.store))
    assert learning.reliability(b.store, "faq", NOW)["rejected"] == 2


def test_site_down_opens_circuit_and_escalates(mk):
    b, site = mk()
    run_ticks(b, 2)
    site.down = True
    for _ in range(3):
        b.store.db.execute("UPDATE jobs SET next_run = '2000-01-01 00:00:00'")
        b.tick()
    esc = {e["key"] for e in state.open_escalations(b.store)}
    assert "site_unreachable" in esc
    assert "Website chưa phản hồi" in decisions(b)[("catalog", "defer")]
    # website sống lại → việc cần người tự đóng
    site.down = False
    b.store.db.execute("UPDATE jobs SET next_run = '2000-01-01 00:00:00'")
    b.tick()
    assert "site_unreachable" not in {e["key"] for e in state.open_escalations(b.store)}


def test_sales_drop_detected(mk):
    orders, oid = [], 0
    for d in range(1, 29):
        for h in range(5):
            oid += 1
            o = order(oid, "delivered", oid, key=f"k{oid}")
            o["created_at"] = ts(days=d, hours=h * 3)
            orders.append(o)
    b, site = mk(orders)
    run_ticks(b, 2)
    esc = {e["key"]: e for e in state.open_escalations(b.store)}
    assert "sales_drop" in esc and "0 đơn" in esc["sales_drop"]["title"]
    # có đơn trong 24 giờ như thường → không báo động
    for i in range(5):
        oid += 1
        o = order(oid, "pending", oid, key=f"n{oid}")
        o["created_at"] = ts(hours=i)
        site.orders.append(o)
    b.store.set("cursor", "")  # buộc tải lại bản chụp
    b.store.db.execute("DELETE FROM sync_state WHERE key='cursor'")
    run_ticks(b, 1)
    assert "sales_drop" not in {e["key"] for e in state.open_escalations(b.store)}


def test_care_list_not_repeated(mk):
    orders = [order(1, "delivered", 1, items=[(1, 5, 1, 1, 50000)], key="A", delivered=ts(days=60)),
              order(2, "delivered", 2, items=[(1, 5, 1, 1, 50000)], key="A", delivered=ts(days=30))]
    b, site = mk(orders)
    run_ticks(b, 2)
    care = [i for i in site.sent if i["kind"] == "care_list"]
    assert len(care) == 1 and care[0]["data"]["entries"][0]["customer_key"] == "A"
    b.store.db.execute("UPDATE brain_tasks SET started_at = ? WHERE action = 'care_list'", (ts(days=1),))
    run_ticks(b, 2)
    assert len([i for i in site.sent if i["kind"] == "care_list"]) == 1, "khách đã nhắc trong 30 ngày không bị nhắc lại"


def test_pause_switch(mk, tmp_path):
    b, site = mk()
    (tmp_path / "STOP").write_text("")
    run_ticks(b, 1)
    assert b.store.one("SELECT COUNT(*) n FROM brain_tasks")["n"] == 0
    assert "tạm dừng" in decisions(b)[("sync", "block")]


def test_think_is_read_only_and_brief(mk):
    b, site = mk()
    run_ticks(b, 2)
    before = b.store.one("SELECT COUNT(*) n FROM brain_tasks")["n"]
    txt = brief.format_thoughts(b.think())
    assert "Quyết định" in txt and b.store.one("SELECT COUNT(*) n FROM brain_tasks")["n"] == before
    p = b.maybe_brief(NOW, force=True)
    md = p.read_text(encoding="utf-8")
    for h in ("Cần anh/chị quyết", "Bộ não nhận thấy", "Văn phòng đã làm", "Đang chờ duyệt", "Bài học"):
        assert h in md
    assert "dị ứng" in md
    assert "Tư vấn viên" in brief.format_office(b, NOW)
