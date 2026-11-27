"""Nhúng trí nhớ thành vector (job nền) và nhúng lại khi đổi model (IT-VEC-02).

Mỗi vector gắn `model_id`, nên chạy song song hai model trong lúc chuyển: model mới được nhúng dần, truy hồi dùng
model đang bật; mục chưa có vector vẫn tìm được theo từ khóa. Chưa có khóa OpenAI → trả `not_configured`, không lỗi.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.core.errors import AppError
from app.gateway import models as gw

BATCH = 64


@dataclass
class EmbedReport:
    status: str  # done | not_configured | error
    embedded: int
    remaining: int
    model: str | None
    detail: str = ""


async def pending_count(conn: AsyncConnection, model_id: str) -> int:
    return int(
        await db.scalar(
            conn,
            "SELECT count(*) FROM agent_memories m WHERE m.verification_status <> 'retired' "
            "AND NOT EXISTS (SELECT 1 FROM memory_embeddings e WHERE e.memory_id = m.id AND e.model_id = :mid)",
            {"mid": model_id},
        )
        or 0
    )


async def embed_pending(conn: AsyncConnection, limit: int = 256) -> EmbedReport:
    em = await gw.embed_model(conn)
    if em is None:
        return EmbedReport("not_configured", 0, 0, None, "Chưa có model embedding nào đang bật")
    rows = await db.all_(
        conn,
        "SELECT m.id, m.title, m.content FROM agent_memories m WHERE m.verification_status <> 'retired' "
        "AND NOT EXISTS (SELECT 1 FROM memory_embeddings e WHERE e.memory_id = m.id AND e.model_id = :mid) ORDER BY m.created_at LIMIT :l",
        {"mid": em.id, "l": limit},
    )
    done = 0
    for i in range(0, len(rows), BATCH):
        part = rows[i : i + BATCH]
        try:
            _, vecs = await gw.embed(conn, [f"{r['title']}\n{r['content']}" for r in part], purpose="memory_embed")
        except AppError as e:
            status = "not_configured" if e.code == "NOT_CONFIGURED" else "error"
            return EmbedReport(status, done, await pending_count(conn, em.id), em.id, e.message)
        for r, v in zip(part, vecs, strict=True):
            await db.execute(
                conn,
                "INSERT INTO memory_embeddings(memory_id, model_id, embedding) VALUES (:m, :mid, CAST(:v AS vector)) ON CONFLICT DO NOTHING",
                {"m": r["id"], "mid": em.id, "v": "[" + ",".join(f"{x:.7f}" for x in v) + "]"},
            )
            done += 1
    return EmbedReport("done", done, await pending_count(conn, em.id), em.id)


async def ensure_index(conn: AsyncConnection, model_id: str, dims: int) -> None:
    """Tạo chỉ mục HNSW riêng cho một model embedding (gọi khi đăng ký model mới)."""
    name = "memory_embeddings_hnsw_" + "".join(ch if ch.isalnum() else "_" for ch in model_id)
    await db.execute(
        conn,
        f"CREATE INDEX IF NOT EXISTS {name} ON memory_embeddings USING hnsw ((embedding::vector({int(dims)})) vector_cosine_ops) "  # noqa: S608
        f"WHERE model_id = '{model_id.replace(chr(39), '')}'",
    )


async def switch_model(conn: AsyncConnection, model_id: str) -> None:
    """Đổi model embedding đang bật; vector của model cũ được giữ lại tới khi model mới nhúng xong (prune_old)."""
    row = await db.one(conn, "SELECT id, dims FROM embedding_models WHERE id = :i", {"i": model_id})
    if row is None:
        raise AppError("EMBED_MODEL_NOT_FOUND", "Không có model embedding này.", 404)
    await ensure_index(conn, row["id"], int(row["dims"]))
    await db.execute(conn, "UPDATE embedding_models SET active = false WHERE active")
    await db.execute(conn, "UPDATE embedding_models SET active = true WHERE id = :i", {"i": model_id})


async def prune_old(conn: AsyncConnection) -> int:
    """Xóa vector của các model không còn bật, chỉ khi model đang bật đã nhúng đủ."""
    em = await gw.embed_model(conn)
    if em is None or await pending_count(conn, em.id) > 0:
        return 0
    return await db.execute(conn, "DELETE FROM memory_embeddings WHERE model_id <> :m", {"m": em.id})
