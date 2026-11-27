"""Truy hồi trí nhớ (BRAIN_SPEC §5).

1. Lọc trước (RLS + phạm vi, loại, trạng thái đã kiểm chứng, còn hiệu lực, metadata), xếp hạng sau.
2. Hai danh sách ứng viên (~50 mục mỗi danh sách): theo từ khóa (văn bản bỏ dấu, tsvector + trigram để chịu lỗi gõ)
   và theo vector (cosine, HNSW của model embedding đang bật).
3. Ghép: score = RRF(k=60) × w_recency(loại) × (0,5 + 0,5·confidence) × w_trust(nguồn).
   Bán rã: episodic 60 ngày; semantic theo valid_to (đã lọc); procedural không giảm.
4. Đóng gói theo ngân sách token và tỉ lệ share_ratio của bộ não; loại mục gần trùng (MMR, Jaccard trên từ).
5. Mỗi mục trả về có memory_id để trích dẫn; lượt truy hồi được ghi vào memory_access_log.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.core.errors import AppError
from app.memory import textnorm
from app.memory.store import acting_as, scopes_for

RRF_K = 60
HALF_LIFE_DAYS = {"episodic": 60.0}
TRUST_W = {"owner": 1.0, "internal": 0.9, "verified_external": 0.8, "unverified_external": 0.5}
CATEGORIES = ("procedural", "experience", "semantic", "shared")
DEFAULT_SHARE = {"procedural": 0.2, "experience": 0.25, "semantic": 0.35, "shared": 0.2}
MMR_LAMBDA = 0.7
NEAR_DUP = 0.85


@dataclass
class Item:
    memory_id: str
    type: str
    scope: str
    title: str
    content: str
    source_ref: str | None
    source_trust: str
    confidence: float
    created_at: datetime
    category: str
    tokens: int
    kw_rank: int | None = None
    vec_rank: int | None = None
    rrf: float = 0.0
    w_recency: float = 1.0
    w_conf: float = 1.0
    w_trust: float = 1.0
    score: float = 0.0
    terms: set[str] = field(default_factory=set, repr=False)


@dataclass
class Result:
    items: list[Item]
    considered: int
    used_tokens: int
    budget_tokens: int
    vector_search: str  # "used" | "not_configured" | "skipped" | "error: …"
    scopes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": [{k: v for k, v in asdict(i).items() if k != "terms"} for i in self.items],
            "considered": self.considered,
            "used_tokens": self.used_tokens,
            "budget_tokens": self.budget_tokens,
            "vector_search": self.vector_search,
            "scopes": self.scopes,
        }


def est_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 3))  # tiếng Việt: khoảng 3 ký tự mỗi token


def category(type_: str, scope: str) -> str:
    if scope == "company":
        return "shared"
    return {"procedural": "procedural", "episodic": "experience", "working": "experience"}.get(type_, "semantic")


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _filters(types: list[str] | None, metadata: dict[str, Any] | None, since: datetime | None) -> tuple[str, dict[str, Any]]:
    from app.domain.approvals import _json

    sql = " AND m.verification_status IN ('verified','active') AND m.valid_from <= now() AND (m.valid_to IS NULL OR m.valid_to > now())"
    p: dict[str, Any] = {}
    if types:
        sql += " AND m.type = ANY(:types)"
        p["types"] = types
    if metadata:
        sql += " AND m.metadata @> CAST(:meta AS jsonb)"
        p["meta"] = _json(metadata)
    if since:
        sql += " AND m.created_at >= :since"
        p["since"] = since
    return sql, p


async def retrieve(
    conn: AsyncConnection,
    agent_key: str,
    query: str,
    *,
    types: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    since: datetime | None = None,
    budget_tokens: int | None = None,
    share_ratio: dict[str, float] | None = None,
    task_id: str | None = None,
    purpose: str = "task",
    query_vector: list[float] | None = None,
    use_vectors: bool = True,
    limit_each: int = 50,
    log: bool = True,
) -> Result:
    principal = f"agent:{agent_key}"
    scopes = await scopes_for(conn, principal)
    if budget_tokens is None or share_ratio is None:
        from app.brain import registry

        try:
            b = (await registry.resolve(conn, agent_key)).loaded.bundle
            budget_tokens = budget_tokens or b.memory.retrieval_budget_tokens
            share_ratio = share_ratio or dict(b.memory.share_ratio)
        except Exception:  # noqa: BLE001 — chưa có bộ não: dùng mặc định
            budget_tokens = budget_tokens or 4000
            share_ratio = share_ratio or DEFAULT_SHARE
    flt, fp = _filters(types, metadata, since)
    # Lớp 1 (ứng dụng) lọc phạm vi; lớp 2 (RLS của Postgres) lọc lại dù lớp 1 có lỗi
    flt += " AND m.owner_scope = ANY(:scopes)"
    fp["scopes"] = scopes

    # ---- vector của câu hỏi (nếu có model embedding và khóa API)
    vec_state = "skipped"
    em = None
    if use_vectors:
        from app.gateway import models as gw

        em = await gw.embed_model(conn)
        if em is None:
            vec_state = "not_configured"
        elif query_vector is None:
            try:
                _, vs = await gw.embed(conn, [query], purpose="memory_query", agent_key=agent_key)
                query_vector = vs[0]
            except AppError as e:
                vec_state = "not_configured" if e.code == "NOT_CONFIGURED" else f"error: {e.code}"
        if query_vector is not None and em is not None:
            vec_state = "used"

    qterms = textnorm.query_terms(query)
    folded = textnorm.search_text(query)
    kw_ids: list[str] = []
    vec_ids: list[str] = []
    async with acting_as(conn, "aico_agent", principal, scopes) as c:
        if qterms:
            tsq = " | ".join(qterms)
            rows = await db.all_(
                c,
                "SELECT m.id, ts_rank_cd(m.tsv, q) + word_similarity(CAST(:f AS text), m.search_text) AS s "  # noqa: S608
                "FROM agent_memories m, to_tsquery('simple', :tsq) q "
                f"WHERE (m.tsv @@ q OR CAST(:f AS text) <% m.search_text) {flt} ORDER BY s DESC, m.created_at DESC LIMIT :lim",
                {"tsq": tsq, "f": folded, "lim": limit_each, **fp},
            )
            kw_ids = [str(r["id"]) for r in rows]
        if vec_state == "used" and em is not None and query_vector is not None:
            dims = int(em.dims)
            if not re.fullmatch(r"[a-z0-9_-]{1,60}", em.id):
                raise AppError("EMBED_MODEL_INVALID", "Tên model embedding không hợp lệ.", 500)
            lit = "[" + ",".join(f"{x:.7f}" for x in query_vector) + "]"
            # model_id ghi thẳng (đã kiểm định dạng) để Postgres chọn đúng chỉ mục HNSW riêng của model (chỉ mục một phần)
            await db.execute(c, "SET LOCAL hnsw.ef_search = 100")
            rows = await db.all_(
                c,
                f"SELECT e.memory_id AS id FROM memory_embeddings e JOIN agent_memories m ON m.id = e.memory_id "  # noqa: S608
                f"WHERE e.model_id = '{em.id}' {flt} ORDER BY e.embedding::vector({dims}) <=> CAST(:qv AS vector({dims})) LIMIT :lim",
                {"qv": lit, "lim": limit_each, **fp},
            )
            vec_ids = [str(r["id"]) for r in rows]
        ids = list(dict.fromkeys(kw_ids + vec_ids))
        details = (
            await db.all_(
                c,
                "SELECT id, type, owner_scope, title, content, source_ref, source_trust, confidence, created_at, search_text "
                "FROM agent_memories WHERE id = ANY(CAST(:ids AS uuid[]))",
                {"ids": ids},
            )
            if ids
            else []
        )

        now = datetime.now(UTC)
        kw_rank = {i: n for n, i in enumerate(kw_ids, 1)}
        vec_rank = {i: n for n, i in enumerate(vec_ids, 1)}
        items: list[Item] = []
        for r in details:
            mid = str(r["id"])
            it = Item(
                memory_id=mid,
                type=r["type"],
                scope=r["owner_scope"],
                title=r["title"],
                content=r["content"],
                source_ref=r["source_ref"],
                source_trust=r["source_trust"],
                confidence=float(r["confidence"]),
                created_at=r["created_at"],
                category=category(r["type"], r["owner_scope"]),
                tokens=est_tokens(r["title"] + "\n" + r["content"]),
                kw_rank=kw_rank.get(mid),
                vec_rank=vec_rank.get(mid),
                terms=set(r["search_text"].split()),
            )
            it.rrf = sum(1 / (RRF_K + rk) for rk in (it.kw_rank, it.vec_rank) if rk)
            hl = HALF_LIFE_DAYS.get(it.type)
            it.w_recency = 0.5 ** (max(0.0, (now - it.created_at).total_seconds() / 86400) / hl) if hl else 1.0
            it.w_conf = 0.5 + 0.5 * it.confidence
            it.w_trust = TRUST_W[it.source_trust]
            it.score = it.rrf * it.w_recency * it.w_conf * it.w_trust
            items.append(it)
        items.sort(key=lambda x: -x.score)

        chosen = pack(items, budget_tokens, share_ratio)
        if log and chosen:
            for rank, it in enumerate(chosen, 1):
                await db.execute(
                    c,
                    "INSERT INTO memory_access_log(memory_id, principal, task_id, purpose, rank, score) VALUES (CAST(:m AS uuid), :p, :t, :pu, :r, :s)",
                    {"m": it.memory_id, "p": principal, "t": task_id, "pu": purpose[:60], "r": rank, "s": it.score},
                )
    return Result(chosen, len(items), sum(i.tokens for i in chosen), budget_tokens, vec_state, scopes)


def pack(items: list[Item], budget: int, share: dict[str, float]) -> list[Item]:
    """Chọn theo điểm có khử trùng (MMR), mỗi nhóm trong hạn mức token của nó; phần hạn mức thừa chia lại theo điểm."""
    if not items:
        return []
    top = items[0].score or 1.0
    chosen: list[Item] = []
    used = {c: 0 for c in CATEGORIES}
    total = 0

    def best(pool: list[Item]) -> Item | None:
        sel, sel_v = None, -1e9
        for it in pool:
            sim = max((jaccard(it.terms, s.terms) for s in chosen), default=0.0)
            if sim >= NEAR_DUP:
                continue
            v = MMR_LAMBDA * it.score / top - (1 - MMR_LAMBDA) * sim
            if v > sel_v:
                sel, sel_v = it, v
        return sel

    for strict in (True, False):  # lượt 1: theo hạn mức từng nhóm; lượt 2: dùng phần còn thừa
        pool = [i for i in items if i not in chosen]
        while pool:
            it = best(pool)
            if it is None:
                break
            pool.remove(it)
            quota = share.get(it.category, 0) * budget
            if total + it.tokens > budget or (strict and used[it.category] + it.tokens > quota):
                continue
            chosen.append(it)
            used[it.category] += it.tokens
            total += it.tokens
    chosen.sort(key=lambda x: -x.score)
    return chosen


async def mark_used(conn: AsyncConnection, agent_key: str, task_id: str, memory_ids: list[str]) -> int:
    """Mục được dùng trong kết quả cuối: đánh dấu lượt truy hồi và tăng `usefulness` (BRAIN_SPEC §5.7)."""
    n = await db.execute(
        conn,
        "UPDATE memory_access_log SET used_in_output = true WHERE principal = :p AND task_id = :t AND memory_id = ANY(CAST(:ids AS uuid[]))",
        {"p": f"agent:{agent_key}", "t": task_id, "ids": memory_ids},
    )
    await db.execute(
        conn, "UPDATE agent_memories SET usefulness = usefulness + 1 WHERE id = ANY(CAST(:ids AS uuid[]))", {"ids": memory_ids}
    )
    return n
