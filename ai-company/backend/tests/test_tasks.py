"""UT-TASK-*: Task Engine (trạng thái, phụ thuộc, hợp đồng giao việc, lease, thử lại, hủy), lịch cron, Message Bus (IT-A2A-01/04)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import DBAPIError

from tests.conftest import needs_db
from tests.officekit import make_task, rows, task

pytestmark = needs_db


async def _tx():  # type: ignore[no-untyped-def]
    from app.core import db

    return db.engine().begin()


# ------------------------------------------------------------------ UT-TASK-01: bảng chuyển trạng thái, hai lớp
async def test_ut_task_01_transitions_checked_in_code_and_db(office: object) -> None:
    from app.core import db
    from app.core.errors import AppError
    from app.tasks import engine

    t = await make_task(title="Viết mô tả trà sen", assigned_agent="content_agent")
    assert t["status"] == "ASSIGNED"  # tạo → chờ → sẵn sàng (không phụ thuộc)
    logs = await rows("SELECT text FROM task_logs WHERE task_id = :t ORDER BY id", {"t": t["id"]})
    assert [x["text"] for x in logs][:3] == ["Tạo việc: Viết mô tả trà sen", "mới tạo → đang chờ", "đang chờ → chờ làm"]
    async with await _tx() as c:
        with pytest.raises(AppError) as e:
            await engine.transition(c, str(t["id"]), "COMPLETED", actor="test")
        assert e.value.code == "TASK_TRANSITION_INVALID"
    async with await _tx() as c:  # lớp 2: CSDL từ chối dù mã có lỗi
        with pytest.raises(DBAPIError, match="TASK_TRANSITION_INVALID"):
            await db.execute(c, "UPDATE tasks SET status = 'COMPLETED' WHERE id = :i", {"i": t["id"]})
    for cur, nxt in [("COMPLETED", "IN_PROGRESS"), ("CANCELLED", "PENDING"), ("CREATED", "COMPLETED")]:
        assert not engine.can(cur, nxt)
    assert engine.can("IN_PROGRESS", "PENDING") and engine.can("FAILED", "PENDING")


# ------------------------------------------------------------------ UT-TASK-02: phụ thuộc, vòng lặp
async def test_ut_task_02_dependencies_and_cycles(office: object) -> None:
    from app.core.errors import AppError
    from app.tasks import engine

    a = await make_task(title="Nghiên cứu từ khóa", assigned_agent="seo_agent")
    b = await make_task(title="Viết bài theo từ khóa", assigned_agent="content_agent", depends_on=[str(a["id"])])
    assert b["status"] == "PENDING"  # chờ a
    async with await _tx() as c:
        with pytest.raises(AppError) as e:
            await engine.add_dependency(c, str(a["id"]), str(b["id"]))
        assert e.value.code == "TASK_DEPENDENCY_CYCLE"
    async with await _tx() as c:
        await engine.transition(c, str(a["id"]), "IN_PROGRESS", actor="test")
        await engine.complete(c, str(a["id"]), {"keywords": ["trà sen"]}, "xong", actor="test")
    assert (await task(str(b["id"])))["status"] == "ASSIGNED"


# ------------------------------------------------------------------ UT-TASK-03: hợp đồng giao việc
async def test_ut_task_03_delegation_contract(office: object) -> None:
    from app.core.errors import AppError
    from app.tasks import engine

    soon = datetime.now(UTC) + timedelta(hours=4)
    ok = {"title": "Viết FAQ giao hàng", "assigned_agent": "content_agent", "created_by": "agent:marketing_director"}
    for bad, code in [
        ({}, "TASK_CONTRACT_INVALID"),  # thiếu tiêu chí
        ({"success_criteria": ["có câu trả lời"], "budget_usd": 0}, "TASK_CONTRACT_INVALID"),
        ({"success_criteria": ["có câu trả lời"], "budget_usd": 0.1}, "TASK_CONTRACT_INVALID"),  # thiếu hạn
    ]:
        async with await _tx() as c:
            with pytest.raises(AppError) as e:
                await engine.create(c, **ok, **bad)
            assert e.value.code == code
    parent = await make_task(title="Kế hoạch tuần", assigned_agent="marketing_director", budget_usd=0.3, deadline=soon, autonomy_max=2)
    good = {**ok, "success_criteria": ["có câu trả lời"], "deadline": soon + timedelta(days=3), "parent_id": str(parent["id"])}
    async with await _tx() as c:
        with pytest.raises(AppError) as e:
            await engine.create(c, **good, budget_usd=0.5)
        assert e.value.code == "TASK_BUDGET_EXCEEDED"
    child = await make_task(**{**good, "budget_usd": 0.1, "autonomy_max": 4})
    assert child["depth"] == 1 and child["root_id"] == parent["id"]
    assert child["deadline"] == parent["deadline"] and child["autonomy_max"] == 2  # không vượt hạn, cấp của cha
    for i in range(2):  # chống vòng lặp: cùng (người giao, người nhận, loại) quá 3 lần/giờ
        await make_task(**{**good, "budget_usd": 0.01, "title": f"FAQ {i}"})
    async with await _tx() as c:
        with pytest.raises(AppError) as e:
            await engine.create(c, **{**good, "budget_usd": 0.01, "title": "FAQ 3"})
        assert e.value.code == "TASK_LOOP_BLOCKED"


async def test_ut_task_03b_depth_and_children_limits(office: object) -> None:
    from app.core import db
    from app.core.errors import AppError
    from app.tasks import engine

    root = await make_task(title="Gốc", assigned_agent="ai_ceo", budget_usd=2)
    cur = root
    for d in range(1, 5):  # độ sâu tối đa 4
        cur = await make_task(title=f"Tầng {d}", assigned_agent="ai_ceo", parent_id=str(cur["id"]), budget_usd=0.1)
    async with await _tx() as c:
        with pytest.raises(AppError) as e:
            await engine.create(
                c, title="Tầng 5", assigned_agent="ai_ceo", created_by="user:owner", parent_id=str(cur["id"]), budget_usd=0.01
            )
        assert e.value.code == "TASK_TOO_DEEP"
    async with await _tx() as c:  # 6 con là tối đa (đã có 1)
        for i in range(5):
            await engine.create(
                c, title=f"Con {i}", assigned_agent="seo_agent", created_by="user:owner", parent_id=str(root["id"]), budget_usd=0.01
            )
        with pytest.raises(AppError) as e:
            await engine.create(
                c, title="Con 7", assigned_agent="seo_agent", created_by="user:owner", parent_id=str(root["id"]), budget_usd=0.01
            )
        assert e.value.code == "TASK_TOO_MANY_CHILDREN"
        assert int(await db.scalar(c, "SELECT count(*) FROM tasks WHERE parent_id = :p", {"p": root["id"]})) == 6


# ------------------------------------------------------------------ UT-TASK-04: nhận việc bằng lease
async def test_ut_task_04_claim_lease_priority_and_agent_limits(office: object) -> None:
    from app.core import db
    from app.tasks import engine

    low = await make_task(title="Việc thường", assigned_agent="seo_agent", priority=3)
    high = await make_task(title="Việc gấp", assigned_agent="seo_agent", priority=0)
    other = await make_task(title="Việc của Content", assigned_agent="content_agent", priority=2)
    paused = await make_task(title="Việc của Ads", assigned_agent="ads_agent", priority=0)
    async with await _tx() as c:
        await db.execute(
            c, "UPDATE agent_status SET state = 'paused' WHERE agent_id = (SELECT id FROM agents WHERE agent_key = 'ads_agent')"
        )
    async with await _tx() as c:
        got = await engine.claim(c, "w1", 10)
    ids = [str(t["id"]) for t in got]
    assert ids == [str(high["id"]), str(other["id"])]  # ưu tiên trước; mỗi agent một việc; agent tạm dừng bị bỏ qua
    assert str(low["id"]) not in ids and str(paused["id"]) not in ids
    t = await task(str(high["id"]))
    assert t["status"] == "IN_PROGRESS" and t["lease_owner"] == "w1" and t["timeout_at"] is not None
    async with await _tx() as c:  # worker khác không nhận lại khi lease còn hạn
        assert await engine.claim(c, "w2", 10) == []
        await db.execute(c, "UPDATE tasks SET lease_until = now() - interval '1 second' WHERE id = :i", {"i": high["id"]})
    async with await _tx() as c:
        got2 = await engine.claim(c, "w2", 10)
    assert [str(x["id"]) for x in got2] == [str(high["id"])]  # lease hết hạn: worker khác nhận lại
    logs = await rows("SELECT event FROM task_logs WHERE task_id = :t", {"t": high["id"]})
    assert "lease" in [x["event"] for x in logs]


# ------------------------------------------------------------------ UT-TASK-05: thử lại có giãn cách, hết lượt thì báo cấp trên
async def test_ut_task_05_retry_backoff_then_error_report(office: object) -> None:
    from app.tasks import engine

    t = await make_task(title="Đọc số liệu", assigned_agent="data_analyst", max_attempts=2)
    async with await _tx() as c:
        await engine.claim(c, "w", 1)
        r = await engine.fail(c, str(t["id"]), "LLM_FAILED", "nhà cung cấp lỗi", actor="test")
    assert r["status"] == "PENDING" and r["attempt"] == 2 and r["not_before"] > datetime.now(UTC) + timedelta(seconds=20)
    async with await _tx() as c:
        assert await engine.promote(c, str(t["id"])) == []  # chưa tới giờ thử lại
        await c.exec_driver_sql(f"UPDATE tasks SET not_before = now() WHERE id = '{t['id']}'")
        assert await engine.promote(c, str(t["id"])) == [str(t["id"])]
        await engine.claim(c, "w", 1)
        r = await engine.fail(c, str(t["id"]), "LLM_FAILED", "lại lỗi", actor="test")
    assert r["status"] == "FAILED"
    msgs = await rows("SELECT message_type, receiver, payload FROM agent_messages WHERE task_id = :t", {"t": t["id"]})
    assert msgs[0]["message_type"] == "error_report" and msgs[0]["receiver"] == "agent:growth_director"  # cấp trên của Data Analyst
    t2 = await make_task(title="Việc bị cấm", assigned_agent="data_analyst")
    async with await _tx() as c:
        await engine.claim(c, "w", 1)
        r = await engine.fail(c, str(t2["id"]), "POLICY_DENIED", "không có quyền", actor="test")
    assert r["status"] == "FAILED" and r["attempt"] == 1  # lỗi không tạm thời: không thử lại


# ------------------------------------------------------------------ UT-TASK-06: hủy lan xuống task con + hủy yêu cầu duyệt
async def test_ut_task_06_cancel_cascades(office: object) -> None:
    from app.domain import approvals
    from app.tasks import engine

    p = await make_task(title="Chiến dịch Tết", assigned_agent="marketing_director", budget_usd=1)
    c1 = await make_task(title="Bài blog Tết", assigned_agent="content_agent", parent_id=str(p["id"]), budget_usd=0.2)
    g1 = await make_task(title="Ảnh bìa", assigned_agent="creative_agent", parent_id=str(c1["id"]), budget_usd=0.1)
    async with await _tx() as c:
        await approvals.create(
            c,
            subject_type="task_output",
            subject_id=str(g1["id"]),
            action="task.generic",
            title="Ảnh bìa",
            summary="",
            payload={"x": 1},
            risk="low",
            requested_by="agent:creative_agent",
        )
        ids = await engine.cancel(c, str(p["id"]), actor="user:owner", reason="đổi kế hoạch")
    assert set(ids) == {str(p["id"]), str(c1["id"]), str(g1["id"])}
    for i in ids:
        assert (await task(i))["status"] == "CANCELLED"
    a = await rows("SELECT status FROM approvals WHERE subject_id = :s", {"s": str(g1["id"])})
    assert a[0]["status"] == "cancelled"


# ------------------------------------------------------------------ UT-TASK-07 + IT-REC-03: cron và chạy bù
def test_ut_task_07_cron_next_run_in_vietnam_time() -> None:
    from app.core.errors import AppError
    from app.tasks.scheduler import next_after

    t0 = datetime(2026, 11, 27, 1, 0, tzinfo=UTC)  # 08:00 giờ VN, thứ Sáu
    assert next_after("30 8 * * *", t0) == datetime(2026, 11, 27, 1, 30, tzinfo=UTC)
    assert next_after("0 8 * * 1", t0) == datetime(2026, 11, 30, 1, 0, tzinfo=UTC)  # thứ Hai kế tiếp
    assert next_after("0 8 * * 7", t0) == datetime(2026, 11, 29, 1, 0, tzinfo=UTC)  # 7 = Chủ nhật
    assert next_after("*/15 * * * *", t0) == datetime(2026, 11, 27, 1, 15, tzinfo=UTC)
    assert next_after("0 9 1 1 *", t0) == datetime(2027, 1, 1, 2, 0, tzinfo=UTC)
    for bad in ("* * *", "61 * * * *", "0 25 * * *", "*/0 * * * *"):
        with pytest.raises(AppError):
            next_after(bad, t0)


async def test_it_rec_03_scheduler_catches_up_once(office: object) -> None:
    from app.core import db
    from app.core.ids import uuid7
    from app.tasks import scheduler

    now = datetime.now(UTC)
    tpl = '{"title": "Báo cáo sáng", "success_criteria": ["có số liệu hôm qua"], "budget_usd": 0.05}'
    async with await _tx() as c:
        for name, due in (("bao-cao-sang", now - timedelta(hours=10)), ("lo-qua-lau", now - timedelta(hours=30))):
            await db.execute(
                c,
                "INSERT INTO schedules(id, name, agent_key, cron, task_template, next_run_at, created_by) "
                "VALUES (:i, :n, 'data_analyst', '0 7 * * *', CAST(:t AS jsonb), :d, 'test')",
                {"i": uuid7(), "n": name, "t": tpl, "d": due},
            )
        created = await scheduler.tick(c, now)
        again = await scheduler.tick(c, now)  # quét lại không tạo thêm
    assert len(created) == 1 and again == []
    t = await task(created[0])
    assert t["created_by"] == "system:scheduler" and t["input_data"]["late_minutes"] >= 590
    logs = await rows("SELECT event FROM task_logs WHERE task_id = :t", {"t": created[0]})
    assert "catch_up" in [x["event"] for x in logs]
    sch = {x["name"]: x for x in await rows("SELECT * FROM schedules")}
    assert all(s["next_run_at"] > now for s in sch.values())  # lần kế tiếp tính từ hiện tại (không dồn)


# ------------------------------------------------------------------ IT-A2A-01: outbox ít nhất một lần, bỏ bản trùng
async def test_it_a2a_01_outbox_at_least_once_dedup(office: object) -> None:
    from app.core import db
    from app.tasks import bus

    parent = await make_task(title="Kế hoạch nội dung", assigned_agent="marketing_director", budget_usd=1)
    payload = {
        "task_id": "0193f0a0-0000-7000-8000-000000000001",
        "title": "Viết FAQ đổi trả",
        "success_criteria": [{"type": "required_fields", "fields": ["answer"]}],
        "budget_usd": 0.1,
        "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }
    async with await _tx() as c:
        m1 = await bus.send(
            c,
            "task_request",
            sender="agent:marketing_director",
            receiver="agent:content_agent",
            task_id=str(parent["id"]),
            payload=payload,
            key="k-1",
        )
        m2 = await bus.send(
            c,
            "task_request",
            sender="agent:marketing_director",
            receiver="agent:content_agent",
            task_id=str(parent["id"]),
            payload=payload,
            key="k-1",
        )
    assert m1 == m2  # cùng khóa: một message
    assert await bus.dispatch() == 1
    async with await _tx() as c:  # giả lập giao lại (worker chết sau khi tạo task, trước khi đánh dấu đã giao)
        await db.execute(c, "UPDATE agent_messages SET status = 'queued' WHERE id = :i", {"i": m1})
    assert await bus.dispatch() == 1
    kids = await rows("SELECT id, created_by, depth FROM tasks WHERE parent_id = :p", {"p": parent["id"]})
    assert len(kids) == 1 and str(kids[0]["id"]) == payload["task_id"] and kids[0]["created_by"] == "agent:marketing_director"
    async with await _tx() as c:  # message lỗi hợp đồng: không thử mãi, task cha không chờ mãi
        bad = {**payload, "task_id": "0193f0a0-0000-7000-8000-000000000002", "success_criteria": []}
        await db.execute(
            c, "INSERT INTO task_dependencies(task_id, depends_on) VALUES (:p, CAST(:c AS uuid))", {"p": parent["id"], "c": bad["task_id"]}
        )
        await bus.send(
            c,
            "task_request",
            sender="agent:marketing_director",
            receiver="agent:content_agent",
            task_id=str(parent["id"]),
            payload=bad,
            key="k-2",
        )
    await bus.dispatch()
    m = await rows("SELECT status, last_error FROM agent_messages WHERE idempotency_key = 'k-2'")
    assert m[0]["status"] == "failed" and "tiêu chí" in m[0]["last_error"]
    assert await rows("SELECT 1 FROM task_dependencies WHERE depends_on = CAST(:c AS uuid)", {"c": bad["task_id"]}) == []


async def test_it_a2a_04_knowledge_goes_to_candidate_box_only(office: object) -> None:
    from app.tasks import bus

    async with await _tx() as c:
        await bus.send(
            c,
            "knowledge_sharing",
            sender="agent:seo_agent",
            receiver="learning_engine",
            trust="untrusted",
            payload={"title": "Từ khóa mùa đông", "claim": "Khách tìm 'trà gừng' tăng mạnh từ tháng 11", "evidence": ["gsc"]},
            key="share-1",
        )
    await bus.dispatch()
    await bus.dispatch()
    cand = await rows("SELECT * FROM knowledge_candidates")
    assert len(cand) == 1 and cand[0]["status"] == "pending" and cand[0]["trust"] == "untrusted"
    assert await rows("SELECT 1 FROM agent_memories") == []  # không ghi thẳng vào trí nhớ của ai
