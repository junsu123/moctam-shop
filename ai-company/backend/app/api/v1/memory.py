"""API trí nhớ cho Control Center: xem (lọc theo loại, phạm vi, nguồn), chi tiết + ai đã truy hồi, thêm kiến thức của Owner,
cho nghỉ hưu, thử truy hồi như một agent ("Giải thích căn cứ"), nhúng vector ngay."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db, security
from app.core.errors import AppError
from app.gateway import models as gw
from app.memory import embedding, retrieval, store, textnorm

router = APIRouter(tags=["memory"])
Owner = Depends(security.require_role("owner", "manager"))
Viewer = Depends(security.current_user)
COLS = (
    "m.id, m.owner_scope, m.type, m.title, left(m.content, 400) AS snippet, m.source_ref, m.source_trust, m.confidence, m.verification_status, "
    "m.valid_from, m.valid_to, m.usefulness, m.created_at, m.created_by_principal, m.metadata, "
    "(SELECT count(*) FROM memory_access_log l WHERE l.memory_id = m.id) AS access_count"
)


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.get("/memory/stats")
async def memory_stats(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    by_type = {
        r["type"]: int(r["n"])
        for r in await db.all_(conn, "SELECT type, count(*) n FROM agent_memories WHERE verification_status <> 'retired' GROUP BY type")
    }
    by_scope = [
        dict(r)
        for r in await db.all_(
            conn,
            "SELECT owner_scope AS scope, count(*) n FROM agent_memories WHERE verification_status <> 'retired' GROUP BY owner_scope ORDER BY n DESC",
        )
    ]
    em = await gw.embed_model(conn)
    total = sum(by_type.values())
    pending = await embedding.pending_count(conn, em.id) if em else total
    configured = bool(
        em and em.secret_name and await db.scalar(conn, "SELECT EXISTS (SELECT 1 FROM secrets WHERE name = :n)", {"n": em.secret_name})
    )
    return {
        "total": total,
        "by_type": by_type,
        "by_scope": by_scope,
        "embedding": {
            "model": em.model_name if em else None,
            "dims": em.dims if em else None,
            "configured": configured,
            "embedded": total - pending,
            "pending": pending,
        },
        "retrievals_today": int(await db.scalar(conn, "SELECT count(*) FROM memory_access_log WHERE at >= date_trunc('day', now())") or 0),
    }


@router.get("/memory")
async def memory_list(
    scope: str | None = None,
    type: Literal["working", "episodic", "semantic", "procedural"] | None = None,  # noqa: A002
    trust: Literal["owner", "internal", "verified_external", "unverified_external"] | None = None,
    status: Literal["active", "verified", "candidate", "deprecated", "retired", "usable"] | None = "usable",
    agent: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    conn: AsyncConnection = Depends(db.get_db),
    cur: security.Current = Viewer,
) -> dict[str, Any]:
    where: list[str] = ["true"]
    p: dict[str, Any] = {}
    if agent:
        where.append("m.owner_scope = ANY(:scopes)")
        p["scopes"] = await store.scopes_for(conn, f"agent:{agent}")
    if scope:
        where.append("m.owner_scope = :scope")
        p["scope"] = scope
    if type:
        where.append("m.type = :type")
        p["type"] = type
    if trust:
        where.append("m.source_trust = :trust")
        p["trust"] = trust
    if status == "usable":
        where.append("m.verification_status IN ('verified','active') AND (m.valid_to IS NULL OR m.valid_to > now())")
    elif status:
        where.append("m.verification_status = :st")
        p["st"] = status
    if q and (terms := textnorm.query_terms(q)):
        where.append("m.tsv @@ to_tsquery('simple', :tsq)")
        p["tsq"] = " & ".join(terms)
    w = " AND ".join(where)
    total = await db.scalar(conn, f"SELECT count(*) FROM agent_memories m WHERE {w}", p)  # noqa: S608
    rows = await db.all_(
        conn,
        f"SELECT {COLS} FROM agent_memories m WHERE {w} ORDER BY m.created_at DESC LIMIT :l OFFSET :o",  # noqa: S608
        {**p, "l": limit, "o": offset},
    )
    return {"total": int(total or 0), "items": [dict(r) for r in rows]}


@router.get("/memory/{memory_id}")
async def memory_detail(memory_id: str, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Viewer) -> dict[str, Any]:
    row = await db.one(
        conn,
        "SELECT m.*, (SELECT count(*) FROM memory_access_log l WHERE l.memory_id = m.id) AS access_count "
        "FROM agent_memories m WHERE m.id = CAST(:i AS uuid)",
        {"i": memory_id},
    )
    if row is None:
        raise AppError("MEMORY_NOT_FOUND", "Không có mục trí nhớ này.", 404)
    d = {k: v for k, v in dict(row).items() if k not in ("tsv", "search_text")}
    for table in ("episodic_memories", "semantic_memories", "procedural_memories"):
        sub = await db.one(conn, f"SELECT * FROM {table} WHERE memory_id = CAST(:i AS uuid)", {"i": memory_id})  # noqa: S608
        if sub:
            d["detail"] = {k: v for k, v in dict(sub).items() if k != "memory_id"}
    d["access"] = [
        dict(r)
        for r in await db.all_(
            conn,
            "SELECT at, principal, task_id, purpose, rank, score, used_in_output FROM memory_access_log WHERE memory_id = CAST(:i AS uuid) "
            "ORDER BY at DESC LIMIT 50",
            {"i": memory_id},
        )
    ]
    d["embeddings"] = [
        r["model_id"]
        for r in await db.all_(conn, "SELECT model_id FROM memory_embeddings WHERE memory_id = CAST(:i AS uuid)", {"i": memory_id})
    ]
    return d


class KnowledgeIn(BaseModel):
    scope: str = Field(pattern=r"^(company|owner_only|dept:(executive|marketing|sales|growth|technology))$")
    type: Literal["semantic", "procedural"] = "semantic"
    title: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=5, max_length=8000)
    category: Literal["product", "brand", "goal", "strategy", "policy", "other"] = "other"
    valid_to: datetime | None = None
    source_ref: str | None = Field(default=None, max_length=500)


@router.post("/memory")
async def memory_add(
    body: KnowledgeIn, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    """Owner thêm kiến thức (đã là người duyệt, nên vào thẳng trạng thái active, độ tin cậy cao nhất)."""
    mid, new = await store.add_knowledge(
        conn,
        principal=cur.actor,
        scope=body.scope,
        type_=body.type,
        title=body.title,
        content=body.content,
        trust="owner",
        confidence=1.0,
        metadata={"category": body.category},
        source_ref=body.source_ref,
        valid_to=body.valid_to,
    )
    if not new:
        raise AppError("MEMORY_DUPLICATE", "Phạm vi này đã có mục trí nhớ cùng nội dung.", 409)
    await audit.record(
        conn, cur.actor, "memory.added", f"memory:{mid}", {"scope": body.scope, "title": body.title}, request_id=_rid(request)
    )
    return {"id": mid}


class RetireIn(BaseModel):
    reason: str = Field(default="", max_length=300)


@router.post("/memory/{memory_id}/retire")
async def memory_retire(
    memory_id: str, body: RetireIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, bool]:
    await store.retire(conn, memory_id, cur.actor, body.reason or None)
    return {"ok": True}


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    types: list[Literal["working", "episodic", "semantic", "procedural"]] | None = None


@router.post("/agents/{key}/memory/search")
async def memory_preview(
    key: str, body: SearchIn, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    """Thử truy hồi đúng như agent sẽ thấy (cùng phạm vi, RLS, trọng số, ngân sách). Không ghi vào nhật ký truy hồi của agent."""
    if not await db.scalar(conn, "SELECT EXISTS (SELECT 1 FROM agents WHERE agent_key = :k)", {"k": key}):
        raise AppError("AGENT_NOT_FOUND", "Không có agent này.", 404)
    r = await retrieval.retrieve(conn, key, body.query, types=list(body.types) if body.types else None, purpose="owner_preview", log=False)
    return r.as_dict()


@router.post("/memory/embed")
async def memory_embed(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> dict[str, Any]:
    rep = await embedding.embed_pending(conn, limit=256)
    return rep.__dict__
