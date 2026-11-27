"""Policy Engine (SECURITY_PLAN §3.1): authorize(agent, công cụ, hành động, ngữ cảnh) → Allow | RequireApproval | Deny.

Thứ tự (dừng ở luật đầu tiên khớp):
 1. Công cụ/hành động có trong registry? Không → Deny (mặc định từ chối).
 2. Agent đang tạm dừng/lỗi/tắt → Deny.
 3. Bộ não nạp được (hash cốt lõi đã ghim)? Không → Deny.
 4. Hiến pháp cấm (đổi giá, thanh toán, đọc secret…) → Deny, ở mọi cấp.
 5. Quyền (agent × công cụ × hành động): không có hoặc hết hạn → Deny (mặc định từ chối).
 6. Cấp tự chủ của quyền thấp hơn cấp tối thiểu của hành động → Deny.
 7. Hạn mức: số lần/ngày, USD mỗi lần, ngân sách AI/ngày của agent → Deny.
 8. Danh sách bắt buộc người duyệt (hiến pháp) → RequireApproval, kể cả khi quyền ở L4.
 9. Quyền đánh dấu `requires_approval` → RequireApproval.
10. Ngữ cảnh "nhiễm" (đã đọc dữ liệu ngoài chưa xác minh) + hành động tác động ra ngoài → RequireApproval.
11. Còn lại → Allow.
Mỗi quyết định được ghi vào `policy_decisions` (kết nối riêng, commit ngay) để dashboard trả lời "vì sao bị chặn".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

from app.brain import registry as brains
from app.brain.loader import BrainError
from app.core import db
from app.domain.lifecycle import BLOCKED, STATE_TEXT
from app.tools import spec as tools

VN = ZoneInfo("Asia/Ho_Chi_Minh")
Kind = Literal["allow", "require_approval", "deny"]


@dataclass(frozen=True)
class PolicyCtx:
    tainted: bool = False  # bước này được sinh sau khi đọc dữ liệu ngoài chưa xác minh
    extra_tags: tuple[str, ...] = ()  # vd Content Gate gắn "publish_risky"
    estimated_usd: float = 0.0
    task_id: str | None = None


@dataclass(frozen=True)
class Decision:
    kind: Kind
    rule: str
    reason: str
    risk: Literal["low", "medium", "high"] = "low"
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def allowed(self) -> bool:
        return self.kind == "allow"


def _deny(rule: str, reason: str) -> Decision:
    return Decision("deny", rule, reason)


async def _decide(conn: AsyncConnection, agent: str, tool_id: str, action: str, ctx: PolicyCtx) -> Decision:
    t = tools.get(tool_id)
    a = t.actions.get(action) if t else None
    if t is None or a is None:
        return _deny("unknown_tool", f"Công cụ {tool_id}.{action} không có trong Tool Registry")
    state = await db.scalar(
        conn, "SELECT s.state FROM agent_status s JOIN agents ag ON ag.id = s.agent_id WHERE ag.agent_key = :k", {"k": agent}
    )
    if state is None:
        return _deny("unknown_agent", f"Không có agent {agent}")
    if state in BLOCKED:
        return _deny("agent_state", f"Agent đang {STATE_TEXT[state]}")
    try:
        brain = await brains.resolve(conn, agent)
    except BrainError as e:
        return _deny("brain", "Bộ não không nạp được: " + "; ".join(e.problems))
    const = brain.loaded.bundle.constitution
    tags = tuple(dict.fromkeys((*a.tags, *ctx.extra_tags)))
    if hit := [g for g in tags if g in const.forbidden_tags]:
        return _deny("constitution", "Hiến pháp cấm: " + "; ".join(const.forbidden_tags[g] for g in hit))
    perm = await db.one(
        conn,
        "SELECT * FROM agent_permissions WHERE agent_key = :a AND tool_id = :t AND action = :ac",
        {"a": agent, "t": tool_id, "ac": action},
    )
    if perm is None:
        return _deny("no_permission", f"Agent không có quyền {tool_id}.{action} (mặc định từ chối)")
    if perm["expires_at"] and perm["expires_at"] <= datetime.now(UTC):
        return _deny("permission_expired", f"Quyền {tool_id}.{action} đã hết hạn")
    if perm["autonomy_level"] < a.min_level:
        return _deny(
            "autonomy_level",
            f"Quyền ở cấp L{perm['autonomy_level']} ({tools.LEVEL_NAMES[perm['autonomy_level']]}), "
            f"hành động cần tối thiểu L{a.min_level} ({tools.LEVEL_NAMES[a.min_level]})",
        )
    limits = perm["limits"] or {}
    if per_day := limits.get("per_day"):
        day0 = datetime.now(VN).replace(hour=0, minute=0, second=0, microsecond=0)
        used = int(
            await db.scalar(
                conn,
                "SELECT count(*) FROM tool_invocations WHERE agent_key = :a AND tool_id = :t AND action = :ac AND at >= :d "
                "AND status IN ('succeeded','running')",
                {"a": agent, "t": tool_id, "ac": action, "d": day0},
            )
            or 0
        )
        if used >= per_day:
            return _deny("daily_limit", f"Đã dùng {used}/{per_day} lần {tool_id}.{action} hôm nay")
    if (max_usd := limits.get("max_usd")) is not None and ctx.estimated_usd > float(max_usd):
        return _deny("usd_limit", f"Ước tính {ctx.estimated_usd:.2f} USD vượt hạn mức {float(max_usd):.2f} USD mỗi lần")
    if ctx.estimated_usd > 0:
        day0 = datetime.now(VN).replace(hour=0, minute=0, second=0, microsecond=0)
        spent = float(
            await db.scalar(
                conn, "SELECT COALESCE(SUM(cost_usd), 0) FROM model_usage WHERE agent_key = :a AND at >= :d", {"a": agent, "d": day0}
            )
            or 0
        )
        cap = brain.loaded.bundle.budget.usd_per_day
        if spent + ctx.estimated_usd > cap:
            return _deny("agent_budget", f"Ngân sách AI hôm nay của agent: đã dùng {spent:.2f}/{cap:.2f} USD")
    if hit := [g for g in tags if g in const.mandatory_approval_tags]:
        risk: Literal["low", "medium", "high"] = "high" if set(hit) & set(const.high_risk_tags) else "medium"
        return Decision(
            "require_approval",
            "mandatory_approval",
            "Luôn cần người duyệt: " + "; ".join(const.mandatory_approval_tags[g] for g in hit),
            risk,
            tags,
        )
    if perm["requires_approval"]:
        return Decision(
            "require_approval",
            "permission_requires_approval",
            f"Quyền {tool_id}.{action} của agent này luôn cần người duyệt",
            "medium",
            tags,
        )
    if ctx.tainted and a.side_effects == "external":
        return Decision(
            "require_approval",
            "taint",
            "Kế hoạch được lập sau khi đọc dữ liệu bên ngoài chưa xác minh; hành động ra ngoài cần người duyệt",
            "medium",
            tags,
        )
    return Decision("allow", "permitted", f"Được phép ở cấp L{perm['autonomy_level']}", "low", tags)


async def authorize(conn: AsyncConnection, agent: str, tool_id: str, action: str, ctx: PolicyCtx | None = None) -> Decision:
    ctx = ctx or PolicyCtx()
    d = await _decide(conn, agent, tool_id, action, ctx)
    async with db.engine().begin() as c:
        from app.domain.approvals import _json

        await db.execute(
            c,
            "INSERT INTO policy_decisions(agent_key, tool_id, action, decision, rule, reason, context) VALUES (:a, :t, :ac, :d, :r, :re, CAST(:c AS jsonb))",
            {"a": agent, "t": tool_id, "ac": action, "d": d.kind, "r": d.rule, "re": d.reason[:500], "c": _json(asdict(ctx))},
        )
    return d
