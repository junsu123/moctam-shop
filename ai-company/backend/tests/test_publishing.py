"""IT-PUB-01…07, IT-LG-02, Content Gate, lịch đăng: AI tự xuất bản FAQ/blog với 5 lớp chặn (ARCHITECTURE ADR-16)."""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from tests.conftest import needs_db
from tests.officekit import FakeModel, done, drain, make_task, rows, task
from tests.sitekit import FakeSite

pytestmark = needs_db
VN = ZoneInfo("Asia/Ho_Chi_Minh")
FAQ_OK = {
    "title": "Xưởng có giao hàng trong ngày không?",
    "body": "Xưởng chưa giao trong ngày. Đơn đặt trước 15 giờ được đóng gói và gửi ngay sáng hôm sau, thường tới nơi sau 2–4 ngày.",
}


# ------------------------------------------------------------------ Content Gate (tất định)
def test_content_gate_deterministic_rules() -> None:
    from app.content.gate import GateConfig, check

    cat = {"products": [{"id": 1, "skus": [{"list_price": 65000}]}]}
    cfg = GateConfig()
    r = check(
        cfg,
        kind="faq",
        title="Trà gừng hợp cả gia đình",
        body="Uống ấm, thân thiện với dạ dày người lớn, giá trị dinh dưỡng cao. " * 2,
        catalog=cat,
    )
    assert r.ok and "giá" not in r.topics  # "gia đình", "giá trị", "thân thiện" không bị nhận nhầm
    assert "sức khỏe" in r.topics  # "dạ dày" là chủ đề chỉ-người-duyệt
    r = check(
        cfg,
        kind="faq",
        title="Giá trà gừng",
        body="Hộp 20 túi giá bán 65.000đ, pha được 20 ly, uống ấm vào buổi sáng rất dễ chịu.",
        catalog=cat,
    )
    assert r.ok and r.topics == ["giá"] and r.prices_found == [65000]
    r = check(
        cfg,
        kind="faq",
        title="Giá trà gừng",
        body="Hộp 20 túi chỉ 59k thôi, pha được 20 ly, uống ấm vào buổi sáng rất dễ chịu nha.",
        catalog=cat,
    )
    assert any("giá không khớp website: 59.000đ" in b for b in r.blocked)
    r = check(
        cfg,
        kind="faq",
        title="Trà gừng chua benh cam",
        body="Trà gừng giúp chua benh cảm cúm nhanh, rẻ nhất thị trường, gọi 0912 345 678 để đặt.",
        catalog=cat,
    )
    joined = " | ".join(r.blocked)
    assert "chữa bệnh" in joined and "rẻ nhất" in joined and "số điện thoại" in joined  # viết không dấu cũng không lọt
    r = check(cfg, kind="blog", title="Ngắn", body="Quá ngắn.", catalog=cat)
    assert any("ngắn quá" in b for b in r.blocked)
    r = check(
        cfg,
        kind="faq",
        title="Dị ứng",
        body="Người dị ứng với gừng nên hỏi ý kiến bác sĩ trước khi dùng sản phẩm này nhé anh chị.",
        catalog=cat,
    )
    assert r.ok and "dị ứng" in r.topics


# ------------------------------------------------------------------ IT-PUB-06 (phần lịch): khung giờ của giai đoạn
def test_it_pub_06_slots_follow_phase_window_and_gap() -> None:
    from app.content.publishing import PublishSettings, next_slot

    s = PublishSettings()  # giai đoạn 1: FAQ 11:30 mỗi ngày; blog Thứ Ba, Thứ Bảy 19:30
    mon = datetime(2026, 11, 30, 8, 0, tzinfo=VN)  # Thứ Hai
    f1 = next_slot(s, "faq", mon, [])
    assert f1 is not None and f1.astimezone(VN) == datetime(2026, 11, 30, 11, 30, tzinfo=VN)
    f2 = next_slot(s, "faq", mon, [("faq", f1)])
    assert f2 is not None and f2.astimezone(VN).date() == date(2026, 12, 1)  # 1 FAQ/ngày
    b1 = next_slot(s, "blog", mon, [])
    assert b1 is not None and b1.astimezone(VN) == datetime(2026, 12, 1, 19, 30, tzinfo=VN)  # Thứ Ba
    b2 = next_slot(s, "blog", mon, [("blog", b1)])
    assert b2 is not None and b2.astimezone(VN) == datetime(2026, 12, 5, 19, 30, tzinfo=VN)  # Thứ Bảy
    b3 = next_slot(s, "blog", mon, [("blog", b1), ("blog", b2)])
    assert b3 is not None and b3.astimezone(VN) == datetime(2026, 12, 8, 19, 30, tzinfo=VN)  # tuần sau (2 bài/tuần)
    s.phase = 3  # FAQ 07:30, 11:30, 17:30; blog 19:30 mỗi ngày; hai bài cách ≥ 3 giờ
    day = datetime(2026, 12, 2, 6, 0, tzinfo=VN)
    blog = next_slot(s, "blog", day, [])
    assert blog is not None
    slots = [next_slot(s, "faq", day, [("blog", blog)])]
    for _ in range(2):
        slots.append(next_slot(s, "faq", day, [("blog", blog), *[("faq", x) for x in slots if x]]))
    local = [x.astimezone(VN).strftime("%d %H:%M") for x in slots if x]
    assert local == ["02 07:30", "02 11:30", "03 07:30"]  # 17:30 cách 19:30 chưa đủ 3 giờ → sang ngày sau
    for t in [*slots, blog]:
        assert t is not None and "07:00" <= t.astimezone(VN).strftime("%H:%M") <= "21:30"
    s.holidays = [date(2026, 12, 2)]
    nxt = next_slot(s, "faq", day, [])
    assert nxt is not None and nxt.astimezone(VN).date() == date(2026, 12, 3)  # ngày nghỉ không đăng


# ------------------------------------------------------------------ tiện ích cho luồng thật qua đồ thị
def _script(faq: dict[str, Any], gate_risk: str = "low") -> Any:
    def s(agent: str, phase: str, title: str, prompt: str) -> dict[str, Any] | None:
        if phase == "gate":
            return {"risk": gate_risk, "reason": "đánh giá thử"}
        if agent == "content_agent":
            return done({**faq, "product_id": 1})
        if agent == "marketing_director" and title.startswith("Review:"):
            return done({"verdict": "approve", "notes": "Đúng chính sách, giọng thân thiện."})
        return None

    return s


async def _faq_task(**kw: Any) -> dict[str, Any]:
    return await make_task(
        title=kw.pop("title", "Viết FAQ về giao hàng"),
        assigned_agent="content_agent",
        task_type="faq",
        requires_review=True,
        reviewer="agent:marketing_director",
        input_data={"publish": True, "product_id": 1},
        autonomy_max=3,
        budget_usd=0.5,
        **kw,
    )


async def _queue() -> list[dict[str, Any]]:
    return await rows("SELECT * FROM publish_queue ORDER BY created_at")


async def _release_at(slot: datetime) -> dict[str, int]:
    from app.content import publishing

    return await publishing.release_due(slot + timedelta(minutes=1))


# ------------------------------------------------------------------ IT-PUB-01: đủ 5 lớp → lên website → Telegram nhận link
async def test_it_pub_01_reviewed_faq_scheduled_then_published(office: FakeModel, site: FakeSite) -> None:
    office.script = _script(FAQ_OK)
    t = await _faq_task()
    await drain(80)
    t = await task(str(t["id"]))
    assert t["status"] == "COMPLETED", (
        t["error"],
        [x["text"] for x in await rows("SELECT text FROM task_logs WHERE task_id = :t", {"t": t["id"]})],
    )
    q = await _queue()
    assert len(q) == 1 and q[0]["status"] == "scheduled" and q[0]["kind"] == "faq"
    assert q[0]["source_refs"] == [{"product_id": 1, "info_version": 3}]
    slot = q[0]["slot_at"].astimezone(VN)
    assert slot.strftime("%H:%M") == "11:30"  # giai đoạn 1: FAQ 11:30
    assert site.published == {}  # chưa tới giờ: chưa đăng
    out = await _release_at(q[0]["slot_at"])
    assert out["published"] == 1
    q = await _queue()
    assert q[0]["status"] == "published" and q[0]["url"] == "https://web.test/hoi-dap.html" and q[0]["content_id"] == 100
    n = await rows("SELECT kind, text, buttons FROM notifications WHERE kind = 'publish'")
    assert "https://web.test/hoi-dap.html" in n[0]["text"] and [b["action"] for b in n[0]["buttons"]] == ["unpublish", "feedback"]
    assert await rows("SELECT 1 FROM approvals") == []  # không thuộc chủ đề chỉ-người-duyệt: không hỏi Owner
    logs = [x["event"] for x in await rows("SELECT event FROM task_logs WHERE task_id = :t ORDER BY id", {"t": t["id"]})]
    assert logs.index("reviewed") < logs.index("publish_scheduled")  # lớp 2 (review) trước khi vào lịch


async def test_publish_requires_review_by_superior(office: FakeModel, site: FakeSite) -> None:
    office.script = _script(FAQ_OK)
    t = await make_task(
        title="FAQ không qua review", assigned_agent="content_agent", task_type="faq", input_data={"publish": True}, autonomy_max=3
    )
    await drain()
    t = await task(str(t["id"]))
    assert t["status"] == "FAILED" and t["error_code"] == "REVIEW_REQUIRED"
    assert await _queue() == []


# ------------------------------------------------------------------ IT-PUB-02: website đếm hạn mức, máy gửi thêm vẫn bị từ chối
async def test_it_pub_02_website_quota_rejects_extra_publish(office: FakeModel, site: FakeSite) -> None:
    from app.core import db
    from app.integrations import website

    site.limit["faq"] = 1
    async with db.engine().connect() as c:
        first = await website.publish(c, {"client_ref": "a", "kind": "faq", "data": {"title": "A", "body": "x"}})
        assert first["status"] == "published"
        from app.core.errors import AppError

        with pytest.raises(AppError) as e:  # phía máy "lỗi" cố gửi bài thứ hai
            await website.publish(c, {"client_ref": "b", "kind": "faq", "data": {"title": "B", "body": "y"}})
    assert e.value.code == "AI_PUBLISH_QUOTA" and e.value.status == 429


@pytest.mark.skipif(
    not os.environ.get("AICO_TEST_WEBSITE_URL"), reason="chưa có website thật (AICO_TEST_WEBSITE_URL + AICO_TEST_WEBSITE_*_KEY)"
)
async def test_it_pub_01_02_real_website(office: FakeModel) -> None:
    """Với website THẬT (PHP + MariaDB): đăng, đếm hạn mức ở website, gỡ bài. CI dựng website từ web/ để chạy test này."""
    from app.core import db
    from app.core.errors import AppError
    from app.domain import store
    from app.integrations import website

    async with db.engine().begin() as c:
        await store.put_setting(c, "website", store.Website(base_url=os.environ["AICO_TEST_WEBSITE_URL"]), "test")
        await store.put_secret(c, website.KEYS["read"], os.environ["AICO_TEST_WEBSITE_READ_KEY"], "test")
        await store.put_secret(c, website.KEYS["publish"], os.environ["AICO_TEST_WEBSITE_PUBLISH_KEY"], "test")
    website.clear_cache()
    async with db.engine().connect() as c:
        cat = await website.catalog(c, fresh=True)
        p = cat["products"][0]
        refs = [{"product_id": p["id"], "info_version": p["info_version"]}]
        res = await website.publish(
            c, {"client_ref": "it-pub-01", "kind": "faq", "data": {**FAQ_OK, "product_id": p["id"], "source_refs": refs}}
        )
        assert res["status"] == "published" and res["url"].endswith("/hoi-dap.html")
        again = await website.publish(c, {"client_ref": "it-pub-01", "kind": "faq", "data": FAQ_OK})
        assert again.get("duplicate") and again["content_id"] == res["content_id"]
        n = 1
        with pytest.raises(AppError) as e:
            for i in range(10):  # hạn mức FAQ ở website (mặc định 3/ngày)
                await website.publish(
                    c, {"client_ref": f"it-pub-02-{i}", "kind": "faq", "data": {**FAQ_OK, "title": f"Câu hỏi số {i} về giao hàng"}}
                )
                n += 1
        assert e.value.code == "AI_PUBLISH_QUOTA" and n <= 3
        u = await website.unpublish(c, int(res["content_id"]), "Kiểm thử IT-PUB-05 với website thật")
        assert u["status"] == "unpublished"
        stale = {**FAQ_OK, "title": "Bài dựa trên nhãn cũ", "source_refs": [{"product_id": p["id"], "info_version": p["info_version"] - 1}]}
        with pytest.raises(AppError) as e2:
            await website.publish(c, {"client_ref": "it-pub-stale", "kind": "faq", "data": stale})
        assert e2.value.code in ("SOURCE_OUTDATED", "AI_PUBLISH_QUOTA")


# ------------------------------------------------------------------ IT-PUB-03: trượt Content Gate → bản nháp + báo lý do
async def test_it_pub_03_gate_block_becomes_draft(office: FakeModel, site: FakeSite) -> None:
    bad = {
        "title": "Trà gừng chữa bệnh cảm cúm",
        "body": "Uống trà gừng mật ong mỗi ngày giúp chữa bệnh cảm cúm, cam kết 100% khỏi sau 3 ngày nha.",
    }
    office.script = _script(bad)
    t = await _faq_task(title="Viết FAQ trà gừng")
    await drain(80)
    assert (await task(str(t["id"])))["status"] == "COMPLETED"
    q = await _queue()
    assert q[0]["status"] == "blocked" and "chữa bệnh" in q[0]["last_error"]
    assert site.published == {} and len(site.drafts) == 1 and site.drafts[0]["client_ref"] == f"co:draft:{q[0]['id']}"
    n = await rows("SELECT text FROM notifications WHERE kind = 'alert'")
    assert "Không tự đăng" in n[0]["text"] and "chữa bệnh" in n[0]["text"] and "bản nháp chờ duyệt" in n[0]["text"]
    assert await rows("SELECT 1 FROM approvals") == []  # bị chặn thì không hỏi Owner duyệt đăng


# ------------------------------------------------------------------ IT-PUB-04 + IT-LG-02: chủ đề chỉ-người-duyệt → Telegram
class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.answers: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        import json

        method = req.url.path.rsplit("/", 1)[-1]
        body = json.loads(req.content or b"{}")
        if method == "sendMessage":
            self.sent.append(body)
        elif method == "answerCallbackQuery":
            self.answers.append(body["text"])
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(self.sent)}})

    def buttons(self, action: str) -> list[str]:
        out = []
        for m in self.sent:
            for row in (m.get("reply_markup") or {}).get("inline_keyboard") or []:
                out += [b["callback_data"] for b in row if b["text"] == action]
        return out


@pytest.fixture
async def tg(office: FakeModel) -> Any:
    from app.core import db
    from app.telegram import bot

    async with db.engine().begin() as c:
        await db.execute(
            c, "INSERT INTO telegram_chats(chat_id, title, can_approve) VALUES (777, 'Owner', true), (888, 'Nhóm báo cáo', false)"
        )
    fake = FakeBot()
    bot.transport = httpx.MockTransport(fake)
    yield fake
    bot.transport = None


async def _dispatch() -> None:
    from app.core import db
    from app.telegram import service

    async with db.engine().begin() as c:
        await service.dispatch(c, "123:TEST", datetime(2026, 12, 1, 3, 0, tzinfo=UTC))  # 10:00 giờ VN, ngoài giờ yên lặng


async def _press(data: str, chat: int = 777) -> str:
    from app.core import db
    from app.telegram import service

    async with db.engine().begin() as c:
        return await service.handle_update(
            c,
            "123:TEST",
            {"update_id": 1, "callback_query": {"id": "cb1", "data": data, "message": {"message_id": 5, "chat": {"id": chat}}}},
        )


async def test_it_pub_04_owner_only_topic_waits_and_expires(office: FakeModel, site: FakeSite, tg: FakeBot) -> None:
    from app.core import db
    from app.tasks import reconcile

    allergy = {
        "title": "Người dị ứng gừng có uống được không?",
        "body": "Người dị ứng với gừng không nên dùng trà gừng mật ong; nếu chưa chắc hãy hỏi bác sĩ trước khi uống.",
    }
    office.script = _script(allergy)
    t = await _faq_task(title="FAQ dị ứng gừng")
    await drain(80)
    t = await task(str(t["id"]))
    assert t["status"] == "WAITING_APPROVAL"
    ap = await rows("SELECT * FROM approvals")
    assert ap[0]["subject_type"] == "tool_call" and "publish_risky" in str(
        await rows("SELECT rule, reason, context FROM policy_decisions WHERE decision = 'require_approval'")
    )
    await _dispatch()
    assert len(tg.buttons("Duyệt")) == 1  # chỉ chat có quyền duyệt nhận nút; nhóm báo cáo chỉ nhận chữ
    assert any(m["chat_id"] == 888 and "reply_markup" not in m for m in tg.sent)
    async with db.engine().begin() as c:  # Owner không trả lời: quá hạn
        await db.execute(c, "UPDATE approvals SET expires_at = now() - interval '1 second'")
    await reconcile.run()
    await drain(40)
    assert (await task(str(t["id"])))["status"] == "CANCELLED"
    assert await _queue() == [] and site.published == {}  # im lặng không phải đồng ý
    assert await _press(tg.buttons("Duyệt")[0]) == "refused"  # yêu cầu đã hết hạn: nút không còn tác dụng


async def test_it_lg_02_approve_on_telegram_after_restart_digest_bound(office: FakeModel, site: FakeSite, tg: FakeBot) -> None:
    from app.core import db
    from app.tasks import graph

    price = {
        "title": "Trà gừng mật ong giá bao nhiêu?",
        "body": "Trà gừng mật ong hộp 20 túi giá bán 65.000đ, pha được 20 ly ấm bụng cho cả nhà vào ngày lạnh.",
    }
    office.script = _script(price)
    t = await _faq_task(title="FAQ giá trà gừng")
    await drain(80)
    assert (await task(str(t["id"])))["status"] == "WAITING_APPROVAL"
    await _dispatch()
    approve, reject = tg.buttons("Duyệt")[0], tg.buttons("Từ chối")[0]
    tok, _, sig = approve.partition(".")
    assert len(approve.encode()) <= 64
    assert await _press(f"{tok}.{'A' * len(sig)}") == "rejected"  # chữ ký giả
    assert await _press(approve, chat=888) == "rejected"  # nút gửi cho chat khác
    assert await _press(approve, chat=999) == "ignored"  # chat lạ
    async with db.engine().begin() as c:  # nội dung đổi sau khi gửi nút: digest lệch → không duyệt được
        real = await db.scalar(c, "SELECT payload_digest FROM approvals")
        await db.execute(c, "UPDATE approvals SET payload_digest = 'khac'")
    assert await _press(approve) == "refused" and "Nội dung đã thay đổi" in tg.answers[-1]
    assert (await rows("SELECT status FROM approvals"))[0]["status"] == "pending"
    await graph.close()  # khởi động lại toàn hệ thống giữa lúc chờ
    async with db.engine().begin() as c:
        await db.execute(c, "UPDATE approvals SET payload_digest = :d", {"d": real})
        await db.execute(c, "UPDATE notifications SET status = 'queued'")
        await db.execute(c, "DELETE FROM notification_deliveries")
    await _dispatch()  # gửi lại nút mới
    approve = tg.buttons("Duyệt")[-1]
    assert await _press(approve) == "approve" and tg.answers[-1] == "Đã duyệt."
    assert await _press(approve) == "rejected"  # mỗi nút dùng một lần
    assert await _press(reject) in ("rejected", "refused")  # nút Từ chối của cùng yêu cầu cũng hết tác dụng
    await drain(40)
    assert (await task(str(t["id"])))["status"] == "COMPLETED"
    q = await _queue()
    assert q[0]["status"] == "scheduled" and q[0]["approval_id"] is not None
    assert "giá" in q[0]["gate"]["topics"]


# ------------------------------------------------------------------ IT-PUB-05: Gỡ bài → biến khỏi website → vào kênh học; Góp ý
async def test_it_pub_05_unpublish_and_feedback_from_telegram(office: FakeModel, site: FakeSite, tg: FakeBot) -> None:
    from app.core import db
    from app.telegram import service

    office.script = _script(FAQ_OK)
    await _faq_task()
    await drain(80)
    await _release_at((await _queue())[0]["slot_at"])
    await _dispatch()
    assert await _press(tg.buttons("Gỡ bài")[0]) == "unpublish"
    q = await _queue()
    assert q[0]["status"] == "retracted" and q[0]["retracted_by"] == "telegram:777" and site.unpublished == [100]
    mem = await rows(
        "SELECT title, content, metadata FROM agent_memories WHERE owner_scope = 'agent:content_agent' AND title LIKE 'Bài học: bài bị gỡ%'"
    )
    assert mem and "Owner bấm Gỡ bài" in mem[0]["content"] and mem[0]["metadata"]["retracted"] is True
    assert await _press(tg.buttons("Góp ý")[0]) == "feedback"
    async with db.engine().begin() as c:
        r = await service.handle_update(
            c, "123:TEST", {"update_id": 2, "message": {"chat": {"id": 777}, "text": "Câu trả lời nên nhắc mã freeship"}}
        )
    assert r == "command"
    fb = await rows("SELECT content FROM agent_memories WHERE title LIKE 'Bài học: góp ý%'")
    assert "nhắc mã freeship" in fb[0]["content"]


# ------------------------------------------------------------------ IT-PUB-06: kiểm lại trước giờ đăng; lỡ giờ không đăng muộn
async def test_it_pub_06_recheck_before_publish_and_no_late_post(office: FakeModel, site: FakeSite) -> None:
    from app.content import publishing

    price = {
        "title": "Trà gừng mật ong giá bao nhiêu?",
        "body": "Trà gừng mật ong hộp 20 túi giá bán 65.000đ, pha được 20 ly ấm bụng cho cả nhà vào ngày lạnh.",
    }
    office.script = _script(price)
    await _faq_task()
    await drain(80)
    from app.core import db
    from app.domain import approvals

    async with db.engine().begin() as c:
        await approvals.decide(c, str((await rows("SELECT id FROM approvals"))[0]["id"]), True, "user:owner")
    await drain(40)
    item = (await _queue())[0]
    assert item["status"] == "scheduled"
    out = await publishing.release_due(item["slot_at"] + timedelta(hours=2))  # máy tắt, bật lại lúc quá giờ
    assert out["rescheduled"] == 1 and site.published == {}
    item2 = (await _queue())[0]
    assert item2["slot_at"] > item["slot_at"] and item2["slot_at"].astimezone(VN).strftime("%H:%M") == "11:30"
    site.products[0]["skus"][0]["list_price"] = 72000  # giá đổi trên website sau khi soạn
    out = await _release_at(item2["slot_at"])
    assert out["blocked"] == 1 and site.published == {}
    item3 = (await _queue())[0]
    assert item3["status"] == "blocked" and "giá không khớp website: 65.000đ" in item3["last_error"]


# ------------------------------------------------------------------ IT-PUB-07: lên/lùi giai đoạn, tạm dừng, ngày nghỉ
async def test_it_pub_07_phase_progress_step_down_pause_and_holiday(office: FakeModel, site: FakeSite, tg: FakeBot) -> None:
    from app.content import publishing
    from app.core import db
    from app.core.ids import uuid7
    from app.telegram import service

    now = datetime.now(UTC)
    async with db.engine().begin() as c:
        assert await publishing.evaluate_phase(c, now) == 1  # lần đầu: bắt đầu đếm giai đoạn 1
        s = await publishing.settings(c)
        s.phase_since = now - timedelta(days=15)
        await db.execute(c, "DELETE FROM settings WHERE key = 'publishing'")
        from app.domain import store

        await store.put_setting(c, "publishing", s, "test")
        for i in range(3):  # 3 bài đã đăng, không bài nào bị gỡ
            await db.execute(
                c,
                "INSERT INTO publish_queue(id, agent_key, kind, title, body, status, invocation_key, content_id, published_at) "
                "VALUES (:i, 'content_agent', 'faq', :t, 'nội dung', 'published', :k, :n, :p)",
                {"i": uuid7(), "t": f"FAQ {i}", "k": f"k{i}", "n": 200 + i, "p": now - timedelta(days=10 - i)},
            )
        assert await publishing.evaluate_phase(c, now) == 2
    up = await rows("SELECT text FROM notifications WHERE text LIKE '%giai đoạn 2%'")
    assert up
    items = await rows("SELECT id FROM publish_queue ORDER BY title")
    async with db.engine().begin() as c:  # Owner gỡ 2 bài trong 7 ngày → lùi về giai đoạn 1 + báo Telegram
        await publishing.unpublish(c, str(items[0]["id"]), actor="user:owner", reason="sai giờ chốt đơn")
        assert (await publishing.settings(c)).phase == 2
        await publishing.unpublish(c, str(items[1]["id"]), actor="telegram:777", reason="giọng văn chưa đúng")
        assert (await publishing.settings(c)).phase == 1
    assert await rows("SELECT 1 FROM notifications WHERE text LIKE '%Lùi lịch đăng về giai đoạn 1%'")
    async with db.engine().begin() as c:  # /tamdung xuatban: giữ hàng chờ, không đăng
        r = await service.handle_update(c, "123:TEST", {"update_id": 3, "message": {"chat": {"id": 777}, "text": "/tamdung xuatban"}})
        assert r == "command"
        await db.execute(
            c,
            "INSERT INTO publish_queue(id, agent_key, kind, title, body, status, invocation_key, slot_at) "
            "VALUES (:i, 'content_agent', 'faq', 'Chờ đăng', 'nội dung đủ dài', 'scheduled', 'k-wait', :s)",
            {"i": uuid7(), "s": datetime(2026, 12, 2, 11, 30, tzinfo=VN)},
        )
    out = await publishing.release_due(datetime(2026, 12, 2, 11, 31, tzinfo=VN))
    assert out == {"published": 0, "blocked": 0, "rescheduled": 0, "failed": 0}
    async with db.engine().begin() as c:
        r = await service.handle_update(c, "123:TEST", {"update_id": 4, "message": {"chat": {"id": 888}, "text": "/tieptuc xuatban"}})
        assert (await publishing.settings(c)).paused  # chat không có quyền duyệt không mở lại được
        await service.handle_update(c, "123:TEST", {"update_id": 5, "message": {"chat": {"id": 777}, "text": "/tieptuc xuatban"}})
        s = await publishing.settings(c)
        assert not s.paused
        s.holidays = [date(2026, 12, 2)]
        from app.domain import store

        await store.put_setting(c, "publishing", s, "test")
    out = await publishing.release_due(datetime(2026, 12, 2, 11, 31, tzinfo=VN))
    assert out["published"] == 0 and (await rows("SELECT status FROM publish_queue WHERE title = 'Chờ đăng'"))[0]["status"] == "scheduled"
    assert any(re.search("tạm dừng tự xuất bản", m["text"]) for m in tg.sent)
