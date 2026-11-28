"""Website moctam giả cho test xuất bản (httpx.MockTransport): catalog, bản nháp, xuất bản có hạn mức ngày, gỡ bài.

Bắt chước đúng hợp đồng của web/app/src/Domain/AiPublisher.php (mã lỗi, hạn mức đếm ở website); test với website THẬT
(PHP + MariaDB) nằm ở test_publishing.py::test_it_pub_01_02_real_website, chạy khi có AICO_TEST_WEBSITE_URL.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

BASE = "https://web.test"
PRODUCTS = [
    {
        "id": 1,
        "name": "Trà gừng mật ong",
        "category_id": 1,
        "info_version": 3,
        "skus": [{"variant_label": "Hộp 20 túi", "list_price": 65000}],
    },
    {"id": 2, "name": "Trà sen Tây Hồ", "category_id": 1, "info_version": 1, "skus": [{"variant_label": "Hộp 100g", "list_price": 180000}]},
]


class FakeSite:
    def __init__(self) -> None:
        self.products = json.loads(json.dumps(PRODUCTS))
        self.limit = {"faq": 3, "blog": 1}
        self.published: dict[str, dict[str, Any]] = {}  # client_ref → bài
        self.drafts: list[dict[str, Any]] = []
        self.unpublished: list[int] = []
        self.calls: list[str] = []
        self.down = False

    def _err(self, status: int, code: str, msg: str) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": code, "message": msg}})

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(f"{req.method} {req.url.path}")
        if self.down:
            raise httpx.ConnectError("website tắt")
        auth = req.headers.get("authorization", "")
        body = json.loads(req.content) if req.content else {}
        path = req.url.path
        if path == "/api/sync/catalog":
            if auth != "Bearer key-read-xxxxxxxxxxxxxxxxxxxx":
                return self._err(403, "FORBIDDEN", "Khóa không có quyền catalog:read.")
            return httpx.Response(200, json={"products": self.products, "published_faqs": [], "published_blogs": []})
        if path == "/api/sync/drafts":
            if auth != "Bearer key-drafts-xxxxxxxxxxxxxxxxxx":
                return self._err(403, "FORBIDDEN", "Khóa không có quyền drafts:write.")
            self.drafts += body["items"]
            return httpx.Response(
                200,
                json={"results": [{"client_ref": i["client_ref"], "status": "accepted", "result": "content:900"} for i in body["items"]]},
            )
        if path in ("/api/sync/publish", "/api/sync/unpublish") and auth != "Bearer key-publish-xxxxxxxxxxxxxxxxx":
            return self._err(403, "FORBIDDEN", "Khóa không có quyền content:publish.")
        if path == "/api/sync/publish":
            ref = body["client_ref"]
            if ref in self.published:
                return httpx.Response(200, json={**self.published[ref], "duplicate": True})
            kind = body["kind"]
            used = len([p for p in self.published.values() if p["kind"] == kind])
            if used >= self.limit[kind]:
                return self._err(429, "AI_PUBLISH_QUOTA", f"Đã hết hạn mức AI xuất bản {kind} hôm nay ({used}/{self.limit[kind]}).")
            for r in body["data"].get("source_refs") or []:
                cur = next(p["info_version"] for p in self.products if p["id"] == r["product_id"])
                if cur != r["info_version"]:
                    return self._err(409, "SOURCE_OUTDATED", "Thông tin sản phẩm đã đổi.")
            cid = 100 + len(self.published)
            item = {"content_id": cid, "kind": kind, "status": "published", "url": f"{BASE}/{'hoi-dap' if kind == 'faq' else 'bai-' + str(cid)}.html",
                    "title": body["data"]["title"]}  # fmt: skip
            self.published[ref] = item
            return httpx.Response(200, json=item)
        if path == "/api/sync/unpublish":
            self.unpublished.append(int(body["content_id"]))
            return httpx.Response(200, json={"content_id": body["content_id"], "status": "unpublished"})
        return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "?"}})


@pytest.fixture
async def site(office: object) -> Any:
    from app.core import db
    from app.domain import store
    from app.integrations import website

    async with db.engine().begin() as c:
        await store.put_setting(c, "website", store.Website(base_url=BASE), "test")
        await store.put_secret(c, website.KEYS["read"], "key-read-xxxxxxxxxxxxxxxxxxxx", "test")
        await store.put_secret(c, website.KEYS["drafts"], "key-drafts-xxxxxxxxxxxxxxxxxx", "test")
        await store.put_secret(c, website.KEYS["publish"], "key-publish-xxxxxxxxxxxxxxxxx", "test")
    fake = FakeSite()
    website.transport = httpx.MockTransport(fake)
    website.clear_cache()
    yield fake
    website.transport = None
    website.clear_cache()
