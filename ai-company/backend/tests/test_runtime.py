"""IT-LG-01/03, IT-REC-01/02, IT-A2A-02/03: đồ thị nhận thức LangGraph chạy thật trên Postgres, model giả theo kịch bản."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tests.conftest import needs_db
from tests.officekit import FakeModel, composed, done, drain, make_task, rows, steps, task

pytestmark = needs_db


async def _events(tid: Any) -> list[str]:
    return [x["event"] for x in await rows("SELECT event FROM task_logs WHERE task_id = :t ORDER BY id", {"t": tid})]


# ------------------------------------------------------------------ IT-LG-01: chạy trọn đồ thị; tự kiểm tra tất định
async def test_it_lg_01_task_runs_through_graph_with_self_check(office: FakeModel) -> None:
    def script(agent: str, phase: str, title: str, prompt: str) -> dict[str, Any] | None:
        if "Tự kiểm tra: thiếu trường: description" in prompt:
            return done({"description": "Trà sen Tây Hồ ướp thủ công, hương sen dịu, hợp biếu Tết."})
        return done({"title": "Trà sen"})  # lần đầu thiếu trường bắt buộc

    office.script = script
    t = await make_task(
        title="Viết mô tả ngắn cho trà sen",
        assigned_agent="content_agent",
        success_criteria=[
            {"type": "required_fields", "fields": ["description"]},
            {"type": "max_len", "field": "description", "n": 300},
            {"type": "not_contains", "field": "description", "text": "chữa bệnh"},
        ],
    )
    await drain()
    t = await task(str(t["id"]))
    assert t["status"] == "COMPLETED", t["error"]
    assert "hương sen" in t["output_data"]["description"]
    assert float(t["spent_usd"]) > 0  # chi phí model cộng vào task
    ev = await _events(t["id"])
    for e in ("start", "recall", "plan", "verify_failed", "verify_ok", "reflect"):
        assert e in ev
    assert [c["phase"] for c in office.calls] == ["plan", "plan"]
    assert "Bạn là Chăm sóc nội dung" in office.calls[0]["system"] or "(content_agent)" in office.calls[0]["system"]
    mem = await rows("SELECT owner_scope, type, title FROM agent_memories")
    assert mem == [{"owner_scope": "agent:content_agent", "type": "episodic", "title": "Trải nghiệm: Viết mô tả ngắn cho trà sen"}]
    usage = await rows("SELECT task_id, agent_key FROM model_usage")
    assert {str(u["task_id"]) for u in usage} == {str(t["id"])} and {u["agent_key"] for u in usage} == {"content_agent"}


# ------------------------------------------------------------------ IT-REC-01: worker chết giữa đồ thị → chạy tiếp, không làm lại tác động
async def test_it_rec_01_crash_mid_graph_resumes_without_repeating_tool(office: FakeModel, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import db
    from app.tasks import graph, runtime

    class Killed(BaseException):
        """Tiến trình worker bị giết: không khối except nào của mã chạy được."""

    crashed = {"n": 0}
    real = runtime.node_compose

    async def flaky(s: runtime.State) -> runtime.State:
        if crashed["n"] == 0:
            crashed["n"] += 1
            raise Killed
        return await real(s)

    monkeypatch.setattr(runtime, "node_compose", flaky)
    await graph.close()  # dựng lại đồ thị với nút đã thay
    office.script = lambda agent, phase, title, prompt: (
        steps(("notify", "owner", {"text": "Doanh thu tuần tăng 12%", "kind": "report"}))
        if phase == "plan"
        else composed({"summary": "Đã gửi báo cáo tuần cho Owner"})
    )
    t = await make_task(title="Gửi báo cáo tuần", assigned_agent="ai_ceo", autonomy_max=3)
    with pytest.raises(Killed):
        await drain()
    mid = await task(str(t["id"]))
    assert mid["status"] == "IN_PROGRESS" and mid["lease_owner"] == "test-worker"
    async with db.engine().begin() as c:  # lease hết hạn (worker không còn gia hạn)
        await db.execute(c, "UPDATE tasks SET lease_until = now() - interval '1 second' WHERE id = :i", {"i": t["id"]})
    await graph.close()  # "khởi động lại" tiến trình
    await drain()
    t = await task(str(t["id"]))
    assert t["status"] == "COMPLETED", t["error"]
    inv = await rows("SELECT tool_id, action, status FROM tool_invocations WHERE task_id = :t", {"t": str(t["id"])})
    assert inv == [{"tool_id": "notify", "action": "owner", "status": "succeeded"}]
    assert len(await rows("SELECT 1 FROM notifications WHERE text LIKE '%Doanh thu tuần%'")) == 1  # tác động đúng một lần
    assert [c["phase"] for c in office.calls].count("plan") == 1  # nút đã xong trước sự cố không chạy lại
    assert "lease" in await _events(t["id"])


# ------------------------------------------------------------------ IT-REC-02 + interrupt: chờ duyệt qua khởi động lại
@pytest.mark.parametrize("approve", [True, False])
async def test_it_rec_02_waiting_approval_survives_restart(office: FakeModel, approve: bool) -> None:
    from app.core import db
    from app.domain import approvals
    from app.tasks import graph

    office.script = lambda *a: done({"question": "Có giao trong ngày không?", "answer": "Đơn trước 15 giờ gửi sáng hôm sau."})
    t = await make_task(title="Soạn FAQ giao hàng", assigned_agent="content_agent", requires_approval=True)
    await drain()
    t = await task(str(t["id"]))
    assert t["status"] == "WAITING_APPROVAL" and t["wait_kind"] == "approval" and t["lease_owner"] is None
    ap = await rows("SELECT id, subject_type, payload FROM approvals WHERE status = 'pending'")
    assert ap[0]["subject_type"] == "task_output" and ap[0]["payload"]["output"]["answer"].startswith("Đơn trước 15 giờ")
    await graph.close()  # khởi động lại cả hệ thống: trạng thái chờ nằm trong CSDL + checkpoint
    await drain()
    assert (await task(str(t["id"])))["status"] == "WAITING_APPROVAL"  # vẫn chờ, không tự chạy tiếp
    async with db.engine().begin() as c:
        await approvals.decide(c, str(ap[0]["id"]), approve, "user:owner", None if approve else "Câu trả lời cần thân thiện hơn")
    assert (await task(str(t["id"])))["status"] == "IN_PROGRESS"  # đã đánh thức
    await drain()
    t = await task(str(t["id"]))
    assert t["status"] == ("COMPLETED" if approve else "CANCELLED")
    mem = await rows("SELECT content FROM agent_memories WHERE owner_scope = 'agent:content_agent'")
    assert len(mem) == 1
    if not approve:
        assert "thân thiện hơn" in mem[0]["content"]  # lời từ chối của Owner thành trải nghiệm của agent
    assert len([c for c in office.calls if c["phase"] == "plan"]) == 1


# ------------------------------------------------------------------ Policy Engine chặn → lập lại kế hoạch → hết lượt thì lỗi
async def test_policy_denied_step_triggers_replan_then_fails(office: FakeModel) -> None:
    office.script = lambda *a: steps(("ads", "update_budget", {"campaign": "tet", "daily_vnd": 500000}))
    t = await make_task(title="Tăng ngân sách quảng cáo Tết", assigned_agent="seo_agent")
    await drain()
    t = await task(str(t["id"]))
    assert t["status"] == "FAILED" and t["error_code"] == "POLICY_DENIED"
    assert len([c for c in office.calls if c["phase"] == "plan"]) == 3  # lần đầu + 2 lần lập lại
    assert "bị chặn" in office.calls[1]["prompt"]
    assert await rows("SELECT 1 FROM tool_invocations") == []  # chưa bước nào bị chặn được chạy
    msgs = await rows("SELECT message_type, receiver FROM agent_messages WHERE task_id = :t", {"t": str(t["id"])})
    assert msgs == [{"message_type": "error_report", "receiver": "agent:marketing_director"}]


# ------------------------------------------------------------------ IT-A2A-02/03: giao việc → review → sửa → duyệt → task cha chạy tiếp
async def test_it_a2a_02_delegate_review_rework_and_parent_resumes(office: FakeModel) -> None:
    def script(agent: str, phase: str, title: str, prompt: str) -> dict[str, Any] | None:
        if agent == "marketing_director" and title == "Lên FAQ giao hàng cho website":
            if phase == "plan":
                return steps(
                    (
                        "task",
                        "delegate",
                        {
                            "agent": "content_agent",
                            "title": "Viết FAQ giao hàng",
                            "success_criteria": [{"type": "required_fields", "fields": ["question", "answer"]}],
                            "budget_usd": 0.2,
                            "deadline_hours": 24,
                        },
                    )
                )
            assert "Đơn đặt trước 15 giờ" in prompt  # kết quả task con được đưa vào bước soạn
            return composed({"summary": "FAQ giao hàng đã sẵn sàng", "faq_count": 1})
        if agent == "content_agent":
            if "Góp ý của marketing_director" in prompt:
                return done({"question": "Có giao trong ngày không?", "answer": "Đơn đặt trước 15 giờ được gửi ngay sáng hôm sau."})
            return done({"question": "Có giao trong ngày không?", "answer": "Có ạ."})
        if agent == "marketing_director" and title.startswith("Review:"):
            if "15 giờ" in prompt:
                return done({"verdict": "approve", "notes": "Rõ ràng, đúng chính sách."})
            return done(
                {
                    "verdict": "request_changes",
                    "notes": "Ghi rõ đơn trước 15 giờ gửi sáng hôm sau; xưởng không giao trong ngày.",
                    "checks": [{"type": "contains", "field": "answer", "text": "15 giờ"}],
                }
            )
        return None

    office.script = script
    main = await make_task(
        title="Lên FAQ giao hàng cho website",
        assigned_agent="marketing_director",
        budget_usd=1,
        deadline=datetime.now(UTC) + timedelta(days=2),
        success_criteria=[{"type": "required_fields", "fields": ["summary"]}],
    )
    await drain(120)
    main = await task(str(main["id"]))
    assert main["status"] == "COMPLETED", (main["error"], await _events(main["id"]))
    kids = await rows("SELECT * FROM tasks WHERE parent_id = :p", {"p": main["id"]})
    assert len(kids) == 1 and kids[0]["status"] == "COMPLETED" and "15 giờ" in kids[0]["output_data"]["answer"]
    child = kids[0]
    assert child["created_by"] == "agent:marketing_director" and child["reviewer"] == "agent:marketing_director"
    reviews = await rows("SELECT round, verdict, reviewer FROM task_reviews WHERE task_id = :t ORDER BY round", {"t": child["id"]})
    assert [(r["round"], r["verdict"]) for r in reviews] == [(1, "request_changes"), (2, "approve")]
    types = [m["message_type"] for m in await rows("SELECT message_type FROM agent_messages ORDER BY created_at")]
    assert types.count("task_request") == 1 and types.count("review_request") == 2 and "task_response" in types
    review_tasks = await rows("SELECT status, assigned_agent FROM tasks WHERE task_type = 'review'")
    assert len(review_tasks) == 2 and all(r["status"] == "COMPLETED" for r in review_tasks)
    lesson = await rows("SELECT title, metadata FROM agent_memories WHERE owner_scope = 'agent:content_agent'")
    assert lesson[0]["title"].startswith("Bài học:") and lesson[0]["metadata"]["checks"][0]["text"] == "15 giờ"
    assert "children" in await _events(main["id"])


# ------------------------------------------------------------------ IT-LG-03: đối soát
async def test_it_lg_03_reconciler(office: FakeModel) -> None:
    from app.core import db
    from app.tasks import engine, graph, reconcile

    office.script = lambda *a: done({"answer": "ok"})
    a = await make_task(title="Việc bị bỏ dở", assigned_agent="seo_agent")
    b = await make_task(title="Việc quá giờ", assigned_agent="content_agent", max_attempts=1)
    c_ = await make_task(title="Chờ duyệt quá hạn", assigned_agent="social_agent", requires_approval=True)
    await drain()  # a, b chạy xong ngay; dựng lại tình huống bằng tay bên dưới
    async with db.engine().begin() as c:
        for t, extra in ((a, ""), (b, ", timeout_at = now() - interval '1 minute'")):
            await db.execute(c, "ALTER TABLE tasks DISABLE TRIGGER task_transition")
            await db.execute(
                c,
                f"UPDATE tasks SET status = 'IN_PROGRESS', lease_owner = 'dead', lease_until = now() - interval '5 minutes'{extra} WHERE id = :i",  # noqa: S608
                {"i": t["id"]},
            )
            await db.execute(c, "ALTER TABLE tasks ENABLE TRIGGER task_transition")
        await db.execute(c, "UPDATE approvals SET expires_at = now() - interval '1 second' WHERE status = 'pending'")
        g = await graph.setup()
        assert g is not None
        await db.execute(
            c,
            "INSERT INTO langgraph.checkpoints(thread_id, checkpoint_ns, checkpoint_id, checkpoint, metadata) "
            "VALUES ('khong-co-task', '', '1', '{}', '{}')",
        )
    rep = await reconcile.run()
    assert str(a["id"]) in rep.requeued
    assert str(b["id"]) in rep.timed_out and (await task(str(b["id"])))["status"] == "FAILED"
    assert rep.approvals_expired == 1 and rep.orphan_checkpoints == ["khong-co-task"]
    assert (await task(str(c_["id"])))["status"] == "IN_PROGRESS"  # đánh thức để kết thúc
    await drain()
    assert (await task(str(c_["id"])))["status"] == "CANCELLED"  # im lặng không phải đồng ý
    assert (await task(str(a["id"])))["status"] in ("COMPLETED", "IN_PROGRESS")
    assert engine.LEASE_S > 0
