import datetime as dt
import json

import pytest

from xuong_ai import config as C
from xuong_ai import textnorm
from xuong_ai.agents import care, content, crosssell, flush_outbox
from xuong_ai.calibrate import evaluate, load_cases
from xuong_ai.llm import BudgetExceeded, Llm
from xuong_ai.memory import Memory, question_type
from xuong_ai.store import Store
from xuong_ai.sync import apply_batch

from .test_sync import ev, order


@pytest.fixture
def store():
    s = Store(":memory:")
    s.set("cursor", 0)
    return s


def cfg(tmp_path=None):
    c = C.load("/nonexistent.toml")
    c.llm.api_key = "test"
    return c


def test_crosssell_lift(store):
    seq = 0
    evs = []
    # 6 đơn đã giao: (trà gừng 1 + hoa cúc 3) ×3, (ngũ cốc 6 + yến mạch 8) ×2, gừng lẻ ×1
    baskets = [(1, 3), (1, 3), (1, 3), (6, 8), (6, 8), (1,)]
    for i, b in enumerate(baskets, 1):
        seq += 1
        evs.append(ev(seq, order(i, "delivered", seq, items=[(p * 10, p, 1, 1, 50000) for p in b], key=f"k{i}")))
    apply_batch(store, evs, seq)
    s = crosssell.suggest(store, min_support=2)
    pairs = {(x["product_id"], x["related_product_id"]) for x in s}
    assert (1, 3) in pairs and (3, 1) in pairs and (6, 8) in pairs
    assert all(x["lift"] > 1 for x in s)
    assert (1, 6) not in pairs


def test_care_due_and_consent(store):
    today = dt.date(2026, 11, 25)
    evs = [
        ev(1, order(1, "delivered", 1, items=[(1, 1, 7, 1, 1)], key="A", delivered="2026-09-26 00:00:00")),
        ev(2, order(2, "delivered", 2, items=[(1, 1, 7, 1, 1)], key="A", delivered="2026-10-26 00:00:00")),  # chu kỳ 30 → đến 25/11
        ev(3, order(3, "delivered", 3, items=[(1, 1, 7, 1, 1)], key="B", consent=False, delivered="2026-10-26 00:00:00")),
        ev(4, order(4, "delivered", 4, items=[(1, 1, 7, 2, 1)], key="C", delivered="2026-10-01 00:00:00")),  # mặc định 30×2 → 30/11
        ev(5, order(5, "delivered", 5, items=[(1, 1, 7, 1, 1)], key="D", delivered="2026-10-27 00:00:00")),
        ev(6, order(6, "pending", 6, items=[(1, 1, 7, 1, 1)], key="D")),  # D đã đặt lại → không nhắc
    ]
    apply_batch(store, evs, 6)
    cat = {"categories": [{"id": 7, "repurchase_days": 30}]}
    lst = care.due_list(store, cat, today=today)
    keys = {x["customer_key"] for x in lst}
    assert keys == {"A", "C"}
    a = [x for x in lst if x["customer_key"] == "A"][0]
    assert a["due_date"] == "2026-11-25" and "chính khách" in a["reason"]
    assert "B" in {x["customer_key"] for x in care.due_list(store, cat, today=today, only_consented=False)}


class FakeLlm(Llm):
    def __init__(self, store, reply):
        c = cfg()
        super().__init__(c.llm, store, transport=lambda s, u, m: (reply, 1000, 200))
        self.prompts = []
        orig = self._transport
        self._transport = lambda s, u, m: (self.prompts.append(u) or orig(s, u, m))


def test_llm_budget_and_redaction(store):
    llm = FakeLlm(store, '{"ok": true}')
    llm.cfg.max_calls_per_day = 2
    llm.complete("t", "sys", "Khách 0912345678 email a@b.vn hỏi")
    assert "0912345678" not in llm.prompts[0] and "a@b.vn" not in llm.prompts[0]
    llm.complete("t", "sys", "x")
    with pytest.raises(BudgetExceeded):
        llm.complete("t", "sys", "x")
    u = llm.usage_today()
    assert u["calls"] == 2 and u["cost_usd"] > 0


CATALOG = {
    "categories": [{"id": 1, "name": "Trà", "repurchase_days": 30}],
    "products": [{"id": 5, "category_id": 1, "name": "Trà gừng mật ong", "short_desc": "", "ingredients": "Gừng 70%", "usage_guide": "Hãm 5 phút",
                  "storage_guide": "Khô ráo", "allergens": "Mật ong", "info_version": 3, "skus": [{"variant_label": "Hộp 20 túi"}]}],
    "published_faqs": [{"id": 1, "question": "Phí giao hàng được tính thế nào?", "answer": "<p>Theo vùng.</p>", "search_text": "phi giao hang duoc tinh the nao theo vung mien phi", "version_id": 11, "category_id": None, "product_id": None}],
    "unanswered_questions": [{"question": "phi ship bao nhieu", "n": 4}, {"question": "Có xuất hóa đơn VAT không?", "n": 3}, {"question": "co xuat hoa don vat khong", "n": 2}],
}


def test_faq_memory_first(store):
    Memory(store).refresh_from_catalog(CATALOG)
    llm = FakeLlm(store, '{"question": "Xưởng có xuất hóa đơn VAT không?", "answer": "Vui lòng liên hệ hotline.", "keywords": "hoa don", "sufficient": false}')
    r = content.faq_drafts(store, llm, CATALOG, threshold=0.3)
    assert r["clusters"] == 2, "gom 2 cách hỏi về hóa đơn thành 1 cụm"
    assert r["memory_hits"] == 1, "câu phí ship đã có FAQ → không gọi LLM"
    assert r["drafted"] == 1 and len(llm.prompts) == 1
    q = store.one("SELECT * FROM outbox")
    assert q["kind"] == "faq" and json.loads(q["payload"])["body_is_text"] is True
    # chạy lại: bản nháp đang chờ duyệt trong bộ nhớ → không gọi LLM nữa
    r2 = content.faq_drafts(store, llm, CATALOG, threshold=0.3)
    assert r2["drafted"] == 0 and len(llm.prompts) == 1


def test_label_change_retires_knowledge(store):
    m = Memory(store)
    m.refresh_from_catalog(CATALOG)
    apply_batch(store, [{"seq": 1, "event_id": "P1", "entity_type": "product", "entity_id": 5, "event_type": "product.updated",
                         "payload": {"product_id": 5, "category_id": 1, "status": "active", "info_version": 3, "version": 1}}], 1)
    m.add_pending("blog_outline", "blog:product:5@v3", "Bài cũ", "", "san_pham", 1, 5, "3")
    apply_batch(store, [{"seq": 2, "event_id": "P2", "entity_type": "product", "entity_id": 5, "event_type": "product.updated",
                         "payload": {"product_id": 5, "category_id": 1, "status": "active", "info_version": 4, "version": 2}}], 2)
    st = {r["source_ref"]: r["status"] for r in store.all("SELECT source_ref, status FROM knowledge WHERE product_id = 5")}
    assert st["blog:product:5@v3"] == "retired" and st["product:5"] == "retired"


def test_outbox_dedupe(store):
    class Site:
        sent = []
        def send_drafts(self, items):
            self.sent.append(items)
            return {"results": [{"client_ref": i["client_ref"], "status": "accepted"} for i in items]}
    from xuong_ai.agents import enqueue
    assert enqueue(store, "r1", "faq", {"a": 1}) and not enqueue(store, "r1", "faq", {"a": 1})
    site = Site()
    assert flush_outbox(store, site)["accepted"] == 1
    assert flush_outbox(store, site)["sent"] == 0


def test_question_type():
    assert question_type("Phí ship bao nhiêu?") == "giao_hang"
    assert question_type("chuyen khoan vietqr") == "thanh_toan"
    assert question_type("bé dị ứng đậu nành") == "di_ung"


def test_calibration_on_seed_faqs():
    """Ngưỡng hiệu chỉnh trên FAQ mẫu: độ chính xác ≥ 90%."""
    from pathlib import Path
    seed = [
        "Phí giao hàng được tính thế nào?|Phí giao hàng tính theo vùng: Hà Nội 20.000đ, Miền Bắc 30.000đ, Miền Trung và Miền Nam 35.000đ. Đơn đủ mức miễn phí theo vùng sẽ được miễn phí giao. Tổng tiền chính xác hiển thị ở giỏ hàng sau khi bạn chọn tỉnh/thành.",
        "Bao lâu thì tôi nhận được hàng?|Thời gian giao dự kiến: Hà Nội 1–2 ngày, Miền Bắc 2–3 ngày, Miền Trung 3–4 ngày, Miền Nam 3–5 ngày kể từ khi đơn được xác nhận.",
        "Thanh toán chuyển khoản VietQR như thế nào?|Sau khi đặt hàng, trang xác nhận hiển thị mã QR kèm đúng số tiền và nội dung chuyển khoản là mã đơn. Bạn quét bằng ứng dụng ngân hàng và giữ nguyên nội dung. Nhân viên đối soát xác nhận khi tiền về tài khoản, sau đó đơn mới được chuẩn bị giao.",
        "Tôi chuyển khoản thiếu hoặc sai nội dung thì sao?|Khoản chuyển thiếu, thừa, sai nội dung hoặc sau hạn sẽ được nhân viên đối soát kiểm tra và liên hệ bạn để thống nhất: bổ sung, hoàn tiền hoặc tạo đơn thay thế.",
        "Có được thanh toán khi nhận hàng (COD) không?|Có. Bạn chọn COD ở bước thanh toán và trả tiền mặt cho người giao hàng. Xưởng sẽ gọi xác nhận đơn trước khi giao.",
        "Chính sách đổi trả ra sao?|Sản phẩm lỗi do đóng gói, vận chuyển hoặc hết hạn được đổi mới hoặc hoàn tiền. Vui lòng quay video khi mở hàng và liên hệ trong 3 ngày kể từ khi nhận. Chi tiết xem trang Chính sách đổi trả.",
        "Bảo quản bột ngũ cốc sau khi mở thế nào?|Đậy kín túi/hũ, để nơi khô ráo thoáng mát, tránh ánh nắng và dùng thìa khô. Nên dùng hết trong khoảng 30 ngày sau khi mở để giữ hương vị.",
        "Trẻ em có dùng được bột ngũ cốc không?|Trẻ từ 1 tuổi có thể dùng lượng nhỏ, pha loãng. Bột có chứa đậu nành, hạt cây và gluten — nếu bé có tiền sử dị ứng, vui lòng hỏi ý kiến bác sĩ trước khi dùng.",
        "Cà phê có tẩm ướp hương liệu không?|Không. Cà phê của xưởng rang mộc 100%, không bơ, không đường, không hương liệu.",
        "Pha trà túi lọc bao lâu là ngon?|Trà thảo mộc hãm với nước sôi 3–5 phút; trà hoa (hoa cúc) nên dùng nước khoảng 90°C. Có thể hãm lại lần hai.",
        "Mã giảm giá có dùng chung với Flash Sale không?|Mỗi đơn dùng một mã giảm giá. Sản phẩm đang Flash Sale có thể không được tính vào điều kiện của mã, tùy quy tắc từng chương trình; giỏ hàng sẽ hiển thị chính xác số tiền được giảm.",
    ]
    faqs = []
    for s in seed:
        q, a = s.split("|")
        faqs.append({"question": q, "answer": a, "search_text": textnorm.fold(q + " " + a[:600])})
    r = evaluate(faqs, load_cases(Path(__file__).parent.parent / "eval" / "faq_eval.jsonl"))
    assert r["best"]["precision"] >= 0.9
    assert r["best"]["accuracy"] >= 0.7, r["errors"]
