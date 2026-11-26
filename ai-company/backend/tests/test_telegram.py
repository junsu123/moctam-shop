"""IT-TG-01, 04, 05: Telegram Gateway với Bot API giả (httpx.MockTransport). IT-TG-02/03 (nút duyệt ký HMAC) thuộc Sprint 4."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.conftest import OwnerSession, needs_db

pytestmark = needs_db
TOKEN = "123456789:AAH" + "x" * 32


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.fail_send = False

    def __call__(self, req: httpx.Request) -> httpx.Response:
        m = re.search(r"/bot([^/]+)/(\w+)$", req.url.path)
        assert m
        token, method = m.groups()
        if token != TOKEN:
            return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
        body = json.loads(req.content or b"{}")
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"id": 1, "username": "xuongtra_ai_bot"}})
        if method == "sendMessage":
            if self.fail_send:
                return httpx.Response(502, json={"ok": False, "description": "Bad Gateway"})
            self.sent.append(body)
            return httpx.Response(200, json={"ok": True, "result": {"message_id": len(self.sent)}})
        if method == "getUpdates":
            ups = [u for u in self.updates if u["update_id"] >= body.get("offset", 0)]
            return httpx.Response(200, json={"ok": True, "result": ups})
        return httpx.Response(404, json={"ok": False})


def msg(uid: int, chat_id: int, text: str, title: str = "Chủ xưởng") -> dict[str, Any]:
    return {"update_id": uid, "message": {"chat": {"id": chat_id, "type": "private", "first_name": title}, "text": text}}


@pytest.fixture
def fake_bot() -> AsyncIterator[FakeBot]:
    from app.telegram import bot

    fb = FakeBot()
    bot.transport = httpx.MockTransport(fb)
    yield fb
    bot.transport = None


async def test_tg05_token_flow_requires_reauth_and_validates(owner: OwnerSession, fake_bot: FakeBot) -> None:
    api = owner.api
    r = await api.put("/api/v1/telegram/token", json={"token": TOKEN}, headers=owner.h)
    assert r.json()["error"]["code"] == "REAUTH_REQUIRED"
    await owner.reauth()
    r = await api.put("/api/v1/telegram/token", json={"token": "987654321:BBB" + "y" * 32}, headers=owner.h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "TELEGRAM_TOKEN_INVALID"
    r = await api.put("/api/v1/telegram/token", json={"token": "khong-phai-token"}, headers=owner.h)
    assert r.status_code == 422
    r = await api.put("/api/v1/telegram/token", json={"token": TOKEN}, headers=owner.h)
    assert r.json() == {"configured": True, "bot_username": "xuongtra_ai_bot", "token_last4": "xxxx"}
    st = (await api.get("/api/v1/telegram")).text
    assert TOKEN not in st and "xuongtra_ai_bot" in st
    assert TOKEN not in (await api.get("/api/v1/events")).text


async def _configured(owner: OwnerSession) -> None:
    await owner.reauth()
    r = await owner.api.put("/api/v1/telegram/token", json={"token": TOKEN}, headers=owner.h)
    assert r.status_code == 200


async def test_tg05_link_code_flow(owner: OwnerSession, fake_bot: FakeBot) -> None:
    from app.core import db
    from app.workers import telegram as worker

    api = owner.api
    await _configured(owner)
    code = (await api.post("/api/v1/telegram/link-code", json={}, headers=owner.h)).json()
    assert re.fullmatch(r"\d{6}", code["code"]) and code["command"] == f"/ketnoi {code['code']}"
    wrong = "000000" if code["code"] != "000000" else "111111"
    fake_bot.updates = [msg(1, 555, f"/ketnoi {wrong}"), msg(2, 555, f"/ketnoi {code['code']}"), msg(3, 777, f"/ketnoi {code['code']}")]
    await worker.tick(TOKEN, set(), poll_s=0)
    chats = (await api.get("/api/v1/telegram")).json()["chats"]
    assert [c["chat_id"] for c in chats] == [555] and chats[0]["can_approve"] is False and chats[0]["title"] == "Chủ xưởng"
    texts = [(s["chat_id"], s["text"]) for s in fake_bot.sent]
    assert texts[0][0] == 555 and "không đúng" in texts[0][1]
    assert texts[1][0] == 555 and "Đã kết nối" in texts[1][1]
    assert texts[2][0] == 777 and "không đúng" in texts[2][1]  # mã đã dùng không dùng lại được
    async with db.engine().connect() as c:
        assert await db.scalar(c, "SELECT value FROM system_meta WHERE key = 'telegram_offset'") == "4"
    # chat được duyệt việc cần xác thực lại (đã xác thực ở trên, vẫn còn hạn 5 phút)
    r = await api.post("/api/v1/telegram/link-code", json={"can_approve": True}, headers=owner.h)
    assert r.status_code == 200


async def test_tg05_link_code_expires(conn: AsyncConnection, fake_bot: FakeBot) -> None:
    from app.core import db
    from app.telegram import service

    code, _ = await service.new_link_code(conn, "user:o@x.vn", False)
    await db.execute(conn, "UPDATE telegram_link_codes SET expires_at = now() - interval '1 minute'")
    assert await service.handle_update(conn, TOKEN, msg(1, 42, f"/ketnoi {code}")) == "bad_code"
    assert await db.scalar(conn, "SELECT count(*) FROM telegram_chats") == 0


async def test_tg01_unknown_chat_ignored_silently(conn: AsyncConnection, fake_bot: FakeBot) -> None:
    from app.core import db
    from app.telegram import service

    seen: set[int] = set()
    for i in range(3):
        assert await service.handle_update(conn, TOKEN, msg(i, 999, "/trangthai", "Người lạ"), seen) == "ignored"
    assert fake_bot.sent == []  # không trả lời người lạ
    n = await db.scalar(conn, "SELECT count(*) FROM audit_logs WHERE action = 'telegram.ignored'")
    assert n == 1  # ghi nhật ký một lần, không ngập


async def test_tg05_quiet_hours_and_urgent(conn: AsyncConnection, fake_bot: FakeBot) -> None:
    from app.core import db
    from app.domain import notify
    from app.telegram import service

    await db.execute(conn, "INSERT INTO telegram_chats(chat_id, title) VALUES (555, 'Chủ xưởng'), (556, 'Nhóm báo cáo')")
    await db.execute(conn, "UPDATE telegram_chats SET receives = ARRAY['report'] WHERE chat_id = 556")
    await notify.enqueue(conn, "publish", "Bài mới: https://xuongtramoc.vn/blog/tra-sen")
    await notify.enqueue(conn, "alert", "Hết ngân sách", urgent=True)
    night = datetime(2026, 11, 26, 16, 30, tzinfo=UTC)  # 23:30 giờ Việt Nam
    r = await service.dispatch(conn, TOKEN, night)
    assert r == {"sent": 1, "held": 1, "failed": 0, "no_recipient": 0}
    assert [(s["chat_id"], s["text"]) for s in fake_bot.sent] == [(555, "Hết ngân sách")]
    morning = datetime(2026, 11, 27, 1, 0, tzinfo=UTC)  # 08:00
    r = await service.dispatch(conn, TOKEN, morning)
    assert r["sent"] == 1 and fake_bot.sent[-1] == {**fake_bot.sent[-1], "chat_id": 555}
    assert 556 not in [s["chat_id"] for s in fake_bot.sent]  # nhóm chỉ nhận báo cáo


async def test_dispatch_retries_then_fails_and_no_recipient(conn: AsyncConnection, fake_bot: FakeBot) -> None:
    from app.core import db
    from app.domain import notify
    from app.telegram import service

    nid = await notify.enqueue(conn, "report", "Báo cáo tuần", urgent=True)
    assert (await service.dispatch(conn, TOKEN))["no_recipient"] == 1
    await db.execute(conn, "INSERT INTO telegram_chats(chat_id, title) VALUES (555, 'Chủ xưởng')")
    nid = await notify.enqueue(conn, "report", "Báo cáo tuần 2", urgent=True)
    fake_bot.fail_send = True
    for _ in range(service.MAX_ATTEMPTS):
        await service.dispatch(conn, TOKEN)
    row = await db.one(conn, "SELECT status, attempts, last_error FROM notifications WHERE id = :i", {"i": nid})
    assert row is not None and dict(row) == {"status": "failed", "attempts": 5, "last_error": "API_ERROR"}


async def test_tg04_outgoing_text_redacted(conn: AsyncConnection, fake_bot: FakeBot) -> None:
    from app.core import db
    from app.domain import notify
    from app.telegram import service

    await db.execute(conn, "INSERT INTO telegram_chats(chat_id, title) VALUES (555, 'Chủ xưởng')")
    await notify.enqueue(conn, "alert", "Khách 0912345678 / an@gmail.com lỗi khóa sk-ant-api03-abcdefghijklmnopqrstuv", urgent=True)
    await service.dispatch(conn, TOKEN)
    text = fake_bot.sent[0]["text"]
    assert "0912345678" not in text and "an@gmail.com" not in text and "abcdefghijklmnop" not in text


def test_quiet_window_math() -> None:
    from app.domain.store import Hours
    from app.telegram.service import in_quiet

    h = Hours()
    at = lambda hh, mm: datetime(2026, 11, 26, hh, mm, tzinfo=UTC)  # noqa: E731 — giờ UTC; VN = UTC+7
    assert in_quiet(at(15, 0), h)  # 22:00 VN
    assert in_quiet(at(23, 59), h)  # 06:59 VN
    assert not in_quiet(at(0, 0), h)  # 07:00 VN
    assert not in_quiet(at(14, 59), h)  # 21:59 VN
    assert not in_quiet(at(3, 0), Hours(quiet_start="07:00", quiet_end="07:00"))


async def test_send_test_and_chat_admin(owner: OwnerSession, fake_bot: FakeBot) -> None:
    from app.core import db

    api = owner.api
    assert (await api.post("/api/v1/telegram/test", headers=owner.h)).json()["error"]["code"] == "TELEGRAM_NOT_CONFIGURED"
    await _configured(owner)
    async with db.engine().begin() as c:
        await db.execute(c, "INSERT INTO telegram_chats(chat_id, title) VALUES (555, 'Chủ xưởng')")
    r = await api.post("/api/v1/telegram/test", headers=owner.h)
    assert r.json()["queued"] is True
    r = await api.patch("/api/v1/telegram/chats/555", json={"receives": ["alert", "report"], "enabled": False}, headers=owner.h)
    assert r.json()["receives"] == ["alert", "report"] and r.json()["enabled"] is False
    assert (await api.patch("/api/v1/telegram/chats/555", json={"receives": ["spam"]}, headers=owner.h)).status_code == 422
    assert (await api.delete("/api/v1/telegram/chats/555", headers=owner.h)).json() == {"ok": True}
    assert (await api.delete("/api/v1/telegram/chats/555", headers=owner.h)).status_code == 404
