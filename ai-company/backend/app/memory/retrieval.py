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
CANDIDATES = 1000  # trần số ứng viên được chấm điểm ở mỗi tầng tìm từ khóa
VEC_OVERFETCH = 400  # số ứng viên lấy từ HNSW trước khi lọc phạm vi
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


def _filters(types: list[str] | None, metadata: dict[str, Any] | None, since: datetime | None) -> dict[str, Any]:
    from app.domain.approvals import _json

    return {"types": types or None, "meta": _json(metadata) if metadata else None, "since": since}


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
    fp = _filters(types, metadata, since)

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
                _, vs = await gw.embed(conn, [query], purpose="memory_query", agent_key=agent_key, task_id=task_id)
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
            kw_ids = await _keyword(c, qterms, folded, fp, limit_each)
        if vec_state == "used" and em is not None and query_vector is not None:
            vec_ids = await _vector(c, em.id, int(em.dims), query_vector, fp, limit_each)
        ids = list(dict.fromkeys(kw_ids + vec_ids))
        details = (
            await db.all_(
                c,
                "SELECT id, type, owner_scope, title, content, source_ref, source_trust, confidence, created_at, search_text "
                # Ba lớp: hàm tìm kiếm lọc theo phạm vi của phiên; câu này lọc lại ở tầng ứng dụng; RLS của Postgres lọc lần nữa
                "FROM agent_memories WHERE id = ANY(CAST(:ids AS uuid[])) AND owner_scope = ANY(:scopes)",
                {"ids": ids, "scopes": scopes},
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
        if log and chosen:  # một câu lệnh cho cả lượt truy hồi
            await db.execute(
                c,
                "INSERT INTO memory_access_log(memory_id, principal, task_id, purpose, rank, score) "
                "SELECT m, :p, :t, :pu, r, s FROM unnest(CAST(:ms AS uuid[]), CAST(:rs AS int[]), CAST(:ss AS float8[])) AS x(m, r, s)",
                {
                    "ms": [i.memory_id for i in chosen],
                    "rs": list(range(1, len(chosen) + 1)),
                    "ss": [i.score for i in chosen],
                    "p": principal,
                    "t": task_id,
                    "pu": purpose[:60],
                },
            )
    return Result(chosen, len(items), sum(i.tokens for i in chosen), budget_tokens, vec_state, scopes)


async def _keyword(c: AsyncConnection, qterms: list[str], folded: str, fp: dict[str, Any], lim: int) -> list[str]:
    """Tìm theo từ khóa hai tầng, chi phí có trần dù kho trí nhớ lớn tới đâu (hàm `aico_mem_keyword`, migration 0004).

    Tầng 1: mục chứa ĐỦ các từ (AND). Tầng 2, chỉ khi tầng 1 chưa đủ: chứa MỘT trong các từ hoặc gần giống chữ (trigram, bắt lỗi gõ).
    Mỗi tầng chỉ chấm điểm tối đa CANDIDATES ứng viên mới nhất: với từ rất phổ biến ("trà") không phải tính hạng cho hàng chục nghìn dòng.
    """
    out: list[str] = []
    for tsq, fuzzy in ((" & ".join(qterms), False), (" | ".join(qterms), True)):
        if len(out) >= lim:
            break
        rows = await db.all_(
            c,
            "SELECT t.id FROM aico_mem_keyword(CAST(:tsq AS text), CAST(:f AS text), :fuzzy, "
            "CAST(:types AS text[]), CAST(:meta AS jsonb), CAST(:since AS timestamptz), "
            "CAST(:seen AS uuid[]), CAST(:cap AS int), CAST(:lim AS int)) WITH ORDINALITY AS t(id, n) ORDER BY t.n",
            {"tsq": tsq, "f": folded, "fuzzy": fuzzy, "seen": out, "cap": CANDIDATES, "lim": lim - len(out), **fp},
        )
        out += [str(r["id"]) for r in rows]
    return out


async def _vector(c: AsyncConnection, model_id: str, dims: int, qv: list[float], fp: dict[str, Any], lim: int) -> list[str]:
    """Tìm theo nghĩa qua chỉ mục HNSW riêng của model (hàm `aico_mem_vector`).

    Chỉ mục trả ứng viên gần nhất TRƯỚC khi lọc phạm vi, nên lấy dư VEC_OVERFETCH ứng viên rồi mới lọc. pgvector ≥ 0.8
    bật thêm quét lặp (iterative scan) để luôn đủ ứng viên sau lọc; bản cũ hơn dựa vào lấy dư."""
    if not re.fullmatch(r"[a-z0-9_-]{1,60}", model_id):
        raise AppError("EMBED_MODEL_INVALID", "Tên model embedding không hợp lệ.", 500)
    lit = "[" + ",".join(f"{x:.7f}" for x in qv) + "]"
    await db.execute(c, f"SET LOCAL hnsw.ef_search = {VEC_OVERFETCH}")
    if await _pgvector_at_least(c, (0, 8)):
        await db.execute(c, "SET LOCAL hnsw.iterative_scan = relaxed_order")
    rows = await db.all_(
        c,
        "SELECT t.id FROM aico_mem_vector(CAST(:model AS text), CAST(:dims AS int), CAST(:qv AS text), "
        "CAST(:types AS text[]), CAST(:meta AS jsonb), CAST(:since AS timestamptz), "
        "CAST(:fetch AS int), CAST(:lim AS int)) WITH ORDINALITY AS t(id, n) ORDER BY t.n",
        {"model": model_id, "dims": dims, "qv": lit, "fetch": VEC_OVERFETCH, "lim": lim, **fp},
    )
    return [str(r["id"]) for r in rows]


_PGV: tuple[int, ...] | None = None


async def _pgvector_at_least(c: AsyncConnection, v: tuple[int, int]) -> bool:
    global _PGV  # noqa: PLW0603 — phiên bản extension không đổi khi tiến trình đang chạy
    if _PGV is None:
        r = await db.one(c, "SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        _PGV = tuple(int(x) for x in re.findall(r"\d+", str(r["extversion"]))[:3]) if r else (0,)
    return _PGV >= v


def pack(items: list[Item], budget: int, share: dict[str, float]) -> list[Item]:
    """Chọn theo điểm có khử trùng (MMR), mỗi nhóm trong hạn mức token của nó; phần hạn mức thừa chia lại theo điểm.

    Độ giống lớn nhất với các mục đã chọn được cập nhật dần sau mỗi lần chọn: O(n·k) phép so Jaccard thay vì O(n·k²)."""
    n = len(items)
    if not n:
        return []
    top = items[0].score or 1.0
    sim = [0.0] * n
    taken = [False] * n
    chosen: list[Item] = []
    used = dict.fromkeys(CATEGORIES, 0)
    total = 0
    for strict in (True, False):  # lượt 1: theo hạn mức từng nhóm; lượt 2: dùng phần còn thừa
        tried = list(taken)
        while True:
            k, best = -1, -1e9
            for j in range(n):
                if tried[j] or sim[j] >= NEAR_DUP:
                    continue
                v = MMR_LAMBDA * items[j].score / top - (1 - MMR_LAMBDA) * sim[j]
                if v > best:
                    k, best = j, v
            if k < 0:
                break
            tried[k] = True
            it = items[k]
            quota = share.get(it.category, 0) * budget
            if total + it.tokens > budget or (strict and used[it.category] + it.tokens > quota):
                continue
            taken[k] = True
            chosen.append(it)
            used[it.category] += it.tokens
            total += it.tokens
            for j in range(n):
                if not taken[j]:
                    sim[j] = max(sim[j], jaccard(items[j].terms, it.terms))
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
