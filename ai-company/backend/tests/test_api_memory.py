"""API trí nhớ cho Control Center."""

from __future__ import annotations

import pytest

from tests.conftest import OwnerSession, needs_db

pytestmark = [needs_db, pytest.mark.usefixtures("synced")]


async def test_owner_knowledge_list_detail_preview_retire(owner: OwnerSession) -> None:
    from app.core import db
    from app.memory import retrieval, store

    api = owner.api
    r = await api.post(
        "/api/v1/memory",
        json={
            "scope": "company",
            "title": "Chính sách đổi trả",
            "content": "Đổi trả trong 7 ngày nếu hộp trà còn nguyên tem",
            "category": "policy",
        },
        headers=owner.h,
    )
    company = r.json()["id"]
    dup = await api.post(
        "/api/v1/memory",
        json={"scope": "company", "title": "Chính sách đổi trả", "content": "Đổi trả trong 7 ngày nếu hộp trà còn nguyên tem"},
        headers=owner.h,
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "MEMORY_DUPLICATE"
    secret = (
        await api.post(
            "/api/v1/memory",
            json={"scope": "owner_only", "title": "Biên lợi nhuận", "content": "Biên lợi nhuận hộp trà quà Tết 45%"},
            headers=owner.h,
        )
    ).json()["id"]
    bad = await api.post(
        "/api/v1/memory",
        json={"scope": "agent:seo_agent", "title": "x x x", "content": "Owner không ghi vào vùng riêng của agent"},
        headers=owner.h,
    )
    assert bad.status_code == 422
    async with db.engine().begin() as c:
        own = await store.remember_episode(
            c, "customer_agent", title="Khách hỏi đổi trả", content="Khách hỏi đổi trả hộp trà bị móp", task_type="reply"
        )
        await retrieval.retrieve(c, "customer_agent", "đổi trả hộp trà", task_id="t-9", purpose="reply")

    lst = (await api.get("/api/v1/memory")).json()
    assert lst["total"] == 3 and {i["owner_scope"] for i in lst["items"]} == {"company", "owner_only", "agent:customer_agent"}
    assert (await api.get("/api/v1/memory?scope=company")).json()["total"] == 1
    assert (await api.get("/api/v1/memory?type=episodic")).json()["items"][0]["id"] == own
    assert (await api.get("/api/v1/memory?q=doi tra")).json()["total"] == 2
    seo = (await api.get("/api/v1/memory?agent=seo_agent")).json()
    assert [i["id"] for i in seo["items"]] == [company]  # SEO không thấy vùng riêng của CSKH hay của Owner

    d = (await api.get(f"/api/v1/memory/{own}")).json()
    assert (
        d["detail"]["task_type"] == "reply" and d["access"][0]["principal"] == "agent:customer_agent" and d["access"][0]["task_id"] == "t-9"
    )
    assert d["access_count"] == 1

    p = (await api.post("/api/v1/agents/content_agent/memory/search", json={"query": "đổi trả hộp trà"}, headers=owner.h)).json()
    found = [i["memory_id"] for i in p["items"]]
    assert company in found and secret not in found and own not in found
    assert p["vector_search"] == "not_configured" and "company" in p["scopes"]
    assert {"rrf", "w_trust", "kw_rank", "score", "category"} <= set(p["items"][0])

    stats = (await api.get("/api/v1/memory/stats")).json()
    assert stats["total"] == 3 and stats["by_type"] == {"semantic": 2, "episodic": 1}
    assert stats["embedding"] == {"model": "text-embedding-3-small", "dims": 512, "configured": False, "embedded": 0, "pending": 3}
    assert (await api.post("/api/v1/memory/embed", headers=owner.h)).json()["status"] == "not_configured"

    assert (await api.post(f"/api/v1/memory/{company}/retire", json={"reason": "Đổi chính sách"}, headers=owner.h)).json() == {"ok": True}
    assert (await api.get("/api/v1/memory?scope=company")).json()["total"] == 0
    assert (await api.get("/api/v1/memory?scope=company&status=retired")).json()["total"] == 1
    assert (await api.post(f"/api/v1/memory/{company}/retire", json={}, headers=owner.h)).status_code == 404
    ev = [e["action"] for e in (await api.get("/api/v1/events")).json() if e["source"] == "audit"]
    assert {"memory.added", "memory.retired"} <= set(ev)


async def test_memory_requires_login_and_owner(api) -> None:  # type: ignore[no-untyped-def]
    assert (await api.get("/api/v1/memory")).status_code == 401
    assert (await api.post("/api/v1/agents/seo_agent/memory/search", json={"query": "x"})).status_code == 401
