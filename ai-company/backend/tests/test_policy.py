"""UT-POL-01…12: Policy Engine (SECURITY_PLAN §3.1–3.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.policy.engine import PolicyCtx, authorize
from tests.conftest import needs_db

pytestmark = [needs_db, pytest.mark.usefixtures("synced")]


async def grant(conn: AsyncConnection, agent: str, tool: str, action: str, level: int, **kw: Any) -> None:
    from app.domain.approvals import _json

    await db.execute(
        conn,
        "INSERT INTO agent_permissions(agent_key, tool_id, action, autonomy_level, limits, requires_approval, granted_by, expires_at) "
        "VALUES (:a, :t, :ac, :l, CAST(:lim AS jsonb), :ra, 'test', :e) ON CONFLICT (agent_key, tool_id, action) DO UPDATE "
        "SET autonomy_level = EXCLUDED.autonomy_level, limits = EXCLUDED.limits, requires_approval = EXCLUDED.requires_approval, expires_at = EXCLUDED.expires_at",
        {"a": agent, "t": tool, "ac": action, "l": level, "lim": _json(kw.get("limits", {})), "ra": kw.get("requires_approval", False), "e": kw.get("expires_at")},
    )


async def test_pol01_default_deny(conn: AsyncConnection) -> None:
    d = await authorize(conn, "social_agent", "site", "publish")
    assert d.kind == "deny" and d.rule == "no_permission" and "mặc định từ chối" in d.reason
    assert (await authorize(conn, "social_agent", "khong_co", "x")).rule == "unknown_tool"
    assert (await authorize(conn, "khong_co_agent", "signals", "read")).rule == "unknown_agent"


@pytest.mark.parametrize("level", [1, 2, 3, 4])
async def test_pol02_autonomy_matrix(conn: AsyncConnection, level: int) -> None:
    """Hành động cần L1 / L2 / L3: được phép khi và chỉ khi cấp của quyền ≥ cấp tối thiểu."""
    for action, min_level in (("catalog", 1), ("draft", 2), ("unpublish", 3)):
        await grant(conn, "creative_agent", "site", action, level)
        d = await authorize(conn, "creative_agent", "site", action)
        assert (d.kind == "allow") == (level >= min_level), (action, level, d)
        if level < min_level:
            assert d.rule == "autonomy_level" and f"L{min_level}" in d.reason


async def test_pol03_mandatory_approval_even_at_l4(conn: AsyncConnection) -> None:
    await grant(conn, "ads_agent", "ads", "change_budget", 4)
    d = await authorize(conn, "ads_agent", "ads", "change_budget")
    assert d.kind == "require_approval" and d.rule == "mandatory_approval" and d.risk == "high"


async def test_pol04_every_mandatory_tag_requires_approval(conn: AsyncConnection) -> None:
    from app.brain import registry

    const = (await registry.resolve(conn, "ai_ceo")).loaded.bundle.constitution
    await grant(conn, "ai_ceo", "report", "compose", 4)
    for tag in const.mandatory_approval_tags:
        d = await authorize(conn, "ai_ceo", "report", "compose", PolicyCtx(extra_tags=(tag,)))
        assert d.kind == "require_approval", tag
        assert d.risk == ("high" if tag in const.high_risk_tags else "medium"), tag


async def test_pol05_constitution_forbids_at_any_level(conn: AsyncConnection) -> None:
    await grant(conn, "ai_ceo", "report", "compose", 4)
    for tag in ("change_price", "payment", "read_secret", "self_grant"):
        d = await authorize(conn, "ai_ceo", "report", "compose", PolicyCtx(extra_tags=(tag,)))
        assert d.kind == "deny" and d.rule == "constitution", tag


async def test_pol06_daily_limit(conn: AsyncConnection) -> None:
    await grant(conn, "seo_agent", "site", "draft", 2, limits={"per_day": 2})
    for i in range(2):
        assert (await authorize(conn, "seo_agent", "site", "draft")).kind == "allow"
        await db.execute(
            conn,
            "INSERT INTO tool_invocations(id, tool_id, action, agent_key, idempotency_key, input_digest, status) "
            "VALUES (gen_random_uuid(), 'site', 'draft', 'seo_agent', :k, 'x', 'succeeded')",
            {"k": f"k{i}"},
        )
    d = await authorize(conn, "seo_agent", "site", "draft")
    assert d.kind == "deny" and d.rule == "daily_limit" and "2/2" in d.reason


async def test_pol07_taint_external_needs_approval(conn: AsyncConnection) -> None:
    tainted = PolicyCtx(tainted=True)
    d = await authorize(conn, "content_agent", "site", "draft", tainted)  # tác động ra ngoài (website)
    assert d.kind == "require_approval" and d.rule == "taint"
    assert (await authorize(conn, "content_agent", "site", "catalog", tainted)).kind == "allow"  # chỉ đọc: không sao
    assert (await authorize(conn, "content_agent", "site", "draft")).kind == "allow"


async def test_pol08_paused_or_degraded_agent_denied(conn: AsyncConnection) -> None:
    for st in ("paused", "degraded", "disabled"):
        await db.execute(conn, "UPDATE agent_status s SET state = :s FROM agents a WHERE a.id = s.agent_id AND a.agent_key = 'data_analyst'", {"s": st})
        assert (await authorize(conn, "data_analyst", "signals", "read")).rule == "agent_state"


async def test_pol09_permission_flagged_requires_approval(conn: AsyncConnection) -> None:
    d = await authorize(conn, "growth_director", "experiment", "launch_live")  # AGENT_DESIGN: thí nghiệm trên trang thật
    assert d.kind == "require_approval" and d.rule == "permission_requires_approval"


async def test_pol10_expired_permission_and_usd_limits(conn: AsyncConnection) -> None:
    await grant(conn, "web_cro_agent", "site", "page_audit", 1, expires_at=datetime.now(UTC) - timedelta(minutes=1))
    assert (await authorize(conn, "web_cro_agent", "site", "page_audit")).rule == "permission_expired"
    await grant(conn, "creative_agent", "image", "generate", 2, limits={"max_usd": 0.05})
    assert (await authorize(conn, "creative_agent", "image", "generate", PolicyCtx(estimated_usd=0.2))).rule == "usd_limit"
    await db.execute(conn, "INSERT INTO model_usage(model_id, agent_key, purpose, tokens_in, tokens_out, cost_usd, latency_ms, ok) "
                           "VALUES ('claude-haiku-5-5', 'creative_agent', 't', 1, 1, 0.049, 1, true)")
    d = await authorize(conn, "creative_agent", "image", "generate", PolicyCtx(estimated_usd=0.02))
    assert d.rule == "agent_budget" and "0.05" in d.reason  # trần riêng 0,05 USD/ngày của Thiết kế


async def test_pol11_every_decision_recorded_with_reason(conn: AsyncConnection) -> None:
    await authorize(conn, "social_agent", "site", "publish")
    await authorize(conn, "data_analyst", "signals", "read", PolicyCtx(task_id="t-1"))
    async with db.engine().connect() as c:
        rows = await db.all_(c, "SELECT agent_key, decision, rule, reason, context FROM policy_decisions ORDER BY id")
    assert [(r["agent_key"], r["decision"], r["rule"]) for r in rows] == [
        ("social_agent", "deny", "no_permission"),
        ("data_analyst", "allow", "permitted"),
    ]
    assert rows[1]["context"]["task_id"] == "t-1" and rows[0]["reason"]


async def test_pol12_approval_expired_or_digest_mismatch(conn: AsyncConnection) -> None:
    from app.domain import approvals

    payload = {"agent": "ads_agent", "tool": "ads", "action": "change_budget", "input": {"campaign": "c1", "usd": 5}}
    a = await approvals.create(conn, subject_type="tool_call", subject_id="k1", action="ads.change_budget", title="t", payload=payload,
                               risk="high", requested_by="agent:ads_agent")
    assert (await approvals.usable(conn, str(a["id"]), "tool_call", "k1", payload)) == (False, "phê duyệt đang ở trạng thái chờ duyệt")
    await approvals.decide(conn, str(a["id"]), True, "user:o")
    assert (await approvals.usable(conn, str(a["id"]), "tool_call", "k1", payload))[0]
    changed = {**payload, "input": {"campaign": "c1", "usd": 50}}
    assert (await approvals.usable(conn, str(a["id"]), "tool_call", "k1", changed)) == (False, "nội dung đã đổi sau khi được duyệt")
    assert (await approvals.usable(conn, str(a["id"]), "tool_call", "k2", payload))[1] == "phê duyệt dành cho việc khác"
    await db.execute(conn, "UPDATE approvals SET expires_at = now() - interval '1 second' WHERE id = :i", {"i": a["id"]})
    assert (await approvals.usable(conn, str(a["id"]), "tool_call", "k1", payload)) == (False, "phê duyệt đã hết hạn")
    # Yêu cầu chờ duyệt quá hạn tự chuyển "hết hạn" (im lặng không phải đồng ý)
    b = await approvals.create(conn, subject_type="tool_call", subject_id="k3", action="x", title="t", payload=payload, risk="low", requested_by="x")
    await db.execute(conn, "UPDATE approvals SET expires_at = now() - interval '1 second' WHERE id = :i", {"i": b["id"]})
    assert await approvals.expire_due(conn) == 1
    from app.core.errors import AppError

    with pytest.raises(AppError) as e:
        await approvals.decide(conn, str(b["id"]), True, "user:o")
    assert e.value.code == "APPROVAL_NOT_PENDING" and "hết hạn" in e.value.message
