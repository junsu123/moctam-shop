"""API Task Engine: Owner giao việc, xem từng bước, review thay mặt Owner, hủy/chạy lại; văn phòng trực tiếp; lịch tự động."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import OwnerSession, needs_db
from tests.officekit import FakeModel, done, drain

pytestmark = needs_db


async def test_owner_gives_task_reviews_and_sees_steps(api: AsyncClient, owner: OwnerSession, office: FakeModel) -> None:
    def script(agent: str, phase: str, title: str, prompt: str) -> dict[str, Any]:
        if "Góp ý của Owner" in prompt:
            return done({"post": "Trà gừng mật ong ấm bụng ngày se lạnh. Đặt trước 15 giờ, gửi sáng hôm sau."})
        return done({"post": "Trà gừng mật ong ấm bụng ngày se lạnh."})

    office.script = script
    r = await api.post(
        "/api/v1/tasks",
        headers=owner.h,
        json={
            "agent": "social_agent",
            "title": "Viết bài Facebook về trà gừng",
            "success_criteria": ["giọng thân thiện", "dưới 300 chữ"],
            "budget_usd": 0.3,
            "requires_review": True,
        },
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    await drain()
    d = (await api.get(f"/api/v1/tasks/{tid}")).json()
    assert d["task"]["status"] == "WAITING_REVIEW" and d["can_review"] and d["next_round"] == 1
    assert [x["event"] for x in d["logs"]][-1] == "status"
    r = await api.post(f"/api/v1/tasks/{tid}/review", headers=owner.h, json={"verdict": "request_changes", "notes": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REVIEW_NOTES_REQUIRED"
    r = await api.post(
        f"/api/v1/tasks/{tid}/review", headers=owner.h, json={"verdict": "request_changes", "notes": "Thêm giờ chốt đơn 15 giờ"}
    )
    assert r.status_code == 200 and r.json()["round"] == 1
    await drain()
    d = (await api.get(f"/api/v1/tasks/{tid}")).json()
    assert d["task"]["status"] == "WAITING_REVIEW" and d["next_round"] == 2
    assert "Thêm giờ chốt đơn" in office.calls[-1]["prompt"]  # góp ý của Owner vào lượt làm lại
    await api.post(f"/api/v1/tasks/{tid}/review", headers=owner.h, json={"verdict": "approve"})
    await drain()
    d = (await api.get(f"/api/v1/tasks/{tid}")).json()
    assert d["task"]["status"] == "COMPLETED" and "15 giờ" in d["task"]["output_data"]["post"]
    assert [(x["round"], x["verdict"]) for x in d["reviews"]] == [(1, "request_changes"), (2, "approve")]
    lst = (await api.get("/api/v1/tasks", params={"group": "done", "top": True})).json()
    assert lst["total"] == 1 and lst["items"][0]["agent_name"]
    st = (await api.get("/api/v1/tasks/stats")).json()
    assert st["groups"]["done"] == 1 and st["spent_today_usd"] > 0
    st = (await api.get(f"/api/v1/tasks/{tid}/state")).json()
    assert st["exists"] and st["next"] == [] and st["round"] == 2
    ev = (await api.get("/api/v1/events")).json()
    assert any(e["source"] == "task" and e["task_id"] == tid for e in ev)  # bước của task lên màn hình Diễn biến


async def test_cancel_retry_live_and_errors(api: AsyncClient, owner: OwnerSession, office: FakeModel) -> None:
    r = await api.post("/api/v1/tasks", headers=owner.h, json={"agent": "khong_co", "title": "Việc lạ"})
    assert r.status_code == 404
    r = await api.post("/api/v1/tasks", headers=owner.h, json={"agent": "seo_agent", "title": "Rà từ khóa", "deadline": "2020-01-01"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "TASK_DEADLINE_PAST"
    tid = (await api.post("/api/v1/tasks", headers=owner.h, json={"agent": "seo_agent", "title": "Rà từ khóa trà sen"})).json()["id"]
    live = (await api.get("/api/v1/live")).json()
    seo = next(a for a in live["agents"] if a["agent_key"] == "seo_agent")
    assert seo["queued"] == 1 and live["need_owner"] == {"approvals": 0, "reviews": 0, "failed": 0}
    assert (await api.post(f"/api/v1/tasks/{tid}/retry", headers=owner.h)).status_code == 409
    r = await api.post(f"/api/v1/tasks/{tid}/cancel", headers=owner.h, json={"reason": "đổi ưu tiên"})
    assert r.status_code == 200 and r.json()["cancelled"] == 1
    assert (await api.post(f"/api/v1/tasks/{tid}/cancel", headers=owner.h, json={"reason": "lần nữa"})).status_code == 409
    assert (await api.get("/api/v1/tasks/khong-phai-uuid")).status_code == 404
    assert (await api.post("/api/v1/tasks", json={"agent": "seo_agent", "title": "Không CSRF"})).status_code == 403


async def test_schedules_crud(api: AsyncClient, owner: OwnerSession, office: FakeModel) -> None:
    body = {"name": "Báo cáo sáng", "agent": "data_analyst", "cron": "0 7 * * *", "title": "Báo cáo số liệu hôm qua"}
    assert (await api.post("/api/v1/schedules", headers=owner.h, json={**body, "cron": "0 25 * * *"})).json()["error"][
        "code"
    ] == "CRON_INVALID"
    r = await api.post("/api/v1/schedules", headers=owner.h, json=body)
    assert r.status_code == 201
    sid = r.json()["id"]
    assert (await api.post("/api/v1/schedules", headers=owner.h, json=body)).status_code == 409
    lst = (await api.get("/api/v1/schedules")).json()
    assert lst[0]["name"] == "Báo cáo sáng" and lst[0]["next_run_at"]
    r = await api.patch(f"/api/v1/schedules/{sid}", headers=owner.h, json={"enabled": False})
    assert r.json() == {"enabled": False, "next_run_at": None}
    assert (await api.delete(f"/api/v1/schedules/{sid}", headers=owner.h)).status_code == 200
    assert (await api.get("/api/v1/schedules")).json() == []
