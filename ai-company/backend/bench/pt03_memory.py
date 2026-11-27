"""PT-03: đo truy hồi lai (từ khóa + vector) trên số lượng lớn bản ghi trí nhớ.

Chạy trên một CSDL RIÊNG đã migrate và đồng bộ bộ não (tên phải chứa "bench"); script xóa sạch trí nhớ trong CSDL đó rồi nạp dữ liệu tổng hợp:

    createdb aico_bench   # hoặc CREATE DATABASE aico_bench OWNER aico
    export AICO_DATABASE_URL=postgresql+psycopg://aico:aico@127.0.0.1/aico_bench AICO_ENV=test AICO_MASTER_KEY=...
    uv run alembic upgrade head && uv run python -m app.cli sync-brains
    uv run python bench/pt03_memory.py --n 200000 --queries 300

Dữ liệu là văn bản tổng hợp từ bộ từ vựng của xưởng, vector 512 chiều sinh quanh 500 cụm (giống phân bố embedding thật hơn vector ngẫu nhiên đều).
Đây là công cụ đo, không phải dữ liệu sản phẩm: chỉ chạy trên CSDL bench.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import statistics
import time
import uuid
from typing import Any

import psycopg
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.core.config import get_settings
from app.memory import retrieval, textnorm

DIMS = 512
MODEL = "openai-te3s-512"
CLUSTERS = 500
DEPTS = ["executive", "marketing", "sales", "growth", "technology"]
SUBJ = [
    "trà sen Tây Hồ",
    "trà gừng mật ong",
    "trà thảo mộc",
    "hộp quà Tết",
    "trà ô long",
    "trà nhài",
    "trà shan tuyết",
    "bộ ấm chén",
    "trà túi lọc",
    "trà hoa cúc",
    "combo quà biếu",
    "trà atiso",
    "trà lài",
    "trà xanh Thái Nguyên",
    "mứt gừng",
    "trà đen",
]
VERB = ["bán chạy", "được hỏi nhiều", "bị phàn nàn", "tăng giá", "hết hàng", "giảm giá", "được khen", "ít người mua", "cần chụp lại ảnh"]
CTX = [
    "dịp Tết",
    "mùa đông",
    "trên Facebook",
    "trên Shopee",
    "khách sỉ",
    "khách quen",
    "quà doanh nghiệp",
    "sau chiến dịch quảng cáo",
    "ở Hà Nội",
    "ở TP.HCM",
    "khi giao chậm",
    "khi có mã giảm giá",
    "buổi tối",
    "cuối tuần",
    "khách mới",
    "đơn trên 500k",
]
ACT = [
    "nên viết bài kể chuyện nguồn gốc",
    "nên gửi tin nhắn chăm sóc",
    "nên ưu đãi miễn phí giao hàng",
    "nên ghép combo",
    "nên đổi ảnh bìa",
    "nên nhắc khách đặt trước 15 giờ",
    "nên trả lời trong 10 phút",
    "nên tặng kèm thiệp",
    "nên giữ giá",
    "nên chạy lại quảng cáo",
]
TYPES = [("episodic", 0.6), ("semantic", 0.3), ("procedural", 0.1)]
TRUST = ["owner", "internal", "verified_external", "unverified_external"]


def sentence(r: random.Random) -> tuple[str, str]:
    s, v, c, a = r.choice(SUBJ), r.choice(VERB), r.choice(CTX), r.choice(ACT)
    title = f"{s.capitalize()} {v} {c}"
    extra = " ".join(r.choice(CTX) for _ in range(r.randint(1, 3)))
    content = f"Ghi nhận: {s} {v} {c}; {a}. Bối cảnh thêm: {extra}. Lần {r.randint(1, 999)}."
    return title, content


def pick_type(r: random.Random) -> str:
    x, acc = r.random(), 0.0
    for t, w in TYPES:
        acc += w
        if x < acc:
            return t
    return "episodic"


def sync_url() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


def load(n: int, agents: list[str], seed: int) -> None:
    r = random.Random(seed)
    url = sync_url()
    t0 = time.perf_counter()
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("TRUNCATE agent_memories CASCADE")
        c.execute(f"DROP INDEX IF EXISTS memory_embeddings_hnsw_{MODEL.replace('-', '_')}")
        with (
            c.cursor() as cur,
            cur.copy(
                "COPY agent_memories (id, owner_scope, type, title, content, search_text, metadata, source_trust, confidence, "
                "content_hash, created_by_principal, created_at) FROM STDIN"
            ) as cp,
        ):
            for i in range(n):
                x = r.random()
                if x < 0.10:
                    scope = "company"
                elif x < 0.30:
                    scope = "dept:" + r.choice(DEPTS)
                else:
                    scope = "agent:" + r.choice(agents)
                t = pick_type(r) if scope.startswith("agent:") else r.choice(["semantic", "procedural"])
                title, content = sentence(r)
                age = r.random() * 365
                cp.write_row(
                    (
                        uuid.UUID(int=r.getrandbits(128), version=4),
                        scope,
                        t,
                        title,
                        content,
                        textnorm.search_text(f"{title} {content}"),
                        json.dumps({"c": i % CLUSTERS}),
                        r.choice(TRUST),
                        round(0.3 + r.random() * 0.7, 2),
                        hashlib.sha256(f"{i}:{content}".encode()).hexdigest(),
                        "bench",
                        time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - age * 86400)),
                    )
                )
        print(f"  nạp {n:,} mục văn bản: {time.perf_counter() - t0:.0f} s")
        t1 = time.perf_counter()
        c.execute("DROP TABLE IF EXISTS bench_centroids")
        c.execute(
            "CREATE UNLOGGED TABLE bench_centroids AS SELECT i, "
            f"(SELECT array_agg((random() - 0.5)::float4) FROM generate_series(1, {DIMS}) j WHERE i >= 0) AS v "
            f"FROM generate_series(0, {CLUSTERS - 1}) i"
        )
        c.execute(
            "INSERT INTO memory_embeddings (memory_id, model_id, embedding) "
            f"SELECT m.id, '{MODEL}', (SELECT array_agg(b.v[j] + ((random() - 0.5) * 0.5)::float4 ORDER BY j) "
            f"FROM generate_series(1, {DIMS}) j)::vector "
            "FROM agent_memories m JOIN bench_centroids b ON b.i = (m.metadata->>'c')::int"
        )
        print(f"  sinh {n:,} vector {DIMS} chiều: {time.perf_counter() - t1:.0f} s")
        t2 = time.perf_counter()
        c.execute("SET maintenance_work_mem = '512MB'")
        c.execute(
            f"CREATE INDEX memory_embeddings_hnsw_{MODEL.replace('-', '_')} ON memory_embeddings "
            f"USING hnsw ((embedding::vector({DIMS})) vector_cosine_ops) WHERE model_id = '{MODEL}'"
        )
        print(f"  dựng chỉ mục HNSW: {time.perf_counter() - t2:.0f} s")
        c.execute("VACUUM ANALYZE agent_memories")
        c.execute("VACUUM ANALYZE memory_embeddings")


def centroids() -> list[list[float]]:
    with psycopg.connect(sync_url()) as c:
        return [list(v) for (v,) in c.execute("SELECT v FROM bench_centroids ORDER BY i").fetchall()]


def near(r: random.Random, cs: list[list[float]]) -> list[float]:
    base = r.choice(cs)
    return [x + (r.random() - 0.5) * 0.5 for x in base]


def query_text(r: random.Random) -> str:
    q = f"{r.choice(SUBJ)} {r.choice(CTX)}"
    return textnorm.fold(q) if r.random() < 0.4 else q  # 40% gõ không dấu như khách/Owner hay gõ


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


async def run_queries(agents: list[str], cs: list[list[float]], q: int, seed: int, *, use_vectors: bool) -> dict[str, Any]:
    r = random.Random(seed)
    lat: list[float] = []
    picked: list[int] = []
    for i in range(q + 20):
        agent = r.choice(agents)
        text = query_text(r)
        vec = near(r, cs) if use_vectors else None
        async with db.engine().begin() as conn:
            t0 = time.perf_counter()
            res = await retrieval.retrieve(conn, agent, text, query_vector=vec, use_vectors=use_vectors, task_id=f"bench-{i}")
            dt = (time.perf_counter() - t0) * 1000
        if i >= 20:  # 20 lượt đầu để làm nóng bộ đệm
            lat.append(dt)
            picked.append(len(res.items))
    return {
        "p50_ms": round(pct(lat, 50), 1),
        "p95_ms": round(pct(lat, 95), 1),
        "p99_ms": round(pct(lat, 99), 1),
        "max_ms": round(max(lat), 1),
        "mean_items": round(statistics.mean(picked), 1),
    }


async def recall(agents: list[str], cs: list[list[float]], q: int, seed: int) -> dict[str, float]:
    """Recall@10 của đường tìm vector thật (hàm aico_mem_vector, ef_search và lấy dư như production) so với tìm chính xác (quét hết)."""
    r = random.Random(seed)
    from app.memory.store import acting_as, scopes_for

    out: list[float] = []
    exact_sql = (
        "SELECT e.memory_id FROM memory_embeddings e JOIN agent_memories m ON m.id = e.memory_id "
        f"WHERE e.model_id = '{MODEL}' AND m.owner_scope = ANY(:s) ORDER BY e.embedding::vector({DIMS}) <=> CAST(:v AS vector({DIMS})) LIMIT 10"
    )
    async with db.engine().connect() as conn:
        for _ in range(q):
            v = "[" + ",".join(f"{x:.6f}" for x in near(r, cs)) + "]"
            agent = r.choice(agents)
            async with conn.begin():
                scopes = await scopes_for(conn, f"agent:{agent}")
                await db.execute(conn, f"SET LOCAL hnsw.ef_search = {retrieval.VEC_OVERFETCH}")
                async with acting_as(conn, "aico_agent", f"agent:{agent}", scopes) as c:
                    approx = {
                        x["id"]
                        for x in await db.all_(
                            c,
                            "SELECT id FROM aico_mem_vector(:m, :d, :v, NULL, NULL, NULL, CAST(:f AS int), 10)",
                            {"m": MODEL, "d": DIMS, "v": v, "f": retrieval.VEC_OVERFETCH},
                        )
                    }
            async with conn.begin():
                await db.execute(conn, "SET LOCAL enable_indexscan = off")
                exact = {x["memory_id"] for x in await db.all_(conn, exact_sql, {"v": v, "s": scopes})}
            out.append(len(approx & exact) / max(1, len(exact)))
    return {"agent_scope": round(statistics.mean(out), 3)}


async def sizes(conn: AsyncConnection) -> dict[str, str]:
    rows = await db.all_(
        conn,
        "SELECT relname AS name, pg_size_pretty(pg_total_relation_size(oid)) AS size FROM pg_class "
        "WHERE relname IN ('agent_memories', 'memory_embeddings') "
        "UNION ALL SELECT relname, pg_size_pretty(pg_relation_size(oid)) FROM pg_class WHERE relname LIKE 'memory_embeddings_hnsw_%'",
    )
    return {x["name"]: x["size"] for x in rows}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200_000)
    ap.add_argument("--queries", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--skip-load", action="store_true")
    a = ap.parse_args()
    url = get_settings().database_url
    if "bench" not in url.rsplit("/", 1)[-1]:
        raise SystemExit("Chỉ chạy trên CSDL có tên chứa 'bench' (script xóa toàn bộ trí nhớ).")
    async with db.engine().connect() as conn:
        agents = [x["agent_key"] for x in await db.all_(conn, "SELECT agent_key FROM agents ORDER BY agent_key")]
    if not agents:
        raise SystemExit("Chưa có agent: chạy `python -m app.cli sync-brains` trước.")
    print(f"PT-03 với {a.n:,} mục trí nhớ, {len(agents)} agent")
    if not a.skip_load:
        load(a.n, agents, a.seed)
    cs = centroids()
    hybrid = await run_queries(agents, cs, a.queries, a.seed + 1, use_vectors=True)
    print("  truy hồi lai (từ khóa + vector, RLS, ghi nhật ký):", hybrid)
    kw = await run_queries(agents, cs, a.queries, a.seed + 2, use_vectors=False)
    print("  chỉ từ khóa:", kw)
    rc = await recall(agents, cs, min(50, a.queries), a.seed + 3)
    print("  recall@10 HNSW:", rc)
    async with db.engine().connect() as conn:
        sz = await sizes(conn)
    print("  dung lượng:", sz)
    await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
