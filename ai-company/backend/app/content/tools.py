"""Công cụ `site.*`: đọc catalog, gửi bản nháp, đưa bài vào lịch xuất bản, gỡ bài (ARCHITECTURE ADR-16).

`site.publish` KHÔNG đăng ngay: nó là cửa vào hàng chờ xuất bản, sau khi đủ các lớp chặn phía nền tảng:
1. Content Gate (tagger chạy TRƯỚC Policy Engine: chủ đề chỉ-người-duyệt hoặc rủi ro trung bình/cao → thẻ `publish_risky`
   → bắt buộc Owner duyệt, kể cả ở cấp L4; handler kiểm lại tất định với giá mới nhất, trượt thì thành bản nháp).
2. Review của cấp trên: bài phải là đầu ra đã được duyệt ở vòng review gần nhất của task (handler kiểm).
3. Owner duyệt (nếu có thẻ `publish_risky`): Tool Gateway tạo yêu cầu duyệt gắn digest, đồ thị dừng chờ.
4. Lịch đăng + hạn mức (`publishing.enqueue` xếp khung giờ). 5. Website kiểm tra lần cuối khi đến giờ đăng.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.content import gate as cg
from app.content import publishing
from app.core import db
from app.core.errors import AppError
from app.domain.approvals import digest
from app.integrations import website
from app.memory.textnorm import fold
from app.tools.spec import ToolCtx

_risk_cache: dict[str, tuple[str, str]] = {}


def _err(e: AppError) -> Exception:
    from app.tools.gateway import ToolError

    return ToolError(e.code, e.message)


class CatalogIn(BaseModel):
    q: str | None = Field(default=None, max_length=200, description="lọc theo tên sản phẩm (có dấu hay không đều được)")
    product_id: int | None = None


class CatalogOut(BaseModel):
    products: list[dict[str, Any]]
    published_faqs: list[str]
    published_blogs: list[str]


async def catalog(ctx: ToolCtx, inp: CatalogIn) -> CatalogOut:
    try:
        cat = await website.catalog(ctx.conn)
    except AppError as e:
        raise _err(e) from e
    keep = ("id", "name", "category_id", "short_desc", "ingredients", "usage_guide", "storage_guide", "allergens", "info_version")
    prods = []
    for p in cat.get("products") or []:
        if inp.product_id and int(p["id"]) != inp.product_id:
            continue
        if inp.q and fold(inp.q) not in fold(str(p.get("name", ""))):
            continue
        d = {k: p.get(k) for k in keep}
        d["skus"] = [{"variant_label": s.get("variant_label"), "price": s.get("list_price")} for s in p.get("skus") or []]
        prods.append(d)
    return CatalogOut(
        products=prods[:30],
        published_faqs=[str(f.get("question")) for f in cat.get("published_faqs") or []][:200],
        published_blogs=[str(b.get("title")) for b in cat.get("published_blogs") or []][:200],
    )


class ArticleIn(BaseModel):
    kind: Literal["faq", "blog"]
    title: str = Field(min_length=5, max_length=200)
    body: str = Field(min_length=40, max_length=60_000)
    meta_description: str | None = Field(default=None, max_length=300)
    keywords: str | None = Field(default=None, max_length=500)
    product_id: int | None = None
    category_id: int | None = None


class DraftOut(BaseModel):
    status: str
    result: str | None = None
    error: str | None = None


async def _source_refs(conn: Any, product_id: int | None) -> list[dict[str, int]]:
    if not product_id:
        return []
    cat = await website.catalog(conn)
    for p in cat.get("products") or []:
        if int(p["id"]) == product_id:
            return [{"product_id": product_id, "info_version": int(p.get("info_version") or 0)}]
    raise AppError("PRODUCT_NOT_FOUND", f"Website không có sản phẩm #{product_id} (hoặc đã ngừng bán).", 422)


async def draft(ctx: ToolCtx, inp: ArticleIn) -> DraftOut:
    try:
        refs = await _source_refs(ctx.conn, inp.product_id)
        r = await website.draft(
            ctx.conn,
            [
                {
                    "client_ref": f"co:draft:{ctx.idempotency_key}"[:80],
                    "kind": inp.kind,
                    "data": {**inp.model_dump(exclude={"kind"}), "source_refs": refs, "generated_by": f"co:{ctx.agent_key}"},
                }
            ],
        )
    except AppError as e:
        raise _err(e) from e
    res = (r.get("results") or [{}])[0]
    return DraftOut(status=str(res.get("status")), result=res.get("result"), error=res.get("error"))


class PublishOut(BaseModel):
    status: Literal["scheduled", "blocked"]
    queue_id: str
    slot_at: str | None = None
    reasons: list[str] = Field(default_factory=list)
    needs_owner: list[str] = Field(default_factory=list)


async def tag_publish(conn: Any, inp: ArticleIn, agent_key: str, task_id: str | None) -> tuple[str, ...]:
    """Lớp 1 + 3 trước Policy Engine: chủ đề chỉ-người-duyệt hoặc rủi ro chưa thấp → `publish_risky` (bắt buộc Owner duyệt)."""
    key = digest(inp.model_dump())
    r = await cg.evaluate(
        conn, kind=inp.kind, title=inp.title, body=inp.body, meta=inp.meta_description or "", product_ids=[inp.product_id] if inp.product_id else None,
        use_classifier=key not in _risk_cache, agent_key=agent_key, task_id=task_id,
    )  # fmt: skip
    if key in _risk_cache:
        r.risk, r.risk_reason = _risk_cache[key]  # type: ignore[assignment]
    elif r.ok:
        _risk_cache[key] = (r.risk, r.risk_reason)
        if len(_risk_cache) > 500:
            _risk_cache.pop(next(iter(_risk_cache)))
    return r.tags if r.ok else ()  # bài sẽ bị chặn thì không hỏi Owner: handler đưa thành bản nháp


async def _reviewed(conn: Any, task_id: str | None, inp: ArticleIn) -> None:
    """Lớp 2: bài phải là đầu ra đã được duyệt ở vòng review gần nhất của task."""
    if not task_id:
        raise AppError("REVIEW_REQUIRED", "Chỉ đăng được bài thuộc một việc đã qua review.", 403)
    t = await db.one(conn, "SELECT requires_review, output_data FROM tasks WHERE id = CAST(:t AS uuid)", {"t": task_id})
    rv = await db.one(conn, "SELECT verdict FROM task_reviews WHERE task_id = CAST(:t AS uuid) ORDER BY round DESC LIMIT 1", {"t": task_id})
    if t is None or not t["requires_review"] or rv is None or rv["verdict"] != "approve":
        raise AppError("REVIEW_REQUIRED", "Bài chưa được cấp trên duyệt (review) nên chưa đăng được.", 403)
    out = t["output_data"] or {}
    if (str(out.get("title", "")).strip(), str(out.get("body", "")).strip()) != (inp.title.strip(), inp.body.strip()):
        raise AppError("REVIEW_MISMATCH", "Nội dung đăng khác bản đã được review.", 403)


async def publish(ctx: ToolCtx, inp: ArticleIn) -> PublishOut:
    try:
        await _reviewed(ctx.conn, ctx.task_id, inp)
        refs = await _source_refs(ctx.conn, inp.product_id)
        g = await cg.evaluate(
            ctx.conn, kind=inp.kind, title=inp.title, body=inp.body, meta=inp.meta_description or "",
            product_ids=[inp.product_id] if inp.product_id else None, fresh_catalog=True, use_classifier=False,
        )  # fmt: skip
        approval = await db.scalar(
            ctx.conn, "SELECT approval_id FROM tool_invocations WHERE idempotency_key = :k", {"k": ctx.idempotency_key}
        )
        data = {**inp.model_dump(exclude={"kind"}), "source_refs": refs}
        item = await publishing.enqueue(
            ctx.conn,
            key=ctx.idempotency_key,
            agent_key=ctx.agent_key,
            task_id=ctx.task_id,
            kind=inp.kind,
            data=data,
            gate=g.as_dict(),
            status="scheduled" if g.ok else "blocked",
            approval_id=str(approval) if approval else None,
        )
        if not g.ok:
            await publishing._block(ctx.conn, item, g.blocked, "Content Gate")
            return PublishOut(status="blocked", queue_id=str(item["id"]), reasons=g.blocked)
    except AppError as e:
        raise _err(e) from e
    slot = item["slot_at"]
    return PublishOut(
        status="scheduled",
        queue_id=str(item["id"]),
        slot_at=slot.astimezone(publishing.VN).strftime("%H:%M %d/%m/%Y") if slot else None,
        needs_owner=g.topics,
    )


class UnpublishIn(BaseModel):
    queue_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    reason: str = Field(min_length=5, max_length=500)


class UnpublishOut(BaseModel):
    status: str


async def unpublish(ctx: ToolCtx, inp: UnpublishIn) -> UnpublishOut:
    try:
        it = await publishing.unpublish(ctx.conn, inp.queue_id, actor=f"agent:{ctx.agent_key}", reason=inp.reason)
    except AppError as e:
        raise _err(e) from e
    return UnpublishOut(status=str(it.get("status")))
