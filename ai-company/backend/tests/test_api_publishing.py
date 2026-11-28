"""API trang Xuất bản và Cài đặt → Website (Sprint 4b): kết nối website, khóa không lộ, lịch đăng, Content Gate, tạm dừng."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import OwnerSession
from tests.sitekit import FakeSite

pytestmark = pytest.mark.asyncio
V = "/api/v1"


async def test_website_connection_keys_never_returned(owner: OwnerSession) -> None:
    from app.integrations import website

    api, h = owner.api, owner.h
    w = (await api.get(f"{V}/website")).json()
    assert w["base_url"] == "" and w["keys"] == {"read": None, "drafts": None, "publish": None}
    r = await api.post(f"{V}/website/test", headers=h)
    assert r.json()["ok"] is False and r.json()["code"] == "NOT_CONFIGURED"
    r = await api.put(f"{V}/website", json={"base_url": "https://web.test"}, headers=h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_REQUIRED"  # đổi nơi gửi khóa: phải xác thực lại
    await owner.reauth()
    r = await api.put(f"{V}/website", json={"base_url": "javascript:alert(1)"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEBSITE_URL_INVALID"
    assert (await api.put(f"{V}/website", json={"base_url": "https://web.test/"}, headers=h)).json()["base_url"] == "https://web.test"
    for kind, key in (("read", "key-read-xxxxxxxxxxxxxxxxxxxx"), ("publish", "key-publish-xxxxxxxxxxxxxxxxx")):
        r = await api.put(f"{V}/website/keys/{kind}", json={"api_key": key}, headers=h)
        assert r.json() == {"kind": kind, "last4": key[-4:]}
    body = (await api.get(f"{V}/website")).text
    assert "key-read" not in body and "key-publish" not in body and '"last4":"xxxx"' in body
    fake = FakeSite()
    website.transport = httpx.MockTransport(fake)
    website.clear_cache()
    try:
        r = (await api.post(f"{V}/website/test", headers=h)).json()
        assert r == {"ok": True, "products": 2, "faqs": 0, "blogs": 0}
    finally:
        website.transport = None
        website.clear_cache()
    assert (await api.delete(f"{V}/website/keys/publish", headers=h)).json()["deleted"] is True
    assert (await api.get(f"{V}/website")).json()["keys"]["publish"] is None


async def test_schedule_gate_and_pause(owner: OwnerSession) -> None:
    api, h = owner.api, owner.h
    s = (await api.get(f"{V}/publishing/settings")).json()
    assert s["phase"] == 1 and s["window_start"] == "07:00" and s["window_end"] == "21:30" and s["upcoming"] == []
    assert s["phases"]["1"]["faq"]["times"] == ["11:30"] and s["phases"]["1"]["blog"]["weekdays"] == [2, 6]
    base = {"phase": 2, "auto_progress": False, "window_start": "07:00", "window_end": "21:30", "min_gap_hours": 3}
    r = await api.put(f"{V}/publishing/settings", json={**base, "window_start": "22:00"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "SETTINGS_INVALID"
    r = await api.put(f"{V}/publishing/settings", json={**base, "holidays": ["2027-02-06"]}, headers=h)
    assert r.status_code == 200 and r.json()["phase"] == 2 and r.json()["holidays"] == ["2027-02-06"] and r.json()["phase_since"]
    lst = (await api.get(f"{V}/publishing?group=queue")).json()
    assert lst["phase"] == 2 and lst["paused"] is False and lst["items"] == []

    r = (
        await api.post(f"{V}/publishing/gate/test", json={"title": "Trà gừng", "body": "Uống mỗi ngày giúp chữa bệnh cảm."}, headers=h)
    ).json()
    assert r["ok"] is False and any("chữa bệnh" in b for b in r["blocked"])
    r = (await api.post(f"{V}/publishing/gate/test", json={"title": "Trà gừng có hợp bà bầu?", "body": "x" * 80}, headers=h)).json()
    assert r["ok"] is True and r["needs_owner"] is True and "sức khỏe" in r["topics"]
    g = (await api.get(f"{V}/publishing/gate")).json()
    g["risk_phrases"].append("thần dược")
    assert (await api.put(f"{V}/publishing/gate", json=g, headers=h)).status_code == 200
    r = (
        await api.post(f"{V}/publishing/gate/test", json={"title": "Trà", "body": "Đúng là thần dược của mùa đông, ấm áp."}, headers=h)
    ).json()
    assert r["ok"] is False

    assert (await api.post(f"{V}/publishing/pause", json={"paused": True, "reason": "đi vắng"}, headers=h)).json() == {"paused": True}
    lst = (await api.get(f"{V}/publishing?group=queue")).json()
    assert lst["paused"] is True and lst["paused_reason"] == "đi vắng"
    assert (await api.post(f"{V}/publishing/pause", json={"paused": False}, headers=h)).json() == {"paused": False}
    from app.core import db

    async with db.engine().connect() as c:
        acts = [r["action"] for r in await db.all_(c, "SELECT action FROM audit_logs ORDER BY id")]
    assert {"publish.schedule_changed", "content_gate.changed"} <= set(acts)
