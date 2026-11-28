"""UT-MEM-01…10, IT-DB-02, IT-VEC-01…02: trí nhớ có phạm vi, RLS, truy hồi lai tiếng Việt, embedding.

Embedding trong test dùng nhà cung cấp giả (httpx.MockTransport): vector túi-từ băm vào 512 chiều, tất định."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import random
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.memory import retrieval, store, textnorm
from tests.conftest import BACKEND, needs_db

pytestmark = needs_db
DIMS = 512


def fake_vec(text: str) -> list[float]:
    v = [0.0] * DIMS
    for t in textnorm.query_terms(text) or ["_"]:
        v[int(hashlib.md5(t.encode()).hexdigest(), 16) % DIMS] += 1.0  # noqa: S324 — chỉ để băm trong test
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        self.calls.append(body)
        data = [{"index": i, "embedding": fake_vec(t)} for i, t in enumerate(body["input"])]
        return httpx.Response(200, json={"data": data, "usage": {"prompt_tokens": sum(len(t) // 3 for t in body["input"])}})


@pytest.fixture
def fake_embed() -> Iterator[FakeEmbeddings]:
    from app.gateway import models

    f = FakeEmbeddings()
    models.transport = httpx.MockTransport(f)
    yield f
    models.transport = None


@pytest.fixture
async def mem(synced: object, conn: AsyncConnection) -> AsyncIterator[AsyncConnection]:
    """Một giao dịch cho cả test (rollback cuối test), như một request thật."""
    yield conn


async def ep(c: AsyncConnection, agent: str, title: str, content: str, **kw: object) -> str:
    return await store.remember_episode(c, agent, title=title, content=content, **kw)  # type: ignore[arg-type]


async def kn(c: AsyncConnection, scope: str, title: str, content: str, **kw: object) -> str:
    mid, _ = await store.add_knowledge(
        c,
        principal="user:owner",
        scope=scope,
        type_=kw.pop("type_", "semantic"),
        title=title,
        content=content,  # type: ignore[arg-type]
        trust=kw.pop("trust", "owner"),
        **kw,
    )  # type: ignore[arg-type]
    return mid


def ids(r: retrieval.Result) -> list[str]:
    return [i.memory_id for i in r.items]


# ------------------------------------------------------------------ UT-MEM-01: lọc phạm vi/loại/thời gian/metadata
async def test_mem01_filters(mem: AsyncConnection) -> None:
    own = await ep(
        mem,
        "seo_agent",
        "Bài trà gừng",
        "Meta description bài trà gừng phải có tên sản phẩm",
        task_type="blog",
        metadata={"channel": "web"},
    )
    other = await ep(mem, "ads_agent", "Quảng cáo trà gừng", "Chiến dịch trà gừng CPA cao")
    dept = await kn(mem, "dept:marketing", "Quy ước phòng", "Bài trà gừng luôn kèm liên kết sản phẩm", type_="procedural")
    comp = await kn(mem, "company", "Thông tin sản phẩm", "Trà gừng mật ong đóng gói 20 túi lọc", metadata={"category": "product"})
    secret = await kn(mem, "owner_only", "Giá vốn", "Giá vốn trà gừng 30.000đ")
    r = await retrieval.retrieve(mem, "seo_agent", "trà gừng", use_vectors=False)
    assert set(ids(r)) == {own, dept, comp} and other not in ids(r) and secret not in ids(r)
    assert set(ids(await retrieval.retrieve(mem, "seo_agent", "trà gừng", types=["procedural"], use_vectors=False))) == {dept}
    assert ids(await retrieval.retrieve(mem, "seo_agent", "trà gừng", metadata={"channel": "web"}, use_vectors=False)) == [own]
    later = datetime.now(UTC) + timedelta(minutes=1)
    assert ids(await retrieval.retrieve(mem, "seo_agent", "trà gừng", since=later, use_vectors=False)) == []


# ------------------------------------------------------------------ UT-MEM-02: RRF + trọng số
async def test_mem02_rrf_and_weights(mem: AsyncConnection, fake_embed: FakeEmbeddings) -> None:
    from app.domain import store as secrets

    await secrets.put_secret(mem, "provider.openai.api_key", "sk-test-" + "e" * 30, "test")
    a = await kn(mem, "company", "Trà sen Tây Hồ", "Trà sen ướp bông sen Tây Hồ, hương thơm dịu", trust="owner")
    b = await kn(
        mem, "company", "Tin trên mạng", "Một bài đăng mạng xã hội nói trà sen Tây Hồ bán chạy nhất phố cổ", trust="unverified_external"
    )
    from app.memory.embedding import embed_pending

    rep = await embed_pending(mem)
    assert rep.status == "done" and rep.embedded == 2 and rep.remaining == 0
    r = await retrieval.retrieve(mem, "content_agent", "trà sen Tây Hồ")
    assert r.vector_search == "used"
    by = {i.memory_id: i for i in r.items}
    assert by[a].kw_rank and by[a].vec_rank  # có mặt ở cả hai danh sách
    assert by[a].w_trust == 1.0 and by[b].w_trust == 0.5 and ids(r)[0] == a
    assert by[a].score == pytest.approx(by[a].rrf * by[a].w_recency * by[a].w_conf * by[a].w_trust)
    # Episodic cũ bị giảm theo bán rã 60 ngày
    new = await ep(mem, "content_agent", "Góp ý bài trà sen", "Không hứa giao trong ngày khi viết bài trà sen")
    old = await ep(mem, "content_agent", "Góp ý cũ bài trà sen", "Ảnh bìa bài trà sen phải là ảnh thật của xưởng")
    await mem.exec_driver_sql(f"UPDATE agent_memories SET created_at = now() - interval '60 days' WHERE id = '{old}'")
    r2 = await retrieval.retrieve(mem, "content_agent", "góp ý bài trà sen", types=["episodic"], use_vectors=False)
    w = {i.memory_id: i.w_recency for i in r2.items}
    assert w[new] == pytest.approx(1.0, abs=0.01) and w[old] == pytest.approx(0.5, abs=0.01)


# ------------------------------------------------------------------ UT-MEM-03: ngân sách token + tỉ lệ nhóm
async def test_mem03_token_budget_and_share(mem: AsyncConnection) -> None:
    for i in range(12):
        await ep(mem, "seo_agent", f"Kinh nghiệm SEO {i}", f"Bài về trà ô long số {i}: " + "nội dung dài " * 40)
        await kn(mem, "company", f"Kiến thức chung {i}", f"Trà ô long loại {i}: " + "mô tả sản phẩm " * 40)
    r = await retrieval.retrieve(
        mem,
        "seo_agent",
        "trà ô long",
        budget_tokens=900,
        share_ratio={"procedural": 0.2, "experience": 0.5, "semantic": 0.1, "shared": 0.2},
        use_vectors=False,
    )
    assert r.used_tokens <= 900 and r.considered == 24
    cats = {c: sum(i.tokens for i in r.items if i.category == c) for c in ("experience", "shared")}
    assert cats["experience"] > 0 and cats["shared"] > 0  # có cả hai nhóm, không nhóm nào chiếm hết


# ------------------------------------------------------------------ UT-MEM-04: khử trùng MMR
async def test_mem04_mmr_removes_near_duplicates(mem: AsyncConnection) -> None:
    a = await ep(mem, "content_agent", "Góp ý meta", "Meta description phải có tên sản phẩm và không quá 155 ký tự")
    b = await ep(mem, "content_agent", "Góp ý meta.", "Meta description phải có tên sản phẩm và không quá 155 ký tự nhé")
    c = await ep(mem, "content_agent", "Góp ý ảnh", "Ảnh bìa bài viết dùng ảnh thật của xưởng, không dùng ảnh mạng")
    r = await retrieval.retrieve(mem, "content_agent", "góp ý meta description ảnh bìa", use_vectors=False)
    assert c in ids(r) and (a in ids(r)) != (b in ids(r))


# ------------------------------------------------------------------ UT-MEM-05: chuẩn hóa tiếng Việt khớp ai/textnorm.py
def test_mem05_textnorm_parity() -> None:
    spec = importlib.util.spec_from_file_location("old_textnorm", BACKEND.parents[1] / "ai" / "xuong_ai" / "textnorm.py")
    assert spec and spec.loader
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    corpus = [
        "Trà Gừng – Mật Ong ĐẶC BIỆT!",
        "ship cod ko",
        "Sp này dc ko ạ?",
        "Cafe sữa đá",
        "Đường Phố Hàng Đào, Hà Nội 2026",
        "  nhiều   khoảng   trắng\tvà\nxuống dòng ",
        "Ứng dụng ưu đãi Tết Ất Tỵ",
        "",
    ]
    for s in corpus:
        assert textnorm.fold(s) == old.fold(s), s
        assert textnorm.terms(s) == old.terms(s), s


async def test_mem05_accent_free_and_abbreviation_queries(mem: AsyncConnection) -> None:
    m = await kn(mem, "company", "Chính sách giao hàng", "Sản phẩm không giao trong ngày; đơn trước 15 giờ gửi ngay hôm sau")
    for q in ("giao hàng trong ngày", "giao hang trong ngay", "GIAO HÀNG", "sp ko giao trong ngay", "ship trong ngày"):
        assert m in ids(await retrieval.retrieve(mem, "customer_agent", q, use_vectors=False, log=False)), q


# ------------------------------------------------------------------ UT-MEM-06: hết hạn / chưa kiểm chứng bị loại
async def test_mem06_validity_and_status(mem: AsyncConnection) -> None:
    ok = await kn(mem, "company", "Khuyến mãi", "Giảm giá trà sen 10% tháng này")
    old = await kn(mem, "company", "Khuyến mãi cũ", "Giảm giá trà sen 20% tháng trước", valid_to=datetime.now(UTC) - timedelta(days=1))
    cand = await kn(mem, "company", "Tin chưa kiểm", "Trà sen chữa mất ngủ", status="candidate", trust="unverified_external")
    gone = await kn(mem, "company", "Thông tin bỏ", "Trà sen giá 500.000đ")
    await store.retire(mem, gone, "user:owner")
    r = await retrieval.retrieve(mem, "content_agent", "trà sen giảm giá", use_vectors=False)
    assert ok in ids(r) and old not in ids(r) and cand not in ids(r) and gone not in ids(r)


# ------------------------------------------------------------------ UT-MEM-07: nhật ký truy hồi + usefulness
async def test_mem07_access_log_and_usefulness(mem: AsyncConnection) -> None:
    m = await ep(mem, "seo_agent", "Kinh nghiệm", "Tiêu đề có từ khóa ở đầu thì CTR tốt hơn")
    await retrieval.retrieve(mem, "seo_agent", "tiêu đề từ khóa", task_id="t-1", purpose="plan", use_vectors=False)
    rows = await db.all_(mem, "SELECT memory_id, principal, task_id, purpose, rank, used_in_output FROM memory_access_log")
    assert [(str(r["memory_id"]), r["principal"], r["task_id"], r["purpose"], r["rank"], r["used_in_output"]) for r in rows] == [
        (m, "agent:seo_agent", "t-1", "plan", 1, False)
    ]
    assert await retrieval.mark_used(mem, "seo_agent", "t-1", [m]) == 1
    assert await db.scalar(mem, "SELECT usefulness FROM agent_memories WHERE id = CAST(:i AS uuid)", {"i": m}) == 1


# ------------------------------------------------------------------ UT-MEM-08: working memory (Redis)
async def test_mem08_working_memory(env: None) -> None:
    from app.memory.working import WorkingMemory

    wm = WorkingMemory("seo_agent", "task-wm-1")
    await wm.set("goal", "Viết dàn ý bài trà gừng")
    assert await wm.add_step({"node": "retrieve", "ok": True}) == 1
    await wm.add_step({"node": "plan", "ok": True})
    snap = await wm.snapshot()
    assert snap == {"goal": "Viết dàn ý bài trà gừng", "steps": [{"node": "retrieve", "ok": True}, {"node": "plan", "ok": True}]}
    assert (await wm.close())["goal"] == "Viết dàn ý bài trà gừng"
    assert await wm.snapshot() == {"steps": []}
    await wm.r.aclose()


# ------------------------------------------------------------------ UT-MEM-09: chống ghi trùng, thay thế phiên bản
async def test_mem09_dedupe_and_supersede(mem: AsyncConnection) -> None:
    a = await ep(mem, "seo_agent", "Bài học", "Không nhồi từ khóa")
    assert await ep(mem, "seo_agent", "Bài học", "Không  nhồi từ khóa!") == a  # trùng sau chuẩn hóa
    old = await kn(mem, "company", "Giờ làm việc", "Xưởng mở cửa 8h đến 17h")
    new = await kn(mem, "company", "Giờ làm việc", "Xưởng mở cửa 7h30 đến 18h", supersedes=old)
    st = {str(r["id"]): r["verification_status"] for r in await db.all_(mem, "SELECT id, verification_status FROM agent_memories")}
    assert st[old] == "deprecated" and st[new] == "active"
    assert ids(await retrieval.retrieve(mem, "customer_agent", "giờ mở cửa xưởng", use_vectors=False)) == [new]


# ------------------------------------------------------------------ UT-MEM-10: phạm vi theo sơ đồ tổ chức
async def test_mem10_scopes_follow_org_chart(mem: AsyncConnection) -> None:
    assert await store.scopes_for(mem, "agent:seo_agent") == ["agent:seo_agent", "company", "dept:marketing"]
    md = await store.scopes_for(mem, "agent:marketing_director")
    assert {"agent:seo_agent", "agent:content_agent", "dept:marketing"} <= set(md) and "agent:customer_agent" not in md
    ceo = await store.scopes_for(mem, "agent:ai_ceo")
    assert {"dept:marketing", "dept:sales", "dept:technology", "agent:marketing_director"} <= set(ceo) and "agent:seo_agent" not in ceo
    assert "owner_only" in await store.scopes_for(mem, "owner") and "owner_only" not in ceo
    m = await ep(mem, "seo_agent", "Kinh nghiệm SEO", "Bài dài 1.500 chữ xếp hạng tốt hơn bài ngắn")
    assert m in ids(await retrieval.retrieve(mem, "marketing_director", "bài dài xếp hạng", use_vectors=False))
    assert m not in ids(await retrieval.retrieve(mem, "content_agent", "bài dài xếp hạng", use_vectors=False))  # chưa chia sẻ qua thẩm định


# ------------------------------------------------------------------ IT-DB-02: RLS ở tầng CSDL
async def test_itdb02_rls_blocks_other_agents_even_with_raw_sql(mem: AsyncConnection) -> None:
    from sqlalchemy.exc import DBAPIError

    ads = await ep(mem, "ads_agent", "Bí mật Ads", "CPA mục tiêu 25.000đ")
    async with mem.begin_nested():
        async with store.acting_as(mem, "aico_agent", "agent:seo_agent", ["agent:seo_agent", "dept:marketing", "company"]) as c:
            # Lớp ứng dụng có lỗi, quên lọc phạm vi: RLS vẫn chặn
            assert await db.scalar(c, "SELECT count(*) FROM agent_memories WHERE owner_scope = 'agent:ads_agent'") == 0
            assert await db.scalar(c, "SELECT count(*) FROM agent_memories WHERE id = CAST(:i AS uuid)", {"i": ads}) == 0
            assert await db.scalar(c, "SELECT count(*) FROM episodic_memories") == 0
    for sql in (
        "INSERT INTO agent_memories(id, owner_scope, type, title, content, search_text, source_trust, content_hash, created_by_principal) "
        "VALUES (gen_random_uuid(), 'agent:ads_agent', 'episodic', 'x', 'x', 'x', 'internal', 'h1', 'agent:seo_agent')",
        "INSERT INTO agent_memories(id, owner_scope, type, title, content, search_text, source_trust, content_hash, created_by_principal) "
        "VALUES (gen_random_uuid(), 'agent:seo_agent', 'semantic', 'x', 'x', 'x', 'internal', 'h2', 'agent:seo_agent')",
        "UPDATE agent_memories SET title = 'sửa' ",
    ):
        with pytest.raises(DBAPIError):
            async with mem.begin_nested():  # ghi vùng agent khác / loại agent không được ghi / không có quyền sửa
                async with store.acting_as(mem, "aico_agent", "agent:seo_agent", ["agent:seo_agent"]) as c:
                    await db.execute(c, sql)
    async with mem.begin_nested():
        async with store.acting_as(mem, "aico_agent", "agent:ads_agent", ["agent:ads_agent"]) as c:
            assert await db.scalar(c, "SELECT count(*) FROM agent_memories") == 1


async def test_itdb02_search_functions_stay_in_session_scope(mem: AsyncConnection) -> None:
    """Hàm tìm kiếm SECURITY DEFINER (để dùng được chỉ mục) vẫn chỉ trả mục trong phạm vi của phiên, không nhận phạm vi qua tham số."""
    ads = await ep(mem, "ads_agent", "Bí mật Ads", "CPA mục tiêu 25.000đ cho trà sen")
    seo = await ep(mem, "seo_agent", "Ghi chú SEO", "CPA không phải việc của SEO, trà sen lên top")
    lit = "[" + ",".join("0.1" for _ in range(DIMS)) + "]"
    for mid in (ads, seo):
        await db.execute(
            mem,
            "INSERT INTO memory_embeddings(memory_id, model_id, embedding) VALUES (CAST(:m AS uuid), 'openai-te3s-512', CAST(:v AS vector))",
            {"m": mid, "v": lit},
        )
    kw = "SELECT id FROM aico_mem_keyword('cpa', 'cpa', true, NULL, NULL, NULL, '{}', 100, 100)"
    vec = f"SELECT id FROM aico_mem_vector('openai-te3s-512', 512, '{lit}', NULL, NULL, NULL, 100, 100)"
    async with mem.begin_nested():
        async with store.acting_as(mem, "aico_agent", "agent:seo_agent", ["agent:seo_agent", "dept:marketing", "company"]) as c:
            assert [str(x["id"]) for x in await db.all_(c, kw)] == [seo]
            assert [str(x["id"]) for x in await db.all_(c, vec)] == [seo]
    async with mem.begin_nested():
        async with store.acting_as(mem, "aico_agent", "agent:seo_agent", []) as c:  # phiên không có phạm vi: không thấy gì
            assert await db.all_(c, kw) == [] and await db.all_(c, vec) == []
    for fn in ("aico_mem_keyword", "aico_mem_vector"):  # không cấp cho PUBLIC
        acl = await db.scalar(
            mem, "SELECT count(*) FROM pg_proc p, aclexplode(p.proacl) a WHERE p.proname = :f AND a.grantee = 0", {"f": fn}
        )
        assert acl == 0


# ------------------------------------------------------------------ IT-VEC-01: HNSW đúng láng giềng gần
async def test_itvec01_hnsw_recall_and_index_use(mem: AsyncConnection) -> None:
    rnd = random.Random(7)
    n = 3000
    vecs: dict[str, list[float]] = {}
    rows = []
    for i in range(n):
        v = [rnd.gauss(0, 1) for _ in range(DIMS)]
        norm = math.sqrt(sum(x * x for x in v))
        v = [x / norm for x in v]
        mid = f"00000000-0000-7000-8000-{i:012d}"
        vecs[mid] = v
        rows.append(f"('{mid}', 'company', 'semantic', 'v{i}', 'nội dung {i}', 'noi dung {i}', 'internal', 'h{i}', 'test')")
    await mem.exec_driver_sql(
        "INSERT INTO agent_memories(id, owner_scope, type, title, content, search_text, source_trust, content_hash, created_by_principal) VALUES "
        + ",".join(rows)
    )
    await mem.exec_driver_sql(
        "INSERT INTO memory_embeddings(memory_id, model_id, embedding) VALUES "
        + ",".join(f"('{k}', 'openai-te3s-512', '[{','.join(f'{x:.6f}' for x in v)}]')" for k, v in vecs.items())
    )
    await mem.exec_driver_sql("ANALYZE memory_embeddings")
    recalls = []
    for q in range(10):
        qv = vecs[f"00000000-0000-7000-8000-{q * 97:012d}"]
        qv = [x + rnd.gauss(0, 0.02) for x in qv]
        exact = sorted(vecs, key=lambda k: -sum(a * b for a, b in zip(vecs[k], qv, strict=True)))[:10]
        r = await retrieval.retrieve(
            mem, "content_agent", "zzz", query_vector=qv, log=False, budget_tokens=100000, limit_each=10, share_ratio={"shared": 1.0}
        )
        got = [i.memory_id for i in r.items if i.vec_rank]
        recalls.append(len(set(got) & set(exact)) / 10)
    assert sum(recalls) / len(recalls) >= 0.9, recalls
    lit = "[" + ",".join("0" for _ in range(DIMS)) + "]"
    # 3.000 dòng thì quét rồi sắp xếp cũng rẻ (planner pg17 + pgvector 0.8 chọn vậy); ở đây chỉ kiểm chỉ mục HNSW một phần DÙNG ĐƯỢC
    for knob in ("enable_seqscan", "enable_bitmapscan", "enable_sort"):
        await mem.exec_driver_sql(f"SET LOCAL {knob} = off")
    plan = "\n".join(
        r[0]
        for r in (
            await mem.exec_driver_sql(
                "EXPLAIN SELECT memory_id FROM memory_embeddings WHERE model_id = 'openai-te3s-512' "
                f"ORDER BY embedding::vector(512) <=> '{lit}'::vector(512) LIMIT 10"
            )
        ).fetchall()
    )
    assert "memory_embeddings_hnsw_openai_te3s_512" in plan, plan


# ------------------------------------------------------------------ IT-VEC-02: đổi model → nhúng lại
async def test_itvec02_reembed_on_model_change(mem: AsyncConnection, fake_embed: FakeEmbeddings) -> None:
    from app.domain import store as secrets
    from app.memory import embedding

    for i in range(5):
        await kn(mem, "company", f"Mục {i}", f"Nội dung trà số {i}, khách 0912345678")
    none = await embedding.embed_pending(mem)
    assert none.status == "not_configured" and none.remaining == 5  # chưa có khóa OpenAI: không lỗi, chờ nhúng sau
    await secrets.put_secret(mem, "provider.openai.api_key", "sk-test-" + "e" * 30, "test")
    first = await embedding.embed_pending(mem)
    assert first.status == "done" and first.embedded == 5 and first.model == "openai-te3s-512"
    assert all("0912345678" not in t for call in fake_embed.calls for t in call["input"])  # type: ignore[union-attr]
    assert fake_embed.calls[0]["dimensions"] == 512
    cost = await db.scalar(mem, "SELECT sum(cost_usd) FROM model_usage WHERE purpose = 'memory_embed'")
    assert cost is not None and float(cost) > 0
    await mem.exec_driver_sql(
        "INSERT INTO embedding_models(id, model_id, dims) VALUES ('openai-te3s-512-v2', 'text-embedding-3-small', 512)"
    )
    await embedding.switch_model(mem, "openai-te3s-512-v2")
    assert await embedding.pending_count(mem, "openai-te3s-512-v2") == 5
    assert await embedding.prune_old(mem) == 0  # model mới chưa nhúng đủ: giữ vector cũ
    again = await embedding.embed_pending(mem)
    assert again.embedded == 5 and again.remaining == 0 and again.model == "openai-te3s-512-v2"
    assert await embedding.prune_old(mem) == 5
    assert await db.scalar(mem, "SELECT count(DISTINCT model_id) FROM memory_embeddings") == 1


async def test_vector_finds_memory_without_shared_words(mem: AsyncConnection) -> None:
    m = await kn(mem, "company", "Quà biếu", "Hộp trà sen cao cấp làm quà Tết cho đối tác")
    v = fake_vec("Hộp trà sen cao cấp làm quà Tết cho đối tác")
    await mem.exec_driver_sql(
        f"INSERT INTO memory_embeddings(memory_id, model_id, embedding) VALUES ('{m}', 'openai-te3s-512', "
        f"'[{','.join(f'{x:.6f}' for x in v)}]')"
    )
    r = await retrieval.retrieve(mem, "sales_intelligence", "món tặng sếp đầu năm", query_vector=v, log=False)
    item = next(i for i in r.items if i.memory_id == m)
    assert item.vec_rank == 1 and item.kw_rank is None  # chỉ tìm thấy nhờ vector
