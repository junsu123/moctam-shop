"""Gọi API đồng bộ của website moctam (docs/API.md của repo gốc). Mỗi loại việc một khóa riêng, ít quyền nhất:

- `website.read_key` (catalog:read): đọc sản phẩm, giá, FAQ đã đăng để soạn bài và để Content Gate đối chiếu.
- `website.drafts_key` (drafts:write): gửi bản nháp, luôn vào hàng chờ duyệt trên website.
- `website.publish_key` (content:publish): AI tự xuất bản/gỡ FAQ/blog. Website tự đếm hạn mức ngày và khung giờ (lớp chặn cuối).

Chưa cấu hình địa chỉ hoặc khóa → AppError NOT_CONFIGURED. Lỗi của website giữ nguyên mã (vd AI_PUBLISH_QUOTA).
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import AppError
from app.domain import store

transport: httpx.AsyncBaseTransport | None = None  # kiểm thử thay bằng MockTransport
KEYS = {"read": "website.read_key", "drafts": "website.drafts_key", "publish": "website.publish_key"}
CATALOG_TTL_S = 600
_cache: dict[str, Any] = {}


async def base_url(conn: AsyncConnection) -> str:
    w = await store.get_setting(conn, "website")
    assert isinstance(w, store.Website)
    return w.base_url.rstrip("/")


async def call(conn: AsyncConnection, method: str, path: str, key: str, body: dict[str, Any] | None = None, timeout_s: float = 20) -> Any:
    base = await base_url(conn)
    secret = await store.get_secret(conn, KEYS[key])
    if not base or not secret:
        raise AppError("NOT_CONFIGURED", "Chưa kết nối website (Cài đặt → Website: địa chỉ và khóa API).", 503)
    try:
        async with httpx.AsyncClient(timeout=timeout_s, transport=transport) as c:
            r = await c.request(method, base + path, json=body, headers={"Authorization": f"Bearer {secret}", "Accept": "application/json"})
    except httpx.TimeoutException as e:
        raise AppError("WEBSITE_TIMEOUT", "Website không phản hồi.", 504) from e
    except httpx.HTTPError as e:
        raise AppError("WEBSITE_UNREACHABLE", f"Không kết nối được website: {type(e).__name__}", 502) from e
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        err = data.get("error") if isinstance(data, dict) else None
        code = str(err.get("code")) if isinstance(err, dict) and err.get("code") else f"WEBSITE_HTTP_{r.status_code}"
        msg = str(err.get("message")) if isinstance(err, dict) and err.get("message") else f"Website trả lỗi HTTP {r.status_code}."
        if r.status_code in (401, 403) and code in ("UNAUTHENTICATED", "FORBIDDEN"):
            msg = f"Website từ chối khóa API ({code}): {msg}"
        raise AppError(code, msg[:500], 502 if r.status_code >= 500 else r.status_code)
    return data


async def catalog(conn: AsyncConnection, *, fresh: bool = False) -> dict[str, Any]:
    """Danh mục đã xác thực của website. Giữ 10 phút; `fresh=True` khi cần đối chiếu giá ngay trước giờ đăng."""
    now = time.monotonic()
    if not fresh and _cache.get("at") and now - _cache["at"] < CATALOG_TTL_S:
        return dict(_cache["data"])
    data = await call(conn, "GET", "/api/sync/catalog", "read")
    _cache.update({"at": now, "data": data})
    return dict(data)


def clear_cache() -> None:
    _cache.clear()


def prices(cat: dict[str, Any], product_ids: list[int] | None = None) -> dict[int, set[int]]:
    """Giá bán hiện hành theo sản phẩm (mọi SKU)."""
    out: dict[int, set[int]] = {}
    for p in cat.get("products") or []:
        pid = int(p.get("id") or 0)
        if product_ids and pid not in product_ids:
            continue
        for s in p.get("skus") or []:
            for k in ("list_price", "price"):
                if s.get(k):
                    out.setdefault(pid, set()).add(int(s[k]))
    return out


async def publish(conn: AsyncConnection, item: dict[str, Any]) -> dict[str, Any]:
    return dict(await call(conn, "POST", "/api/sync/publish", "publish", item))


async def unpublish(conn: AsyncConnection, content_id: int, reason: str) -> dict[str, Any]:
    return dict(await call(conn, "POST", "/api/sync/unpublish", "publish", {"content_id": content_id, "reason": reason}))


async def draft(conn: AsyncConnection, items: list[dict[str, Any]]) -> dict[str, Any]:
    return dict(await call(conn, "POST", "/api/sync/drafts", "drafts", {"items": items}))
